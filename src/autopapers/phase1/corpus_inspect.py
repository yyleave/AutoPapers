from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path
from typing import Any


def load_corpus_snapshot_document(path: Path) -> dict[str, Any]:
    """
    Parse a corpus snapshot JSON file into a dict.

    Raises ``json.JSONDecodeError`` or ``TypeError`` if not a JSON object.
    """

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("Corpus snapshot must be a JSON object")
    return data


def summarize_corpus_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    """
    Aggregate node/edge counts from a corpus-snapshot dict (no I/O).
    """

    nodes_raw = data.get("nodes")
    edges_raw = data.get("edges")
    nodes = nodes_raw if isinstance(nodes_raw, list) else []
    edges = edges_raw if isinstance(edges_raw, list) else []

    by_type: dict[str, int] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        t = str(n.get("type", "?"))
        by_type[t] = by_type.get(t, 0) + 1

    by_rel: dict[str, int] = {}
    for e in edges:
        if not isinstance(e, dict):
            continue
        r = str(e.get("relation", "?"))
        by_rel[r] = by_rel.get(r, 0) + 1

    return {
        "schema_version": data.get("schema_version"),
        "built_at": data.get("built_at"),
        "node_total": len(nodes),
        "edge_total": len(edges),
        "nodes_by_type": dict(sorted(by_type.items())),
        "edges_by_relation": dict(sorted(by_rel.items())),
    }


def snapshot_edges_to_csv(data: dict[str, Any]) -> str:
    """Serialize snapshot ``edges`` to CSV (header: source,target,relation)."""

    edges_raw = data.get("edges")
    edges = edges_raw if isinstance(edges_raw, list) else []
    buf = StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["source", "target", "relation"])
    for e in edges:
        if not isinstance(e, dict):
            continue
        w.writerow(
            [
                e.get("source", ""),
                e.get("target", ""),
                e.get("relation", ""),
            ]
        )
    return buf.getvalue()
