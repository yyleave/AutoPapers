from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import typer

from autopapers import __version__ as autopapers_version
from autopapers.config import Paths, default_toml_path, get_paths, load_config
from autopapers.env_check import build_doctor_payload, build_llm_backend_diagnostics
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
from autopapers.phase2.debate import merge_stub_to_proposal, run_debate
from autopapers.phase2.proposal_markdown import proposal_to_markdown
from autopapers.providers.base import PaperRef, Provider
from autopapers.providers.registry import ProviderRegistry
from autopapers.repo_paths import ensure_legacy_api_on_path
from autopapers.status_report import build_status

app = typer.Typer(
    add_completion=False,
    help="AutoPapers CLI (MVP scaffold)",
    epilog=(
        "Quick: status, flow, doctor, workspace-init, run-all, publish, release, "
        "release-verify, resume; orchestration: phase5 run | phase5 verify. "
        "Groups: profile, papers, phase1, corpus, proposal, phase3, phase4, phase5."
    ),
)
profile_app = typer.Typer(help="Phase 1: user profile utilities")
app.add_typer(profile_app, name="profile")

papers_app = typer.Typer(help="Phase 1: paper search/fetch (provider-based)")
app.add_typer(papers_app, name="papers")

phase1_app = typer.Typer(help="Phase 1: profile → search → optional fetch")
app.add_typer(phase1_app, name="phase1")

proposal_app = typer.Typer(help="Phase 2: proposal draft / confirm (LLM debate)")
app.add_typer(proposal_app, name="proposal")

corpus_app = typer.Typer(help="Phase 1: corpus / KG snapshot from metadata")
app.add_typer(corpus_app, name="corpus")

phase3_app = typer.Typer(help="Phase 3: thin execution planning scaffold")
app.add_typer(phase3_app, name="phase3")

phase4_app = typer.Typer(help="Phase 4: grounded manuscript and submission scaffold")
app.add_typer(phase4_app, name="phase4")

phase5_app = typer.Typer(help="Phase 5: end-to-end orchestration scaffold")
app.add_typer(phase5_app, name="phase5")

# Written by ``workspace-init`` when no configs/default.toml exists under the data repo root.
_WORKSPACE_DEFAULT_TOML = (
    'log_level = "INFO"\n'
    'provider = "arxiv"\n'
    "\n"
    "# Optional: contact_email for config/status only (HTTP polite UA uses AUTOPAPERS_MAILTO).\n"
    '# contact_email = "you@example.com"\n'
)


@app.callback()
def _global_options() -> None:
    cfg = load_config()
    setup_logging(level=cfg.log_level)
    logging.getLogger(__name__).debug("Loaded config: %s", cfg)


def _provider() -> tuple[str, ProviderRegistry]:
    cfg = load_config()
    reg = ProviderRegistry.default()
    return cfg.provider, reg


def _search_provider_for_cli(
    provider_cli: str | None,
) -> tuple[str, Provider, ProviderRegistry, str]:
    """
    Resolve paper search provider: optional CLI override vs config default.

    Returns:
        effective_name, provider instance, registry, config_default_name

    Raises:
        typer.Exit: unknown provider name (after printing JSON error).
    """

    cfg_name, reg = _provider()
    if isinstance(provider_cli, str) and provider_cli.strip():
        eff = provider_cli.strip().lower()
    else:
        eff = cfg_name
    try:
        prov = reg.get(eff)
    except KeyError:
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "unknown_provider",
                    "provider": eff,
                    "available": sorted(reg.providers.keys()),
                },
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1) from None
    return eff, prov, reg, cfg_name


def _schema_path() -> Path:
    return Path(__file__).resolve().parent / "schemas" / "user_profile.schema.json"


def _proposal_schema_path() -> Path:
    return Path(__file__).resolve().parent / "schemas" / "research_proposal.schema.json"


def _merge_expect_flags_from_checksums(
    checksums: dict[str, str] | None,
    *,
    expect_artifacts: bool,
    expect_pdf: bool,
    expect_bib: bool,
) -> tuple[bool, bool, bool]:
    """Treat keys present in a release checksum map as assets that must exist on disk."""

    if not checksums:
        return expect_artifacts, expect_pdf, expect_bib
    return (
        expect_artifacts or "artifacts/phase3" in checksums,
        expect_pdf or "manuscript-draft.pdf" in checksums,
        expect_bib or "references.bib" in checksums,
    )


def _collect_optional_present_for_bundle(
    bundle_dir: Path,
    *,
    include_pdf: bool,
    include_bib: bool,
    include_artifacts: bool,
) -> list[str]:
    """Relative paths materialized under bundle_dir when include_* flags were set."""

    present: list[str] = []
    if include_pdf and (bundle_dir / "manuscript-draft.pdf").is_file():
        present.append("manuscript-draft.pdf")
    if include_bib and (bundle_dir / "references.bib").is_file():
        present.append("references.bib")
    if include_artifacts and (bundle_dir / "artifacts" / "phase3").is_dir():
        present.append("artifacts/phase3")
    return sorted(present)


