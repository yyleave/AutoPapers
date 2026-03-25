from __future__ import annotations

import json

from typer.testing import CliRunner

from autopapers.cli import app


def test_providers_command_lists_all() -> None:
    runner = CliRunner()
    r = runner.invoke(app, ["providers"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    names = {p["name"] for p in data["providers"]}
    assert names == {"aminer", "arxiv", "crossref", "local_pdf", "openalex"}
    for p in data["providers"]:
        assert "description" in p
        assert isinstance(p["description"], str)
        assert p["description"].strip() != ""
