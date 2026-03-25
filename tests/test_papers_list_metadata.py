from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autopapers.cli import app


def test_list_metadata_limit_zero_returns_no_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    meta = tmp_path / "data" / "papers" / "metadata"
    meta.mkdir(parents=True)
    (meta / "a.json").write_text("{}", encoding="utf-8")
    r = CliRunner().invoke(app, ["papers", "list-metadata", "--limit", "0"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert data["files"] == []


def test_list_metadata_missing_dir_returns_empty_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["papers", "list-metadata"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert data["files"] == []


def test_list_metadata_lists_json_newest_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    meta = tmp_path / "data" / "papers" / "metadata"
    meta.mkdir(parents=True)
    (meta / "older.json").write_text("{}", encoding="utf-8")
    newer = meta / "newer.json"
    newer.write_text("{}", encoding="utf-8")
    o = (meta / "older.json").stat().st_mtime
    os.utime(newer, (o + 100, o + 100))

    runner = CliRunner()
    r = runner.invoke(app, ["papers", "list-metadata", "--limit", "10"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    names = [x["name"] for x in data["files"]]
    assert names[0] == "newer.json"
