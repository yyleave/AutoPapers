from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from autopapers.providers.aminer_provider import AminerProvider
from autopapers.repo_paths import ensure_legacy_api_on_path


@patch("api.aminer_client.AMinerClient")
def test_aminer_client_receives_explicit_api_token(mock_cls: MagicMock) -> None:
    inst = mock_cls.return_value
    inst.paper_search.return_value = []
    AminerProvider(api_token="explicit-tok").search(query="x", limit=1)
    mock_cls.assert_called_once_with("explicit-tok")


@patch("api.aminer_client.AMinerClient")
def test_aminer_search_empty_returns_no_refs(mock_cls: MagicMock) -> None:
    inst = mock_cls.return_value
    inst.paper_search.return_value = []
    refs = AminerProvider().search(query="quantum", limit=3)
    assert refs == []
    inst.paper_search.assert_called_once_with("quantum", page=0, size=3)
    inst.paper_info.assert_not_called()


@patch("api.aminer_client.AMinerClient")
def test_aminer_search_merges_paper_info(mock_cls: MagicMock) -> None:
    ensure_legacy_api_on_path()
    from api.aminer_client import Paper

    brief = Paper(
        id="aminer-1",
        title="Brief",
        authors=["A"],
        pdf_url=None,
        url="https://example.org/p/1",
    )
    detailed = Paper(
        id="aminer-1",
        title="Detailed title",
        authors=["A", "B"],
        pdf_url="https://example.org/1.pdf",
        url="https://example.org/p/1",
    )
    inst = mock_cls.return_value
    inst.paper_search.return_value = [brief]
    inst.paper_info.return_value = [detailed]

    refs = AminerProvider().search(query="ml", limit=5)
    assert len(refs) == 1
    r0 = refs[0]
    assert r0.source == "aminer"
    assert r0.id == "aminer-1"
    assert r0.title == "Detailed title"
    assert r0.pdf_url == "https://example.org/1.pdf"
    inst.paper_info.assert_called_once_with(["aminer-1"])


@pytest.mark.network
def test_aminer_search_network_smoke() -> None:
    if os.environ.get("AUTOPAPERS_NETWORK_SMOKE", "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }:
        pytest.skip("Set AUTOPAPERS_NETWORK_SMOKE=1 to run provider network smoke tests")
    if not os.environ.get("AMINER_API_KEY"):
        pytest.skip("Set AMINER_API_KEY to run AMiner network smoke tests")
    refs = AminerProvider().search(query="transformer", limit=1)
    assert isinstance(refs, list)
