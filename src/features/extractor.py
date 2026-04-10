from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from common.config import AppSettings
from common.io import ensure_dir, write_json
from common.runtime import stable_hash_int
from common.text import tokenize


FEATURE_DESCRIPTIONS = {
    "bm25_score": "Raw BM25 score from the BM25 candidate run.",
    "vector_score": "Raw vector similarity score from the vector candidate run.",
    "hybrid_score": "Raw fused score from the hybrid candidate run.",
    "bm25_rank": "Candidate rank in the BM25 run.",
    "vector_rank": "Candidate rank in the vector run.",
    "hybrid_rank": "Candidate rank in the hybrid run.",
    "bm25_score_norm": "Per-query min-max normalized BM25 score.",
    "vector_score_norm": "Per-query min-max normalized vector score.",
    "hybrid_score_norm": "Per-query min-max normalized hybrid score.",
    "term_overlap": "Shared query/product-text token ratio.",
    "title_exact_match": "1 if the query text exactly matches the title, else 0.",
    "title_token_coverage": "Shared query/title token ratio.",
    "brand_exact_match": "1 if the product brand string appears in the query, else 0.",
    "color_mention_match": "1 if the product color string appears in the query, else 0.",
    "description_length": "Token count of product description.",
    "bullet_point_length": "Token count of product bullet points.",
    "query_length_bucket": "Bucketed query length: 0 short, 1 medium, 2 long.",
    "product_text_completeness": "Fraction of tracked text fields that are non-empty.",
    "text_field_coverage_score": "Count of non-empty tracked text fields.",
    "source_prior": "Normalized prior based on source frequency in the split.",
}

_QUERY_COLUMNS = ["query_id", "query", "split", "product_locale", "source"]
_JUDGMENT_COLUMNS = [
    "query_id",
    "product_id",
    "split",
    "esci_label",
    "grade_default",
    "grade_strict",
    "grade_amazon",
]
_DOCUMENT_COLUMNS = [
    "product_id",
    "product_title",
    "product_brand",
    "product_color",
    "product_description",
    "product_bullet_point",
    "product_text",
]


def _load_queries(settings: AppSettings, profile: str, split: str) -> pd.DataFrame:
    queries = pd.read_csv(settings.evaluation_dir(profile) / "queries.csv", usecols=_QUERY_COLUMNS)
    queries = queries[queries["split"] == split].drop_duplicates(subset=["query_id"]).copy()
    queries["query"] = queries["query"].fillna("").astype(str)
    queries["source"] = queries["source"].fillna("unknown").astype(str)
    queries["query_lower"] = queries["query"].str.strip().str.lower()
    queries["query_tokens"] = queries["query"].map(lambda value: frozenset(tokenize(value)))
    queries["query_token_count"] = queries["query_tokens"].map(len).astype(np.int16)
    queries["query_length_bucket"] = queries["query"].map(_query_length_bucket).astype(np.int8)
    source_frequency = queries["source"].value_counts(normalize=True).to_dict()
    queries["source_prior"] = queries["source"].map(source_frequency).fillna(0.0).astype(np.float32)
    return queries


def _load_judgments(settings: AppSettings, profile: str, split: str) -> pd.DataFrame:
    judgments = pd.read_csv(settings.evaluation_dir(profile) / "judgments.csv", usecols=_JUDGMENT_COLUMNS)
    judgments = judgments[judgments["split"] == split].copy()
    return judgments.drop_duplicates(subset=["query_id", "product_id"])


def _load_documents(settings: AppSettings, profile: str) -> pd.DataFrame:
    documents = pd.read_parquet(
        settings.processed_dir(profile) / "search_documents.parquet",
        columns=_DOCUMENT_COLUMNS,
    ).copy()
    for column in _DOCUMENT_COLUMNS[1:]:
        documents[column] = documents[column].fillna("").astype(str)
    documents["title_lower"] = documents["product_title"].str.strip().str.lower()
    documents["title_tokens"] = documents["product_title"].map(lambda value: frozenset(tokenize(value)))
    documents["product_text_tokens"] = documents["product_text"].map(lambda value: frozenset(tokenize(value)))
    documents["description_length"] = documents["product_description"].map(lambda value: len(tokenize(value))).astype(
        np.int32
    )
    documents["bullet_point_length"] = documents["product_bullet_point"].map(
        lambda value: len(tokenize(value))
    ).astype(np.int32)
    completeness_columns = [
        "product_title",
        "product_description",
        "product_bullet_point",
        "product_brand",
        "product_color",
    ]
    documents["text_field_coverage_score"] = (
        documents[completeness_columns].astype(str).apply(lambda row: sum(bool(value.strip()) for value in row), axis=1)
    ).astype(np.int8)
    documents["product_text_completeness"] = (
        documents["text_field_coverage_score"] / len(completeness_columns)
    ).astype(np.float32)
    documents["product_brand_lower"] = documents["product_brand"].str.lower()
    documents["product_color_lower"] = documents["product_color"].str.lower()
    return documents.drop(columns=["product_description", "product_bullet_point", "product_text"])


