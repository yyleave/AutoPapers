from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autopapers.cli import app


def test_workspace_init_writes_default_toml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTOPAPERS_REPO_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["workspace-init"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert data["ok"] is True
    assert "written" in data
    p = Path(data["written"])
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert 'provider = "arxiv"' in text
    assert data["status"]["config"]["default_toml_present"] is True


def test_workspace_init_skips_when_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTOPAPERS_REPO_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "configs"
    cfg.mkdir(parents=True)
    toml_body = 'log_level = "INFO"\nprovider = "openalex"\n'
    (cfg / "default.toml").write_text(toml_body, encoding="utf-8")
    r = CliRunner().invoke(app, ["workspace-init"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert data["ok"] is True
    assert data["skipped"] is True
    assert "openalex" in (cfg / "default.toml").read_text(encoding="utf-8")


def test_workspace_init_force_overwrites(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTOPAPERS_REPO_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "configs"
    cfg.mkdir(parents=True)
    target = cfg / "default.toml"
    target.write_text("provider = \"crossref\"\n", encoding="utf-8")
    r = CliRunner().invoke(app, ["workspace-init", "--force"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert data["ok"] is True
    assert "written" in data
    assert 'provider = "arxiv"' in target.read_text(encoding="utf-8")
