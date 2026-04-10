from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


def _dcg(gains: Iterable[float]) -> float:
    total = 0.0
    for index, gain in enumerate(gains, start=1):
        if gain <= 0:
            continue
        total += gain / np.log2(index + 1)
    return float(total)


def _first_relevant_rank(gains: list[float]) -> int | None:
    for index, gain in enumerate(gains, start=1):
        if gain > 0:
            return index
    return None


@dataclass(frozen=True)
class EvaluationSummary:
    queries: int
    ndcg_at_10: float
    mrr: float
    precision_at_10: float
    recall_at_50: float
    recall_at_100: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "queries": self.queries,
            "ndcg_at_10": self.ndcg_at_10,
            "mrr": self.mrr,
            "precision_at_10": self.precision_at_10,
            "recall_at_50": self.recall_at_50,
            "recall_at_100": self.recall_at_100,
        }


def evaluate_run(
    judgments: pd.DataFrame,
    run: pd.DataFrame,
    grade_column: str,
) -> tuple[EvaluationSummary, pd.DataFrame]:
    qrels = judgments[["query_id", "product_id", grade_column]].copy()
    qrels = qrels.rename(columns={grade_column: "grade"})
    qrels["grade"] = qrels["grade"].astype(float)
    qrels = qrels.groupby(["query_id", "product_id"], as_index=False)["grade"].max()

    if "rank" not in run.columns:
        run = run.sort_values(["query_id", "score"], ascending=[True, False]).copy()
        run["rank"] = run.groupby("query_id").cumcount() + 1
    run = run.sort_values(["query_id", "rank", "score"], ascending=[True, True, False]).copy()
    run = run.drop_duplicates(subset=["query_id", "product_id"], keep="first")
    run["rank"] = run.groupby("query_id").cumcount() + 1

    metrics_rows: list[dict[str, float | int]] = []
    grouped_qrels = qrels.groupby("query_id")
    grouped_runs = run.sort_values(["query_id", "rank"]).groupby("query_id")

    for query_id, qrels_frame in grouped_qrels:
        relevant_lookup = dict(zip(qrels_frame["product_id"], qrels_frame["grade"], strict=False))
        ranked_products = grouped_runs.get_group(query_id)["product_id"].tolist() if query_id in grouped_runs.groups else []
        gains = [relevant_lookup.get(product_id, 0.0) for product_id in ranked_products]
        ideal_gains = sorted(relevant_lookup.values(), reverse=True)
        relevant_total = sum(1 for gain in relevant_lookup.values() if gain > 0)

        ndcg_at_10 = 0.0
        ideal_dcg_at_10 = _dcg(ideal_gains[:10])
        if ideal_dcg_at_10 > 0:
            ndcg_at_10 = _dcg(gains[:10]) / ideal_dcg_at_10

        first_relevant_rank = _first_relevant_rank(gains)
        reciprocal_rank = 1.0 / first_relevant_rank if first_relevant_rank else 0.0
        precision_at_10 = sum(1 for gain in gains[:10] if gain > 0) / 10.0
        recall_at_50 = (
            sum(1 for gain in gains[:50] if gain > 0) / relevant_total if relevant_total else 0.0
        )
        recall_at_100 = (
            sum(1 for gain in gains[:100] if gain > 0) / relevant_total if relevant_total else 0.0
        )

        metrics_rows.append(
            {
                "query_id": int(query_id),
                "ndcg_at_10": float(ndcg_at_10),
                "mrr": float(reciprocal_rank),
                "precision_at_10": float(precision_at_10),
                "recall_at_50": float(recall_at_50),
                "recall_at_100": float(recall_at_100),
                "relevant_total": int(relevant_total),
                "returned_documents": int(len(ranked_products)),
            }
        )

    per_query = pd.DataFrame(metrics_rows).sort_values("query_id")
    summary = EvaluationSummary(
        queries=int(len(per_query)),
        ndcg_at_10=float(per_query["ndcg_at_10"].mean()) if not per_query.empty else 0.0,
        mrr=float(per_query["mrr"].mean()) if not per_query.empty else 0.0,
        precision_at_10=float(per_query["precision_at_10"].mean()) if not per_query.empty else 0.0,
        recall_at_50=float(per_query["recall_at_50"].mean()) if not per_query.empty else 0.0,
        recall_at_100=float(per_query["recall_at_100"].mean()) if not per_query.empty else 0.0,
    )
    return summary, per_query
