from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.mark.integration
def test_mvp_demo_script_extended_runs(tmp_path: Path) -> None:
    repo = _repo_root()
    script = repo / "scripts" / "mvp_demo.sh"
    run_dir = tmp_path / "mvp-extended"
    env = os.environ.copy()
    result = subprocess.run(
        ["bash", str(script), "--mode", "offline", "--workdir", str(run_dir), "--extended"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert (run_dir / "data" / "submissions" / "submission-package.tar.gz").is_file()
    assert (run_dir / "data" / "experiments" / "experiment-report.json").is_file()


@pytest.mark.integration
def test_mvp_demo_script_offline_runs(tmp_path: Path) -> None:
    repo = _repo_root()
    script = repo / "scripts" / "mvp_demo.sh"
    run_dir = tmp_path / "mvp-run"
    env = os.environ.copy()
    result = subprocess.run(
        ["bash", str(script), "--mode", "offline", "--workdir", str(run_dir)],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert (run_dir / "data" / "proposals" / "proposal-confirmed.json").is_file()
    assert (run_dir / "data" / "kg" / "corpus-snapshot.json").is_file()


@pytest.mark.integration
def test_full_pipeline_demo_script_offline_runs(tmp_path: Path) -> None:
    repo = _repo_root()
    script = repo / "scripts" / "full_pipeline_demo.sh"
    run_dir = tmp_path / "full-run"
    env = os.environ.copy()
    result = subprocess.run(
        [
            "bash",
            str(script),
            "--mode",
            "offline",
            "--workdir",
            str(run_dir),
            "--title",
            "Script Integration Topic",
        ],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert (run_dir / "data" / "submissions" / "submission-package").is_dir()
    assert (run_dir / "data" / "submissions" / "submission-package.tar.gz").is_file()
    assert (run_dir / "data" / "releases" / "release-report.json").is_file()
    assert (run_dir / "data" / "releases" / "release-verify-report.json").is_file()


def test_release_check_script_help() -> None:
    repo = _repo_root()
    script = repo / "scripts" / "release_check.sh"
    result = subprocess.run(
        ["bash", str(script), "--help"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Pre-release acceptance checklist" in result.stdout


@pytest.mark.integration
def test_release_check_script_runs_offline() -> None:
    repo = _repo_root()
    script = repo / "scripts" / "release_check.sh"
    result = subprocess.run(
        ["bash", str(script), "--skip-offline-tests", "--skip-demo-tests"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "Release check passed." in result.stdout
    assert "doctor" in result.stdout.lower()
    assert "app_version" in result.stdout


@pytest.mark.integration
def test_release_check_script_runs_legacy_stage_only() -> None:
    repo = _repo_root()
    script = repo / "scripts" / "release_check.sh"
    result = subprocess.run(
        ["bash", str(script), "--skip-offline-tests", "--legacy-only-tests"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "Demo + legacy scripts integration (legacy-only)" in result.stdout
    assert "Release check passed." in result.stdout
