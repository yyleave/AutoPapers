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

# 环境与数据目录概览（配置、provider、metadata 数量；若存在语料快照则含节点/边统计；
# 并内嵌与 `doctor` 相同的可选能力 JSON 于 `doctor` 字段）
uv run autopapers status

# 可选能力自检：AMiner / LLM（含 PATH 中的 ollama CLI）/ Docker / LaTeX、mailto、default.toml
# uv run autopapers doctor
# doctor.optional_features：paper_fetcher_cli、llm_backend_valid / llm_backend_hint（与 config 逻辑一致）

# 一键跑完整 MVP 链路（profile -> phase1 -> corpus -> proposal -> status）
# 建议先把 user_profile.json 的 keywords 指向一个本地 PDF 路径（local_pdf provider）
# uv run autopapers run-all --profile user_profile.json --title "My topic"
# 单次指定文献源（与 phase1 run --provider 相同）：例如 AMiner
# uv run autopapers run-all --profile user_profile.json --provider aminer --title "My topic"

# 版本号（与 pyproject 版本一致，需可编辑/安装包）
uv run autopapers version

# 当前生效的 provider / 日志级别、default.toml、数据根目录、entrypoints_on_path、
# llm（backend_valid / backend_hint）等（JSON）
uv run autopapers config

# 在空目录（已设置 AUTOPAPERS_REPO_ROOT）下生成最小 configs/default.toml，便于与 flow/status 对齐
# uv run autopapers workspace-init

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

# AMiner：固定走 AMiner API（需 AMINER_API_KEY；与 AUTOPAPERS_PROVIDER 无关）；可加 --download-first 拉首条直链 PDF
# uv run autopapers papers aminer-search -q "graph neural networks" -l 5
# uv run autopapers papers aminer-search -q "GNN" --download-first

# 备用：使用内置“自动下载器”按 title/doi 下载（arXiv → Unpaywall → S2 → Anna's，best-effort）
# 该路径不依赖 provider，适合拿到 DOI/标题后做一次“尽力下载”
# uv run autopapers papers download --title "Attention is all you need"
# uv run autopapers papers download --doi "10.5555/3295222.3295349" --title "Attention is all you need"

# 列出已写入的检索/抓取元数据 JSON（按修改时间倒序）
uv run autopapers papers list-metadata

# 查看某条元数据（显式路径，或 --latest search|fetch|any）
uv run autopapers papers show-metadata --latest search

# Phase 1 一键：profile → 搜索 →（可选）拉取首篇 PDF →（可选）转文本 + manifest
# 仅校验 profile 并打印将使用的检索 query / provider（不写 metadata、不请求网络）
# uv run autopapers phase1 run --profile user_profile.json --dry-run
# 单次覆盖文献源（无需改 AUTOPAPERS_PROVIDER），例如 AMiner（需 AMINER_API_KEY）：
# uv run autopapers phase1 run --profile user_profile.json --provider aminer --fetch-first --parse-fetched
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

# Phase 2 LLM backend（默认 openai；也支持 ollama）
# OpenAI:
# export AUTOPAPERS_LLM_BACKEND=openai
# export OPENAI_API_KEY='sk-...'
# export AUTOPAPERS_OPENAI_MODEL='gpt-4o-mini'   # optional
# Ollama:
# export AUTOPAPERS_LLM_BACKEND=ollama
# export AUTOPAPERS_OLLAMA_MODEL='llama3.1:8b'   # optional
# ollama pull llama3.1:8b && ollama serve

# 将 proposal JSON 导出为 Markdown（默认与输入同名的 .md）
uv run autopapers proposal export -i ./data/proposals/proposal-draft.json

# Phase 3/4 占位流程：执行报告 -> 论文草稿 -> 投稿打包目录
uv run autopapers phase3 run --proposal ./data/proposals/proposal-confirmed.json
uv run autopapers phase3 evaluate --report ./data/experiments/experiment-report.json
uv run autopapers phase4 draft \
  --proposal ./data/proposals/proposal-confirmed.json \
  --experiment ./data/experiments/experiment-report.json
uv run autopapers phase4 bundle \
  --proposal ./data/proposals/proposal-confirmed.json \
  --experiment ./data/experiments/experiment-report.json \
  --evaluation ./data/experiments/evaluation-summary.json \
  --manuscript ./data/manuscripts/manuscript-draft.md
uv run autopapers phase4 submit --bundle-dir ./data/submissions/submission-package

