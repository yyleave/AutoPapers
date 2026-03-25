from __future__ import annotations

from pathlib import Path

import pytest

from autopapers.phase1.profile.validate import load_schema, validate_profile


def schema_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "autopapers"
        / "schemas"
        / "user_profile.schema.json"
    )


def test_valid_profile_passes() -> None:
    schema = load_schema(schema_path())
    profile = {
        "schema_version": "0.1",
        "user": {"languages": ["zh", "en"]},
        "background": {"domains": [], "skills": [], "constraints": []},
        "hardware": {"device": "mac"},
        "research_intent": {
            "problem_statements": [],
            "keywords": [],
            "non_goals": [],
            "risk_tolerance": "medium",
        },
    }
    validate_profile(profile=profile, schema=schema)


def test_invalid_profile_fails() -> None:
    schema = load_schema(schema_path())
    profile = {
        "schema_version": "0.1",
        "user": {"languages": []},
        "background": {"domains": [], "skills": [], "constraints": []},
        "hardware": {"device": "not-a-real-device"},
        "research_intent": {
            "problem_statements": [],
            "keywords": [],
            "non_goals": [],
            "risk_tolerance": "extreme",
        },
    }

    with pytest.raises(ValueError) as e:
        validate_profile(profile=profile, schema=schema)

    msg = str(e.value)
    assert "Profile validation failed" in msg

