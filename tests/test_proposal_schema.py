from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autopapers.cli import app
from autopapers.phase1.profile.validate import load_schema, validate_profile
from autopapers.phase2.debate import merge_stub_to_proposal, run_debate_stub


def proposal_schema_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "autopapers"
        / "schemas"
        / "research_proposal.schema.json"
    )


def test_proposal_merged_stub_validates() -> None:
    schema = load_schema(proposal_schema_path())
    debate = run_debate_stub(profile_summary="p", corpus_summary="c")
    prop = merge_stub_to_proposal(title="T", debate=debate)
    validate_profile(profile=prop, schema=schema)


def test_proposal_validate_cli_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    debate = run_debate_stub(profile_summary="p", corpus_summary="c")
    prop = merge_stub_to_proposal(title="T", debate=debate)
    f = tmp_path / "proposal.json"
    f.write_text(json.dumps(prop), encoding="utf-8")
    r = CliRunner().invoke(app, ["proposal", "validate", "-i", str(f)])
    assert r.exit_code == 0
    out = json.loads(r.stdout)
    assert out["ok"] is True
    assert out["title"] == "T"


def test_proposal_validate_cli_rejects_empty_doc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    f = tmp_path / "empty-proposal.json"
    f.write_text("{}", encoding="utf-8")
    r = CliRunner().invoke(app, ["proposal", "validate", "-i", str(f)])
    assert r.exit_code == 1
    err = json.loads(r.stderr.strip())
    assert err["ok"] is False
    assert err["error"] == "validation"


def test_proposal_validate_cli_bad_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    f = tmp_path / "broken.json"
    f.write_text("{", encoding="utf-8")
    r = CliRunner().invoke(app, ["proposal", "validate", "-i", str(f)])
    assert r.exit_code == 1
    err = json.loads(r.stderr.strip())
    assert err["ok"] is False
    assert err["error"] == "invalid_json"
    assert "detail" in err
