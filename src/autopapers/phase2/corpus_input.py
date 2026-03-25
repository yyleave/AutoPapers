from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from autopapers.config import Paths

DEFAULT_SNAPSHOT = "corpus-snapshot.json"
MAX_CHARS = 20_000
_MAX_EXTRACTS = 8
_SNIPPET_PER_FILE = 2_000
_MAX_PAPERS_LIST = 20


def format_snapshot_for_proposal(data: dict[str, Any], *, max_chars: int = MAX_CHARS) -> str:
    """
    Turn a corpus-snapshot dict into human-readable context for proposal drafting.

    Includes short Paper lines and text snippets from TextExtract nodes when files exist.
    """
    nodes_raw = data.get("nodes")
    if not isinstance(nodes_raw, list):
        return json.dumps(data, ensure_ascii=False)[:max_chars]

    nodes: list[dict[str, Any]] = [n for n in nodes_raw if isinstance(n, dict)]
    edges = data.get("edges") or []
    edge_n = len(edges) if isinstance(edges, list) else 0

    parts: list[str] = [
        f"Corpus graph: {len(nodes)} nodes, {edge_n} edges "
        f"(snapshot schema {data.get('schema_version', '?')})."
    ]

    papers = [n for n in nodes if n.get("type") == "Paper"][:_MAX_PAPERS_LIST]
    for p in papers:
        label = p.get("label") or "(no title)"
        src = p.get("source") or "?"
        ext = p.get("external_id") or "?"
        parts.append(f"- Paper: {label} | {src}:{ext}")

    extracts = [n for n in nodes if n.get("type") == "TextExtract"][:_MAX_EXTRACTS]
    for ex in extracts:
        outp = ex.get("output_txt")
        if not outp:
            continue
        path = Path(str(outp))
        label = ex.get("label") or path.name
        if path.is_file():
            snippet = path.read_text(encoding="utf-8", errors="replace")[:_SNIPPET_PER_FILE]
            parts.append(f"--- Extract: {label} ({path.name}) ---\n{snippet}")
        else:
            parts.append(f"--- Extract: {label} (missing file {path}) ---")

    out = "\n\n".join(parts).strip()
    return out[:max_chars]


def load_corpus_text_for_proposal(
    paths: Paths,
    corpus: Path | None,
) -> tuple[str, Path | None]:
    """
    Resolve corpus text for proposal drafting.

    If ``corpus`` is given, read that file. Otherwise use
    ``paths.kg_dir / corpus-snapshot.json`` when it exists.

    When the file is JSON with a ``nodes`` list (corpus snapshot), format it into
    summaries plus TextExtract file snippets instead of raw truncated JSON.
    """
    if corpus is not None:
        raw_text = corpus.read_text(encoding="utf-8")
        path_used: Path | None = corpus
    else:
        default = paths.kg_dir / DEFAULT_SNAPSHOT
        if not default.is_file():
            return "", None
        raw_text = default.read_text(encoding="utf-8")
        path_used = default

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return raw_text[:MAX_CHARS], path_used

    if isinstance(data, dict) and isinstance(data.get("nodes"), list):
        return format_snapshot_for_proposal(data, max_chars=MAX_CHARS), path_used

    return raw_text[:MAX_CHARS], path_used
