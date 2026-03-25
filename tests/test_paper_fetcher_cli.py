from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


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
