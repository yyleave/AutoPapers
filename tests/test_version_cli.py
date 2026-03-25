from __future__ import annotations

from typer.testing import CliRunner

from autopapers.cli import app


def test_version_command_prints_non_empty() -> None:
    runner = CliRunner()
    r = runner.invoke(app, ["version"])
    assert r.exit_code == 0
    assert r.stdout.strip() != ""
