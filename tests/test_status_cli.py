from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autopapers.cli import app


def test_status_cli_prints_json_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOPAPERS_REPO_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["status"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert "app_version" in data
    assert data["config"]["provider"]
    assert "data" in data
    assert "corpus_snapshot" in data
    assert data["autopapers_repo_root_env_set"] is True
    assert data["paths"]["repo_root"] == str(tmp_path.resolve())


def test_status_cli_repo_root_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTOPAPERS_REPO_ROOT", raising=False)
    r = CliRunner().invoke(app, ["status"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert data["autopapers_repo_root_env_set"] is False
