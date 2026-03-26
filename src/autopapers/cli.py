from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import typer

from autopapers import __version__ as autopapers_version
from autopapers.config import Paths, default_toml_path, get_paths, load_config
from autopapers.logging_utils import setup_logging
from autopapers.phase1.corpus_inspect import (
    load_corpus_snapshot_document,
    snapshot_edges_to_csv,
    snapshot_nodes_to_csv,
    summarize_corpus_snapshot,
)
from autopapers.phase1.corpus_snapshot import build_corpus_snapshot, write_corpus_snapshot
from autopapers.phase1.papers.metadata_pick import MetadataKind, newest_papers_metadata
from autopapers.phase1.papers.parse_pdf import extract_and_save_txt
from autopapers.phase1.papers.storage import (
    write_fetch_record,
    write_parse_manifest,
    write_search_record,
)
from autopapers.phase1.profile.extract import load_profile_from_json
from autopapers.phase1.profile.store import save_profile
from autopapers.phase1.profile.summary import compact_profile_view
from autopapers.phase1.profile.validate import load_schema, validate_profile
from autopapers.phase2.corpus_input import load_corpus_text_for_proposal
from autopapers.phase2.debate import merge_stub_to_proposal, run_debate_stub
from autopapers.phase2.proposal_markdown import proposal_to_markdown
from autopapers.providers.base import PaperRef
from autopapers.providers.registry import ProviderRegistry
from autopapers.status_report import build_status

app = typer.Typer(add_completion=False, help="AutoPapers CLI (MVP scaffold)")
profile_app = typer.Typer(help="Phase 1: user profile utilities")
app.add_typer(profile_app, name="profile")

papers_app = typer.Typer(help="Phase 1: paper search/fetch (provider-based)")
app.add_typer(papers_app, name="papers")

phase1_app = typer.Typer(help="Phase 1: profile → search → optional fetch")
app.add_typer(phase1_app, name="phase1")

proposal_app = typer.Typer(help="Phase 2: proposal draft / confirm (stub debate)")
app.add_typer(proposal_app, name="proposal")

corpus_app = typer.Typer(help="Phase 1: corpus / KG snapshot from metadata")
app.add_typer(corpus_app, name="corpus")

phase3_app = typer.Typer(help="Phase 3: sandbox execution scaffold")
app.add_typer(phase3_app, name="phase3")

phase4_app = typer.Typer(help="Phase 4: manuscript draft and submission scaffold")
app.add_typer(phase4_app, name="phase4")

phase5_app = typer.Typer(help="Phase 5: end-to-end orchestration scaffold")
app.add_typer(phase5_app, name="phase5")


@app.callback()
def _global_options() -> None:
    cfg = load_config()
    setup_logging(level=cfg.log_level)
    logging.getLogger(__name__).debug("Loaded config: %s", cfg)


def _provider() -> tuple[str, ProviderRegistry]:
    cfg = load_config()
    reg = ProviderRegistry.default()
    return cfg.provider, reg


def _schema_path() -> Path:
    return Path(__file__).resolve().parent / "schemas" / "user_profile.schema.json"


def _proposal_schema_path() -> Path:
    return Path(__file__).resolve().parent / "schemas" / "research_proposal.schema.json"


