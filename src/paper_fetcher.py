"""
论文获取工具（Legacy）

整合 AMiner API（获取元数据）+ PDFDownloader（自动下载全文）

对外推荐入口：`uv run autopapers`（见 README）。本模块保留用于迁移与对照。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.aminer_client import AMinerClient, Paper, format_paper_info
from api.pdf_downloader import PDFDownloader, DownloadResult


class PaperFetcher:
    """论文获取工具"""

    def __init__(
        self,
        aminer_token: str = None,
        download_dir: str = "./downloads"
    ):
        self.aminer = None
        self.aminer_token = aminer_token or os.environ.get("AMINER_API_KEY")
        self.downloader = PDFDownloader(download_dir=download_dir)

        if self.aminer_token:
            try:
                self.aminer = AMinerClient(self.aminer_token)
            except ValueError as e:
                print(f"警告: {e}")

    def search_papers(self, query: str, limit: int = 10) -> list:
        """通过 AMiner 搜索论文"""
        if not self.aminer:
            print("错误: 未配置 AMiner API Token")
            print("请设置: export AMINER_API_KEY='your_token'")
            print("获取: https://open.aminer.cn/open/board?tab=control")
            return []

        print(f"\n搜索: {query}")
        return self.aminer.search_by_title(query, limit=limit)

    def download_pdf(self, paper: Paper) -> DownloadResult:
        """自动下载论文 PDF"""
        return self.downloader.download(
            title=paper.title,
            doi=paper.doi,
            authors=paper.authors
        )

    def fetch(
        self,
        query: str,
        limit: int = 5,
        auto_download: bool = True
    ) -> list:
        """
        完整流程：搜索 + 下载

        Args:
            query: 搜索关键词
            limit: 结果数量
            auto_download: 是否自动下载 PDF
        """
        # 搜索
        papers = self.search_papers(query, limit)

        if not papers:
            print("未找到相关论文")
            return []

        # 显示结果
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

        # 下载
        if auto_download:
            print("\n" + "="*60)
            print("自动下载 PDF...")
            print("="*60)

            for i, paper in enumerate(papers, 1):
                print(f"\n[{i}/{len(papers)}] {paper.title[:50]}...")
                result = self.download_pdf(paper)

                if result.success:
                    print(f"  ✓ {result.source}: {result.filepath}")
                else:
                    print(f"  ✗ {result.error}")
                    if result.url:
                        print(f"  手动: {result.url}")

        return papers


def main():
    import argparse

    parser = argparse.ArgumentParser(description="论文搜索与下载")
    parser.add_argument("query", nargs="?", default="Attention is all you need",
                        help="搜索关键词")
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
        auto_download=not args.no_download
    )


if __name__ == "__main__":
    main()
