from __future__ import annotations

from pathlib import Path

from pypdf import PdfWriter

from autopapers.phase1.papers.parse_pdf import (
    extract_and_save_txt,
    extract_pdf_text,
    extract_pdf_text_with_stats,
)


def _minimal_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        writer.write(f)


def _n_page_pdf(path: Path, n: int) -> None:
    writer = PdfWriter()
    for _ in range(n):
        writer.add_blank_page(width=72, height=72)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        writer.write(f)


def test_extract_and_save_txt_writes_file(tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"
    _minimal_pdf(pdf)
    out = tmp_path / "out" / "a.txt"
    text, total, read = extract_and_save_txt(pdf, out, max_pages=5)
    assert out.is_file()
    assert total >= 1
    assert read >= 1
    assert isinstance(text, str)


def test_extract_pdf_text_with_stats_respects_max_pages(tmp_path: Path) -> None:
    pdf = tmp_path / "multi.pdf"
    _n_page_pdf(pdf, 4)
    _text, total, read = extract_pdf_text_with_stats(pdf, max_pages=2)
    assert total == 4
    assert read == 2


def test_extract_pdf_text_matches_stats_text(tmp_path: Path) -> None:
    pdf = tmp_path / "one.pdf"
    _minimal_pdf(pdf)
    assert extract_pdf_text(pdf, max_pages=1) == extract_pdf_text_with_stats(
        pdf, max_pages=1
    )[0]


def test_extract_and_save_txt_max_pages_zero_reads_all(tmp_path: Path) -> None:
    pdf = tmp_path / "many.pdf"
    _n_page_pdf(pdf, 3)
    out = tmp_path / "full.txt"
    _t, total, read = extract_and_save_txt(pdf, out, max_pages=0)
    assert total == 3
    assert read == 3
