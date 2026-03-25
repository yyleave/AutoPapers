from __future__ import annotations

from pathlib import Path

import pytest

from autopapers.phase1.profile.validate import load_json, load_schema, validate_profile


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


def test_load_json_reads_object(tmp_path: Path) -> None:
    p = tmp_path / "doc.json"
    p.write_text('{"k": true}', encoding="utf-8")
    assert load_json(p) == {"k": True}


def test_load_schema_rejects_non_object(tmp_path: Path) -> None:
    p = tmp_path / "schema.json"
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(TypeError, match="JSON object"):
        load_schema(p)


def test_validate_profile_error_mentions_root_or_fields() -> None:
    schema = load_schema(schema_path())
    with pytest.raises(ValueError) as exc_info:
        validate_profile(profile={}, schema=schema)
    msg = str(exc_info.value)
    assert "Profile validation failed" in msg
    assert "<root>" in msg or "schema_version" in msg


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

