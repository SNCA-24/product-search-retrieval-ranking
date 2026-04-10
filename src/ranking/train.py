from __future__ import annotations

import pandas as pd

from common.config import AppSettings
from common.io import ensure_dir, write_json
from common.runtime import require_optional
from evaluation.metrics import evaluate_run
from features.extractor import build_feature_dataset


METADATA_COLUMNS = {
    "example_id",
    "query",
    "query_id",
    "product_id",
    "product_locale",
    "esci_label",
    "small_version",
    "large_version",
    "split",
    "source",
    "product_title",
    "product_description",
    "product_bullet_point",
    "product_brand",
    "product_color",
    "product_text",
    "grade_default",
    "grade_strict",
    "grade_amazon",
    "fold",
}


def _feature_columns(frame: pd.DataFrame) -> list[str]:
    return [column for column in frame.columns if column not in METADATA_COLUMNS]


def _training_params(settings: AppSettings, objective: str) -> dict[str, object]:
    objective_lookup = {
        "pointwise": settings.models["ranking"]["pointwise_objective"],
        "pairwise": settings.models["ranking"]["pairwise_objective"],
        "listwise": settings.models["ranking"]["listwise_objective"],
    }
    params: dict[str, object] = {
        "objective": objective_lookup[objective],
        "eta": 0.08,
        "max_depth": 6,
        "subsample": 0.9,
        "colsample_bytree": 0.8,
        "nthread": 1,
        "seed": 42,
    }
    if objective == "pointwise":
        params["eval_metric"] = "rmse"
    else:
        params["eval_metric"] = "ndcg@10"
    return params


def _selected_ranker(settings: AppSettings) -> tuple[str, str]:
    ranking_config = settings.models["ranking"]
    return (
        ranking_config.get("selected_objective", "listwise"),
        ranking_config.get("selected_gain_mapping", "default"),
    )


def train_ranker(
    settings: AppSettings,
    profile: str,
    objective: str,
    gain_mapping: str,
) -> dict[str, str]:
    xgb = require_optional("xgboost", "ranking")
    mlflow = require_optional("mlflow", "ranking")

    profile_name = settings.resolved_profile(profile)
    train_path = build_feature_dataset(settings, profile_name, "train")
    test_path = build_feature_dataset(settings, profile_name, "test")
    train_frame = pd.read_parquet(train_path).sort_values(["query_id", "product_id"])
    test_frame = pd.read_parquet(test_path).sort_values(["query_id", "product_id"])
    feature_columns = _feature_columns(train_frame)
    label_column = f"grade_{gain_mapping}"

    fit_frame = train_frame[train_frame["fold"] == "train"].copy()
    validation_frame = train_frame[train_frame["fold"] == "validation"].copy()

    dtrain = xgb.DMatrix(fit_frame[feature_columns], label=fit_frame[label_column])
    dvalid = xgb.DMatrix(validation_frame[feature_columns], label=validation_frame[label_column])
    if objective in {"pairwise", "listwise"}:
        dtrain.set_group(fit_frame.groupby("query_id").size().tolist())
        dvalid.set_group(validation_frame.groupby("query_id").size().tolist())

    params = _training_params(settings, objective)
    mlflow.set_tracking_uri(settings.mlruns_root.as_uri())
    run_name = f"{objective}-{gain_mapping}-{profile_name}"

    model_dir = ensure_dir(settings.processed_dir(profile_name) / "models")
    reports_dir = ensure_dir(settings.evaluation_dir(profile_name) / "reports")
    runs_dir = ensure_dir(settings.evaluation_dir(profile_name) / "runs")
    model_path = model_dir / f"{objective}_{gain_mapping}.json"
    report_path = reports_dir / f"ranking_{objective}_{gain_mapping}.json"
    validation_per_query_path = reports_dir / f"ranking_{objective}_{gain_mapping}_validation_per_query.csv"
    test_run_path = runs_dir / f"ltr_{objective}_{gain_mapping}_test.csv"
    selected_model_path = model_dir / "selected_ranker.json"
    default_test_run_path = runs_dir / "ltr_test.csv"

    with mlflow.start_run(run_name=run_name):
        mlflow.log_params(
            {
                "profile": profile_name,
                "objective": objective,
                "gain_mapping": gain_mapping,
                "feature_count": len(feature_columns),
                "train_rows": len(fit_frame),
                "validation_rows": len(validation_frame),
                "test_rows": len(test_frame),
            }
        )
        booster = xgb.train(
            params=params,
            dtrain=dtrain,
            num_boost_round=300,
            evals=[(dtrain, "train"), (dvalid, "validation")],
            early_stopping_rounds=25,
            verbose_eval=False,
        )
        booster.save_model(model_path)

        validation_scores = booster.predict(dvalid)
        validation_run = validation_frame[["query_id", "product_id"]].copy()
        validation_run["score"] = validation_scores
        validation_run = validation_run.sort_values(["query_id", "score"], ascending=[True, False])
        validation_run["rank"] = validation_run.groupby("query_id").cumcount() + 1

        validation_summary, validation_per_query = evaluate_run(
            judgments=validation_frame[["query_id", "product_id", label_column]].rename(
                columns={label_column: "grade"}
            ),
            run=validation_run,
            grade_column="grade",
        )
        validation_per_query.to_csv(validation_per_query_path, index=False)

        dtest = xgb.DMatrix(test_frame[feature_columns])
        if objective in {"pairwise", "listwise"}:
            dtest.set_group(test_frame.groupby("query_id").size().tolist())
        test_scores = booster.predict(dtest)
        test_run = test_frame[["query_id", "product_id"]].copy()
        test_run["score"] = test_scores
        test_run = test_run.sort_values(["query_id", "score"], ascending=[True, False])
        test_run["rank"] = test_run.groupby("query_id").cumcount() + 1
        test_run["system"] = "ltr"
        test_run.to_csv(test_run_path, index=False)

        importance = booster.get_score(importance_type="gain")
        report = {
            "objective": objective,
            "gain_mapping": gain_mapping,
            "profile": profile_name,
            "feature_columns": feature_columns,
            "validation_summary": validation_summary.to_dict(),
            "feature_importance": importance,
            "model_path": str(model_path),
            "test_run_path": str(test_run_path),
        }
        write_json(report_path, report)
        selected_objective, selected_gain_mapping = _selected_ranker(settings)
        if objective == selected_objective and gain_mapping == selected_gain_mapping:
            test_run.to_csv(default_test_run_path, index=False)
            write_json(
                selected_model_path,
                {
                    "objective": objective,
                    "gain_mapping": gain_mapping,
                    "model_path": str(model_path),
                    "test_run_path": str(test_run_path),
                    "report_path": str(report_path),
                },
            )
        mlflow.log_metrics(
            {
                "validation_ndcg_at_10": validation_summary.ndcg_at_10,
                "validation_mrr": validation_summary.mrr,
                "validation_precision_at_10": validation_summary.precision_at_10,
                "validation_recall_at_50": validation_summary.recall_at_50,
                "validation_recall_at_100": validation_summary.recall_at_100,
            }
        )
        mlflow.log_artifact(str(model_path))
        mlflow.log_artifact(str(report_path))

    return {
        "model_path": str(model_path),
        "report_path": str(report_path),
        "validation_per_query_path": str(validation_per_query_path),
        "test_run_path": str(test_run_path),
    }
