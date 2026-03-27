from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autopapers import __version__ as autopapers_version
from autopapers.cli import app
from autopapers.phase2.debate import merge_stub_to_proposal, run_debate_stub


def _confirmed(path: Path) -> None:
    debate = run_debate_stub(profile_summary="p", corpus_summary="c")
    prop = merge_stub_to_proposal(title="P5", debate=debate, status="confirmed")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prop, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_phase5_run_writes_all_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    proposal = tmp_path / "data" / "proposals" / "proposal-confirmed.json"
    _confirmed(proposal)
    r = CliRunner().invoke(app, ["phase5", "run", "--proposal", str(proposal)])
    assert r.exit_code == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] is True
    assert Path(out["experiment_report"]).is_file()
    assert Path(out["evaluation_summary"]).is_file()
    assert Path(out["manuscript_draft"]).is_file()
    bundle = Path(out["submission_bundle"])
    assert bundle.is_dir()
    assert (bundle / "manifest.json").is_file()
    man = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert man.get("schema_version") == "0.2"
    assert man.get("autopapers_version") == autopapers_version
    assert isinstance(man.get("generated_at"), str) and man["generated_at"].endswith("Z")
    assert Path(out["submission_archive"]).is_file()
    assert out["status"]["data"]["submission_bundle_exists"] is True
    assert out["status"]["data"]["submission_archive_exists"] is True


def test_phase5_run_rejects_non_confirmed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    debate = run_debate_stub(profile_summary="p", corpus_summary="c")
    draft = merge_stub_to_proposal(title="Draft", debate=debate, status="draft")
    proposal = tmp_path / "proposal-draft.json"
    proposal.write_text(json.dumps(draft), encoding="utf-8")
    r = CliRunner().invoke(app, ["phase5", "run", "--proposal", str(proposal)])
    assert r.exit_code == 1
    err = json.loads(r.stderr.strip())
    assert err["error"] == "invalid_status"


def test_phase5_run_no_archive_option(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    proposal = tmp_path / "data" / "proposals" / "proposal-confirmed.json"
    _confirmed(proposal)
    r = CliRunner().invoke(
        app,
        ["phase5", "run", "--proposal", str(proposal), "--no-archive"],
    )
    assert r.exit_code == 0
    out = json.loads(r.stdout)
    assert out["submission_archive"] is None
    assert out["status"]["data"]["submission_archive_exists"] is False


def test_phase5_verify_ok_with_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    proposal = tmp_path / "data" / "proposals" / "proposal-confirmed.json"
    _confirmed(proposal)
    run = CliRunner().invoke(app, ["phase5", "run", "--proposal", str(proposal)])
    assert run.exit_code == 0
    out = json.loads(run.stdout)
    bundle = Path(out["submission_bundle"])
    archive = Path(out["submission_archive"])

    verify = CliRunner().invoke(
        app,
        ["phase5", "verify", "--bundle-dir", str(bundle), "--archive", str(archive)],
    )
    assert verify.exit_code == 0
    payload = json.loads(verify.stdout)
    assert payload["ok"] is True
    assert payload["missing"] == []
    assert payload["manifest"]["ok"] is True
    assert payload["archive"]["ok"] is True


def test_phase5_verify_fails_on_missing_bundle_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    bundle = tmp_path / "data" / "submissions" / "submission-package"
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / "proposal-confirmed.json").write_text("{}", encoding="utf-8")
    r = CliRunner().invoke(app, ["phase5", "verify", "--bundle-dir", str(bundle)])
    assert r.exit_code == 1
    err = json.loads(r.stderr.strip())
    assert err["ok"] is False
    assert "experiment-report.json" in err["missing"]


def test_phase5_verify_fails_on_invalid_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    bundle = tmp_path / "data" / "submissions" / "submission-package"
    bundle.mkdir(parents=True, exist_ok=True)
    for name in [
        "proposal-confirmed.json",
        "experiment-report.json",
        "evaluation-summary.json",
        "manuscript-draft.md",
        "manifest.json",
    ]:
        (bundle / name).write_text("{}", encoding="utf-8")
    bad = tmp_path / "bad.tar.gz"
    bad.write_text("not a tar", encoding="utf-8")
    r = CliRunner().invoke(
        app,
        ["phase5", "verify", "--bundle-dir", str(bundle), "--archive", str(bad)],
    )
    assert r.exit_code == 1
    err = json.loads(r.stderr.strip())
    assert err["archive"]["error"] == "invalid_archive"


