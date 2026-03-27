from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autopapers.cli import app


def test_flow_cli_when_archive_missing_suggests_phase5_run_alternative(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """phase4+ complete but no tar.gz: next_steps include phase5 run one-liner."""
    monkeypatch.setenv("AUTOPAPERS_REPO_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    (data / "papers" / "metadata").mkdir(parents=True, exist_ok=True)
    (data / "papers" / "metadata" / "x.json").write_text("{}", encoding="utf-8")
    (data / "kg").mkdir(parents=True, exist_ok=True)
    (data / "kg" / "corpus-snapshot.json").write_text("{}", encoding="utf-8")
    (data / "proposals").mkdir(parents=True, exist_ok=True)
    (data / "proposals" / "proposal-confirmed.json").write_text("{}", encoding="utf-8")
    (data / "experiments").mkdir(parents=True, exist_ok=True)
    (data / "experiments" / "experiment-report.json").write_text("{}", encoding="utf-8")
    (data / "experiments" / "evaluation-summary.json").write_text("{}", encoding="utf-8")
    (data / "manuscripts").mkdir(parents=True, exist_ok=True)
    (data / "manuscripts" / "manuscript-draft.md").write_text("# m\n", encoding="utf-8")
    bundle = data / "submissions" / "submission-package"
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / "placeholder.txt").write_text("x", encoding="utf-8")

    r = CliRunner().invoke(app, ["flow"])
    assert r.exit_code == 0
    out = json.loads(r.stdout)
    assert out["phase5_archive"] is False
    assert any("phase5 run" in s for s in out["next_steps"])
    verify_lines = [s for s in out["next_steps"] if "phase5 verify" in s]
    assert len(verify_lines) == 1
    assert "--archive" not in verify_lines[0]
