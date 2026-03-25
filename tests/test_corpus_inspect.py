from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autopapers.cli import app
from autopapers.phase1.corpus_inspect import (
    load_corpus_snapshot_document,
    snapshot_edges_to_csv,
    summarize_corpus_snapshot,
)


def test_summarize_counts_by_type_and_relation() -> None:
    data = {
        "schema_version": "0.1",
        "built_at": "2026-01-01",
        "nodes": [
            {"id": "1", "type": "Paper"},
            {"id": "2", "type": "Paper"},
            {"id": "3", "type": "Fetch"},
        ],
        "edges": [
            {"relation": "FETCHED", "source": "a", "target": "b"},
            {"relation": "SEARCH_HIT", "source": "q", "target": "b"},
        ],
    }
    s = summarize_corpus_snapshot(data)
    assert s["node_total"] == 3
    assert s["nodes_by_type"]["Paper"] == 2
    assert s["edges_by_relation"]["FETCHED"] == 1


def test_corpus_info_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    kg = tmp_path / "data" / "kg"
    kg.mkdir(parents=True)
    snap = kg / "corpus-snapshot.json"
    payload = {"schema_version": "0.1", "nodes": [{"type": "Paper"}], "edges": []}
    snap.write_text(json.dumps(payload), encoding="utf-8")

    runner = CliRunner()
    r = runner.invoke(app, ["corpus", "info"])
    assert r.exit_code == 0
    out = json.loads(r.stdout)
    assert out["node_total"] == 1
    assert "Paper" in out["nodes_by_type"]


def test_corpus_info_missing_exits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    r = runner.invoke(app, ["corpus", "info"])
    assert r.exit_code == 1


def test_snapshot_edges_to_csv_rows() -> None:
    data = {"edges": [{"source": "x", "target": "y", "relation": "R"}]}
    csv = snapshot_edges_to_csv(data)
    lines = csv.strip().split("\n")
    assert lines[0] == "source,target,relation"
    assert lines[1] == "x,y,R"


def test_load_corpus_snapshot_document(tmp_path: Path) -> None:
    p = tmp_path / "x.json"
    p.write_text('{"a": 1}', encoding="utf-8")
    assert load_corpus_snapshot_document(p)["a"] == 1


def test_load_corpus_snapshot_not_object(tmp_path: Path) -> None:
    p = tmp_path / "x.json"
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(TypeError):
        load_corpus_snapshot_document(p)


def test_corpus_export_edges_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    kg = tmp_path / "data" / "kg"
    kg.mkdir(parents=True)
    snap = kg / "corpus-snapshot.json"
    snap.write_text(
        json.dumps(
            {"edges": [{"source": "a", "target": "b", "relation": "FETCHED"}]}
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(app, ["corpus", "export-edges"])
    assert r.exit_code == 0
    assert "FETCHED" in r.stdout


def test_corpus_export_edges_writes_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    kg = tmp_path / "data" / "kg"
    kg.mkdir(parents=True)
    snap = kg / "corpus-snapshot.json"
    snap.write_text(json.dumps({"edges": []}), encoding="utf-8")
    out = tmp_path / "e.csv"
    r = CliRunner().invoke(
        app,
        ["corpus", "export-edges", "-o", str(out)],
    )
    assert r.exit_code == 0
    assert out.is_file()
    assert "source,target,relation" in out.read_text(encoding="utf-8")
