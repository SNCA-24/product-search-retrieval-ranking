from __future__ import annotations
# ruff: noqa: E402

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import httpx
import pandas as pd

from common.config import load_settings
from common.io import ensure_dir, read_json, write_json
from evaluation.metrics import evaluate_run
from common.runtime import require_optional

RRF_K = 60


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * percentile))
    return ordered[index]


def _normalize_group(series: pd.Series) -> pd.Series:
    minimum = series.min()
    maximum = series.max()
    if pd.isna(minimum) or pd.isna(maximum) or minimum == maximum:
        return pd.Series([0.0] * len(series), index=series.index, dtype="float32")
    return ((series - minimum) / (maximum - minimum)).astype("float32")


def _feature_columns(settings, profile: str) -> list[str]:
    selected = read_json(settings.processed_dir(profile) / "models" / "selected_ranker.json")
    report = read_json(Path(selected["report_path"]))
    return list(report["feature_columns"])


def _model_path(settings, profile: str) -> Path:
    selected = read_json(settings.processed_dir(profile) / "models" / "selected_ranker.json")
    return Path(selected["model_path"])


def _load_test_feature_frame(settings, profile: str) -> pd.DataFrame:
    return pd.read_parquet(settings.processed_dir(profile) / "features" / "test_ltr_features.parquet")


def _rescore_for_depth(settings, profile: str, depth: int) -> tuple[pd.DataFrame, dict[str, float]]:
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("KMP_INIT_AT_FORK", "FALSE")
    os.environ.setdefault("KMP_BLOCKTIME", "0")
    feature_columns = _feature_columns(settings, profile)
    feature_frame = _load_test_feature_frame(settings, profile).copy()
    top_k = settings.profile_config(profile).top_k
    default_rank = top_k + 1

    feature_frame = feature_frame[
        (feature_frame["bm25_rank"] <= depth) | (feature_frame["vector_rank"] <= depth)
    ].copy()

    bm25_in_scope = feature_frame["bm25_rank"] <= depth
    vector_in_scope = feature_frame["vector_rank"] <= depth
    feature_frame.loc[~bm25_in_scope, "bm25_score"] = 0.0
    feature_frame.loc[~bm25_in_scope, "bm25_rank"] = default_rank
    feature_frame.loc[~vector_in_scope, "vector_score"] = 0.0
    feature_frame.loc[~vector_in_scope, "vector_rank"] = default_rank

    feature_frame["hybrid_score"] = (
        bm25_in_scope.astype("float32") / (RRF_K + feature_frame["bm25_rank"].clip(upper=depth))
        + vector_in_scope.astype("float32") / (RRF_K + feature_frame["vector_rank"].clip(upper=depth))
    ).astype("float32")
    feature_frame["hybrid_rank"] = (
        feature_frame.groupby("query_id")["hybrid_score"]
        .rank(method="first", ascending=False)
        .astype("int16")
    )
    feature_frame["bm25_score_norm"] = feature_frame.groupby("query_id")["bm25_score"].transform(_normalize_group)
    feature_frame["vector_score_norm"] = feature_frame.groupby("query_id")["vector_score"].transform(_normalize_group)
    feature_frame["hybrid_score_norm"] = feature_frame.groupby("query_id")["hybrid_score"].transform(_normalize_group)

    xgb = require_optional("xgboost", "ranking")
    booster = xgb.Booster()
    booster.load_model(str(_model_path(settings, profile)))
    booster.set_param({"nthread": 1})
    matrix = xgb.DMatrix(feature_frame[feature_columns])
    feature_frame["score"] = booster.predict(matrix).astype("float32")

    run = feature_frame[["query_id", "product_id", "score", "hybrid_rank", "bm25_rank"]].copy()
    run = run.sort_values(["query_id", "score", "hybrid_rank", "bm25_rank"], ascending=[True, False, True, True])
    run["rank"] = run.groupby("query_id").cumcount() + 1
    run["system"] = f"ltr_depth_{depth}"
    run = run[["query_id", "product_id", "score", "rank", "system"]]

    judgments = pd.read_csv(settings.evaluation_dir(profile) / "judgments.csv")
    judgments = judgments[judgments["split"] == "test"][["query_id", "product_id", "grade_default"]].copy()
    summary, _ = evaluate_run(judgments=judgments, run=run, grade_column="grade_default")
    return run, summary.to_dict()


