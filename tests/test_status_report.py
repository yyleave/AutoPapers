from __future__ import annotations

from pathlib import Path

from autopapers.config import AppConfig, get_paths
from autopapers.status_report import build_status


def test_build_status_counts(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    paths.papers_metadata_dir.mkdir(parents=True)
    (paths.papers_metadata_dir / "a.json").write_text("{}", encoding="utf-8")
    paths.profiles_dir.mkdir(parents=True)
    (paths.profiles_dir / "p.json").write_text("{}", encoding="utf-8")

    r = build_status(paths=paths, cfg=AppConfig(provider="crossref", log_level="DEBUG"))
    assert r["app_version"]
    assert r["config"]["provider"] == "crossref"
    assert r["data"]["metadata_json"] == 1
    assert r["data"]["profiles_json"] == 1
    assert "crossref" in r["providers"]


def test_build_status_proposal_flags(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    paths.proposals_dir.mkdir(parents=True)
    (paths.proposals_dir / "proposal-draft.json").write_text("{}", encoding="utf-8")

    r = build_status(paths=paths)
    assert r["data"]["proposal_draft_exists"] is True
    assert r["data"]["proposal_confirmed_exists"] is False
