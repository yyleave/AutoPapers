# AMiner API 集成文档

## 概述

AMiner 是全球领先的学术数据平台，由智谱 AI 构建，提供学者、论文、机构、期刊、专利等全维度学术数据。

### 数据规模

- **3.5亿+** 论文
- **1.35亿** 学者
- **4000万** 专利
- **6000万** 学者画像

### 官方资源

- **API 文档**: https://open.aminer.cn/open/docs
- **控制台（生成 Token）**: https://open.aminer.cn/open/board?tab=control

---

## 认证

所有 API 调用需要在请求头中携带 Token：

```
Authorization: <your_token>
```

### 获取 Token

1. 访问 [AMiner 控制台](https://open.aminer.cn/open/board?tab=control) 并登录
2. 点击「生成密钥」
3. 粘贴 API Key，设置过期时间
4. 点击「开始生成」
5. **立即复制保存**（Token 仅显示一次）

### 配置环境变量

```bash
export AMINER_API_KEY="<your_token>"
```

---

## API 基础信息

- **基础域名**: `https://datacenter.aminer.cn/gateway/open_platform`
- **请求格式**: JSON
- **默认超时**: 30s
- **最大重试**: 3次
- **退避策略**: 指数退避（1s → 2s → 4s）+ 随机抖动

---

## 28 个开放 API 速查表

### 论文相关

| # | API 名称 | 方法 | 价格 | 路径 |
|---|---------|------|------|------|
| 1 | 论文问答搜索 | POST | ¥0.05/次 | `/api/paper/qa/search` |
| 2 | 论文搜索 | GET | 免费 | `/api/paper/search` |
| 3 | 论文搜索 Pro | GET | ¥0.01/次 | `/api/paper/search/pro` |
| 4 | 论文信息（批量） | POST | 免费 | `/api/paper/info` |
| 5 | 论文详情（单篇） | GET | ¥0.01/次 | `/api/paper/detail` |
| 6 | 论文引用 | GET | ¥0.10/次 | `/api/paper/relation` |
| 7 | 论文搜索接口 | GET | ¥0.30/次 | `/api/paper/list/by/search/venue` |
| 8 | 论文批量查询 | GET | ¥0.10/次 | `/api/paper/list/citation/by/keywords` |
| 9 | 按年份与期刊获取论文详情 | GET | ¥0.20/次 | `/api/paper/platform/allpubs/more/detail/by/ts/org/venue` |

### 学者相关

| # | API 名称 | 方法 | 价格 | 路径 |
|---|---------|------|------|------|
| 10 | 学者搜索 | POST | 免费 | `/api/person/search` |
| 11 | 学者详情 | GET | ¥1.00/次 | `/api/person/detail` |
| 12 | 学者画像 | GET | ¥0.50/次 | `/api/person/figure` |
| 13 | 学者论文 | GET | ¥1.50/次 | `/api/person/paper/relation` |
| 14 | 学者专利 | GET | ¥1.50/次 | `/api/person/patent/relation` |
| 15 | 学者项目 | GET | ¥3.00/次 | `/api/project/person/v3/open` |

### 机构相关

| # | API 名称 | 方法 | 价格 | 路径 |
|---|---------|------|------|------|
| 16 | 机构搜索 | POST | 免费 | `/api/organization/search` |
| 17 | 机构详情 | POST | ¥0.01/次 | `/api/organization/detail` |
| 18 | 机构消歧 | POST | ¥0.01/次 | `/api/organization/na` |
| 19 | 机构消歧 Pro | POST | ¥0.05/次 | `/api/organization/na/pro` |
| 20 | 机构学者 | GET | ¥0.50/次 | `/api/organization/person/relation` |
| 21 | 机构论文 | GET | ¥0.10/次 | `/api/organization/paper/relation` |
| 22 | 机构专利 | GET | ¥0.10/次 | `/api/organization/patent/relation` |

### 期刊相关

| # | API 名称 | 方法 | 价格 | 路径 |
|---|---------|------|------|------|
| 23 | 期刊搜索 | POST | 免费 | `/api/venue/search` |
| 24 | 期刊详情 | POST | ¥0.20/次 | `/api/venue/detail` |
| 25 | 期刊论文 | POST | ¥0.10/次 | `/api/venue/paper/relation` |

### 专利相关

| # | API 名称 | 方法 | 价格 | 路径 |
|---|---------|------|------|------|
| 26 | 专利搜索 | POST | 免费 | `/api/patent/search` |
| 27 | 专利信息 | GET | 免费 | `/api/patent/info` |
| 28 | 专利详情 | GET | ¥0.01/次 | `/api/patent/detail` |

---

## 论文搜索接口选型指南

| API | 侧重点 | 适用场景 | 成本 |
|-----|--------|---------|------|
| `paper_search` | 标题检索、快速拿 `paper_id` | 已知论文标题，先定位目标 | 免费 |
| `paper_search_pro` | 多条件检索与排序 | 主题检索、按引用量/年份排序 | ¥0.01/次 |
| `paper_qa_search` | 自然语言问答/语义检索 | 用自然语言描述需求 | ¥0.05/次 |
| `paper_list_by_search_venue` | 返回更完整论文信息 | 需要丰富字段做分析/报告 | ¥0.30/次 |
| `paper_list_by_keywords` | 多关键词批量检索 | 批量专题拉取 | ¥0.10/次 |
| `paper_detail_by_condition` | 年份+期刊维度拉详情 | 期刊年度监控、选刊分析 | ¥0.20/次 |

### 推荐路由

1. **已知标题**: `paper_search → paper_detail → paper_relation`
2. **条件筛选**: `paper_search_pro → paper_detail`
3. **自然语言问答**: `paper_qa_search`（无结果降级 `paper_search_pro`）
4. **期刊年度分析**: `venue_search → venue_paper_relation → paper_detail_by_condition`

---

## 6 大组合工作流

### 工作流 1：学者全景分析（Scholar Profile）

**适用场景**: 了解某位学者的完整学术画像

```
学者搜索（name → person_id）
    ↓
并行调用：
  ├── 学者详情（bio/教育背景/荣誉）
  ├── 学者画像（研究方向/兴趣/工作经历）
  ├── 学者论文（论文列表）
  ├── 学者专利（专利列表）
  └── 学者项目（科研项目/资助信息）
```

### 工作流 2：论文深度挖掘（Paper Deep Dive）

**适用场景**: 获取论文完整信息及引用关系

```
论文搜索 / 论文搜索pro（title/keyword → paper_id）
    ↓
论文详情（摘要/作者/DOI/期刊/年份/关键词）
    ↓
论文引用（该论文引用了哪些论文 → cited_ids）
    ↓
（可选）对被引论文批量获取论文信息
```

### 工作流 3：机构研究力分析（Org Analysis）

**适用场景**: 分析某机构的学者规模、论文产出、专利数量

```
机构消歧pro（原始字符串 → org_id）
    ↓
并行调用：
  ├── 机构详情（简介/类型/成立时间）
  ├── 机构学者（学者列表）
  ├── 机构论文（论文列表）
  └── 机构专利（专利ID列表，最多10000条）
```

### 工作流 4：期刊论文监控（Venue Papers）

**适用场景**: 追踪某期刊特定年份的论文

```
期刊搜索（name → venue_id）
    ↓
期刊详情（ISSN/类型/简称）
    ↓
期刊论文（venue_id + year → paper_id 列表）
    ↓
（可选）论文详情批量查询
```

### 工作流 5：学术智能问答（Paper QA Search）

**适用场景**: 用自然语言或结构化关键词智能搜索论文

**核心参数**:
- `query`: 自然语言提问
- `topic_high/middle/low`: 精细控制关键词权重
- `sci_flag`: 只看 SCI 论文
- `force_citation_sort`: 按引用量排序
- `author_terms / org_terms`: 限定作者或机构

### 工作流 6：专利链分析（Patent Analysis）

**适用场景**: 搜索特定技术领域的专利

```
专利搜索（query → patent_id）
    ↓
专利详情（摘要/申请日/申请号/受让人/发明人）
```

---

## 实体 URL 模板

返回结果中必须附带可访问 URL：

| 实体类型 | URL 模板 |
|---------|---------|
| 论文 | `https://www.aminer.cn/pub/{paper_id}` |
| 学者 | `https://www.aminer.cn/profile/{person_id}` |
| 专利 | `https://www.aminer.cn/patent/{patent_id}` |
| 期刊 | `https://www.aminer.cn/open/journal/detail/{venue_id}` |

---

## 稳定性与失败处理

### 重试策略

- **可重试状态码**: `408 / 429 / 500 / 502 / 503 / 504`
- **不可重试**: `4xx` 错误（参数错误、鉴权问题）

### 工作流降级

- `paper_deep_dive`: `paper_search` 无结果时自动降级到 `paper_search_pro`
- `paper_qa`: `query` 模式无结果时，自动降级到 `paper_search_pro`

---

## 费用控制策略

1. **免费优先**: 优先使用免费接口（`paper_search` / `paper_info` / `venue_search`）
2. **最优组合查询**: 禁止无差别全量详情拉取
3. **默认数量限制**: 用户未指定数量时，默认仅查询前 10 条详情
4. **分级查询**: 先用低成本接口筛选，再对目标子集调用收费接口

---

## Python 客户端示例

```python
import os
import requests
from typing import Optional, Dict, Any

class AMinerClient:
    """AMiner API 客户端"""

    BASE_URL = "https://datacenter.aminer.cn/gateway/open_platform"

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("AMINER_API_KEY")
        if not self.token:
            raise ValueError("请设置 AMINER_API_KEY 环境变量或传入 token")

    def _request(self, method: str, path: str, params: Dict = None, json: Dict = None) -> Dict:
        """发送请求"""
        headers = {"Authorization": self.token}
        url = f"{self.BASE_URL}{path}"

        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json,
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    # 论文搜索
    def paper_search(self, title: str, page: int = 0, size: int = 10) -> Dict:
        """免费 - 论文标题搜索"""
        return self._request("GET", "/api/paper/search", {
            "title": title, "page": page, "size": size
        })

    def paper_search_pro(self, title: str = None, author: str = None,
                         org: str = None, keyword: str = None,
                         order: str = "n_citation", page: int = 0, size: int = 10) -> Dict:
        """¥0.01/次 - 多条件检索"""
        params = {"page": page, "size": size, "order": order}
        if title: params["title"] = title
        if author: params["author"] = author
        if org: params["org"] = org
        if keyword: params["keyword"] = keyword
        return self._request("GET", "/api/paper/search/pro", params)

    def paper_detail(self, paper_id: str) -> Dict:
        """¥0.01/次 - 论文详情"""
        return self._request("GET", "/api/paper/detail", {"paper_id": paper_id})

    def paper_relation(self, paper_id: str) -> Dict:
        """¥0.10/次 - 论文引用关系"""
        return self._request("GET", "/api/paper/relation", {"paper_id": paper_id})

    # 学者搜索
    def person_search(self, name: str, page: int = 0, size: int = 10) -> Dict:
        """免费 - 学者搜索"""
        return self._request("POST", "/api/person/search", json={
            "name": name, "page": page, "size": size
        })

    def person_detail(self, person_id: str) -> Dict:
        """¥1.00/次 - 学者详情"""
        return self._request("GET", "/api/person/detail", {"person_id": person_id})

    def person_papers(self, person_id: str, page: int = 0, size: int = 10) -> Dict:
        """¥1.50/次 - 学者论文"""
        return self._request("GET", "/api/person/paper/relation", {
            "person_id": person_id, "page": page, "size": size
        })

    # 机构搜索
    def org_search(self, name: str, page: int = 0, size: int = 10) -> Dict:
        """免费 - 机构搜索"""
        return self._request("POST", "/api/organization/search", json={
            "name": name, "page": page, "size": size
        })

    def org_detail(self, org_id: str) -> Dict:
        """¥0.01/次 - 机构详情"""
        return self._request("POST", "/api/organization/detail", json={"id": org_id})

    # 期刊搜索
    def venue_search(self, name: str, page: int = 0, size: int = 10) -> Dict:
        """免费 - 期刊搜索"""
        return self._request("POST", "/api/venue/search", json={
            "name": name, "page": page, "size": size
        })

    def venue_papers(self, venue_id: str, year: int, page: int = 0, size: int = 10) -> Dict:
        """¥0.10/次 - 期刊论文"""
        return self._request("POST", "/api/venue/paper/relation", json={
            "venue_id": venue_id, "year": year, "page": page, "size": size
        })

    # 专利搜索
    def patent_search(self, query: str, page: int = 0, size: int = 10) -> Dict:
        """免费 - 专利搜索"""
        return self._request("POST", "/api/patent/search", json={
            "query": query, "page": page, "size": size
        })


# 使用示例
if __name__ == "__main__":
    client = AMinerClient()  # 自动读取 AMINER_API_KEY 环境变量

    # 搜索论文
    result = client.paper_search(title="Attention is all you need")
    print(result)

    # 获取学者信息
    scholars = client.person_search(name="Yann LeCun")
    print(scholars)
```

---

## 参考资源

- [AMiner 官方文档](https://open.aminer.cn/open/docs)
- [AMiner 控制台](https://open.aminer.cn/open/board?tab=control)
- [ClawHub AMiner Skill](https://clawhub.ai/mrhenghu/aminer-open-academic-1-0-5)
- [OpenClaw 实战教程](https://zhuanlan.zhihu.com/p/2012175493072462861)
