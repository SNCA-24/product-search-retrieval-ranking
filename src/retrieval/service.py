from __future__ import annotations

from pathlib import Path
import time
from uuid import uuid4
from dataclasses import replace
from threading import Lock

import numpy as np
import pandas as pd

from common.config import AppSettings
from common.io import ensure_dir
from common.runtime import require_optional
from common.types import SearchRequest, SearchResponse, SearchResult
from indexing.opensearch import explain_document, search_bm25, search_vector
from ranking.service import OnlineLTRRanker
from retrieval.cache import load_run_cache, save_run_cache


def _rrf_fuse(
    bm25_hits: list[dict],
    vector_hits: list[dict],
    final_k: int,
    rrf_k: int = 60,
) -> list[dict]:
    fused: dict[str, dict] = {}
    for source_name, hits in [("bm25", bm25_hits), ("vector", vector_hits)]:
        for rank, hit in enumerate(hits, start=1):
            doc_id = hit["_id"]
            existing = fused.setdefault(
                doc_id,
                {
                    "hit": hit,
                    "rrf_score": 0.0,
                    "raw_scores": {"bm25": 0.0, "vector": 0.0},
                    "source_ranks": {"bm25_rank": None, "vector_rank": None},
                },
            )
            existing["rrf_score"] += 1.0 / (rrf_k + rank)
            existing["raw_scores"][source_name] = float(hit["_score"])
            existing["source_ranks"][f"{source_name}_rank"] = rank
    ranked = sorted(fused.values(), key=lambda item: item["rrf_score"], reverse=True)
    for rank, item in enumerate(ranked, start=1):
        item["hit"]["_score"] = item["rrf_score"]
        item["hit"]["_rrf_raw_scores"] = item["raw_scores"]
        item["hit"]["_rank"] = rank
        item["hit"]["_rrf_rank_positions"] = {
            **item["source_ranks"],
            "hybrid_rank": rank,
        }
    return [item["hit"] for item in ranked[:final_k]]


