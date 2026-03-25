from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pypdf import PdfWriter
from typer.testing import CliRunner

from autopapers.cli import app
from autopapers.providers.aminer_provider import AminerProvider
from autopapers.providers.arxiv_provider import ArxivProvider
from autopapers.providers.base import PaperRef
from autopapers.providers.crossref_provider import CrossrefProvider
from autopapers.providers.openalex_provider import OpenAlexProvider
from autopapers.repo_paths import ensure_legacy_api_on_path


def _two_json_objects(stdout: str) -> tuple[dict, dict]:
    dec = json.JSONDecoder()
    s = stdout.strip()
    o1, i = dec.raw_decode(s)
    while i < len(s) and s[i].isspace():
        i += 1
    o2, _ = dec.raw_decode(s, i)
    return o1, o2


def _minimal_profile(path: Path, *, pdf_abs: str) -> None:
    doc = {
        "schema_version": "0.1",
        "user": {"languages": ["en"]},
        "background": {"domains": [], "skills": [], "constraints": []},
        "hardware": {"device": "other"},
        "research_intent": {
            "problem_statements": [],
            "keywords": [pdf_abs],
            "non_goals": [],
            "risk_tolerance": "medium",
        },
    }
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def _tiny_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with path.open("wb") as f:
        writer.write(f)