def test_phase5_verify_fails_when_manifest_optional_present_missing_on_disk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    bundle = tmp_path / "data" / "submissions" / "submission-package"
    bundle.mkdir(parents=True, exist_ok=True)
    for name in [
        "proposal-confirmed.json",
        "experiment-report.json",
        "evaluation-summary.json",
        "manuscript-draft.md",
    ]:
        (bundle / name).write_text("{}", encoding="utf-8")
    (bundle / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "files": [
                    "proposal-confirmed.json",
                    "experiment-report.json",
                    "evaluation-summary.json",
                    "manuscript-draft.md",
                ],
                "optional_present": ["manuscript-draft.pdf"],
            }
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(app, ["phase5", "verify", "--bundle-dir", str(bundle)])
    assert r.exit_code == 1
    err = json.loads(r.stderr.strip())
    assert err["manifest"]["ok"] is False
    assert err["manifest"]["optional_missing"] == ["manuscript-draft.pdf"]


def test_phase5_verify_fails_on_manifest_content_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    bundle = tmp_path / "data" / "submissions" / "submission-package"
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / "proposal-confirmed.json").write_text("{}", encoding="utf-8")
    (bundle / "experiment-report.json").write_text("{}", encoding="utf-8")
    (bundle / "evaluation-summary.json").write_text("{}", encoding="utf-8")
    (bundle / "manuscript-draft.md").write_text("# draft\n", encoding="utf-8")
    (bundle / "manifest.json").write_text(
        json.dumps({"files": ["proposal-confirmed.json"]}),
        encoding="utf-8",
    )
    r = CliRunner().invoke(app, ["phase5", "verify", "--bundle-dir", str(bundle)])
    assert r.exit_code == 1
    err = json.loads(r.stderr.strip())
    assert err["manifest"]["ok"] is False
    assert "experiment-report.json" in err["manifest"]["missing_from_manifest"]


