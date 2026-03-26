from __future__ import annotations

import json
from pathlib import Path

from autopapers.config import AppConfig, get_paths
from autopapers.status_report import build_status


def test_build_status_includes_contact_email_when_set(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    r = build_status(
        paths=paths,
        cfg=AppConfig(
            provider="arxiv",
            log_level="INFO",
            contact_email="writer@example.org",
        ),
    )
    assert r["config"]["contact_email"] == "writer@example.org"


def test_build_status_counts(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    paths.papers_metadata_dir.mkdir(parents=True)
    (paths.papers_metadata_dir / "a.json").write_text("{}", encoding="utf-8")
    paths.profiles_dir.mkdir(parents=True)
    (paths.profiles_dir / "p.json").write_text("{}", encoding="utf-8")

    r = build_status(paths=paths, cfg=AppConfig(provider="crossref", log_level="DEBUG"))
    assert r["app_version"]
    assert r["autopapers_repo_root_env_set"] is False
    assert "polite_mailto_configured" in r
    assert r["config"]["provider"] == "crossref"
    assert r["data"]["metadata_json"] == 1
    assert r["data"]["profiles_json"] == 1
    assert "crossref" in r["providers"]
    assert "default_toml_path" in r["config"]
    assert "default_toml_present" in r["config"]
    assert "contact_email" in r["config"]
    assert r["corpus_snapshot"]["present"] is False
    assert r["corpus_snapshot"]["summary"] is None


def test_build_status_includes_corpus_summary_when_present(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    paths.kg_dir.mkdir(parents=True)
    (paths.kg_dir / "corpus-snapshot.json").write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "nodes": [{"id": "1", "type": "Paper"}],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )
    r = build_status(paths=paths)
    assert r["corpus_snapshot"]["present"] is True
    assert r["corpus_snapshot"]["summary"] is not None
    assert r["corpus_snapshot"]["summary"]["node_total"] == 1


def test_build_status_corpus_snapshot_load_error_non_object(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    paths.kg_dir.mkdir(parents=True)
    (paths.kg_dir / "corpus-snapshot.json").write_text("[]", encoding="utf-8")
    r = build_status(paths=paths)
    assert r["corpus_snapshot"]["present"] is True
    assert r["corpus_snapshot"]["load_error"] is True
    assert r["corpus_snapshot"]["summary"] is None


def test_build_status_corpus_snapshot_load_error_on_bad_json(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    paths.kg_dir.mkdir(parents=True)
    (paths.kg_dir / "corpus-snapshot.json").write_text("{", encoding="utf-8")
    r = build_status(paths=paths)
    assert r["corpus_snapshot"]["present"] is True
    assert r["corpus_snapshot"]["load_error"] is True
    assert r["corpus_snapshot"]["summary"] is None


def test_build_status_proposal_flags(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    paths.proposals_dir.mkdir(parents=True)
    (paths.proposals_dir / "proposal-draft.json").write_text("{}", encoding="utf-8")

    r = build_status(paths=paths)
    assert r["data"]["proposal_draft_exists"] is True
    assert r["data"]["proposal_confirmed_exists"] is False

    (paths.proposals_dir / "proposal-confirmed.json").write_text("{}", encoding="utf-8")
    r2 = build_status(paths=paths)
    assert r2["data"]["proposal_draft_exists"] is True
    assert r2["data"]["proposal_confirmed_exists"] is True


def test_build_status_phase3_phase4_flags(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    exp = paths.data_dir / "experiments" / "experiment-report.json"
    ms = paths.data_dir / "manuscripts" / "manuscript-draft.md"
    bundle = paths.data_dir / "submissions" / "submission-package"

    r0 = build_status(paths=paths)
    assert r0["data"]["experiment_report_exists"] is False
    assert r0["data"]["manuscript_draft_exists"] is False
    assert r0["data"]["submission_bundle_exists"] is False

    exp.parent.mkdir(parents=True, exist_ok=True)
    ms.parent.mkdir(parents=True, exist_ok=True)
    bundle.mkdir(parents=True, exist_ok=True)
    exp.write_text("{}", encoding="utf-8")
    ms.write_text("# draft\n", encoding="utf-8")

    r1 = build_status(paths=paths)
    assert r1["data"]["experiment_report_exists"] is True
    assert r1["data"]["manuscript_draft_exists"] is True
    assert r1["data"]["submission_bundle_exists"] is True
