from __future__ import annotations

import json
from pathlib import Path

import pytest
from pypdf import PdfWriter
from typer.testing import CliRunner

from autopapers.cli import app


def _minimal_profile(path: Path, *, pdf_abs: str) -> None:
    doc = {
        "schema_version": "0.1",
        "user": {"languages": ["en"]},
        "background": {"domains": [], "skills": [], "constraints": []},
        "hardware": {"device": "other"},
        "research_intent": {
            "problem_statements": [],
            "keywords": [pdf_abs],
            "non_goals": [],
            "risk_tolerance": "medium",
        },
    }
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def _tiny_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with path.open("wb") as f:
        writer.write(f)


def test_phase1_run_search_only_writes_search_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    pdf = tmp_path / "only_search.pdf"
    _tiny_pdf(pdf)
    prof = tmp_path / "p.json"
    _minimal_profile(prof, pdf_abs=str(pdf.resolve()))
    r = CliRunner().invoke(
        app,
        ["phase1", "run", "--profile", str(prof), "--limit", "1"],
        env={"AUTOPAPERS_PROVIDER": "local_pdf"},
    )
    assert r.exit_code == 0, r.stdout + r.stderr
    summary = json.loads(r.stdout)
    assert summary.get("count") == 1
    meta = Path(summary["metadata_file"])
    assert meta.is_file()
    row = json.loads(meta.read_text(encoding="utf-8"))
    assert row["type"] == "search"
    pdfs_dir = tmp_path / "data" / "papers" / "pdfs"
    assert not pdfs_dir.is_dir() or not any(pdfs_dir.glob("*.pdf"))


def test_phase1_dry_run_no_search(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    prof = tmp_path / "p.json"
    prof.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "user": {"languages": ["en"]},
                "background": {"domains": [], "skills": [], "constraints": []},
                "hardware": {"device": "other"},
                "research_intent": {
                    "problem_statements": [],
                    "keywords": ["rl", "transformer"],
                    "non_goals": [],
                    "risk_tolerance": "medium",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    runner = CliRunner()
    r = runner.invoke(
        app,
        ["phase1", "run", "--profile", str(prof), "--dry-run", "--limit", "5"],
        env={"AUTOPAPERS_PROVIDER": "arxiv"},
    )
    assert r.exit_code == 0
    out = json.loads(r.stdout)
    assert out["dry_run"] is True
    assert "rl" in out["query"] and "transformer" in out["query"]
    assert out["provider"] == "arxiv"
    assert out["limit"] == 5
    assert not (tmp_path / "data").exists()


def test_phase1_parse_fetched_requires_fetch_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    prof = tmp_path / "p.json"
    _minimal_profile(prof, pdf_abs=str(tmp_path / "x.pdf"))
    runner = CliRunner()
    r = runner.invoke(
        app,
        ["phase1", "run", "--profile", str(prof), "--parse-fetched"],
        env={"AUTOPAPERS_PROVIDER": "local_pdf"},
    )
    assert r.exit_code == 1


def test_phase1_parse_fetched_writes_parsed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    pdf = tmp_path / "doc.pdf"
    _tiny_pdf(pdf)
    prof = tmp_path / "p.json"
    _minimal_profile(prof, pdf_abs=str(pdf.resolve()))

    runner = CliRunner()
    r = runner.invoke(
        app,
        [
            "phase1",
            "run",
            "--profile",
            str(prof),
            "--fetch-first",
            "--parse-fetched",
            "--limit",
            "1",
        ],
        env={"AUTOPAPERS_PROVIDER": "local_pdf"},
    )
    assert r.exit_code == 0, r.stdout + r.stderr
    parsed = tmp_path / "data" / "papers" / "parsed" / "doc.txt"
    assert parsed.is_file()
    man = tmp_path / "data" / "papers" / "parsed" / "doc.manifest.json"
    assert man.is_file()
