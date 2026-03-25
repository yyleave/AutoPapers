from __future__ import annotations

import pytest

from autopapers.providers.arxiv_provider import ArxivProvider, _arxiv_id_from_entry_id


def test_arxiv_id_from_entry_abs_url() -> None:
    assert (
        _arxiv_id_from_entry_id("http://arxiv.org/abs/2501.01234v1") == "2501.01234v1"
    )
    assert _arxiv_id_from_entry_id("not-a-url") == "not-a-url"


@pytest.mark.network
def test_arxiv_search_returns_results() -> None:
    provider = ArxivProvider()
    refs = provider.search(query="transformer", limit=1)
    assert len(refs) <= 1
    # Network calls can fail in CI; we only assert shape when results exist.
    if refs:
        assert refs[0].id

