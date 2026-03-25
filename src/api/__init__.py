"""
AutoPapers API 模块
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
