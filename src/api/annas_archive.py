"""
Anna's Archive SciDB 论文下载器

通过 Anna's Archive 获取论文全文 PDF
"""

import re
import os
import time
import requests
from typing import Optional, List, Dict
from dataclasses import dataclass
from urllib.parse import quote


@dataclass
class SearchResult:
    """搜索结果"""
    title: str
    authors: str
    year: Optional[str]
    file_type: str
    size: str
    source: str
    url: str
    md5: Optional[str] = None


class AnnasArchiveClient:
    """Anna's Archive SciDB 客户端"""

    BASE_URL = "https://annas-archive.gl"
    SCIDB_URL = "https://annas-archive.gl/scidb"

    # 请求头
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    def __init__(self, download_dir: str = "./downloads"):
        self.download_dir = download_dir
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

        # 创建下载目录
        os.makedirs(download_dir, exist_ok=True)

    def search(
        self,
        query: str,
        page: int = 1,
        content_type: str = "book",
        sort: str = ""
    ) -> List[SearchResult]:
        """
        搜索论文/书籍

        Args:
            query: 搜索关键词（标题、作者、DOI等）
            page: 页码
            content_type: 内容类型
                - "book": 书籍
                - "journal_article": 期刊论文
                - "standalone_document": 独立文档
            sort: 排序方式
                - "": 默认
                - "newest": 最新
                - "oldest": 最旧
                - "smallest": 最小文件
                - "largest": 最大文件

        Returns:
            搜索结果列表
        """
        # 构建搜索 URL
        search_url = f"{self.BASE_URL}/search"

        params = {
            "q": query,
            "page": page,
        }

        if content_type:
            params["content"] = content_type
        if sort:
            params["sort"] = sort

        try:
            response = self.session.get(search_url, params=params, timeout=30)
            response.raise_for_status()

            return self._parse_search_results(response.text)

        except requests.exceptions.RequestException as e:
            print(f"搜索请求失败: {e}")
            return []

    def search_by_doi(self, doi: str) -> List[SearchResult]:
        """
        通过 DOI 搜索论文

        Args:
            doi: 论文 DOI

        Returns:
            搜索结果列表
        """
        return self.search(doi, content_type="journal_article")

    def search_by_title(self, title: str, author: str = None) -> List[SearchResult]:
        """
        通过标题和作者搜索

        Args:
            title: 论文标题
            author: 作者（可选）

        Returns:
            搜索结果列表
        """
        query = title
        if author:
            query = f"{title} {author}"

        return self.search(query, content_type="journal_article")

    def _parse_search_results(self, html: str) -> List[SearchResult]:
        """解析搜索结果页面"""
        results = []

        # 简单的 HTML 解析（实际使用建议用 BeautifulSoup）
        # 这里使用正则表达式进行基础解析

        # 匹配搜索结果项
        # 实际实现需要根据 Anna's Archive 的 HTML 结构调整
        import re

        # 匹配结果链接
        pattern = r'<a[^>]+href="(/md5/[^"]+)"[^>]*>.*?</a>'
        links = re.findall(pattern, html, re.DOTALL)

        # 匹配标题
        title_pattern = r'<h3[^>]*>(.*?)</h3>'
        titles = re.findall(title_pattern, html, re.DOTALL)

        # 匹配作者
        author_pattern = r'<div[^>]*class="[^"]*author[^"]*"[^>]*>(.*?)</div>'
        authors = re.findall(author_pattern, html, re.DOTALL)

        # 构建结果
        for i in range(min(len(links), len(titles))):
            result = SearchResult(
                title=self._clean_html(titles[i]) if i < len(titles) else "",
                authors=self._clean_html(authors[i]) if i < len(authors) else "",
                year=None,
                file_type="pdf",
                size="",
                source="Anna's Archive",
                url=f"{self.BASE_URL}{links[i]}",
                md5=links[i].split("/")[-1] if "/" in links[i] else None
            )
            results.append(result)

        return results

    def _clean_html(self, text: str) -> str:
        """清理 HTML 标签"""
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def get_download_info(self, md5: str) -> Optional[Dict]:
        """
        获取下载信息

        Args:
            md5: 文件 MD5 值

        Returns:
            下载信息字典
        """
        url = f"{self.BASE_URL}/md5/{md5}"

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            # 解析下载链接
            # 实际实现需要根据页面结构解析
            download_links = []

            # 匹配下载链接
            patterns = [
                r'href="(https?://[^"]*fast[^"]*\.partner[^"]*)"[^>]*>\s*⚡',
                r'href="(https?://[^"]*download[^"]*)"[^>]*',
            ]

            for pattern in patterns:
                links = re.findall(pattern, response.text)
                download_links.extend(links)

            if download_links:
                return {
                    "md5": md5,
                    "url": url,
                    "download_links": download_links
                }

            return None

        except requests.exceptions.RequestException as e:
            print(f"获取下载信息失败: {e}")
            return None

    def download(
        self,
        md5: str,
        filename: str = None,
        timeout: int = 120
    ) -> Optional[str]:
        """
        下载论文 PDF

        Args:
            md5: 文件 MD5 值
            filename: 保存的文件名（不含扩展名）
            timeout: 下载超时时间（秒）

        Returns:
            下载文件的完整路径，失败返回 None
        """
        # 获取下载信息
        info = self.get_download_info(md5)

        if not info or not info.get("download_links"):
            print(f"未找到下载链接: {md5}")
            return None

        # 尝试下载
        for link in info["download_links"]:
            try:
                print(f"尝试从 {link[:50]}... 下载")

                response = self.session.get(link, timeout=timeout, stream=True)
                response.raise_for_status()

                # 确定文件名
                if not filename:
                    content_disp = response.headers.get("content-disposition", "")
                    if "filename=" in content_disp:
                        filename = re.search(r'filename="?([^";]+)"?', content_disp).group(1)
                    else:
                        filename = f"paper_{md5}"

                if not filename.endswith(".pdf"):
                    filename += ".pdf"

                filepath = os.path.join(self.download_dir, filename)

                # 下载文件
                total_size = int(response.headers.get("content-length", 0))
                downloaded = 0

                with open(filepath, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                            # 显示进度
                            if total_size:
                                percent = (downloaded / total_size) * 100
                                print(f"\r下载进度: {percent:.1f}%", end="")

                print(f"\n下载完成: {filepath}")
                return filepath

            except requests.exceptions.RequestException as e:
                print(f"下载失败: {e}")
                continue

        return None

    def open_scidb(self):
        """
        打开 SciDB 页面（需要浏览器手动访问）

        SciDB 是 Anna's Archive 的学术数据库专用入口
        """
        print(f"请手动访问: {self.SCIDB_URL}")
        print("SciDB 提供更精准的学术论文搜索")


# ============ 使用示例 ============

if __name__ == "__main__":
    import webbrowser

    client = AnnasArchiveClient(download_dir="./downloads")

    # 示例 1: 搜索论文
    query = "Attention is all you need transformer"
    print(f"搜索: {query}")

    results = client.search_by_title(query)

    print(f"\n找到 {len(results)} 个结果:\n")

    for i, result in enumerate(results[:5], 1):
        print(f"{i}. {result.title}")
        print(f"   作者: {result.authors}")
        print(f"   链接: {result.url}")
        print()

    # 示例 2: 如果没有自动解析结果，打开浏览器手动搜索
    if not results:
        print("自动搜索无结果，请手动访问:")
        search_url = f"{client.SCIDB_URL}?q={quote(query)}"
        print(search_url)
        webbrowser.open(search_url)
