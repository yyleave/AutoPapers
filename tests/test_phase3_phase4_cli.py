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
    assert doc["status"] in {"planned", "executed"}
    assert doc["proposal_title"] == "T"


def test_phase3_evaluate_writes_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    report = tmp_path / "data" / "experiments" / "experiment-report.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps({"status": "planned", "proposal_title": "E", "experiment_plan": {"steps": []}}),
        encoding="utf-8",
    )
    r = CliRunner().invoke(app, ["phase3", "evaluate", "--report", str(report)])
    assert r.exit_code == 0
    out = Path(r.stdout.strip())
    assert out.is_file()
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["status"] == "evaluated"
    assert doc["proposal_title"] == "E"


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
                "schema_version": "0.2",
                "status": "planned",
                "experiment_plan": {
                    "steps": [{"name": "S", "detail": "D"}],
                },
                "metrics": {"primary_metric": "to_be_defined", "value": None},
                "artifacts": {
                    "dir": str((tmp_path / "my-artifacts").resolve()),
                },
            }
        ),
        encoding="utf-8",
    )
    art_dir = tmp_path / "my-artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)
    (art_dir / "metrics.json").write_text("{}", encoding="utf-8")
    kg = tmp_path / "data" / "kg"
    kg.mkdir(parents=True, exist_ok=True)
    (kg / "corpus-snapshot.json").write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "nodes": [
                    {
                        "id": "paper:test:1",
                        "type": "Paper",
                        "label": "Corpus Paper",
                        "source": "test",
                        "external_id": "1",
                    }
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )
    eva = tmp_path / "data" / "experiments" / "evaluation-summary.json"
    eva.write_text(json.dumps({"status": "evaluated", "proposal_title": "T"}), encoding="utf-8")

    r1 = CliRunner().invoke(
        app,
        ["phase4", "draft", "--proposal", str(proposal), "--experiment", str(exp)],
    )
    assert r1.exit_code == 0
    md = Path(r1.stdout.strip())
    assert md.is_file()
    md_text = md.read_text(encoding="utf-8")
    assert "# T" in md_text
    assert "## Traceability" in md_text
    md.with_suffix(".pdf").write_bytes(b"%PDF-1.4\n%mock\n")

    r2 = CliRunner().invoke(
        app,
        [
            "phase4",
            "bundle",
            "--proposal",
            str(proposal),
            "--experiment",
            str(exp),
            "--evaluation",
            str(eva),
            "--manuscript",
            str(md),
            "--include-artifacts",
            "--include-pdf",
            "--include-bib",
        ],
    )
    assert r2.exit_code == 0
    bundle = Path(r2.stdout.strip())
    assert (bundle / "proposal-confirmed.json").is_file()
    assert (bundle / "experiment-report.json").is_file()
    assert (bundle / "evaluation-summary.json").is_file()
    assert (bundle / "manuscript-draft.md").is_file()
    assert (bundle / "manuscript-draft.pdf").is_file()
    assert (bundle / "manifest.json").is_file()
    man = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert man.get("schema_version") == "0.2"
    assert man.get("autopapers_version")
    assert isinstance(man.get("generated_at"), str) and man["generated_at"].endswith("Z")
    assert man.get("optional_present") == [
        "artifacts/phase3",
        "manuscript-draft.pdf",
        "references.bib",
    ]
    assert (bundle / "artifacts" / "phase3" / "metrics.json").is_file()
    assert (bundle / "references.bib").is_file()
    assert "Corpus Paper" in (bundle / "references.bib").read_text(encoding="utf-8")


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
    exp_doc = json.loads(Path(out["experiment_report"]).read_text(encoding="utf-8"))
    assert exp_doc.get("execution", {}).get("mode") == "local_experiment_py"
    assert Path(out["evaluation_summary"]).is_file()
    assert Path(out["manuscript_draft"]).is_file()
    assert Path(out["submission_bundle"]).is_dir()
    assert Path(out["submission_archive"]).is_file()
