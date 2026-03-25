from __future__ import annotations

from pathlib import Path

from pypdf import PdfWriter

from autopapers.phase1.papers.parse_pdf import extract_and_save_txt


def _minimal_pdf(path: Path) -> None:
    writer = PdfWriter()
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
