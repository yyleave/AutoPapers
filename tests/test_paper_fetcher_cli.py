from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_paper_fetcher_console_script_help_exits_zero() -> None:
    r = subprocess.run(
        ["uv", "run", "paper-fetcher", "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert "usage:" in r.stdout.lower()


def test_paper_fetcher_help_exits_zero() -> None:
    script = REPO_ROOT / "src" / "paper_fetcher.py"
    r = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    assert "usage:" in r.stdout.lower()


def test_paper_fetcher_no_token_no_download_path_runs() -> None:
    script = REPO_ROOT / "src" / "paper_fetcher.py"
    env = dict(os.environ)
    env.pop("AMINER_API_KEY", None)
    r = subprocess.run(
        [
            sys.executable,
            str(script),
            "offline query",
            "--limit",
            "1",
            "--no-download",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "autopapers" in out
    assert "未设置 AMINER_API_KEY" in out
    assert "未找到相关论文" in out
