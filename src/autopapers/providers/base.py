from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class PaperRef:
    source: str
    id: str
    title: str | None = None
    pdf_url: str | None = None


class Provider(Protocol):
    name: str

    def search(self, *, query: str, limit: int = 5) -> list[PaperRef]: ...

    def fetch_pdf(self, *, ref: PaperRef, dest_dir: Path) -> Path: ...

