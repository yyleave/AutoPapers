from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autopapers.cli import app
from autopapers.phase1.profile.summary import compact_profile_view


def test_compact_profile_view_empty_profile() -> None:
    v = compact_profile_view({})
    assert v["schema_version"] is None
    assert v["display_name"] is None
    assert v["keywords"] == []
    assert v["problem_statements"] == []


def test_compact_profile_view_shape() -> None:
    prof = {
        "schema_version": "0.1",
        "user": {"display_name": "Alice", "languages": ["en"]},
        "research_intent": {
            "keywords": ["ml"],
            "problem_statements": ["p1"],
            "risk_tolerance": "low",
        },
        "hardware": {"device": "linux"},
    }
    v = compact_profile_view(prof)
    assert v["display_name"] == "Alice"
    assert v["keywords"] == ["ml"]
    assert v["hardware_device"] == "linux"
    assert v["risk_tolerance"] == "low"


def test_profile_show_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    prof_path = tmp_path / "u.json"
    prof_path.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "user": {"languages": ["en"]},
                "background": {"domains": [], "skills": [], "constraints": []},
                "hardware": {"device": "other"},
                "research_intent": {
                    "problem_statements": [],
                    "keywords": ["x"],
                    "non_goals": [],
                    "risk_tolerance": "medium",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(app, ["profile", "show", "-i", str(prof_path)])
    assert r.exit_code == 0
    out = json.loads(r.stdout)
    assert out["keywords"] == ["x"]
