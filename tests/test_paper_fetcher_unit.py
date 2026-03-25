from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO = Path(__file__).resolve().parents[1]
_SRC = str(REPO / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


def _pf():
    import paper_fetcher as pf

    return pf


def test_paper_fetcher_without_token_search_returns_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AMINER_API_KEY", raising=False)
    fetcher = _pf().PaperFetcher(aminer_token=None, download_dir=str(tmp_path / "dl"))
    assert fetcher.aminer is None
    assert fetcher.search_papers("q", limit=2) == []


@patch("paper_fetcher.AMinerClient")
def test_paper_fetcher_search_delegates_to_aminer(
    mock_client: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AMINER_API_KEY", raising=False)
    mock_inst = MagicMock()
    mock_client.return_value = mock_inst
    mock_inst.search_by_title.return_value = []

    fetcher = _pf().PaperFetcher(aminer_token="tok", download_dir=str(tmp_path / "dl"))
    assert fetcher.search_papers("topic", limit=4) == []
    mock_inst.search_by_title.assert_called_once_with("topic", limit=4)


@patch("paper_fetcher.AMinerClient")
def test_paper_fetch_skip_download_does_not_call_downloader(
    mock_client: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AMINER_API_KEY", raising=False)
    mock_inst = MagicMock()
    mock_client.return_value = mock_inst
    paper = MagicMock()
    paper.title = "Hello"
    paper.authors = []
    paper.year = None
    paper.venue = None
    paper.doi = None
    paper.url = None
    mock_inst.search_by_title.return_value = [paper]

    fetcher = _pf().PaperFetcher(aminer_token="tok", download_dir=str(tmp_path / "dl"))
    with patch.object(fetcher, "download_pdf") as mock_dl:
        out = fetcher.fetch("q", limit=1, auto_download=False)
    mock_dl.assert_not_called()
    assert len(out) == 1
    assert out[0].title == "Hello"


@patch("paper_fetcher.AMinerClient")
def test_paper_fetcher_aminer_client_valueerror_leaves_client_none(
    mock_client: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AMINER_API_KEY", raising=False)
    mock_client.side_effect = ValueError("invalid token")

    fetcher = _pf().PaperFetcher(aminer_token="bad", download_dir=str(tmp_path / "dl"))
    assert fetcher.aminer is None
    assert fetcher.search_papers("anything", limit=1) == []


@patch("paper_fetcher.AMinerClient")
def test_paper_fetcher_fetch_empty_search_returns_empty_list(
    mock_client: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AMINER_API_KEY", raising=False)
    mock_inst = MagicMock()
    mock_client.return_value = mock_inst
    mock_inst.search_by_title.return_value = []

    fetcher = _pf().PaperFetcher(aminer_token="tok", download_dir=str(tmp_path / "dl"))
    with patch.object(fetcher, "download_pdf") as mock_dl:
        out = fetcher.fetch("ghost query", limit=5, auto_download=True)
    assert out == []
    mock_dl.assert_not_called()