def test_phase5_verify_release_report_optional_file_missing_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hashes for optional bundle files must fail verification when the file is absent."""

    monkeypatch.chdir(tmp_path)
    bundle = tmp_path / "data" / "submissions" / "submission-package"
    bundle.mkdir(parents=True, exist_ok=True)
    arch = tmp_path / "data" / "submissions" / "submission-package.tar.gz"
    for name in [
        "proposal-confirmed.json",
        "experiment-report.json",
        "evaluation-summary.json",
        "manuscript-draft.md",
    ]:
        (bundle / name).write_text("{}", encoding="utf-8")
    (bundle / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "files": [
                    "proposal-confirmed.json",
                    "experiment-report.json",
                    "evaluation-summary.json",
                    "manuscript-draft.md",
                ],
            }
        ),
        encoding="utf-8",
    )
    with tarfile.open(arch, "w:gz") as tf:
        tf.add(bundle, arcname=bundle.name)
    rr_path = tmp_path / "release-report.json"
    body = {
        "submission_bundle": str(bundle.resolve()),
        "submission_archive": str(arch.resolve()),
        "checksums": {
            "proposal-confirmed.json": hashlib.sha256(
                (bundle / "proposal-confirmed.json").read_bytes()
            ).hexdigest(),
            "experiment-report.json": hashlib.sha256(
                (bundle / "experiment-report.json").read_bytes()
            ).hexdigest(),
            "evaluation-summary.json": hashlib.sha256(
                (bundle / "evaluation-summary.json").read_bytes()
            ).hexdigest(),
            "manuscript-draft.md": hashlib.sha256(
                (bundle / "manuscript-draft.md").read_bytes()
            ).hexdigest(),
            "manifest.json": hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest(),
            "submission-package.tar.gz": hashlib.sha256(arch.read_bytes()).hexdigest(),
            "manuscript-draft.pdf": "a" * 64,
        },
    }
    rr_path.write_text(json.dumps(body, indent=2), encoding="utf-8")

    v = CliRunner().invoke(
        app,
        [
            "phase5",
            "verify",
            "--bundle-dir",
            str(bundle),
            "--archive",
            str(arch),
            "--release-report",
            str(rr_path),
        ],
    )
    assert v.exit_code == 1
    err = json.loads(v.stderr.strip())
    assert err["hashes"]["ok"] is False
    assert "manuscript-draft.pdf" in err["hashes"]["mismatch"]
    assert err["hashes"]["mismatch"]["manuscript-draft.pdf"]["actual"] == "MISSING_FILE"


def test_phase5_verify_with_release_report_checksum_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    prof = tmp_path / "user.json"
    prof.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "user": {"languages": ["en"]},
                "background": {"domains": [], "skills": [], "constraints": []},
                "hardware": {"device": "other"},
                "research_intent": {
                    "problem_statements": [],
                    "keywords": [],
                    "non_goals": [],
                    "risk_tolerance": "medium",
                },
            }
        ),
        encoding="utf-8",
    )
    rel = CliRunner().invoke(
        app,
        ["release", "--profile", str(prof), "--no-verify"],
        env={"AUTOPAPERS_PROVIDER": "local_pdf"},
    )
    assert rel.exit_code == 0
    r_out = json.loads(rel.stdout)
    rr = Path(r_out["release_report"])
    rr_doc = json.loads(rr.read_text(encoding="utf-8"))
    rr_doc["checksums"]["proposal-confirmed.json"] = "deadbeef"
    rr.write_text(json.dumps(rr_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    bundle = Path(rr_doc["submission_bundle"])
    archive = Path(rr_doc["submission_archive"])

    v = CliRunner().invoke(
        app,
        [
            "phase5",
            "verify",
            "--bundle-dir",
            str(bundle),
            "--archive",
            str(archive),
            "--release-report",
            str(rr),
        ],
    )
    assert v.exit_code == 1
    err = json.loads(v.stderr.strip())
    assert err["hashes"]["ok"] is False
    assert "proposal-confirmed.json" in err["hashes"]["mismatch"]


def test_phase5_verify_expect_optional_files_and_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    proposal = tmp_path / "data" / "proposals" / "proposal-confirmed.json"
    _confirmed(proposal)
    run = CliRunner().invoke(app, ["phase5", "run", "--proposal", str(proposal), "--no-archive"])
    assert run.exit_code == 0
    out = json.loads(run.stdout)
    bundle = Path(out["submission_bundle"])

    # Missing optional assets should fail when explicitly expected.
    v_missing = CliRunner().invoke(
        app,
        [
            "phase5",
            "verify",
            "--bundle-dir",
            str(bundle),
            "--expect-pdf",
            "--expect-bib",
            "--expect-artifacts",
        ],
    )
    assert v_missing.exit_code == 1
    err = json.loads(v_missing.stderr.strip())
    assert err["ok"] is False
    assert sorted(err["optional_missing"]) == [
        "artifacts/phase3",
        "manuscript-draft.pdf",
        "references.bib",
    ]

    # Create the expected optional assets; verification should pass.
    (bundle / "manuscript-draft.pdf").write_bytes(b"%PDF-1.4\n%mock\n")
    (bundle / "references.bib").write_text("@misc{a,title={t}}\n", encoding="utf-8")
    (bundle / "artifacts" / "phase3").mkdir(parents=True, exist_ok=True)
    (bundle / "artifacts" / "phase3" / "metrics.json").write_text("{}", encoding="utf-8")
    v_ok = CliRunner().invoke(
        app,
        [
            "phase5",
            "verify",
            "--bundle-dir",
            str(bundle),
            "--expect-pdf",
            "--expect-bib",
            "--expect-artifacts",
        ],
    )
    assert v_ok.exit_code == 0, v_ok.stdout + v_ok.stderr
    payload = json.loads(v_ok.stdout)
    assert payload["ok"] is True
