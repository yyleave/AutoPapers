from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autopapers.config import Paths


def _iso_ts() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _serialize_refs(refs: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in refs:
        if is_dataclass(r) and not isinstance(r, type):
            out.append(asdict(r))  # type: ignore[arg-type]
        elif hasattr(r, "__dict__"):
            out.append(dict(r.__dict__))
        else:
            out.append({"value": repr(r)})
    return out


def write_search_record(
    paths: Paths,
    *,
    provider: str,
    query: str,
    refs: list[Any],
) -> Path:
    paths.papers_metadata_dir.mkdir(parents=True, exist_ok=True)
    ts = _iso_ts()
    payload: dict[str, Any] = {
        "type": "search",
        "created_at": ts,
        "provider": provider,
        "query": query,
        "count": len(refs),
        "results": _serialize_refs(refs),
    }
    out = paths.papers_metadata_dir / f"search-{ts}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def write_fetch_record(
    paths: Paths,
    *,
    source: str,
    paper_id: str,
    title: str | None,
    pdf_path: Path,
) -> Path:
    paths.papers_metadata_dir.mkdir(parents=True, exist_ok=True)
    ts = _iso_ts()
    payload: dict[str, Any] = {
        "type": "fetch",
        "created_at": ts,
        "source": source,
        "id": paper_id,
        "title": title,
        "pdf_path": str(pdf_path.resolve()),
    }
    out = paths.papers_metadata_dir / f"fetch-{ts}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def write_parse_manifest(
    *,
    pdf_path: Path,
    txt_path: Path,
    char_count: int,
    pages_total: int,
    pages_read: int,
    max_pages_config: int | None,
) -> Path:
    """Write <txt_stem>.manifest.json beside the extracted .txt."""

    ts = _iso_ts()
    out = txt_path.parent / f"{txt_path.stem}.manifest.json"
    payload: dict[str, Any] = {
        "type": "parse",
        "created_at": ts,
        "input_pdf": str(pdf_path.resolve()),
        "output_txt": str(txt_path.resolve()),
        "char_count": char_count,
        "pages_total": pages_total,
        "pages_read": pages_read,
        "max_pages": max_pages_config,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out
