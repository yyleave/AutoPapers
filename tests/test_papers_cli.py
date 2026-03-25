from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from autopapers.cli import app
from autopapers.providers.arxiv_provider import ArxivProvider
from autopapers.providers.base import PaperRef
from autopapers.providers.crossref_provider import CrossrefProvider
from autopapers.providers.openalex_provider import OpenAlexProvider
from autopapers.repo_paths import ensure_legacy_api_on_path


def test_papers_search_local_pdf_directory_lists_pdfs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOPAPERS_PROVIDER", "local_pdf")
    d = tmp_path / "pdf_dir"
    d.mkdir()
    (d / "first.pdf").write_bytes(b"%PDF")
    (d / "second.pdf").write_bytes(b"%PDF")
    r = CliRunner().invoke(
        app,
        ["papers", "search", "-q", str(d), "--no-save", "--limit", "10"],
    )
    assert r.exit_code == 0
    rows = json.loads(r.stdout)
    assert len(rows) == 2
    ids = {row["id"] for row in rows}
    assert ids == {"first", "second"}


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


@patch.object(ArxivProvider, "search")
def test_papers_search_arxiv_cli_mocked_writes_search_metadata(
    mock_search: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOPAPERS_PROVIDER", "arxiv")
    mock_search.return_value = [
        PaperRef(
            source="arxiv",
            id="2501.00002",
            title="Mock paper",
            pdf_url="https://arxiv.org/pdf/2501.00002.pdf",
        ),
    ]
    r = CliRunner().invoke(app, ["papers", "search", "-q", "attention", "--limit", "1"])
    assert r.exit_code == 0
    rows = json.loads(r.stdout.strip())
    assert len(rows) == 1
    assert rows[0]["id"] == "2501.00002"
    assert "Wrote metadata" in (r.stderr or "")
    meta_dir = tmp_path / "data" / "papers" / "metadata"
    found = list(meta_dir.glob("search-*.json"))
    assert len(found) == 1
    row = json.loads(found[0].read_text(encoding="utf-8"))
    assert row["type"] == "search"
    assert row["provider"] == "arxiv"
    assert row["query"] == "attention"
    assert row["count"] == 1
    mock_search.assert_called_once_with(query="attention", limit=1)


@patch.object(ArxivProvider, "search")
def test_papers_search_arxiv_no_save_skips_metadata_write(
    mock_search: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOPAPERS_PROVIDER", "arxiv")
    mock_search.return_value = [
        PaperRef(
            source="arxiv",
            id="2501.00099",
            title="No save",
            pdf_url="https://arxiv.org/pdf/2501.00099.pdf",
        ),
    ]
    r = CliRunner().invoke(
        app,
        ["papers", "search", "-q", "test", "--limit", "1", "--no-save"],
    )
    assert r.exit_code == 0
    rows = json.loads(r.stdout.strip())
    assert len(rows) == 1
    assert "Wrote metadata" not in (r.stderr or "")
    meta_dir = tmp_path / "data" / "papers" / "metadata"
    assert (not meta_dir.is_dir()) or not list(meta_dir.glob("search-*.json"))
    mock_search.assert_called_once_with(query="test", limit=1)


@patch.object(OpenAlexProvider, "search")
def test_papers_search_openalex_cli_mocked_writes_search_metadata(
    mock_search: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOPAPERS_PROVIDER", "openalex")
    mock_search.return_value = [
        PaperRef(
            source="openalex",
            id="W424242",
            title="OpenAlex mock",
            pdf_url="https://oa.example/p.pdf",
        ),
    ]
    r = CliRunner().invoke(app, ["papers", "search", "-q", "attention is", "--limit", "2"])
    assert r.exit_code == 0
    rows = json.loads(r.stdout.strip())
    assert len(rows) == 1
    assert rows[0]["id"] == "W424242"
    assert "Wrote metadata" in (r.stderr or "")
    found = list((tmp_path / "data" / "papers" / "metadata").glob("search-*.json"))
    assert len(found) == 1
    row = json.loads(found[0].read_text(encoding="utf-8"))
    assert row["provider"] == "openalex"
    assert row["query"] == "attention is"
    assert row["count"] == 1
    mock_search.assert_called_once_with(query="attention is", limit=2)


@patch.object(OpenAlexProvider, "search")
def test_papers_search_openalex_no_save_skips_metadata_write(
    mock_search: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOPAPERS_PROVIDER", "openalex")
    mock_search.return_value = [
        PaperRef(source="openalex", id="W9", title="Ns", pdf_url=None),
    ]
    r = CliRunner().invoke(
        app,
        ["papers", "search", "-q", "q", "--limit", "3", "--no-save"],
    )
    assert r.exit_code == 0
    rows = json.loads(r.stdout.strip())
    assert len(rows) == 1
    assert rows[0]["id"] == "W9"
    assert "Wrote metadata" not in (r.stderr or "")
    meta_dir = tmp_path / "data" / "papers" / "metadata"
    assert (not meta_dir.is_dir()) or not list(meta_dir.glob("search-*.json"))
    mock_search.assert_called_once_with(query="q", limit=3)


@patch.object(CrossrefProvider, "search")
def test_papers_search_crossref_cli_mocked_writes_search_metadata(
    mock_search: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOPAPERS_PROVIDER", "crossref")
    mock_search.return_value = [
        PaperRef(
            source="crossref",
            id="10.1000/cr",
            title="Crossref CLI mock",
            pdf_url="https://journals.example/a.pdf",
        ),
    ]
    r = CliRunner().invoke(
        app,
        ["papers", "search", "-q", "machine learning survey", "--limit", "5"],
    )
    assert r.exit_code == 0
    rows = json.loads(r.stdout.strip())
    assert len(rows) == 1
    assert rows[0]["id"] == "10.1000/cr"
    assert "Wrote metadata" in (r.stderr or "")
    found = list((tmp_path / "data" / "papers" / "metadata").glob("search-*.json"))
    assert len(found) == 1
    row = json.loads(found[0].read_text(encoding="utf-8"))
    assert row["provider"] == "crossref"
    assert row["query"] == "machine learning survey"
    assert row["count"] == 1
    mock_search.assert_called_once_with(query="machine learning survey", limit=5)


@patch.object(CrossrefProvider, "search")
def test_papers_search_crossref_no_save_skips_metadata_write(
    mock_search: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOPAPERS_PROVIDER", "crossref")
    mock_search.return_value = [
        PaperRef(source="crossref", id="10.0/nosave", title="N", pdf_url=None),
    ]
    r = CliRunner().invoke(
        app,
        ["papers", "search", "-q", "cells", "--limit", "2", "--no-save"],
    )
    assert r.exit_code == 0
    rows = json.loads(r.stdout.strip())
    assert len(rows) == 1
    assert rows[0]["id"] == "10.0/nosave"
    assert "Wrote metadata" not in (r.stderr or "")
    meta_dir = tmp_path / "data" / "papers" / "metadata"
    assert (not meta_dir.is_dir()) or not list(meta_dir.glob("search-*.json"))
    mock_search.assert_called_once_with(query="cells", limit=2)


@patch("api.aminer_client.AMinerClient")
def test_papers_search_aminer_cli_mocked_writes_search_metadata(
    mock_client_cls: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_legacy_api_on_path()
    from api.aminer_client import Paper

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOPAPERS_PROVIDER", "aminer")
    mock_inst = MagicMock()
    mock_client_cls.return_value = mock_inst
    p = Paper(
        id="aminer-cli-1",
        title="AM title",
        authors=["A"],
        pdf_url="https://x/y.pdf",
    )
    mock_inst.paper_search.return_value = [p]
    mock_inst.paper_info.return_value = [p]

    r = CliRunner().invoke(app, ["papers", "search", "-q", "topic search", "--limit", "3"])
    assert r.exit_code == 0
    rows = json.loads(r.stdout.strip())
    assert len(rows) == 1
    assert rows[0]["id"] == "aminer-cli-1"
    assert rows[0]["source"] == "aminer"
    assert "Wrote metadata" in (r.stderr or "")
    found = list((tmp_path / "data" / "papers" / "metadata").glob("search-*.json"))
    assert len(found) == 1
    row = json.loads(found[0].read_text(encoding="utf-8"))
    assert row["provider"] == "aminer"
    assert row["query"] == "topic search"
    assert row["count"] == 1
    mock_inst.paper_search.assert_called_once_with("topic search", page=0, size=3)
    mock_inst.paper_info.assert_called_once_with(["aminer-cli-1"])


@patch("api.aminer_client.AMinerClient")
def test_papers_search_aminer_no_save_empty_skips_metadata(
    mock_client_cls: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_inst = MagicMock()
    mock_client_cls.return_value = mock_inst
    mock_inst.paper_search.return_value = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOPAPERS_PROVIDER", "aminer")
    r = CliRunner().invoke(
        app,
        ["papers", "search", "-q", "none", "--limit", "1", "--no-save"],
    )
    assert r.exit_code == 0
    assert json.loads(r.stdout.strip()) == []
    assert "Wrote metadata" not in (r.stderr or "")
    meta_dir = tmp_path / "data" / "papers" / "metadata"
    assert (not meta_dir.is_dir()) or not list(meta_dir.glob("search-*.json"))
    mock_inst.paper_info.assert_not_called()


def test_show_metadata_latest_empty_dir_exits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "papers" / "metadata").mkdir(parents=True)
    r = CliRunner().invoke(app, ["papers", "show-metadata", "--latest", "any"])
    assert r.exit_code == 1
    err = json.loads(r.stderr.strip())
    assert err["error"] == "no_metadata_files"


def test_show_metadata_requires_path_or_latest() -> None:
    r = CliRunner().invoke(app, ["papers", "show-metadata"])
    assert r.exit_code == 1


def test_show_metadata_rejects_path_and_latest_together(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    f = tmp_path / "meta.json"
    f.write_text("{}", encoding="utf-8")
    r = CliRunner().invoke(
        app,
        ["papers", "show-metadata", "--path", str(f), "--latest", "any"],
    )
    assert r.exit_code == 1


def test_show_metadata_rejects_invalid_latest() -> None:
    r = CliRunner().invoke(app, ["papers", "show-metadata", "--latest", "invalid"])
    assert r.exit_code == 1


def test_show_metadata_invalid_json_exits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    bad = tmp_path / "broken-meta.json"
    bad.write_text("{", encoding="utf-8")
    r = CliRunner().invoke(app, ["papers", "show-metadata", "--path", str(bad)])
    assert r.exit_code == 1
    err = json.loads(r.stderr)
    assert err.get("error") == "invalid_json"
