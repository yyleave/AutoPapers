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
