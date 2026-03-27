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
    (b / "evaluation-summary.json").write_text("{}", encoding="utf-8")
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


def test_phase4_pdf_engine_missing_exits_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    md = tmp_path / "data" / "manuscripts" / "manuscript-draft.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text("# draft\n", encoding="utf-8")

    # Force "no engine available" regardless of the runner environment.
    import autopapers.cli as cli  # noqa: PLC0415

    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    r = CliRunner().invoke(app, ["phase4", "pdf", "--manuscript", str(md)])
    assert r.exit_code != 0


def test_phase4_latex_first_line_is_valid_documentclass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generated .tex must use single backslash LaTeX commands (not ``\\\\documentclass``)."""

    monkeypatch.chdir(tmp_path)
    md = tmp_path / "data" / "manuscripts" / "manuscript-draft.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text("# Title\n\nbody\n", encoding="utf-8")
    r = CliRunner().invoke(app, ["phase4", "latex", "--manuscript", str(md)])
    assert r.exit_code == 0, r.stdout + r.stderr
    tex_path = Path(r.stdout.strip())
    first = tex_path.read_text(encoding="utf-8").lstrip().split("\n", 1)[0]
    assert first == r"\documentclass[11pt]{article}"
    assert not first.startswith(r"\\documentclass")


def test_phase4_bib_writes_references_bib(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    snap = tmp_path / "data" / "kg" / "corpus-snapshot.json"
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "nodes": [
                    {
                        "id": "paper:local:1",
                        "type": "Paper",
                        "label": "A Paper",
                        "source": "local",
                        "external_id": "1",
                        "pdf_path": "/tmp/a.pdf",
                    }
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(app, ["phase4", "bib", "--snapshot", str(snap)])
    assert r.exit_code == 0
    out = Path(r.stdout.strip())
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "@misc" in text
    assert "A Paper" in text
