from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from common.config import AppSettings
from common.constants import RAW_COLUMNS, TEXT_COLUMNS
from common.io import ensure_dir, write_json
from common.runtime import stable_hash_int
from common.text import lexical_overlap_score, unique_join


@dataclass(frozen=True)
class PreparedArtifacts:
    train_examples: Path
    test_examples: Path
    search_documents: Path
    queries_csv: Path
    judgments_csv: Path
    baseline_train_run: Path
    baseline_test_run: Path
    data_quality_report: Path


def _read_split(path: Path, split_name: str) -> pd.DataFrame:
    frame = pd.read_parquet(path, columns=RAW_COLUMNS)
    frame["split"] = split_name
    return frame


def _stable_query_sample(query_ids: list[int], sample_size: int | None) -> set[int]:
    if sample_size is None or sample_size >= len(query_ids):
        return set(query_ids)
    ranked = sorted(query_ids, key=stable_hash_int)
    return set(ranked[:sample_size])


def _build_searchable_text(row: pd.Series) -> str:
    return unique_join(
        [
            row["product_title"],
            row["product_brand"],
            row["product_color"],
            row["product_description"],
            row["product_bullet_point"],
            row["product_text"],
        ]
    )


def _normalize_text_columns(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in TEXT_COLUMNS:
        normalized[column] = normalized[column].fillna("").astype(str)
    return normalized


def _attach_gain_columns(frame: pd.DataFrame, gain_mappings: dict[str, dict[str, float]]) -> pd.DataFrame:
    enriched = frame.copy()
    for mapping_name, mapping in gain_mappings.items():
        enriched[f"grade_{mapping_name}"] = enriched["esci_label"].map(mapping).astype(float)
    return enriched


def _load_and_filter(settings: AppSettings, split_name: str) -> pd.DataFrame:
    split_path = settings.train_path() if split_name == "train" else settings.test_path()
    frame = _read_split(split_path, split_name=split_name)
    frame = frame[
        (frame["product_locale"] == settings.filters["locale"])
        & (frame["small_version"] == settings.filters["small_version"])
    ].copy()
    return frame


def _build_queries_table(frame: pd.DataFrame) -> pd.DataFrame:
    columns = ["query_id", "query", "split", "product_locale", "source"]
    queries = frame[columns].drop_duplicates(subset=["query_id", "split"]).sort_values(
        ["split", "query_id"]
    )
    return queries


def _build_judgments_table(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "query_id",
        "product_id",
        "split",
        "esci_label",
        "source",
        "grade_default",
        "grade_strict",
        "grade_amazon",
    ]
    return frame[columns].sort_values(["split", "query_id", "product_id"])


def _build_search_documents(frame: pd.DataFrame) -> pd.DataFrame:
    documents = (
        frame[
            [
                "product_id",
                "product_locale",
                "product_title",
                "product_brand",
                "product_color",
                "product_description",
                "product_bullet_point",
                "product_text",
            ]
        ]
        .drop_duplicates(subset=["product_id", "product_locale"])
        .copy()
    )
    documents["document_id"] = (
        documents["product_locale"].astype(str) + ":" + documents["product_id"].astype(str)
    )
    documents["searchable_text"] = documents.apply(_build_searchable_text, axis=1)
    return documents.sort_values(["product_locale", "product_id"])


def _build_baseline_run(frame: pd.DataFrame, split_name: str) -> pd.DataFrame:
    baseline = frame[frame["split"] == split_name][
        ["query_id", "product_id", "query", "product_title", "product_text"]
    ].copy()
    baseline["score"] = baseline.apply(
        lambda row: lexical_overlap_score(
            row["query"], unique_join([row["product_title"], row["product_text"]])
        ),
        axis=1,
    )
    baseline = baseline.sort_values(["query_id", "score", "product_id"], ascending=[True, False, True])
    baseline["rank"] = baseline.groupby("query_id").cumcount() + 1
    baseline["system"] = "baseline"
    return baseline[["query_id", "product_id", "score", "rank", "system"]]


def _data_quality_report(frame: pd.DataFrame, queries: pd.DataFrame, documents: pd.DataFrame) -> dict[str, Any]:
    report: dict[str, Any] = {
        "overall": {
            "rows": int(len(frame)),
            "unique_queries": int(queries["query_id"].nunique()),
            "unique_products": int(documents["product_id"].nunique()),
            "label_distribution": frame["esci_label"].value_counts().to_dict(),
            "null_counts": {column: int(frame[column].isna().sum()) for column in TEXT_COLUMNS},
            "duplicate_query_product_pairs": int(
                frame.duplicated(subset=["split", "query_id", "product_id"]).sum()
            ),
        },
        "splits": {},
    }
    for split_name, split_frame in frame.groupby("split"):
        report["splits"][split_name] = {
            "rows": int(len(split_frame)),
            "unique_queries": int(split_frame["query_id"].nunique()),
            "unique_products": int(split_frame["product_id"].nunique()),
            "label_distribution": split_frame["esci_label"].value_counts().to_dict(),
            "text_completeness": {
                column: float((split_frame[column].astype(str).str.len() > 0).mean())
                for column in TEXT_COLUMNS
            },
        }
    return report


def prepare_dataset(settings: AppSettings, profile: str) -> PreparedArtifacts:
    profile_name = settings.resolved_profile(profile)
    profile_config = settings.profile_config(profile_name)
    processed_dir = ensure_dir(settings.processed_dir(profile_name))
    evaluation_dir = ensure_dir(settings.evaluation_dir(profile_name))
    runs_dir = ensure_dir(evaluation_dir / "runs")
    reports_dir = ensure_dir(evaluation_dir / "reports")

    sources = pd.read_csv(settings.sources_csv)
    train_frame = _load_and_filter(settings, "train")
    test_frame = _load_and_filter(settings, "test")

    if profile_config.train_query_sample_size is not None:
        selected_queries = _stable_query_sample(
            train_frame["query_id"].drop_duplicates().tolist(),
            profile_config.train_query_sample_size,
        )
        train_frame = train_frame[train_frame["query_id"].isin(selected_queries)].copy()

    if profile_config.test_query_sample_size is not None:
        selected_queries = _stable_query_sample(
            test_frame["query_id"].drop_duplicates().tolist(),
            profile_config.test_query_sample_size,
        )
        test_frame = test_frame[test_frame["query_id"].isin(selected_queries)].copy()

    combined = pd.concat([train_frame, test_frame], ignore_index=True)
    combined = _normalize_text_columns(combined)
    combined = combined.merge(sources, how="left", on="query_id")
    combined["source"] = combined["source"].fillna("unknown")
    combined = _attach_gain_columns(combined, settings.gain_mappings)

    queries = _build_queries_table(combined)
    judgments = _build_judgments_table(combined)
    documents = _build_search_documents(combined)
    quality_report = _data_quality_report(combined, queries, documents)

    train_examples_path = processed_dir / "train_examples.parquet"
    test_examples_path = processed_dir / "test_examples.parquet"
    search_documents_path = processed_dir / "search_documents.parquet"
    queries_csv_path = evaluation_dir / "queries.csv"
    judgments_csv_path = evaluation_dir / "judgments.csv"
    baseline_train_path = runs_dir / "baseline_train.csv"
    baseline_test_path = runs_dir / "baseline_test.csv"
    quality_report_path = reports_dir / "data_quality.json"

    combined[combined["split"] == "train"].to_parquet(train_examples_path, index=False)
    combined[combined["split"] == "test"].to_parquet(test_examples_path, index=False)
    documents.to_parquet(search_documents_path, index=False)
    queries.to_csv(queries_csv_path, index=False)
    judgments.to_csv(judgments_csv_path, index=False)
    _build_baseline_run(combined, "train").to_csv(baseline_train_path, index=False)
    _build_baseline_run(combined, "test").to_csv(baseline_test_path, index=False)
    write_json(quality_report_path, quality_report)

    return PreparedArtifacts(
        train_examples=train_examples_path,
        test_examples=test_examples_path,
        search_documents=search_documents_path,
        queries_csv=queries_csv_path,
        judgments_csv=judgments_csv_path,
        baseline_train_run=baseline_train_path,
        baseline_test_run=baseline_test_path,
        data_quality_report=quality_report_path,
    )
