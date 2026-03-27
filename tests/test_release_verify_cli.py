from __future__ import annotations

import json
from pathlib import Path

import pytest
from pypdf import PdfWriter
from typer.testing import CliRunner

from autopapers import __version__ as autopapers_version
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


def test_release_verify_ok(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    pdf = tmp_path / "x.pdf"
    _tiny_pdf(pdf)
    prof = tmp_path / "user.json"
    _profile(prof, str(pdf.resolve()))
    rel = CliRunner().invoke(
        app,
        ["release", "--profile", str(prof)],
        env={"AUTOPAPERS_PROVIDER": "local_pdf"},
    )
    assert rel.exit_code == 0
    out = CliRunner().invoke(app, ["release-verify"])
    assert out.exit_code == 0
    payload = json.loads(out.stdout)
    assert payload["ok"] is True
    vrep = Path(payload["release_verify_report"])
    assert vrep.is_file()
    vr_doc = json.loads(vrep.read_text(encoding="utf-8"))
    assert vr_doc["schema_version"] == "0.2"
    assert vr_doc["autopapers_version"] == autopapers_version
    assert isinstance(vr_doc.get("generated_at"), str) and vr_doc["generated_at"].endswith("Z")
    assert payload["status"]["data"]["release_verify_report_exists"] is True


def test_release_verify_ok_without_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    pdf = tmp_path / "z.pdf"
    _tiny_pdf(pdf)
    prof = tmp_path / "user.json"
    _profile(prof, str(pdf.resolve()))
    rel = CliRunner().invoke(
        app,
        ["release", "--profile", str(prof), "--no-archive"],
        env={"AUTOPAPERS_PROVIDER": "local_pdf"},
    )
    assert rel.exit_code == 0
    out = CliRunner().invoke(app, ["release-verify"])
    assert out.exit_code == 0
    payload = json.loads(out.stdout)
    assert payload["ok"] is True


def test_release_verify_detects_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    pdf = tmp_path / "y.pdf"
    _tiny_pdf(pdf)
    prof = tmp_path / "user.json"
    _profile(prof, str(pdf.resolve()))
    rel = CliRunner().invoke(
        app,
        ["release", "--profile", str(prof)],
        env={"AUTOPAPERS_PROVIDER": "local_pdf"},
    )
    assert rel.exit_code == 0
    release_report = tmp_path / "data" / "releases" / "release-report.json"
    rep = json.loads(release_report.read_text(encoding="utf-8"))
    bundle = Path(rep["submission_bundle"])
    (bundle / "manuscript-draft.md").write_text("# tampered\n", encoding="utf-8")
    out = CliRunner().invoke(app, ["release-verify"])
    assert out.exit_code == 1
    err = json.loads(out.stderr.strip())
    assert err["ok"] is False
    assert err["detail"]["hashes"]["ok"] is False
