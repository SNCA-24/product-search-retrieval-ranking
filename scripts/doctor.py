from __future__ import annotations
# ruff: noqa: E402

import argparse
import shutil
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pandas as pd

from common.config import load_settings


def _check_service(host: str, port: int, timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout)
        return connection.connect_ex((host, port)) == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate local machine-safe setup.")
    parser.add_argument("--profile", choices=["dev", "full"], default=None)
    args = parser.parse_args()

    settings = load_settings(args.profile)
    problems: list[str] = []
    warnings: list[str] = []

    executable = Path(sys.executable).resolve()
    if "/opt/anaconda3/" in str(executable):
        warnings.append(f"Interpreter is Anaconda-managed: {executable}")

    disk = shutil.disk_usage(settings.repo_root)
    free_gb = disk.free / (1024 ** 3)
    if free_gb < settings.minimum_free_disk_gb:
        problems.append(
            f"Only {free_gb:.1f} GiB free. Recommended minimum is {settings.minimum_free_disk_gb} GiB."
        )

    for required_path in [settings.train_path(), settings.test_path(), settings.sources_csv]:
        if not required_path.exists():
            problems.append(f"Missing required data asset: {required_path}")

    if settings.train_path().exists():
        try:
            pd.read_parquet(settings.train_path(), columns=["query_id"]).head(1)
        except Exception as exc:
            problems.append(f"Train parquet is not readable: {exc}")

    if settings.test_path().exists():
        try:
            pd.read_parquet(settings.test_path(), columns=["query_id"]).head(1)
        except Exception as exc:
            problems.append(f"Test parquet is not readable: {exc}")

    for service_name, endpoint in settings.services.items():
        if not _check_service(endpoint.host, endpoint.port):
            warnings.append(f"{service_name} is not listening on {endpoint.host}:{endpoint.port}")

    print(f"Interpreter: {executable}")
    print(f"Free disk: {free_gb:.1f} GiB")
    print(f"Profile: {settings.resolved_profile(args.profile)}")
    print(f"Raw train: {settings.train_path()}")
    print(f"Raw test: {settings.test_path()}")
    print(f"Sources: {settings.sources_csv}")
    for warning in warnings:
        print(f"WARN: {warning}")
    for problem in problems:
        print(f"FAIL: {problem}")
    if problems:
        return 1
    print("Doctor checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
