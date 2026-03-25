from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_schema(schema_path: Path) -> dict[str, Any]:
    schema = load_json(schema_path)
    if not isinstance(schema, dict):
        raise TypeError("Schema must be a JSON object")
    return schema


def validate_profile(*, profile: Any, schema: dict[str, Any]) -> None:
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(profile), key=lambda e: list(e.absolute_path))
    if errors:
        lines: list[str] = []
        for e in errors[:20]:
            path = ".".join(str(p) for p in e.absolute_path) or "<root>"
            lines.append(f"- {path}: {e.message}")
        more = "" if len(errors) <= 20 else f"\n(… {len(errors) - 20} more)"
        raise ValueError("Profile validation failed:\n" + "\n".join(lines) + more)

