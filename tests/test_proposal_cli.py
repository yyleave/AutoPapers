from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autopapers.cli import app


def test_proposal_draft_cli_writes_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    prof = tmp_path / "user.json"
    assert CliRunner().invoke(app, ["profile", "init", "-o", str(prof)]).exit_code == 0
    r = CliRunner().invoke(
        app,
        ["proposal", "draft", "--profile", str(prof), "--title", "Custom title"],
    )
    assert r.exit_code == 0
    out = Path(r.stdout.strip())
    assert out.is_file()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["title"] == "Custom title"
    assert data["status"] == "draft"


def test_proposal_confirm_and_export_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    prof = tmp_path / "user.json"
    assert CliRunner().invoke(app, ["profile", "init", "-o", str(prof)]).exit_code == 0
    assert (
        CliRunner().invoke(
            app,
            ["proposal", "draft", "--profile", str(prof), "-t", "T1"],
        ).exit_code
        == 0
    )
    draft = tmp_path / "data" / "proposals" / "proposal-draft.json"
    r = CliRunner().invoke(app, ["proposal", "confirm", "-i", str(draft)])
    assert r.exit_code == 0
    confirmed = Path(r.stdout.strip())
    assert json.loads(confirmed.read_text(encoding="utf-8"))["status"] == "confirmed"

    md_path = tmp_path / "prop.md"
    r2 = CliRunner().invoke(
        app,
        ["proposal", "export", "-i", str(confirmed), "-o", str(md_path)],
    )
    assert r2.exit_code == 0
    assert md_path.is_file()
    text = md_path.read_text(encoding="utf-8")
    assert "# T1" in text
    assert "confirmed" in text.lower() or "Status" in text
