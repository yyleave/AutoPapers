from __future__ import annotations

from dataclasses import dataclass

from autopapers.providers.arxiv_provider import ArxivProvider
from autopapers.providers.base import Provider
from autopapers.providers.local_pdf_provider import LocalPdfProvider


@dataclass(frozen=True)
class ProviderRegistry:
    providers: dict[str, Provider]

    @classmethod
    def default(cls) -> ProviderRegistry:
        providers: dict[str, Provider] = {
            "arxiv": ArxivProvider(),
            "local_pdf": LocalPdfProvider(),
        }
        return cls(providers=providers)

    def get(self, name: str) -> Provider:
        try:
            return self.providers[name]
        except KeyError as e:
            avail = ", ".join(sorted(self.providers.keys()))
            raise KeyError(f"Unknown provider: {name}. Available: {avail}") from e

