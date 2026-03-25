from __future__ import annotations

from pathlib import Path


def extract_pdf_text_with_stats(
    pdf_path: Path, *, max_pages: int | None = 20
) -> tuple[str, int, int]:
    """
    Return (extracted_text, total_page_count, pages_read).
    """
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise RuntimeError(
            "pypdf is required for PDF parsing. Install dependencies with: uv sync"
        ) from e

    reader = PdfReader(str(pdf_path))
    parts: list[str] = []
    n = len(reader.pages)
    limit = n if max_pages is None else min(n, max_pages)
    for i in range(limit):
        text = reader.pages[i].extract_text() or ""
        if text.strip():
            parts.append(text)
    return "\n\n".join(parts).strip(), n, limit


def extract_pdf_text(pdf_path: Path, *, max_pages: int | None = 20) -> str:
    """
    Best-effort PDF text extraction (Phase 1 stub for KG upstream).

    Uses pypdf when available. Install: project dependency `pypdf`.
    """

    return extract_pdf_text_with_stats(pdf_path, max_pages=max_pages)[0]


def extract_and_save_txt(
    input_pdf: Path,
    output_txt: Path,
    *,
    max_pages: int | None,
) -> tuple[str, int, int]:
    """
    Extract text and write ``output_txt`` (UTF-8). ``max_pages`` 0 or None = all pages.
    Returns (text, total_pages, pages_read).
    """

    limit = None if max_pages in (0, None) else max_pages
    text, pages_total, pages_read = extract_pdf_text_with_stats(
        input_pdf, max_pages=limit
    )
    output_txt.parent.mkdir(parents=True, exist_ok=True)
    output_txt.write_text(text + "\n", encoding="utf-8")
    return text, pages_total, pages_read
