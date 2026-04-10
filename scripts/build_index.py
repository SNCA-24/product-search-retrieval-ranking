from __future__ import annotations
# ruff: noqa: E402

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pandas as pd

from common.config import load_settings
from indexing.embeddings import generate_product_embeddings
from indexing.opensearch import (
    DEFAULT_INDEX_BATCH_SIZE,
    create_index,
    index_documents,
    sync_index_checkpoint_from_live_count,
)
from retrieval.service import OpenSearchRetriever


def _benchmark_retrieval(profile: str, split: str, mode: str, query_limit: int | None) -> None:
    settings = load_settings(profile)
    retriever = OpenSearchRetriever(settings=settings, profile=profile)
    queries = pd.read_csv(settings.evaluation_dir(profile) / "queries.csv")
    queries = queries[queries["split"] == split].copy()
    if query_limit is not None:
        queries = queries.head(query_limit)

    modes = ["bm25", "vector", "hybrid"] if mode == "all" else [mode]
    for selected_mode in modes:
        path = retriever.benchmark_queries(
            queries=queries,
            split=split,
            mode=selected_mode,
            use_cache=True,
        )
        print(f"{selected_mode}_run={path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenSearch indexing and retrieval utilities.")
    parser.add_argument("--profile", choices=["dev", "full"], default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_index_parser = subparsers.add_parser("create-index")
    create_index_parser.add_argument("--force-recreate", action="store_true")

    subparsers.add_parser("generate-embeddings")
    index_parser = subparsers.add_parser("index-documents")
    index_parser.add_argument("--batch-size", type=int, default=DEFAULT_INDEX_BATCH_SIZE)
    index_parser.add_argument("--reset-checkpoint", action="store_true")
    index_parser.add_argument("--bootstrap-from-live-count", action="store_true")

    sync_parser = subparsers.add_parser("sync-index-checkpoint")
    sync_parser.add_argument("--batch-size", type=int, default=DEFAULT_INDEX_BATCH_SIZE)

    benchmark_parser = subparsers.add_parser("benchmark-retrieval")
    benchmark_parser.add_argument("--split", choices=["train", "test"], default="test")
    benchmark_parser.add_argument("--mode", choices=["all", "bm25", "vector", "hybrid"], default="all")
    benchmark_parser.add_argument("--query-limit", type=int, default=None)

    args = parser.parse_args()
    settings = load_settings(args.profile)
    profile = settings.resolved_profile(args.profile)

    if args.command == "create-index":
        index_name = create_index(settings=settings, force_recreate=args.force_recreate)
        print(f"index_name={index_name}")
    elif args.command == "generate-embeddings":
        artifacts = generate_product_embeddings(settings=settings, profile=profile)
        print(f"matrix_path={artifacts.matrix_path}")
        print(f"manifest_path={artifacts.manifest_path}")
        print(f"metadata_path={artifacts.metadata_path}")
    elif args.command == "index-documents":
        result = index_documents(
            settings=settings,
            profile=profile,
            batch_size=args.batch_size,
            reset_checkpoint=args.reset_checkpoint,
            bootstrap_from_live_count=args.bootstrap_from_live_count,
        )
        print(result)
    elif args.command == "sync-index-checkpoint":
        result = sync_index_checkpoint_from_live_count(
            settings=settings,
            profile=profile,
            batch_size=args.batch_size,
        )
        print(result)
    elif args.command == "benchmark-retrieval":
        _benchmark_retrieval(profile=profile, split=args.split, mode=args.mode, query_limit=args.query_limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
