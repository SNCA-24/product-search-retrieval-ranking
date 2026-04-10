from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from common.config import AppSettings
from common.io import ensure_dir, write_json
from common.runtime import require_optional


@dataclass(frozen=True)
class EmbeddingArtifacts:
    matrix_path: Path
    manifest_path: Path
    metadata_path: Path


def embedding_dir(settings: AppSettings, profile: str) -> Path:
    return ensure_dir(settings.processed_dir(profile) / "embeddings")


def generate_product_embeddings(settings: AppSettings, profile: str) -> EmbeddingArtifacts:
    sentence_transformers = require_optional("sentence_transformers", "retrieval")
    profile_name = settings.resolved_profile(profile)
    docs_path = settings.processed_dir(profile_name) / "search_documents.parquet"
    documents = pd.read_parquet(docs_path)

    model_name = settings.models["embeddings"]["name"]
    batch_size = int(settings.models["embeddings"]["batch_size"])
    model = sentence_transformers.SentenceTransformer(model_name, device="cpu")
    matrix = model.encode(
        documents["searchable_text"].tolist(),
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    ).astype("float32")

    target_dir = embedding_dir(settings, profile_name)
    matrix_path = target_dir / "product_embeddings.npy"
    manifest_path = target_dir / "product_embedding_ids.parquet"
    metadata_path = target_dir / "metadata.json"

    np.save(matrix_path, matrix)
    manifest = documents[["document_id", "product_id", "product_locale"]].copy()
    manifest["row_index"] = np.arange(len(manifest))
    manifest.to_parquet(manifest_path, index=False)
    write_json(
        metadata_path,
        {
            "model_name": model_name,
            "dimension": int(matrix.shape[1]),
            "rows": int(matrix.shape[0]),
            "dtype": "float32",
        },
    )
    return EmbeddingArtifacts(matrix_path=matrix_path, manifest_path=manifest_path, metadata_path=metadata_path)


def load_embedding_lookup(settings: AppSettings, profile: str) -> tuple[pd.DataFrame, np.ndarray]:
    profile_name = settings.resolved_profile(profile)
    base_dir = embedding_dir(settings, profile_name)
    manifest = pd.read_parquet(base_dir / "product_embedding_ids.parquet")
    matrix = np.load(base_dir / "product_embeddings.npy")
    return manifest, matrix
