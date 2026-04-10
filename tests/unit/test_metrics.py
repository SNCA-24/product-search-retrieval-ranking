from __future__ import annotations

import pandas as pd

from evaluation.metrics import evaluate_run


def test_evaluate_run_deduplicates_query_product_pairs() -> None:
    judgments = pd.DataFrame(
        [
            {"query_id": 1, "product_id": "a", "grade_default": 3.0},
            {"query_id": 1, "product_id": "b", "grade_default": 2.0},
        ]
    )
    run = pd.DataFrame(
        [
            {"query_id": 1, "product_id": "a", "score": 10.0},
            {"query_id": 1, "product_id": "a", "score": 9.0},
            {"query_id": 1, "product_id": "b", "score": 8.0},
        ]
    )

    summary, per_query = evaluate_run(judgments=judgments, run=run, grade_column="grade_default")

    assert summary.recall_at_100 == 1.0
    assert int(per_query.iloc[0]["returned_documents"]) == 2


def test_evaluate_run_scores_expected_ordering() -> None:
    judgments = pd.DataFrame(
        [
            {"query_id": 10, "product_id": "x", "grade_default": 3.0},
            {"query_id": 10, "product_id": "y", "grade_default": 0.0},
        ]
    )
    run = pd.DataFrame(
        [
            {"query_id": 10, "product_id": "x", "score": 1.0},
            {"query_id": 10, "product_id": "y", "score": 0.5},
        ]
    )

    summary, _ = evaluate_run(judgments=judgments, run=run, grade_column="grade_default")

    assert summary.mrr == 1.0
    assert summary.recall_at_50 == 1.0
