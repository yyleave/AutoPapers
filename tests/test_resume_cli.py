from __future__ import annotations

import json
from pathlib import Path

import pytest
from pypdf import PdfWriter
from typer.testing import CliRunner

from autopapers.cli import app
from autopapers.phase2.debate import merge_stub_to_proposal, run_debate_stub


def _tiny_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        writer.write(f)


def _confirmed(path: Path) -> None:
    d = run_debate_stub(profile_summary="p", corpus_summary="c")
    p = merge_stub_to_proposal(title="Resume", debate=d, status="confirmed")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(p, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_resume_from_confirmed_proposal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    confirmed = tmp_path / "data" / "proposals" / "proposal-confirmed.json"
    _confirmed(confirmed)
    r = CliRunner().invoke(app, ["resume"])
    assert r.exit_code == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] is True
    assert Path(out["experiment_report"]).is_file()
    assert Path(out["evaluation_summary"]).is_file()
    assert Path(out["submission_bundle"]).is_dir()
    assert Path(out["submission_archive"]).is_file()


def test_resume_falls_back_to_release_with_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    pdf = tmp_path / "r.pdf"
    _tiny_pdf(pdf)
    prof = tmp_path / "user.json"
    prof.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "user": {"languages": ["en"]},
                "background": {"domains": [], "skills": [], "constraints": []},
                "hardware": {"device": "other"},
                "research_intent": {
                    "problem_statements": [],
                    "keywords": [str(pdf.resolve())],
                    "non_goals": [],
                    "risk_tolerance": "medium",
                },
            }
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(
        app,
        ["resume", "--profile", str(prof)],
        env={"AUTOPAPERS_PROVIDER": "local_pdf"},
    )
    assert r.exit_code == 0
    out = json.loads(r.stdout)
    assert out["ok"] is True
    assert Path(out["release_report"]).is_file()


def test_resume_without_confirmed_and_profile_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["resume"])
    assert r.exit_code == 1
    err = json.loads(r.stderr.strip())
    assert err["error"] == "resume_unavailable"
