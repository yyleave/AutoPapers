from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from autopapers.repo_paths import repo_root


@dataclass(frozen=True)
class Paths:
    repo_root: Path
    data_dir: Path
    cache_dir: Path
    runs_dir: Path
    artifacts_dir: Path
    profiles_dir: Path
    papers_dir: Path
    papers_metadata_dir: Path
    papers_pdfs_dir: Path
    papers_parsed_dir: Path
    proposals_dir: Path
    kg_dir: Path


def _resolve_data_repo_root(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    env = os.environ.get("AUTOPAPERS_REPO_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd().resolve()


def get_paths(*, repo_root: Path | None = None) -> Paths:
    """
    Resolve project paths.

    Data lives under ``<root>/data`` where ``root`` is: explicit ``repo_root`` argument, else
    ``AUTOPAPERS_REPO_ROOT`` if set, else current working directory. This path should be
    gitignored.
    """

    root = _resolve_data_repo_root(repo_root)
    data_dir = (root / "data").resolve()
    cache_dir = data_dir / "cache"
    runs_dir = data_dir / "runs"
    artifacts_dir = data_dir / "artifacts"
    profiles_dir = data_dir / "profiles"
    papers_dir = data_dir / "papers"
    papers_metadata_dir = papers_dir / "metadata"
    papers_pdfs_dir = papers_dir / "pdfs"
    papers_parsed_dir = papers_dir / "parsed"
    proposals_dir = data_dir / "proposals"
    kg_dir = data_dir / "kg"
    return Paths(
        repo_root=root,
        data_dir=data_dir,
        cache_dir=cache_dir,
        runs_dir=runs_dir,
        artifacts_dir=artifacts_dir,
        profiles_dir=profiles_dir,
        papers_dir=papers_dir,
        papers_metadata_dir=papers_metadata_dir,
        papers_pdfs_dir=papers_pdfs_dir,
        papers_parsed_dir=papers_parsed_dir,
        proposals_dir=proposals_dir,
        kg_dir=kg_dir,
    )


@dataclass(frozen=True)
class AppConfig:
    log_level: str = "INFO"
    provider: str = "arxiv"
    #: Optional contact for ``autopapers config`` / status (HTTP polite pool still uses mailto env).
    contact_email: str | None = None


def default_toml_path() -> Path:
    """
    Path to ``configs/default.toml``: under ``AUTOPAPERS_REPO_ROOT`` if set, else package repo root.
    """

    env = os.environ.get("AUTOPAPERS_REPO_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve() / "configs" / "default.toml"
    return repo_root() / "configs" / "default.toml"


def load_config() -> AppConfig:
    """
    Load defaults from configs/default.toml when present; environment overrides.

    When ``AUTOPAPERS_REPO_ROOT`` is set (same root as ``get_paths()`` data layout),
    ``<root>/configs/default.toml`` is used so project config travels with that checkout.
    """
    log_level = "INFO"
    provider = "arxiv"
    contact_email: str | None = None

    cfg_path = default_toml_path()
    if cfg_path.is_file():
        data = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            log_level = str(data.get("log_level", log_level))
            provider = str(data.get("provider", provider))
            ce = data.get("contact_email")
            if isinstance(ce, str) and ce.strip():
                contact_email = ce.strip()

    env_ce = os.environ.get("AUTOPAPERS_CONTACT_EMAIL", "").strip()
    if env_ce:
        contact_email = env_ce

    return AppConfig(
        log_level=os.environ.get("AUTOPAPERS_LOG_LEVEL", log_level),
        provider=os.environ.get("AUTOPAPERS_PROVIDER", provider),
        contact_email=contact_email,
    )

