from __future__ import annotations

from pathlib import Path

import pytest

from autopapers.config import _resolve_data_repo_root, get_paths


def test_get_paths_uses_autopapers_repo_root_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AUTOPAPERS_REPO_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "proj"
    root.mkdir()
    monkeypatch.setenv("AUTOPAPERS_REPO_ROOT", str(root))
    p = get_paths()
    assert p.repo_root == root.resolve()
    assert p.data_dir == (root / "data").resolve()


def test_resolve_data_repo_root_explicit_wins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv("AUTOPAPERS_REPO_ROOT", str(other))
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    assert _resolve_data_repo_root(explicit) == explicit.resolve()
