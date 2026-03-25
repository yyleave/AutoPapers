from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autopapers.cli import app
from autopapers.phase1.corpus_inspect import (
    load_corpus_snapshot_document,
    snapshot_edges_to_csv,
    snapshot_nodes_to_csv,
    summarize_corpus_snapshot,
)


def test_summarize_treats_non_list_nodes_edges_as_empty() -> None:
    s = summarize_corpus_snapshot({"nodes": "not-a-list", "edges": 42})
    assert s["node_total"] == 0
    assert s["edge_total"] == 0
    assert s["nodes_by_type"] == {}
    assert s["edges_by_relation"] == {}


def test_snapshot_nodes_csv_serializes_object_label_as_json() -> None:
    data = {
        "nodes": [{"id": "n1", "type": "Paper", "label": {"en": "Title", "n": 1}}],
    }
    csv = snapshot_nodes_to_csv(data)
    assert "n1" in csv
    assert "Paper" in csv
    assert "en" in csv and "Title" in csv


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


def test_corpus_info_custom_snapshot_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    custom = tmp_path / "other-snapshot.json"
    custom.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "nodes": [{"id": "f1", "type": "Fetch", "label": "x"}],
                "edges": [],
            },
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(app, ["corpus", "info", "--snapshot", str(custom)])
    assert r.exit_code == 0
    out = json.loads(r.stdout)
    assert out["node_total"] == 1
    assert out["nodes_by_type"].get("Fetch") == 1
    assert out["snapshot"] == str(custom.resolve())


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


def test_corpus_build_dry_run_skips_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    r = runner.invoke(app, ["corpus", "build", "--dry-run"])
    assert r.exit_code == 0
    out = json.loads(r.stdout)
    assert out["dry_run"] is True
    assert "would_write" in out
    assert "node_total" in out
    snap = tmp_path / "data" / "kg" / "corpus-snapshot.json"
    assert not snap.is_file()


