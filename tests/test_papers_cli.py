from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autopapers.cli import app


def test_papers_search_local_pdf_provider_no_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOPAPERS_PROVIDER", "local_pdf")
    pdf = tmp_path / "paper_x.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    r = CliRunner().invoke(
        app,
        ["papers", "search", "-q", str(pdf), "--no-save", "--limit", "2"],
    )
    assert r.exit_code == 0
    rows = json.loads(r.stdout)
    assert len(rows) == 1
    assert rows[0]["source"] == "local_pdf"
    assert rows[0]["id"] == "paper_x"


def test_papers_search_writes_search_metadata_when_not_no_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOPAPERS_PROVIDER", "local_pdf")
    pdf = tmp_path / "saved.pdf"
    pdf.write_bytes(b"%PDF")
    r = CliRunner().invoke(
        app,
        ["papers", "search", "-q", str(pdf), "--limit", "1"],
    )
    assert r.exit_code == 0
    assert "Wrote metadata" in (r.stderr or "")
    meta_dir = tmp_path / "data" / "papers" / "metadata"
    found = list(meta_dir.glob("search-*.json"))
    assert len(found) == 1
    row = json.loads(found[0].read_text(encoding="utf-8"))
    assert row["type"] == "search"
    assert row["provider"] == "local_pdf"
    assert row["count"] == 1


def test_show_metadata_requires_path_or_latest() -> None:
    r = CliRunner().invoke(app, ["papers", "show-metadata"])
    assert r.exit_code == 1


def test_show_metadata_rejects_invalid_latest() -> None:
    r = CliRunner().invoke(app, ["papers", "show-metadata", "--latest", "invalid"])
    assert r.exit_code == 1
