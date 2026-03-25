from __future__ import annotations

import json
from pathlib import Path

from autopapers.config import get_paths
from autopapers.phase1.corpus_snapshot import build_corpus_snapshot, write_corpus_snapshot


def test_build_corpus_skips_invalid_metadata_json(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    paths.papers_metadata_dir.mkdir(parents=True)
    (paths.papers_metadata_dir / "broken.json").write_text("{", encoding="utf-8")
    (paths.papers_metadata_dir / "search-ok.json").write_text(
        json.dumps(
            {
                "type": "search",
                "created_at": "2026-01-01T00:00:00Z",
                "provider": "arxiv",
                "query": "x",
                "results": [
                    {
                        "source": "arxiv",
                        "id": "1",
                        "title": "T",
                        "pdf_url": None,
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    snap = build_corpus_snapshot(paths)
    assert snap["node_count"] >= 2


def test_build_corpus_includes_profile_user_and_keywords(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    paths.papers_metadata_dir.mkdir(parents=True)
    prof = tmp_path / "user.json"
    prof.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "user": {"display_name": "Alice"},
                "research_intent": {
                    "keywords": ["  gnn  ", "", 99, "rl"],
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    snap = build_corpus_snapshot(paths, profile_path=prof)
    types = {n["type"] for n in snap["nodes"]}
    assert "User" in types
    assert "Keyword" in types
    labels = {n["label"] for n in snap["nodes"] if n["type"] == "Keyword"}
    assert "gnn" in labels
    assert "rl" in labels
    assert any(n.get("type") == "User" and n.get("label") == "Alice" for n in snap["nodes"])


def test_build_corpus_from_search_metadata(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    paths.papers_metadata_dir.mkdir(parents=True)
    (paths.papers_metadata_dir / "search-test.json").write_text(
        json.dumps(
            {
                "type": "search",
                "created_at": "2026-01-01T00:00:00Z",
                "provider": "arxiv",
                "query": "transformer",
                "results": [
                    {
                        "source": "arxiv",
                        "id": "1706.03762",
                        "title": "Attention",
                        "pdf_url": "https://arxiv.org/pdf/1706.03762.pdf",
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    snap = build_corpus_snapshot(paths)
    assert snap["node_count"] >= 2  # query + paper
    types = {n["type"] for n in snap["nodes"]}
    assert "Paper" in types
    assert "SearchQuery" in types


def test_corpus_includes_parse_manifest_linked_to_fetch(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    paths.papers_metadata_dir.mkdir(parents=True)
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF")
    (paths.papers_metadata_dir / "fetch-test.json").write_text(
        json.dumps(
            {
                "type": "fetch",
                "created_at": "2026-01-01T00:00:00Z",
                "source": "arxiv",
                "id": "1234.5678",
                "title": "T",
                "pdf_path": str(pdf),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    paths.papers_parsed_dir.mkdir(parents=True)
    txt = paths.papers_parsed_dir / "doc.txt"
    txt.write_text("hi", encoding="utf-8")
    (paths.papers_parsed_dir / "doc.manifest.json").write_text(
        json.dumps(
            {
                "type": "parse",
                "created_at": "2026-01-02T00:00:00Z",
                "input_pdf": str(pdf.resolve()),
                "output_txt": str(txt.resolve()),
                "char_count": 2,
                "pages_total": 1,
                "pages_read": 1,
                "max_pages": 20,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    snap = build_corpus_snapshot(paths)
    types = {n["type"] for n in snap["nodes"]}
    assert "TextExtract" in types
    assert "Paper" in types
    assert any(e["relation"] == "EXTRACTED_FROM" for e in snap["edges"])


def test_write_snapshot(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    snap = {"schema_version": "0.1", "nodes": [], "edges": [], "node_count": 0, "edge_count": 0}
    p = write_corpus_snapshot(paths, snap)
    assert p.name == "corpus-snapshot.json"
    assert p.parent.name == "kg"
