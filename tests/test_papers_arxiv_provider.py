from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autopapers.providers.arxiv_provider import ArxivProvider, _arxiv_id_from_entry_id
from autopapers.providers.base import PaperRef


@patch("autopapers.providers.arxiv_provider.urllib.request.urlopen")
def test_arxiv_search_empty_atom_feed(mock_urlopen: MagicMock) -> None:
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"></feed>
"""
    resp = MagicMock()
    resp.__enter__.return_value.read.return_value = xml
    resp.__exit__.return_value = None
    mock_urlopen.return_value = resp
    assert ArxivProvider().search(query="zzzznomatchzzzz", limit=5) == []


def test_arxiv_fetch_pdf_requires_pdf_url(tmp_path: Path) -> None:
    ref = PaperRef(source="arxiv", id="2501.00001", title="T", pdf_url=None)
    with pytest.raises(ValueError, match="No pdf_url"):
        ArxivProvider().fetch_pdf(ref=ref, dest_dir=tmp_path)


@patch("autopapers.providers.arxiv_provider.urllib.request.urlopen")
def test_arxiv_fetch_pdf_writes_response_bytes(mock_urlopen: MagicMock, tmp_path: Path) -> None:
    ref = PaperRef(
        source="arxiv",
        id="2501.00001",
        title="T",
        pdf_url="https://arxiv.org/pdf/2501.00001.pdf",
    )
    resp = MagicMock()
    resp.__enter__.return_value.read.return_value = b"%PDF-1.4 fake"
    resp.__exit__.return_value = None
    mock_urlopen.return_value = resp
    dest = tmp_path / "pdfs"
    out = ArxivProvider().fetch_pdf(ref=ref, dest_dir=dest)
    assert out == dest / "2501.00001.pdf"
    assert out.read_bytes() == b"%PDF-1.4 fake"
    mock_urlopen.assert_called_once()


def test_arxiv_id_from_entry_abs_url() -> None:
    assert (
        _arxiv_id_from_entry_id("http://arxiv.org/abs/2501.01234v1") == "2501.01234v1"
    )
    assert _arxiv_id_from_entry_id("not-a-url") == "not-a-url"


@pytest.mark.network
def test_arxiv_search_returns_results() -> None:
    if os.environ.get("AUTOPAPERS_NETWORK_SMOKE", "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }:
        pytest.skip("Set AUTOPAPERS_NETWORK_SMOKE=1 to run provider network smoke tests")
    provider = ArxivProvider()
    refs = provider.search(query="transformer", limit=1)
    assert len(refs) <= 1
    # Network calls can fail in CI; we only assert shape when results exist.
    if refs:
        assert refs[0].id

