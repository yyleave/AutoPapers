from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autopapers.cli import app
from autopapers.status_report import build_status


def test_doctor_cli_matches_status_doctor_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTOPAPERS_REPO_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    st = build_status()
    r = CliRunner().invoke(app, ["doctor"])
    assert r.exit_code == 0
    from_cli = json.loads(r.stdout)
    assert from_cli == st["doctor"]


def test_doctor_cli_outputs_structure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOPAPERS_REPO_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["doctor"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert data["ok"] is True
    assert "app_version" in data
    assert "python" in data
    assert data["config"]["default_toml_present"] is False
    assert "optional_features" in data
    assert "latex_engines" in data["optional_features"]
    assert "docker_cli" in data["optional_features"]
    assert isinstance(data["optional_features"]["ollama_cli"], bool)
    assert "paper_fetcher_cli" in data["optional_features"]
    assert isinstance(data["optional_features"]["paper_fetcher_cli"], bool)
    assert data["optional_features"]["llm_supported_backends"] == ["ollama", "openai", "stub"]
    assert data["optional_features"]["llm_backend_valid"] is True
    assert data["optional_features"]["llm_backend_hint"] is None


def test_doctor_cli_invalid_llm_backend_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOPAPERS_LLM_BACKEND", "nope")
    r = CliRunner().invoke(app, ["doctor"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert data["optional_features"]["llm_backend"] == "nope"
    assert data["optional_features"]["llm_backend_valid"] is False
    assert (
        data["optional_features"]["llm_backend_hint"]
        == "Set AUTOPAPERS_LLM_BACKEND to openai|ollama|stub"
    )


def test_doctor_cli_sees_aminer_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMINER_API_KEY", "k")
    r = CliRunner().invoke(app, ["doctor"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert data["optional_features"]["aminer_api_key"] is True
