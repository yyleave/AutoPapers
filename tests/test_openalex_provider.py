from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from autopapers.providers.openalex_provider import OpenAlexProvider


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
