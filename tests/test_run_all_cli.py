from __future__ import annotations

import json
from pathlib import Path

import pytest
from pypdf import PdfWriter
from typer.testing import CliRunner

from autopapers.cli import app


def _tiny_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        writer.write(f)


def _minimal_profile(path: Path, *, keyword: str) -> None:
    doc = {
        "schema_version": "0.1",
        "user": {"languages": ["en"]},
        "background": {"domains": [], "skills": [], "constraints": []},
        "hardware": {"device": "other"},
        "research_intent": {
            "problem_statements": [],
            "keywords": [keyword],
            "non_goals": [],
            "risk_tolerance": "medium",
        },
    }
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def test_run_all_local_pdf_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    pdf = tmp_path / "demo.pdf"
    _tiny_pdf(pdf)
    profile = tmp_path / "user.json"
    _minimal_profile(profile, keyword=str(pdf.resolve()))

    r = CliRunner().invoke(
        app,
        ["run-all", "--profile", str(profile), "--title", "All Flow", "--limit", "1"],
        env={"AUTOPAPERS_PROVIDER": "local_pdf"},
    )
    assert r.exit_code == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] is True
    assert out["provider"] == "local_pdf"
    assert out["search_count"] == 1
    assert Path(out["search_metadata"]).is_file()
    assert Path(out["fetch_metadata"]).is_file()
    assert Path(out["pdf"]).is_file()
    assert Path(out["parsed_txt"]).is_file()
    assert Path(out["parse_manifest"]).is_file()
    assert Path(out["corpus_snapshot"]).is_file()
    assert Path(out["proposal_draft"]).is_file()
    assert Path(out["proposal_confirmed"]).is_file()
    assert Path(out["proposal_markdown"]).is_file()
    assert out["status"]["data"]["proposal_confirmed_exists"] is True


def test_run_all_unknown_provider_exits_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    pdf = tmp_path / "demo.pdf"
    _tiny_pdf(pdf)
    profile = tmp_path / "user.json"
    _minimal_profile(profile, keyword=str(pdf.resolve()))
    r = CliRunner().invoke(
        app,
        [
            "run-all",
            "--profile",
            str(profile),
            "--title",
            "T",
            "--limit",
            "1",
            "--provider",
            "not_a_provider",
        ],
        env={"AUTOPAPERS_PROVIDER": "local_pdf"},
    )
    assert r.exit_code == 1
    err = json.loads(r.stderr.strip())
    assert err["error"] == "unknown_provider"

