from __future__ import annotations

from pathlib import Path

import pandas as pd

from common.io import ensure_dir


def load_run_cache(path: Path) -> pd.DataFrame | None:
    if path.exists():
        return pd.read_csv(path)
    return None


def save_run_cache(path: Path, frame: pd.DataFrame) -> Path:
    ensure_dir(path.parent)
    frame.to_csv(path, index=False)
    return path
