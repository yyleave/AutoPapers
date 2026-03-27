from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autopapers.cli import app


def test_flow_cli_phase3_suggests_generate_experiment_when_runner_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTOPAPERS_REPO_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    (data / "papers" / "metadata").mkdir(parents=True, exist_ok=True)
    (data / "papers" / "metadata" / "x.json").write_text("{}", encoding="utf-8")
    (data / "kg").mkdir(parents=True, exist_ok=True)
    (data / "kg" / "corpus-snapshot.json").write_text("{}", encoding="utf-8")
    (data / "proposals").mkdir(parents=True, exist_ok=True)
    (data / "proposals" / "proposal-confirmed.json").write_text("{}", encoding="utf-8")

    r = CliRunner().invoke(app, ["flow"])
    assert r.exit_code == 0
    out = json.loads(r.stdout)
    assert out["phase3_experiment"] is False
    assert any("generate-experiment" in s for s in out["next_steps"])
    assert any("phase3 run" in s for s in out["next_steps"])


def test_flow_cli_suggests_aminer_when_aminer_key_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTOPAPERS_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("AMINER_API_KEY", "test-token")
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["flow"])
    assert r.exit_code == 0
    out = json.loads(r.stdout)
    assert out["phase1_data"] is False
    assert any("--provider aminer" in s for s in out["next_steps"])
    assert any("aminer-search" in s for s in out["next_steps"])


def test_flow_cli_initial_state_suggests_phase1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTOPAPERS_REPO_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["flow"])
    assert r.exit_code == 0
    out = json.loads(r.stdout)
    assert out["phase1_data"] is False
    assert any("workspace-init" in s for s in out["next_steps"])
    assert any("phase1 run" in s for s in out["next_steps"])


def test_flow_cli_completed_state_suggests_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTOPAPERS_REPO_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    (data / "papers" / "metadata").mkdir(parents=True, exist_ok=True)
    (data / "papers" / "metadata" / "x.json").write_text("{}", encoding="utf-8")
    (data / "kg").mkdir(parents=True, exist_ok=True)
    (data / "kg" / "corpus-snapshot.json").write_text("{}", encoding="utf-8")
    (data / "proposals").mkdir(parents=True, exist_ok=True)
    (data / "proposals" / "proposal-confirmed.json").write_text("{}", encoding="utf-8")
    (data / "experiments").mkdir(parents=True, exist_ok=True)
    (data / "experiments" / "experiment-report.json").write_text("{}", encoding="utf-8")
    (data / "experiments" / "evaluation-summary.json").write_text("{}", encoding="utf-8")
    (data / "manuscripts").mkdir(parents=True, exist_ok=True)
    (data / "manuscripts" / "manuscript-draft.md").write_text("# m\n", encoding="utf-8")
    (data / "submissions" / "submission-package").mkdir(parents=True, exist_ok=True)
    (data / "submissions" / "submission-package.tar.gz").write_bytes(b"gz")
    (data / "releases").mkdir(parents=True, exist_ok=True)
    (data / "releases" / "release-report.json").write_text("{}", encoding="utf-8")

    r = CliRunner().invoke(app, ["flow"])
    assert r.exit_code == 0
    out = json.loads(r.stdout)
    assert out["release_report"] is True
    assert out["release_verify_report"] is False
    assert any("release-verify" in s for s in out["next_steps"])


def test_flow_cli_fully_completed_state_suggests_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTOPAPERS_REPO_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    (data / "papers" / "metadata").mkdir(parents=True, exist_ok=True)
    (data / "papers" / "metadata" / "x.json").write_text("{}", encoding="utf-8")
    (data / "kg").mkdir(parents=True, exist_ok=True)
    (data / "kg" / "corpus-snapshot.json").write_text("{}", encoding="utf-8")
    (data / "proposals").mkdir(parents=True, exist_ok=True)
    (data / "proposals" / "proposal-confirmed.json").write_text("{}", encoding="utf-8")
    (data / "experiments").mkdir(parents=True, exist_ok=True)
    (data / "experiments" / "experiment-report.json").write_text("{}", encoding="utf-8")
    (data / "experiments" / "evaluation-summary.json").write_text("{}", encoding="utf-8")
    (data / "manuscripts").mkdir(parents=True, exist_ok=True)
    (data / "manuscripts" / "manuscript-draft.md").write_text("# m\n", encoding="utf-8")
    (data / "submissions" / "submission-package").mkdir(parents=True, exist_ok=True)
    (data / "submissions" / "submission-package.tar.gz").write_bytes(b"gz")
    (data / "releases").mkdir(parents=True, exist_ok=True)
    (data / "releases" / "release-report.json").write_text("{}", encoding="utf-8")
    (data / "releases" / "release-verify-report.json").write_text("{}", encoding="utf-8")

    r = CliRunner().invoke(app, ["flow"])
    assert r.exit_code == 0
    out = json.loads(r.stdout)
    assert out["release_report"] is True
    assert out["release_verify_report"] is True
    assert any("resume" in s for s in out["next_steps"])
    assert any("publish" in s for s in out["next_steps"])
    assert any("doctor" in s for s in out["next_steps"])


def test_flow_cli_phase5_done_suggests_release_and_publish_shortcut(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Archive exists but no release-report: next_steps include release and publish."""

    monkeypatch.setenv("AUTOPAPERS_REPO_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    (data / "papers" / "metadata").mkdir(parents=True, exist_ok=True)
    (data / "papers" / "metadata" / "x.json").write_text("{}", encoding="utf-8")
    (data / "kg").mkdir(parents=True, exist_ok=True)
    (data / "kg" / "corpus-snapshot.json").write_text("{}", encoding="utf-8")
    (data / "proposals").mkdir(parents=True, exist_ok=True)
    (data / "proposals" / "proposal-confirmed.json").write_text("{}", encoding="utf-8")
    (data / "experiments").mkdir(parents=True, exist_ok=True)
    (data / "experiments" / "experiment-report.json").write_text("{}", encoding="utf-8")
    (data / "experiments" / "evaluation-summary.json").write_text("{}", encoding="utf-8")
    (data / "manuscripts").mkdir(parents=True, exist_ok=True)
    (data / "manuscripts" / "manuscript-draft.md").write_text("# m\n", encoding="utf-8")
    (data / "submissions" / "submission-package").mkdir(parents=True, exist_ok=True)
    (data / "submissions" / "submission-package.tar.gz").write_bytes(b"gz")

    r = CliRunner().invoke(app, ["flow"])
    assert r.exit_code == 0
    out = json.loads(r.stdout)
    assert out["phase5_archive"] is True
    assert out["release_report"] is False
    assert any("autopapers release" in s for s in out["next_steps"])
    assert any("autopapers publish" in s for s in out["next_steps"])
