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
    assert "entrypoints_on_path" in data
    ep = data["entrypoints_on_path"]
    assert isinstance(ep["autopapers"], bool)
    assert isinstance(ep["paper_fetcher_cli"], bool)
    assert data["llm"]["effective_backend"] in {"openai", "ollama", "stub"}
    assert data["llm"]["supported_backends"] == ["openai", "ollama", "stub"]
    assert data["llm"]["backend_valid"] is True
    assert data["llm"]["backend_hint"] is None
    assert "AUTOPAPERS_LLM_BACKEND" in data["llm"]


def test_config_llm_invalid_backend_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOPAPERS_LLM_BACKEND", "bad-backend")
    r = CliRunner().invoke(app, ["config"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert data["llm"]["effective_backend"] == "bad-backend"
    assert data["llm"]["backend_valid"] is False
    assert data["llm"]["backend_hint"] == "Set AUTOPAPERS_LLM_BACKEND to openai|ollama|stub"
