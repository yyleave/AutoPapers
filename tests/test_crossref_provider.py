from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from autopapers.providers.crossref_provider import CrossrefProvider


@patch("autopapers.providers.crossref_provider.urllib.request.urlopen")
def test_crossref_search_parses_results(mock_urlopen: MagicMock) -> None:
    body = {
        "message": {
            "items": [
                {
                    "DOI": "10.1234/example",
                    "title": ["Crossref Title"],
                    "link": [
                        {
                            "URL": "https://example.org/full.pdf",
                            "content-type": "application/pdf",
                        }
                    ],
                }
            ]
        }
    }
    resp = MagicMock()
    resp.__enter__.return_value.read.return_value = json.dumps(body).encode("utf-8")
    resp.__exit__.return_value = None
    mock_urlopen.return_value = resp

    p = CrossrefProvider()
    refs = p.search(query="test", limit=5)
    assert len(refs) == 1
    assert refs[0].id == "10.1234/example"
    assert refs[0].source == "crossref"
    assert refs[0].title == "Crossref Title"
    assert refs[0].pdf_url == "https://example.org/full.pdf"
