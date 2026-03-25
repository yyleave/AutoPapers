from __future__ import annotations

from typing import Any


def compact_profile_view(profile: dict[str, Any]) -> dict[str, Any]:
    """Stable, small JSON-friendly view for CLI / logging (not a schema)."""

    u = profile.get("user") or {}
    ri = profile.get("research_intent") or {}
    hw = profile.get("hardware") or {}
    return {
        "schema_version": profile.get("schema_version"),
        "display_name": u.get("display_name"),
        "languages": u.get("languages"),
        "keywords": list(ri.get("keywords") or []),
        "problem_statements": list(ri.get("problem_statements") or []),
        "risk_tolerance": ri.get("risk_tolerance"),
        "hardware_device": hw.get("device"),
    }
