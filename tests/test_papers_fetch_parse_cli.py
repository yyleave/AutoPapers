from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pypdf import PdfWriter
from typer.testing import CliRunner

from autopapers.cli import app
from autopapers.providers.aminer_provider import AminerProvider
from autopapers.providers.arxiv_provider import ArxivProvider
from autopapers.providers.crossref_provider import CrossrefProvider
from autopapers.providers.openalex_provider import OpenAlexProvider


def _tiny_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        writer.write(f)


def test_papers_fetch_local_pdf_missing_path_exits_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    missing = tmp_path / "does-not-exist.pdf"
    r = CliRunner().invoke(
        app,
        [
            "papers",
            "fetch",
            "--source",
            "local_pdf",
            "--id",
            "x",
            "--pdf-url",
            str(missing),
        ],
    )
    assert r.exit_code != 0


def test_papers_fetch_local_pdf_copies_to_pdfs_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "source.pdf"
    src.write_bytes(b"%PDF-bytes")
    r = CliRunner().invoke(
        app,
        [
            "papers",
            "fetch",
            "--source",
            "local_pdf",
            "--id",
            "source",
            "--pdf-url",
            str(src),
        ],
    )
    assert r.exit_code == 0
    out_line = r.stdout.strip().split("\n", 1)[0]
    out_pdf = Path(out_line)
    assert out_pdf.is_file()
    assert out_pdf.read_bytes() == b"%PDF-bytes"
    assert (tmp_path / "data" / "papers" / "metadata").is_dir()
    meta_files = list((tmp_path / "data" / "papers" / "metadata").glob("fetch-*.json"))
    assert len(meta_files) == 1
    meta = json.loads(meta_files[0].read_text(encoding="utf-8"))
    assert meta["type"] == "fetch"
    assert meta["id"] == "source"


