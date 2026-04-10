from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import numpy as np
import pandas as pd

from common.config import AppSettings
from common.io import ensure_dir, read_json, write_json
from common.runtime import require_optional
from indexing.embeddings import load_embedding_lookup
from indexing.mappings import product_index_mapping

DEFAULT_INDEX_BATCH_SIZE = 2500


def _client(settings: AppSettings):
    opensearchpy = require_optional("opensearchpy", "retrieval")
    parsed = urlparse(settings.opensearch["url"])
    return opensearchpy.OpenSearch(
        hosts=[
            {
                "host": parsed.hostname,
                "port": parsed.port,
            }
        ],
        use_ssl=bool(settings.opensearch["use_ssl"]),
        verify_certs=bool(settings.opensearch["verify_certs"]),
        timeout=int(settings.opensearch["request_timeout_seconds"]),
    )


def _checkpoint_dir(settings: AppSettings, profile: str) -> Any:
    profile_name = settings.resolved_profile(profile)
    return ensure_dir(settings.cache_root / "indexing" / profile_name)


def checkpoint_path(settings: AppSettings, profile: str) -> Any:
    return _checkpoint_dir(settings, profile) / "index_documents_checkpoint.json"


def clear_index_checkpoint(settings: AppSettings, profile: str) -> Any:
    path = checkpoint_path(settings, profile)
    if path.exists():
        path.unlink()
    return path


def _load_index_checkpoint(settings: AppSettings, profile: str) -> dict[str, Any] | None:
    path = checkpoint_path(settings, profile)
    if not path.exists():
        return None
    return read_json(path)