# 可选：把 Phase3 的 artifacts（metrics.json/summary.txt 等）也打包进 submission-package
# uv run autopapers phase4 bundle \
#   --proposal ./data/proposals/proposal-confirmed.json \
#   --experiment ./data/experiments/experiment-report.json \
#   --evaluation ./data/experiments/evaluation-summary.json \
#   --manuscript ./data/manuscripts/manuscript-draft.md \
#   --include-artifacts
#
# 可选：把 `manuscript-draft.pdf` 也打包进 submission-package（需要先生成同名 .pdf）
# uv run autopapers phase4 pdf --manuscript ./data/manuscripts/manuscript-draft.md
# uv run autopapers phase4 bundle \
#   --proposal ./data/proposals/proposal-confirmed.json \
#   --experiment ./data/experiments/experiment-report.json \
#   --evaluation ./data/experiments/evaluation-summary.json \
#   --manuscript ./data/manuscripts/manuscript-draft.md \
#   --include-pdf

# 可选：生成 Phase3 evaluator 脚本（可复现执行）
uv run autopapers proposal generate-evaluator --proposal ./data/proposals/proposal-confirmed.json
# 可选：Docker 沙盒执行（需要本机 docker）
# uv run autopapers phase3 run --proposal ./data/proposals/proposal-confirmed.json --runner docker

# 可选：导出 LaTeX（最小可编译版本；后续可替换为真实模板）
uv run autopapers phase4 latex --manuscript ./data/manuscripts/manuscript-draft.md

# 可选：编译 PDF（需要本机安装 LaTeX 引擎；推荐 tectonic）
# brew install tectonic
# uv run autopapers phase4 pdf --manuscript ./data/manuscripts/manuscript-draft.md

# 可选：从语料快照生成最小可用的 references.bib（用于 LaTeX/PDF 自动打印参考文献）
# uv run autopapers phase4 bib --snapshot ./data/kg/corpus-snapshot.json

# 一键全流程（包含 phase3/4 占位产物）
# uv run autopapers run-all --profile user_profile.json --full-flow
# 若 run-all 全流程后直接需要归档，可保持默认 archive 或显式 --archive
# uv run autopapers run-all --profile user_profile.json --full-flow --archive

# 最短全流程入口：默认 bundle + .tar.gz（等价 run-all --full-flow --archive）；仅目录不打包：
# uv run autopapers publish --profile user_profile.json --title "My topic" --no-archive
# uv run autopapers publish --profile user_profile.json --title "My topic"
# publish / release 同样支持单次 --provider aminer（与 run-all、phase1 一致）
# 若希望 submission 包含 artifacts：
# uv run autopapers publish --profile user_profile.json --title "My topic" --include-artifacts
#
# 若希望 submission 包含 manuscript PDF：
# uv run autopapers publish --profile user_profile.json --title "My topic" --include-pdf

# 发布闭环（publish + verify + release-report.json）
# uv run autopapers release --profile user_profile.json --title "My topic"
# 与 publish 相同，可只生成 bundle、不写 .tar.gz：release ... --no-archive
# 若希望 release-report 的 checksum/verify 也覆盖 artifacts：
# uv run autopapers release --profile user_profile.json --title "My topic" --include-artifacts
#
# 若希望 release-report 的 checksum/verify 也覆盖 manuscript PDF：
# uv run autopapers release --profile user_profile.json --title "My topic" --include-pdf
#
# 若希望打包并验签 references.bib（从 corpus-snapshot 刷新）：
# uv run autopapers release --profile user_profile.json --title "My topic" --include-bib
# 发布后二次验签（读取 release-report 的 checksum 重新核验）
# uv run autopapers release-verify
# release-report.json / release-verify-report.json 含 schema_version 0.2、autopapers_version、generated_at、proposal_title（可追溯）

# 断点续跑：若已有 proposal-confirmed.json，则从 Phase3+ 继续；否则可传 --profile 自动回退全流程
# uv run autopapers resume
# uv run autopapers resume --profile user_profile.json
# 回退到 release 时可带与 release 相同的检索/解析与选题参数，例如：
# uv run autopapers resume --profile user_profile.json --title "My topic" --limit 2 --parse-max-pages 10
# 已有 confirmed proposal 时也可用 --no-archive 只更新 bundle、不写 .tar.gz
# 回退到 release 时同样可单次指定文献源：resume --profile ... --provider local_pdf

# 查看当前流程进度与推荐下一步命令
# uv run autopapers flow

# Phase5 编排占位：从 confirmed proposal 一键产出 experiment/manuscript/submission bundle
# uv run autopapers phase5 run --proposal ./data/proposals/proposal-confirmed.json
# 若不想生成 tar.gz 归档，可显式关闭：--no-archive
# 验证 submission 包与归档一致性
# uv run autopapers phase5 verify --bundle-dir ./data/submissions/submission-package
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

