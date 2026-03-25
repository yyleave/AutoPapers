from __future__ import annotations

import json
from pathlib import Path

from autopapers.config import get_paths
from autopapers.phase1.papers.storage import (
    write_fetch_record,
    write_parse_manifest,
    write_search_record,
)
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


def test_write_parse_manifest(tmp_path: Path) -> None:
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF")
    txt = tmp_path / "out.txt"
    txt.write_text("hello\n", encoding="utf-8")
    m = write_parse_manifest(
        pdf_path=pdf,
        txt_path=txt,
        char_count=5,
        pages_total=3,
        pages_read=2,
        max_pages_config=20,
    )
    assert m == tmp_path / "out.manifest.json"
    data = json.loads(m.read_text(encoding="utf-8"))
    assert data["type"] == "parse"
    assert data["char_count"] == 5
    assert data["pages_total"] == 3
