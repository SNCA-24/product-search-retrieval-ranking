from __future__ import annotations
# ruff: noqa: E402

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.config import load_settings
from data_prep.prepare import prepare_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare processed ESCI tables and evaluation artifacts.")
    parser.add_argument("--profile", choices=["dev", "full"], default=None)
    args = parser.parse_args()

    settings = load_settings(args.profile)
    artifacts = prepare_dataset(settings=settings, profile=settings.resolved_profile(args.profile))
    print(f"train_examples={artifacts.train_examples}")
    print(f"test_examples={artifacts.test_examples}")
    print(f"search_documents={artifacts.search_documents}")
    print(f"queries_csv={artifacts.queries_csv}")
    print(f"judgments_csv={artifacts.judgments_csv}")
    print(f"baseline_train_run={artifacts.baseline_train_run}")
    print(f"baseline_test_run={artifacts.baseline_test_run}")
    print(f"data_quality_report={artifacts.data_quality_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
