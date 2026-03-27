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


def test_publish_runs_full_pipeline_to_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    pdf = tmp_path / "pub.pdf"
    _tiny_pdf(pdf)
    profile = tmp_path / "user.json"
    profile.write_text(
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
        ["publish", "--profile", str(profile), "--title", "Publish Demo", "--limit", "1"],
        env={"AUTOPAPERS_PROVIDER": "local_pdf"},
    )
    assert r.exit_code == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] is True
    assert Path(out["proposal_confirmed"]).is_file()
    assert Path(out["submission_bundle"]).is_dir()
    assert Path(out["submission_archive"]).is_file()


def test_publish_no_archive_om_tar_gz(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    pdf = tmp_path / "pub.pdf"
    _tiny_pdf(pdf)
    profile = tmp_path / "user.json"
    profile.write_text(
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
        [
            "publish",
            "--profile",
            str(profile),
            "--title",
            "NoArchive",
            "--limit",
            "1",
            "--no-archive",
        ],
        env={"AUTOPAPERS_PROVIDER": "local_pdf"},
    )
    assert r.exit_code == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] is True
    assert Path(out["submission_bundle"]).is_dir()
    assert out["submission_archive"] is None
