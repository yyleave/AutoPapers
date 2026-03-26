from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autopapers.cli import app
from autopapers.phase2.debate import merge_stub_to_proposal, run_debate_stub


def _confirmed(path: Path) -> None:
    debate = run_debate_stub(profile_summary="p", corpus_summary="c")
    prop = merge_stub_to_proposal(title="P5", debate=debate, status="confirmed")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prop, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_phase5_run_writes_all_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    proposal = tmp_path / "data" / "proposals" / "proposal-confirmed.json"
    _confirmed(proposal)
    r = CliRunner().invoke(app, ["phase5", "run", "--proposal", str(proposal)])
    assert r.exit_code == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] is True
    assert Path(out["experiment_report"]).is_file()
    assert Path(out["manuscript_draft"]).is_file()
    bundle = Path(out["submission_bundle"])
    assert bundle.is_dir()
    assert (bundle / "manifest.json").is_file()
    assert out["status"]["data"]["submission_bundle_exists"] is True


def test_phase5_run_rejects_non_confirmed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    debate = run_debate_stub(profile_summary="p", corpus_summary="c")
    draft = merge_stub_to_proposal(title="Draft", debate=debate, status="draft")
    proposal = tmp_path / "proposal-draft.json"
    proposal.write_text(json.dumps(draft), encoding="utf-8")
    r = CliRunner().invoke(app, ["phase5", "run", "--proposal", str(proposal)])
    assert r.exit_code == 1
    err = json.loads(r.stderr.strip())
    assert err["error"] == "invalid_status"