def _wait_for_health(base_url: str, timeout_seconds: float = 30.0) -> None:
    deadline = time.time() + timeout_seconds
    with httpx.Client(timeout=2.0) as client:
        while time.time() < deadline:
            try:
                response = client.get(f"{base_url}/health")
                response.raise_for_status()
                return
            except Exception:
                time.sleep(0.5)
    raise RuntimeError("Timed out waiting for API health endpoint.")


def _benchmark_latency(base_url: str, queries: pd.DataFrame) -> dict[str, float]:
    latencies: list[float] = []
    timeout_count = 0
    zero_result_count = 0
    fallback_count = 0

    with httpx.Client(timeout=10.0) as client:
        for _, row in queries.iterrows():
            started = time.perf_counter()
            try:
                response = client.get(
                    f"{base_url}/search",
                    params={"q": row["query"], "mode": "ltr", "locale": "us", "k": 10},
                )
                response.raise_for_status()
                payload = response.json()
                latencies.append((time.perf_counter() - started) * 1000)
                if not payload.get("results"):
                    zero_result_count += 1
                if payload.get("fallback_triggered"):
                    fallback_count += 1
            except httpx.TimeoutException:
                timeout_count += 1

    total = len(queries)
    return {
        "query_count": total,
        "p50_ms": float(pd.Series(latencies).median()) if latencies else 0.0,
        "p95_ms": _percentile(latencies, 0.95),
        "timeout_rate": timeout_count / total if total else 0.0,
        "zero_result_rate": zero_result_count / total if total else 0.0,
        "fallback_trigger_rate": fallback_count / total if total else 0.0,
    }


def _run_latency_for_depth(profile: str, depth: int, queries: pd.DataFrame) -> dict[str, float]:
    env = os.environ.copy()
    env["ESCI_PROFILE"] = profile
    env["ESCI_ONLINE_CANDIDATE_DEPTH"] = str(depth)
    env["PYTHONPATH"] = str(SRC)

    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.app:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_health("http://127.0.0.1:8000")
        with httpx.Client(timeout=10.0) as client:
            client.get(
                "http://127.0.0.1:8000/search",
                params={"q": "wireless mouse", "mode": "ltr", "locale": "us", "k": 10},
            ).raise_for_status()
        return _benchmark_latency("http://127.0.0.1:8000", queries)
    finally:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sweep online LTR candidate depth and report quality/latency.")
    parser.add_argument("--profile", choices=["dev", "full"], default="full")
    parser.add_argument("--depths", nargs="+", type=int, default=[40, 50, 60])
    parser.add_argument("--latency-queries", type=int, default=25)
    parser.add_argument("--output-stem", default="ltr_candidate_depth_sweep")
    args = parser.parse_args()

    settings = load_settings(args.profile)
    profile = settings.resolved_profile(args.profile)
    reports_dir = ensure_dir(settings.evaluation_dir(profile) / "reports")
    runs_dir = ensure_dir(settings.evaluation_dir(profile) / "runs")

    queries = pd.read_csv(settings.evaluation_dir(profile) / "queries.csv")
    test_queries = queries[queries["split"] == "test"].copy()
    latency_queries = test_queries.head(args.latency_queries)

    rows: list[dict[str, float | int | str]] = []
    for run_index, depth in enumerate(args.depths, start=1):
        run, quality = _rescore_for_depth(settings, profile, depth)
        run_path = runs_dir / f"ltr_depth_{depth}_test.csv"
        run.to_csv(run_path, index=False)
        latency = _run_latency_for_depth(profile, depth, latency_queries)
        rows.append(
            {
                "run_index": run_index,
                "depth": depth,
                "ndcg_at_10": quality["ndcg_at_10"],
                "p95_ms": latency["p95_ms"],
                "p50_ms": latency["p50_ms"],
                "query_count_latency": latency["query_count"],
                "run_path": str(run_path),
            }
        )

    summary = pd.DataFrame(rows).sort_values(["depth", "run_index"])
    csv_path = reports_dir / f"{args.output_stem}.csv"
    json_path = reports_dir / f"{args.output_stem}.json"
    summary.to_csv(csv_path, index=False)
    write_json(json_path, {"profile": profile, "results": summary.to_dict(orient="records")})
    print(f"csv_path={csv_path}")
    print(f"json_path={json_path}")
    print(summary.to_dict(orient="records"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
