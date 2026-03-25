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