def _write_submission_manifest(
    bundle_dir: Path,
    *,
    include_pdf: bool = False,
    include_bib: bool = False,
    include_artifacts: bool = False,
) -> None:
    """Write manifest.json with required file list and optional_present when applicable."""

    optional_present = _collect_optional_present_for_bundle(
        bundle_dir,
        include_pdf=include_pdf,
        include_bib=include_bib,
        include_artifacts=include_artifacts,
    )
    doc: dict[str, object] = {
        "schema_version": "0.2",
        "autopapers_version": autopapers_version,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "files": [
            "proposal-confirmed.json",
            "experiment-report.json",
            "evaluation-summary.json",
            "manuscript-draft.md",
        ],
    }
    if optional_present:
        doc["optional_present"] = optional_present
    (bundle_dir / "manifest.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _tar_lists_bundle_path(*, tar_names: list[str], arc_prefix: str, rel: str) -> bool:
    """Whether .tar.gz members include bundle-relative path rel (file or artifacts/phase3 tree)."""

    rel = rel.strip().strip("/")
    if not rel:
        return False
    if rel == "artifacts/phase3":
        base = f"{arc_prefix}/{rel}"
        return any(n == base or n.startswith(base + "/") for n in tar_names)
    return any(n.endswith(f"{arc_prefix}/{rel}") for n in tar_names)


def _write_phase3_experiment_scaffold(
    proposal_path: Path,
    *,
    output_dir: Path | None = None,
) -> dict[str, str]:
    """
    Write experiment_spec.json + experiment.py for local Phase 3 runs.

    Raises:
        ValueError: invalid JSON, schema validation failure, or detail prefixed with
        ``invalid_json:``.
    """

    try:
        raw = json.loads(proposal_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid_json: {e}") from e

    prop_schema = load_schema(_proposal_schema_path())
    try:
        validate_profile(profile=raw, schema=prop_schema)
    except ValueError as e:
        raise ValueError(str(e)) from e

    paths = get_paths()
    out_dir = output_dir or (paths.runs_dir / "phase3")
    out_dir.mkdir(parents=True, exist_ok=True)

    spec = {
        "schema_version": "0.1",
        "proposal_title": raw.get("title"),
        "proposal_path": str(proposal_path.resolve()),
        "task": "token_coverage_on_corpus_snapshot",
        "inputs": {
            "corpus_snapshot": "data/kg/corpus-snapshot.json",
        },
        "outputs": {
            "metrics_json": "metrics.json",
            "summary_txt": "summary.txt",
        },
    }
    (out_dir / "experiment_spec.json").write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    code = (
        "import json\n"
        "import re\n"
        "import sys\n"
        "from pathlib import Path\n"
        "\n"
        "def tokenize(text: str) -> set[str]:\n"
        "    return set(re.findall(r\"[A-Za-z0-9]{3,}|[一-龥]{2,}\", text.lower()))\n"
        "\n"
        "def main() -> int:\n"
        "    corpus_snapshot = Path(sys.argv[1])\n"
        "    query_text = sys.argv[2]\n"
        "    out_dir = Path(sys.argv[3])\n"
        "    out_dir.mkdir(parents=True, exist_ok=True)\n"
        "\n"
        "    try:\n"
        "        corpus_doc = json.loads(corpus_snapshot.read_text(encoding='utf-8'))\n"
        "    except Exception as exc:\n"
        "        (out_dir / 'metrics.json').write_text(\n"
        "            json.dumps({'ok': False, 'error': str(exc)}),\n"
        "            encoding='utf-8',\n"
        "        )\n"
        "        return 2\n"
        "\n"
        "    nodes = corpus_doc.get('nodes') if isinstance(corpus_doc, dict) else []\n"
        "    nodes = nodes if isinstance(nodes, list) else []\n"
        "    query_tokens = tokenize(query_text)\n"
        "    corpus_tokens = set()\n"
        "    for n in nodes:\n"
        "        if not isinstance(n, dict):\n"
        "            continue\n"
        "        if str(n.get('type','')) == 'Paper':\n"
        "            lab = n.get('label')\n"
        "            if isinstance(lab, str) and lab.strip():\n"
        "                corpus_tokens |= tokenize(lab)\n"
        "        if str(n.get('type','')) == 'TextExtract':\n"
        "            outp = n.get('output_txt')\n"
        "            if not outp:\n"
        "                continue\n"
        "            p = Path(str(outp))\n"
        "            if p.is_file():\n"
        "                snippet = p.read_text(\n"
        "                    encoding='utf-8',\n"
        "                    errors='replace',\n"
        "                )[:20000]\n"
        "                corpus_tokens |= tokenize(snippet)\n"
        "\n"
        "    coverage = (\n"
        "        (len(query_tokens & corpus_tokens) / float(len(query_tokens)))\n"
        "        if query_tokens\n"
        "        else 0.0\n"
        "    )\n"
        "    matched = sorted(\n"
        "        list(query_tokens & corpus_tokens),\n"
        "        key=lambda s: (-len(s), s),\n"
        "    )[:10]\n"
        "    metrics = {\n"
        "        'ok': True,\n"
        "        'primary_metric': 'evidence_coverage',\n"
        "        'value': coverage,\n"
        "        'matched_tokens_sample': matched,\n"
        "    }\n"
        "    (out_dir / 'metrics.json').write_text(\n"
        "        json.dumps(metrics, ensure_ascii=False, indent=2) + '\\n',\n"
        "        encoding='utf-8',\n"
        "    )\n"
        "    (out_dir / 'summary.txt').write_text(\n"
        "        f\"evidence_coverage={coverage:.3f}\\n\",\n"
        "        encoding='utf-8',\n"
        "    )\n"
        "    print(json.dumps(metrics, ensure_ascii=False))\n"
        "    return 0\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n"
    )
    (out_dir / "experiment.py").write_text(code, encoding="utf-8")
    return {
        "output_dir": str(out_dir.resolve()),
        "spec": str((out_dir / "experiment_spec.json").resolve()),
        "runner": str((out_dir / "experiment.py").resolve()),
    }


def _write_phase3_evaluator_script(
    *,
    proposal: Path,
    output: Path | None = None,
) -> Path:
    """
    Write ``evaluator.py`` (token-coverage helper for Docker/local). Same validation as
    ``proposal generate-evaluator`` CLI.

    Raises:
        ValueError: invalid JSON (prefix ``invalid_json:``) or schema validation message.
    """

    try:
        raw = json.loads(proposal.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid_json: {e}") from e

    prop_schema = load_schema(_proposal_schema_path())
    try:
        validate_profile(profile=raw, schema=prop_schema)
    except ValueError as e:
        raise ValueError(str(e)) from e

    paths = get_paths()
    out = output or (paths.runs_dir / "phase3" / "evaluator.py")
    out.parent.mkdir(parents=True, exist_ok=True)
    code = (
        "import json\n"
        "import re\n"
        "import sys\n"
        "from pathlib import Path\n"
        "\n"
        "corpus_path = Path(sys.argv[1])\n"
        "query_text = sys.argv[2]\n"
        "max_extracts = int(sys.argv[3])\n"
        "max_chars_per_extract = int(sys.argv[4])\n"
        "max_tokens_sample = int(sys.argv[5])\n"
        "\n"
        "def tokenize(text: str) -> set[str]:\n"
        "    return set(re.findall(r\"[A-Za-z0-9]{3,}|[一-龥]{2,}\", text.lower()))\n"
        "\n"
        "try:\n"
        "    corpus_doc = json.loads(corpus_path.read_text(encoding=\"utf-8\"))\n"
        "    nodes = corpus_doc.get(\"nodes\") if isinstance(corpus_doc, dict) else None\n"
        "    if not isinstance(nodes, list):\n"
        "        nodes = []\n"
        "\n"
        "    query_tokens = tokenize(query_text)\n"
        "    corpus_tokens = set()\n"
        "    extracts_read = 0\n"
        "\n"
        "    for n in nodes:\n"
        "        if not isinstance(n, dict):\n"
        "            continue\n"
        "        typ = str(n.get(\"type\", \"\"))\n"
        "        if typ == \"Paper\":\n"
        "            lab = n.get(\"label\")\n"
        "            if isinstance(lab, str) and lab.strip():\n"
        "                corpus_tokens |= tokenize(lab)\n"
        "        elif typ == \"TextExtract\":\n"
        "            if extracts_read >= max_extracts:\n"
        "                continue\n"
        "            outp = n.get(\"output_txt\")\n"
        "            if not outp:\n"
        "                continue\n"
        "            out_path = Path(str(outp))\n"
        "            if not out_path.is_file():\n"
        "                continue\n"
        "            try:\n"
        "                snippet = out_path.read_text(\n"
        "                    encoding=\"utf-8\",\n"
        "                    errors=\"replace\",\n"
        "                )[:max_chars_per_extract]\n"
        "            except OSError:\n"
        "                continue\n"
        "            corpus_tokens |= tokenize(snippet)\n"
        "            extracts_read += 1\n"
        "\n"
        "    corpus_token_count = len(corpus_tokens)\n"
        "    query_token_count = len(query_tokens)\n"
        "    coverage = (\n"
        "        (len(query_tokens & corpus_tokens) / float(len(query_tokens)))\n"
        "        if query_tokens\n"
        "        else 0.0\n"
        "    )\n"
        "    matched = list(query_tokens & corpus_tokens)\n"
        "    matched_tokens_sample = sorted(\n"
        "        matched,\n"
        "        key=lambda s: (-len(s), s),\n"
        "    )[:max_tokens_sample]\n"
        "\n"
        "    result = {\n"
        "        \"executed\": True,\n"
        "        \"query_token_count\": query_token_count,\n"
        "        \"corpus_token_count\": corpus_token_count,\n"
        "        \"coverage\": coverage,\n"
        "        \"matched_tokens_sample\": matched_tokens_sample,\n"
        "    }\n"
        "except Exception as exc:\n"
        "    result = {\"executed\": False, \"error\": str(exc)}\n"
        "\n"
        "print(json.dumps(result, ensure_ascii=False))\n"
    )
    out.write_text(code, encoding="utf-8")
    return out


def _phase3_local_experiment_report(
    *,
    proposal: Path,
    raw: dict[str, Any],
    paths: Paths,
) -> dict[str, Any]:
    """Run local ``experiment.py`` when available; otherwise return a planned experiment report."""

    exp_py = paths.runs_dir / "phase3" / "experiment.py"
    exp_spec = paths.runs_dir / "phase3" / "experiment_spec.json"
    if exp_py.is_file() and (paths.kg_dir / "corpus-snapshot.json").is_file():
        query_text = "\n".join(
            [
                str(raw.get("problem") or ""),
                str(raw.get("hypothesis") or ""),
            ]
        )[:4000]
        art_dir = paths.artifacts_dir / "phase3" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        art_dir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [
                sys.executable,
                str(exp_py),
                str((paths.kg_dir / "corpus-snapshot.json").resolve()),
                query_text,
                str(art_dir.resolve()),
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
        parsed: dict[str, Any] = {}
        try:
            out_text = (proc.stdout or "").strip()
            parsed = json.loads(out_text) if out_text else {}
        except json.JSONDecodeError:
            parsed = {}
        report = _build_experiment_report(proposal=raw, proposal_path=proposal)
        report["status"] = "executed" if proc.returncode == 0 else "failed"
        report["metrics"] = {
            "primary_metric": "evidence_coverage",
            "value": parsed.get("value"),
        }
        report["artifacts"] = {
            "dir": str(art_dir.resolve()),
            "metrics_json": str((art_dir / "metrics.json").resolve())
            if (art_dir / "metrics.json").is_file()
            else None,
            "summary_txt": str((art_dir / "summary.txt").resolve())
            if (art_dir / "summary.txt").is_file()
            else None,
        }
        report["execution"] = {
            "mode": "local_experiment_py",
            "spec": str(exp_spec.resolve()) if exp_spec.is_file() else None,
            "runner": str(exp_py.resolve()),
            "logs": {
                "returncode": proc.returncode,
                "stderr_tail": (proc.stderr or "")[-1000:],
            },
        }
        return report
    return _build_experiment_report(proposal=raw, proposal_path=proposal)


def _experiment_report_for_full_pipeline(
    *,
    paths: Paths,
    confirmed_path: Path,
    proposal: dict[str, Any],
) -> dict[str, Any]:
    """
    Phase 3 report for one-shot pipelines: run local ``experiment.py`` when corpus snapshot
    exists; otherwise return a planned report. Ensures experiment scaffold exists when needed.

    Raises:
        ValueError: forwarded from :func:`_write_phase3_experiment_scaffold`.
    """

    corpus_snap = paths.kg_dir / "corpus-snapshot.json"
    if not corpus_snap.is_file():
        return _build_experiment_report(proposal=proposal, proposal_path=confirmed_path)
    exp_py = paths.runs_dir / "phase3" / "experiment.py"
    if not exp_py.is_file():
        _write_phase3_experiment_scaffold(confirmed_path)
    return _phase3_local_experiment_report(
        proposal=confirmed_path,
        raw=proposal,
        paths=paths,
    )


def _build_experiment_report(*, proposal: dict[str, Any], proposal_path: Path) -> dict[str, Any]:
    """
    Phase 3 execution (lightweight, deterministic):
    - Load corpus-snapshot.json (when present)
    - Execute a lightweight evidence scoring routine via local subprocess
      (simulates the Phase 3 execution sandbox in a safe/offline way)
    """

    contributions = [str(x) for x in (proposal.get("contributions") or []) if str(x).strip()]
    baselines = [str(x) for x in (proposal.get("baselines") or []) if str(x).strip()]
    steps: list[dict[str, str]] = [
        {
            "id": "s1",
            "name": "PrepareDatasetAndSplits",
            "detail": "Collect/prepare data and define train/valid/test protocol.",
        },
        {
            "id": "s2",
            "name": "ImplementMethodFromHypothesis",
            "detail": str(proposal.get("hypothesis") or "")[:240] or "Implement proposed method.",
        },
        {
            "id": "s3",
            "name": "RunBaselines",
            "detail": "; ".join(baselines[:3]) or "Run standard baselines in the target field.",
        },
        {
            "id": "s4",
            "name": "EvaluateAndAblate",
            "detail": "Report primary metric and at least one ablation/sensitivity check.",
        },
    ]

    paths = get_paths()
    corpus_snapshot_path = paths.kg_dir / "corpus-snapshot.json"
    executed = False
    corpus_token_count = None
    query_token_count = None
    coverage = None
    matched_tokens: list[str] = []
    exec_logs: dict[str, Any] = {}

    if corpus_snapshot_path.is_file():
        query_text = "\n".join(
            [
                str(proposal.get("problem") or ""),
                str(proposal.get("hypothesis") or ""),
            ]
        ).strip()[:4000]

        max_extracts = 8
        max_chars_per_extract = 20_000
        max_tokens_sample = 10

        # Token coverage scoring. The inner code is intentionally self-contained
        # to simulate an isolated Phase 3 runner.
        code = """
import json
import re
import sys
from pathlib import Path

corpus_path = Path(sys.argv[1])
query_text = sys.argv[2]
max_extracts = int(sys.argv[3])
max_chars_per_extract = int(sys.argv[4])
max_tokens_sample = int(sys.argv[5])

def tokenize(text: str) -> set[str]:
    # Support both alnum words and simple CJK runs.
    return set(re.findall(r"[A-Za-z0-9]{3,}|[一-龥]{2,}", text.lower()))

try:
    corpus_doc = json.loads(corpus_path.read_text(encoding="utf-8"))
    nodes = corpus_doc.get("nodes") if isinstance(corpus_doc, dict) else None
    if not isinstance(nodes, list):
        nodes = []

    query_tokens = tokenize(query_text)
    corpus_tokens = set()
    extracts_read = 0

    for n in nodes:
        if not isinstance(n, dict):
            continue
        typ = str(n.get("type", ""))
        if typ == "Paper":
            lab = n.get("label")
            if isinstance(lab, str) and lab.strip():
                corpus_tokens |= tokenize(lab)
        elif typ == "TextExtract":
            if extracts_read >= max_extracts:
                continue
            outp = n.get("output_txt")
            if not outp:
                continue
            out_path = Path(str(outp))
            if not out_path.is_file():
                continue
            try:
                snippet = out_path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )[:max_chars_per_extract]
            except OSError:
                continue
            corpus_tokens |= tokenize(snippet)
            extracts_read += 1

    corpus_token_count = len(corpus_tokens)
    query_token_count = len(query_tokens)
    if query_tokens:
        coverage = len(query_tokens & corpus_tokens) / float(len(query_tokens))
    else:
        coverage = 0.0

    matched = list(query_tokens & corpus_tokens)
    matched_tokens_sample = sorted(matched, key=lambda s: (-len(s), s))[:max_tokens_sample]

    result = {
        "executed": True,
        "query_token_count": query_token_count,
        "corpus_token_count": corpus_token_count,
        "coverage": coverage,
        "matched_tokens_sample": matched_tokens_sample,
    }
except Exception as exc:
    result = {"executed": False, "error": str(exc)}

print(json.dumps(result, ensure_ascii=False))
"""

        script_dir = paths.runs_dir / "phase3"
        script_dir.mkdir(parents=True, exist_ok=True)
        default_script = script_dir / "evaluator.py"
        if default_script.is_file():
            script_path = default_script
        else:
            ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            script_path = script_dir / f"token_coverage_evaluator_{ts}.py"
            script_path.write_text(code, encoding="utf-8")

        exec_logs["evaluator_script"] = str(script_path.resolve())

        proc = subprocess.run(
            [
                sys.executable,
                str(script_path),
                str(corpus_snapshot_path),
                query_text,
                str(max_extracts),
                str(max_chars_per_extract),
                str(max_tokens_sample),
            ],
            capture_output=True,
            text=True,
            timeout=45,
        )
        exec_logs["returncode"] = proc.returncode
        exec_logs["stderr_tail"] = (proc.stderr or "")[-1000:]
        stdout = (proc.stdout or "").strip()
        try:
            parsed = json.loads(stdout) if stdout else {}
        except json.JSONDecodeError:
            parsed = {"executed": False, "error": "invalid_subprocess_json"}

        executed = bool(parsed.get("executed"))
        if executed:
            query_token_count = parsed.get("query_token_count")
            corpus_token_count = parsed.get("corpus_token_count")
            coverage = parsed.get("coverage")
            matched_tokens = parsed.get("matched_tokens_sample") or []

    metric_value: float | None
    primary_metric: str
    if executed and isinstance(coverage, (int, float)):
        primary_metric = "evidence_coverage"
        metric_value = float(coverage)
    else:
        primary_metric = "evidence_coverage"
        metric_value = None

    # Keep enough information for Phase 4 grounded writing.
    return {
        "schema_version": "0.2",
        "status": "executed" if executed else "planned",
        "proposal_title": proposal.get("title"),
        "proposal_path": str(proposal_path.resolve()),
        "corpus_snapshot_path": str(corpus_snapshot_path.resolve())
        if corpus_snapshot_path.is_file()
        else None,
        "summary": "Executed lightweight evidence coverage scoring against corpus snapshot."
        if executed
        else "Thin execution plan generated; corpus snapshot not available.",
        "experiment_plan": {
            "objective": str(proposal.get("problem") or "")[:260],
            "steps": steps,
            "expected_contributions": contributions[:3],
        },
        "metrics": {"primary_metric": primary_metric, "value": metric_value},
        "execution": {
            "mode": "subprocess_token_coverage",
            "query_token_count": query_token_count,
            "corpus_token_count": corpus_token_count,
            "matched_tokens_sample": matched_tokens,
            "logs": exec_logs,
        },
    }


def _build_evaluation_summary(*, report: dict[str, Any], report_path: Path) -> dict[str, Any]:
    plan = report.get("experiment_plan") if isinstance(report.get("experiment_plan"), dict) else {}
    primary = (report.get("metrics") or {}).get("primary_metric")
    value = (report.get("metrics") or {}).get("value")
    try:
        v = float(value) if value is not None else None
    except (TypeError, ValueError):
        v = None

    threshold = float(os.environ.get("AUTOPAPERS_COVERAGE_THRESHOLD", "0.1"))
    passed = v is not None and v >= threshold
    execution = report.get("execution") if isinstance(report.get("execution"), dict) else {}
    logs = execution.get("logs") if isinstance(execution.get("logs"), dict) else {}
    returncode = logs.get("returncode")
    stderr_tail = logs.get("stderr_tail")

    return {
        "schema_version": "0.2",
        "status": "evaluated",
        "from_report": str(report_path.resolve()),
        "proposal_title": report.get("proposal_title"),
        "quality_gate": {
            "reproducibility": "pass_deterministic",
            "completeness": (
                "pass_executed"
                if report.get("status") == "executed"
                else "warning_planned"
            ),
            "evidence_coverage_pass": passed,
            "threshold": threshold,
            "measured": v,
            "primary_metric": primary,
            "subprocess_returncode": returncode,
        },
        "execution_logs": {
            "stderr_tail": stderr_tail,
        },
        "checklist": [
            "Corpus snapshot loaded and token coverage computed (when available)",
            "Baselines listed in proposal",
            "Primary metric defined in experiment report",
        ],
        "plan_steps": len(plan.get("steps") or []),
    }


def _build_manuscript_markdown(
    *,
    proposal: dict[str, Any],
    experiment_report: dict[str, Any],
    proposal_path: Path,
    experiment_path: Path,
) -> str:
    def tokenize(text: str) -> set[str]:
        return set(re.findall(r"[A-Za-z0-9]{3,}|[一-龥]{2,}", text.lower()))

    contributions = [str(x) for x in (proposal.get("contributions") or []) if str(x).strip()]
    risks = [str(x) for x in (proposal.get("risks") or []) if str(x).strip()]
    steps = []
    exp_plan = experiment_report.get("experiment_plan")
    if isinstance(exp_plan, dict):
        steps = exp_plan.get("steps") or []
    step_lines = []
    for item in steps[:5]:
        if isinstance(item, dict):
            step_lines.append(f"- {item.get('name', 'Step')}: {item.get('detail', '')}")
    if not step_lines:
        step_lines = ["- Experimental procedure to be finalized."]

    metric = (experiment_report.get("metrics") or {}).get("primary_metric")
    metric_value = (experiment_report.get("metrics") or {}).get("value")
    coverage_line = (
        f"- primary_metric: {metric}"
        + (f" (value: {metric_value:.3f})" if isinstance(metric_value, (int, float)) else "")
    )
    execution = experiment_report.get("execution") or {}
    matched_tokens_sample = execution.get("matched_tokens_sample", [])
    logs = execution.get("logs") if isinstance(execution.get("logs"), dict) else {}
    returncode = logs.get("returncode")
    stderr_tail = logs.get("stderr_tail")

    artifacts = (
        experiment_report.get("artifacts")
        if isinstance(experiment_report.get("artifacts"), dict)
        else {}
    )
    art_dir = artifacts.get("dir")
    art_metrics = artifacts.get("metrics_json")
    art_summary = artifacts.get("summary_txt")

    references_section: list[str] = []
    corpus_snapshot_path_raw = experiment_report.get("corpus_snapshot_path")
    if isinstance(corpus_snapshot_path_raw, str) and corpus_snapshot_path_raw.strip():
        corpus_snapshot_path = Path(corpus_snapshot_path_raw)
        if corpus_snapshot_path.is_file():
            try:
                corpus_doc = json.loads(corpus_snapshot_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                corpus_doc = {}
            nodes = corpus_doc.get("nodes") if isinstance(corpus_doc, dict) else None
            if isinstance(nodes, list):
                query_text = "\n".join(
                    [
                        str(proposal.get("problem") or ""),
                        str(proposal.get("hypothesis") or ""),
                    ]
                ).strip()[:4000]
                query_tokens = tokenize(query_text)

                best: list[tuple[int, dict[str, str]]] = []
                max_refs = 3
                for n in nodes:
                    if not isinstance(n, dict):
                        continue
                    if str(n.get("type", "")) != "TextExtract":
                        continue
                    outp = n.get("output_txt")
                    if not outp:
                        continue
                    out_path = Path(str(outp))
                    if not out_path.is_file():
                        continue
                    try:
                        snippet = out_path.read_text(
                            encoding="utf-8",
                            errors="replace",
                        )[:4000]
                    except OSError:
                        continue
                    overlap = len(query_tokens & tokenize(snippet))
                    if overlap <= 0:
                        continue
                    label = n.get("label") or out_path.name
                    best.append(
                        (
                            overlap,
                            {
                                "label": str(label),
                                "path": str(out_path.resolve()),
                            },
                        )
                    )
                    best.sort(key=lambda t: (-t[0], t[1]["path"]))
                    best = best[:max_refs]

                if best:
                    references_section = [
                        "## References",
                        "",
                        *[
                            f"{idx}. {ref['label']} ({ref['path']})"
                            for idx, (_, ref) in enumerate(best, start=1)
                        ],
                        "",
                    ]

    return "\n".join(
        [
            f"# {proposal.get('title', 'Research draft')}",
            "",
            "## Abstract",
            "",
            "This draft is grounded on a confirmed proposal and a generated execution plan.",
            "It outlines a testable hypothesis, expected contributions, and evaluation protocol.",
            "",
            "## Problem",
            "",
            str(proposal.get("problem") or ""),
            "",
            "## Hypothesis",
            "",
            str(proposal.get("hypothesis") or ""),
            "",
            "## Method (Planned)",
            "",
            *step_lines,
            "",
            "## Results",
            "",
            f"- status: {experiment_report.get('status', '')}",
            coverage_line,
            f"- matched_tokens_sample: {matched_tokens_sample}",
            f"- subprocess_returncode: {returncode}",
            f"- subprocess_stderr_tail: {str(stderr_tail)[:120] if stderr_tail else 'None'}",
            f"- artifacts_dir: {art_dir}" if art_dir else "- artifacts_dir: None",
            (
                f"- artifacts_metrics_json: {art_metrics}"
                if art_metrics
                else "- artifacts_metrics_json: None"
            ),
            (
                f"- artifacts_summary_txt: {art_summary}"
                if art_summary
                else "- artifacts_summary_txt: None"
            ),
            "",
            "## Discussion",
            "",
            "This is a lightweight deterministic execution artifact (Phase 3 MVP). "
            "Replace with real code generation + sandboxed execution for production-grade "
            "experimentation.",
            "",
            "## Expected Contributions",
            "",
            *([f"- {c}" for c in contributions[:5]] or ["- Contribution details pending."]),
            "",
            "## Limitations / Risks",
            "",
            *([f"- {r}" for r in risks[:5]] or ["- Risks to be refined after first run."]),
            "",
            *references_section,
            "## Traceability",
            "",
            f"- proposal_source: {proposal_path.resolve()}",
            f"- experiment_source: {experiment_path.resolve()}",
        ]
    )


def _references_bib_text_from_snapshot(snap: dict[str, Any]) -> str:
    """Build minimal BibTeX from corpus snapshot Paper nodes (shared by phase4 bib and bundle)."""

    nodes_raw = snap.get("nodes")
    nodes = nodes_raw if isinstance(nodes_raw, list) else []
    entries: list[str] = []
    used: set[str] = set()
    for n in nodes:
        if not isinstance(n, dict):
            continue
        if str(n.get("type", "")) != "Paper":
            continue
        title = n.get("label")
        if title is None:
            continue
        title_s = str(title).strip()
        if not title_s:
            continue
        src = str(n.get("source", "") or "unknown").strip() or "unknown"
        ext = str(n.get("external_id", "") or n.get("id", "") or "paper").strip() or "paper"
        key_raw = f"{src}_{ext}"
        key = re.sub(r"[^0-9A-Za-z_:-]+", "_", key_raw)[:120] or "paper"
        i = 2
        base = key
        while key in used:
            key = f"{base}_{i}"
            i += 1
        used.add(key)
        url = n.get("pdf_url") or n.get("pdf_path")
        how = f"\\url{{{url}}}" if isinstance(url, str) and url.strip() else src
        entries.append(
            "\n".join(
                [
                    f"@misc{{{key},",
                    f"  title = {{{title_s.replace('{', '').replace('}', '')}}},",
                    f"  howpublished = {{{how}}},",
                    f"  note = {{{src}}},",
                    "}",
                ]
            )
        )
    return "\n\n".join(entries) + ("\n" if entries else "")


def _refresh_references_bib_for_manuscript(paths: Paths, manuscript_path: Path) -> None:
    """Write manuscript-adjacent references.bib from data/kg/corpus-snapshot.json if present."""

    snap_path = paths.kg_dir / "corpus-snapshot.json"
    if not snap_path.is_file():
        return
    try:
        snap = load_corpus_snapshot_document(snap_path)
    except (OSError, json.JSONDecodeError, TypeError):
        return
    out = manuscript_path.with_name("references.bib")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_references_bib_text_from_snapshot(snap), encoding="utf-8")


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
    expect_artifacts: bool = False,
    expect_pdf: bool = False,
    expect_bib: bool = False,
) -> tuple[dict[str, object], bool]:
    def _hash_tree(root: Path) -> str:
        """Stable hash of a directory tree (paths + bytes)."""

        h = hashlib.sha256()
        for p in sorted(root.rglob("*")):
            rel = p.relative_to(root).as_posix()
            if p.is_dir():
                h.update(b"D\x00")
                h.update(rel.encode("utf-8"))
                h.update(b"\x00")
                continue
            if not p.is_file():
                continue
            h.update(b"F\x00")
            h.update(rel.encode("utf-8"))
            h.update(b"\x00")
            h.update(p.read_bytes())
            h.update(b"\x00")
        return h.hexdigest()

    required_files = [
        "proposal-confirmed.json",
        "experiment-report.json",
        "evaluation-summary.json",
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
                "evaluation-summary.json",
                "manuscript-draft.md",
            }
            manifest_missing = sorted(expected_set - listed_set)
            manifest_extra = sorted(listed_set - expected_set)
            optional_raw = manifest_obj.get("optional_present")
            optional_rel: list[str] = []
            if isinstance(optional_raw, list):
                optional_rel = [
                    str(x).strip().strip("/") for x in optional_raw if str(x).strip()
                ]
            optional_bundle_missing: list[str] = []
            for rel in optional_rel:
                p = bundle_dir / rel
                if rel == "artifacts/phase3":
                    if not p.is_dir():
                        optional_bundle_missing.append(rel)
                else:
                    if not p.is_file():
                        optional_bundle_missing.append(rel)
            manifest_ok = (
                len(manifest_missing) == 0
                and len(manifest_extra) == 0
                and len(optional_bundle_missing) == 0
            )
            manifest_check = {
                "ok": manifest_ok,
                "missing_from_manifest": manifest_missing,
                "unexpected_in_manifest": manifest_extra,
                "optional_present": optional_rel,
                "optional_missing": optional_bundle_missing,
            }
            if not manifest_ok:
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
                optional_in_tar_missing: list[str] = []
                manifest_for_tar = bundle_dir / "manifest.json"
                if manifest_for_tar.is_file():
                    try:
                        mo = json.loads(manifest_for_tar.read_text(encoding="utf-8"))
                        op = mo.get("optional_present")
                        if isinstance(op, list):
                            for rel in op:
                                rs = str(rel).strip().strip("/")
                                if not rs:
                                    continue
                                if not _tar_lists_bundle_path(
                                    tar_names=names,
                                    arc_prefix="submission-package",
                                    rel=rs,
                                ):
                                    optional_in_tar_missing.append(rs)
                    except json.JSONDecodeError:
                        pass
                payload["archive"] = {
                    "ok": len(a_missing) == 0 and len(optional_in_tar_missing) == 0,
                    "path": str(archive.resolve()),
                    "missing": a_missing,
                    "optional_missing": optional_in_tar_missing,
                }
                if a_missing or optional_in_tar_missing:
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
            "evaluation-summary.json": bundle_dir / "evaluation-summary.json",
            "manuscript-draft.md": bundle_dir / "manuscript-draft.md",
            "manifest.json": bundle_dir / "manifest.json",
        }
        optional_files = {
            "manuscript-draft.pdf": bundle_dir / "manuscript-draft.pdf",
            "references.bib": bundle_dir / "references.bib",
        }
        for k, p in optional_files.items():
            if k in expected_hashes:
                file_map[k] = p
        if "submission-package.tar.gz" in expected_hashes:
            if archive is None:
                exp_tar = expected_hashes["submission-package.tar.gz"]
                actual_hashes["submission-package.tar.gz"] = "NO_ARCHIVE_PATH"
                hash_mismatch["submission-package.tar.gz"] = {
                    "expected": exp_tar,
                    "actual": "NO_ARCHIVE_PATH",
                }
            else:
                file_map["submission-package.tar.gz"] = archive
        for name, path in file_map.items():
            exp = expected_hashes.get(name)
            if exp is None:
                continue
            if not path.is_file():
                actual_hashes[name] = "MISSING_FILE"
                hash_mismatch[name] = {"expected": exp, "actual": "MISSING_FILE"}
                continue
            h = hashlib.sha256(path.read_bytes()).hexdigest()
            actual_hashes[name] = h
            if exp != h:
                hash_mismatch[name] = {"expected": exp, "actual": h}
        # Optional directory checksums (e.g. artifacts) can be included in expected_hashes.
        dir_map = {
            "artifacts/phase3": bundle_dir / "artifacts" / "phase3",
        }
        for name, path in dir_map.items():
            exp = expected_hashes.get(name)
            if exp is None:
                continue
            if not path.is_dir():
                actual_hashes[name] = "MISSING_DIR"
                hash_mismatch[name] = {"expected": exp, "actual": "MISSING_DIR"}
                continue
            h = _hash_tree(path)
            actual_hashes[name] = h
            if exp != h:
                hash_mismatch[name] = {"expected": exp, "actual": h}
        payload["hashes"] = {
            "ok": len(hash_mismatch) == 0,
            "actual": actual_hashes,
            "mismatch": hash_mismatch,
        }
        if hash_mismatch:
            ok = False

    optional_missing: list[str] = []
    if expect_artifacts and not (bundle_dir / "artifacts" / "phase3").is_dir():
        optional_missing.append("artifacts/phase3")
    if expect_pdf and not (bundle_dir / "manuscript-draft.pdf").is_file():
        optional_missing.append("manuscript-draft.pdf")
    if expect_bib and not (bundle_dir / "references.bib").is_file():
        optional_missing.append("references.bib")
    if optional_missing:
        payload["optional_missing"] = optional_missing
        ok = False

    return payload, ok


@app.command("status")
def cmd_status() -> None:
    """
    Print config, registered providers, and data directory counts (JSON).
    """

    typer.echo(json.dumps(build_status(), ensure_ascii=False, indent=2))


@app.command("doctor")
def cmd_doctor() -> None:
    """
    Print readiness for optional features (LLM, AMiner, Ollama CLI, Docker, LaTeX) and workspace
    config (JSON).

    The same payload is embedded under ``doctor`` in ``autopapers status``.
    """

    typer.echo(json.dumps(build_doctor_payload(), ensure_ascii=False, indent=2))


@app.command("flow")
def cmd_flow() -> None:
    """
    Print high-level workflow stage completion and suggested next commands.
    """

    st = build_status()
    d = st.get("data", {})
    cfg_info = st.get("config") or {}
    phase1_done = bool(d.get("metadata_json")) and bool(d.get("corpus_snapshot_exists"))
    phase2_done = bool(d.get("proposal_confirmed_exists"))
    phase3_done = bool(d.get("experiment_report_exists")) and bool(
        d.get("evaluation_summary_exists")
    )
    phase4_done = bool(d.get("manuscript_draft_exists")) and bool(d.get("submission_bundle_exists"))
    phase5_done = bool(d.get("submission_archive_exists"))
    release_done = bool(d.get("release_report_exists"))
    release_verify_done = bool(d.get("release_verify_report_exists"))
    has_pdf = bool(d.get("manuscript_pdf_exists")) or bool(d.get("submission_bundle_pdf_exists"))
    has_bib = bool(d.get("manuscript_references_bib_exists")) or bool(
        d.get("submission_bundle_references_bib_exists")
    )
    has_artifacts = bool(d.get("submission_bundle_artifacts_phase3_exists"))
    corpus_ok = bool(d.get("corpus_snapshot_exists"))

    next_steps: list[str] = []
    if not phase1_done:
        if not cfg_info.get("default_toml_present"):
            next_steps.append(
                "uv run autopapers workspace-init  "
                "# optional: write configs/default.toml under AUTOPAPERS_REPO_ROOT (or cwd)"
            )
        if st.get("aminer_api_key_configured"):
            next_steps.append(
                "uv run autopapers phase1 run --profile user_profile.json "
                "--provider aminer --fetch-first --parse-fetched"
            )
        else:
            next_steps.append(
                "uv run autopapers phase1 run --profile user_profile.json "
                "--fetch-first --parse-fetched"
            )
        next_steps.append("uv run autopapers corpus build --profile user_profile.json")
        if st.get("aminer_api_key_configured"):
            next_steps.append(
                "uv run autopapers papers aminer-search -q \"ad-hoc topic\" -l 3 "
                "# optional; profile-driven phase1 above already uses --provider aminer"
            )
    elif not phase2_done:
        next_steps.append("uv run autopapers proposal draft --profile user_profile.json")
        next_steps.append(
            "uv run autopapers proposal confirm "
            "-i ./data/proposals/proposal-draft.json"
        )
    elif not phase3_done:
        if d.get("proposal_confirmed_exists") and not d.get("phase3_experiment_py_exists"):
            next_steps.append(
                "uv run autopapers proposal generate-experiment "
                "--proposal ./data/proposals/proposal-confirmed.json"
            )
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
        if corpus_ok and not has_bib:
            next_steps.append(
                "uv run autopapers phase4 bib --snapshot ./data/kg/corpus-snapshot.json"
            )
        if not has_pdf:
            next_steps.append(
                "uv run autopapers phase4 pdf "
                "--manuscript ./data/manuscripts/manuscript-draft.md"
            )
        next_steps.append(
            "uv run autopapers phase4 bundle "
            "--proposal ./data/proposals/proposal-confirmed.json "
            "--experiment ./data/experiments/experiment-report.json "
            "--evaluation ./data/experiments/evaluation-summary.json "
            "--manuscript ./data/manuscripts/manuscript-draft.md "
            "--include-artifacts --include-pdf --include-bib"
        )
    elif not phase5_done:
        next_steps.append(
            "uv run autopapers phase4 submit "
            "--bundle-dir ./data/submissions/submission-package"
        )
        v_opt = ""
        if d.get("submission_bundle_artifacts_phase3_exists"):
            v_opt += " --expect-artifacts"
        if d.get("submission_bundle_pdf_exists"):
            v_opt += " --expect-pdf"
        if d.get("submission_bundle_references_bib_exists"):
            v_opt += " --expect-bib"
        # ``submission_archive_exists`` equals ``phase5_done`` in status; here we have a bundle
        # but no archive yet—verify the directory only (after ``phase4 submit``, flow advances).
        verify_line = (
            "uv run autopapers phase5 verify "
            "--bundle-dir ./data/submissions/submission-package"
        )
        verify_line += v_opt
        next_steps.append(verify_line)
        next_steps.append(
            "uv run autopapers phase5 run "
            "--proposal ./data/proposals/proposal-confirmed.json "
            "# optional: regenerate experiment+manuscript+bundle+archive in one command"
        )
    elif not release_done:
        tail = " --include-artifacts" if has_artifacts else ""
        tail += " --include-pdf" if has_pdf else ""
        tail += " --include-bib" if has_bib or corpus_ok else ""
        next_steps.append(f"uv run autopapers release --profile user_profile.json{tail}")
        next_steps.append(
            "uv run autopapers publish --profile user_profile.json"
            f"{tail}  "
            "# same end-to-end bundle (+ optional archive); skips release-report / signed checksums"
        )
    elif not release_verify_done:
        next_steps.append("uv run autopapers release-verify")
    else:
        next_steps.append(
            "All stages completed. Refresh Phase3+ from proposal-confirmed: "
            "`uv run autopapers resume`"
        )
        next_steps.append(
            "Re-run full pipeline from profile: "
            "`uv run autopapers publish --profile user_profile.json` "
            "or `uv run autopapers release --profile user_profile.json` (adds release-report)"
        )
        next_steps.append(
            "Optional: `uv run autopapers doctor` — LLM/Docker/LaTeX readiness (JSON output)"
        )

    payload = {
        "phase1_data": phase1_done,
        "phase2_proposal": phase2_done,
        "phase3_experiment": phase3_done,
        "phase4_manuscript_bundle": phase4_done,
        "phase5_archive": phase5_done,
        "release_report": release_done,
        "release_verify_report": release_verify_done,
        "aminer_api_key_configured": bool(st.get("aminer_api_key_configured")),
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
    llm_diag = build_llm_backend_diagnostics()
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
                "entrypoints_on_path": {
                    "autopapers": shutil.which("autopapers") is not None,
                    "paper_fetcher_cli": shutil.which("paper-fetcher") is not None,
                },
                "llm": llm_diag,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("workspace-init")
def cmd_workspace_init(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing configs/default.toml",
    ),
) -> None:
    """
    Create ``configs/default.toml`` under the data repo root if missing.

    Use this in an empty directory with ``AUTOPAPERS_REPO_ROOT`` so ``config`` / ``status``
    match a real file-based setup (defaults otherwise come only from code + env).
    """

    paths = get_paths()
    cfg_dir = paths.repo_root / "configs"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    target = cfg_dir / "default.toml"
    if target.is_file() and not force:
        typer.echo(
            json.dumps(
                {
                    "ok": True,
                    "skipped": True,
                    "path": str(target.resolve()),
                    "hint": "Pass --force to overwrite",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    target.write_text(_WORKSPACE_DEFAULT_TOML, encoding="utf-8")
    typer.echo(
        json.dumps(
            {
                "ok": True,
                "written": str(target.resolve()),
                "default_toml_present": target.is_file(),
                "status": build_status(),
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
        help=(
            "Also run phase3 (executes experiment.py when corpus snapshot exists), "
            "evaluation, and phase4 manuscript/bundle scaffold"
        ),
    ),
    archive: bool = typer.Option(
        True,
        "--archive/--no-archive",
        help="With --full-flow, also create submission-package.tar.gz archive",
    ),
    include_artifacts: bool = typer.Option(
        False,
        "--include-artifacts",
        help="With --full-flow: copy phase3 artifacts into bundle/artifacts/",
    ),
    include_pdf: bool = typer.Option(
        False,
        "--include-pdf",
        help="With --full-flow: compile and include manuscript PDF in the bundle (best-effort)",
    ),
    include_bib: bool = typer.Option(
        False,
        "--include-bib",
        help=(
            "With --full-flow: refresh references.bib from corpus and copy into bundle "
            "(best-effort)"
        ),
    ),
    provider: str | None = typer.Option(
        None,
        "--provider",
        help="Paper search provider for this run (overrides config; e.g. aminer, arxiv)",
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

    provider_name, prov, _reg, _cfg_default = _search_provider_for_cli(provider)
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
    try:
        debate = run_debate(profile_summary=prof_summary, corpus_summary=corpus_summary)
    except ValueError as e:
        err = {"ok": False, "error": "llm_setup", "detail": str(e)}
        typer.echo(json.dumps(err, indent=2), err=True)
        raise typer.Exit(code=1) from e
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
        try:
            report = _experiment_report_for_full_pipeline(
                paths=paths,
                confirmed_path=confirmed_path,
                proposal=proposal,
            )
        except ValueError as e:
            typer.echo(
                json.dumps(
                    {
                        "ok": False,
                        "error": "phase3_scaffold",
                        "detail": str(e),
                    },
                    indent=2,
                ),
                err=True,
            )
            raise typer.Exit(code=1) from e
        experiment_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        evaluation_summary_path = exp_dir / "evaluation-summary.json"
        summary_doc = _build_evaluation_summary(report=report, report_path=experiment_path)
        evaluation_summary_path.write_text(
            json.dumps(summary_doc, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        ms_dir = paths.data_dir / "manuscripts"
        ms_dir.mkdir(parents=True, exist_ok=True)
        manuscript_path = ms_dir / "manuscript-draft.md"
        manuscript_path.write_text(
            _build_manuscript_markdown(
                proposal=proposal,
                experiment_report=report,
                proposal_path=confirmed_path,
                experiment_path=experiment_path,
            )
            + "\n",
            encoding="utf-8",
        )

        bundle_dir = paths.data_dir / "submissions" / "submission-package"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(confirmed_path, bundle_dir / "proposal-confirmed.json")
        shutil.copy2(experiment_path, bundle_dir / "experiment-report.json")
        shutil.copy2(evaluation_summary_path, bundle_dir / "evaluation-summary.json")
        shutil.copy2(manuscript_path, bundle_dir / "manuscript-draft.md")
        if include_pdf:
            try:
                phase4_pdf(manuscript=manuscript_path)
            except typer.Exit:
                pass
            pdf = manuscript_path.with_suffix(".pdf")
            if pdf.is_file():
                shutil.copy2(pdf, bundle_dir / "manuscript-draft.pdf")
        if include_bib:
            _refresh_references_bib_for_manuscript(paths, manuscript_path)
            bib = manuscript_path.with_name("references.bib")
            if bib.is_file():
                shutil.copy2(bib, bundle_dir / "references.bib")
        if include_artifacts:
            artifacts = (
                report.get("artifacts")
                if isinstance(report.get("artifacts"), dict)
                else None
            )
            if isinstance(artifacts, dict):
                src_dir = artifacts.get("dir")
                if isinstance(src_dir, str) and src_dir.strip():
                    src_path = Path(src_dir)
                    if src_path.is_dir():
                        dst = bundle_dir / "artifacts" / "phase3"
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copytree(src_path, dst, dirs_exist_ok=True)
        _write_submission_manifest(
            bundle_dir,
            include_pdf=include_pdf,
            include_bib=include_bib,
            include_artifacts=include_artifacts,
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
    include_artifacts: bool = typer.Option(
        False,
        "--include-artifacts",
        help="Include phase3 artifacts in submission bundle (best-effort)",
    ),
    include_pdf: bool = typer.Option(
        False,
        "--include-pdf",
        help="Compile and include manuscript PDF in submission bundle (best-effort)",
    ),
    include_bib: bool = typer.Option(
        False,
        "--include-bib",
        help="Refresh references.bib from corpus and include in submission bundle (best-effort)",
    ),
    provider: str | None = typer.Option(
        None,
        "--provider",
        help="Paper search provider for this run (overrides config; e.g. aminer, arxiv)",
    ),
    archive: bool = typer.Option(
        True,
        "--archive/--no-archive",
        help="After bundling: also write data/submissions/submission-package.tar.gz",
    ),
) -> None:
    """One-command full pipeline to submission bundle (and optional archive)."""

    cmd_run_all(
        profile=profile,
        title=title,
        limit=limit,
        parse_max_pages=parse_max_pages,
        full_flow=True,
        archive=archive,
        include_artifacts=include_artifacts,
        include_pdf=include_pdf,
        include_bib=include_bib,
        provider=provider,
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
    include_artifacts: bool = typer.Option(
        False,
        "--include-artifacts",
        help="Include phase3 artifacts in submission bundle and checksums (best-effort)",
    ),
    include_pdf: bool = typer.Option(
        False,
        "--include-pdf",
        help="Compile and include manuscript PDF in submission bundle and checksums (best-effort)",
    ),
    include_bib: bool = typer.Option(
        False,
        "--include-bib",
        help="Refresh references.bib from corpus and include in bundle and checksums (best-effort)",
    ),
    provider: str | None = typer.Option(
        None,
        "--provider",
        help="Paper search provider for this run (overrides config; e.g. aminer, arxiv)",
    ),
    archive: bool = typer.Option(
        True,
        "--archive/--no-archive",
        help="Write data/submissions/submission-package.tar.gz and include it in checksums",
    ),
) -> None:
    """Run publish pipeline and emit release report for downstream delivery."""

    schema_path = _schema_path()
    data = load_profile_from_json(profile)
    validate_profile(profile=data, schema=load_schema(schema_path))

    provider_name, prov, _reg, _cfg_default = _search_provider_for_cli(provider)
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
    try:
        debate = run_debate(profile_summary=prof_summary, corpus_summary=corpus_summary)
    except ValueError as e:
        err = {"ok": False, "error": "llm_setup", "detail": str(e)}
        typer.echo(json.dumps(err, indent=2), err=True)
        raise typer.Exit(code=1) from e
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
    try:
        report = _experiment_report_for_full_pipeline(
            paths=paths,
            confirmed_path=confirmed_path,
            proposal=proposal,
        )
    except ValueError as e:
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "phase3_scaffold",
                    "detail": str(e),
                },
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1) from e
    exp_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_doc = _build_evaluation_summary(report=report, report_path=exp_out)
    eval_out.write_text(
        json.dumps(summary_doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    ms_out.parent.mkdir(parents=True, exist_ok=True)
    ms_out.write_text(
        _build_manuscript_markdown(
            proposal=proposal,
            experiment_report=report,
            proposal_path=confirmed_path,
            experiment_path=exp_out,
        )
        + "\n",
        encoding="utf-8",
    )
    if include_pdf:
        try:
            phase4_pdf(manuscript=ms_out)
        except typer.Exit:
            pass
    if include_bib:
        _refresh_references_bib_for_manuscript(paths, ms_out)
    bundle_out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(confirmed_path, bundle_out / "proposal-confirmed.json")
    shutil.copy2(exp_out, bundle_out / "experiment-report.json")
    shutil.copy2(eval_out, bundle_out / "evaluation-summary.json")
    shutil.copy2(ms_out, bundle_out / "manuscript-draft.md")
    if include_pdf:
        pdf = ms_out.with_suffix(".pdf")
        if pdf.is_file():
            shutil.copy2(pdf, bundle_out / "manuscript-draft.pdf")
    if include_bib:
        bib = ms_out.with_name("references.bib")
        if bib.is_file():
            shutil.copy2(bib, bundle_out / "references.bib")
    if include_artifacts:
        artifacts = (
            report.get("artifacts") if isinstance(report.get("artifacts"), dict) else None
        )
        if isinstance(artifacts, dict):
            src_dir = artifacts.get("dir")
            if isinstance(src_dir, str) and src_dir.strip():
                src_path = Path(src_dir)
                if src_path.is_dir():
                    dst = bundle_out / "artifacts" / "phase3"
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(src_path, dst, dirs_exist_ok=True)
    _write_submission_manifest(
        bundle_out,
        include_pdf=include_pdf,
        include_bib=include_bib,
        include_artifacts=include_artifacts,
    )
    if archive:
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
    }
    if archive:
        checksums["submission-package.tar.gz"] = hashlib.sha256(
            archive_out.read_bytes()
        ).hexdigest()
    if include_pdf and (bundle_out / "manuscript-draft.pdf").is_file():
        checksums["manuscript-draft.pdf"] = hashlib.sha256(
            (bundle_out / "manuscript-draft.pdf").read_bytes()
        ).hexdigest()
    if include_bib and (bundle_out / "references.bib").is_file():
        checksums["references.bib"] = hashlib.sha256(
            (bundle_out / "references.bib").read_bytes()
        ).hexdigest()
    if include_artifacts and (bundle_out / "artifacts" / "phase3").is_dir():
        h = hashlib.sha256()
        root = bundle_out / "artifacts" / "phase3"
        for p in sorted(root.rglob("*")):
            rel = p.relative_to(root).as_posix()
            if p.is_dir():
                h.update(b"D\x00")
                h.update(rel.encode("utf-8"))
                h.update(b"\x00")
                continue
            if not p.is_file():
                continue
            h.update(b"F\x00")
            h.update(rel.encode("utf-8"))
            h.update(b"\x00")
            h.update(p.read_bytes())
            h.update(b"\x00")
        checksums["artifacts/phase3"] = h.hexdigest()

    verify_payload: dict[str, object] | None = None
    verify_ok = True
    if verify:
        verify_payload, verify_ok = _verify_submission_assets(
            bundle_dir=bundle_out,
            archive=archive_out if archive else None,
            expected_hashes=checksums,
            expect_artifacts=include_artifacts,
            expect_pdf=include_pdf,
            expect_bib=include_bib,
        )

    release_report = {
        "schema_version": "0.2",
        "autopapers_version": autopapers_version,
        "generated_at": datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "proposal_title": str(proposal.get("title") or ""),
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
        "submission_archive": str(archive_out.resolve()) if archive else None,
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
    if not isinstance(bundle_raw, str) or not isinstance(checksums, dict):
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "invalid_release_report",
                    "detail": "submission_bundle and checksums (object) are required",
                },
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1)

    archive_path: Path | None = None
    if isinstance(archive_raw, str) and archive_raw.strip():
        archive_path = Path(archive_raw)

    ch = {str(k): str(v) for k, v in checksums.items()}
    ea, ep, eb = _merge_expect_flags_from_checksums(
        ch,
        expect_artifacts=False,
        expect_pdf=False,
        expect_bib=False,
    )
    detail, ok = _verify_submission_assets(
        bundle_dir=Path(bundle_raw),
        archive=archive_path,
        expected_hashes=ch,
        expect_artifacts=ea,
        expect_pdf=ep,
        expect_bib=eb,
    )
    paths = get_paths()
    verify_report = {
        "schema_version": "0.2",
        "autopapers_version": autopapers_version,
        "generated_at": datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
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
    title: str = typer.Option(
        "Research direction",
        "--title",
        "-t",
        help="When falling back to release: proposal / manuscript title",
    ),
    limit: int = typer.Option(
        3,
        "--limit",
        "-l",
        help="When falling back to release: search result count",
    ),
    parse_max_pages: int = typer.Option(
        20,
        "--parse-max-pages",
        help="When falling back to release: max PDF pages to parse (0 = all)",
    ),
    verify: bool = typer.Option(
        True,
        "--verify/--no-verify",
        help="Verify bundle/archive integrity after resume run",
    ),
    include_artifacts: bool = typer.Option(
        False,
        "--include-artifacts",
        help="Include phase3 artifacts in submission bundle (best-effort)",
    ),
    include_pdf: bool = typer.Option(
        False,
        "--include-pdf",
        help="Compile and include manuscript PDF in submission bundle (best-effort)",
    ),
    include_bib: bool = typer.Option(
        False,
        "--include-bib",
        help="Refresh references.bib from corpus and include in submission bundle (best-effort)",
    ),
    provider: str | None = typer.Option(
        None,
        "--provider",
        help=(
            "When falling back to full release (--profile): paper search provider "
            "(overrides config; e.g. aminer, arxiv, local_pdf)"
        ),
    ),
    archive: bool = typer.Option(
        True,
        "--archive/--no-archive",
        help=(
            "When falling back to release: same as ``release``. "
            "When resuming from confirmed proposal: write submission .tar.gz after bundle"
        ),
    ),
) -> None:
    """
    Resume pipeline from existing artifacts.

    Priority:
    1) if data/proposals/proposal-confirmed.json exists, continue from Phase3+
       (``--archive/--no-archive`` controls writing submission-package.tar.gz)
    2) else if --profile is provided, run full release pipeline from profile
       (``--title``, ``--limit``, ``--parse-max-pages`` and ``--archive`` are forwarded)
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
            title=title,
            limit=limit,
            parse_max_pages=parse_max_pages,
            verify=verify,
            include_artifacts=include_artifacts,
            include_pdf=include_pdf,
            include_bib=include_bib,
            provider=provider,
            archive=archive,
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
    try:
        report = _experiment_report_for_full_pipeline(
            paths=paths,
            confirmed_path=confirmed,
            proposal=raw,
        )
    except ValueError as e:
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "phase3_scaffold",
                    "detail": str(e),
                },
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1) from e
    exp_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_doc = _build_evaluation_summary(report=report, report_path=exp_out)
    eval_out.write_text(
        json.dumps(summary_doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    ms_out.parent.mkdir(parents=True, exist_ok=True)
    ms_out.write_text(
        _build_manuscript_markdown(
            proposal=raw,
            experiment_report=report,
            proposal_path=confirmed,
            experiment_path=exp_out,
        )
        + "\n",
        encoding="utf-8",
    )
    if include_pdf:
        try:
            phase4_pdf(manuscript=ms_out)
        except typer.Exit:
            pass
    if include_bib:
        _refresh_references_bib_for_manuscript(paths, ms_out)
    bundle_out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(confirmed, bundle_out / "proposal-confirmed.json")
    shutil.copy2(exp_out, bundle_out / "experiment-report.json")
    shutil.copy2(eval_out, bundle_out / "evaluation-summary.json")
    shutil.copy2(ms_out, bundle_out / "manuscript-draft.md")
    if include_pdf:
        pdf = ms_out.with_suffix(".pdf")
        if pdf.is_file():
            shutil.copy2(pdf, bundle_out / "manuscript-draft.pdf")
    if include_bib:
        bib = ms_out.with_name("references.bib")
        if bib.is_file():
            shutil.copy2(bib, bundle_out / "references.bib")
    if include_artifacts:
        artifacts = (
            report.get("artifacts") if isinstance(report.get("artifacts"), dict) else None
        )
        if isinstance(artifacts, dict):
            src_dir = artifacts.get("dir")
            if isinstance(src_dir, str) and src_dir.strip():
                src_path = Path(src_dir)
                if src_path.is_dir():
                    dst = bundle_out / "artifacts" / "phase3"
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(src_path, dst, dirs_exist_ok=True)
    _write_submission_manifest(
        bundle_out,
        include_pdf=include_pdf,
        include_bib=include_bib,
        include_artifacts=include_artifacts,
    )
    if archive:
        if archive_path.is_file():
            archive_path.unlink()
        with tarfile.open(archive_path, "w:gz") as tf:
            tf.add(bundle_out, arcname=bundle_out.name)

    verify_payload: dict[str, object] | None = None
    ok = True
    if verify:
        verify_payload, ok = _verify_submission_assets(
            bundle_dir=bundle_out,
            archive=archive_path if archive else None,
            expect_artifacts=include_artifacts,
            expect_pdf=include_pdf,
            expect_bib=include_bib,
        )

    payload: dict[str, object] = {
        "ok": ok,
        "resumed_from": str(confirmed.resolve()),
        "experiment_report": str(exp_out.resolve()),
        "evaluation_summary": str(eval_out.resolve()),
        "manuscript_draft": str(ms_out.resolve()),
        "submission_bundle": str(bundle_out.resolve()),
        "submission_archive": (
            str(archive_path.resolve()) if archive and archive_path.is_file() else None
        ),
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


@papers_app.command("aminer-search")
def papers_aminer_search(
    query: str = typer.Option(
        ...,
        "--query",
        "-q",
        help="AMiner search query",
    ),
    limit: int = typer.Option(5, "--limit", "-l", help="Max results"),
    no_save: bool = typer.Option(False, "--no-save", help="Do not write search metadata JSON"),
    download_first: bool = typer.Option(
        False,
        "--download-first",
        help="Fetch PDF for the first hit into data/papers/pdfs/ (direct pdf_url/url only)",
    ),
) -> None:
    """
    Search AMiner using AMINER_API_KEY (ignores AUTOPAPERS_PROVIDER).

    Optional --download-first uses the provider's direct PDF URL; for broader download
    fallbacks use ``papers download --title ...`` after inspecting results.
    """

    paths = get_paths()
    reg = ProviderRegistry.default()
    p = reg.get("aminer")
    try:
        refs = p.search(query=query, limit=limit)
    except ValueError as e:
        typer.echo(
            json.dumps(
                {"ok": False, "error": "aminer_setup", "detail": str(e)},
                ensure_ascii=False,
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1) from e
    except RuntimeError as e:
        typer.echo(
            json.dumps(
                {"ok": False, "error": "aminer_request", "detail": str(e)},
                ensure_ascii=False,
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1) from e

    typer.echo(json.dumps([r.__dict__ for r in refs], ensure_ascii=False, indent=2))
    if not no_save:
        meta_path = write_search_record(paths, provider="aminer", query=query, refs=refs)
        typer.echo(f"Wrote metadata: {meta_path}", err=True)

    if download_first and refs:
        ref0 = refs[0]
        try:
            out = p.fetch_pdf(ref=ref0, dest_dir=paths.papers_pdfs_dir)
        except (OSError, ValueError, RuntimeError) as e:
            typer.echo(
                json.dumps(
                    {
                        "ok": False,
                        "error": "fetch_failed",
                        "detail": str(e),
                        "ref": ref0.__dict__,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                err=True,
            )
            raise typer.Exit(code=1) from e
        fetch_meta = write_fetch_record(
            paths,
            source="aminer",
            paper_id=ref0.id,
            title=ref0.title,
            pdf_path=out,
        )
        typer.echo(
            json.dumps(
                {
                    "ok": True,
                    "pdf": str(out.resolve()),
                    "fetch_metadata": str(fetch_meta.resolve()),
                },
                ensure_ascii=False,
                indent=2,
            ),
            err=True,
        )


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


@papers_app.command("download")
def papers_download(
    title: str | None = typer.Option(None, "--title", help="Paper title"),
    doi: str | None = typer.Option(None, "--doi", help="DOI (optional, recommended)"),
    authors: str | None = typer.Option(
        None,
        "--authors",
        help="Comma-separated author names (optional; used to improve download)",
    ),
    email: str = typer.Option(
        os.environ.get("AUTOPAPERS_MAILTO", "").strip() or "research@example.com",
        "--email",
        help="Contact email for Unpaywall (default: AUTOPAPERS_MAILTO or research@example.com)",
    ),
) -> None:
    """
    Download a paper PDF using the legacy PDF downloader (arXiv → Unpaywall → S2 → Anna's).

    Writes the PDF under ./data/papers/pdfs/ and a fetch metadata JSON under
    ./data/papers/metadata/.
    """

    if not (title or doi):
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "invalid_args",
                    "detail": "Provide at least one of --title or --doi",
                },
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1)

    paths = get_paths()
    ensure_legacy_api_on_path()
    from api.pdf_downloader import PDFDownloader  # noqa: PLC0415

    auth_list = (
        [a.strip() for a in (authors or "").split(",") if a.strip()] if authors else None
    )
    downloader = PDFDownloader(download_dir=str(paths.papers_pdfs_dir), email=email)
    result = downloader.download(title=title, doi=doi, authors=auth_list)

    if not getattr(result, "success", False):
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "download_failed",
                    "detail": getattr(result, "error", None),
                    "manual_url": getattr(result, "manual_url", None),
                },
                ensure_ascii=False,
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1)

    raw_path = getattr(result, "filepath", None)
    if not isinstance(raw_path, str) or not raw_path.strip():
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "download_failed",
                    "detail": "Downloader returned no filepath",
                },
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1)

    pdf_path = Path(raw_path).expanduser().resolve()
    if not pdf_path.is_file():
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "download_failed",
                    "detail": "Downloaded file not found",
                    "path": str(pdf_path),
                },
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1)

    pid = (doi or title or "paper").strip()
    pid = re.sub(r"\s+", "_", pid)
    pid = re.sub(r"[^0-9A-Za-z._-]", "_", pid)[:120] or "paper"
    meta_path = write_fetch_record(
        paths,
        source="pdf_downloader",
        paper_id=pid,
        title=title,
        pdf_path=pdf_path,
    )
    typer.echo(str(pdf_path))
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
    provider: str | None = typer.Option(
        None,
        "--provider",
        help=(
            "Override AUTOPAPERS_PROVIDER / config for this run only "
            "(e.g. aminer, arxiv, crossref, openalex, local_pdf)"
        ),
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

    eff_provider, prov, _reg, cfg_provider = _search_provider_for_cli(provider)

    if dry_run:
        typer.echo(
            json.dumps(
                {
                    "dry_run": True,
                    "profile": str(profile.resolve()),
                    "query": query,
                    "provider": eff_provider,
                    "provider_config_default": cfg_provider,
                    "provider_cli_overridden": bool(provider and provider.strip()),
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

    paths = get_paths()
    refs = prov.search(query=query, limit=limit)
    meta = write_search_record(paths, provider=eff_provider, query=query, refs=refs)
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

    try:
        debate = run_debate(profile_summary=prof_summary, corpus_summary=corpus_summary)
    except ValueError as e:
        err = {"ok": False, "error": "llm_setup", "detail": str(e)}
        typer.echo(json.dumps(err, indent=2), err=True)
        raise typer.Exit(code=1) from e
    proposal = merge_stub_to_proposal(title=title, debate=debate, status="draft")

    prop_schema = load_schema(_proposal_schema_path())
    validate_profile(profile=proposal, schema=prop_schema)

    paths.proposals_dir.mkdir(parents=True, exist_ok=True)
    out = output or (paths.proposals_dir / "proposal-draft.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    typer.echo(str(out))


@proposal_app.command("generate-evaluator")
def proposal_generate_evaluator(
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
        help="Evaluator script path (default: data/runs/phase3/evaluator.py)",
    ),
) -> None:
    """
    Generate a deterministic Phase 3 evaluator script for offline execution.

    The evaluator prints a JSON result to stdout.
    """

    try:
        out = _write_phase3_evaluator_script(proposal=proposal, output=output)
    except ValueError as e:
        msg = str(e)
        err_key = "invalid_json" if msg.startswith("invalid_json:") else "validation"
        typer.echo(
            json.dumps({"ok": False, "error": err_key, "detail": msg}, indent=2),
            err=True,
        )
        raise typer.Exit(code=1) from e

    typer.echo(str(out.resolve()))


@proposal_app.command("generate-experiment")
def proposal_generate_experiment(
    proposal: Path = typer.Option(
        Path("data/proposals/proposal-confirmed.json"),
        "--proposal",
        "-p",
        exists=True,
        dir_okay=False,
        help="Confirmed proposal JSON path",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Directory to write experiment spec + runner (default: data/runs/phase3)",
    ),
) -> None:
    """
    Generate a minimal Phase 3 experiment spec and runnable experiment.py.

    This is an MVP scaffold for a future generator agent: deterministic and offline-safe.
    """

    try:
        result = _write_phase3_experiment_scaffold(proposal, output_dir=output_dir)
    except ValueError as e:
        msg = str(e)
        err_key = "invalid_json" if msg.startswith("invalid_json:") else "validation"
        typer.echo(
            json.dumps({"ok": False, "error": err_key, "detail": msg}, indent=2),
            err=True,
        )
        raise typer.Exit(code=1) from e

    typer.echo(
        json.dumps(
            {"ok": True, **result},
            ensure_ascii=False,
            indent=2,
        )
    )


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
    runner: str = typer.Option(
        "local",
        "--runner",
        help="Execution runner: local (default) or docker (requires docker)",
    ),
) -> None:
    """Phase3 thin flow: run evaluator and write experiment report."""

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
    runner = runner.strip().lower()
    if runner not in {"local", "docker"}:
        typer.echo(
            json.dumps(
                {"ok": False, "error": "invalid_args", "detail": "runner must be local|docker"},
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1)

    if runner == "local":
        report = _phase3_local_experiment_report(proposal=proposal, raw=raw, paths=paths)
    else:
        # Docker runner executes experiment.py (preferred) or evaluator.py inside a python image.
        # This is best-effort and optional (tests do not require docker).
        exp_py = paths.runs_dir / "phase3" / "experiment.py"
        exp_spec = paths.runs_dir / "phase3" / "experiment_spec.json"
        eval_script = paths.runs_dir / "phase3" / "evaluator.py"
        if not eval_script.is_file():
            try:
                _write_phase3_evaluator_script(proposal=proposal, output=eval_script)
            except ValueError as e:
                typer.echo(
                    json.dumps(
                        {
                            "ok": False,
                            "error": "evaluator_scaffold",
                            "detail": str(e),
                        },
                        indent=2,
                    ),
                    err=True,
                )
                raise typer.Exit(code=1) from e
        corpus_snapshot = paths.kg_dir / "corpus-snapshot.json"
        if not corpus_snapshot.is_file():
            # Fall back to local planned report when corpus is missing.
            report = _build_experiment_report(proposal=raw, proposal_path=proposal)
        else:
            data_dir = paths.data_dir.resolve()
            container = os.environ.get("AUTOPAPERS_DOCKER_IMAGE", "python:3.11-slim").strip()
            query_text = "\n".join(
                [
                    str(raw.get("problem") or ""),
                    str(raw.get("hypothesis") or ""),
                ]
            )[:4000]

            # Prefer running experiment.py when present, producing artifacts under
            # /data/artifacts/phase3/<ts>.
            ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            art_dir = paths.artifacts_dir / "phase3" / ts
            art_dir.mkdir(parents=True, exist_ok=True)

            if exp_py.is_file():
                cmd = [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{data_dir}:/data",
                    container,
                    "python",
                    f"/data/runs/phase3/{exp_py.name}",
                    "/data/kg/corpus-snapshot.json",
                    query_text,
                    f"/data/artifacts/phase3/{ts}",
                ]
            else:
                cmd = [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{data_dir}:/data",
                    container,
                    "python",
                    f"/data/runs/phase3/{eval_script.name}",
                    "/data/kg/corpus-snapshot.json",
                    query_text,
                    "8",
                    "20000",
                    "10",
                ]
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=90,
                )
            except FileNotFoundError as e:
                typer.echo(
                    json.dumps(
                        {
                            "ok": False,
                            "error": "docker_missing",
                            "detail": "docker not found; install Docker or use --runner local",
                        },
                        indent=2,
                    ),
                    err=True,
                )
                raise typer.Exit(code=1) from e
            if proc.returncode != 0:
                typer.echo(
                    json.dumps(
                        {
                            "ok": False,
                            "error": "docker_failed",
                            "detail": (proc.stderr or proc.stdout)[-1500:],
                            "cmd": cmd[:8] + ["..."],
                        },
                        indent=2,
                    ),
                    err=True,
                )
                raise typer.Exit(code=1)
            try:
                parsed = json.loads((proc.stdout or "").strip())
            except json.JSONDecodeError:
                parsed = {"executed": False, "error": "invalid_docker_json"}
            # Build a report mirroring local structure.
            report = _build_experiment_report(proposal=raw, proposal_path=proposal)
            if exp_py.is_file():
                report["status"] = "executed" if proc.returncode == 0 else "failed"
                report["metrics"] = {
                    "primary_metric": "evidence_coverage",
                    "value": parsed.get("value"),
                }
                report["artifacts"] = {
                    "dir": str(art_dir.resolve()),
                    "metrics_json": str((art_dir / "metrics.json").resolve())
                    if (art_dir / "metrics.json").is_file()
                    else None,
                    "summary_txt": str((art_dir / "summary.txt").resolve())
                    if (art_dir / "summary.txt").is_file()
                    else None,
                }
                report["execution"] = {
                    "mode": "docker_experiment_py",
                    "spec": str(exp_spec.resolve()) if exp_spec.is_file() else None,
                    "runner": str(exp_py.resolve()),
                    "logs": {
                        "returncode": proc.returncode,
                        "stderr_tail": (proc.stderr or "")[-1000:],
                        "docker_image": container,
                    },
                }
            elif parsed.get("executed"):
                report["status"] = "executed"
                report["metrics"] = {
                    "primary_metric": "evidence_coverage",
                    "value": parsed.get("coverage"),
                }
                report["execution"] = {
                    "mode": "docker_token_coverage",
                    "query_token_count": parsed.get("query_token_count"),
                    "corpus_token_count": parsed.get("corpus_token_count"),
                    "matched_tokens_sample": parsed.get("matched_tokens_sample") or [],
                    "logs": {
                        "returncode": proc.returncode,
                        "stderr_tail": (proc.stderr or "")[-1000:],
                        "evaluator_script": str(eval_script.resolve()),
                        "docker_image": container,
                    },
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
    """Phase3 thin flow: derive evaluation checklist from experiment plan report."""

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
    summary = _build_evaluation_summary(report=rep, report_path=report)
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
    """Phase4 thin flow: render grounded manuscript scaffold with traceability."""

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
    md = _build_manuscript_markdown(
        proposal=prop,
        experiment_report=exp,
        proposal_path=proposal,
        experiment_path=experiment,
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
    evaluation: Path = typer.Option(
        Path("data/experiments/evaluation-summary.json"),
        "--evaluation",
        exists=True,
        dir_okay=False,
        help="Evaluation summary JSON path",
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
    include_artifacts: bool = typer.Option(
        False,
        "--include-artifacts",
        help="If present in experiment-report.json, copy artifacts into bundle/artifacts/",
    ),
    include_pdf: bool = typer.Option(
        False,
        "--include-pdf",
        help="If manuscript .pdf exists, copy it into the bundle",
    ),
    include_bib: bool = typer.Option(
        False,
        "--include-bib",
        help="Refresh references.bib from corpus (if snapshot exists) and copy into bundle",
    ),
) -> None:
    """Phase4 stub: package proposal/experiment/manuscript into one submission folder."""

    paths = get_paths()
    out_dir = output_dir or (paths.data_dir / "submissions" / "submission-package")
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(proposal, out_dir / "proposal-confirmed.json")
    shutil.copy2(experiment, out_dir / "experiment-report.json")
    shutil.copy2(evaluation, out_dir / "evaluation-summary.json")
    shutil.copy2(manuscript, out_dir / "manuscript-draft.md")
    if include_pdf:
        pdf = manuscript.with_suffix(".pdf")
        if pdf.is_file():
            shutil.copy2(pdf, out_dir / "manuscript-draft.pdf")
    if include_bib:
        _refresh_references_bib_for_manuscript(paths, manuscript)
        bib = manuscript.with_name("references.bib")
        if bib.is_file():
            shutil.copy2(bib, out_dir / "references.bib")

    if include_artifacts:
        try:
            rep = json.loads(experiment.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            rep = {}
        artifacts = rep.get("artifacts") if isinstance(rep, dict) else None
        if isinstance(artifacts, dict):
            src_dir = artifacts.get("dir")
            if isinstance(src_dir, str) and src_dir.strip():
                src_path = Path(src_dir)
                if src_path.is_dir():
                    dst = out_dir / "artifacts" / "phase3"
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(src_path, dst, dirs_exist_ok=True)
    _write_submission_manifest(
        out_dir,
        include_pdf=include_pdf,
        include_bib=include_bib,
        include_artifacts=include_artifacts,
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
        bundle_dir / "evaluation-summary.json",
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


@phase4_app.command("latex")
def phase4_latex(
    manuscript: Path = typer.Option(
        Path("data/manuscripts/manuscript-draft.md"),
        "--manuscript",
        "-m",
        exists=True,
        dir_okay=False,
        help="Input grounded Markdown manuscript",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output .tex path (default: same stem as manuscript with .tex)",
    ),
) -> None:
    """Export a minimal LaTeX file from manuscript markdown (MVP)."""

    md = manuscript.read_text(encoding="utf-8")
    title = manuscript.stem.replace("_", " ")
    has_bib = manuscript.with_name("references.bib").is_file()
    tex = "\n".join(
        [
            r"\documentclass[11pt]{article}",
            r"\usepackage[margin=1in]{geometry}",
            r"\usepackage[T1]{fontenc}",
            r"\usepackage[utf8]{inputenc}",
            r"\usepackage{hyperref}",
            r"\usepackage{verbatim}",
            r"\usepackage[numbers]{natbib}" if has_bib else "",
            "",
            r"\title{" + title.replace("{", "").replace("}", "") + r"}",
            r"\author{AutoPapers}",
            r"\date{}",
            "",
            r"\begin{document}",
            r"\maketitle",
            "",
            r"\begin{verbatim}",
            md.rstrip("\n"),
            r"\end{verbatim}",
            "",
            r"\nocite{*}" if has_bib else "",
            r"\bibliographystyle{plain}" if has_bib else "",
            r"\bibliography{references}" if has_bib else "",
            "",
            r"\end{document}",
            "",
        ]
    )
    out = output or manuscript.with_suffix(".tex")
    out.write_text(tex, encoding="utf-8")
    typer.echo(str(out.resolve()))


@phase4_app.command("pdf")
def phase4_pdf(
    manuscript: Path = typer.Option(
        Path("data/manuscripts/manuscript-draft.md"),
        "--manuscript",
        "-m",
        exists=True,
        dir_okay=False,
        help="Input grounded Markdown manuscript",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output PDF path (default: same stem as manuscript with .pdf)",
    ),
    engine: str | None = typer.Option(
        None,
        "--engine",
        help="Force engine: tectonic | latexmk | pdflatex (default: auto)",
    ),
    keep_tex: bool = typer.Option(
        True,
        "--keep-tex/--no-keep-tex",
        help="Keep intermediate .tex file",
    ),
) -> None:
    """
    Compile manuscript to a PDF (best-effort).

    Prefers `tectonic` (single-command LaTeX engine). Falls back to `latexmk` or `pdflatex`.
    """

    tex_path = manuscript.with_suffix(".tex")
    if not tex_path.is_file():
        phase4_latex(manuscript=manuscript, output=tex_path)

    out_pdf = output or manuscript.with_suffix(".pdf")
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    has_bib = manuscript.with_name("references.bib").is_file()
    chosen = (engine or "").strip().lower() or "auto"
    if chosen == "auto":
        # Prefer latexmk/pdflatex when bibliography exists (needs multiple passes).
        if has_bib:
            candidates = ["latexmk", "pdflatex", "tectonic"]
        else:
            candidates = ["tectonic", "latexmk", "pdflatex"]
    else:
        candidates = [chosen]
    available = [c for c in candidates if shutil.which(c)]
    if not available:
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "latex_engine_missing",
                    "detail": "No LaTeX engine found. Install `tectonic` (recommended) or TeXLive.",
                    "tried": candidates,
                },
                ensure_ascii=False,
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1)

    eng = available[0]
    workdir = tex_path.parent
    if eng == "tectonic":
        cmd = [
            "tectonic",
            "--outdir",
            str(out_pdf.parent.resolve()),
            str(tex_path.resolve()),
        ]
    elif eng == "latexmk":
        cmd = [
            "latexmk",
            "-pdf",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-outdir=" + str(out_pdf.parent.resolve()),
            str(tex_path.name),
        ]
    elif eng == "pdflatex":
        cmd = [
            "pdflatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-output-directory",
            str(out_pdf.parent.resolve()),
            str(tex_path.name),
        ]
    else:
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "invalid_engine",
                    "detail": "engine must be: tectonic | latexmk | pdflatex",
                    "engine": eng,
                },
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1)

    if eng == "pdflatex" and has_bib and shutil.which("bibtex"):
        # Multiple-pass compilation with BibTeX.
        bib_base = (out_pdf.parent / tex_path.stem).resolve()
        bib_cmd = ["bibtex", str(bib_base)]
        cmds = [cmd, bib_cmd, cmd, cmd]
    else:
        cmds = [cmd]
    for c in cmds:
        proc = subprocess.run(
            c,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=180,
        )
        if proc.returncode != 0:
            typer.echo(
                json.dumps(
                    {
                        "ok": False,
                        "error": "latex_compile_failed",
                        "engine": eng,
                        "cmd": c,
                        "stderr_tail": (proc.stderr or "")[-2000:],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                err=True,
            )
            raise typer.Exit(code=1)

    produced = out_pdf.parent / f"{tex_path.stem}.pdf"
    if produced.is_file() and produced.resolve() != out_pdf.resolve():
        out_pdf.write_bytes(produced.read_bytes())
    if not out_pdf.is_file():
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "pdf_not_found",
                    "detail": "Compilation succeeded but output PDF was not found",
                    "expected": str(out_pdf.resolve()),
                },
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1)

    if not keep_tex and tex_path.is_file():
        tex_path.unlink()
    typer.echo(str(out_pdf.resolve()))


@phase4_app.command("bib")
def phase4_bib(
    snapshot: Path = typer.Option(
        Path("data/kg/corpus-snapshot.json"),
        "--snapshot",
        "-s",
        exists=True,
        dir_okay=False,
        help="Corpus snapshot JSON (default: data/kg/corpus-snapshot.json)",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output .bib path (default: data/manuscripts/references.bib)",
    ),
) -> None:
    """
    Generate a minimal BibTeX file from corpus snapshot Paper nodes.

    This is MVP-grade: emits @misc entries with title + howpublished.
    """

    try:
        snap = load_corpus_snapshot_document(snapshot)
    except (OSError, json.JSONDecodeError, TypeError) as e:
        typer.echo(
            json.dumps(
                {"ok": False, "error": "invalid_snapshot", "detail": str(e)},
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1) from e

    paths = get_paths()
    out = output or (paths.data_dir / "manuscripts" / "references.bib")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_references_bib_text_from_snapshot(snap), encoding="utf-8")
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
    include_artifacts: bool = typer.Option(
        False,
        "--include-artifacts",
        help="If present in experiment-report.json, copy artifacts into bundle/artifacts/",
    ),
    include_pdf: bool = typer.Option(
        False,
        "--include-pdf",
        help="Compile and include manuscript PDF in submission bundle (best-effort)",
    ),
    include_bib: bool = typer.Option(
        False,
        "--include-bib",
        help="Refresh references.bib from corpus and copy into submission bundle (best-effort)",
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
    try:
        report = _experiment_report_for_full_pipeline(
            paths=paths,
            confirmed_path=proposal,
            proposal=raw,
        )
    except ValueError as e:
        typer.echo(
            json.dumps(
                {
                    "ok": False,
                    "error": "phase3_scaffold",
                    "detail": str(e),
                },
                indent=2,
            ),
            err=True,
        )
        raise typer.Exit(code=1) from e
    exp_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_doc = _build_evaluation_summary(report=report, report_path=exp_out)
    eval_out.write_text(
        json.dumps(summary_doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    ms_out.parent.mkdir(parents=True, exist_ok=True)
    ms_out.write_text(
        _build_manuscript_markdown(
            proposal=raw,
            experiment_report=report,
            proposal_path=proposal,
            experiment_path=exp_out,
        )
        + "\n",
        encoding="utf-8",
    )
    if include_pdf:
        try:
            phase4_pdf(manuscript=ms_out)
        except typer.Exit:
            pass
    if include_bib:
        _refresh_references_bib_for_manuscript(paths, ms_out)

    bundle_out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(proposal, bundle_out / "proposal-confirmed.json")
    shutil.copy2(exp_out, bundle_out / "experiment-report.json")
    shutil.copy2(eval_out, bundle_out / "evaluation-summary.json")
    shutil.copy2(ms_out, bundle_out / "manuscript-draft.md")
    if include_pdf:
        pdf = ms_out.with_suffix(".pdf")
        if pdf.is_file():
            shutil.copy2(pdf, bundle_out / "manuscript-draft.pdf")
    if include_bib:
        bib = ms_out.with_name("references.bib")
        if bib.is_file():
            shutil.copy2(bib, bundle_out / "references.bib")

    if include_artifacts:
        artifacts = (
            report.get("artifacts") if isinstance(report.get("artifacts"), dict) else None
        )
        if isinstance(artifacts, dict):
            src_dir = artifacts.get("dir")
            if isinstance(src_dir, str) and src_dir.strip():
                src_path = Path(src_dir)
                if src_path.is_dir():
                    dst = bundle_out / "artifacts" / "phase3"
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(src_path, dst, dirs_exist_ok=True)
    _write_submission_manifest(
        bundle_out,
        include_pdf=include_pdf,
        include_bib=include_bib,
        include_artifacts=include_artifacts,
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
        None,
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
    expect_artifacts: bool = typer.Option(
        False,
        "--expect-artifacts",
        help="Fail if bundle/artifacts/phase3 is missing",
    ),
    expect_pdf: bool = typer.Option(
        False,
        "--expect-pdf",
        help="Fail if bundle/manuscript-draft.pdf is missing",
    ),
    expect_bib: bool = typer.Option(
        False,
        "--expect-bib",
        help="Fail if bundle/references.bib is missing",
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
    ea, ep, eb = _merge_expect_flags_from_checksums(
        expected_hashes,
        expect_artifacts=expect_artifacts,
        expect_pdf=expect_pdf,
        expect_bib=expect_bib,
    )
    detail, ok = _verify_submission_assets(
        bundle_dir=bundle_dir,
        archive=archive,
        expected_hashes=expected_hashes,
        expect_artifacts=ea,
        expect_pdf=ep,
        expect_bib=eb,
    )
    payload: dict[str, object] = {"ok": ok, **detail}

    if ok:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2), err=True)
    raise typer.Exit(code=1)
