from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from common.constants import VALID_PROFILES
from common.runtime import env_or_default, repo_root


@dataclass(frozen=True)
class ServiceEndpoint:
    host: str
    port: int

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


@dataclass(frozen=True)
class ProfileConfig:
    name: str
    train_query_sample_size: int | None
    test_query_sample_size: int | None
    top_k: int
    benchmark_queries: int


@dataclass(frozen=True)
class AppSettings:
    repo_root: Path
    default_profile: str
    minimum_free_disk_gb: int
    raw_data_root: Path
    raw_train_file: str
    raw_test_file: str
    sources_csv: Path
    processed_root: Path
    evaluation_root: Path
    cache_root: Path
    reports_root: Path
    mlruns_root: Path
    profiles: dict[str, ProfileConfig]
    filters: dict[str, Any]
    models: dict[str, Any]
    opensearch: dict[str, Any]
    gain_mappings: dict[str, dict[str, float]]
    latency_budgets_ms: dict[str, int]
    services: dict[str, ServiceEndpoint]

    def resolved_profile(self, profile: str | None) -> str:
        chosen = profile or self.default_profile
        if chosen not in VALID_PROFILES:
            raise ValueError(f"Unsupported profile '{chosen}'. Expected one of {sorted(VALID_PROFILES)}.")
        return chosen

    def profile_config(self, profile: str | None) -> ProfileConfig:
        return self.profiles[self.resolved_profile(profile)]

    def processed_dir(self, profile: str | None) -> Path:
        return self.processed_root / self.resolved_profile(profile)

    def evaluation_dir(self, profile: str | None) -> Path:
        return self.evaluation_root / self.resolved_profile(profile)

    def train_path(self) -> Path:
        return self.raw_data_root / self.raw_train_file

    def test_path(self) -> Path:
        return self.raw_data_root / self.raw_test_file


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _resolve_path(root: Path, raw_value: str) -> Path:
    return (root / raw_value).resolve()


def load_settings(profile: str | None = None) -> AppSettings:
    root = repo_root()
    config_path = _resolve_path(root, env_or_default("ESCI_CONFIG_PATH", "configs/services.yaml"))
    ports_path = _resolve_path(root, env_or_default("ESCI_PORTS_PATH", "configs/local_ports.yaml"))
    config_data = _load_yaml(config_path)
    ports_data = _load_yaml(ports_path)
    ranking_models = {**config_data["models"]["ranking"]}
    candidate_depth = os.environ.get("ESCI_ONLINE_CANDIDATE_DEPTH")
    if candidate_depth is not None:
        ranking_models["online_candidate_depth"] = int(candidate_depth)
    vector_multiplier = os.environ.get("ESCI_ONLINE_VECTOR_SEARCH_MULTIPLIER")
    if vector_multiplier is not None:
        ranking_models["online_vector_search_multiplier"] = int(vector_multiplier)
    models = {
        **config_data["models"],
        "ranking": ranking_models,
    }

    profiles = {
        name: ProfileConfig(name=name, **profile_config)
        for name, profile_config in config_data["profiles"].items()
    }
    services = {
        name: ServiceEndpoint(**service_config)
        for name, service_config in ports_data["services"].items()
    }
    mlruns_root = _resolve_path(
        root,
        env_or_default("MLFLOW_TRACKING_URI", config_data["paths"]["mlruns_root"]),
    )

    settings = AppSettings(
        repo_root=root,
        default_profile=profile or env_or_default("ESCI_PROFILE", config_data["project"]["default_profile"]),
        minimum_free_disk_gb=int(config_data["project"]["minimum_free_disk_gb"]),
        raw_data_root=_resolve_path(
            root,
            env_or_default("ESCI_RAW_DATA_ROOT", config_data["raw_data"]["root"]),
        ),
        raw_train_file=config_data["raw_data"]["train_file"],
        raw_test_file=config_data["raw_data"]["test_file"],
        sources_csv=_resolve_path(
            root,
            env_or_default("ESCI_SOURCES_PATH", config_data["raw_data"]["sources_csv"]),
        ),
        processed_root=_resolve_path(root, config_data["paths"]["processed_root"]),
        evaluation_root=_resolve_path(root, config_data["paths"]["evaluation_root"]),
        cache_root=_resolve_path(root, config_data["paths"]["cache_root"]),
        reports_root=_resolve_path(root, config_data["paths"]["reports_root"]),
        mlruns_root=mlruns_root,
        profiles=profiles,
        filters=config_data["filters"],
        models=models,
        opensearch={
            **config_data["opensearch"],
            "url": env_or_default("OPENSEARCH_URL", config_data["opensearch"]["url"]),
        },
        gain_mappings=config_data["gain_mappings"],
        latency_budgets_ms=config_data["latency_budgets_ms"],
        services=services,
    )
    settings.resolved_profile(profile)
    return settings
