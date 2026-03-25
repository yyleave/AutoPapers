from __future__ import annotations

import json
import logging
import os
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


@app.command("status")
def cmd_status() -> None:
    """
    Print config, registered providers, and data directory counts (JSON).
    """

    typer.echo(json.dumps(build_status(), ensure_ascii=False, indent=2))


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
                },
                "env_override": {
                    "AUTOPAPERS_PROVIDER": os.environ.get("AUTOPAPERS_PROVIDER") is not None,
                    "AUTOPAPERS_LOG_LEVEL": os.environ.get("AUTOPAPERS_LOG_LEVEL") is not None,
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
        typer.echo("Provide exactly one of --path or --latest", err=True)
        raise typer.Exit(code=1)
    if latest is not None and latest not in ("search", "fetch", "any"):
        typer.echo("--latest must be one of: search, fetch, any", err=True)
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
        typer.echo("Error: --parse-fetched requires --fetch-first", err=True)
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
) -> None:
    """Export graph edges from a corpus snapshot as CSV (source,target,relation)."""

    paths = get_paths()
    _, data = _load_corpus_snapshot_for_cli(paths, snapshot)

    csv_text = snapshot_edges_to_csv(data)
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

    raw = json.loads(input.read_text(encoding="utf-8"))
    prop_schema = load_schema(_proposal_schema_path())
    validate_profile(profile=raw, schema=prop_schema)
    raw["status"] = "confirmed"
    validate_profile(profile=raw, schema=prop_schema)

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

    raw = json.loads(input.read_text(encoding="utf-8"))
    prop_schema = load_schema(_proposal_schema_path())
    validate_profile(profile=raw, schema=prop_schema)
    md = proposal_to_markdown(raw)
    out = output or input.with_suffix(".md")
    out.write_text(md, encoding="utf-8")
    typer.echo(str(out))
