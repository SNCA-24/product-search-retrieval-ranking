from __future__ import annotations
# ruff: noqa: E402

import argparse
import statistics
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
from common.io import ensure_dir, write_json


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * percentile))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark local API latency.")
    parser.add_argument("--profile", choices=["dev", "full"], default=None)
    parser.add_argument("--endpoint", choices=["search", "debug/search"], default="search")
    parser.add_argument("--queries", type=int, default=None)
    parser.add_argument("--mode", choices=["bm25", "vector", "hybrid", "ltr"], default="hybrid")
    args = parser.parse_args()

    settings = load_settings(args.profile)
    profile = settings.resolved_profile(args.profile)
    profile_config = settings.profile_config(profile)
    max_queries = args.queries or profile_config.benchmark_queries
    queries = pd.read_csv(settings.evaluation_dir(profile) / "queries.csv")
    queries = queries[queries["split"] == "test"].head(max_queries)

    base_url = settings.services["api"].url
    latencies: list[float] = []
    fallback_count = 0
    zero_result_count = 0
    timeout_count = 0

    with httpx.Client(timeout=10.0) as client:
        for _, row in queries.iterrows():
            started = time.perf_counter()
            try:
                response = client.get(
                    f"{base_url}/{args.endpoint}",
                    params={"q": row["query"], "mode": args.mode, "locale": "us", "k": 10},
                )
                response.raise_for_status()
                payload = response.json()
                latencies.append((time.perf_counter() - started) * 1000)
                if payload.get("fallback_triggered"):
                    fallback_count += 1
                if not payload.get("results"):
                    zero_result_count += 1
            except httpx.TimeoutException:
                timeout_count += 1

    report = {
        "profile": profile,
        "endpoint": args.endpoint,
        "mode": args.mode,
        "query_count": len(queries),
        "p50_ms": statistics.median(latencies) if latencies else 0.0,
        "p95_ms": _percentile(latencies, 0.95),
        "timeout_rate": timeout_count / len(queries) if len(queries) else 0.0,
        "zero_result_rate": zero_result_count / len(queries) if len(queries) else 0.0,
        "fallback_trigger_rate": fallback_count / len(queries) if len(queries) else 0.0,
    }
    reports_dir = ensure_dir(settings.evaluation_dir(profile) / "reports")
    report_path = reports_dir / f"latency_{args.endpoint.replace('/', '_')}_{args.mode}.json"
    write_json(report_path, report)
    print(f"report={report_path}")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
