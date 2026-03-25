from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from autopapers.cli import app


def test_config_contact_email_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTOPAPERS_CONTACT_EMAIL", "cfg-env@example.com")
    r = CliRunner().invoke(app, ["config"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert data["effective"]["contact_email"] == "cfg-env@example.com"
    assert data["env_override"]["AUTOPAPERS_CONTACT_EMAIL"] is True


def test_config_command_outputs_json() -> None:
    runner = CliRunner()
    r = runner.invoke(app, ["config"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert "effective" in data
    assert "provider" in data["effective"]
    assert "log_level" in data["effective"]
    assert "contact_email" in data["effective"]
    assert "default_toml_path" in data
    assert "data_repo_root" in data
    assert "env_override" in data