def _save_index_checkpoint(
    settings: AppSettings,
    profile: str,
    *,
    index_name: str,
    total_documents: int,
    batch_size: int,
    next_row_index: int,
    source: str,
    completed: bool,
) -> Any:
    path = checkpoint_path(settings, profile)
    payload = {
        "batch_size": int(batch_size),
        "completed": bool(completed),
        "index_name": index_name,
        "next_row_index": int(next_row_index),
        "profile": settings.resolved_profile(profile),
        "source": source,
        "total_documents": int(total_documents),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    write_json(path, payload)
    return path


def current_index_count(settings: AppSettings) -> int:
    client = _client(settings)
    index_name = settings.opensearch["index_name"]
    if not client.indices.exists(index=index_name):
        return 0
    return int(client.count(index=index_name)["count"])


def sync_index_checkpoint_from_live_count(
    settings: AppSettings,
    profile: str,
    batch_size: int = DEFAULT_INDEX_BATCH_SIZE,
) -> dict[str, Any]:
    profile_name = settings.resolved_profile(profile)
    documents = pd.read_parquet(
        settings.processed_dir(profile_name) / "search_documents.parquet",
        columns=["document_id"],
    )
    total_documents = int(len(documents))
    live_count = current_index_count(settings)
    if live_count >= total_documents:
        aligned_count = total_documents
    else:
        aligned_count = min((live_count // batch_size) * batch_size, total_documents)
    path = _save_index_checkpoint(
        settings,
        profile_name,
        index_name=settings.opensearch["index_name"],
        total_documents=total_documents,
        batch_size=batch_size,
        next_row_index=aligned_count,
        source="live_count_sync",
        completed=aligned_count >= total_documents,
    )
    return {
        "checkpoint_path": str(path),
        "live_count": live_count,
        "aligned_row_index": aligned_count,
        "total_documents": total_documents,
    }


def create_index(settings: AppSettings, force_recreate: bool = False) -> str:
    client = _client(settings)
    index_name = settings.opensearch["index_name"]
    exists = client.indices.exists(index=index_name)
    if exists and force_recreate:
        client.indices.delete(index=index_name)
        exists = False
    if not exists:
        client.indices.create(
            index=index_name,
            body=product_index_mapping(int(settings.models["embeddings"]["dimension"])),
        )
    return index_name


def _load_documents_with_embeddings(
    settings: AppSettings,
    profile: str,
) -> tuple[pd.DataFrame, np.ndarray]:
    profile_name = settings.resolved_profile(profile)
    documents = pd.read_parquet(settings.processed_dir(profile_name) / "search_documents.parquet")
    documents = documents.sort_values(["document_id"]).reset_index(drop=True)
    manifest, matrix = load_embedding_lookup(settings, profile_name)
    lookup = manifest[["document_id", "row_index"]].drop_duplicates(subset=["document_id"])
    documents = documents.merge(lookup, how="left", on="document_id")
    missing_embeddings = int(documents["row_index"].isna().sum())
    if missing_embeddings:
        raise ValueError(f"Missing embeddings for {missing_embeddings} search documents.")
    documents["row_index"] = documents["row_index"].astype(int)
    return documents, matrix


def _resolve_start_row(
    *,
    total_documents: int,
    checkpoint: dict[str, Any] | None,
    live_count: int,
    batch_size: int,
    bootstrap_from_live_count: bool,
) -> tuple[int, str]:
    aligned_live_count = min((live_count // batch_size) * batch_size, total_documents)
    if checkpoint is not None:
        checkpoint_row = int(checkpoint.get("next_row_index", 0))
        checkpoint_source = str(checkpoint.get("source", "batch"))
        if checkpoint_source == "batch":
            safe_row = min(checkpoint_row, aligned_live_count, total_documents)
        else:
            safe_row = aligned_live_count
        return safe_row, "checkpoint"
    if bootstrap_from_live_count and live_count > 0:
        safe_row = aligned_live_count
        return safe_row, "live_count_bootstrap"
    return 0, "fresh"


def index_documents(
    settings: AppSettings,
    profile: str,
    *,
    batch_size: int = DEFAULT_INDEX_BATCH_SIZE,
    reset_checkpoint: bool = False,
    bootstrap_from_live_count: bool = False,
) -> dict[str, int | bool | str]:
    helpers = require_optional("opensearchpy.helpers", "retrieval")

    profile_name = settings.resolved_profile(profile)
    client = _client(settings)
    index_name = settings.opensearch["index_name"]
    documents, matrix = _load_documents_with_embeddings(settings, profile_name)
    total_documents = int(len(documents))

    if reset_checkpoint:
        clear_index_checkpoint(settings, profile_name)

    checkpoint = _load_index_checkpoint(settings, profile_name)
    live_count = current_index_count(settings)
    start_row, resume_source = _resolve_start_row(
        total_documents=total_documents,
        checkpoint=checkpoint,
        live_count=live_count,
        batch_size=batch_size,
        bootstrap_from_live_count=bootstrap_from_live_count,
    )

    if start_row >= total_documents:
        _save_index_checkpoint(
            settings,
            profile_name,
            index_name=index_name,
            total_documents=total_documents,
            batch_size=batch_size,
            next_row_index=total_documents,
            source=resume_source,
            completed=True,
        )
        return {
            "already_complete": True,
            "batch_size": int(batch_size),
            "checkpoint_path": str(checkpoint_path(settings, profile_name)),
            "indexed_documents": total_documents,
            "resumed": start_row > 0,
            "start_row": start_row,
        }

    indexed_documents = start_row
    for batch_start in range(start_row, total_documents, batch_size):
        batch_end = min(batch_start + batch_size, total_documents)
        batch = documents.iloc[batch_start:batch_end]
        actions = []
        for row in batch.itertuples(index=False):
            payload = {
                "document_id": row.document_id,
                "product_id": row.product_id,
                "product_locale": row.product_locale,
                "product_title": row.product_title,
                "product_brand": row.product_brand,
                "product_color": row.product_color,
                "product_description": row.product_description,
                "product_bullet_point": row.product_bullet_point,
                "product_text": row.product_text,
                "searchable_text": row.searchable_text,
                "embedding": matrix[row.row_index].astype(np.float32).tolist(),
            }
            actions.append({"_index": index_name, "_id": row.document_id, "_source": payload})
        success, _ = helpers.bulk(client, actions, raise_on_error=True)
        indexed_documents += int(success)
        _save_index_checkpoint(
            settings,
            profile_name,
            index_name=index_name,
            total_documents=total_documents,
            batch_size=batch_size,
            next_row_index=batch_end,
            source="batch",
            completed=batch_end >= total_documents,
        )

    return {
        "already_complete": False,
        "batch_size": int(batch_size),
        "checkpoint_path": str(checkpoint_path(settings, profile_name)),
        "indexed_documents": indexed_documents,
        "resumed": start_row > 0,
        "start_row": start_row,
    }


def bm25_query(query: str, locale: str, brand: str | None, color: str | None, size: int) -> dict[str, Any]:
    filters: list[dict[str, Any]] = [{"term": {"product_locale": locale}}]
    if brand:
        filters.append({"term": {"product_brand": brand}})
    if color:
        filters.append({"term": {"product_color": color}})
    return {
        "size": size,
        "_source": True,
        "query": {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": query,
                            "fields": ["product_title^3", "searchable_text"],
                        }
                    }
                ],
                "filter": filters,
            }
        },
    }


def search_bm25(
    settings: AppSettings,
    query: str,
    locale: str,
    size: int,
    brand: str | None = None,
    color: str | None = None,
) -> list[dict[str, Any]]:
    client = _client(settings)
    response = client.search(
        index=settings.opensearch["index_name"],
        body=bm25_query(query=query, locale=locale, brand=brand, color=color, size=size),
    )
    return response["hits"]["hits"]


def search_vector(
    settings: AppSettings,
    query_vector: list[float],
    locale: str,
    size: int,
) -> list[dict[str, Any]]:
    client = _client(settings)
    response = client.search(
        index=settings.opensearch["index_name"],
        body={
            "size": size,
            "_source": True,
            "query": {"knn": {"embedding": {"vector": query_vector, "k": size}}},
            "post_filter": {"term": {"product_locale": locale}},
        },
    )
    return response["hits"]["hits"]


def explain_document(
    settings: AppSettings,
    document_id: str,
    query: str,
    locale: str,
    brand: str | None,
    color: str | None,
) -> dict[str, Any]:
    client = _client(settings)
    return client.explain(
        index=settings.opensearch["index_name"],
        id=document_id,
        body={"query": bm25_query(query=query, locale=locale, brand=brand, color=color, size=1)["query"]},
    )
