from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autopapers.cli import app


@pytest.mark.integration
def test_profile_corpus_proposal_chain_no_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No-network chain: corpus snapshot, profile init, corpus info, proposal, status."""
    monkeypatch.chdir(tmp_path)
    user = tmp_path / "user.json"
    kg = tmp_path / "data" / "kg"
    kg.mkdir(parents=True)
    snap = kg / "corpus-snapshot.json"
    snap.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "nodes": [
                    {
                        "id": "paper:local:1",
                        "type": "Paper",
                        "label": "Integration Paper",
                        "source": "local",
                        "external_id": "1",
                    }
                ],
                "edges": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    runner = CliRunner()
    assert runner.invoke(app, ["profile", "init", "-o", str(user)]).exit_code == 0

    r_info = runner.invoke(app, ["corpus", "info"])
    assert r_info.exit_code == 0
    info = json.loads(r_info.stdout)
    assert Path(info["snapshot"]).resolve() == snap.resolve()

    r_draft = runner.invoke(
        app,
        ["proposal", "draft", "--profile", str(user), "-t", "Integration chain"],
    )
    assert r_draft.exit_code == 0
    err = r_draft.stderr or ""
    assert "Using corpus:" in err
    draft_path = Path(r_draft.stdout.strip())
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    assert draft["title"] == "Integration chain"
    assert "Feasibility / scope (conservative):" in str(draft["problem"])
    killer = str(draft.get("debate_notes", {}).get("killer", ""))
    assert "Integration Paper" in killer or "local" in killer

    r_confirm = runner.invoke(app, ["proposal", "confirm", "-i", str(draft_path)])
    assert r_confirm.exit_code == 0
    confirmed = Path(r_confirm.stdout.strip())
    assert json.loads(confirmed.read_text(encoding="utf-8"))["status"] == "confirmed"

    md_out = tmp_path / "out.md"
    r_export = runner.invoke(app, ["proposal", "export", "-i", str(confirmed), "-o", str(md_out)])
    assert r_export.exit_code == 0
    assert md_out.is_file()
    md = md_out.read_text(encoding="utf-8")
    assert "# Integration chain" in md

    r_status = runner.invoke(app, ["status"])
    assert r_status.exit_code == 0
    status = json.loads(r_status.stdout)
    assert status["corpus_snapshot"]["present"] is True
    assert status["data"]["proposal_draft_exists"] is True
    assert status["data"]["proposal_confirmed_exists"] is True
