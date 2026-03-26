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


def _profile(path: Path, keyword: str) -> None:
    path.write_text(
        json.dumps(
            {
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
        ),
        encoding="utf-8",
    )


def test_release_runs_publish_and_verify(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    pdf = tmp_path / "release.pdf"
    _tiny_pdf(pdf)
    prof = tmp_path / "user.json"
    _profile(prof, str(pdf.resolve()))
    r = CliRunner().invoke(
        app,
        ["release", "--profile", str(prof), "--title", "Release Demo", "--limit", "1"],
        env={"AUTOPAPERS_PROVIDER": "local_pdf"},
    )
    assert r.exit_code == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] is True
    report = Path(out["release_report"])
    assert report.is_file()
    rep = json.loads(report.read_text(encoding="utf-8"))
    assert rep["ok"] is True
    assert Path(rep["submission_archive"]).is_file()
    assert out["status"]["data"]["release_report_exists"] is True


def test_release_no_verify_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    pdf = tmp_path / "release2.pdf"
    _tiny_pdf(pdf)
    prof = tmp_path / "user.json"
    _profile(prof, str(pdf.resolve()))
    r = CliRunner().invoke(
        app,
        ["release", "--profile", str(prof), "--no-verify"],
        env={"AUTOPAPERS_PROVIDER": "local_pdf"},
    )
    assert r.exit_code == 0
    out = json.loads(r.stdout)
    assert out["ok"] is True
    assert out["verify"] is None