def _load_run(settings: AppSettings, profile: str, split: str, system: str) -> pd.DataFrame:
    path = settings.evaluation_dir(profile) / "runs" / f"{system}_{split}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"Missing candidate run '{path}'. Generate retrieval runs before feature extraction."
        )
    return pd.read_csv(path)


def _normalize_score(series: pd.Series) -> pd.Series:
    minimum = series.min()
    maximum = series.max()
    if pd.isna(minimum) or pd.isna(maximum) or minimum == maximum:
        return pd.Series(np.zeros(len(series), dtype=np.float32), index=series.index)
    return ((series - minimum) / (maximum - minimum)).astype(np.float32)


def _query_length_bucket(query: str) -> int:
    length = len(tokenize(query))
    if length <= 2:
        return 0
    if length <= 5:
        return 1
    return 2


def _overlap_ratio(query_tokens: frozenset[str], document_tokens: frozenset[str]) -> float:
    query_size = len(query_tokens)
    if query_size == 0 or not document_tokens:
        return 0.0
    return float(len(query_tokens & document_tokens) / query_size)


def _feature_dirs(settings: AppSettings, profile: str) -> Path:
    return ensure_dir(settings.processed_dir(profile) / "features")


def build_feature_dataset(settings: AppSettings, profile: str, split: str) -> Path:
    profile_name = settings.resolved_profile(profile)
    queries = _load_queries(settings, profile_name, split)
    judgments = _load_judgments(settings, profile_name, split)
    documents = _load_documents(settings, profile_name)
    bm25 = _load_run(settings, profile_name, split, "bm25").rename(
        columns={"score": "bm25_score", "rank": "bm25_rank"}
    )
    vector = _load_run(settings, profile_name, split, "vector").rename(
        columns={"score": "vector_score", "rank": "vector_rank"}
    )
    hybrid = _load_run(settings, profile_name, split, "hybrid").rename(
        columns={"score": "hybrid_score", "rank": "hybrid_rank"}
    )

    top_k = settings.profile_config(profile_name).top_k
    candidates = pd.concat(
        [
            bm25.loc[bm25["bm25_rank"] <= top_k, ["query_id", "product_id"]],
            vector.loc[vector["vector_rank"] <= top_k, ["query_id", "product_id"]],
        ],
        ignore_index=True,
    ).drop_duplicates(subset=["query_id", "product_id"])

    features = candidates.merge(
        bm25[["query_id", "product_id", "bm25_score", "bm25_rank"]],
        how="left",
        on=["query_id", "product_id"],
    )
    features = features.merge(
        vector[["query_id", "product_id", "vector_score", "vector_rank"]],
        how="left",
        on=["query_id", "product_id"],
    )
    features = features.merge(
        hybrid[["query_id", "product_id", "hybrid_score", "hybrid_rank"]],
        how="left",
        on=["query_id", "product_id"],
    )
    features = features.merge(
        judgments[["query_id", "product_id", "esci_label", "grade_default", "grade_strict", "grade_amazon"]],
        how="left",
        on=["query_id", "product_id"],
    )
    features = features.merge(
        queries[["query_id", "query", "product_locale", "source", "query_length_bucket", "source_prior"]],
        how="left",
        on="query_id",
    )
    features = features.merge(
        documents[
            [
                "product_id",
                "product_title",
                "product_brand",
                "product_color",
                "title_lower",
                "description_length",
                "bullet_point_length",
                "text_field_coverage_score",
                "product_text_completeness",
                "product_brand_lower",
                "product_color_lower",
            ]
        ],
        how="left",
        on="product_id",
    )
    features = features.fillna(
        {
            "bm25_score": 0.0,
            "vector_score": 0.0,
            "hybrid_score": 0.0,
            "bm25_rank": top_k + 1,
            "vector_rank": top_k + 1,
            "hybrid_rank": top_k + 1,
            "query": "",
            "product_locale": settings.filters["locale"],
            "source": "unknown",
            "query_length_bucket": 0,
            "source_prior": 0.0,
            "product_title": "",
            "product_brand": "",
            "product_color": "",
            "title_lower": "",
            "product_brand_lower": "",
            "product_color_lower": "",
            "description_length": 0,
            "bullet_point_length": 0,
            "text_field_coverage_score": 0,
            "product_text_completeness": 0.0,
            "esci_label": "Irrelevant",
            "grade_default": 0.0,
            "grade_strict": 0.0,
            "grade_amazon": 0.0,
        }
    )

    query_tokens_by_id = queries.set_index("query_id")["query_tokens"].to_dict()
    query_lower_by_id = queries.set_index("query_id")["query_lower"].to_dict()
    title_tokens_by_product = documents.set_index("product_id")["title_tokens"].to_dict()
    text_tokens_by_product = documents.set_index("product_id")["product_text_tokens"].to_dict()

    query_ids = features["query_id"].tolist()
    product_ids = features["product_id"].tolist()
    features["term_overlap"] = np.array(
        [
            _overlap_ratio(
                query_tokens_by_id.get(query_id, frozenset()),
                text_tokens_by_product.get(product_id, frozenset()),
            )
            for query_id, product_id in zip(query_ids, product_ids)
        ],
        dtype=np.float32,
    )
    features["title_token_coverage"] = np.array(
        [
            _overlap_ratio(
                query_tokens_by_id.get(query_id, frozenset()),
                title_tokens_by_product.get(product_id, frozenset()),
            )
            for query_id, product_id in zip(query_ids, product_ids)
        ],
        dtype=np.float32,
    )
    features["title_exact_match"] = np.array(
        [
            int(query_lower_by_id.get(query_id, "") == title_lower)
            for query_id, title_lower in zip(query_ids, features["title_lower"].tolist())
        ],
        dtype=np.int8,
    )
    features["brand_exact_match"] = np.array(
        [
            int(bool(brand_lower) and brand_lower in query_lower_by_id.get(query_id, ""))
            for query_id, brand_lower in zip(query_ids, features["product_brand_lower"].tolist())
        ],
        dtype=np.int8,
    )
    features["color_mention_match"] = np.array(
        [
            int(bool(color_lower) and color_lower in query_lower_by_id.get(query_id, ""))
            for query_id, color_lower in zip(query_ids, features["product_color_lower"].tolist())
        ],
        dtype=np.int8,
    )

    for column in ["bm25_score", "vector_score", "hybrid_score"]:
        features[column] = features[column].astype(np.float32)
        normalized_column = f"{column}_norm"
        features[normalized_column] = features.groupby("query_id")[column].transform(_normalize_score)

    for column in ["bm25_rank", "vector_rank", "hybrid_rank"]:
        features[column] = features[column].astype(np.int16)
    for column in [
        "description_length",
        "bullet_point_length",
        "query_length_bucket",
        "text_field_coverage_score",
        "title_exact_match",
        "brand_exact_match",
        "color_mention_match",
    ]:
        features[column] = features[column].astype(np.int16 if column.endswith("_length") else np.int8)
    for column in ["product_text_completeness", "source_prior", "grade_default", "grade_strict", "grade_amazon"]:
        features[column] = features[column].astype(np.float32)

    features["split"] = split
    if split == "train":
        features["fold"] = features["query_id"].map(
            lambda value: "train" if stable_hash_int(value) % 10 < 8 else "validation"
        )
    else:
        features["fold"] = "test"

    features = features.drop(columns=["title_lower", "product_brand_lower", "product_color_lower"])

    output_dir = _feature_dirs(settings, profile_name)
    feature_path = output_dir / f"{split}_ltr_features.parquet"
    dictionary_path = output_dir / "feature_dictionary.json"

    features.to_parquet(feature_path, index=False)
    write_json(dictionary_path, FEATURE_DESCRIPTIONS)
    return feature_path
