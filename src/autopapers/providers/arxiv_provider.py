from __future__ import annotations

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from autopapers.providers.base import PaperRef

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def _arxiv_id_from_entry_id(entry_id: str) -> str:
    # entry_id like: http://arxiv.org/abs/2501.01234v1
    m = re.search(r"/abs/([^/]+)$", entry_id)
    return m.group(1) if m else entry_id


@dataclass(frozen=True)
class ArxivProvider:
    name: str = "arxiv"

    def search(self, *, query: str, limit: int = 5) -> list[PaperRef]:
        q = urllib.parse.quote(query)
        url = f"https://export.arxiv.org/api/query?search_query=all:{q}&start=0&max_results={limit}"
        with urllib.request.urlopen(url, timeout=20) as resp:
            raw = resp.read()

        root = ET.fromstring(raw)
        refs: list[PaperRef] = []
        for entry in root.findall("atom:entry", ATOM_NS):
            entry_id = entry.findtext("atom:id", default="", namespaces=ATOM_NS)
            title = (entry.findtext("atom:title", default="", namespaces=ATOM_NS) or "").strip()
            arxiv_id = _arxiv_id_from_entry_id(entry_id)

            pdf_url = None
            for link in entry.findall("atom:link", ATOM_NS):
                if link.attrib.get("title") == "pdf":
                    pdf_url = link.attrib.get("href")
                    break
            if not pdf_url:
                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

            refs.append(PaperRef(source=self.name, id=arxiv_id, title=title, pdf_url=pdf_url))
        return refs

    def fetch_pdf(self, *, ref: PaperRef, dest_dir: Path) -> Path:
        if not ref.pdf_url:
            raise ValueError("No pdf_url available for this ref")
        dest_dir.mkdir(parents=True, exist_ok=True)
        out = dest_dir / f"{ref.id}.pdf"
        with urllib.request.urlopen(ref.pdf_url, timeout=60) as resp:
            out.write_bytes(resp.read())
        return out

