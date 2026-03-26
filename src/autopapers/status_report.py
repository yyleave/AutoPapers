from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from autopapers import __version__
from autopapers.config import AppConfig, Paths, default_toml_path, get_paths, load_config
from autopapers.phase1.corpus_inspect import (
    load_corpus_snapshot_document,
    summarize_corpus_snapshot,
)
from autopapers.providers.polite_ua import polite_mailto
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
    experiment = p.data_dir / "experiments" / "experiment-report.json"
    manuscript = p.data_dir / "manuscripts" / "manuscript-draft.md"
    submission_bundle = p.data_dir / "submissions" / "submission-package"
    submission_archive = p.data_dir / "submissions" / "submission-package.tar.gz"
    release_report = p.data_dir / "releases" / "release-report.json"
    cfg_toml = default_toml_path()

    corpus_snapshot: dict[str, Any] = {
        "path": str(snap.resolve()),
        "present": snap.is_file(),
        "summary": None,
    }
    if snap.is_file():
        try:
            doc = load_corpus_snapshot_document(snap)
            corpus_snapshot["summary"] = summarize_corpus_snapshot(doc)
        except (OSError, json.JSONDecodeError, TypeError):
            corpus_snapshot["load_error"] = True

    return {
        "app_version": __version__,
        "autopapers_repo_root_env_set": bool(os.environ.get("AUTOPAPERS_REPO_ROOT", "").strip()),
        "polite_mailto_configured": polite_mailto() is not None,
        "config": {
            "provider": c.provider,
            "log_level": c.log_level,
            "contact_email": c.contact_email,
            "default_toml_path": str(cfg_toml),
            "default_toml_present": cfg_toml.is_file(),
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
        "corpus_snapshot": corpus_snapshot,
        "data": {
            "metadata_json": _safe_glob_count(p.papers_metadata_dir, "*.json"),
            "pdfs": _safe_glob_count(p.papers_pdfs_dir, "*.pdf"),
            "parsed_txt": _safe_glob_count(p.papers_parsed_dir, "*.txt"),
            "parse_manifests": _safe_glob_count(p.papers_parsed_dir, "*.manifest.json"),
            "profiles_json": _safe_glob_count(p.profiles_dir, "*.json"),
            "corpus_snapshot_exists": snap.is_file(),
            "proposal_draft_exists": draft.is_file(),
            "proposal_confirmed_exists": confirmed.is_file(),
            "experiment_report_exists": experiment.is_file(),
            "manuscript_draft_exists": manuscript.is_file(),
            "submission_bundle_exists": submission_bundle.is_dir(),
            "submission_archive_exists": submission_archive.is_file(),
            "release_report_exists": release_report.is_file(),
        },
    }
