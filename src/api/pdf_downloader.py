"""
PDF 下载器 - 完整版

优先级：
1. arXiv（免费无限制）
2. Unpaywall（合法开放获取）
3. Semantic Scholar（AI/CS/生物医学）
4. Playwright + Anna's Archive（全领域）
"""

import os
import re
import asyncio
import requests
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class DownloadResult:
    success: bool
    filepath: Optional[str] = None
    source: Optional[str] = None
    error: Optional[str] = None
    manual_url: Optional[str] = None


class PDFDownloader:
    """PDF 自动下载器"""

    def __init__(self, download_dir: str = "./downloads", email: str = "research@example.com"):
        self.download_dir = download_dir
        self.email = email
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        os.makedirs(download_dir, exist_ok=True)

    def download(
        self,
        title: str = None,
        doi: str = None,
        authors: list = None
    ) -> DownloadResult:
        """自动下载论文"""
        filename = self._make_filename(title, doi)

        # 1. arXiv
        arxiv_id = self._extract_arxiv_id(doi, title)
        if arxiv_id:
            print(f"[1/4] arXiv: {arxiv_id}")
            result = self._download_arxiv(arxiv_id, filename)
            if result.success:
                return result

        # 2. Unpaywall
        if doi:
            print(f"[2/4] Unpaywall: {doi}")
            result = self._download_unpaywall(doi, filename)
            if result.success:
                return result

        # 3. Semantic Scholar
        if doi:
            print(f"[3/4] Semantic Scholar: {doi}")
            result = self._download_s2(doi, filename)
            if result.success:
                return result

        # 4. Anna's Archive (Playwright)
        print(f"[4/4] Anna's Archive (自动化)...")
        return self._download_annas(title, doi, filename)

    def _extract_arxiv_id(self, doi: str = None, title: str = None) -> Optional[str]:
        if doi:
            m = re.search(r'arxiv\.(\d{4}\.\d{4,5})', doi, re.I)
            if m:
                return m.group(1)
        return None

    def _download_arxiv(self, arxiv_id: str, filename: str) -> DownloadResult:
        url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        filepath = os.path.join(self.download_dir, f"arxiv_{arxiv_id}.pdf")
        return self._download_file(url, filepath, "arXiv")

    def _download_unpaywall(self, doi: str, filename: str) -> DownloadResult:
        api_url = f"https://api.unpaywall.org/v2/{doi}?email={self.email}"
        try:
            resp = requests.get(api_url, headers=self.headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if data.get("is_oa"):
                for loc in data.get("oa_locations", []):
                    pdf_url = loc.get("url_for_pdf")
                    if pdf_url:
                        filepath = os.path.join(self.download_dir, filename)
                        return self._download_file(pdf_url, filepath, "Unpaywall")

            return DownloadResult(success=False, error="No OA version")
        except Exception as e:
            return DownloadResult(success=False, error=str(e))

    def _download_s2(self, doi: str, filename: str) -> DownloadResult:
        api_url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=openAccessPdf"
        try:
            resp = requests.get(api_url, headers=self.headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            oa_pdf = data.get("openAccessPdf")
            if oa_pdf and oa_pdf.get("url"):
                filepath = os.path.join(self.download_dir, filename)
                return self._download_file(oa_pdf["url"], filepath, "Semantic Scholar")

            return DownloadResult(success=False, error="No PDF in S2")
        except Exception as e:
            return DownloadResult(success=False, error=str(e))

    def _download_annas(self, title: str, doi: str, filename: str) -> DownloadResult:
        """使用 Playwright 从 Anna's Archive 下载"""
        try:
            from .annas_playwright import AnnasArchiveSync

            query = doi if doi else title
            if not query:
                return DownloadResult(success=False, error="No query for Anna's Archive")

            downloader = AnnasArchiveSync(self.download_dir)
            success, result = downloader.download(query, filename)

            if success:
                return DownloadResult(success=True, filepath=result, source="Anna's Archive")
            else:
                return DownloadResult(success=False, error=result, manual_url=result)

        except ImportError:
            manual_url = f"https://annas-archive.gl/search?q={doi or title}&content=journal_article"
            return DownloadResult(success=False, error="Playwright not installed", manual_url=manual_url)

    def _download_file(self, url: str, filepath: str, source: str) -> DownloadResult:
        try:
            resp = requests.get(url, headers=self.headers, timeout=120, stream=True)
            resp.raise_for_status()

            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)

            print(f"  ✓ 保存: {filepath}")
            return DownloadResult(success=True, filepath=filepath, source=source)
        except Exception as e:
            return DownloadResult(success=False, error=str(e))

    def _make_filename(self, title: str, doi: str) -> str:
        if title:
            clean = re.sub(r'[^\w\s\-]', '', title)
            clean = re.sub(r'\s+', '_', clean)[:50]
            return f"{clean}.pdf"
        elif doi:
            return f"{doi.replace('/', '_')}.pdf"
        return "paper.pdf"
