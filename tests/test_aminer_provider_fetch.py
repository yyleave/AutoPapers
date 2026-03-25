from __future__ import annotations

from pathlib import Path

import pytest

from autopapers.providers.aminer_provider import AminerProvider
from autopapers.providers.base import PaperRef


def test_aminer_fetch_pdf_copies_local_file(tmp_path: Path) -> None:
    src = tmp_path / "paper.pdf"
    src.write_bytes(b"%PDF-local")
    ref = PaperRef(source="aminer", id="pid-1", title="T", pdf_url=str(src))
    dest_dir = tmp_path / "downloads"
    out = AminerProvider().fetch_pdf(ref=ref, dest_dir=dest_dir)
    assert out == dest_dir / "paper.pdf"
    assert out.read_bytes() == b"%PDF-local"


def test_aminer_fetch_pdf_missing_local_raises(tmp_path: Path) -> None:
    ref = PaperRef(
        source="aminer",
        id="x",
        title="T",
        pdf_url=str(tmp_path / "nope.pdf"),
    )
    with pytest.raises(ValueError, match="Cannot fetch PDF"):
        AminerProvider().fetch_pdf(ref=ref, dest_dir=tmp_path / "out")


def test_aminer_fetch_pdf_no_url_raises(tmp_path: Path) -> None:
    ref = PaperRef(source="aminer", id="x", title="T", pdf_url=None)
    with pytest.raises(ValueError, match="No pdf_url"):
        AminerProvider().fetch_pdf(ref=ref, dest_dir=tmp_path / "out")
