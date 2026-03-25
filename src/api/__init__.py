"""
Legacy API 包（`src/api/`）

新功能请接到 `autopapers` CLI 与 `src/autopapers/providers/`，本目录逐步收敛。
"""

from .aminer_client import AMinerClient, Paper, format_paper_info
from .annas_archive import AnnasArchiveClient, SearchResult

__all__ = [
    "AMinerClient",
    "Paper",
    "format_paper_info",
    "AnnasArchiveClient",
    "SearchResult",
]