@patch.object(ArxivProvider, "fetch_pdf")
def test_papers_fetch_arxiv_cli_mocked_writes_fetch_metadata(
    mock_fetch: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    out_pdf = tmp_path / "data" / "papers" / "pdfs" / "2501.00001.pdf"
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    out_pdf.write_bytes(b"%PDF-mock")
    mock_fetch.return_value = out_pdf

    r = CliRunner().invoke(
        app,
        [
            "papers",
            "fetch",
            "--source",
            "arxiv",
            "--id",
            "2501.00001",
            "--title",
            "Mock title",
            "--pdf-url",
            "https://arxiv.org/pdf/2501.00001.pdf",
        ],
    )
    assert r.exit_code == 0
    first_line = r.stdout.strip().split("\n", 1)[0]
    assert first_line == str(out_pdf.resolve())
    assert "Wrote metadata" in (r.stderr or "")
    metas = list((tmp_path / "data" / "papers" / "metadata").glob("fetch-*.json"))
    assert len(metas) == 1
    doc = json.loads(metas[0].read_text(encoding="utf-8"))
    assert doc["type"] == "fetch"
    assert doc["id"] == "2501.00001"
    mock_fetch.assert_called_once()


@patch.object(CrossrefProvider, "fetch_pdf")
def test_papers_fetch_crossref_cli_mocked_writes_fetch_metadata(
    mock_fetch: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    out_pdf = tmp_path / "data" / "papers" / "pdfs" / "10.1000_fetch.pdf"
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    out_pdf.write_bytes(b"%PDF-cr")
    mock_fetch.return_value = out_pdf

    r = CliRunner().invoke(
        app,
        [
            "papers",
            "fetch",
            "--source",
            "crossref",
            "--id",
            "10.1000/fetch",
            "--title",
            "CR title",
            "--pdf-url",
            "https://pub.example/article.pdf",
        ],
    )
    assert r.exit_code == 0
    first_line = r.stdout.strip().split("\n", 1)[0]
    assert first_line == str(out_pdf.resolve())
    assert "Wrote metadata" in (r.stderr or "")
    metas = list((tmp_path / "data" / "papers" / "metadata").glob("fetch-*.json"))
    assert len(metas) == 1
    doc = json.loads(metas[0].read_text(encoding="utf-8"))
    assert doc["type"] == "fetch"
    assert doc["id"] == "10.1000/fetch"
    mock_fetch.assert_called_once()


@patch.object(OpenAlexProvider, "fetch_pdf")
def test_papers_fetch_openalex_cli_mocked_writes_fetch_metadata(
    mock_fetch: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    out_pdf = tmp_path / "data" / "papers" / "pdfs" / "W200.pdf"
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    out_pdf.write_bytes(b"%PDF-oa")
    mock_fetch.return_value = out_pdf

    r = CliRunner().invoke(
        app,
        [
            "papers",
            "fetch",
            "--source",
            "openalex",
            "--id",
            "W200",
            "--title",
            "OA title",
            "--pdf-url",
            "https://oa.example/paper.pdf",
        ],
    )
    assert r.exit_code == 0
    first_line = r.stdout.strip().split("\n", 1)[0]
    assert first_line == str(out_pdf.resolve())
    assert "Wrote metadata" in (r.stderr or "")
    metas = list((tmp_path / "data" / "papers" / "metadata").glob("fetch-*.json"))
    assert len(metas) == 1
    doc = json.loads(metas[0].read_text(encoding="utf-8"))
    assert doc["type"] == "fetch"
    assert doc["id"] == "W200"
    mock_fetch.assert_called_once()


@patch.object(AminerProvider, "fetch_pdf")
def test_papers_fetch_aminer_cli_mocked_writes_fetch_metadata(
    mock_fetch: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    out_pdf = tmp_path / "data" / "papers" / "pdfs" / "PID_001.pdf"
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    out_pdf.write_bytes(b"%PDF-aminer")
    mock_fetch.return_value = out_pdf

    r = CliRunner().invoke(
        app,
        [
            "papers",
            "fetch",
            "--source",
            "aminer",
            "--id",
            "PID_001",
            "--title",
            "AMiner paper",
            "--pdf-url",
            "https://static.aminer.cn/pdf/example.pdf",
        ],
    )
    assert r.exit_code == 0
    first_line = r.stdout.strip().split("\n", 1)[0]
    assert first_line == str(out_pdf.resolve())
    assert "Wrote metadata" in (r.stderr or "")
    metas = list((tmp_path / "data" / "papers" / "metadata").glob("fetch-*.json"))
    assert len(metas) == 1
    doc = json.loads(metas[0].read_text(encoding="utf-8"))
    assert doc["type"] == "fetch"
    assert doc["id"] == "PID_001"
    assert doc["source"] == "aminer"
    mock_fetch.assert_called_once()


def test_papers_fetch_unknown_source_exits_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(
        app,
        ["papers", "fetch", "--source", "not_a_provider", "--id", "x"],
    )
    assert r.exit_code != 0


def test_papers_parse_custom_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    pdf = tmp_path / "in.pdf"
    _tiny_pdf(pdf)
    out = tmp_path / "nested" / "custom-out.txt"
    r = CliRunner().invoke(
        app,
        [
            "papers",
            "parse",
            "-i",
            str(pdf),
            "-o",
            str(out),
            "--max-pages",
            "1",
        ],
    )
    assert r.exit_code == 0
    assert Path(r.stdout.strip()) == out
    assert out.is_file()


def test_papers_parse_writes_parsed_txt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    pdf = tmp_path / "doc.pdf"
    _tiny_pdf(pdf)
    r = CliRunner().invoke(
        app,
        ["papers", "parse", "-i", str(pdf), "--max-pages", "1"],
    )
    assert r.exit_code == 0
    txt_path = Path(r.stdout.strip())
    assert txt_path.is_file()
    assert txt_path.parent.name == "parsed"
    assert txt_path.suffix == ".txt"


def test_papers_parse_write_manifest_creates_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    pdf = tmp_path / "with_manifest.pdf"
    _tiny_pdf(pdf)
    r = CliRunner().invoke(
        app,
        [
            "papers",
            "parse",
            "-i",
            str(pdf),
            "--max-pages",
            "1",
            "--write-manifest",
        ],
    )
    assert r.exit_code == 0
    txt_path = Path(r.stdout.strip().split("\n")[0])
    man = txt_path.with_name(f"{txt_path.stem}.manifest.json")
    assert man.is_file()
    meta = json.loads(man.read_text(encoding="utf-8"))
    assert meta["type"] == "parse"
    assert "Wrote manifest" in (r.stderr or "")


def test_papers_parse_batch_processes_glob(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    indir = tmp_path / "in_pdfs"
    indir.mkdir(parents=True)
    _tiny_pdf(indir / "one.pdf")
    _tiny_pdf(indir / "two.pdf")
    r = CliRunner().invoke(
        app,
        [
            "papers",
            "parse-batch",
            "--input-dir",
            str(indir),
            "--pattern",
            "*.pdf",
            "--max-pages",
            "1",
        ],
    )
    assert r.exit_code == 0
    out_lines = [ln for ln in r.stdout.strip().split("\n") if ln]
    assert len(out_lines) == 2
    summary = json.loads(r.stderr.strip())
    assert summary["parsed"] == 2
    assert summary["errors"] == []


def test_papers_parse_batch_write_manifest_per_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    indir = tmp_path / "batch_in"
    indir.mkdir(parents=True)
    _tiny_pdf(indir / "solo.pdf")
    r = CliRunner().invoke(
        app,
        [
            "papers",
            "parse-batch",
            "--input-dir",
            str(indir),
            "--max-pages",
            "1",
            "--write-manifest",
        ],
    )
    assert r.exit_code == 0
    parsed = tmp_path / "data" / "papers" / "parsed"
    assert (parsed / "solo.txt").is_file()
    assert (parsed / "solo.manifest.json").is_file()
    assert "manifest:" in (r.stderr or "").lower()


def test_papers_parse_batch_continues_after_bad_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    indir = tmp_path / "mixed_pdfs"
    indir.mkdir(parents=True)
    _tiny_pdf(indir / "good.pdf")
    (indir / "bad.pdf").write_bytes(b"not-a-pdf")
    r = CliRunner().invoke(
        app,
        [
            "papers",
            "parse-batch",
            "--input-dir",
            str(indir),
            "--max-pages",
            "1",
        ],
    )
    assert r.exit_code == 0
    err = r.stderr.strip()
    summary = json.loads(err[err.index("{") :])
    assert summary["parsed"] == 1
    assert len(summary["errors"]) == 1
    assert "bad.pdf" in summary["errors"][0]
