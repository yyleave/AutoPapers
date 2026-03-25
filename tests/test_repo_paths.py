from __future__ import annotations

import sys

from autopapers import repo_paths


def test_src_dir_points_at_src_with_package() -> None:
    d = repo_paths.src_dir()
    assert (d / "autopapers" / "repo_paths.py").is_file()


def test_repo_root_is_parent_of_src() -> None:
    assert repo_paths.repo_root() == repo_paths.src_dir().parent


def test_ensure_legacy_api_on_path_idempotent() -> None:
    s = str(repo_paths.src_dir())
    repo_paths.ensure_legacy_api_on_path()
    k = sys.path.count(s)
    assert k >= 1
    repo_paths.ensure_legacy_api_on_path()
    assert sys.path.count(s) == k
