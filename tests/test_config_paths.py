from __future__ import annotations

from pathlib import Path

import pytest

from autopapers.config import _resolve_data_repo_root, get_paths, load_config


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


def test_load_config_env_without_default_toml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTOPAPERS_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("AUTOPAPERS_PROVIDER", "crossref")
    monkeypatch.setenv("AUTOPAPERS_LOG_LEVEL", "DEBUG")
    monkeypatch.delenv("AUTOPAPERS_CONTACT_EMAIL", raising=False)
    cfg_path = tmp_path / "configs" / "default.toml"
    assert not cfg_path.is_file()
    c = load_config()
    assert c.provider == "crossref"
    assert c.log_level == "DEBUG"


def test_load_config_reads_toml_under_autopapers_repo_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "default.toml").write_text(
        'provider = "openalex"\nlog_level = "WARNING"\ncontact_email = "toml@example.com"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("AUTOPAPERS_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("AUTOPAPERS_PROVIDER", raising=False)
    monkeypatch.delenv("AUTOPAPERS_LOG_LEVEL", raising=False)
    monkeypatch.delenv("AUTOPAPERS_CONTACT_EMAIL", raising=False)
    c = load_config()
    assert c.provider == "openalex"
    assert c.log_level == "WARNING"
    assert c.contact_email == "toml@example.com"


def test_load_config_contact_email_env_overrides_toml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "default.toml").write_text(
        'contact_email = "a@b.c"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("AUTOPAPERS_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("AUTOPAPERS_CONTACT_EMAIL", "env@example.com")
    c = load_config()
    assert c.contact_email == "env@example.com"
