from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from autopapers.config import get_paths
from autopapers.phase1.papers.metadata_pick import newest_papers_metadata


def test_newest_papers_metadata_respects_kind(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    meta = paths.papers_metadata_dir
    meta.mkdir(parents=True)
    t0 = time.time()
    a = meta / "search-a.json"
    b = meta / "search-b.json"
    fx = meta / "fetch-x.json"
    a.write_text("{}", encoding="utf-8")
    b.write_text("{}", encoding="utf-8")
    fx.write_text("{}", encoding="utf-8")
    os.utime(a, (t0, t0))
    os.utime(fx, (t0 + 1, t0 + 1))
    os.utime(b, (t0 + 2, t0 + 2))

    assert newest_papers_metadata(paths, kind="search") == b
    assert newest_papers_metadata(paths, kind="fetch") == fx
    assert newest_papers_metadata(paths, kind="any") == b


def test_newest_papers_metadata_empty_dir(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    paths.papers_metadata_dir.mkdir(parents=True)
    assert newest_papers_metadata(paths, kind="any") is None


def test_newest_papers_metadata_missing_dir(tmp_path: Path) -> None:
    paths = get_paths(repo_root=tmp_path)
    # data/ may exist but papers/metadata not created
    paths.data_dir.mkdir(parents=True)
    assert not paths.papers_metadata_dir.is_dir()
    assert newest_papers_metadata(paths, kind="any") is None


def test_show_metadata_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from autopapers.cli import app

    monkeypatch.chdir(tmp_path)
    meta = tmp_path / "data" / "papers" / "metadata"
    meta.mkdir(parents=True)
    (meta / "search-z.json").write_text(
        json.dumps({"type": "search", "query": "q"}),
        encoding="utf-8",
    )

    runner = CliRunner()
    r = runner.invoke(app, ["papers", "show-metadata", "--latest", "search"])
    assert r.exit_code == 0
    out = json.loads(r.stdout)
    assert out["data"]["query"] == "q"