def test_phase1_run_fetch_first_no_op_when_zero_hits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    empty_dir = tmp_path / "empty_for_fetch"
    empty_dir.mkdir()
    prof = tmp_path / "p.json"
    prof.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "user": {"languages": ["en"]},
                "background": {"domains": [], "skills": [], "constraints": []},
                "hardware": {"device": "other"},
                "research_intent": {
                    "problem_statements": [],
                    "keywords": [str(empty_dir.resolve())],
                    "non_goals": [],
                    "risk_tolerance": "medium",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(
        app,
        [
            "phase1",
            "run",
            "--profile",
            str(prof),
            "--limit",
            "2",
            "--fetch-first",
        ],
        env={"AUTOPAPERS_PROVIDER": "local_pdf"},
    )
    assert r.exit_code == 0
    payload = json.loads(r.stdout.strip())
    assert payload["count"] == 0
    assert "pdf" not in payload


def test_phase1_run_empty_local_dir_writes_zero_count_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    empty_dir = tmp_path / "no_pdfs"
    empty_dir.mkdir()
    prof = tmp_path / "p.json"
    prof.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "user": {"languages": ["en"]},
                "background": {"domains": [], "skills": [], "constraints": []},
                "hardware": {"device": "other"},
                "research_intent": {
                    "problem_statements": [],
                    "keywords": [str(empty_dir.resolve())],
                    "non_goals": [],
                    "risk_tolerance": "medium",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(
        app,
        ["phase1", "run", "--profile", str(prof), "--limit", "3"],
        env={"AUTOPAPERS_PROVIDER": "local_pdf"},
    )
    assert r.exit_code == 0
    payload = json.loads(r.stdout)
    assert payload["count"] == 0
    meta = Path(payload["metadata_file"])
    assert json.loads(meta.read_text(encoding="utf-8"))["count"] == 0


def test_phase1_run_search_only_writes_search_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    pdf = tmp_path / "only_search.pdf"
    _tiny_pdf(pdf)
    prof = tmp_path / "p.json"
    _minimal_profile(prof, pdf_abs=str(pdf.resolve()))
    r = CliRunner().invoke(
        app,
        ["phase1", "run", "--profile", str(prof), "--limit", "1"],
        env={"AUTOPAPERS_PROVIDER": "local_pdf"},
    )
    assert r.exit_code == 0, r.stdout + r.stderr
    summary = json.loads(r.stdout)
    assert summary.get("count") == 1
    meta = Path(summary["metadata_file"])
    assert meta.is_file()
    row = json.loads(meta.read_text(encoding="utf-8"))
    assert row["type"] == "search"
    pdfs_dir = tmp_path / "data" / "papers" / "pdfs"
    assert not pdfs_dir.is_dir() or not any(pdfs_dir.glob("*.pdf"))


def test_phase1_dry_run_fallback_query_when_keywords_and_problems_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    prof = tmp_path / "p.json"
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
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(
        app,
        ["phase1", "run", "--profile", str(prof), "--dry-run"],
        env={"AUTOPAPERS_PROVIDER": "arxiv"},
    )
    assert r.exit_code == 0
    assert json.loads(r.stdout)["query"] == "machine learning"


def test_phase1_dry_run_builds_query_from_problem_statement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    prof = tmp_path / "p.json"
    prof.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "user": {"languages": ["en"]},
                "background": {"domains": [], "skills": [], "constraints": []},
                "hardware": {"device": "other"},
                "research_intent": {
                    "problem_statements": ["fairness in neural ranking"],
                    "keywords": [],
                    "non_goals": [],
                    "risk_tolerance": "medium",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(
        app,
        ["phase1", "run", "--profile", str(prof), "--dry-run"],
        env={"AUTOPAPERS_PROVIDER": "arxiv"},
    )
    assert r.exit_code == 0
    out = json.loads(r.stdout)
    assert out["dry_run"] is True
    assert "fairness" in out["query"]


def test_phase1_dry_run_no_search(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    prof = tmp_path / "p.json"
    prof.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "user": {"languages": ["en"]},
                "background": {"domains": [], "skills": [], "constraints": []},
                "hardware": {"device": "other"},
                "research_intent": {
                    "problem_statements": [],
                    "keywords": ["rl", "transformer"],
                    "non_goals": [],
                    "risk_tolerance": "medium",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    runner = CliRunner()
    r = runner.invoke(
        app,
        ["phase1", "run", "--profile", str(prof), "--dry-run", "--limit", "5"],
        env={"AUTOPAPERS_PROVIDER": "arxiv"},
    )
    assert r.exit_code == 0
    out = json.loads(r.stdout)
    assert out["dry_run"] is True
    assert "rl" in out["query"] and "transformer" in out["query"]
    assert out["provider"] == "arxiv"
    assert out["limit"] == 5
    assert not (tmp_path / "data").exists()


@patch.object(OpenAlexProvider, "search")
def test_phase1_run_openalex_mocked_writes_search_metadata(
    mock_search: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    mock_search.return_value = [
        PaperRef(
            source="openalex",
            id="W777",
            title="Mock work",
            pdf_url="https://example.org/a.pdf",
        ),
    ]
    prof = tmp_path / "p.json"
    prof.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "user": {"languages": ["en"]},
                "background": {"domains": [], "skills": [], "constraints": []},
                "hardware": {"device": "other"},
                "research_intent": {
                    "problem_statements": [],
                    "keywords": ["graph", "neural"],
                    "non_goals": [],
                    "risk_tolerance": "medium",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(
        app,
        ["phase1", "run", "--profile", str(prof), "--limit", "2"],
        env={"AUTOPAPERS_PROVIDER": "openalex"},
    )
    assert r.exit_code == 0, r.stdout + r.stderr
    summary = json.loads(r.stdout)
    assert summary["count"] == 1
    meta = Path(summary["metadata_file"])
    row = json.loads(meta.read_text(encoding="utf-8"))
    assert row["type"] == "search"
    assert row["provider"] == "openalex"
    assert row["query"] == "graph neural"
    mock_search.assert_called_once_with(query="graph neural", limit=2)


@patch.object(CrossrefProvider, "search")
def test_phase1_run_crossref_mocked_writes_search_metadata(
    mock_search: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    mock_search.return_value = [
        PaperRef(
            source="crossref",
            id="10.1000/xyz",
            title="Crossref mock",
            pdf_url=None,
        ),
    ]
    prof = tmp_path / "p.json"
    prof.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "user": {"languages": ["en"]},
                "background": {"domains": [], "skills": [], "constraints": []},
                "hardware": {"device": "other"},
                "research_intent": {
                    "problem_statements": [],
                    "keywords": ["doi", "semantics"],
                    "non_goals": [],
                    "risk_tolerance": "medium",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(
        app,
        ["phase1", "run", "--profile", str(prof), "--limit", "4"],
        env={"AUTOPAPERS_PROVIDER": "crossref"},
    )
    assert r.exit_code == 0, r.stdout + r.stderr
    summary = json.loads(r.stdout)
    assert summary["count"] == 1
    meta = Path(summary["metadata_file"])
    row = json.loads(meta.read_text(encoding="utf-8"))
    assert row["type"] == "search"
    assert row["provider"] == "crossref"
    assert row["query"] == "doi semantics"
    mock_search.assert_called_once_with(query="doi semantics", limit=4)


@patch.object(ArxivProvider, "search")
def test_phase1_run_arxiv_mocked_writes_search_metadata(
    mock_search: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    mock_search.return_value = [
        PaperRef(
            source="arxiv",
            id="2501.09999",
            title="ArXiv mock",
            pdf_url="https://arxiv.org/pdf/2501.09999.pdf",
        ),
    ]
    prof = tmp_path / "p.json"
    prof.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "user": {"languages": ["en"]},
                "background": {"domains": [], "skills": [], "constraints": []},
                "hardware": {"device": "other"},
                "research_intent": {
                    "problem_statements": [],
                    "keywords": ["attention", "mechanism"],
                    "non_goals": [],
                    "risk_tolerance": "medium",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(
        app,
        ["phase1", "run", "--profile", str(prof), "--limit", "3"],
        env={"AUTOPAPERS_PROVIDER": "arxiv"},
    )
    assert r.exit_code == 0, r.stdout + r.stderr
    summary = json.loads(r.stdout)
    assert summary["count"] == 1
    meta = Path(summary["metadata_file"])
    row = json.loads(meta.read_text(encoding="utf-8"))
    assert row["type"] == "search"
    assert row["provider"] == "arxiv"
    assert row["query"] == "attention mechanism"
    mock_search.assert_called_once_with(query="attention mechanism", limit=3)


@patch("api.aminer_client.AMinerClient")
def test_phase1_run_aminer_mocked_writes_search_metadata(
    mock_client_cls: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_legacy_api_on_path()
    from api.aminer_client import Paper

    monkeypatch.chdir(tmp_path)
    mock_inst = MagicMock()
    mock_client_cls.return_value = mock_inst
    p = Paper(
        id="phase1-aminer-1",
        title="Phase1 AM",
        authors=["B"],
        pdf_url="https://x/p.pdf",
    )
    mock_inst.paper_search.return_value = [p]
    mock_inst.paper_info.return_value = [p]

    prof = tmp_path / "p.json"
    prof.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "user": {"languages": ["en"]},
                "background": {"domains": [], "skills": [], "constraints": []},
                "hardware": {"device": "other"},
                "research_intent": {
                    "problem_statements": [],
                    "keywords": ["knowledge", "graph"],
                    "non_goals": [],
                    "risk_tolerance": "medium",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(
        app,
        ["phase1", "run", "--profile", str(prof), "--limit", "2"],
        env={"AUTOPAPERS_PROVIDER": "aminer"},
    )
    assert r.exit_code == 0, r.stdout + r.stderr
    summary = json.loads(r.stdout)
    assert summary["count"] == 1
    meta = Path(summary["metadata_file"])
    row = json.loads(meta.read_text(encoding="utf-8"))
    assert row["type"] == "search"
    assert row["provider"] == "aminer"
    assert row["query"] == "knowledge graph"
    mock_inst.paper_search.assert_called_once_with("knowledge graph", page=0, size=2)
    mock_inst.paper_info.assert_called_once_with(["phase1-aminer-1"])


@patch.object(OpenAlexProvider, "search")
def test_phase1_run_uses_problem_statement_when_keywords_empty(
    mock_search: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-dry-run: query falls back to first problem_statements when keywords are empty."""
    monkeypatch.chdir(tmp_path)
    mock_search.return_value = [
        PaperRef(
            source="openalex",
            id="W42",
            title="From problem statement",
            pdf_url=None,
        ),
    ]
    query_text = "causal inference under distribution shift"
    prof = tmp_path / "p.json"
    prof.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "user": {"languages": ["en"]},
                "background": {"domains": [], "skills": [], "constraints": []},
                "hardware": {"device": "other"},
                "research_intent": {
                    "problem_statements": [query_text],
                    "keywords": [],
                    "non_goals": [],
                    "risk_tolerance": "medium",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(
        app,
        ["phase1", "run", "--profile", str(prof), "--limit", "5"],
        env={"AUTOPAPERS_PROVIDER": "openalex"},
    )
    assert r.exit_code == 0, r.stdout + r.stderr
    summary = json.loads(r.stdout)
    assert summary["count"] == 1
    meta = Path(summary["metadata_file"])
    row = json.loads(meta.read_text(encoding="utf-8"))
    assert row["query"] == query_text
    mock_search.assert_called_once_with(query=query_text, limit=5)


@patch.object(ArxivProvider, "fetch_pdf")
@patch.object(ArxivProvider, "search")
def test_phase1_run_fetch_first_arxiv_mocked_writes_search_and_fetch(
    mock_search: MagicMock,
    mock_fetch: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    mock_search.return_value = [
        PaperRef(
            source="arxiv",
            id="2501.08888",
            title="Fetch mock",
            pdf_url="https://arxiv.org/pdf/2501.08888.pdf",
        ),
    ]
    out_pdf = tmp_path / "data" / "papers" / "pdfs" / "2501.08888.pdf"
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    out_pdf.write_bytes(b"%PDF-phase1")
    mock_fetch.return_value = out_pdf

    prof = tmp_path / "p.json"
    prof.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "user": {"languages": ["en"]},
                "background": {"domains": [], "skills": [], "constraints": []},
                "hardware": {"device": "other"},
                "research_intent": {
                    "problem_statements": [],
                    "keywords": ["gnn"],
                    "non_goals": [],
                    "risk_tolerance": "medium",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(
        app,
        [
            "phase1",
            "run",
            "--profile",
            str(prof),
            "--limit",
            "1",
            "--fetch-first",
        ],
        env={"AUTOPAPERS_PROVIDER": "arxiv"},
    )
    assert r.exit_code == 0, r.stdout + r.stderr
    summary, fetch_payload = _two_json_objects(r.stdout)
    assert summary["count"] == 1
    assert Path(summary["metadata_file"]).is_file()
    assert Path(fetch_payload["pdf"]).resolve() == out_pdf.resolve()
    assert Path(fetch_payload["fetch_metadata"]).is_file()
    fetch_row = json.loads(Path(fetch_payload["fetch_metadata"]).read_text(encoding="utf-8"))
    assert fetch_row["type"] == "fetch"
    assert fetch_row["id"] == "2501.08888"
    mock_search.assert_called_once_with(query="gnn", limit=1)
    mock_fetch.assert_called_once()


@patch.object(AminerProvider, "fetch_pdf")
@patch("api.aminer_client.AMinerClient")
def test_phase1_run_fetch_first_aminer_mocked_writes_search_and_fetch(
    mock_client_cls: MagicMock,
    mock_fetch: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_legacy_api_on_path()
    from api.aminer_client import Paper

    monkeypatch.chdir(tmp_path)
    mock_inst = MagicMock()
    mock_client_cls.return_value = mock_inst
    ap = Paper(
        id="aminer-ph1-1",
        title="AM fetch",
        authors=["C"],
        pdf_url="https://static.example/doc.pdf",
    )
    mock_inst.paper_search.return_value = [ap]
    mock_inst.paper_info.return_value = [ap]

    out_pdf = tmp_path / "data" / "papers" / "pdfs" / "aminer-ph1-1.pdf"
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    out_pdf.write_bytes(b"%PDF-aminer-fetch")
    mock_fetch.return_value = out_pdf

    prof = tmp_path / "p.json"
    prof.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "user": {"languages": ["en"]},
                "background": {"domains": [], "skills": [], "constraints": []},
                "hardware": {"device": "other"},
                "research_intent": {
                    "problem_statements": [],
                    "keywords": ["multi", "hop"],
                    "non_goals": [],
                    "risk_tolerance": "medium",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(
        app,
        [
            "phase1",
            "run",
            "--profile",
            str(prof),
            "--limit",
            "1",
            "--fetch-first",
        ],
        env={"AUTOPAPERS_PROVIDER": "aminer"},
    )
    assert r.exit_code == 0, r.stdout + r.stderr
    summary, fetch_payload = _two_json_objects(r.stdout)
    assert summary["count"] == 1
    search_row = json.loads(Path(summary["metadata_file"]).read_text(encoding="utf-8"))
    assert search_row["provider"] == "aminer"
    assert Path(fetch_payload["pdf"]).resolve() == out_pdf.resolve()
    fetch_row = json.loads(Path(fetch_payload["fetch_metadata"]).read_text(encoding="utf-8"))
    assert fetch_row["type"] == "fetch"
    assert fetch_row["id"] == "aminer-ph1-1"
    assert fetch_row["source"] == "aminer"
    mock_inst.paper_search.assert_called_once_with("multi hop", page=0, size=1)
    mock_inst.paper_info.assert_called_once_with(["aminer-ph1-1"])
    mock_fetch.assert_called_once()


@patch.object(ArxivProvider, "fetch_pdf")
@patch.object(ArxivProvider, "search")
def test_phase1_run_parse_fetched_arxiv_mocked_writes_txt_and_manifest(
    mock_search: MagicMock,
    mock_fetch: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    mock_search.return_value = [
        PaperRef(
            source="arxiv",
            id="2501.07777",
            title="Parse chain",
            pdf_url="https://arxiv.org/pdf/2501.07777.pdf",
        ),
    ]
    out_pdf = tmp_path / "data" / "papers" / "pdfs" / "2501.07777.pdf"
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    _tiny_pdf(out_pdf)
    mock_fetch.return_value = out_pdf

    prof = tmp_path / "p.json"
    prof.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "user": {"languages": ["en"]},
                "background": {"domains": [], "skills": [], "constraints": []},
                "hardware": {"device": "other"},
                "research_intent": {
                    "problem_statements": [],
                    "keywords": ["parse-chain"],
                    "non_goals": [],
                    "risk_tolerance": "medium",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(
        app,
        [
            "phase1",
            "run",
            "--profile",
            str(prof),
            "--limit",
            "1",
            "--fetch-first",
            "--parse-fetched",
            "--parse-max-pages",
            "1",
        ],
        env={"AUTOPAPERS_PROVIDER": "arxiv"},
    )
    assert r.exit_code == 0, r.stdout + r.stderr
    summary, payload = _two_json_objects(r.stdout)
    assert summary["count"] == 1
    assert Path(str(payload["pdf"])).is_file()
    txt = Path(str(payload["parsed_txt"]))
    assert txt.name == "2501.07777.txt"
    assert txt.is_file()
    man = Path(str(payload["parse_manifest"]))
    assert man.is_file()
    man_doc = json.loads(man.read_text(encoding="utf-8"))
    assert man_doc["type"] == "parse"
    assert man_doc["input_pdf"] == str(out_pdf.resolve())
    assert man_doc["pages_read"] >= 1
    mock_search.assert_called_once_with(query="parse-chain", limit=1)
    mock_fetch.assert_called_once()


@patch.object(AminerProvider, "fetch_pdf")
@patch("api.aminer_client.AMinerClient")
def test_phase1_run_parse_fetched_aminer_mocked_writes_txt_and_manifest(
    mock_client_cls: MagicMock,
    mock_fetch: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_legacy_api_on_path()
    from api.aminer_client import Paper

    monkeypatch.chdir(tmp_path)
    mock_inst = MagicMock()
    mock_client_cls.return_value = mock_inst
    ap = Paper(
        id="aminer-parse-1",
        title="AM parse",
        authors=["D"],
        pdf_url="https://x/y.pdf",
    )
    mock_inst.paper_search.return_value = [ap]
    mock_inst.paper_info.return_value = [ap]

    out_pdf = tmp_path / "data" / "papers" / "pdfs" / "aminer-parse-1.pdf"
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    _tiny_pdf(out_pdf)
    mock_fetch.return_value = out_pdf

    prof = tmp_path / "p.json"
    prof.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "user": {"languages": ["en"]},
                "background": {"domains": [], "skills": [], "constraints": []},
                "hardware": {"device": "other"},
                "research_intent": {
                    "problem_statements": [],
                    "keywords": ["aminer-parse-chain"],
                    "non_goals": [],
                    "risk_tolerance": "medium",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    r = CliRunner().invoke(
        app,
        [
            "phase1",
            "run",
            "--profile",
            str(prof),
            "--limit",
            "1",
            "--fetch-first",
            "--parse-fetched",
            "--parse-max-pages",
            "1",
        ],
        env={"AUTOPAPERS_PROVIDER": "aminer"},
    )
    assert r.exit_code == 0, r.stdout + r.stderr
    summary, payload = _two_json_objects(r.stdout)
    assert summary["count"] == 1
    assert Path(str(payload["pdf"])).is_file()
    txt = Path(str(payload["parsed_txt"]))
    assert txt.name == "aminer-parse-1.txt"
    assert txt.is_file()
    man = Path(str(payload["parse_manifest"]))
    assert man.is_file()
    man_doc = json.loads(man.read_text(encoding="utf-8"))
    assert man_doc["type"] == "parse"
    assert man_doc["input_pdf"] == str(out_pdf.resolve())
    assert man_doc["pages_read"] >= 1
    mock_inst.paper_search.assert_called_once_with("aminer-parse-chain", page=0, size=1)
    mock_inst.paper_info.assert_called_once_with(["aminer-parse-1"])
    mock_fetch.assert_called_once()


def test_phase1_parse_fetched_requires_fetch_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    prof = tmp_path / "p.json"
    _minimal_profile(prof, pdf_abs=str(tmp_path / "x.pdf"))
    runner = CliRunner()
    r = runner.invoke(
        app,
        ["phase1", "run", "--profile", str(prof), "--parse-fetched"],
        env={"AUTOPAPERS_PROVIDER": "local_pdf"},
    )
    assert r.exit_code == 1


def test_phase1_parse_fetched_writes_parsed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    pdf = tmp_path / "doc.pdf"
    _tiny_pdf(pdf)
    prof = tmp_path / "p.json"
    _minimal_profile(prof, pdf_abs=str(pdf.resolve()))

    runner = CliRunner()
    r = runner.invoke(
        app,
        [
            "phase1",
            "run",
            "--profile",
            str(prof),
            "--fetch-first",
            "--parse-fetched",
            "--limit",
            "1",
        ],
        env={"AUTOPAPERS_PROVIDER": "local_pdf"},
    )
    assert r.exit_code == 0, r.stdout + r.stderr
    parsed = tmp_path / "data" / "papers" / "parsed" / "doc.txt"
    assert parsed.is_file()
    man = tmp_path / "data" / "papers" / "parsed" / "doc.manifest.json"
    assert man.is_file()
