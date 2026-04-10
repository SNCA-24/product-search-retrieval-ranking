from __future__ import annotations
# ruff: noqa: E402

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pandas as pd

from common.config import load_settings
from common.constants import VALID_GAIN_MAPPINGS
from common.io import ensure_dir, write_json
from evaluation.metrics import evaluate_run


def _default_run_path(evaluation_dir: Path, system: str, split: str) -> Path:
    return evaluation_dir / "runs" / f"{system}_{split}.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate an offline run against ESCI judgments.")
    parser.add_argument("--profile", choices=["dev", "full"], default=None)
    parser.add_argument("--system", required=True)
    parser.add_argument("--split", choices=["train", "test"], default="test")
    parser.add_argument("--gain-mapping", choices=sorted(VALID_GAIN_MAPPINGS), default="default")
    parser.add_argument("--run-path", type=Path, default=None)
    args = parser.parse_args()

    settings = load_settings(args.profile)
    profile = settings.resolved_profile(args.profile)
    evaluation_dir = settings.evaluation_dir(profile)
    judgments = pd.read_csv(evaluation_dir / "judgments.csv")
    judgments = judgments[judgments["split"] == args.split].copy()

    run_path = args.run_path or _default_run_path(evaluation_dir, args.system, args.split)
    if not run_path.exists():
        raise FileNotFoundError(f"Run file not found: {run_path}")

    run = pd.read_csv(run_path)
    summary, per_query = evaluate_run(
        judgments=judgments,
        run=run,
        grade_column=f"grade_{args.gain_mapping}",
    )

    reports_dir = ensure_dir(evaluation_dir / "reports")
    report_path = reports_dir / f"{args.system}_{args.split}_{args.gain_mapping}.json"
    per_query_path = reports_dir / f"{args.system}_{args.split}_{args.gain_mapping}_per_query.csv"

    report_payload = {
        "system": args.system,
        "split": args.split,
        "gain_mapping": args.gain_mapping,
        "summary": summary.to_dict(),
        "run_path": str(run_path),
        "judgments_path": str(evaluation_dir / "judgments.csv"),
    }
    write_json(report_path, report_payload)
    per_query.to_csv(per_query_path, index=False)

    print(f"report={report_path}")
    print(f"per_query={per_query_path}")
    print(summary.to_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
