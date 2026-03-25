"""
Anna's Archive + Sci-Hub Playwright 自动化下载器
"""

import os
import re
import asyncio
import requests
from typing import Optional, List, Tuple
from dataclasses import dataclass
from urllib.parse import quote, urljoin


@dataclass
class SearchResult:
    title: str
    author: str
    year: str
    size: str
    format: str
    url: str
    md5: str


class AnnasArchivePlaywright:
    """自动化下载器"""

    MIRRORS = ["https://annas-archive.gl", "https://annas-archive.org"]
    SCI_HUB_MIRRORS = ["https://sci-hub.se", "https://sci-hub.st", "https://sci-hub.ru"]

    def __init__(self, download_dir: str = "./downloads", headless: bool = True):
        self.download_dir = os.path.abspath(download_dir)
        self.headless = headless
        os.makedirs(download_dir, exist_ok=True)

    async def download(self, query: str, filename: str = None) -> Tuple[bool, str]:
        """搜索并下载论文"""
        from playwright.async_api import async_playwright

        base_url = self.MIRRORS[0]

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=['--disable-blink-features=AutomationControlled']
            )
            context = await browser.new_context(
                accept_downloads=True,
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            )
            page = await context.new_page()

            try:
                # Step 1: 搜索
                search_url = f"{base_url}/search?q={quote(query)}&content=journal_article"
                print(f"  [1/4] 搜索: {query[:50]}...")
                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

                # Step 2: 点击第一个结果
                first_link = await page.query_selector("a[href*='/md5/']")
                if not first_link:
                    await browser.close()
                    return await self._try_scihub(query, filename)

                href = await first_link.get_attribute("href")
                detail_url = f"{base_url}{href}"
                print(f"  [2/4] 进入详情页...")

                await page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)

                # Step 3: 获取下载链接
                print(f"  [3/4] 解析下载链接...")
                download_url = await self._get_download_url(page, base_url)

                # Step 4: 下载
                if download_url:
                    success, result = await self._handle_download(page, download_url, query, filename, base_url)
                    if success:
                        await browser.close()
                        return True, result
                    download_url = result  # 可能是手动链接

                # Anna's Archive 失败，尝试 Sci-Hub
                await browser.close()
                return await self._try_scihub(query, filename)

            except Exception as e:
                await browser.close()
                return await self._try_scihub(query, filename)

    async def _get_download_url(self, page, base_url: str) -> Optional[str]:
        """获取下载链接"""
        # 方法 1: Fast 下载
        fast_btn = await page.query_selector("a:has-text('Fast')")
        if fast_btn:
            return await fast_btn.get_attribute("href")

        # 方法 2: Partner 下载
        partner_btn = await page.query_selector("a:has-text('Partner')")
        if partner_btn:
            return await partner_btn.get_attribute("href")

        # 方法 3: 所有下载链接
        all_links = await page.query_selector_all("a")
        for link in all_links:
            href = await link.get_attribute("href")
            text = await link.inner_text()
            if href and any(x in text.lower() for x in ["fast", "partner", "download", "slow"]):
                return href

        # 方法 4: 从 HTML 提取
        content = await page.content()
        patterns = [
            r'href="(https?://[^"]*ipfs[^"]*)"',
            r'href="(https?://[^"]*fast[^"]*partner[^"]*)"',
        ]
        for pattern in patterns:
            m = re.search(pattern, content, re.I)
            if m:
                return m.group(1)

        return None

    async def _handle_download(self, page, download_url: str, query: str, filename: str, base_url: str) -> Tuple[bool, str]:
        """处理下载"""
        if not download_url.startswith("http"):
            download_url = urljoin(base_url, download_url)

        print(f"  [4/4] 处理: {download_url[:60]}...")

        # 处理 fast_download 页面
        if "fast_download" in download_url or "account/downloaded" in download_url:
            await page.goto(download_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            # 查找真实 PDF 链接
            pdf_link = await page.query_selector("a[href$='.pdf']")
            if pdf_link:
                real_url = await pdf_link.get_attribute("href")
                if real_url:
                    download_url = real_url if real_url.startswith("http") else urljoin(base_url, real_url)

        # 直接下载 PDF
        if ".pdf" in download_url or "ipfs" in download_url or "cdn" in download_url:
            try:
                headers = {"User-Agent": "Mozilla/5.0"}
                resp = requests.get(download_url, headers=headers, timeout=120, stream=True)
                if resp.status_code == 200:
                    if not filename:
                        filename = query.replace("/", "_")[:50] + ".pdf"
                    filepath = os.path.join(self.download_dir, filename)

                    total = int(resp.headers.get("content-length", 0))
                    with open(filepath, "wb") as f:
                        downloaded = 0
                        for chunk in resp.iter_content(8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total:
                                    print(f"\r  下载: {downloaded*100//total}%", end="")

                    print(f"\n  ✓ 保存: {filepath}")
                    return True, filepath
            except Exception as e:
                print(f"  下载失败: {e}")

        return False, download_url

    async def _try_scihub(self, doi: str, filename: str) -> Tuple[bool, str]:
        """尝试从 Sci-Hub 下载"""
        print(f"  尝试 Sci-Hub...")

        for mirror in self.SCI_HUB_MIRRORS:
            try:
                url = f"{mirror}/{doi}"
                print(f"  访问 {mirror}...")

                resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
                if resp.status_code != 200:
                    continue

                # 提取 PDF URL
                patterns = [
                    r'src="(https?://[^"]+\.pdf[^"]*)"',
                    r'href="(https?://[^"]+\.pdf[^"]*)"',
                    r'location\.href=[\'"](https?://[^\'"]+)',
                ]

                pdf_url = None
                for pattern in patterns:
                    m = re.search(pattern, resp.text, re.I)
                    if m:
                        pdf_url = m.group(1)
                        break

                if pdf_url:
                    # 下载 PDF
                    pdf_resp = requests.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=120, stream=True)
                    if pdf_resp.status_code == 200:
                        if not filename:
                            filename = doi.replace("/", "_")[:50] + ".pdf"
                        filepath = os.path.join(self.download_dir, filename)

                        with open(filepath, "wb") as f:
                            for chunk in pdf_resp.iter_content(8192):
                                if chunk:
                                    f.write(chunk)

                        print(f"  ✓ Sci-Hub 下载成功: {filepath}")
                        return True, filepath

            except Exception as e:
                print(f"  {mirror} 失败")
                continue

        return False, f"手动下载:\n  Sci-Hub: https://sci-hub.se/{doi}"


class AnnasArchiveSync:
    """同步接口"""

    def __init__(self, download_dir: str = "./downloads", headless: bool = True):
        self._downloader = AnnasArchivePlaywright(download_dir, headless)

    def download(self, query: str, filename: str = None) -> Tuple[bool, str]:
        return asyncio.run(self._downloader.download(query, filename))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--output", "-o", default="./downloads")
    parser.add_argument("--show-browser", action="store_true")

    args = parser.parse_args()

    dl = AnnasArchivePlaywright(args.output, headless=not args.show_browser)
    success, result = asyncio.run(dl.download(args.query))

    print()
    if success:
        print(f"✓ 成功: {result}")
    else:
        print(f"结果: {result}")
