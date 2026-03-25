from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autopapers.config import Paths


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _paper_node_id(source: str, pid: str) -> str:
    return f"paper:{source}:{pid}"


def _query_node_id(query: str) -> str:
    q = query.strip()[:200]
    safe = re.sub(r"\s+", " ", q)
    return f"query:{hash(safe) & 0xFFFFFFFFFFFFF:x}"


def build_corpus_snapshot(
    paths: Paths,
    *,
    profile_path: Path | None = None,
) -> dict[str, Any]:
    """
    Merge Phase 1 metadata JSON files into a single JSON graph (MVP for KG).

    Nodes: Paper, SearchQuery, Fetch, User (optional).
    Edges: SEARCHED_FOR, FETCHED (stub relations for downstream tooling).
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen_node: set[str] = set()

    def add_node(nid: str, payload: dict[str, Any]) -> None:
        if nid in seen_node:
            return
        seen_node.add(nid)
        nodes.append({"id": nid, **payload})

    def add_edge(src: str, dst: str, rel: str, meta: dict[str, Any] | None = None) -> None:
        edges.append(
            {
                "source": src,
                "target": dst,
                "relation": rel,
                "meta": meta or {},
            }
        )

    if paths.papers_metadata_dir.is_dir():
        for meta_file in sorted(paths.papers_metadata_dir.glob("*.json")):
            try:
                row = json.loads(meta_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            kind = row.get("type")
            created = row.get("created_at", "")
            if kind == "search":
                q = str(row.get("query", ""))
                qid = _query_node_id(q)
                add_node(
                    qid,
                    {
                        "type": "SearchQuery",
                        "label": q[:300],
                        "created_at": created,
                        "provider": row.get("provider"),
                        "metadata_file": str(meta_file),
                    },
                )
                for r in row.get("results") or []:
                    if not isinstance(r, dict):
                        continue
                    src = str(r.get("source", ""))
                    pid = str(r.get("id", ""))
                    if not src or not pid:
                        continue
                    nid = _paper_node_id(src, pid)
                    add_node(
                        nid,
                        {
                            "type": "Paper",
                            "label": r.get("title"),
                            "pdf_url": r.get("pdf_url"),
                            "source": src,
                            "external_id": pid,
                        },
                    )
                    add_edge(qid, nid, "SEARCH_HIT", {"at": created})
            elif kind == "fetch":
                src = str(row.get("source", ""))
                pid = str(row.get("id", ""))
                pdf_path = row.get("pdf_path")
                if src and pid:
                    nid = _paper_node_id(src, pid)
                    add_node(
                        nid,
                        {
                            "type": "Paper",
                            "label": row.get("title"),
                            "source": src,
                            "external_id": pid,
                            "pdf_path": pdf_path,
                        },
                    )
                    fetch_id = f"fetch:{hash(str(meta_file)) & 0xFFFFFFFFFFFFF:x}"
                    add_node(
                        fetch_id,
                        {
                            "type": "Fetch",
                            "label": str(pdf_path)[:200] if pdf_path else "fetch",
                            "created_at": created,
                            "metadata_file": str(meta_file),
                        },
                    )
                    add_edge(fetch_id, nid, "FETCHED", {"at": created})

    if profile_path and profile_path.is_file():
        uid = "user:profile"
        prof = json.loads(profile_path.read_text(encoding="utf-8"))
        add_node(
            uid,
            {
                "type": "User",
                "label": prof.get("user", {}).get("display_name") or "profile",
                "schema_version": prof.get("schema_version"),
                "path": str(profile_path.resolve()),
            },
        )
        intent = prof.get("research_intent") or {}
        for kw in intent.get("keywords") or []:
            if not isinstance(kw, str) or not kw.strip():
                continue
            kid = _query_node_id(kw)
            add_node(
                kid,
                {"type": "Keyword", "label": kw.strip(), "from_profile": True},
            )
            add_edge(uid, kid, "INTERESTED_IN", {})

    return {
        "schema_version": "0.1",
        "built_at": _now_iso(),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }


def write_corpus_snapshot(paths: Paths, snapshot: dict[str, Any]) -> Path:
    paths.kg_dir.mkdir(parents=True, exist_ok=True)
    out = paths.kg_dir / "corpus-snapshot.json"
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out
