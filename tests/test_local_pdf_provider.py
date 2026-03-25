from __future__ import annotations

from pathlib import Path

from autopapers.providers.local_pdf_provider import LocalPdfProvider


def test_local_pdf_search_single_file(tmp_path: Path) -> None:
    pdf = tmp_path / "paper_a.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    prov = LocalPdfProvider()
    refs = prov.search(query=str(pdf), limit=5)
    assert len(refs) == 1
    assert refs[0].id == "paper_a"
    assert refs[0].source == "local_pdf"
    assert refs[0].pdf_url == str(pdf)


def test_local_pdf_search_skips_non_pdf_file(tmp_path: Path) -> None:
    f = tmp_path / "notes.txt"
    f.write_text("x", encoding="utf-8")
    prov = LocalPdfProvider()
    assert prov.search(query=str(f)) == []


def test_local_pdf_search_directory_respects_limit(tmp_path: Path) -> None:
    for i in range(4):
        (tmp_path / f"doc{i}.pdf").write_bytes(b"%PDF")
    prov = LocalPdfProvider()
    refs = prov.search(query=str(tmp_path), limit=2)
    assert len(refs) == 2


def test_local_pdf_search_missing_path_returns_empty() -> None:
    prov = LocalPdfProvider()
    assert prov.search(query="/nonexistent/path/zzz-no-pdf") == []


def test_local_pdf_fetch_copies_into_dest(tmp_path: Path) -> None:
    src = tmp_path / "source.pdf"
    src.write_bytes(b"%PDF-bytes")
    prov = LocalPdfProvider()
    refs = prov.search(query=str(src))
    dest_dir = tmp_path / "out"
    out = prov.fetch_pdf(ref=refs[0], dest_dir=dest_dir)
    assert out.is_file()
    assert out.read_bytes() == b"%PDF-bytes"
    assert out.parent == dest_dir
