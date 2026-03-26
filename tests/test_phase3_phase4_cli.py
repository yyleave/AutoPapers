from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autopapers.cli import app
from autopapers.phase2.debate import merge_stub_to_proposal, run_debate_stub


def _confirmed_proposal(path: Path) -> None:
    debate = run_debate_stub(profile_summary="p", corpus_summary="c")
    prop = merge_stub_to_proposal(title="T", debate=debate, status="confirmed")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prop, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_phase3_run_writes_experiment_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    proposal = tmp_path / "data" / "proposals" / "proposal-confirmed.json"
    _confirmed_proposal(proposal)
    r = CliRunner().invoke(app, ["phase3", "run", "--proposal", str(proposal)])
    assert r.exit_code == 0
    out = Path(r.stdout.strip())
    assert out.is_file()
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["status"] == "completed_stub"
    assert doc["proposal_title"] == "T"


def test_phase4_draft_and_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    proposal = tmp_path / "data" / "proposals" / "proposal-confirmed.json"
    _confirmed_proposal(proposal)

    exp = tmp_path / "data" / "experiments" / "experiment-report.json"
    exp.parent.mkdir(parents=True, exist_ok=True)
    exp.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "status": "completed_stub",
                "metrics": {"primary_metric": "tbd", "value": None},
            }
        ),
        encoding="utf-8",
    )

    r1 = CliRunner().invoke(
        app,
        ["phase4", "draft", "--proposal", str(proposal), "--experiment", str(exp)],
    )
    assert r1.exit_code == 0
    md = Path(r1.stdout.strip())
    assert md.is_file()
    assert "# T" in md.read_text(encoding="utf-8")

    r2 = CliRunner().invoke(
        app,
        [
            "phase4",
            "bundle",
            "--proposal",
            str(proposal),
            "--experiment",
            str(exp),
            "--manuscript",
            str(md),
        ],
    )
    assert r2.exit_code == 0
    bundle = Path(r2.stdout.strip())
    assert (bundle / "proposal-confirmed.json").is_file()
    assert (bundle / "experiment-report.json").is_file()
    assert (bundle / "manuscript-draft.md").is_file()
    assert (bundle / "manifest.json").is_file()


def test_run_all_full_flow_includes_phase3_phase4_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    profile = tmp_path / "user.json"
    profile.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "user": {"languages": ["en"]},
                "background": {"domains": [], "skills": [], "constraints": []},
                "hardware": {"device": "other"},
                "research_intent": {
                    "problem_statements": [],
                    "keywords": [],
                    "non_goals": [],
                    "risk_tolerance": "medium",
                },
            }
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(
        app,
        ["run-all", "--profile", str(profile), "--full-flow"],
        env={"AUTOPAPERS_PROVIDER": "local_pdf"},
    )
    assert r.exit_code == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert Path(out["experiment_report"]).is_file()
    assert Path(out["manuscript_draft"]).is_file()
    assert Path(out["submission_bundle"]).is_dir()
    assert Path(out["submission_archive"]).is_file()
