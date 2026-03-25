from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autopapers.cli import app


def test_profile_init_writes_template(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "user_profile.json"
    r = CliRunner().invoke(app, ["profile", "init", "-o", str(out)])
    assert r.exit_code == 0
    assert "Wrote template" in r.stdout
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema_version"] == "0.1"
    assert data["hardware"]["device"] == "mac"


def test_profile_show_cli_rejects_invalid_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    bad = tmp_path / "bad-show.json"
    bad.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "user": {"languages": []},
                "background": {"domains": [], "skills": [], "constraints": []},
                "hardware": {"device": "mac"},
                "research_intent": {
                    "problem_statements": [],
                    "keywords": [],
                    "non_goals": [],
                    "risk_tolerance": "medium",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(app, ["profile", "show", "-i", str(bad)])
    assert r.exit_code != 0


def test_profile_validate_cli_rejects_invalid_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    bad = tmp_path / "invalid-profile.json"
    bad.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "user": {"languages": []},
                "background": {"domains": [], "skills": [], "constraints": []},
                "hardware": {"device": "mac"},
                "research_intent": {
                    "problem_statements": [],
                    "keywords": [],
                    "non_goals": [],
                    "risk_tolerance": "medium",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(app, ["profile", "validate", "-i", str(bad)])
    assert r.exit_code != 0


def test_profile_validate_template_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "p.json"
    assert CliRunner().invoke(app, ["profile", "init", "-o", str(out)]).exit_code == 0
    r = CliRunner().invoke(app, ["profile", "validate", "-i", str(out)])
    assert r.exit_code == 0
    assert r.stdout.strip() == "OK"


def test_profile_save_writes_under_data_profiles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "p.json"
    assert CliRunner().invoke(app, ["profile", "init", "-o", str(out)]).exit_code == 0
    r = CliRunner().invoke(app, ["profile", "save", "-i", str(out)])
    assert r.exit_code == 0
    assert "Saved:" in r.stdout
    saved = list((tmp_path / "data" / "profiles").glob("profile-*.json"))
    assert len(saved) == 1
