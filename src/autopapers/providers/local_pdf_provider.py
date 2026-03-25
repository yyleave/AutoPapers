from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from autopapers.providers.base import PaperRef


@dataclass(frozen=True)
class LocalPdfProvider:
    """
    A provider that treats `query` as a local path (file or directory).

    This keeps PDF ingestion compliant: the user supplies the files.
    """

    name: str = "local_pdf"

    def search(self, *, query: str, limit: int = 5) -> list[PaperRef]:
        p = Path(query).expanduser().resolve()
        if p.is_file():
            if p.suffix.lower() != ".pdf":
                return []
            return [PaperRef(source=self.name, id=p.stem, title=p.name, pdf_url=str(p))]
        if p.is_dir():
            refs: list[PaperRef] = []
            for pdf in sorted(p.glob("*.pdf"))[:limit]:
                refs.append(
                    PaperRef(source=self.name, id=pdf.stem, title=pdf.name, pdf_url=str(pdf))
                )
            return refs
        return []

    def fetch_pdf(self, *, ref: PaperRef, dest_dir: Path) -> Path:
        if not ref.pdf_url:
            raise ValueError("No local path available for this ref")
        src = Path(ref.pdf_url).expanduser().resolve()
        if not src.exists():
            raise FileNotFoundError(src)
        dest_dir.mkdir(parents=True, exist_ok=True)
        out = dest_dir / src.name
        shutil.copyfile(src, out)
        return out

