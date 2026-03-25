"""
论文获取工具

整合 AMiner API（获取元数据）和 Anna's Archive（获取全文）
"""

import os
import sys
import webbrowser
from urllib.parse import quote
from typing import List, Optional

# 添加路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.aminer_client import AMinerClient, Paper, format_paper_info
from api.annas_archive import AnnasArchiveClient, SearchResult


class PaperFetcher:
    """论文获取工具"""

    def __init__(
        self,
        aminer_token: str = None,
        download_dir: str = "./downloads"
    ):
        """
        初始化

        Args:
            aminer_token: AMiner API Token（可选，默认从环境变量读取）
            download_dir: PDF 下载目录
        """
        self.aminer = None
        self.aminer_token = aminer_token or os.environ.get("AMINER_API_KEY")
        self.annas = AnnasArchiveClient(download_dir=download_dir)

        # 如果有 token，初始化 AMiner 客户端
        if self.aminer_token:
            try:
                self.aminer = AMinerClient(self.aminer_token)
            except ValueError as e:
                print(f"警告: {e}")

    def search_papers(self, query: str, limit: int = 10) -> List[Paper]:
        """
        搜索论文（通过 AMiner）

        Args:
            query: 搜索关键词
            limit: 结果数量

        Returns:
            论文列表
        """
        if not self.aminer:
            print("错误: 未配置 AMiner API Token")
            print("请设置环境变量: export AMINER_API_KEY='your_token'")
            print("获取 Token: https://open.aminer.cn/open/board?tab=control")
            return []

        print(f"\n通过 AMiner 搜索: {query}")
        papers = self.aminer.search_by_title(query, limit=limit)

        return papers

    def get_fulltext(
        self,
        paper: Paper,
        auto_download: bool = False,
        open_browser: bool = True
    ) -> Optional[str]:
        """
        获取论文全文

        策略（优先级从高到低）：
        1. DOI 搜索（最精确）
        2. AMiner PDF 链接
        3. 标题+作者搜索
        4. 打开浏览器手动下载

        Args:
            paper: 论文对象
            auto_download: 是否自动下载
            open_browser: 是否在自动下载失败时打开浏览器

        Returns:
            下载文件的路径，失败返回 None
        """
        print(f"\n获取全文: {paper.title}")

        # 策略 1 (最高优先级): DOI 搜索 - 最精确
        if paper.doi:
            print(f"[优先] 通过 DOI 搜索: {paper.doi}")
            if open_browser:
                # 直接打开浏览器用 DOI 搜索
                search_url = f"{self.annas.BASE_URL}/search?q={quote(paper.doi)}&content=journal_article"
                print(f"打开: {search_url}")
                webbrowser.open(search_url)
            return None

        # 策略 2: 检查 AMiner PDF 链接
        if paper.pdf_url:
            print(f"AMiner 提供 PDF 链接: {paper.pdf_url}")
            if open_browser:
                webbrowser.open(paper.pdf_url)
            return None

        # 策略 3: 通过标题和作者搜索
        query = paper.title
        if paper.authors:
            query += f" {paper.authors[0]}"

        print(f"通过标题搜索: {query}")
        if open_browser:
            search_url = f"{self.annas.SCIDB_URL}?q={quote(query)}&content=journal_article"
            print(f"打开: {search_url}")
            webbrowser.open(search_url)

        return None

    def _download_best_result(
        self,
        results: List[SearchResult],
        filename: str
    ) -> Optional[str]:
        """下载最佳结果"""
        if not results:
            return None

        best = results[0]
        print(f"\n最佳匹配: {best.title}")

        if best.md5:
            return self.annas.download(best.md5, filename)

        if open_browser:
            webbrowser.open(best.url)

        return None

    def fetch(
        self,
        query: str,
        limit: int = 5,
        auto_download: bool = False
    ) -> List[Paper]:
        """
        完整流程：搜索论文 + 获取全文

        Args:
            query: 搜索关键词
            limit: 结果数量
            auto_download: 是否自动下载 PDF

        Returns:
            论文列表
        """
        # Step 1: 通过 AMiner 搜索
        papers = self.search_papers(query, limit)

        if not papers:
            print("未找到相关论文")
            return []

        # Step 2: 显示结果
        print(f"\n找到 {len(papers)} 篇论文:\n")
        for i, paper in enumerate(papers, 1):
            print(f"--- 论文 {i} ---")
            print(format_paper_info(paper))
            print()

        # Step 3: 获取全文
        print("\n" + "="*60)
        print("尝试获取全文 PDF...")
        print("="*60)

        for i, paper in enumerate(papers, 1):
            print(f"\n[{i}/{len(papers)}]")
            self.get_fulltext(paper, auto_download=auto_download)

        return papers


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="论文搜索与下载工具")
    parser.add_argument("query", nargs="?", default="Attention is all you need",
                        help="搜索关键词（标题、作者等）")
    parser.add_argument("--limit", "-l", type=int, default=5,
                        help="结果数量（默认5）")
    parser.add_argument("--download", "-d", action="store_true",
                        help="自动下载 PDF")
    parser.add_argument("--download-dir", "-o", default="./downloads",
                        help="下载目录（默认 ./downloads）")
    parser.add_argument("--no-browser", action="store_true",
                        help="不自动打开浏览器")

    args = parser.parse_args()

    # 检查 AMiner Token
    if not os.environ.get("AMINER_API_KEY"):
        print("="*60)
        print("警告: 未设置 AMINER_API_KEY 环境变量")
        print("="*60)
        print("\n将使用 Anna's Archive 直接搜索...")
        print("建议配置 AMiner API 获取更准确的论文元数据")
        print("\n获取 Token: https://open.aminer.cn/open/board?tab=control")
        print("设置环境变量: export AMINER_API_KEY='your_token'\n")

    # 创建获取器
    fetcher = PaperFetcher(download_dir=args.download_dir)

    # 执行搜索
    papers = fetcher.fetch(
        query=args.query,
        limit=args.limit,
        auto_download=args.download
    )

    return papers


if __name__ == "__main__":
    main()
