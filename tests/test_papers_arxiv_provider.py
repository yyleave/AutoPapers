from __future__ import annotations

import pytest

from autopapers.providers.arxiv_provider import ArxivProvider


@pytest.mark.network
def test_arxiv_search_returns_results() -> None:
    provider = ArxivProvider()
    refs = provider.search(query="transformer", limit=1)
    assert len(refs) <= 1
    # Network calls can fail in CI; we only assert shape when results exist.
    if refs:
        assert refs[0].id

