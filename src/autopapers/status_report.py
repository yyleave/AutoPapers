from __future__ import annotations

from pathlib import Path
from typing import Any

from autopapers import __version__
from autopapers.config import AppConfig, Paths, get_paths, load_config
from autopapers.providers.registry import ProviderRegistry


def _safe_glob_count(dir_path: Path, pattern: str) -> int:
    if not dir_path.is_dir():
        return 0
    return sum(1 for _ in dir_path.glob(pattern))


def build_status(
    *,
    paths: Paths | None = None,
    cfg: AppConfig | None = None,
) -> dict[str, Any]:
    """
    Collect non-secret runtime / data layout summary for ``status`` CLI and tests.
    """

    p = paths or get_paths()
    c = cfg or load_config()
    reg = ProviderRegistry.default()

    snap = p.kg_dir / "corpus-snapshot.json"
    draft = p.proposals_dir / "proposal-draft.json"
    confirmed = p.proposals_dir / "proposal-confirmed.json"

    return {
        "app_version": __version__,
        "config": {
            "provider": c.provider,
            "log_level": c.log_level,
        },
        "paths": {
            "repo_root": str(p.repo_root),
            "data_dir": str(p.data_dir),
            "papers_metadata_dir": str(p.papers_metadata_dir),
            "papers_pdfs_dir": str(p.papers_pdfs_dir),
            "papers_parsed_dir": str(p.papers_parsed_dir),
            "kg_dir": str(p.kg_dir),
            "proposals_dir": str(p.proposals_dir),
            "profiles_dir": str(p.profiles_dir),
        },
        "providers": sorted(reg.providers.keys()),
        "data": {
            "metadata_json": _safe_glob_count(p.papers_metadata_dir, "*.json"),
            "pdfs": _safe_glob_count(p.papers_pdfs_dir, "*.pdf"),
            "parsed_txt": _safe_glob_count(p.papers_parsed_dir, "*.txt"),
            "parse_manifests": _safe_glob_count(p.papers_parsed_dir, "*.manifest.json"),
            "profiles_json": _safe_glob_count(p.profiles_dir, "*.json"),
            "corpus_snapshot_exists": snap.is_file(),
            "proposal_draft_exists": draft.is_file(),
            "proposal_confirmed_exists": confirmed.is_file(),
        },
    }
