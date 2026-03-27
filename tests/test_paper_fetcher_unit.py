from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autopapers.providers.base import PaperRef

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


@patch("paper_fetcher.AminerProvider")
@patch("paper_fetcher.AMinerClient")
def test_paper_fetcher_search_delegates_to_provider(
    mock_client: MagicMock,
    mock_prov_cls: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AMINER_API_KEY", raising=False)
    mock_client.return_value = MagicMock()
    mock_inst = MagicMock()
    mock_prov_cls.return_value = mock_inst
    mock_inst.search.return_value = []

    fetcher = _pf().PaperFetcher(aminer_token="tok", download_dir=str(tmp_path / "dl"))
    assert fetcher.search_papers("topic", limit=4) == []
    mock_inst.search.assert_called_once_with(query="topic", limit=4)


@patch("paper_fetcher.AminerProvider")
@patch("paper_fetcher.AMinerClient")
def test_paper_fetch_skip_download_does_not_call_downloader(
    mock_client: MagicMock,
    mock_prov_cls: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AMINER_API_KEY", raising=False)
    mock_client.return_value = MagicMock()
    mock_inst = MagicMock()
    mock_prov_cls.return_value = mock_inst
    mock_inst.search.return_value = [
        PaperRef(source="aminer", id="id1", title="Hello", pdf_url=None),
    ]

    fetcher = _pf().PaperFetcher(aminer_token="tok", download_dir=str(tmp_path / "dl"))
    with patch.object(fetcher, "download_pdf") as mock_dl:
        out = fetcher.fetch("q", limit=1, auto_download=False)
    mock_dl.assert_not_called()
    assert len(out) == 1
    assert out[0].title == "Hello"


@patch("paper_fetcher.AminerProvider")
def test_paper_fetcher_aminer_client_valueerror_leaves_provider_none(
    _mock_prov_cls: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AMINER_API_KEY", raising=False)

    with patch("paper_fetcher.AMinerClient") as mock_client:
        mock_client.side_effect = ValueError("invalid token")
        fetcher = _pf().PaperFetcher(aminer_token="bad", download_dir=str(tmp_path / "dl"))
    assert fetcher.aminer is None
    assert fetcher.search_papers("anything", limit=1) == []


@patch("paper_fetcher.AminerProvider")
@patch("paper_fetcher.AMinerClient")
def test_paper_fetcher_fetch_empty_search_returns_empty_list(
    mock_client: MagicMock,
    mock_prov_cls: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AMINER_API_KEY", raising=False)
    mock_client.return_value = MagicMock()
    mock_inst = MagicMock()
    mock_prov_cls.return_value = mock_inst
    mock_inst.search.return_value = []

    fetcher = _pf().PaperFetcher(aminer_token="tok", download_dir=str(tmp_path / "dl"))
    with patch.object(fetcher, "download_pdf") as mock_dl:
        out = fetcher.fetch("ghost query", limit=5, auto_download=True)
    assert out == []
    mock_dl.assert_not_called()


def _mock_paper(title: str) -> PaperRef:
    return PaperRef(
        source="aminer",
        id="p1",
        title=title,
        pdf_url="https://example.com/x.pdf",
        authors=("Alice",),
        year=2024,
        venue="Venue",
        doi="10.1000/x",
        url="https://example/paper",
    )


@patch("paper_fetcher.AminerProvider")
@patch("paper_fetcher.AMinerClient")
def test_paper_fetch_auto_download_calls_download_per_paper(
    mock_client: MagicMock,
    mock_prov_cls: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.pdf_downloader import DownloadResult

    monkeypatch.delenv("AMINER_API_KEY", raising=False)
    mock_client.return_value = MagicMock()
    mock_inst = MagicMock()
    mock_prov_cls.return_value = mock_inst
    mock_inst.search.return_value = [
        _mock_paper("First title"),
        _mock_paper("Second title"),
    ]

    fetcher = _pf().PaperFetcher(aminer_token="tok", download_dir=str(tmp_path / "dl"))
    ok = DownloadResult(success=True, filepath="/tmp/a.pdf", source="stub")
    with patch.object(fetcher, "download_pdf", return_value=ok) as mock_dl:
        out = fetcher.fetch("q", limit=2, auto_download=True)
    assert len(out) == 2
    assert mock_dl.call_count == 2
    assert mock_dl.call_args_list[0][0][0].title == "First title"
    assert mock_dl.call_args_list[1][0][0].title == "Second title"


@patch("paper_fetcher.AminerProvider")
@patch("paper_fetcher.AMinerClient")
def test_paper_fetch_prints_manual_url_on_failed_download(
    mock_client: MagicMock,
    mock_prov_cls: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from api.pdf_downloader import DownloadResult

    monkeypatch.delenv("AMINER_API_KEY", raising=False)
    mock_client.return_value = MagicMock()
    mock_inst = MagicMock()
    mock_prov_cls.return_value = mock_inst
    mock_inst.search.return_value = [_mock_paper("Only")]

    bad = DownloadResult(
        success=False,
        error="no pdf",
        manual_url="https://example/manual",
    )
    fetcher = _pf().PaperFetcher(aminer_token="tok", download_dir=str(tmp_path / "dl"))
    with patch.object(fetcher, "download_pdf", return_value=bad):
        fetcher.fetch("q", limit=1, auto_download=True)
    captured = capsys.readouterr().out
    assert "✗" in captured
    assert "https://example/manual" in captured
