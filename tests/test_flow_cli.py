from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autopapers.cli import app


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
    assert any("resume" in s for s in out["next_steps"])
