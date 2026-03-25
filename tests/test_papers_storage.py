from __future__ import annotations

import json
from pathlib import Path

from autopapers.config import get_paths
from autopapers.phase1.papers.storage import write_fetch_record, write_search_record
from autopapers.providers.base import PaperRef


def test_write_search_record(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    refs = [
        PaperRef(source="arxiv", id="1234.5678", title="T", pdf_url="https://example/x.pdf")
    ]
    p = write_search_record(paths, provider="arxiv", query="q", refs=refs)
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["type"] == "search"
    assert data["count"] == 1
    assert data["results"][0]["id"] == "1234.5678"


def test_write_fetch_record(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    p = write_fetch_record(
        paths, source="arxiv", paper_id="1", title="t", pdf_path=pdf
    )
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["type"] == "fetch"
