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
from ranking.train import train_ranker


def main() -> int:
    parser = argparse.ArgumentParser(description="Train XGBoost rankers with local MLflow tracking.")
    parser.add_argument("--profile", choices=["dev", "full"], default=None)
    parser.add_argument("--objective", choices=["pointwise", "pairwise", "listwise"], required=True)
    parser.add_argument("--gain-mapping", choices=["default", "strict", "amazon"], required=True)
    args = parser.parse_args()

    settings = load_settings(args.profile)
    outputs = train_ranker(
        settings=settings,
        profile=settings.resolved_profile(args.profile),
        objective=args.objective,
        gain_mapping=args.gain_mapping,
    )
    for key, value in outputs.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
