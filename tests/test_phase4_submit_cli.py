from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autopapers.cli import app


def _bundle_dir(base: Path) -> Path:
    b = base / "data" / "submissions" / "submission-package"
    b.mkdir(parents=True, exist_ok=True)
    (b / "proposal-confirmed.json").write_text("{}", encoding="utf-8")
    (b / "experiment-report.json").write_text("{}", encoding="utf-8")
    (b / "manuscript-draft.md").write_text("# draft\n", encoding="utf-8")
    (b / "manifest.json").write_text("{}", encoding="utf-8")
    return b


def test_phase4_submit_creates_tar_gz(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    b = _bundle_dir(tmp_path)
    r = CliRunner().invoke(app, ["phase4", "submit", "--bundle-dir", str(b)])
    assert r.exit_code == 0, r.stdout + r.stderr
    out = Path(r.stdout.strip())
    assert out.is_file()
    with tarfile.open(out, "r:gz") as tf:
        names = tf.getnames()
    assert any(n.endswith("submission-package/manifest.json") for n in names)


def test_phase4_submit_rejects_incomplete_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    b = tmp_path / "data" / "submissions" / "submission-package"
    b.mkdir(parents=True, exist_ok=True)
    (b / "proposal-confirmed.json").write_text("{}", encoding="utf-8")
    r = CliRunner().invoke(app, ["phase4", "submit", "--bundle-dir", str(b)])
    assert r.exit_code == 1
    err = json.loads(r.stderr.strip())
    assert err["error"] == "bundle_incomplete"
