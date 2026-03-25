"""
Anna's Archive + Sci-Hub 完整 Playwright 自动化

全程使用浏览器操作，不依赖 requests
"""

import os
import re
import asyncio
from typing import Optional, Tuple
from urllib.parse import quote, urljoin


class AnnasArchivePlaywright:
    """完整浏览器自动化下载器"""

    MIRRORS = ["https://annas-archive.gl", "https://annas-archive.org"]
    SCI_HUB_MIRRORS = ["https://sci-hub.se", "https://sci-hub.st", "https://sci-hub.ru"]

    def __init__(self, download_dir: str = "./downloads", headless: bool = True):
        self.download_dir = os.path.abspath(download_dir)
        self.headless = headless
        os.makedirs(download_dir, exist_ok=True)

    async def download(self, query: str, filename: str = None) -> Tuple[bool, str]:
        """全程自动化下载"""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=['--disable-blink-features=AutomationControlled']
            )
            context = await browser.new_context(
                accept_downloads=True,
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            try:
                # === Anna's Archive ===
                result = await self._download_from_annas(page, query, filename)
                if result[0]:
                    await browser.close()
                    return result

                # === Sci-Hub ===
                result = await self._download_from_scihub(page, query, filename)
                await browser.close()
                return result

            except Exception as e:
                await browser.close()
                return False, str(e)

    async def _download_from_annas(self, page, query: str, filename: str) -> Tuple[bool, str]:
        """从 Anna's Archive 下载"""
        base_url = self.MIRRORS[0]

        try:
            # Step 1: 搜索
            search_url = f"{base_url}/search?q={quote(query)}&content=journal_article"
            print(f"  [Anna's] 搜索: {query[:40]}...")
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            # Step 2: 点击第一个结果
            first_link = await page.query_selector("a[href*='/md5/']")
            if not first_link:
                print(f"  [Anna's] 无搜索结果")
                return False, "无结果"

            href = await first_link.get_attribute("href")
            detail_url = f"{base_url}{href}"
            print(f"  [Anna's] 进入详情页...")

            await page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            # Step 3: 点击下载按钮
            print(f"  [Anna's] 查找下载按钮...")

            # 尝试多种下载按钮
            download_selectors = [
                "a:has-text('Fast')",
                "a:has-text('Partner')",
                "a:has-text('Slow')",
                "button:has-text('Download')",
            ]

            clicked = False
            for selector in download_selectors:
                btn = await page.query_selector(selector)
                if btn:
                    print(f"  [Anna's] 点击: {selector}")
                    await btn.click()
                    clicked = True
                    await asyncio.sleep(3)
                    break

            if not clicked:
                print(f"  [Anna's] 无下载按钮")
                return False, "无下载按钮"

            # Step 4: 检查是否跳转到下载页
            current_url = page.url
            print(f"  [Anna's] 当前URL: {current_url[:60]}...")

            # 如果跳转到 fast_download 页面，继续查找 PDF
            if "fast_download" in current_url or "account" in current_url:
                await asyncio.sleep(2)

                # 查找 PDF 链接或下载按钮
                pdf_selectors = [
                    "a[href$='.pdf']",
                    "a:has-text('.pdf')",
                    "button:has-text('Download')",
                    "a[target='_blank']",
                ]

                for sel in pdf_selectors:
                    pdf_link = await page.query_selector(sel)
                    if pdf_link:
                        href = await pdf_link.get_attribute("href")
                        if href and ".pdf" in href.lower():
                            print(f"  [Anna's] 找到 PDF: {href[:50]}...")
                            # 点击下载
                            await pdf_link.click()
                            await asyncio.sleep(2)

            # Step 5: 尝试等待下载
            try:
                async with page.expect_download(timeout=60000) as download_info:
                    pass  # 等待下载触发
                download = await download_info.value

                if not filename:
                    filename = query.replace("/", "_")[:50] + ".pdf"
                filepath = os.path.join(self.download_dir, filename)
                await download.save_as(filepath)
                print(f"  [Anna's] ✓ 下载成功: {filepath}")
                return True, filepath
            except:
                pass

            # Step 6: 从页面提取 PDF URL 并用浏览器下载
            content = await page.content()
            pdf_patterns = [
                r'src="(https?://[^"]+\.pdf[^"]*)"',
                r'href="(https?://[^"]+\.pdf[^"]*)"',
                r'"(https?://[^"]*ipfs[^"]*\.pdf[^"]*)"',
            ]

            for pattern in pdf_patterns:
                m = re.search(pattern, content, re.I)
                if m:
                    pdf_url = m.group(1)
                    print(f"  [Anna's] 提取到 PDF: {pdf_url[:50]}...")

                    # 用浏览器访问并下载
                    return await self._browser_download(page, pdf_url, query, filename)

            # 检测到需要会员页面
            if "not_member" in current_url or "account" in current_url:
                detail_page = page.url.split("/fast_download")[0]
                print(f"  [Anna's] 需要免费会员账户")
                print(f"  [Anna's] 详情页: {detail_page}")
                # 保存当前状态，让用户可以手动完成
                return False, f"需要会员账户\n  详情页: {detail_page}\n  操作: 点击任意下载按钮，会跳转注册页(免费)"

            print(f"  [Anna's] 未找到 PDF 链接")
            return False, "Anna's Archive 需要账户"

        except Exception as e:
            print(f"  [Anna's] 失败: {str(e)[:50]}")
            return False, str(e)

    async def _download_from_scihub(self, page, query: str, filename: str) -> Tuple[bool, str]:
        """用 Playwright 从 Sci-Hub 下载"""

        for mirror in self.SCI_HUB_MIRRORS:
            try:
                url = f"{mirror}/{query}"
                print(f"  [Sci-Hub] 访问 {mirror}...")

                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

                # 检查是否有验证码
                if await page.query_selector("iframe[src*='captcha']"):
                    print(f"  [Sci-Hub] 需要验证码，跳过...")
                    continue

                # 查找 PDF embed 或 link
                pdf_selectors = [
                    "embed[type='application/pdf']",
                    "iframe[src*='.pdf']",
                    "a[href$='.pdf']",
                    "#pdf",
                ]

                pdf_url = None
                for sel in pdf_selectors:
                    elem = await page.query_selector(sel)
                    if elem:
                        src = await elem.get_attribute("src") or await elem.get_attribute("href")
                        if src:
                            pdf_url = src
                            print(f"  [Sci-Hub] 找到 PDF: {src[:50]}...")
                            break

                # 从页面源码提取
                if not pdf_url:
                    content = await page.content()
                    patterns = [
                        r'src="(https?://[^"]+\.pdf[^"]*)"',
                        r'href="(https?://[^"]+\.pdf[^"]*)"',
                        r'location\.href=[\'"](https?://[^\'"]+)',
                    ]
                    for p in patterns:
                        m = re.search(p, content, re.I)
                        if m:
                            pdf_url = m.group(1)
                            break

                if pdf_url:
                    return await self._browser_download(page, pdf_url, query, filename)

                print(f"  [Sci-Hub] {mirror} 未找到 PDF")

            except Exception as e:
                print(f"  [Sci-Hub] {mirror} 失败: {str(e)[:30]}")
                continue

        # Sci-Hub 被封锁
        annas_url = f"{self.MIRRORS[0]}/search?q={quote(query)}&content=journal_article"

        return False, f"""需要手动操作:
1. Anna's Archive (需免费注册):
   {annas_url}

2. Sci-Hub (需 VPN):
   https://sci-hub.se/{query}"""

    async def _browser_download(self, page, pdf_url: str, query: str, filename: str) -> Tuple[bool, str]:
        """用浏览器下载 PDF"""
        try:
            print(f"  浏览器下载: {pdf_url[:60]}...")

            # 监听下载事件
            try:
                async with page.expect_download(timeout=120000) as download_info:
                    await page.goto(pdf_url, wait_until="domcontentloaded", timeout=60000)

                download = await download_info.value

                if not filename:
                    suggested = download.suggested_filename
                    filename = suggested if suggested else query.replace("/", "_")[:50] + ".pdf"

                filepath = os.path.join(self.download_dir, filename)
                await download.save_as(filepath)
                print(f"  ✓ 下载成功: {filepath}")
                return True, filepath

            except:
                # 如果没有触发下载，可能是直接显示 PDF
                await asyncio.sleep(3)

                # 检查页面是否是 PDF
                current_url = page.url
                if ".pdf" in current_url:
                    # 用 Playwright 的截图+打印方式或者重新请求
                    print(f"  PDF 在浏览器中显示，尝试其他方式...")

                    # 方法：获取页面内容作为 PDF
                    if not filename:
                        filename = query.replace("/", "_")[:50] + ".pdf"
                    filepath = os.path.join(self.download_dir, filename)

                    # 使用 page.pdf() 导出
                    await page.pdf(path=filepath)
                    print(f"  ✓ 导出 PDF: {filepath}")
                    return True, filepath

                return False, f"无法下载: {current_url}"

        except Exception as e:
            print(f"  下载失败: {str(e)[:50]}")
            return False, str(e)


class AnnasArchiveSync:
    """同步接口"""

    def __init__(self, download_dir: str = "./downloads", headless: bool = True):
        self._downloader = AnnasArchivePlaywright(download_dir, headless)

    def download(self, query: str, filename: str = None) -> Tuple[bool, str]:
        return asyncio.run(self._downloader.download(query, filename))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("query", help="DOI 或标题")
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
