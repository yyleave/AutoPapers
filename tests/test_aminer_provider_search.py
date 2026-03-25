from __future__ import annotations

from unittest.mock import MagicMock, patch

from autopapers.providers.aminer_provider import AminerProvider
from autopapers.repo_paths import ensure_legacy_api_on_path


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
