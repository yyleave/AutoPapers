from __future__ import annotations

from typer.testing import CliRunner

from autopapers.cli import app


def test_version_command_prints_non_empty() -> None:
    runner = CliRunner()
    r = runner.invoke(app, ["version"])
    assert r.exit_code == 0
    assert r.stdout.strip() != ""


def test_root_help_lists_quick_commands_epilog() -> None:
    r = CliRunner().invoke(app, ["--help"])
    assert r.exit_code == 0
    out = r.stdout
    assert "workspace-init" in out
    assert "status" in out
    assert "release-verify" in out
    assert "phase5" in out
