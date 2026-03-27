"""
论文获取工具（Legacy）

检索与直链下载路径与 `autopapers` 的 `AminerProvider` 对齐；多级回退下载仍使用 `PDFDownloader`。

对外推荐入口：`uv run autopapers`（见 README）。
遗留 CLI：`uv run paper-fetcher`（与主包一同由 `pyproject` 安装）。本模块保留用于迁移与对照。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Legacy 脚本：保证在「仅 python src/paper_fetcher.py」且未安装可编辑包时仍能导入 src/api
_here = Path(__file__).resolve().parent
_repo_root = _here.parent
for _p in (_repo_root, _here):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from api.aminer_client import AMinerClient, Paper
from api.pdf_downloader import DownloadResult, PDFDownloader
from autopapers.providers.aminer_provider import AminerProvider
from autopapers.providers.base import PaperRef


def _ref_to_paper(ref: PaperRef) -> Paper:
    return Paper(
        id=ref.id,
        title=ref.title or "",
        authors=list(ref.authors) if ref.authors else [],
        year=ref.year,
        doi=ref.doi,
        venue=ref.venue,
        url=ref.url,
        pdf_url=ref.pdf_url,
    )


def _paper_to_ref(paper: Paper) -> PaperRef:
    return PaperRef(
        source="aminer",
        id=paper.id,
        title=paper.title,
        pdf_url=paper.pdf_url,
        authors=tuple(paper.authors) if paper.authors else None,
        year=paper.year,
        doi=paper.doi,
        venue=paper.venue,
        url=paper.url,
    )


class PaperFetcher:
    """论文获取工具"""

    def __init__(
        self,
        aminer_token: str | None = None,
        download_dir: str = "./downloads",
    ):
        self._aminer_provider: AminerProvider | None = None
        self.aminer_token = aminer_token or os.environ.get("AMINER_API_KEY")
        self.downloader = PDFDownloader(download_dir=download_dir)

        if self.aminer_token:
            try:
                AMinerClient(self.aminer_token)
                self._aminer_provider = AminerProvider(api_token=self.aminer_token)
            except ValueError as e:
                print(f"警告: {e}")

    @property
    def aminer(self) -> AminerProvider | None:
        """兼容旧属性名：配置成功时返回与 CLI 一致的 AMiner provider。"""
        return self._aminer_provider

    def search_papers(self, query: str, limit: int = 10) -> list[Paper]:
        """通过 AMiner 搜索论文"""
        if not self._aminer_provider:
            print("错误: 未配置 AMiner API Token")
            print("请设置: export AMINER_API_KEY='your_token'")
            print("获取: https://open.aminer.cn/open/board?tab=control")
            return []

        print(f"\n搜索: {query}")
        refs = self._aminer_provider.search(query=query, limit=limit)
        return [_ref_to_paper(r) for r in refs]

    def download_pdf(self, paper: Paper) -> DownloadResult:
        """自动下载论文 PDF（优先 AMiner 直链，否则走 PDFDownloader 链）"""
        dest = Path(self.downloader.download_dir)
        direct = paper.pdf_url or (
            paper.url if paper.url and str(paper.url).startswith("http") else None
        )
        if self._aminer_provider and direct:
            ref = _paper_to_ref(paper)
            try:
                path = self._aminer_provider.fetch_pdf(ref=ref, dest_dir=dest)
                return DownloadResult(success=True, filepath=str(path), source="aminer_direct")
            except (OSError, ValueError):
                pass
        return self.downloader.download(
            title=paper.title,
            doi=paper.doi,
            authors=paper.authors,
        )

    def fetch(
        self,
        query: str,
        limit: int = 5,
        auto_download: bool = True,
    ) -> list[Paper]:
        """
        完整流程：搜索 + 下载

        Args:
            query: 搜索关键词
            limit: 结果数量
            auto_download: 是否自动下载 PDF
        """
        papers = self.search_papers(query, limit)

        if not papers:
            print("未找到相关论文")
            return []

        print(f"\n找到 {len(papers)} 篇论文:\n")
        for i, paper in enumerate(papers, 1):
            print(f"--- [{i}] ---")
            print(f"标题: {paper.title}")
            print(f"作者: {', '.join(paper.authors[:3])}")
            if paper.year:
                print(f"年份: {paper.year}")
            if paper.venue:
                print(f"来源: {paper.venue}")
            if paper.doi:
                print(f"DOI: {paper.doi}")
            print(f"链接: {paper.url}")
            print()

        if auto_download:
            print("\n" + "=" * 60)
            print("自动下载 PDF...")
            print("=" * 60)

            for i, paper in enumerate(papers, 1):
                print(f"\n[{i}/{len(papers)}] {paper.title[:50]}...")
                result = self.download_pdf(paper)

                if result.success:
                    print(f"  ✓ {result.source}: {result.filepath}")
                else:
                    print(f"  ✗ {result.error}")
                    if result.manual_url:
                        print(f"  手动: {result.manual_url}")

        return papers


def main():
    import argparse

    print(
        "提示: 推荐统一入口 `uv run autopapers papers aminer-search -q \"...\"` "
        "（或 AUTOPAPERS_PROVIDER=aminer 时使用 `papers search`）。"
        " 环境与可选依赖摘要: `uv run autopapers status` / `doctor`。\n",
        flush=True,
    )
    parser = argparse.ArgumentParser(description="论文搜索与下载")
    parser.add_argument(
        "query",
        nargs="?",
        default="Attention is all you need",
        help="搜索关键词",
    )
    parser.add_argument("--limit", "-l", type=int, default=3, help="结果数量")
    parser.add_argument("--no-download", action="store_true", help="不自动下载")
    parser.add_argument("--output", "-o", default="./downloads", help="下载目录")

    args = parser.parse_args()

    if not os.environ.get("AMINER_API_KEY"):
        print("警告: 未设置 AMINER_API_KEY")
        print("获取: https://open.aminer.cn/open/board?tab=control")
        print("设置: export AMINER_API_KEY='your_token'\n")

    fetcher = PaperFetcher(download_dir=args.output)
    fetcher.fetch(
        query=args.query,
        limit=args.limit,
        auto_download=not args.no_download,
    )


if __name__ == "__main__":
    main()
