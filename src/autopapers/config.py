from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    repo_root: Path
    data_dir: Path
    cache_dir: Path
    runs_dir: Path
    artifacts_dir: Path
    profiles_dir: Path


def get_paths(*, repo_root: Path | None = None) -> Paths:
    """
    Resolve project paths.

    Data is intentionally kept under ./data by default and should be gitignored.
    """

    root = (repo_root or Path.cwd()).resolve()
    data_dir = (root / "data").resolve()
    cache_dir = data_dir / "cache"
    runs_dir = data_dir / "runs"
    artifacts_dir = data_dir / "artifacts"
    profiles_dir = data_dir / "profiles"
    return Paths(
        repo_root=root,
        data_dir=data_dir,
        cache_dir=cache_dir,
        runs_dir=runs_dir,
        artifacts_dir=artifacts_dir,
        profiles_dir=profiles_dir,
    )


@dataclass(frozen=True)
class AppConfig:
    log_level: str = "INFO"
    provider: str = "arxiv"


def load_config() -> AppConfig:
    # MVP: env-only config. Can be extended to read configs/default.toml later.
    return AppConfig(
        log_level=os.environ.get("AUTOPAPERS_LOG_LEVEL", "INFO"),
        provider=os.environ.get("AUTOPAPERS_PROVIDER", "arxiv"),
    )

