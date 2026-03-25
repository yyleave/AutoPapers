from __future__ import annotations

from pathlib import Path

from autopapers.config import get_paths
from autopapers.phase2.corpus_input import DEFAULT_SNAPSHOT, load_corpus_text_for_proposal


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
    assert "nodes" in text


def test_no_snapshot_returns_empty(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    text, used = load_corpus_text_for_proposal(paths, None)
    assert used is None
    assert text == ""
