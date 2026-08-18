"""Configuration loading (SPEC.md §8): TOML file plus programmatic defaults."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BackendConfig:
    mode: str = "postgres"          # "postgres" or "api"
    dsn: str = ""                    # postgres mode


@dataclass
class ExpansionConfig:
    default_hops: int = 1
    max_hops: int = 3
    default_budget: int = 100
    # Server-side cap on edges fetched per frontier query, per edge kind.
    edge_limit: int = 5000


@dataclass
class WitnessConfig:
    # Each family contributes at most family_cap to the effective count
    # (§4.2). Default: the Lsjbot bot-generated cluster.
    clone_families: list[list[str]] = field(
        default_factory=lambda: [["ceb", "war", "sv", "vi"]])
    family_cap: float = 1.0
    # Per-language scalar weights (generalization anticipated by §4.2);
    # unlisted languages weigh 1.0.
    weights: dict[str, float] = field(default_factory=dict)


@dataclass
class TemporalConfig:
    # Prepended to the STARTS default priority order (§5.2.1).
    anchor_priority: list[str] = field(
        default_factory=lambda: ["P571", "P569", "P580", "P577"])
    undated: str = "margin"          # "margin" or "infer"


@dataclass
class ApiBackendConfig:
    cache_dir: str = "~/.cache/algae-microscope"
    user_agent: str = "algae-microscope/0.1 (https://github.com/jamiecox/algae-microscope)"
    cache_ttl_seconds: int = 86400
    # Minimum interval between HTTP requests (rate limiting, §2.3).
    min_request_interval: float = 0.25
    # Inbound typed edges via SPARQL: bounded and optional (§2.3).
    sparql_inbound: bool = False
    sparql_limit: int = 200


@dataclass
class Config:
    backend: BackendConfig = field(default_factory=BackendConfig)
    expansion: ExpansionConfig = field(default_factory=ExpansionConfig)
    witnesses: WitnessConfig = field(default_factory=WitnessConfig)
    temporal: TemporalConfig = field(default_factory=TemporalConfig)
    api_backend: ApiBackendConfig = field(default_factory=ApiBackendConfig)


def _apply(section_obj, data: dict) -> None:
    for key, value in data.items():
        if hasattr(section_obj, key):
            setattr(section_obj, key, value)


def load_config(path: str | Path | None = None) -> Config:
    """Load config from `path`, $ALGAE_MICROSCOPE_CONFIG, ./config.toml, or
    defaults — first one that exists wins."""
    candidates = []
    if path:
        candidates.append(Path(path))
    env = os.environ.get("ALGAE_MICROSCOPE_CONFIG")
    if env:
        candidates.append(Path(env))
    candidates.append(Path("config.toml"))

    config = Config()
    for candidate in candidates:
        if candidate.is_file():
            with open(candidate, "rb") as f:
                data = tomllib.load(f)
            for section in ("backend", "expansion", "witnesses", "temporal",
                            "api_backend"):
                if section in data:
                    _apply(getattr(config, section), data[section])
            break
        if path and candidate == Path(path):
            raise FileNotFoundError(f"config file not found: {path}")
    return config