def _load_corpus_snapshot_for_cli(
    paths: Paths,
    snapshot: Path | None,
) -> tuple[Path, dict[str, Any]]:
    path = snapshot or (paths.kg_dir / "corpus-snapshot.json")
    if not path.is_file():
        typer.echo(
            json.dumps(
                {"error": "snapshot_not_found", "path": str(path.resolve())},
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1)
    try:
        data = load_corpus_snapshot_document(path)
    except json.JSONDecodeError as e:
        typer.echo(
            json.dumps(
                {
                    "error": "invalid_json",
                    "path": str(path.resolve()),
                    "detail": str(e),
                },
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1) from e
    except TypeError as e:
        typer.echo(
            json.dumps(
                {
                    "error": "expected_object",
                    "path": str(path.resolve()),
                    "detail": str(e),
                },
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1) from e
    return path, data


def _verify_submission_assets(
    *,
    bundle_dir: Path,
    archive: Path | None,
    expected_hashes: dict[str, str] | None = None,
) -> tuple[dict[str, object], bool]:
    required_files = [
        "proposal-confirmed.json",
        "experiment-report.json",
        "manuscript-draft.md",
        "manifest.json",
    ]
    missing = [name for name in required_files if not (bundle_dir / name).is_file()]
    ok = not missing

    payload: dict[str, object] = {
        "bundle_dir": str(bundle_dir.resolve()),
        "missing": missing,
    }
    manifest_check: dict[str, object] | None = None
    manifest_path = bundle_dir / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest_obj = json.loads(manifest_path.read_text(encoding="utf-8"))
            listed = manifest_obj.get("files")
            listed_set = set(listed) if isinstance(listed, list) else set()
            expected_set = {
                "proposal-confirmed.json",
                "experiment-report.json",
                "manuscript-draft.md",
            }
            manifest_missing = sorted(expected_set - listed_set)
            manifest_extra = sorted(listed_set - expected_set)
            manifest_check = {
                "ok": len(manifest_missing) == 0 and len(manifest_extra) == 0,
                "missing_from_manifest": manifest_missing,
                "unexpected_in_manifest": manifest_extra,
            }
            if not manifest_check["ok"]:
                ok = False
        except json.JSONDecodeError as e:
            manifest_check = {
                "ok": False,
                "error": "invalid_manifest_json",
                "detail": str(e),
            }
            ok = False
    else:
        manifest_check = {
            "ok": False,
            "error": "manifest_not_found",
        }
        ok = False
    payload["manifest"] = manifest_check
    if archive is not None:
        if not archive.is_file():
            payload["archive"] = {
                "ok": False,
                "error": "archive_not_found",
                "path": str(archive),
            }
            ok = False
        else:
            try:
                with tarfile.open(archive, "r:gz") as tf:
                    names = tf.getnames()
                present = {
                    name: any(n.endswith(f"submission-package/{name}") for n in names)
                    for name in required_files
                }
                a_missing = [k for k, v in present.items() if not v]
                payload["archive"] = {
                    "ok": len(a_missing) == 0,
                    "path": str(archive.resolve()),
                    "missing": a_missing,
                }
                if a_missing:
                    ok = False
            except tarfile.TarError as e:
                payload["archive"] = {
                    "ok": False,
                    "error": "invalid_archive",
                    "detail": str(e),
                    "path": str(archive),
                }
                ok = False
    if expected_hashes is not None:
        actual_hashes: dict[str, str] = {}
        hash_mismatch: dict[str, dict[str, str]] = {}
        file_map = {
            "proposal-confirmed.json": bundle_dir / "proposal-confirmed.json",
            "experiment-report.json": bundle_dir / "experiment-report.json",
            "manuscript-draft.md": bundle_dir / "manuscript-draft.md",
            "manifest.json": bundle_dir / "manifest.json",
        }
        if archive is not None and archive.is_file():
            file_map["submission-package.tar.gz"] = archive
        for name, path in file_map.items():
            if not path.is_file():
                continue
            h = hashlib.sha256(path.read_bytes()).hexdigest()
            actual_hashes[name] = h
            exp = expected_hashes.get(name)
            if exp is not None and exp != h:
                hash_mismatch[name] = {"expected": exp, "actual": h}
        payload["hashes"] = {
            "ok": len(hash_mismatch) == 0,
            "actual": actual_hashes,
            "mismatch": hash_mismatch,
        }
        if hash_mismatch:
            ok = False
    return payload, ok


@app.command("status")
def cmd_status() -> None:
    """
    Print config, registered providers, and data directory counts (JSON).
    """

    typer.echo(json.dumps(build_status(), ensure_ascii=False, indent=2))


@app.command("flow")
def cmd_flow() -> None:
    """
    Print high-level workflow stage completion and suggested next commands.
    """

    st = build_status()
    d = st.get("data", {})
    phase1_done = bool(d.get("metadata_json")) and bool(d.get("corpus_snapshot_exists"))
    phase2_done = bool(d.get("proposal_confirmed_exists"))
    phase3_done = bool(d.get("experiment_report_exists")) and bool(
        d.get("evaluation_summary_exists")
    )
    phase4_done = bool(d.get("manuscript_draft_exists")) and bool(d.get("submission_bundle_exists"))
    phase5_done = bool(d.get("submission_archive_exists"))
    release_done = bool(d.get("release_report_exists"))

    next_steps: list[str] = []
    if not phase1_done:
        next_steps.append(
            "uv run autopapers phase1 run --profile user_profile.json "
            "--fetch-first --parse-fetched"
        )
        next_steps.append("uv run autopapers corpus build --profile user_profile.json")
    elif not phase2_done:
        next_steps.append("uv run autopapers proposal draft --profile user_profile.json")
        next_steps.append(
            "uv run autopapers proposal confirm "
            "-i ./data/proposals/proposal-draft.json"
        )
    elif not phase3_done:
        next_steps.append(
            "uv run autopapers phase3 run "
            "--proposal ./data/proposals/proposal-confirmed.json"
        )
        next_steps.append(
            "uv run autopapers phase3 evaluate "
            "--report ./data/experiments/experiment-report.json"
        )
    elif not phase4_done:
        next_steps.append(
            "uv run autopapers phase4 draft "
            "--proposal ./data/proposals/proposal-confirmed.json "
            "--experiment ./data/experiments/experiment-report.json"
        )
        next_steps.append(
            "uv run autopapers phase4 bundle "
            "--proposal ./data/proposals/proposal-confirmed.json "
            "--experiment ./data/experiments/experiment-report.json "
            "--manuscript ./data/manuscripts/manuscript-draft.md"
        )
    elif not phase5_done:
        next_steps.append(
            "uv run autopapers phase4 submit "
            "--bundle-dir ./data/submissions/submission-package"
        )
        next_steps.append(
            "uv run autopapers phase5 verify "
            "--bundle-dir ./data/submissions/submission-package"
        )
    elif not release_done:
        next_steps.append("uv run autopapers release --profile user_profile.json")
    else:
        next_steps.append(
            "All stages completed. Re-run with "
            "`uv run autopapers resume` to refresh artifacts."
        )

    payload = {
        "phase1_data": phase1_done,
        "phase2_proposal": phase2_done,
        "phase3_experiment": phase3_done,
        "phase4_manuscript_bundle": phase4_done,
        "phase5_archive": phase5_done,
        "release_report": release_done,
        "next_steps": next_steps,
    }
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@app.command("version")
def cmd_version() -> None:
    """Print package version."""

    typer.echo(autopapers_version)


@app.command("config")
def cmd_config() -> None:
    """Print effective provider/log settings, TOML path, and data repo root (JSON)."""

    cfg = load_config()
    toml = default_toml_path()
    paths = get_paths()
    typer.echo(
        json.dumps(
            {
                "app_version": autopapers_version,
                "effective": {
                    "provider": cfg.provider,
                    "log_level": cfg.log_level,
                    "contact_email": cfg.contact_email,
                },
                "env_override": {
                    "AUTOPAPERS_PROVIDER": os.environ.get("AUTOPAPERS_PROVIDER") is not None,
                    "AUTOPAPERS_LOG_LEVEL": os.environ.get("AUTOPAPERS_LOG_LEVEL") is not None,
                    "AUTOPAPERS_CONTACT_EMAIL": os.environ.get("AUTOPAPERS_CONTACT_EMAIL")
                    is not None,
                    "AUTOPAPERS_REPO_ROOT": bool(
                        os.environ.get("AUTOPAPERS_REPO_ROOT", "").strip()
                    ),
                },
                "default_toml_path": str(toml),
                "default_toml_present": toml.is_file(),
                "data_repo_root": str(paths.repo_root.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("providers")
def cmd_providers() -> None:
    """List registered paper search/fetch providers (names + short description)."""

    reg = ProviderRegistry.default()
    rows: list[dict[str, str]] = []
    for name in sorted(reg.providers.keys()):
        prov = reg.providers[name]
        doc = (type(prov).__doc__ or "").strip()
        line = doc.split("\n", 1)[0].strip() if doc else ""
        rows.append({"name": name, "description": line})
    typer.echo(json.dumps({"providers": rows}, ensure_ascii=False, indent=2))


@app.command("run-all")
def cmd_run_all(
    profile: Path = typer.Option(
        ...,
        "--profile",
        "-p",
        exists=True,
        dir_okay=False,
        help="Validated user profile JSON",
    ),
    title: str = typer.Option("Research direction", "--title", "-t"),
    limit: int = typer.Option(3, "--limit", "-l", help="Search result count"),
    parse_max_pages: int = typer.Option(
        20,
        "--parse-max-pages",
        help="Max pages when parsing fetched PDF (0 = all pages)",
    ),
    full_flow: bool = typer.Option(
        False,
        "--full-flow",
        help="Also run phase3 execution stub and phase4 manuscript/bundle scaffold",
    ),
    archive: bool = typer.Option(
        True,
        "--archive/--no-archive",
        help="With --full-flow, also create submission-package.tar.gz archive",
    ),
) -> None:
    """
    One-shot MVP chain:
    profile -> phase1(search/fetch/parse first) -> corpus build
    -> proposal draft/confirm/export -> status.
    """

    schema_path = _schema_path()
    data = load_profile_from_json(profile)
    validate_profile(profile=data, schema=load_schema(schema_path))

    keywords = list(data.get("research_intent", {}).get("keywords") or [])
    problems = list(data.get("research_intent", {}).get("problem_statements") or [])
    if keywords:
        query = " ".join(str(k) for k in keywords[:8])
    elif problems:
        query = str(problems[0])
    else:
        query = "machine learning"

    provider_name, reg = _provider()
    prov = reg.get(provider_name)
    paths = get_paths()

    refs = prov.search(query=query, limit=limit)
    search_meta = write_search_record(paths, provider=provider_name, query=query, refs=refs)

    fetched_pdf: Path | None = None
    fetch_meta: Path | None = None
    parsed_txt: Path | None = None
    parse_manifest: Path | None = None
    if refs:
        r0 = refs[0]
        fetched_pdf = prov.fetch_pdf(ref=r0, dest_dir=paths.papers_pdfs_dir)
        fetch_meta = write_fetch_record(
            paths,
            source=r0.source,
            paper_id=r0.id,
            title=r0.title,
            pdf_path=fetched_pdf,
        )
        paths.papers_parsed_dir.mkdir(parents=True, exist_ok=True)
        parsed_txt = paths.papers_parsed_dir / f"{fetched_pdf.stem}.txt"
        page_limit = None if parse_max_pages == 0 else parse_max_pages
        text, pages_total, pages_read = extract_and_save_txt(
            fetched_pdf, parsed_txt, max_pages=page_limit
        )
        parse_manifest = write_parse_manifest(
            pdf_path=fetched_pdf,
            txt_path=parsed_txt,
            char_count=len(text),
            pages_total=pages_total,
            pages_read=pages_read,
            max_pages_config=parse_max_pages,
        )

    snap = build_corpus_snapshot(paths, profile_path=profile)
    snapshot_path = write_corpus_snapshot(paths, snap)

    prof_summary = json.dumps(
        data.get("research_intent", {}),
        ensure_ascii=False,
    )[:1200]
    corpus_summary, _ = load_corpus_text_for_proposal(paths, snapshot_path)
    debate = run_debate_stub(profile_summary=prof_summary, corpus_summary=corpus_summary)
    proposal = merge_stub_to_proposal(title=title, debate=debate, status="draft")
    prop_schema = load_schema(_proposal_schema_path())
    validate_profile(profile=proposal, schema=prop_schema)

    paths.proposals_dir.mkdir(parents=True, exist_ok=True)
    draft_path = paths.proposals_dir / "proposal-draft.json"
    draft_path.write_text(
        json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    proposal["status"] = "confirmed"
    validate_profile(profile=proposal, schema=prop_schema)
    confirmed_path = paths.proposals_dir / "proposal-confirmed.json"
    confirmed_path.write_text(
        json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md_path = confirmed_path.with_suffix(".md")
    md_path.write_text(proposal_to_markdown(proposal), encoding="utf-8")

    experiment_path: Path | None = None
    evaluation_summary_path: Path | None = None
    manuscript_path: Path | None = None
    bundle_dir: Path | None = None
    archive_path: Path | None = None
    if full_flow:
        exp_dir = paths.data_dir / "experiments"
        exp_dir.mkdir(parents=True, exist_ok=True)
        experiment_path = exp_dir / "experiment-report.json"
        report = {
            "schema_version": "0.1",
            "status": "completed_stub",
            "proposal_title": proposal.get("title"),
            "proposal_path": str(confirmed_path.resolve()),
            "summary": "Stub execution finished; replace with real sandbox later.",
            "metrics": {
                "primary_metric": "tbd",
                "value": None,
            },
        }
        experiment_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        evaluation_summary_path = exp_dir / "evaluation-summary.json"
        evaluation_summary_path.write_text(
            json.dumps(
                {
                    "schema_version": "0.1",
                    "status": "evaluated_stub",
                    "from_report": str(experiment_path.resolve()),
                    "proposal_title": proposal.get("title"),
                    "quality_gate": {
                        "reproducibility": "pass_stub",
                        "completeness": "pass_stub",
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        ms_dir = paths.data_dir / "manuscripts"
        ms_dir.mkdir(parents=True, exist_ok=True)
        manuscript_path = ms_dir / "manuscript-draft.md"
        manuscript_path.write_text(
            "\n".join(
                [
                    f"# {proposal.get('title', 'Research draft')}",
                    "",
                    "## Abstract",
                    "",
                    "TBD (generated from proposal + experiment report).",
                    "",
                    "## Problem",
                    "",
                    str(proposal.get("problem") or ""),
                    "",
                    "## Hypothesis",
                    "",
                    str(proposal.get("hypothesis") or ""),
                    "",
                    "## Experiment Snapshot",
                    "",
                    "- status: completed_stub",
                    "- primary_metric: tbd",
                    "",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        bundle_dir = paths.data_dir / "submissions" / "submission-package"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(confirmed_path, bundle_dir / "proposal-confirmed.json")
        shutil.copy2(experiment_path, bundle_dir / "experiment-report.json")
        shutil.copy2(manuscript_path, bundle_dir / "manuscript-draft.md")
        (bundle_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "0.1",
                    "files": [
                        "proposal-confirmed.json",
                        "experiment-report.json",
                        "manuscript-draft.md",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if archive:
            archive_path = paths.data_dir / "submissions" / "submission-package.tar.gz"
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            with tarfile.open(archive_path, "w:gz") as tf:
                tf.add(bundle_dir, arcname=bundle_dir.name)

    typer.echo(
        json.dumps(
            {
                "ok": True,
                "provider": provider_name,
                "query": query,
                "search_count": len(refs),
                "search_metadata": str(search_meta.resolve()),
                "fetch_metadata": str(fetch_meta.resolve()) if fetch_meta else None,
                "pdf": str(fetched_pdf.resolve()) if fetched_pdf else None,
                "parsed_txt": str(parsed_txt.resolve()) if parsed_txt else None,
                "parse_manifest": str(parse_manifest.resolve()) if parse_manifest else None,
                "corpus_snapshot": str(snapshot_path.resolve()),
                "proposal_draft": str(draft_path.resolve()),
                "proposal_confirmed": str(confirmed_path.resolve()),
                "proposal_markdown": str(md_path.resolve()),
                "experiment_report": str(experiment_path.resolve())
                if experiment_path
                else None,
                "evaluation_summary": str(evaluation_summary_path.resolve())
                if evaluation_summary_path
                else None,
                "manuscript_draft": str(manuscript_path.resolve())
                if manuscript_path
                else None,
                "submission_bundle": str(bundle_dir.resolve()) if bundle_dir else None,
                "submission_archive": str(archive_path.resolve()) if archive_path else None,
                "status": build_status(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("publish")
def cmd_publish(
    profile: Path = typer.Option(
        ...,
        "--profile",
        "-p",
        exists=True,
        dir_okay=False,
        help="Validated user profile JSON",
    ),
    title: str = typer.Option("Research direction", "--title", "-t"),
    limit: int = typer.Option(3, "--limit", "-l", help="Search result count"),
    parse_max_pages: int = typer.Option(
        20,
        "--parse-max-pages",
        help="Max pages when parsing fetched PDF (0 = all pages)",
    ),
) -> None:
    """One-command full pipeline to submission archive (MVP scaffold)."""

    cmd_run_all(
        profile=profile,
        title=title,
        limit=limit,
        parse_max_pages=parse_max_pages,
        full_flow=True,
        archive=True,
    )


@app.command("release")
def cmd_release(
    profile: Path = typer.Option(
        ...,
        "--profile",
        "-p",
        exists=True,
        dir_okay=False,
        help="Validated user profile JSON",
    ),
    title: str = typer.Option("Research direction", "--title", "-t"),
    limit: int = typer.Option(3, "--limit", "-l", help="Search result count"),
    parse_max_pages: int = typer.Option(
        20,
        "--parse-max-pages",
        help="Max pages when parsing fetched PDF (0 = all pages)",
    ),
    verify: bool = typer.Option(
        True,
        "--verify/--no-verify",
        help="Verify bundle/archive integrity and write release-report.json",
    ),
) -> None:
    """Run publish pipeline and emit release report for downstream delivery."""

    schema_path = _schema_path()
    data = load_profile_from_json(profile)
    validate_profile(profile=data, schema=load_schema(schema_path))

    provider_name, reg = _provider()
    prov = reg.get(provider_name)
    paths = get_paths()

    keywords = list(data.get("research_intent", {}).get("keywords") or [])
    problems = list(data.get("research_intent", {}).get("problem_statements") or [])
    if keywords:
        query = " ".join(str(k) for k in keywords[:8])
    elif problems:
        query = str(problems[0])
    else:
        query = "machine learning"

    refs = prov.search(query=query, limit=limit)
    search_meta = write_search_record(paths, provider=provider_name, query=query, refs=refs)

    fetched_pdf: Path | None = None
    fetch_meta: Path | None = None
    parsed_txt: Path | None = None
    parse_manifest: Path | None = None
    if refs:
        r0 = refs[0]
        fetched_pdf = prov.fetch_pdf(ref=r0, dest_dir=paths.papers_pdfs_dir)
        fetch_meta = write_fetch_record(
            paths,
            source=r0.source,
            paper_id=r0.id,
            title=r0.title,
            pdf_path=fetched_pdf,
        )
        paths.papers_parsed_dir.mkdir(parents=True, exist_ok=True)
        parsed_txt = paths.papers_parsed_dir / f"{fetched_pdf.stem}.txt"
        page_limit = None if parse_max_pages == 0 else parse_max_pages
        text, pages_total, pages_read = extract_and_save_txt(
            fetched_pdf, parsed_txt, max_pages=page_limit
        )
        parse_manifest = write_parse_manifest(
            pdf_path=fetched_pdf,
            txt_path=parsed_txt,
            char_count=len(text),
            pages_total=pages_total,
            pages_read=pages_read,
            max_pages_config=parse_max_pages,
        )

    snap = build_corpus_snapshot(paths, profile_path=profile)
    snapshot_path = write_corpus_snapshot(paths, snap)

    prof_summary = json.dumps(
        data.get("research_intent", {}),
        ensure_ascii=False,
    )[:1200]
    corpus_summary, _ = load_corpus_text_for_proposal(paths, snapshot_path)
    debate = run_debate_stub(profile_summary=prof_summary, corpus_summary=corpus_summary)
    proposal = merge_stub_to_proposal(title=title, debate=debate, status="draft")
    prop_schema = load_schema(_proposal_schema_path())
    validate_profile(profile=proposal, schema=prop_schema)

    paths.proposals_dir.mkdir(parents=True, exist_ok=True)
    draft_path = paths.proposals_dir / "proposal-draft.json"
    draft_path.write_text(
        json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    proposal["status"] = "confirmed"
    validate_profile(profile=proposal, schema=prop_schema)
    confirmed_path = paths.proposals_dir / "proposal-confirmed.json"
    confirmed_path.write_text(
        json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md_path = confirmed_path.with_suffix(".md")
    md_path.write_text(proposal_to_markdown(proposal), encoding="utf-8")

    exp_out = paths.data_dir / "experiments" / "experiment-report.json"
    eval_out = paths.data_dir / "experiments" / "evaluation-summary.json"
    ms_out = paths.data_dir / "manuscripts" / "manuscript-draft.md"
    bundle_out = paths.data_dir / "submissions" / "submission-package"
    archive_out = paths.data_dir / "submissions" / "submission-package.tar.gz"

    exp_out.parent.mkdir(parents=True, exist_ok=True)
    exp_out.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "status": "completed_stub",
                "proposal_title": proposal.get("title"),
                "proposal_path": str(confirmed_path.resolve()),
                "summary": "Stub execution finished; replace with real sandbox later.",
                "metrics": {"primary_metric": "tbd", "value": None},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    eval_out.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "status": "evaluated_stub",
                "from_report": str(exp_out.resolve()),
                "proposal_title": proposal.get("title"),
                "quality_gate": {
                    "reproducibility": "pass_stub",
                    "completeness": "pass_stub",
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    ms_out.parent.mkdir(parents=True, exist_ok=True)
    ms_out.write_text(
        "\n".join(
            [
                f"# {proposal.get('title', 'Research draft')}",
                "",
                "## Abstract",
                "",
                "TBD (generated from proposal + experiment report).",
                "",
                "## Problem",
                "",
                str(proposal.get("problem") or ""),
                "",
                "## Hypothesis",
                "",
                str(proposal.get("hypothesis") or ""),
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    bundle_out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(confirmed_path, bundle_out / "proposal-confirmed.json")
    shutil.copy2(exp_out, bundle_out / "experiment-report.json")
    shutil.copy2(ms_out, bundle_out / "manuscript-draft.md")
    (bundle_out / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "files": [
                    "proposal-confirmed.json",
                    "experiment-report.json",
                    "manuscript-draft.md",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if archive_out.is_file():
        archive_out.unlink()
    with tarfile.open(archive_out, "w:gz") as tf:
        tf.add(bundle_out, arcname=bundle_out.name)

    checksums = {
        "proposal-confirmed.json": hashlib.sha256(confirmed_path.read_bytes()).hexdigest(),
        "experiment-report.json": hashlib.sha256(exp_out.read_bytes()).hexdigest(),
        "evaluation-summary.json": hashlib.sha256(eval_out.read_bytes()).hexdigest(),
        "manuscript-draft.md": hashlib.sha256(ms_out.read_bytes()).hexdigest(),
        "manifest.json": hashlib.sha256((bundle_out / "manifest.json").read_bytes()).hexdigest(),
        "submission-package.tar.gz": hashlib.sha256(archive_out.read_bytes()).hexdigest(),
    }

    verify_payload: dict[str, object] | None = None
    verify_ok = True
    if verify:
        verify_payload, verify_ok = _verify_submission_assets(
            bundle_dir=bundle_out,
            archive=archive_out,
            expected_hashes=checksums,
        )

    release_report = {
        "schema_version": "0.1",
        "ok": verify_ok,
        "provider": provider_name,
        "query": query,
        "search_count": len(refs),
        "search_metadata": str(search_meta.resolve()),
        "fetch_metadata": str(fetch_meta.resolve()) if fetch_meta else None,
        "pdf": str(fetched_pdf.resolve()) if fetched_pdf else None,
        "parsed_txt": str(parsed_txt.resolve()) if parsed_txt else None,
        "parse_manifest": str(parse_manifest.resolve()) if parse_manifest else None,
        "proposal_confirmed": str(confirmed_path.resolve()),
        "proposal_markdown": str(md_path.resolve()),
        "experiment_report": str(exp_out.resolve()),
        "evaluation_summary": str(eval_out.resolve()),
        "manuscript_draft": str(ms_out.resolve()),
        "submission_bundle": str(bundle_out.resolve()),
        "submission_archive": str(archive_out.resolve()),
        "checksums": checksums,
        "verify": verify_payload,
    }
    report_path = paths.data_dir / "releases" / "release-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(release_report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    payload = {
        "ok": verify_ok,
        "release_report": str(report_path.resolve()),
        "verify": verify_payload,
        "status": build_status(),
    }
    if verify_ok:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2), err=True)
    raise typer.Exit(code=1)


@app.command("release-verify")
def cmd_release_verify(
    release_report: Path = typer.Option(
        Path("data/releases/release-report.json"),
        "--release-report",
        "-r",
        help="Release report JSON path generated by `autopapers release`",
    ),
) -> None:
    """Re-verify bundle/archive against checksums recorded in release report."""

    if not release_report.is_file():
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "release_report_not_found",
                    "path": str(release_report),
                },
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        rr = json.loads(release_report.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        typer.echo(
            json.dumps({"ok": False, "error": "invalid_json", "detail": str(e)}),
            err=True,
        )
        raise typer.Exit(code=1) from e

    bundle_raw = rr.get("submission_bundle")
    archive_raw = rr.get("submission_archive")
    checksums = rr.get("checksums")
    if not isinstance(bundle_raw, str) or not isinstance(archive_raw, str) or not isinstance(
        checksums, dict
    ):
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "invalid_release_report",
                    "detail": "submission_bundle/submission_archive/checksums are required",
                },
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1)

    detail, ok = _verify_submission_assets(
        bundle_dir=Path(bundle_raw),
        archive=Path(archive_raw),
        expected_hashes={str(k): str(v) for k, v in checksums.items()},
    )
    paths = get_paths()
    verify_report = {
        "schema_version": "0.1",
        "ok": ok,
        "release_report": str(release_report.resolve()),
        "detail": detail,
    }
    report_path = paths.data_dir / "releases" / "release-verify-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(verify_report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    payload = {
        "ok": ok,
        "release_verify_report": str(report_path.resolve()),
        "detail": detail,
        "status": build_status(),
    }
    if ok:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2), err=True)
    raise typer.Exit(code=1)


@app.command("resume")
def cmd_resume(
    profile: Path | None = typer.Option(
        None,
        "--profile",
        "-p",
        exists=True,
        dir_okay=False,
        help="Optional profile JSON; used when confirmed proposal is missing",
    ),
    verify: bool = typer.Option(
        True,
        "--verify/--no-verify",
        help="Verify bundle/archive integrity after resume run",
    ),
) -> None:
    """
    Resume pipeline from existing artifacts.

    Priority:
    1) if data/proposals/proposal-confirmed.json exists, continue from Phase3+
    2) else if --profile is provided, run full release pipeline from profile
    3) otherwise fail with actionable error
    """

    paths = get_paths()
    confirmed = paths.proposals_dir / "proposal-confirmed.json"
    if not confirmed.is_file():
        if profile is None:
            typer.echo(
                json.dumps(
                    {
                        "ok": False,
                        "error": "resume_unavailable",
                        "detail": "missing proposal-confirmed.json and no --profile provided",
                    },
                    indent=2,
                ),
                err=True,
            )
            raise typer.Exit(code=1)
        cmd_release(
            profile=profile,
            title="Research direction",
            limit=3,
            parse_max_pages=20,
            verify=verify,
        )
        return

    # Continue from confirmed proposal (Phase3+ artifacts)
    try:
        raw = json.loads(confirmed.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        typer.echo(
            json.dumps({"ok": False, "error": "invalid_json", "detail": str(e)}),
            err=True,
        )
        raise typer.Exit(code=1) from e
    prop_schema = load_schema(_proposal_schema_path())
    try:
        validate_profile(profile=raw, schema=prop_schema)
    except ValueError as e:
        typer.echo(
            json.dumps({"ok": False, "error": "validation", "detail": str(e)}, indent=2),
            err=True,
        )
        raise typer.Exit(code=1) from e
    if raw.get("status") != "confirmed":
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "invalid_status",
                    "detail": "proposal status must be confirmed",
                    "status": raw.get("status"),
                },
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1)

    exp_out = paths.data_dir / "experiments" / "experiment-report.json"
    eval_out = paths.data_dir / "experiments" / "evaluation-summary.json"
    ms_out = paths.data_dir / "manuscripts" / "manuscript-draft.md"
    bundle_out = paths.data_dir / "submissions" / "submission-package"
    archive_path = paths.data_dir / "submissions" / "submission-package.tar.gz"
    exp_out.parent.mkdir(parents=True, exist_ok=True)
    exp_out.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "status": "completed_stub",
                "proposal_title": raw.get("title"),
                "proposal_path": str(confirmed.resolve()),
                "summary": "Stub execution finished; replace with real sandbox later.",
                "metrics": {"primary_metric": "tbd", "value": None},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    eval_out.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "status": "evaluated_stub",
                "from_report": str(exp_out.resolve()),
                "proposal_title": raw.get("title"),
                "quality_gate": {
                    "reproducibility": "pass_stub",
                    "completeness": "pass_stub",
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    ms_out.parent.mkdir(parents=True, exist_ok=True)
    ms_out.write_text(
        "\n".join(
            [
                f"# {raw.get('title', 'Research draft')}",
                "",
                "## Abstract",
                "",
                "TBD (generated from proposal + experiment report).",
                "",
                "## Problem",
                "",
                str(raw.get("problem") or ""),
                "",
                "## Hypothesis",
                "",
                str(raw.get("hypothesis") or ""),
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    bundle_out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(confirmed, bundle_out / "proposal-confirmed.json")
    shutil.copy2(exp_out, bundle_out / "experiment-report.json")
    shutil.copy2(ms_out, bundle_out / "manuscript-draft.md")
    (bundle_out / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "files": [
                    "proposal-confirmed.json",
                    "experiment-report.json",
                    "manuscript-draft.md",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if archive_path.is_file():
        archive_path.unlink()
    with tarfile.open(archive_path, "w:gz") as tf:
        tf.add(bundle_out, arcname=bundle_out.name)

    verify_payload: dict[str, object] | None = None
    ok = True
    if verify:
        verify_payload, ok = _verify_submission_assets(
            bundle_dir=bundle_out,
            archive=archive_path,
        )

    payload: dict[str, object] = {
        "ok": ok,
        "resumed_from": str(confirmed.resolve()),
        "experiment_report": str(exp_out.resolve()),
        "evaluation_summary": str(eval_out.resolve()),
        "manuscript_draft": str(ms_out.resolve()),
        "submission_bundle": str(bundle_out.resolve()),
        "submission_archive": str(archive_path.resolve()) if archive_path.is_file() else None,
        "verify": verify_payload,
        "status": build_status(),
    }
    if ok:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2), err=True)
    raise typer.Exit(code=1)


@profile_app.command("init")
def profile_init(
    output: Path = typer.Option(
        Path("user_profile.json"),
        "--output",
        "-o",
        help="Output JSON path",
    ),
) -> None:
    """
    Create a minimal user profile JSON template.
    """

    template = {
        "schema_version": "0.1",
        "user": {"languages": ["zh", "en"]},
        "background": {"domains": [], "skills": [], "constraints": []},
        "hardware": {"device": "mac"},
        "research_intent": {
            "problem_statements": [],
            "keywords": [],
            "non_goals": [],
            "risk_tolerance": "medium",
        },
        "resources": {"datasets": [], "codebases": []},
        "preferences": {"output_formats": []},
    }

    output.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    typer.echo(f"Wrote template: {output}")


@profile_app.command("validate")
def profile_validate(
    input: Path = typer.Option(
        ...,
        "--input",
        "-i",
        exists=True,
        dir_okay=False,
        help="Profile JSON",
    ),
    schema: Path | None = typer.Option(None, "--schema", help="Override schema path"),
) -> None:
    """
    Validate a user profile against JSON Schema.
    """

    schema_path = schema or _schema_path()
    profile = load_profile_from_json(input)
    schema_obj = load_schema(schema_path)
    validate_profile(profile=profile, schema=schema_obj)
    typer.echo("OK")


@profile_app.command("save")
def profile_save(
    input: Path = typer.Option(
        ...,
        "--input",
        "-i",
        exists=True,
        dir_okay=False,
        help="Profile JSON",
    ),
    schema: Path | None = typer.Option(None, "--schema", help="Override schema path"),
) -> None:
    """
    Validate and save a user profile into ./data/profiles/.
    """

    schema_path = schema or _schema_path()
    profile = load_profile_from_json(input)
    schema_obj = load_schema(schema_path)
    validate_profile(profile=profile, schema=schema_obj)
    out = save_profile(profile=profile)
    typer.echo(f"Saved: {out}")


@profile_app.command("show")
def profile_show(
    input: Path = typer.Option(
        ...,
        "--input",
        "-i",
        exists=True,
        dir_okay=False,
        help="Profile JSON",
    ),
    schema: Path | None = typer.Option(None, "--schema", help="Override schema path"),
) -> None:
    """Validate profile and print a compact summary (keywords, intent, hardware)."""

    schema_path = schema or _schema_path()
    profile = load_profile_from_json(input)
    schema_obj = load_schema(schema_path)
    validate_profile(profile=profile, schema=schema_obj)
    view = compact_profile_view(profile)
    view["path"] = str(input.resolve())
    typer.echo(json.dumps(view, ensure_ascii=False, indent=2))


@papers_app.command("search")
def papers_search(
    query: str = typer.Option(
        ...,
        "--query",
        "-q",
        help="Search query (or local path for local_pdf)",
    ),
    limit: int = typer.Option(5, "--limit", "-l", help="Max results"),
    no_save: bool = typer.Option(False, "--no-save", help="Do not write metadata JSON"),
) -> None:
    """
    Search papers using configured provider; writes metadata under data/papers/metadata/.
    """

    provider_name, reg = _provider()
    p = reg.get(provider_name)
    refs = p.search(query=query, limit=limit)
    paths = get_paths()
    typer.echo(json.dumps([r.__dict__ for r in refs], ensure_ascii=False, indent=2))
    if not no_save:
        meta_path = write_search_record(
            paths, provider=provider_name, query=query, refs=refs
        )
        typer.echo(f"Wrote metadata: {meta_path}", err=True)


@papers_app.command("list-metadata")
def papers_list_metadata(
    limit: int = typer.Option(30, "--limit", "-l", help="Max files (newest first)"),
) -> None:
    """List JSON metadata files under data/papers/metadata/."""

    paths = get_paths()
    d = paths.papers_metadata_dir
    if not d.is_dir():
        typer.echo(
            json.dumps({"metadata_dir": str(d), "files": []}, ensure_ascii=False, indent=2)
        )
        return
    files = sorted(d.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[
        :limit
    ]
    rows: list[dict[str, object]] = []
    for f in files:
        st = f.stat()
        rows.append(
            {
                "name": f.name,
                "path": str(f.resolve()),
                "mtime_iso": datetime.fromtimestamp(st.st_mtime, tz=UTC).isoformat(),
            }
        )
    typer.echo(
        json.dumps({"metadata_dir": str(d), "files": rows}, ensure_ascii=False, indent=2)
    )


@papers_app.command("show-metadata")
def papers_show_metadata(
    path: Path | None = typer.Option(
        None,
        "--path",
        exists=True,
        dir_okay=False,
        help="Metadata JSON file",
    ),
    latest: str | None = typer.Option(
        None,
        "--latest",
        help="Print newest under metadata/: search | fetch | any",
    ),
) -> None:
    """Pretty-print one metadata JSON (--path or --latest, not both)."""

    if (path is None) == (latest is None):
        typer.echo(
            json.dumps(
                {
                    "error": "invalid_args",
                    "detail": "Provide exactly one of --path or --latest",
                },
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1)
    if latest is not None and latest not in ("search", "fetch", "any"):
        typer.echo(
            json.dumps(
                {
                    "error": "invalid_latest",
                    "detail": "--latest must be one of: search, fetch, any",
                    "latest": latest,
                },
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1)

    paths = get_paths()
    if path is None:
        picked = newest_papers_metadata(paths, kind=cast(MetadataKind, latest))
        if picked is None:
            typer.echo(
                json.dumps({"error": "no_metadata_files", "kind": latest}, indent=2),
                err=True,
            )
            raise typer.Exit(code=1)
        path = picked

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        typer.echo(
            json.dumps(
                {
                    "error": "invalid_json",
                    "path": str(path.resolve()),
                    "detail": str(e),
                },
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1) from e

    typer.echo(
        json.dumps({"file": str(path.resolve()), "data": data}, ensure_ascii=False, indent=2)
    )


@papers_app.command("fetch")
def papers_fetch(
    source: str = typer.Option(
        ...,
        "--source",
        help="Source: arxiv, openalex, crossref, local_pdf, aminer",
    ),
    pid: str = typer.Option(..., "--id", help="Paper id (arXiv id or file stem)"),
    title: str | None = typer.Option(None, "--title", help="Optional title"),
    pdf_url: str | None = typer.Option(None, "--pdf-url", help="Optional pdf url or local path"),
) -> None:
    """
    Fetch a PDF for a given paper reference (saved under ./data/papers/pdfs/).
    """

    reg = ProviderRegistry.default()
    p = reg.get(source)
    paths = get_paths()
    dest_dir = paths.papers_pdfs_dir
    ref = PaperRef(source=source, id=pid, title=title, pdf_url=pdf_url)
    out = p.fetch_pdf(ref=ref, dest_dir=dest_dir)
    meta_path = write_fetch_record(
        paths,
        source=source,
        paper_id=pid,
        title=title,
        pdf_path=out,
    )
    typer.echo(str(out))
    typer.echo(f"Wrote metadata: {meta_path}", err=True)


@papers_app.command("parse")
def papers_parse(
    input: Path = typer.Option(
        ...,
        "--input",
        "-i",
        exists=True,
        dir_okay=False,
        help="PDF file path",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output text path (default: data/papers/parsed/<stem>.txt)",
    ),
    max_pages: int = typer.Option(
        20,
        "--max-pages",
        help="Max pages to extract (default 20); use 0 for all pages",
    ),
    write_manifest: bool = typer.Option(
        False,
        "--write-manifest",
        help="Write <output-stem>.manifest.json beside the .txt",
    ),
) -> None:
    """
    Extract text from PDF into data/papers/parsed/ (uses pypdf).
    """

    paths = get_paths()
    paths.papers_parsed_dir.mkdir(parents=True, exist_ok=True)
    out = output or (paths.papers_parsed_dir / f"{input.stem}.txt")
    limit = None if max_pages == 0 else max_pages
    text, pages_total, pages_read = extract_and_save_txt(
        input, out, max_pages=limit
    )
    typer.echo(str(out))
    if write_manifest:
        meta = write_parse_manifest(
            pdf_path=input,
            txt_path=out,
            char_count=len(text),
            pages_total=pages_total,
            pages_read=pages_read,
            max_pages_config=max_pages,
        )
        typer.echo(f"Wrote manifest: {meta}", err=True)


@papers_app.command("parse-batch")
def papers_parse_batch(
    input_dir: Path = typer.Option(
        ...,
        "--input-dir",
        exists=True,
        file_okay=False,
        help="Directory containing PDFs",
    ),
    pattern: str = typer.Option("*.pdf", "--pattern", help="Glob relative to input-dir"),
    max_pages: int = typer.Option(
        20,
        "--max-pages",
        help="Max pages per file (default 20); 0 = all pages",
    ),
    write_manifest: bool = typer.Option(
        False,
        "--write-manifest",
        help="Write a .manifest.json beside each .txt",
    ),
) -> None:
    """
    Extract text from every PDF matching pattern under input-dir into data/papers/parsed/.
    """

    paths = get_paths()
    paths.papers_parsed_dir.mkdir(parents=True, exist_ok=True)
    limit = None if max_pages == 0 else max_pages
    candidates = sorted(input_dir.glob(pattern))
    parsed = 0
    errors: list[str] = []
    for pdf in candidates:
        if not pdf.is_file():
            continue
        out = paths.papers_parsed_dir / f"{pdf.stem}.txt"
        try:
            text, pages_total, pages_read = extract_and_save_txt(
                pdf, out, max_pages=limit
            )
            parsed += 1
            typer.echo(str(out))
            if write_manifest:
                meta = write_parse_manifest(
                    pdf_path=pdf,
                    txt_path=out,
                    char_count=len(text),
                    pages_total=pages_total,
                    pages_read=pages_read,
                    max_pages_config=max_pages,
                )
                typer.echo(f"manifest: {meta}", err=True)
        except Exception as e:  # noqa: BLE001 — batch should continue
            errors.append(f"{pdf.name}: {e}")
            typer.echo(f"skip {pdf.name}: {e}", err=True)
    summary = {"parsed": parsed, "candidates": len(candidates), "errors": errors}
    typer.echo(json.dumps(summary, ensure_ascii=False, indent=2), err=True)


@phase1_app.command("run")
def phase1_run(
    profile: Path = typer.Option(
        ...,
        "--profile",
        "-p",
        exists=True,
        dir_okay=False,
        help="Validated user profile JSON",
    ),
    limit: int = typer.Option(3, "--limit", "-l", help="Search result count"),
    fetch_first: bool = typer.Option(
        False,
        "--fetch-first",
        help="Fetch PDF for the first search hit",
    ),
    parse_fetched: bool = typer.Option(
        False,
        "--parse-fetched",
        help="After --fetch-first, extract text + .manifest.json under data/papers/parsed/",
    ),
    parse_max_pages: int = typer.Option(
        20,
        "--parse-max-pages",
        help="With --parse-fetched: max pages (0 = all)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate profile and print planned query/provider only (no search or writes)",
    ),
) -> None:
    """
    Load profile → build query from keywords/problem_statements → search → optional fetch #1.
    """

    if parse_fetched and not fetch_first:
        typer.echo(
            json.dumps(
                {
                    "error": "invalid_args",
                    "detail": "--parse-fetched requires --fetch-first",
                },
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1)

    schema_path = _schema_path()
    data = load_profile_from_json(profile)
    validate_profile(profile=data, schema=load_schema(schema_path))

    keywords = list(data.get("research_intent", {}).get("keywords") or [])
    problems = list(data.get("research_intent", {}).get("problem_statements") or [])
    if keywords:
        query = " ".join(str(k) for k in keywords[:8])
    elif problems:
        query = str(problems[0])
    else:
        query = "machine learning"

    provider_name, reg = _provider()
    if dry_run:
        typer.echo(
            json.dumps(
                {
                    "dry_run": True,
                    "profile": str(profile.resolve()),
                    "query": query,
                    "provider": provider_name,
                    "limit": limit,
                    "fetch_first": fetch_first,
                    "parse_fetched": parse_fetched,
                    "parse_max_pages": parse_max_pages,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    prov = reg.get(provider_name)
    paths = get_paths()
    refs = prov.search(query=query, limit=limit)
    meta = write_search_record(paths, provider=provider_name, query=query, refs=refs)
    typer.echo(json.dumps({"metadata_file": str(meta), "count": len(refs)}, indent=2))

    if fetch_first and refs:
        r0 = refs[0]
        pdf_path = prov.fetch_pdf(ref=r0, dest_dir=paths.papers_pdfs_dir)
        fmeta = write_fetch_record(
            paths,
            source=r0.source,
            paper_id=r0.id,
            title=r0.title,
            pdf_path=pdf_path,
        )
        payload: dict[str, object] = {
            "pdf": str(pdf_path),
            "fetch_metadata": str(fmeta),
        }
        if parse_fetched:
            paths.papers_parsed_dir.mkdir(parents=True, exist_ok=True)
            out_txt = paths.papers_parsed_dir / f"{pdf_path.stem}.txt"
            page_limit = None if parse_max_pages == 0 else parse_max_pages
            text, pages_total, pages_read = extract_and_save_txt(
                pdf_path, out_txt, max_pages=page_limit
            )
            pmeta = write_parse_manifest(
                pdf_path=pdf_path,
                txt_path=out_txt,
                char_count=len(text),
                pages_total=pages_total,
                pages_read=pages_read,
                max_pages_config=parse_max_pages,
            )
            payload["parsed_txt"] = str(out_txt)
            payload["parse_manifest"] = str(pmeta)
        typer.echo(json.dumps(payload, indent=2))


@corpus_app.command("build")
def corpus_build(
    profile: Path | None = typer.Option(
        None,
        "--profile",
        "-p",
        exists=True,
        dir_okay=False,
        help="Optional profile JSON to add User/Keyword nodes",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Compute snapshot in memory and print summary only; do not write JSON",
    ),
) -> None:
    """
    Build data/kg/corpus-snapshot.json from metadata, fetch records, and parse manifests.

    Incorporates data/papers/metadata/*.json and data/papers/parsed/*.manifest.json.
    """

    paths = get_paths()
    snap = build_corpus_snapshot(paths, profile_path=profile)
    if dry_run:
        summary = summarize_corpus_snapshot(snap)
        summary["dry_run"] = True
        summary["would_write"] = str((paths.kg_dir / "corpus-snapshot.json").resolve())
        typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    out = write_corpus_snapshot(paths, snap)
    typer.echo(str(out))


@corpus_app.command("info")
def corpus_info(
    snapshot: Path | None = typer.Option(
        None,
        "--snapshot",
        "-s",
        exists=True,
        dir_okay=False,
        help="Snapshot JSON (default: data/kg/corpus-snapshot.json)",
    ),
) -> None:
    """Print node/edge summaries for an existing corpus snapshot (no rebuild)."""

    paths = get_paths()
    path, data = _load_corpus_snapshot_for_cli(paths, snapshot)
    summary = summarize_corpus_snapshot(data)
    summary["snapshot"] = str(path.resolve())
    typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))


@corpus_app.command("export-edges")
def corpus_export_edges(
    snapshot: Path | None = typer.Option(
        None,
        "--snapshot",
        "-s",
        exists=True,
        dir_okay=False,
        help="Snapshot JSON (default: data/kg/corpus-snapshot.json)",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Write CSV here (default: print to stdout)",
    ),
    relation: str | None = typer.Option(
        None,
        "--relation",
        "-r",
        help="Only edges with this relation (e.g. FETCHED, SEARCH_HIT)",
    ),
) -> None:
    """Export graph edges from a corpus snapshot as CSV (source,target,relation)."""

    paths = get_paths()
    _, data = _load_corpus_snapshot_for_cli(paths, snapshot)

    csv_text = snapshot_edges_to_csv(data, relation_filter=relation)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(csv_text, encoding="utf-8")
        typer.echo(str(output.resolve()))
    else:
        typer.echo(csv_text.rstrip("\n"))


@corpus_app.command("export-nodes")
def corpus_export_nodes(
    snapshot: Path | None = typer.Option(
        None,
        "--snapshot",
        "-s",
        exists=True,
        dir_okay=False,
        help="Snapshot JSON (default: data/kg/corpus-snapshot.json)",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Write CSV here (default: print to stdout)",
    ),
    node_type: str | None = typer.Option(
        None,
        "--type",
        "-t",
        help="Only nodes with this type (e.g. Paper, TextExtract)",
    ),
) -> None:
    """Export graph nodes from a corpus snapshot as CSV (id,type,label)."""

    paths = get_paths()
    _, data = _load_corpus_snapshot_for_cli(paths, snapshot)
    csv_text = snapshot_nodes_to_csv(data, type_filter=node_type)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(csv_text, encoding="utf-8")
        typer.echo(str(output.resolve()))
    else:
        typer.echo(csv_text.rstrip("\n"))


@proposal_app.command("draft")
def proposal_draft(
    profile: Path = typer.Option(
        ...,
        "--profile",
        "-p",
        exists=True,
        dir_okay=False,
    ),
    corpus: Path | None = typer.Option(
        None,
        "--corpus",
        "-c",
        exists=True,
        dir_okay=False,
        help=(
            "Corpus path. JSON with a snapshot 'nodes' list is expanded to paper lines "
            "and TextExtract .txt snippets. "
            "If omitted, uses data/kg/corpus-snapshot.json when present."
        ),
    ),
    title: str = typer.Option("Research direction", "--title", "-t"),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Draft JSON path (default: data/proposals/proposal-draft.json)",
    ),
) -> None:
    """
    Stub debate + write draft proposal JSON under data/proposals/.
    """

    schema_path = _schema_path()
    prof = load_profile_from_json(profile)
    validate_profile(profile=prof, schema=load_schema(schema_path))
    prof_summary = json.dumps(
        prof.get("research_intent", {}),
        ensure_ascii=False,
    )[:1200]

    paths = get_paths()
    corpus_summary, corpus_used = load_corpus_text_for_proposal(paths, corpus)
    if corpus_used:
        typer.echo(f"Using corpus: {corpus_used}", err=True)
    elif not corpus_summary:
        typer.echo(
            "No corpus supplied and data/kg/corpus-snapshot.json missing; "
            "run: uv run autopapers corpus build",
            err=True,
        )

    debate = run_debate_stub(profile_summary=prof_summary, corpus_summary=corpus_summary)
    proposal = merge_stub_to_proposal(title=title, debate=debate, status="draft")

    prop_schema = load_schema(_proposal_schema_path())
    validate_profile(profile=proposal, schema=prop_schema)

    paths.proposals_dir.mkdir(parents=True, exist_ok=True)
    out = output or (paths.proposals_dir / "proposal-draft.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    typer.echo(str(out))


@proposal_app.command("validate")
def proposal_validate(
    input: Path = typer.Option(
        ...,
        "--input",
        "-i",
        exists=True,
        dir_okay=False,
        help="Proposal JSON to check",
    ),
) -> None:
    """Validate proposal JSON against schema (read-only; no confirm / no export)."""

    try:
        raw = json.loads(input.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        typer.echo(
            json.dumps({"ok": False, "error": "invalid_json", "detail": str(e)}),
            err=True,
        )
        raise typer.Exit(code=1) from e

    prop_schema = load_schema(_proposal_schema_path())
    try:
        validate_profile(profile=raw, schema=prop_schema)
    except ValueError as e:
        typer.echo(
            json.dumps({"ok": False, "error": "validation", "detail": str(e)}, indent=2),
            err=True,
        )
        raise typer.Exit(code=1) from e

    typer.echo(
        json.dumps(
            {
                "ok": True,
                "path": str(input.resolve()),
                "title": raw.get("title"),
                "status": raw.get("status"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@proposal_app.command("confirm")
def proposal_confirm(
    input: Path = typer.Option(
        ...,
        "--input",
        "-i",
        exists=True,
        dir_okay=False,
        help="Draft proposal JSON",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Confirmed JSON path (default: data/proposals/proposal-confirmed.json)",
    ),
) -> None:
    """
    Validate proposal schema and mark status confirmed; writes proposal-confirmed.json.
    """

    try:
        raw = json.loads(input.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        typer.echo(
            json.dumps({"ok": False, "error": "invalid_json", "detail": str(e)}),
            err=True,
        )
        raise typer.Exit(code=1) from e

    prop_schema = load_schema(_proposal_schema_path())
    try:
        validate_profile(profile=raw, schema=prop_schema)
        raw["status"] = "confirmed"
        validate_profile(profile=raw, schema=prop_schema)
    except ValueError as e:
        typer.echo(
            json.dumps({"ok": False, "error": "validation", "detail": str(e)}, indent=2),
            err=True,
        )
        raise typer.Exit(code=1) from e

    paths = get_paths()
    paths.proposals_dir.mkdir(parents=True, exist_ok=True)
    out = output or (paths.proposals_dir / "proposal-confirmed.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    typer.echo(str(out))


@proposal_app.command("export")
def proposal_export(
    input: Path = typer.Option(
        ...,
        "--input",
        "-i",
        exists=True,
        dir_okay=False,
        help="Proposal JSON (draft or confirmed)",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Markdown path (default: same stem as input with .md)",
    ),
) -> None:
    """
    Validate proposal JSON and write a readable Markdown summary (for notes / sharing).
    """

    try:
        raw = json.loads(input.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        typer.echo(
            json.dumps({"ok": False, "error": "invalid_json", "detail": str(e)}),
            err=True,
        )
        raise typer.Exit(code=1) from e

    prop_schema = load_schema(_proposal_schema_path())
    try:
        validate_profile(profile=raw, schema=prop_schema)
    except ValueError as e:
        typer.echo(
            json.dumps({"ok": False, "error": "validation", "detail": str(e)}, indent=2),
            err=True,
        )
        raise typer.Exit(code=1) from e

    md = proposal_to_markdown(raw)
    out = output or input.with_suffix(".md")
    out.write_text(md, encoding="utf-8")
    typer.echo(str(out))


@phase3_app.command("run")
def phase3_run(
    proposal: Path = typer.Option(
        Path("data/proposals/proposal-confirmed.json"),
        "--proposal",
        "-p",
        exists=True,
        dir_okay=False,
        help="Confirmed proposal JSON path",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Experiment report JSON path (default: data/experiments/experiment-report.json)",
    ),
) -> None:
    """Phase3 stub: generate an execution report from confirmed proposal."""

    try:
        raw = json.loads(proposal.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        typer.echo(
            json.dumps({"ok": False, "error": "invalid_json", "detail": str(e)}),
            err=True,
        )
        raise typer.Exit(code=1) from e

    prop_schema = load_schema(_proposal_schema_path())
    try:
        validate_profile(profile=raw, schema=prop_schema)
    except ValueError as e:
        typer.echo(
            json.dumps({"ok": False, "error": "validation", "detail": str(e)}, indent=2),
            err=True,
        )
        raise typer.Exit(code=1) from e

    if raw.get("status") != "confirmed":
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "invalid_status",
                    "detail": "proposal status must be confirmed",
                    "status": raw.get("status"),
                },
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1)

    paths = get_paths()
    out = output or (paths.data_dir / "experiments" / "experiment-report.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": "0.1",
        "status": "completed_stub",
        "proposal_title": raw.get("title"),
        "proposal_path": str(proposal.resolve()),
        "summary": "Stub execution finished; replace with real sandbox later.",
        "metrics": {"primary_metric": "tbd", "value": None},
    }
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    typer.echo(str(out.resolve()))


@phase3_app.command("evaluate")
def phase3_evaluate(
    report: Path = typer.Option(
        Path("data/experiments/experiment-report.json"),
        "--report",
        "-r",
        exists=True,
        dir_okay=False,
        help="Experiment report JSON path",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Evaluation summary JSON path (default: data/experiments/evaluation-summary.json)",
    ),
) -> None:
    """Phase3 stub: derive an evaluation summary from experiment report."""

    try:
        rep = json.loads(report.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        typer.echo(
            json.dumps({"ok": False, "error": "invalid_json", "detail": str(e)}),
            err=True,
        )
        raise typer.Exit(code=1) from e

    paths = get_paths()
    out = output or (paths.data_dir / "experiments" / "evaluation-summary.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": "0.1",
        "status": "evaluated_stub",
        "from_report": str(report.resolve()),
        "proposal_title": rep.get("proposal_title"),
        "quality_gate": {
            "reproducibility": "pass_stub",
            "completeness": "pass_stub",
        },
    }
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    typer.echo(str(out.resolve()))


@phase4_app.command("draft")
def phase4_draft(
    proposal: Path = typer.Option(
        Path("data/proposals/proposal-confirmed.json"),
        "--proposal",
        "-p",
        exists=True,
        dir_okay=False,
        help="Confirmed proposal JSON path",
    ),
    experiment: Path = typer.Option(
        Path("data/experiments/experiment-report.json"),
        "--experiment",
        "-e",
        exists=True,
        dir_okay=False,
        help="Experiment report JSON path",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Markdown path (default: data/manuscripts/manuscript-draft.md)",
    ),
) -> None:
    """Phase4 stub: render a manuscript draft from proposal + experiment report."""

    try:
        prop = json.loads(proposal.read_text(encoding="utf-8"))
        exp = json.loads(experiment.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        typer.echo(
            json.dumps({"ok": False, "error": "invalid_json", "detail": str(e)}),
            err=True,
        )
        raise typer.Exit(code=1) from e

    paths = get_paths()
    out = output or (paths.data_dir / "manuscripts" / "manuscript-draft.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    md = "\n".join(
        [
            f"# {prop.get('title', 'Research draft')}",
            "",
            "## Abstract",
            "",
            "TBD (generated from proposal + experiment report).",
            "",
            "## Problem",
            "",
            str(prop.get("problem") or ""),
            "",
            "## Hypothesis",
            "",
            str(prop.get("hypothesis") or ""),
            "",
            "## Experiment Snapshot",
            "",
            f"- status: {exp.get('status', '')}",
            f"- primary_metric: {exp.get('metrics', {}).get('primary_metric', 'tbd')}",
            f"- value: {exp.get('metrics', {}).get('value', '')}",
            "",
        ]
    )
    out.write_text(md + "\n", encoding="utf-8")
    typer.echo(str(out.resolve()))


@phase4_app.command("bundle")
def phase4_bundle(
    proposal: Path = typer.Option(
        Path("data/proposals/proposal-confirmed.json"),
        "--proposal",
        "-p",
        exists=True,
        dir_okay=False,
        help="Confirmed proposal JSON path",
    ),
    experiment: Path = typer.Option(
        Path("data/experiments/experiment-report.json"),
        "--experiment",
        "-e",
        exists=True,
        dir_okay=False,
        help="Experiment report JSON path",
    ),
    manuscript: Path = typer.Option(
        Path("data/manuscripts/manuscript-draft.md"),
        "--manuscript",
        "-m",
        exists=True,
        dir_okay=False,
        help="Manuscript markdown path",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Bundle directory (default: data/submissions/submission-package)",
    ),
) -> None:
    """Phase4 stub: package proposal/experiment/manuscript into one submission folder."""

    paths = get_paths()
    out_dir = output_dir or (paths.data_dir / "submissions" / "submission-package")
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(proposal, out_dir / "proposal-confirmed.json")
    shutil.copy2(experiment, out_dir / "experiment-report.json")
    shutil.copy2(manuscript, out_dir / "manuscript-draft.md")
    (out_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "files": [
                    "proposal-confirmed.json",
                    "experiment-report.json",
                    "manuscript-draft.md",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    typer.echo(str(out_dir.resolve()))


@phase4_app.command("submit")
def phase4_submit(
    bundle_dir: Path = typer.Option(
        Path("data/submissions/submission-package"),
        "--bundle-dir",
        "-b",
        exists=True,
        file_okay=False,
        help="Submission package directory generated by phase4 bundle",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output archive path (default: data/submissions/submission-package.tar.gz)",
    ),
) -> None:
    """Phase4 scaffold: archive submission package as .tar.gz for handoff/upload."""

    required = [
        bundle_dir / "proposal-confirmed.json",
        bundle_dir / "experiment-report.json",
        bundle_dir / "manuscript-draft.md",
        bundle_dir / "manifest.json",
    ]
    missing = [str(p.name) for p in required if not p.is_file()]
    if missing:
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "bundle_incomplete",
                    "detail": "bundle is missing required files",
                    "missing": missing,
                },
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1)

    paths = get_paths()
    out = output or (paths.data_dir / "submissions" / "submission-package.tar.gz")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out, "w:gz") as tf:
        tf.add(bundle_dir, arcname=bundle_dir.name)
    typer.echo(str(out.resolve()))


@phase5_app.command("run")
def phase5_run(
    proposal: Path = typer.Option(
        Path("data/proposals/proposal-confirmed.json"),
        "--proposal",
        "-p",
        exists=True,
        dir_okay=False,
        help="Confirmed proposal JSON path",
    ),
    full_status: bool = typer.Option(
        True,
        "--full-status/--no-full-status",
        help="Include full status payload in output JSON",
    ),
    archive: bool = typer.Option(
        True,
        "--archive/--no-archive",
        help="Also create submission .tar.gz archive after bundle generation",
    ),
) -> None:
    """Phase5 scaffold: orchestrate phase3->phase4 draft->phase4 bundle."""

    paths = get_paths()

    exp_out = paths.data_dir / "experiments" / "experiment-report.json"
    eval_out = paths.data_dir / "experiments" / "evaluation-summary.json"
    ms_out = paths.data_dir / "manuscripts" / "manuscript-draft.md"
    bundle_out = paths.data_dir / "submissions" / "submission-package"
    archive_out = paths.data_dir / "submissions" / "submission-package.tar.gz"

    try:
        raw = json.loads(proposal.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        typer.echo(
            json.dumps({"ok": False, "error": "invalid_json", "detail": str(e)}),
            err=True,
        )
        raise typer.Exit(code=1) from e

    prop_schema = load_schema(_proposal_schema_path())
    try:
        validate_profile(profile=raw, schema=prop_schema)
    except ValueError as e:
        typer.echo(
            json.dumps({"ok": False, "error": "validation", "detail": str(e)}, indent=2),
            err=True,
        )
        raise typer.Exit(code=1) from e

    if raw.get("status") != "confirmed":
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "invalid_status",
                    "detail": "proposal status must be confirmed",
                    "status": raw.get("status"),
                },
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1)

    exp_out.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": "0.1",
        "status": "completed_stub",
        "proposal_title": raw.get("title"),
        "proposal_path": str(proposal.resolve()),
        "summary": "Stub execution finished; replace with real sandbox later.",
        "metrics": {"primary_metric": "tbd", "value": None},
    }
    exp_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    eval_out.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "status": "evaluated_stub",
                "from_report": str(exp_out.resolve()),
                "proposal_title": raw.get("title"),
                "quality_gate": {
                    "reproducibility": "pass_stub",
                    "completeness": "pass_stub",
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    ms_out.parent.mkdir(parents=True, exist_ok=True)
    ms_out.write_text(
        "\n".join(
            [
                f"# {raw.get('title', 'Research draft')}",
                "",
                "## Abstract",
                "",
                "TBD (generated from proposal + experiment report).",
                "",
                "## Problem",
                "",
                str(raw.get("problem") or ""),
                "",
                "## Hypothesis",
                "",
                str(raw.get("hypothesis") or ""),
                "",
                "## Experiment Snapshot",
                "",
                "- status: completed_stub",
                "- primary_metric: tbd",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    bundle_out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(proposal, bundle_out / "proposal-confirmed.json")
    shutil.copy2(exp_out, bundle_out / "experiment-report.json")
    shutil.copy2(ms_out, bundle_out / "manuscript-draft.md")
    (bundle_out / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "files": [
                    "proposal-confirmed.json",
                    "experiment-report.json",
                    "manuscript-draft.md",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if archive_out.is_file():
        archive_out.unlink()
    if archive:
        with tarfile.open(archive_out, "w:gz") as tf:
            tf.add(bundle_out, arcname=bundle_out.name)

    payload: dict[str, object] = {
        "ok": True,
        "proposal_confirmed": str(proposal.resolve()),
        "experiment_report": str(exp_out.resolve()),
        "evaluation_summary": str(eval_out.resolve()),
        "manuscript_draft": str(ms_out.resolve()),
        "submission_bundle": str(bundle_out.resolve()),
        "submission_archive": str(archive_out.resolve()) if archive else None,
    }
    if full_status:
        payload["status"] = build_status()
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@phase5_app.command("verify")
def phase5_verify(
    bundle_dir: Path = typer.Option(
        Path("data/submissions/submission-package"),
        "--bundle-dir",
        "-b",
        exists=True,
        file_okay=False,
        help="Submission package directory to validate",
    ),
    archive: Path | None = typer.Option(
        Path("data/submissions/submission-package.tar.gz"),
        "--archive",
        "-a",
        help="Optional submission archive to validate against bundle",
    ),
    release_report: Path | None = typer.Option(
        None,
        "--release-report",
        "-r",
        exists=True,
        dir_okay=False,
        help="Optional release-report.json to verify checksums",
    ),
) -> None:
    """Validate submission package completeness and optional archive consistency."""
    expected_hashes: dict[str, str] | None = None
    if release_report is not None:
        try:
            rr = json.loads(release_report.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            typer.echo(
                json.dumps({"ok": False, "error": "invalid_json", "detail": str(e)}),
                err=True,
            )
            raise typer.Exit(code=1) from e
        hashes = rr.get("checksums")
        if not isinstance(hashes, dict):
            typer.echo(
                json.dumps(
                    {
                        "ok": False,
                        "error": "invalid_release_report",
                        "detail": "release report missing checksums object",
                    },
                    indent=2,
                ),
                err=True,
            )
            raise typer.Exit(code=1)
        expected_hashes = {str(k): str(v) for k, v in hashes.items()}
    detail, ok = _verify_submission_assets(
        bundle_dir=bundle_dir,
        archive=archive,
        expected_hashes=expected_hashes,
    )
    payload: dict[str, object] = {"ok": ok, **detail}

    if ok:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2), err=True)
    raise typer.Exit(code=1)
