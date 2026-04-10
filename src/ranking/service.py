from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from common.config import AppSettings
from common.io import ensure_dir, read_json
from common.runtime import require_optional
from common.text import tokenize
from common.types import SearchRequest, SearchResult


class OnlineLTRRanker:
    def __init__(self, settings: AppSettings, profile: str) -> None:
        self.settings = settings
        self.profile = settings.resolved_profile(profile)
        self._selected_metadata_cache: dict[str, str] | None = None
        self._feature_columns_cache: list[str] | None = None
        self._product_stats_cache: pd.DataFrame | None = None
        self._xgb_module = None
        self._booster = None

    def _product_stats_path(self) -> Path | None:
        if not hasattr(self.settings, "processed_dir"):
            return None
        return self.settings.processed_dir(self.profile) / "features" / "online_product_stats.parquet"

    def _build_product_stats_store(self) -> Path | None:
        path = self._product_stats_path()
        if path is None:
            return None
        if path.exists():
            return path

        documents = pd.read_parquet(
            self.settings.processed_dir(self.profile) / "search_documents.parquet",
            columns=[
                "product_id",
                "product_title",
                "product_brand",
                "product_color",
                "product_description",
                "product_bullet_point",
            ],
        ).copy()
        for column in [
            "product_title",
            "product_brand",
            "product_color",
            "product_description",
            "product_bullet_point",
        ]:
            documents[column] = documents[column].fillna("").astype(str)

        documents["description_length"] = documents["product_description"].map(lambda value: len(tokenize(value))).astype(
            np.int32
        )
        documents["bullet_point_length"] = documents["product_bullet_point"].map(
            lambda value: len(tokenize(value))
        ).astype(np.int32)
        coverage_columns = [
            "product_title",
            "product_description",
            "product_bullet_point",
            "product_brand",
            "product_color",
        ]
        documents["text_field_coverage_score"] = (
            documents[coverage_columns]
            .astype(str)
            .apply(lambda row: sum(bool(value.strip()) for value in row), axis=1)
            .astype(np.int8)
        )
        documents["product_text_completeness"] = (
            documents["text_field_coverage_score"] / len(coverage_columns)
        ).astype(np.float32)
        documents["product_title_lower"] = documents["product_title"].str.strip().str.lower()
        documents["product_brand_lower"] = documents["product_brand"].str.strip().str.lower()
        documents["product_color_lower"] = documents["product_color"].str.strip().str.lower()

        output = documents[
            [
                "product_id",
                "description_length",
                "bullet_point_length",
                "text_field_coverage_score",
                "product_text_completeness",
                "product_title_lower",
                "product_brand_lower",
                "product_color_lower",
            ]
        ].drop_duplicates(subset=["product_id"])
        ensure_dir(path.parent)
        output.to_parquet(path, index=False)
        return path

    def _product_stats_lookup(self) -> pd.DataFrame:
        if self._product_stats_cache is None:
            path = self._build_product_stats_store()
            if path is None:
                self._product_stats_cache = pd.DataFrame()
            else:
                self._product_stats_cache = pd.read_parquet(path).set_index("product_id")
        return self._product_stats_cache

    def _selected_metadata(self) -> dict[str, str]:
        if self._selected_metadata_cache is None:
            path = self.settings.processed_dir(self.profile) / "models" / "selected_ranker.json"
            if not path.exists():
                raise FileNotFoundError(f"Missing selected ranker metadata at '{path}'.")
            self._selected_metadata_cache = read_json(path)
        return self._selected_metadata_cache

    def _feature_columns(self) -> list[str]:
        if self._feature_columns_cache is None:
            report_path = Path(self._selected_metadata()["report_path"])
            report = read_json(report_path)
            self._feature_columns_cache = list(report["feature_columns"])
        return self._feature_columns_cache

    def _xgb(self):
        if self._xgb_module is None:
            os.environ.setdefault("OMP_NUM_THREADS", "1")
            os.environ.setdefault("KMP_INIT_AT_FORK", "FALSE")
            os.environ.setdefault("KMP_BLOCKTIME", "0")
            self._xgb_module = require_optional("xgboost", "ranking")
        return self._xgb_module

    def _booster_instance(self):
        if self._booster is None:
            booster = self._xgb().Booster()
            booster.load_model(self._selected_metadata()["model_path"])
            booster.set_param({"nthread": 1})
            self._booster = booster
        return self._booster

    @staticmethod
    def _query_length_bucket(query: str) -> int:
        length = len(tokenize(query))
        if length <= 2:
            return 0
        if length <= 5:
            return 1
        return 2

    @staticmethod
    def _overlap_ratio(query_tokens: frozenset[str], document_tokens: frozenset[str]) -> float:
        if not query_tokens or not document_tokens:
            return 0.0
        return float(len(query_tokens & document_tokens) / len(query_tokens))

    @staticmethod
    def _normalize(values: list[float]) -> list[np.float32]:
        if not values:
            return []
        minimum = min(values)
        maximum = max(values)
        if minimum == maximum:
            return [np.float32(0.0) for _ in values]
        return [np.float32((value - minimum) / (maximum - minimum)) for value in values]

    @staticmethod
    def _result_maps(
        bm25_results: list[SearchResult],
        vector_results: list[SearchResult],
        hybrid_results: list[SearchResult],
    ) -> tuple[dict[str, SearchResult], dict[str, SearchResult], dict[str, SearchResult]]:
        return (
            {result.product_id: result for result in bm25_results},
            {result.product_id: result for result in vector_results},
            {result.product_id: result for result in hybrid_results},
        )

    def _build_feature_frame(
        self,
        request: SearchRequest,
        *,
        bm25_results: list[SearchResult],
        vector_results: list[SearchResult],
        hybrid_results: list[SearchResult],
    ) -> pd.DataFrame:
        candidate_limit = self.settings.profile_config(self.profile).top_k + 1
        query_text = request.query or ""
        query_lower = query_text.strip().lower()
        query_tokens = frozenset(tokenize(query_text))
        query_length_bucket = self._query_length_bucket(query_text)

        bm25_map, vector_map, hybrid_map = self._result_maps(bm25_results, vector_results, hybrid_results)
        candidate_ids = list(dict.fromkeys([result.product_id for result in bm25_results + vector_results]))
        stats_lookup = self._product_stats_lookup()
        stats_map: dict[str, dict[str, object]] = {}
        if not stats_lookup.empty and candidate_ids:
            stats_map = stats_lookup.reindex(candidate_ids).to_dict(orient="index")
        rows: list[dict[str, object]] = []

        for product_id in candidate_ids:
            bm25_result = bm25_map.get(product_id)
            vector_result = vector_map.get(product_id)
            hybrid_result = hybrid_map.get(product_id)
            base_result = bm25_result or vector_result or hybrid_result
            if base_result is None:
                continue

            product_title = base_result.product_title or ""
            product_brand = base_result.product_brand or ""
            product_color = base_result.product_color or ""
            product_description = base_result.product_description or ""
            product_bullet_point = base_result.product_bullet_point or ""
            product_text = base_result.product_text or base_result.searchable_text or ""

            precomputed = stats_map.get(product_id, {})
            title_lower = str(precomputed.get("product_title_lower") or product_title.strip().lower())
            brand_lower = str(precomputed.get("product_brand_lower") or product_brand.strip().lower())
            color_lower = str(precomputed.get("product_color_lower") or product_color.strip().lower())
            title_tokens = frozenset(tokenize(product_title))
            product_text_tokens = frozenset(tokenize(product_text))
            description_length = int(precomputed.get("description_length", len(tokenize(product_description))))
            bullet_point_length = int(precomputed.get("bullet_point_length", len(tokenize(product_bullet_point))))
            coverage_score = int(
                precomputed.get(
                    "text_field_coverage_score",
                    sum(
                        bool(value.strip())
                        for value in [
                            product_title,
                            product_description,
                            product_bullet_point,
                            product_brand,
                            product_color,
                        ]
                    ),
                )
            )
            completeness = float(precomputed.get("product_text_completeness", coverage_score / 5.0))
            row = {
                "product_id": base_result.product_id,
                "product_locale": base_result.product_locale,
                "query": query_text,
                "source": "unknown",
                "product_title": product_title,
                "product_brand": product_brand,
                "product_color": product_color,
                "bm25_score": float(bm25_result.score) if bm25_result else 0.0,
                "vector_score": float(vector_result.score) if vector_result else 0.0,
                "hybrid_score": float(hybrid_result.score) if hybrid_result else 0.0,
                "bm25_rank": int(bm25_result.rank) if bm25_result else candidate_limit,
                "vector_rank": int(vector_result.rank) if vector_result else candidate_limit,
                "hybrid_rank": int(hybrid_result.rank) if hybrid_result else candidate_limit,
                "term_overlap": self._overlap_ratio(query_tokens, product_text_tokens),
                "title_exact_match": int(query_lower == title_lower),
                "title_token_coverage": self._overlap_ratio(query_tokens, title_tokens),
                "brand_exact_match": int(bool(brand_lower) and brand_lower in query_lower),
                "color_mention_match": int(bool(color_lower) and color_lower in query_lower),
                "description_length": description_length,
                "bullet_point_length": bullet_point_length,
                "query_length_bucket": query_length_bucket,
                "product_text_completeness": completeness,
                "text_field_coverage_score": coverage_score,
                "source_prior": 0.0,
            }
            rows.append(row)

        features = pd.DataFrame(rows)
        if features.empty:
            return features
        for column in ["bm25_score", "vector_score", "hybrid_score"]:
            values = features[column].astype(float).tolist() if not features.empty else []
            features[f"{column}_norm"] = self._normalize(values)
        return features

    def rank(
        self,
        request: SearchRequest,
        *,
        bm25_results: list[SearchResult],
        vector_results: list[SearchResult],
        hybrid_results: list[SearchResult],
    ) -> list[SearchResult]:
        features = self._build_feature_frame(
            request,
            bm25_results=bm25_results,
            vector_results=vector_results,
            hybrid_results=hybrid_results,
        )
        if features.empty:
            return []

        feature_columns = self._feature_columns()
        matrix = self._xgb().DMatrix(features[feature_columns])
        scores = self._booster_instance().predict(matrix)
        features["ltr_score"] = scores.astype(np.float32)

        bm25_map, vector_map, hybrid_map = self._result_maps(bm25_results, vector_results, hybrid_results)
        ordered = features.sort_values(["ltr_score", "hybrid_rank", "bm25_rank", "product_id"], ascending=[False, True, True, True])

        results: list[SearchResult] = []
        for rank, row in enumerate(ordered.itertuples(index=False), start=1):
            if rank > request.k:
                break
            product_id = row.product_id
            base_result = bm25_map.get(product_id) or vector_map.get(product_id) or hybrid_map.get(product_id)
            if base_result is None:
                continue
            results.append(
                SearchResult(
                    product_id=base_result.product_id,
                    product_locale=base_result.product_locale,
                    product_title=base_result.product_title,
                    product_brand=base_result.product_brand,
                    product_color=base_result.product_color,
                    score=float(row.ltr_score),
                    rank=rank,
                    searchable_text=base_result.searchable_text,
                    raw_scores={
                        "ltr": float(row.ltr_score),
                        "bm25": float(row.bm25_score),
                        "vector": float(row.vector_score),
                        "hybrid": float(row.hybrid_score),
                    },
                    debug_details={
                        "rank_positions": {
                            "bm25_rank": int(row.bm25_rank),
                            "vector_rank": int(row.vector_rank),
                            "hybrid_rank": int(row.hybrid_rank),
                            "ltr_rank": rank,
                        },
                        "feature_snapshot": {
                            "term_overlap": float(row.term_overlap),
                            "title_exact_match": int(row.title_exact_match),
                            "title_token_coverage": float(row.title_token_coverage),
                            "brand_exact_match": int(row.brand_exact_match),
                            "color_mention_match": int(row.color_mention_match),
                            "text_field_coverage_score": int(row.text_field_coverage_score),
                            "product_text_completeness": float(row.product_text_completeness),
                            "bm25_score_norm": float(row.bm25_score_norm),
                            "vector_score_norm": float(row.vector_score_norm),
                            "hybrid_score_norm": float(row.hybrid_score_norm),
                        },
                        "raw_metadata": {
                            "product_id": base_result.product_id,
                            "locale": base_result.product_locale,
                            "brand": base_result.product_brand,
                            "color": base_result.product_color,
                        },
                    },
                    product_description=base_result.product_description,
                    product_bullet_point=base_result.product_bullet_point,
                    product_text=base_result.product_text,
                )
            )
        return results

    def explain_metadata(self) -> dict[str, str]:
        return self._selected_metadata()
