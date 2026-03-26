# AutoPapers

**多智能体自动化科研论文写作系统**

将学术论文写作的全流程映射为公司组织架构，通过多 Agent 协作实现从选题到发表的自动化研究工作流。

## 核心理念

论文不仅是学术成果，更是你（作为"公司CEO"）向学术界交付的"产品"。本系统将知识生产链条拆解为六个核心部门：

| 公司运作环节 | 学术写作阶段 | 核心目标 |
|-------------|-------------|---------|
| 基础设施 | 专业知识学习 | 构建底层技术栈 |
| 产品战略 | 选题 (Proposal) | 寻找市场空白与差异化 |
| 核心研发 | 实验/推导 | 验证逻辑，产出核心功能 |
| 生产制造 | 论文撰写 (Draft) | 标准化封装与逻辑串联 |
| 质量控制 | 修改 (Revision) | 压力测试，修补漏洞 |
| 市场与公关 | 投稿审稿 (Publishing) | 渠道匹配与危机应对 |

## 系统架构

```
Phase 1: 数据底座与图谱初始化
    ↓
Phase 2: 多智能体辩论与方向收敛
    ↓
Phase 3: 沙盒执行与评估闭环
    ↓
Phase 4: 防幻觉论文编撰
```

## 核心特性

- **多智能体辩论机制**：激进派、保守派、刺客三方对抗，产出高质量选题
- **Governed Memory**：分层记忆架构，硬约束与软知识分离
- **硬件感知沙盒**：自动适配本地算力环境
- **防幻觉编撰**：强制 Grounding，引用与数据 100% 可追溯
- **Git 级透明度**：全链路版本控制，过程可回溯

## 参考项目

