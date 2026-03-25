from __future__ import annotations

import json
from pathlib import Path

from autopapers.config import get_paths
from autopapers.phase2.corpus_input import (
    DEFAULT_SNAPSHOT,
    format_snapshot_for_proposal,
    load_corpus_text_for_proposal,
)


def test_load_corpus_non_json_file_returns_truncated_text(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    plain = tmp_path / "notes.txt"
    plain.write_text("Plain corpus context\n" + "x" * 100, encoding="utf-8")
    text, used = load_corpus_text_for_proposal(paths, plain)
    assert used == plain
    assert text.startswith("Plain corpus context")


def test_explicit_corpus_file(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    f = tmp_path / "x.json"
    f.write_text('{"a": 1}', encoding="utf-8")
    text, used = load_corpus_text_for_proposal(paths, f)
    assert used == f
    assert '"a": 1' in text


def test_default_snapshot_when_present(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    paths.kg_dir.mkdir(parents=True)
    snap = paths.kg_dir / DEFAULT_SNAPSHOT
    snap.write_text('{"nodes":[]}', encoding="utf-8")
    text, used = load_corpus_text_for_proposal(paths, None)
    assert used == snap
    assert "Corpus graph:" in text
    assert "0 nodes" in text


def test_snapshot_includes_text_extract_snippets(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    txt = tmp_path / "ex.txt"
    txt.write_text("Abstract: hello world\n" + "x" * 100, encoding="utf-8")
    snap = {
        "schema_version": "0.1",
        "node_count": 1,
        "edge_count": 0,
        "nodes": [
            {
                "id": "parse:x",
                "type": "TextExtract",
                "output_txt": str(txt.resolve()),
                "label": "ex",
            }
        ],
        "edges": [],
    }
    paths.kg_dir.mkdir(parents=True)
    (paths.kg_dir / DEFAULT_SNAPSHOT).write_text(
        json.dumps(snap), encoding="utf-8"
    )
    text, used = load_corpus_text_for_proposal(paths, None)
    assert used is not None
    assert "Abstract: hello world" in text


def test_format_snapshot_non_list_nodes_uses_json_snippet() -> None:
    out = format_snapshot_for_proposal({"schema_version": "0.1", "nodes": "not-list"})
    assert "0.1" in out
    assert "not-list" in out or '"not-list"' in out


def test_format_snapshot_lists_papers(tmp_path: Path) -> None:
    data = {
        "schema_version": "0.1",
        "nodes": [
            {
                "id": "paper:arxiv:1",
                "type": "Paper",
                "label": "My Title",
                "source": "arxiv",
                "external_id": "1",
            }
        ],
        "edges": [],
    }
    out = format_snapshot_for_proposal(data)
    assert "My Title" in out
    assert "arxiv:1" in out


def test_no_snapshot_returns_empty(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    text, used = load_corpus_text_for_proposal(paths, None)
    assert used is None
    assert text == ""
