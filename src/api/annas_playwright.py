"""
Anna's Archive Playwright 自动化下载器 v2

改进的下载流程，更可靠
"""

import os
import re
import time
import asyncio
from typing import Optional, List, Tuple
from dataclasses import dataclass
from urllib.parse import quote, urljoin


@dataclass
class SearchResult:
    """搜索结果"""
    title: str
    author: str
    year: str
    size: str
    format: str
    url: str
    md5: str


class AnnasArchivePlaywright:
    """Anna's Archive 自动化下载器"""

    # 使用多个镜像
    MIRRORS = [
        "https://annas-archive.gl",
        "https://annas-archive.org",
        "https://annas-archive.se",
    ]

    def __init__(self, download_dir: str = "./downloads", headless: bool = True):
        self.download_dir = os.path.abspath(download_dir)
        self.headless = headless
        os.makedirs(download_dir, exist_ok=True)

    def _get_browser(self, playwright):
        """获取浏览器实例"""
        return playwright.chromium.launch(
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled']
        )

    async def search(
        self,
        query: str,
        content_type: str = "journal_article",
        max_results: int = 5
    ) -> List[SearchResult]:
        """搜索论文"""
        from playwright.async_api import async_playwright

        results = []
        base_url = self.MIRRORS[0]
        search_url = f"{base_url}/search?q={quote(query)}&content={content_type}"

        async with async_playwright() as p:
            browser = await self._get_browser(p)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            try:
                print(f"  搜索: {query}")
                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

                # 获取结果链接
                links = await page.query_selector_all("a[href*='/md5/']")
                print(f"  找到 {len(links)} 个结果")

                for i, link in enumerate(links[:max_results]):
                    href = await link.get_attribute("href")
                    if href:
                        md5 = href.split("/md5/")[-1].split("?")[0]
                        text = await link.inner_text()

                        results.append(SearchResult(
                            title=text.split("\n")[0][:100] if text else f"Result {i+1}",
                            author="",
                            year="",
                            size="",
                            format="PDF",
                            url=f"{base_url}{href}",
                            md5=md5
                        ))

            except Exception as e:
                print(f"  搜索错误: {e}")
            finally:
                await browser.close()

        return results

    async def download(
        self,
        query: str,
        filename: str = None
    ) -> Tuple[bool, str]:
        """
        搜索并下载论文

        Returns:
            (success, filepath or error_message or manual_download_url)
        """
        from playwright.async_api import async_playwright

        base_url = self.MIRRORS[0]

        async with async_playwright() as p:
            browser = await self._get_browser(p)
            context = await browser.new_context(
                accept_downloads=True,
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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
                    return False, "未找到搜索结果"

                href = await first_link.get_attribute("href")
                detail_url = f"{base_url}{href}"
                print(f"  [2/4] 进入详情页...")

                await page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)

                # Step 3: 获取页面内容和下载链接
                print(f"  [3/4] 解析下载链接...")

                # 获取页面 HTML
                content = await page.content()

                # 尝试多种方式获取下载链接
                download_url = None

                # 方法 1: 查找快速下载按钮
                fast_btn = await page.query_selector("a:has-text('Fast')")
                if fast_btn:
                    download_url = await fast_btn.get_attribute("href")

                # 方法 2: 查找 Partner 下载
                if not download_url:
                    partner_btn = await page.query_selector("a:has-text('Partner')")
                    if partner_btn:
                        download_url = await partner_btn.get_attribute("href")

                # 方法 3: 查找所有可能的下载链接
                if not download_url:
                    all_links = await page.query_selector_all("a")
                    for link in all_links:
                        href = await link.get_attribute("href")
                        text = await link.inner_text()
                        if href and any(x in text.lower() for x in ["fast", "partner", "download", "下载", "slow"]):
                            download_url = href
                            break

                # 方法 4: 从 HTML 中提取
                if not download_url:
                    # 查找 IPFS 或其他直链
                    patterns = [
                        r'href="(https?://[^"]*ipfs[^"]*)"',
                        r'href="(https?://[^"]*fast[^"]*\.partner[^"]*)"',
                        r'"url":"(https?://[^"]+)"',
                    ]
                    for pattern in patterns:
                        match = re.search(pattern, content, re.I)
                        if match:
                            download_url = match.group(1)
                            break

                # Step 4: 下载或返回手动链接
                if download_url:
                    if not download_url.startswith("http"):
                        download_url = urljoin(base_url, download_url)

                    print(f"  [4/4] 处理下载链接...")

                    # 处理 fast_download 链接（需要额外步骤）
                    if "fast_download" in download_url:
                        print(f"  进入快速下载页...")
                        await page.goto(download_url, wait_until="domcontentloaded", timeout=30000)
                        await asyncio.sleep(3)

                        # 查找真正的下载按钮
                        dl_selectors = [
                            "a[href*='.pdf']",
                            "a:has-text('Download')",
                            "a:has-text('下载')",
                            "button:has-text('Download')",
                            "a[download]",
                        ]

                        real_dl_url = None
                        for sel in dl_selectors:
                            btn = await page.query_selector(sel)
                            if btn:
                                real_dl_url = await btn.get_attribute("href")
                                if real_dl_url:
                                    break

                        if real_dl_url:
                            if not real_dl_url.startswith("http"):
                                real_dl_url = urljoin(base_url, real_dl_url)
                            download_url = real_dl_url

                    # 尝试直接下载 PDF
                    if download_url.endswith(".pdf") or "ipfs" in download_url or "cdn" in download_url:
                        try:
                            # 使用 requests 直接下载（更可靠）
                            import requests
                            headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
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
                                await browser.close()
                                return True, filepath
                        except Exception as e:
                            print(f"  下载失败: {e}")

                    # 需要手动下载 - 提供 Sci-Hub 备选
                    scihub_url = f"https://sci-hub.se/{query}"
                    await browser.close()
                    return False, f"手动下载:\n  Anna's Archive: {download_url}\n  Sci-Hub: {scihub_url}"

                else:
                    # 返回详情页链接 + Sci-Hub
                    scihub_url = f"https://sci-hub.se/{query}"
                    await browser.close()
                    return False, f"手动下载:\n  Anna's Archive: {detail_url}\n  Sci-Hub: {scihub_url}"

            except Exception as e:
                await browser.close()
                return False, str(e)


class AnnasArchiveSync:
    """同步接口"""

    def __init__(self, download_dir: str = "./downloads", headless: bool = True):
        self._downloader = AnnasArchivePlaywright(download_dir, headless)

    def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        return asyncio.run(self._downloader.search(query, max_results=max_results))

    def download(self, query: str, filename: str = None) -> Tuple[bool, str]:
        return asyncio.run(self._downloader.download(query, filename))


# 命令行
async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Anna's Archive 自动下载")
    parser.add_argument("query", help="DOI 或标题")
    parser.add_argument("--output", "-o", default="./downloads")
    parser.add_argument("--show-browser", action="store_true")

    args = parser.parse_args()

    dl = AnnasArchivePlaywright(args.output, headless=not args.show_browser)
    success, result = await dl.download(args.query)

    print()
    if success:
        print(f"✓ 成功: {result}")
    else:
        print(f"结果: {result}")


if __name__ == "__main__":
    asyncio.run(main())
