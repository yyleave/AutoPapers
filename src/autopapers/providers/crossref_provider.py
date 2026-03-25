from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autopapers.providers.base import PaperRef
from autopapers.providers.polite_ua import polite_user_agent

CROSSREF_WORKS = "https://api.crossref.org/works"


def _pick_pdf_url(item: dict[str, Any]) -> str | None:
    for link in item.get("link") or []:
        if not isinstance(link, dict):
            continue
        url = link.get("URL") or link.get("url")
        if not url:
            continue
        ct = str(link.get("content-type") or "").lower()
        u = str(url)
        if "pdf" in ct or u.lower().endswith(".pdf"):
            return u
    return None


def _title(item: dict[str, Any]) -> str | None:
    titles = item.get("title")
    if isinstance(titles, list) and titles:
        t0 = titles[0]
        return str(t0) if t0 else None
    return None


@dataclass(frozen=True)
class CrossrefProvider:
    """
    Crossref REST API (works search). No API key; set CROSSREF_MAILTO or OPENALEX_MAILTO.

    https://github.com/CrossRef/rest-api-doc
    """

    name: str = "crossref"

    def search(self, *, query: str, limit: int = 5) -> list[PaperRef]:
        rows = min(max(limit, 1), 100)
        params = urllib.parse.urlencode({"query": query, "rows": rows})
        url = f"{CROSSREF_WORKS}?{params}"
        req = urllib.request.Request(
            url, headers={"User-Agent": polite_user_agent(context="crossref")}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
        data = json.loads(raw.decode("utf-8"))
        msg = data.get("message") or {}
        items = msg.get("items") or []
        if not isinstance(items, list):
            return []
        refs: list[PaperRef] = []
        for item in items[:limit]:
            if not isinstance(item, dict):
                continue
            doi = item.get("DOI")
            if not doi:
                continue
            refs.append(
                PaperRef(
                    source=self.name,
                    id=str(doi),
                    title=_title(item),
                    pdf_url=_pick_pdf_url(item),
                )
            )
        return refs

    def fetch_pdf(self, *, ref: PaperRef, dest_dir: Path) -> Path:
        if not ref.pdf_url:
            raise ValueError(
                "No PDF link in Crossref record; use --pdf-url, or try arxiv / openalex."
            )
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in ref.id)[:80]
        out = dest_dir / f"{safe}.pdf"
        req = urllib.request.Request(
            ref.pdf_url, headers={"User-Agent": polite_user_agent(context="crossref-pdf")}
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            out.write_bytes(resp.read())
        return out
