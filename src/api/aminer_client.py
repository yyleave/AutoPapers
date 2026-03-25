"""
AMiner API 客户端

使用免费 API 获取论文信息
"""

import os
import time
import requests
from typing import Optional, Dict, Any, List
from dataclasses import dataclass


@dataclass
class Paper:
    """论文数据结构"""
    id: str
    title: str
    authors: List[str]
    year: Optional[int] = None
    abstract: Optional[str] = None
    doi: Optional[str] = None
    venue: Optional[str] = None
    n_citation: Optional[int] = None
    url: Optional[str] = None
    pdf_url: Optional[str] = None


class AMinerClient:
    """AMiner API 客户端"""

    BASE_URL = "https://datacenter.aminer.cn/gateway/open_platform"

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("AMINER_API_KEY")
        if not self.token:
            raise ValueError(
                "请设置 AMINER_API_KEY 环境变量或传入 token\n"
                "获取方式: https://open.aminer.cn/open/board?tab=control"
            )

    def _request(
        self,
        method: str,
        path: str,
        params: Dict = None,
        json_data: Dict = None,
        max_retries: int = 3
    ) -> Dict:
        """发送请求（带重试）"""
        headers = {"Authorization": self.token}
        url = f"{self.BASE_URL}{path}"

        for attempt in range(max_retries):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_data,
                    timeout=30
                )

                # 可重试的状态码
                if response.status_code in [408, 429, 500, 502, 503, 504]:
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt) + (0.1 * (attempt + 1))
                        time.sleep(wait_time)
                        continue

                response.raise_for_status()
                return response.json()

            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    continue
                raise
            except requests.exceptions.RequestException as e:
                raise RuntimeError(f"API 请求失败: {e}")

    # ============ 免费 API ============

    def paper_search(self, title: str, page: int = 0, size: int = 10) -> List[Paper]:
        """
        免费 - 论文标题搜索

        Args:
            title: 论文标题关键词
            page: 页码（从0开始）
            size: 每页数量

        Returns:
            论文列表
        """
        result = self._request("GET", "/api/paper/search", {
            "title": title,
            "page": page,
            "size": size
        })
        return self._parse_papers(result)

    def paper_info(self, paper_ids: List[str]) -> List[Paper]:
        """
        免费 - 批量获取论文基础信息

        Args:
            paper_ids: 论文ID列表（最多100个）

        Returns:
            论文列表
        """
        result = self._request("POST", "/api/paper/info", json_data={
            "ids": paper_ids[:100]  # 限制100个
        })
        return self._parse_papers(result)

    def person_search(self, name: str, page: int = 0, size: int = 10) -> List[Dict]:
        """
        免费 - 学者搜索

        Args:
            name: 学者姓名
            page: 页码
            size: 每页数量

        Returns:
            学者列表
        """
        result = self._request("POST", "/api/person/search", json_data={
            "name": name,
            "page": page,
            "size": size
        })
        return result.get("data", [])

    def org_search(self, name: str, page: int = 0, size: int = 10) -> List[Dict]:
        """
        免费 - 机构搜索
        """
        result = self._request("POST", "/api/organization/search", json_data={
            "name": name,
            "page": page,
            "size": size
        })
        return result.get("data", [])

    def venue_search(self, name: str, page: int = 0, size: int = 10) -> List[Dict]:
        """
        免费 - 期刊/会议搜索
        """
        result = self._request("POST", "/api/venue/search", json_data={
            "name": name,
            "page": page,
            "size": size
        })
        return result.get("data", [])

    def patent_search(self, query: str, page: int = 0, size: int = 10) -> List[Dict]:
        """
        免费 - 专利搜索
        """
        result = self._request("POST", "/api/patent/search", json_data={
            "query": query,
            "page": page,
            "size": size
        })
        return result.get("data", [])

    # ============ 收费 API（按需调用）============

    def paper_detail(self, paper_id: str) -> Optional[Paper]:
        """
        ¥0.01/次 - 获取论文详情
        """
        result = self._request("GET", "/api/paper/detail", {
            "paper_id": paper_id
        })
        papers = self._parse_papers(result)
        return papers[0] if papers else None

    def paper_relation(self, paper_id: str) -> Dict:
        """
        ¥0.10/次 - 获取论文引用关系
        """
        return self._request("GET", "/api/paper/relation", {
            "paper_id": paper_id
        })

    # ============ 辅助方法 ============

    def _parse_papers(self, result: Dict) -> List[Paper]:
        """解析论文数据"""
        papers = []
        for item in result.get("data", []):
            paper = Paper(
                id=item.get("id", ""),
                title=item.get("title", ""),
                authors=[a.get("name", "") for a in item.get("authors", [])],
                year=item.get("year"),
                abstract=item.get("abstract"),
                doi=item.get("doi"),
                venue=item.get("venue", {}).get("name") if isinstance(item.get("venue"), dict) else item.get("venue"),
                n_citation=item.get("n_citation"),
                url=f"https://www.aminer.cn/pub/{item.get('id', '')}",
                pdf_url=item.get("pdf")
            )
            papers.append(paper)
        return papers

    def search_by_title(self, title: str, limit: int = 5) -> List[Paper]:
        """
        便捷方法：按标题搜索论文

        这是推荐的使用免费 API 的方式：
        1. 使用 paper_search 获取 paper_id
        2. 使用 paper_info 获取基础信息
        """
        print(f"搜索论文: {title}")
        papers = self.paper_search(title, size=limit)

        if papers:
            # 批量获取更详细的信息
            paper_ids = [p.id for p in papers]
            detailed = self.paper_info(paper_ids)

            # 合并信息
            for i, paper in enumerate(papers):
                for detail in detailed:
                    if detail.id == paper.id:
                        papers[i] = detail
                        break

        return papers


def format_paper_info(paper: Paper) -> str:
    """格式化论文信息"""
    lines = [
        f"标题: {paper.title}",
        f"作者: {', '.join(paper.authors)}",
    ]

    if paper.year:
        lines.append(f"年份: {paper.year}")
    if paper.venue:
        lines.append(f"期刊/会议: {paper.venue}")
    if paper.n_citation is not None:
        lines.append(f"引用数: {paper.n_citation}")
    if paper.doi:
        lines.append(f"DOI: {paper.doi}")
    if paper.url:
        lines.append(f"AMiner链接: {paper.url}")
    if paper.pdf_url:
        lines.append(f"PDF链接: {paper.pdf_url}")

    if paper.abstract:
        abstract = paper.abstract[:300] + "..." if len(paper.abstract) > 300 else paper.abstract
        lines.append(f"摘要: {abstract}")

    return "\n".join(lines)


# ============ 使用示例 ============

if __name__ == "__main__":
    import sys

    # 检查环境变量
    if not os.environ.get("AMINER_API_KEY"):
        print("错误: 请先设置 AMINER_API_KEY 环境变量")
        print("\n获取方式:")
        print("1. 访问 https://open.aminer.cn/open/board?tab=control")
        print("2. 登录并生成 API Token")
        print("3. 设置环境变量: export AMINER_API_KEY='your_token'")
        sys.exit(1)

    client = AMinerClient()

    # 示例：搜索论文
    search_term = sys.argv[1] if len(sys.argv) > 1 else "Attention is all you need"

    print(f"\n{'='*60}")
    print(f"搜索论文: {search_term}")
    print('='*60)

    papers = client.search_by_title(search_term, limit=5)

    print(f"\n找到 {len(papers)} 篇论文:\n")

    for i, paper in enumerate(papers, 1):
        print(f"\n--- 论文 {i} ---")
        print(format_paper_info(paper))
        print()
