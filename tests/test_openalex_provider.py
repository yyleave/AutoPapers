from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autopapers.providers.base import PaperRef
from autopapers.providers.openalex_provider import (
    OpenAlexProvider,
    _openalex_short_id,
    _pick_pdf_url,
)


@patch("autopapers.providers.openalex_provider.urllib.request.urlopen")
def test_openalex_search_empty_results(mock_urlopen: MagicMock) -> None:
    body = {"results": []}
    resp = MagicMock()
    resp.__enter__.return_value.read.return_value = json.dumps(body).encode("utf-8")
    resp.__exit__.return_value = None
    mock_urlopen.return_value = resp
    assert OpenAlexProvider().search(query="nothing", limit=5) == []


@patch("autopapers.providers.openalex_provider.urllib.request.urlopen")
def test_openalex_search_non_list_results(mock_urlopen: MagicMock) -> None:
    body = {"results": "unexpected"}
    resp = MagicMock()
    resp.__enter__.return_value.read.return_value = json.dumps(body).encode("utf-8")
    resp.__exit__.return_value = None
    mock_urlopen.return_value = resp
    assert OpenAlexProvider().search(query="q", limit=3) == []


@patch("autopapers.providers.openalex_provider.urllib.request.urlopen")
def test_openalex_search_skips_non_dict_work_entries(mock_urlopen: MagicMock) -> None:
    body = {
        "results": [
            None,
            {"id": "https://openalex.org/W9", "title": "Keep"},
        ],
    }
    resp = MagicMock()
    resp.__enter__.return_value.read.return_value = json.dumps(body).encode("utf-8")
    resp.__exit__.return_value = None
    mock_urlopen.return_value = resp
    refs = OpenAlexProvider().search(query="q", limit=5)
    assert len(refs) == 1
    assert refs[0].id == "W9"


def test_openalex_fetch_pdf_requires_url(tmp_path: Path) -> None:
    ref = PaperRef(source="openalex", id="W1", title="t", pdf_url=None)
    with pytest.raises(ValueError, match="No PDF URL"):
        OpenAlexProvider().fetch_pdf(ref=ref, dest_dir=tmp_path)


@patch("autopapers.providers.openalex_provider.urllib.request.urlopen")
def test_openalex_search_parses_results(mock_urlopen: MagicMock) -> None:
    body = {
        "results": [
            {
                "id": "https://openalex.org/W123",
                "title": "Example Paper",
                "primary_location": {"pdf_url": "https://example.org/paper.pdf"},
            }
        ]
    }
    resp = MagicMock()
    resp.__enter__.return_value.read.return_value = json.dumps(body).encode("utf-8")
    resp.__exit__.return_value = None
    mock_urlopen.return_value = resp

    p = OpenAlexProvider()
    refs = p.search(query="test", limit=5)
    assert len(refs) == 1
    assert refs[0].id == "W123"
    assert refs[0].source == "openalex"
    assert refs[0].title == "Example Paper"
    assert refs[0].pdf_url == "https://example.org/paper.pdf"


def test_openalex_short_id_from_url() -> None:
    assert _openalex_short_id("") == ""
    assert _openalex_short_id("https://openalex.org/W123") == "W123"
    assert _openalex_short_id("https://openalex.org/W123/") == "W123"


def test_openalex_pick_pdf_primary_over_best_oa() -> None:
    w = {
        "primary_location": {"pdf_url": "https://primary.pdf"},
        "best_oa_location": {"pdf_url": "https://best.pdf"},
    }
    assert _pick_pdf_url(w) == "https://primary.pdf"


def test_openalex_pick_pdf_content_urls_and_locations() -> None:
    assert (
        _pick_pdf_url({"content_urls": {"pdf_url": "https://cu.pdf"}}) == "https://cu.pdf"
    )
    loc_w = {"locations": [1, {"pdf_url": "https://loc.pdf"}]}
    assert _pick_pdf_url(loc_w) == "https://loc.pdf"


def test_openalex_pick_pdf_open_access_pdf_suffix_only() -> None:
    assert (
        _pick_pdf_url({"open_access": {"oa_url": "https://x.org/a.pdf"}})
        == "https://x.org/a.pdf"
    )
    assert _pick_pdf_url({"open_access": {"oa_url": "https://x.org/html"}}) is None


def test_openalex_pick_pdf_empty() -> None:
    assert _pick_pdf_url({}) is None
