from __future__ import annotations

import hashlib
import importlib
import os
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def stable_hash_int(value: Any) -> int:
    digest = hashlib.sha1(str(value).encode("utf-8")).hexdigest()
    return int(digest, 16)


def env_or_default(name: str, default: str) -> str:
    return os.environ.get(name, default)


def require_optional(module_name: str, extra_name: str) -> Any:
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        raise RuntimeError(
            f"Missing optional dependency '{module_name}'. Install the '{extra_name}' extra first."
        ) from exc