在同一工作目录下继续跑 **Phase5 编排**（`phase5 run` + `phase5 verify`，从已确认的 proposal 生成实验报告、文稿、打包与归档）：

```bash
scripts/mvp_demo.sh --mode offline --extended
```

全流程（含发布与验签）演示：

```bash
scripts/full_pipeline_demo.sh --mode offline
# 或：
scripts/full_pipeline_demo.sh --mode hybrid
```

可选参数：

- `--workdir /tmp/my-run`：指定独立输出目录（不污染当前 `data/`）
- `--mode offline|hybrid`：`offline` 仅本地链路；`hybrid` 末尾会尝试 network smoke
- `mvp_demo.sh --extended`：默认 MVP 之后追加 `phase5 run` 与 `phase5 verify`
- `full_pipeline_demo.sh`：在 `release-verify` 之后额外执行一次 `phase5 verify`

脚本会按顺序执行并输出产物路径；加 `--extended` 时在最后增加 `phase5 run`、`phase5 verify` 与 submission 相关路径说明：

1. `workspace-init`（写入 `configs/default.toml`）+ PDF 夹具 + `profile init` 与字段补齐
2. `phase1 run --fetch-first --parse-fetched`
3. `corpus build/info/export-*`
4. `proposal draft/confirm/export`
5. `status` 与 `flow`
6. 产物路径清单

### Network smoke 开关

- 测试默认由 pytest 配置排除：`-m "not network"`。
- 手动执行在线冒烟：

```bash
AUTOPAPERS_NETWORK_SMOKE=1 uv run pytest -q -m network \
  tests/test_papers_arxiv_provider.py::test_arxiv_search_returns_results \
  tests/test_openalex_provider.py::test_openalex_search_network_smoke \
  tests/test_crossref_provider.py::test_crossref_search_network_smoke \
  tests/test_aminer_provider_search.py::test_aminer_search_network_smoke
```

或直接使用脚本：

```bash
scripts/run_all_providers_smoke.sh
```

说明：AMiner 网络冒烟还需要设置 `AMINER_API_KEY`，否则会被自动 skip。

## 发布前一键验收

建议在发布前执行：

```bash
scripts/release_check.sh
```

仓库 CI 默认也执行同一离线验收脚本（`scripts/release_check.sh`），本地先跑可减少 CI 往返。第 1 阶段为 **Ruff** + **`autopapers doctor`**（环境快照 JSON）。

如需在线冒烟，可在 GitHub Actions 手动触发 `ci`，并开启 `run_network_smoke=true`（可选配置仓库 secret: `AMINER_API_KEY`）。

如需连同 provider 网络冒烟一起执行：

```bash
scripts/release_check.sh --with-network-smoke
```

如在脚本自测场景下只想校验主流程（跳过 demo 脚本测试阶段）：

```bash
scripts/release_check.sh --skip-demo-tests
```

如需仅检查 lint + 可选网络冒烟（跳过离线回归与 demo 测试）：

```bash
scripts/release_check.sh --skip-offline-tests --skip-demo-tests
```

默认第 3 阶段会同时执行 `tests/test_demo_scripts.py` 与 `tests/test_paper_fetcher_cli.py`，覆盖新旧脚本入口。

如只想验证 legacy 脚本入口测试，可用：

```bash
scripts/release_check.sh --skip-offline-tests --legacy-only-tests
```

### 常见问题排查

- `snapshot_not_found`：先运行 `uv run autopapers corpus build`。
- `invalid_json` / `validation`：检查输入 JSON 是否为有效且符合 schema。
- `phase1 run` 提示参数错误：`--parse-fetched` 必须和 `--fetch-first` 同时使用。
- hybrid 模式网络冒烟失败：通常是外网连通性或上游 API 波动，离线 MVP 不受影响。
- `proposal draft` / `run-all` 报 `llm_setup`：检查 `AUTOPAPERS_LLM_BACKEND` 与对应凭证/服务（OpenAI 需要 `OPENAI_API_KEY`；Ollama 需要本地服务与模型；`autopapers doctor` 会报告 `ollama_cli` 是否在 PATH）。

**Legacy**：`src/paper_fetcher.py` 与 `src/api/` 为早期脚本；除 `python src/paper_fetcher.py` 外也可使用 **`uv run paper-fetcher`**（与 `autopapers` 同环境）。检索与 AMiner 直链下载已与 `autopapers.providers.AminerProvider` 对齐，多级回退仍用 `PDFDownloader`。新开发请以 `autopapers` CLI 为准。

另可按仓库内 `requirements.txt` 使用 `pip`（与 uv 二选一即可）。

## 贡献

欢迎贡献！请查看 [CONTRIBUTING.md](./CONTRIBUTING.md)

## 许可证

MIT License
