from __future__ import annotations

import json

from typer.testing import CliRunner

from autopapers.cli import app


def test_config_command_outputs_json() -> None:
    runner = CliRunner()
    r = runner.invoke(app, ["config"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert "effective" in data
    assert "provider" in data["effective"]
    assert "log_level" in data["effective"]
    assert "default_toml_path" in data
    assert "data_repo_root" in data
    assert "env_override" in data
