from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autopapers.providers.base import PaperRef

OPENALEX_WORKS = "https://api.openalex.org/works"


def _user_agent() -> str:
    mail = os.environ.get("OPENALEX_MAILTO", "").strip()
    if mail:
        return f"AutoPapers/0.1 (mailto:{mail})"
    return "AutoPapers/0.1 (https://github.com/yyleave/AutoPapers; respectful polling)"


def _openalex_short_id(work_url: str) -> str:
    if not work_url:
        return ""
    return work_url.rstrip("/").rsplit("/", 1)[-1]


def _pick_pdf_url(w: dict[str, Any]) -> str | None:
    pl = w.get("primary_location") or {}
    if isinstance(pl, dict) and pl.get("pdf_url"):
        return str(pl["pdf_url"])
    boa = w.get("best_oa_location") or {}
    if isinstance(boa, dict) and boa.get("pdf_url"):
        return str(boa["pdf_url"])
    cu = w.get("content_urls") or {}
    if isinstance(cu, dict) and cu.get("pdf_url"):
        return str(cu["pdf_url"])
    for loc in w.get("locations") or []:
        if not isinstance(loc, dict):
            continue
        pu = loc.get("pdf_url")
        if pu:
            return str(pu)
    oa = w.get("open_access") or {}
    if isinstance(oa, dict):
        url = oa.get("oa_url")
        if url and str(url).lower().endswith(".pdf"):
            return str(url)
    return None


@dataclass(frozen=True)
class OpenAlexProvider:
    """
    OpenAlex Works search (no API key; be polite, see OPENALEX_MAILTO).

    Docs: https://docs.openalex.org/how-to-use-the-api/api-overview
    """

    name: str = "openalex"

    def search(self, *, query: str, limit: int = 5) -> list[PaperRef]:
        params = urllib.parse.urlencode(
            {"search": query, "per_page": min(max(limit, 1), 200)}
        )
        url = f"{OPENALEX_WORKS}?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": _user_agent()})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
        data = json.loads(raw.decode("utf-8"))
        results = data.get("results") or []
        if not isinstance(results, list):
            return []
        refs: list[PaperRef] = []
        for w in results[:limit]:
            if not isinstance(w, dict):
                continue
            wid = w.get("id", "")
            short_id = _openalex_short_id(str(wid))
            title = (w.get("title") or w.get("display_name") or "") or None
            pdf_url = _pick_pdf_url(w)
            refs.append(
                PaperRef(
                    source=self.name,
                    id=short_id or str(wid),
                    title=str(title) if title else None,
                    pdf_url=pdf_url,
                )
            )
        return refs

    def fetch_pdf(self, *, ref: PaperRef, dest_dir: Path) -> Path:
        if not ref.pdf_url:
            raise ValueError(
                "No PDF URL in OpenAlex record; try arXiv or another provider, "
                "or pass --pdf-url to papers fetch."
            )
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in ref.id)[:80]
        out = dest_dir / f"{safe}.pdf"
        req = urllib.request.Request(ref.pdf_url, headers={"User-Agent": _user_agent()})
        with urllib.request.urlopen(req, timeout=120) as resp:
            out.write_bytes(resp.read())
        return out
