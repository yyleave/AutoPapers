from __future__ import annotations

import json
from pathlib import Path

import pytest

from autopapers.phase1.profile.extract import load_profile_from_json
from autopapers.phase1.profile.store import save_profile


def test_load_profile_from_json_object(tmp_path: Path) -> None:
    p = tmp_path / "user.json"
    p.write_text('{"schema_version": "0.1", "x": 1}', encoding="utf-8")
    data = load_profile_from_json(p)
    assert data == {"schema_version": "0.1", "x": 1}


def test_save_profile_writes_timestamped_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTOPAPERS_REPO_ROOT", str(tmp_path))
    profile = {"schema_version": "0.1", "user": {}}
    out = save_profile(profile=profile)
    assert out.parent == tmp_path / "data" / "profiles"
    assert out.name.startswith("profile-") and out.suffix == ".json"
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved == profile


def test_save_profile_custom_dir(tmp_path: Path) -> None:
    custom = tmp_path / "my_profiles"
    out = save_profile(profile={"a": 1}, profiles_dir=custom)
    assert out.parent == custom
    assert json.loads(out.read_text(encoding="utf-8")) == {"a": 1}
