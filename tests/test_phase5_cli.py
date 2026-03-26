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
    assert Path(out["submission_archive"]).is_file()
    assert out["status"]["data"]["submission_bundle_exists"] is True
    assert out["status"]["data"]["submission_archive_exists"] is True


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


def test_phase5_run_no_archive_option(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    proposal = tmp_path / "data" / "proposals" / "proposal-confirmed.json"
    _confirmed(proposal)
    r = CliRunner().invoke(
        app,
        ["phase5", "run", "--proposal", str(proposal), "--no-archive"],
    )
    assert r.exit_code == 0
    out = json.loads(r.stdout)
    assert out["submission_archive"] is None
    assert out["status"]["data"]["submission_archive_exists"] is False


def test_phase5_verify_ok_with_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    proposal = tmp_path / "data" / "proposals" / "proposal-confirmed.json"
    _confirmed(proposal)
    run = CliRunner().invoke(app, ["phase5", "run", "--proposal", str(proposal)])
    assert run.exit_code == 0
    out = json.loads(run.stdout)
    bundle = Path(out["submission_bundle"])
    archive = Path(out["submission_archive"])

    verify = CliRunner().invoke(
        app,
        ["phase5", "verify", "--bundle-dir", str(bundle), "--archive", str(archive)],
    )
    assert verify.exit_code == 0
    payload = json.loads(verify.stdout)
    assert payload["ok"] is True
    assert payload["missing"] == []
    assert payload["archive"]["ok"] is True


def test_phase5_verify_fails_on_missing_bundle_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    bundle = tmp_path / "data" / "submissions" / "submission-package"
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / "proposal-confirmed.json").write_text("{}", encoding="utf-8")
    r = CliRunner().invoke(app, ["phase5", "verify", "--bundle-dir", str(bundle)])
    assert r.exit_code == 1
    err = json.loads(r.stderr.strip())
    assert err["ok"] is False
    assert "experiment-report.json" in err["missing"]


def test_phase5_verify_fails_on_invalid_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    bundle = tmp_path / "data" / "submissions" / "submission-package"
    bundle.mkdir(parents=True, exist_ok=True)
    for name in [
        "proposal-confirmed.json",
        "experiment-report.json",
        "manuscript-draft.md",
        "manifest.json",
    ]:
        (bundle / name).write_text("{}", encoding="utf-8")
    bad = tmp_path / "bad.tar.gz"
    bad.write_text("not a tar", encoding="utf-8")
    r = CliRunner().invoke(
        app,
        ["phase5", "verify", "--bundle-dir", str(bundle), "--archive", str(bad)],
    )
    assert r.exit_code == 1
    err = json.loads(r.stderr.strip())
    assert err["archive"]["error"] == "invalid_archive"
