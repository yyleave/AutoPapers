from __future__ import annotations

import json
from pathlib import Path

from autopapers.config import get_paths
from autopapers.phase1.corpus_snapshot import build_corpus_snapshot, write_corpus_snapshot


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


def test_write_snapshot(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    snap = {"schema_version": "0.1", "nodes": [], "edges": [], "node_count": 0, "edge_count": 0}
    p = write_corpus_snapshot(paths, snap)
    assert p.name == "corpus-snapshot.json"
    assert p.parent.name == "kg"
