from __future__ import annotations

import dataclasses

import pytest

from autopapers.providers.base import PaperRef


def test_paper_ref_frozen() -> None:
    r = PaperRef(source="s", id="i", title="t")
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.title = "other"  # type: ignore[misc]


def test_paper_ref_optional_fields_default_none() -> None:
    r = PaperRef(source="arxiv", id="2501.0001")
    assert r.title is None
    assert r.pdf_url is None
    assert r.authors is None
    assert r.year is None
    assert r.doi is None
    assert r.venue is None
    assert r.url is None
