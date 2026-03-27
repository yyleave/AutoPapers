from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from pathlib import Path

from autopapers.providers.base import PaperRef
from autopapers.repo_paths import ensure_legacy_api_on_path


@dataclass(frozen=True)
class AminerProvider:
    """
    AMiner metadata search (requires AMINER_API_KEY).

    Uses legacy [`api/aminer_client.py`](../../api/aminer_client.py) under `src/`.
    """

    name: str = "aminer"
    #: When set, passed to :class:`AMinerClient` instead of relying only on env.
    api_token: str | None = None

    def search(self, *, query: str, limit: int = 5) -> list[PaperRef]:
        ensure_legacy_api_on_path()
        from api.aminer_client import AMinerClient  # noqa: PLC0415

        client = AMinerClient(self.api_token)
        papers = client.paper_search(query, page=0, size=limit)
        if papers:
            paper_ids = [p.id for p in papers]
            detailed = client.paper_info(paper_ids)
            by_id = {d.id: d for d in detailed}
            papers = [by_id.get(p.id, p) for p in papers]
        refs: list[PaperRef] = []
        for p in papers:
            pdf = p.pdf_url or p.url
            refs.append(
                PaperRef(
                    source=self.name,
                    id=p.id,
                    title=p.title,
                    pdf_url=pdf,
                    authors=tuple(p.authors) if p.authors else None,
                    year=p.year,
                    doi=p.doi,
                    venue=p.venue,
                    url=p.url,
                )
            )
        return refs

    def fetch_pdf(self, *, ref: PaperRef, dest_dir: Path) -> Path:
        if not ref.pdf_url:
            raise ValueError("No pdf_url or url for this paper")
        url = ref.pdf_url
        if url.startswith("http"):
            dest_dir.mkdir(parents=True, exist_ok=True)
            safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in ref.id)[:80]
            out = dest_dir / f"{safe}.pdf"
            with urllib.request.urlopen(url, timeout=60) as resp:
                out.write_bytes(resp.read())
            return out
        path = Path(url).expanduser().resolve()
        if path.is_file():
            dest_dir.mkdir(parents=True, exist_ok=True)
            out = dest_dir / path.name
            out.write_bytes(path.read_bytes())
            return out
        raise ValueError(f"Cannot fetch PDF from: {url}")
