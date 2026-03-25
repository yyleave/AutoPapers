from __future__ import annotations

import json
import logging
from pathlib import Path

import typer

from autopapers.config import get_paths, load_config
from autopapers.logging_utils import setup_logging
from autopapers.phase1.profile.extract import load_profile_from_json
from autopapers.phase1.profile.store import save_profile
from autopapers.phase1.profile.validate import load_schema, validate_profile
from autopapers.providers.base import PaperRef
from autopapers.providers.registry import ProviderRegistry

app = typer.Typer(add_completion=False, help="AutoPapers CLI (MVP scaffold)")
profile_app = typer.Typer(help="Phase 1: user profile utilities")
app.add_typer(profile_app, name="profile")

papers_app = typer.Typer(help="Phase 1: paper search/fetch (provider-based)")
app.add_typer(papers_app, name="papers")


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


@papers_app.command("search")
def papers_search(
    query: str = typer.Option(
        ...,
        "--query",
        "-q",
        help="Search query (or local path for local_pdf)",
    ),
    limit: int = typer.Option(5, "--limit", "-l", help="Max results"),
) -> None:
    """
    Search papers using configured provider.
    """

    provider_name, reg = _provider()
    p = reg.get(provider_name)
    refs = p.search(query=query, limit=limit)
    typer.echo(json.dumps([r.__dict__ for r in refs], ensure_ascii=False, indent=2))


@papers_app.command("fetch")
def papers_fetch(
    source: str = typer.Option(..., "--source", help="Source name (arxiv/local_pdf)"),
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
    dest_dir = paths.data_dir / "papers" / "pdfs"
    ref = PaperRef(source=source, id=pid, title=title, pdf_url=pdf_url)
    out = p.fetch_pdf(ref=ref, dest_dir=dest_dir)
    typer.echo(str(out))