class OpenSearchRetriever:
    def __init__(self, settings: AppSettings, profile: str) -> None:
        self.settings = settings
        self.profile = settings.resolved_profile(profile)
        self._embedding_model = None
        self._ranker = None
        self._embedding_model_lock = Lock()
        self._ranker_lock = Lock()

    def _embedding_model_instance(self):
        if self._embedding_model is None:
            with self._embedding_model_lock:
                if self._embedding_model is None:
                    sentence_transformers = require_optional("sentence_transformers", "retrieval")
                    self._embedding_model = sentence_transformers.SentenceTransformer(
                        self.settings.models["embeddings"]["name"],
                        device="cpu",
                    )
        return self._embedding_model

    def _query_embedding(self, query: str) -> list[float]:
        model = self._embedding_model_instance()
        vector = model.encode([query], normalize_embeddings=True, convert_to_numpy=True)[0]
        return vector.astype(np.float32).tolist()

    def _ranker_instance(self) -> OnlineLTRRanker:
        if self._ranker is None:
            with self._ranker_lock:
                if self._ranker is None:
                    self._ranker = OnlineLTRRanker(settings=self.settings, profile=self.profile)
        return self._ranker

    def _candidate_depth(self, requested_k: int) -> int:
        ranking_config = self.settings.models.get("ranking", {})
        configured_depth = int(
            ranking_config.get("online_candidate_depth", self.settings.profile_config(self.profile).top_k)
        )
        return max(configured_depth, requested_k)

    def _vector_search_size(self, candidate_depth: int) -> int:
        ranking_config = self.settings.models.get("ranking", {})
        multiplier = int(ranking_config.get("online_vector_search_multiplier", 2))
        return max(candidate_depth * multiplier, candidate_depth)

    @staticmethod
    def _filter_hits(hits: list[dict], brand: str | None, color: str | None, k: int) -> list[dict]:
        filtered: list[dict] = []
        for hit in hits:
            source = hit["_source"]
            if brand and source.get("product_brand") != brand:
                continue
            if color and source.get("product_color") != color:
                continue
            filtered.append(hit)
            if len(filtered) >= k:
                break
        return filtered

    def _bm25_hits(self, request: SearchRequest, size: int) -> list[dict]:
        return search_bm25(
            self.settings,
            query=request.query,
            locale=request.locale,
            size=size,
            brand=request.brand,
            color=request.color,
        )

    def _vector_hits(
        self,
        request: SearchRequest,
        size: int,
        *,
        query_vector: list[float] | None = None,
        search_size: int | None = None,
    ) -> list[dict]:
        vector_hits = search_vector(
            self.settings,
            query_vector=query_vector if query_vector is not None else self._query_embedding(request.query),
            locale=request.locale,
            size=search_size if search_size is not None else max(size * 5, self.settings.profile_config(self.profile).top_k),
        )
        return self._filter_hits(vector_hits, request.brand, request.color, size)

    def _fuse_hits(self, bm25_hits: list[dict], vector_hits: list[dict], final_k: int) -> list[dict]:
        return _rrf_fuse(bm25_hits, vector_hits, final_k=final_k)

    def _hybrid_hits(self, request: SearchRequest, size: int) -> list[dict]:
        depth = max(size * 5, self.settings.profile_config(self.profile).top_k)
        bm25_hits = search_bm25(
            self.settings,
            query=request.query,
            locale=request.locale,
            size=depth,
        )
        vector_hits = search_vector(
            self.settings,
            query_vector=self._query_embedding(request.query),
            locale=request.locale,
            size=depth,
        )
        filtered_bm25 = self._filter_hits(bm25_hits, request.brand, request.color, depth)
        filtered_vector = self._filter_hits(vector_hits, request.brand, request.color, depth)
        return _rrf_fuse(filtered_bm25, filtered_vector, final_k=size)

    def _retrieve_hits(self, request: SearchRequest, mode: str, size: int) -> list[dict]:
        if mode == "bm25":
            return self._bm25_hits(request, size=size)
        if mode == "vector":
            return self._vector_hits(request, size=size)
        if mode == "hybrid":
            return self._hybrid_hits(request, size=size)
        raise ValueError(f"Unsupported retrieval mode '{mode}'.")

    @staticmethod
    def _format_results(hits: list[dict], default_score_key: str) -> list[SearchResult]:
        results: list[SearchResult] = []
        for rank, hit in enumerate(hits, start=1):
            source = hit["_source"]
            raw_scores = hit.get("_rrf_raw_scores", {default_score_key: float(hit["_score"])})
            raw_scores = {**raw_scores, default_score_key: float(hit["_score"])}
            rank_positions = hit.get("_rrf_rank_positions", {})
            if default_score_key == "bm25":
                rank_positions = {"bm25_rank": rank}
            elif default_score_key == "vector":
                rank_positions = {"vector_rank": rank}
            elif default_score_key == "hybrid":
                rank_positions = {**rank_positions, "hybrid_rank": rank}
            results.append(
                SearchResult(
                    product_id=source["product_id"],
                    product_locale=source["product_locale"],
                    product_title=source.get("product_title", ""),
                    product_brand=source.get("product_brand", ""),
                    product_color=source.get("product_color", ""),
                    score=float(hit["_score"]),
                    rank=rank,
                    searchable_text=source.get("searchable_text", ""),
                    raw_scores=raw_scores,
                    debug_details={
                        "rank_positions": rank_positions,
                        "raw_metadata": {
                            "product_id": source.get("product_id", ""),
                            "locale": source.get("product_locale", ""),
                            "brand": source.get("product_brand", ""),
                            "color": source.get("product_color", ""),
                        },
                    },
                    product_description=source.get("product_description", ""),
                    product_bullet_point=source.get("product_bullet_point", ""),
                    product_text=source.get("product_text", ""),
                )
            )
        return results

    def search(self, request: SearchRequest, allow_fallbacks: bool = True) -> SearchResponse:
        if request.locale != "us":
            raise ValueError("Only locale=us is supported in v1.")

        timings: dict[str, float] = {}
        requested_mode = request.mode
        fallback_triggered = False
        fallback_reason = None
        request_id = uuid4().hex[:12]

        try:
            started = time.perf_counter()
            if request.mode in {"bm25", "vector", "hybrid"}:
                hits = self._retrieve_hits(request, request.mode, request.k)
                used_mode = request.mode
                results = self._format_results(hits, request.mode)
            elif request.mode == "ltr":
                candidate_k = self._candidate_depth(request.k)
                query_vector = self._query_embedding(request.query)
                bm25_hits = self._bm25_hits(request, size=candidate_k)
                vector_hits = self._vector_hits(
                    request,
                    size=candidate_k,
                    query_vector=query_vector,
                    search_size=self._vector_search_size(candidate_k),
                )
                union_size = len({hit["_id"] for hit in bm25_hits + vector_hits})
                hybrid_hits = self._fuse_hits(
                    bm25_hits,
                    vector_hits,
                    final_k=max(union_size, request.k),
                )
                timings["retrieval"] = (time.perf_counter() - started) * 1000

                ranking_started = time.perf_counter()
                results = self._ranker_instance().rank(
                    request,
                    bm25_results=self._format_results(bm25_hits, "bm25"),
                    vector_results=self._format_results(vector_hits, "vector"),
                    hybrid_results=self._format_results(hybrid_hits, "hybrid"),
                )
                timings["feature_hydration_and_l2"] = (time.perf_counter() - ranking_started) * 1000
                used_mode = "ltr"
            else:
                raise ValueError(f"Unsupported search mode '{request.mode}'.")
            if request.mode != "ltr":
                timings["retrieval"] = (time.perf_counter() - started) * 1000
        except Exception as exc:
            if not allow_fallbacks or request.mode == "bm25":
                raise
            fallback_triggered = True
            fallback_reason = str(exc)
            fallback_mode = "hybrid" if request.mode == "ltr" else "bm25"
            fallback_request = replace(request, mode=fallback_mode)
            fallback_response = self.search(fallback_request, allow_fallbacks=fallback_mode != "bm25")
            return SearchResponse(
                query=request.query,
                requested_mode=requested_mode,
                used_mode=fallback_response.used_mode,
                locale=request.locale,
                results=fallback_response.results,
                timings_ms=fallback_response.timings_ms,
                request_id=request_id,
                fallback_triggered=fallback_triggered,
                fallback_reason=fallback_reason,
            )

        return SearchResponse(
            query=request.query,
            requested_mode=requested_mode,
            used_mode=used_mode,
            locale=request.locale,
            results=results,
            timings_ms=timings,
            request_id=request_id,
            fallback_triggered=fallback_triggered,
            fallback_reason=fallback_reason,
        )

    def explain(self, request: SearchRequest, product_id: str) -> dict:
        if request.mode == "ltr":
            return {
                "mode": "ltr",
                "candidate_mode": "hybrid",
                "ranker": self._ranker_instance().explain_metadata(),
                "note": "LTR reranks the BM25/vector candidate union using the selected XGBoost model.",
            }
        document_id = f"{request.locale}:{product_id}"
        payload = explain_document(
            self.settings,
            document_id=document_id,
            query=request.query,
            locale=request.locale,
            brand=request.brand,
            color=request.color,
        )
        if request.mode == "hybrid":
            payload["hybrid_note"] = "Hybrid ranking uses client-side RRF over BM25 and vector retrieval."
        return payload

    def benchmark_queries(
        self,
        queries: pd.DataFrame,
        split: str,
        mode: str,
        use_cache: bool = True,
    ) -> Path:
        cache_dir = ensure_dir(self.settings.cache_root / "retrieval" / self.profile)
        runs_dir = ensure_dir(self.settings.evaluation_dir(self.profile) / "runs")
        cache_path = cache_dir / f"{mode}_{split}.csv"
        run_path = runs_dir / f"{mode}_{split}.csv"

        cached = load_run_cache(cache_path) if use_cache else None
        if cached is not None:
            cached.to_csv(run_path, index=False)
            return run_path

        rows: list[dict[str, object]] = []
        for _, row in queries.iterrows():
            response = self.search(
                SearchRequest(
                    query=row["query"],
                    mode=mode,
                    locale=row["product_locale"],
                    k=self.settings.profile_config(self.profile).top_k,
                ),
                allow_fallbacks=False,
            )
            for result in response.results:
                rows.append(
                    {
                        "query_id": row["query_id"],
                        "product_id": result.product_id,
                        "score": result.score,
                        "rank": result.rank,
                        "system": mode,
                    }
                )

        frame = pd.DataFrame(rows)
        save_run_cache(cache_path, frame)
        frame.to_csv(run_path, index=False)
        return run_path