- [AutoResearchClaw](https://github.com/aiming-lab/AutoResearchClaw) - 多智能体辩论与哨兵机制
- [FARS](https://gitlab.com/fars-a) - Git 级全链路透明度
- [PaperClaw](https://github.com/meowscles69/PaperClaw) - 模块化技能库
- [Governed Memory](https://github.com/personizeai/governed-memory) - 分层记忆架构

## 文档

- [架构设计](./ARCHITECTURE.md)
- [工作流程](./WORKFLOW.md)
- [参考资源](./REFERENCES.md)
- [开发路线图](./ROADMAP.md)
- [AMiner API 集成](./docs/AMINER_API.md)

## 快速开始

推荐使用 **uv** 与统一 CLI `autopapers`：

```bash
git clone https://github.com/yyleave/AutoPapers.git
cd AutoPapers

uv sync

# 环境与数据目录概览（配置、provider、metadata 数量；若存在语料快照则含节点/边统计）
uv run autopapers status

# 一键跑完整 MVP 链路（profile -> phase1 -> corpus -> proposal -> status）
# 建议先把 user_profile.json 的 keywords 指向一个本地 PDF 路径（local_pdf provider）
# uv run autopapers run-all --profile user_profile.json --title "My topic"

# 版本号（与 pyproject 版本一致，需可编辑/安装包）
uv run autopapers version

# 当前生效的 provider / 日志级别、default.toml 路径、数据根目录等（JSON）
uv run autopapers config

# 已注册的文献源名称与简介（JSON）
uv run autopapers providers

# 若当前工作目录不是仓库根目录，可指定仓库根：./data 与 configs/default.toml 均相对该路径
# export AUTOPAPERS_REPO_ROOT="/path/to/AutoPapers"

# Phase 1：用户画像
uv run autopapers profile init -o user_profile.json
uv run autopapers profile validate -i user_profile.json
uv run autopapers profile show -i user_profile.json

# 文献检索（AUTOPAPERS_PROVIDER：arxiv / openalex / crossref / local_pdf / aminer）
# HTTP User-Agent 邮箱（OpenAlex / Crossref / arXiv 等）：优先 AUTOPAPERS_MAILTO，否则 OPENALEX_MAILTO / CROSSREF_MAILTO
# export AUTOPAPERS_MAILTO='you@example.com'
# 可选：configs/default.toml 的 contact_email 或环境变量 AUTOPAPERS_CONTACT_EMAIL，仅在 config/status 中展示（不替代上述 UA）
uv run autopapers papers search -q "transformer" -l 3

# 列出已写入的检索/抓取元数据 JSON（按修改时间倒序）
uv run autopapers papers list-metadata

# 查看某条元数据（显式路径，或 --latest search|fetch|any）
uv run autopapers papers show-metadata --latest search

# Phase 1 一键：profile → 搜索 →（可选）拉取首篇 PDF →（可选）转文本 + manifest
# 仅校验 profile 并打印将使用的检索 query / provider（不写 metadata、不请求网络）
# uv run autopapers phase1 run --profile user_profile.json --dry-run
uv run autopapers phase1 run --profile user_profile.json --fetch-first --parse-fetched

# PDF 转文本（需依赖已安装）；可选写入解析清单 JSON
uv run autopapers papers parse -i ./data/papers/pdfs/some.pdf --write-manifest

# 批量解析某目录下 PDF → data/papers/parsed/
uv run autopapers papers parse-batch --input-dir ./data/papers/pdfs --write-manifest

# 从检索元数据 + PDF 解析清单合并语料快照（Phase 1 → KG MVP）
uv run autopapers corpus build
# 可选：把用户画像里的关键词并入图中
uv run autopapers corpus build --profile user_profile.json
# 只计算合并结果统计，不写 corpus-snapshot.json
# uv run autopapers corpus build --dry-run
# 查看当前快照的节点类型 / 边类型统计（不重新 build）
uv run autopapers corpus info

# 将快照中的边导出为 CSV（默认打印；可用 -o 写入文件）
uv run autopapers corpus export-edges
# uv run autopapers corpus export-edges -r FETCHED -o fetched.csv
uv run autopapers corpus export-nodes
# uv run autopapers corpus export-nodes -t Paper -o papers.csv

# Phase 2 占位：生成/确认 proposal（未指定 --corpus 时会自动用 data/kg/corpus-snapshot.json）
uv run autopapers proposal draft --profile user_profile.json
# uv run autopapers proposal draft --profile user_profile.json -o ./my-draft.json
uv run autopapers proposal validate -i ./data/proposals/proposal-draft.json
uv run autopapers proposal confirm -i ./data/proposals/proposal-draft.json
# uv run autopapers proposal confirm -i ./draft.json -o ./confirmed.json

# 将 proposal JSON 导出为 Markdown（默认与输入同名的 .md）
uv run autopapers proposal export -i ./data/proposals/proposal-draft.json
```

## 5 分钟跑通 MVP（端到端）

默认推荐先跑离线链路（稳定、可复现）：

```bash
uv sync
scripts/mvp_demo.sh --mode offline
```

如果你希望在离线链路之外追加真实 provider 冒烟（不阻断主流程）：

```bash
scripts/mvp_demo.sh --mode hybrid
```

可选参数：

- `--workdir /tmp/my-run`：指定独立输出目录（不污染当前 `data/`）
- `--mode offline|hybrid`：`offline` 仅本地链路；`hybrid` 末尾会尝试 network smoke

脚本会按顺序执行并输出产物路径：

1. `profile init` + profile 最小字段补齐
2. `phase1 run --fetch-first --parse-fetched`
3. `corpus build/info/export-*`
4. `proposal draft/confirm/export`
5. `status`

### Network smoke 开关

- 测试默认由 pytest 配置排除：`-m "not network"`。
- 手动执行在线冒烟：

```bash
AUTOPAPERS_NETWORK_SMOKE=1 uv run pytest -q -m network \
  tests/test_papers_arxiv_provider.py::test_arxiv_search_returns_results \
  tests/test_openalex_provider.py::test_openalex_search_network_smoke
```

### 常见问题排查

- `snapshot_not_found`：先运行 `uv run autopapers corpus build`。
- `invalid_json` / `validation`：检查输入 JSON 是否为有效且符合 schema。
- `phase1 run` 提示参数错误：`--parse-fetched` 必须和 `--fetch-first` 同时使用。
- hybrid 模式网络冒烟失败：通常是外网连通性或上游 API 波动，离线 MVP 不受影响。

**Legacy**：`src/paper_fetcher.py` 与 `src/api/` 为早期脚本，仍以 `python src/paper_fetcher.py`（仓库根目录）等方式可用；脚本会将 `src/` 注入 `sys.path`，便于未安装可编辑包时导入 `api`。新开发请以 `autopapers` 为准。

另可按仓库内 `requirements.txt` 使用 `pip`（与 uv 二选一即可）。

## 贡献

欢迎贡献！请查看 [CONTRIBUTING.md](./CONTRIBUTING.md)

## 许可证

MIT License