def test_corpus_build_writes_snapshot_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    meta = tmp_path / "data" / "papers" / "metadata"
    meta.mkdir(parents=True)
    (meta / "search-one.json").write_text(
        json.dumps(
            {
                "type": "search",
                "created_at": "2026-01-01T00:00:00Z",
                "provider": "arxiv",
                "query": "q",
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
    r = CliRunner().invoke(app, ["corpus", "build"])
    assert r.exit_code == 0
    snap = tmp_path / "data" / "kg" / "corpus-snapshot.json"
    assert snap.is_file()
    assert r.stdout.strip() == str(snap.resolve())
    data = json.loads(snap.read_text(encoding="utf-8"))
    assert data["node_count"] >= 2


def test_corpus_build_with_profile_adds_user_and_keywords(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    meta = tmp_path / "data" / "papers" / "metadata"
    meta.mkdir(parents=True)
    (meta / "search-empty.json").write_text(
        json.dumps(
            {
                "type": "search",
                "created_at": "2026-01-01T00:00:00Z",
                "provider": "arxiv",
                "query": "q",
                "results": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    prof = tmp_path / "prof.json"
    prof.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "user": {"display_name": "Carol"},
                "research_intent": {"keywords": ["topic-a"]},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(app, ["corpus", "build", "--profile", str(prof)])
    assert r.exit_code == 0
    snap = json.loads(
        (tmp_path / "data" / "kg" / "corpus-snapshot.json").read_text(encoding="utf-8")
    )
    types = {n["type"] for n in snap["nodes"]}
    assert "User" in types
    assert "Keyword" in types
    assert any(
        n.get("type") == "User" and n.get("label") == "Carol" for n in snap["nodes"]
    )


def test_corpus_info_snapshot_array_not_object_exits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    kg = tmp_path / "data" / "kg"
    kg.mkdir(parents=True)
    (kg / "corpus-snapshot.json").write_text("[]", encoding="utf-8")
    r = CliRunner().invoke(app, ["corpus", "info"])
    assert r.exit_code == 1
    err = json.loads(r.stderr.strip())
    assert err["error"] == "expected_object"


def test_corpus_info_invalid_snapshot_json_exits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    kg = tmp_path / "data" / "kg"
    kg.mkdir(parents=True)
    (kg / "corpus-snapshot.json").write_text("{", encoding="utf-8")
    r = CliRunner().invoke(app, ["corpus", "info"])
    assert r.exit_code == 1
    err = json.loads(r.stderr.strip())
    assert err["error"] == "invalid_json"


def test_corpus_info_missing_exits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    r = runner.invoke(app, ["corpus", "info"])
    assert r.exit_code == 1


def test_snapshot_nodes_to_csv_rows() -> None:
    data = {
        "nodes": [
            {"id": "n1", "type": "Paper", "label": "Title"},
            {"id": "n2", "type": "Fetch", "label": None},
        ]
    }
    csv = snapshot_nodes_to_csv(data)
    lines = csv.strip().split("\n")
    assert lines[0] == "id,type,label"
    assert "n1,Paper,Title" in lines


def test_snapshot_nodes_to_csv_type_filter() -> None:
    data = {
        "nodes": [
            {"id": "a", "type": "Paper", "label": "X"},
            {"id": "b", "type": "User", "label": "u"},
        ]
    }
    csv = snapshot_nodes_to_csv(data, type_filter="Paper")
    lines = csv.strip().split("\n")
    assert len(lines) == 2
    assert "Paper" in lines[1]
    assert "User" not in csv


def test_snapshot_edges_to_csv_rows() -> None:
    data = {"edges": [{"source": "x", "target": "y", "relation": "R"}]}
    csv = snapshot_edges_to_csv(data)
    lines = csv.strip().split("\n")
    assert lines[0] == "source,target,relation"
    assert lines[1] == "x,y,R"


def test_snapshot_edges_to_csv_relation_filter() -> None:
    data = {
        "edges": [
            {"relation": "FETCHED", "source": "x", "target": "y"},
            {"relation": "SEARCH_HIT", "source": "q", "target": "y"},
        ]
    }
    csv = snapshot_edges_to_csv(data, relation_filter="FETCHED")
    lines = csv.strip().split("\n")
    assert len(lines) == 2
    assert "FETCHED" in lines[1]
    assert "SEARCH_HIT" not in lines[1]


def test_load_corpus_snapshot_document(tmp_path: Path) -> None:
    p = tmp_path / "x.json"
    p.write_text('{"a": 1}', encoding="utf-8")
    assert load_corpus_snapshot_document(p)["a"] == 1


def test_load_corpus_snapshot_not_object(tmp_path: Path) -> None:
    p = tmp_path / "x.json"
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(TypeError):
        load_corpus_snapshot_document(p)


def test_load_corpus_snapshot_invalid_json_raises(tmp_path: Path) -> None:
    p = tmp_path / "broken.json"
    p.write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_corpus_snapshot_document(p)


def test_corpus_export_edges_missing_default_snapshot_exits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["corpus", "export-edges"])
    assert r.exit_code == 1
    err = json.loads(r.stderr.strip())
    assert err["error"] == "snapshot_not_found"


def test_corpus_export_nodes_invalid_snapshot_json_exits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    kg = tmp_path / "data" / "kg"
    kg.mkdir(parents=True)
    snap = kg / "corpus-snapshot.json"
    snap.write_text("{", encoding="utf-8")
    r = CliRunner().invoke(app, ["corpus", "export-nodes"])
    assert r.exit_code == 1
    err = json.loads(r.stderr.strip())
    assert err["error"] == "invalid_json"


def test_corpus_export_edges_snapshot_not_object_exits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    kg = tmp_path / "data" / "kg"
    kg.mkdir(parents=True)
    snap = kg / "corpus-snapshot.json"
    snap.write_text("[]", encoding="utf-8")
    r = CliRunner().invoke(app, ["corpus", "export-edges"])
    assert r.exit_code == 1
    err = json.loads(r.stderr.strip())
    assert err["error"] == "expected_object"


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


def test_corpus_export_edges_relation_filter_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    kg = tmp_path / "data" / "kg"
    kg.mkdir(parents=True)
    snap = kg / "corpus-s.json"
    snap.write_text(
        json.dumps(
            {
                "edges": [
                    {"source": "a", "target": "b", "relation": "FETCHED"},
                    {"source": "q", "target": "b", "relation": "SEARCH_HIT"},
                ]
            }
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(
        app,
        ["corpus", "export-edges", "-s", str(snap), "-r", "SEARCH_HIT"],
    )
    assert r.exit_code == 0
    rows = [ln for ln in r.stdout.strip().split("\n") if ln]
    assert len(rows) == 2
    assert rows[1] == "q,b,SEARCH_HIT"


def test_corpus_export_nodes_type_filter_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    kg = tmp_path / "data" / "kg"
    kg.mkdir(parents=True)
    snap = kg / "corpus-snapshot.json"
    snap.write_text(
        json.dumps(
            {
                "nodes": [
                    {"id": "x", "type": "Paper", "label": "L"},
                    {"id": "y", "type": "Fetch", "label": "f"},
                ]
            }
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(
        app,
        ["corpus", "export-nodes", "-t", "Paper"],
    )
    assert r.exit_code == 0
    assert "Paper" in r.stdout
    assert "Fetch" not in r.stdout


def test_corpus_export_nodes_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    kg = tmp_path / "data" / "kg"
    kg.mkdir(parents=True)
    snap = kg / "corpus-snapshot.json"
    snap.write_text(
        json.dumps({"nodes": [{"id": "x", "type": "Paper", "label": "L"}]}),
        encoding="utf-8",
    )
    r = CliRunner().invoke(app, ["corpus", "export-nodes"])
    assert r.exit_code == 0
    assert "Paper" in r.stdout


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
