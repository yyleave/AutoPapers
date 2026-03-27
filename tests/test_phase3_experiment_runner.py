from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autopapers.cli import _write_phase3_evaluator_script, app


def _write_minimal_confirmed_proposal(path: Path) -> None:
    doc = {
        "schema_version": "0.1",
        "title": "X",
        "problem": "We study transformer attention.",
        "hypothesis": "Attention helps.",
        "risks": ["risk"],
        "status": "confirmed",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_write_phase3_evaluator_script_writes_runnable_stub(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    proposal = tmp_path / "data" / "proposals" / "proposal-confirmed.json"
    _write_minimal_confirmed_proposal(proposal)
    custom = tmp_path / "data" / "runs" / "phase3" / "my-eval.py"
    out = _write_phase3_evaluator_script(proposal=proposal, output=custom)
    assert out.resolve() == custom.resolve()
    body = out.read_text(encoding="utf-8")
    assert "coverage" in body
    assert "tokenize" in body


def test_phase3_run_uses_experiment_py_when_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    # Minimal corpus snapshot with a TextExtract file.
    paths = tmp_path / "data"
    (paths / "kg").mkdir(parents=True, exist_ok=True)
    (paths / "runs" / "phase3").mkdir(parents=True, exist_ok=True)
    parsed_txt = paths / "papers" / "parsed" / "t.txt"
    parsed_txt.parent.mkdir(parents=True, exist_ok=True)
    parsed_txt.write_text("transformer attention helps", encoding="utf-8")
    snap = {
        "schema_version": "0.1",
        "built_at": "x",
        "node_count": 1,
        "edge_count": 0,
        "nodes": [{"id": "t", "type": "TextExtract", "label": "t", "output_txt": str(parsed_txt)}],
        "edges": [],
    }
    (paths / "kg" / "corpus-snapshot.json").write_text(
        json.dumps(snap, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    proposal = paths / "proposals" / "proposal-confirmed.json"
    _write_minimal_confirmed_proposal(proposal)

    # Generate experiment runner.
    gen = CliRunner().invoke(app, ["proposal", "generate-experiment", "--proposal", str(proposal)])
    assert gen.exit_code == 0

    run = CliRunner().invoke(
        app,
        ["phase3", "run", "--proposal", str(proposal), "--runner", "local"],
    )
    assert run.exit_code == 0, run.stdout + run.stderr
    out = Path(run.stdout.strip())
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["status"] in {"executed", "failed"}
    assert "artifacts" in rep
    if rep["status"] == "executed":
        art = Path(rep["artifacts"]["dir"])
        assert (art / "metrics.json").is_file()

