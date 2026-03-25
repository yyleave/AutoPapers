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
