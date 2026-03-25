from __future__ import annotations

from pathlib import Path
from typing import Literal

from autopapers.config import Paths

MetadataKind = Literal["search", "fetch", "any"]


def newest_papers_metadata(paths: Paths, *, kind: MetadataKind) -> Path | None:
    """Return the newest *.json in papers metadata dir filtered by filename prefix."""

    d = paths.papers_metadata_dir
    if not d.is_dir():
        return None
    candidates: list[Path] = []
    for f in d.glob("*.json"):
        if kind == "search" and not f.name.startswith("search-"):
            continue
        if kind == "fetch" and not f.name.startswith("fetch-"):
            continue
        candidates.append(f)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)
