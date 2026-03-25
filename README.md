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

# 环境与数据目录概览（配置、已注册 provider、metadata/pdf 数量等）
uv run autopapers status

# Phase 1：用户画像
uv run autopapers profile init -o user_profile.json
uv run autopapers profile validate -i user_profile.json

# 文献检索（AUTOPAPERS_PROVIDER：arxiv / openalex / crossref / local_pdf / aminer）
# 建议在 User-Agent 中带邮箱（各 API polite use）：export OPENALEX_MAILTO='you@example.com'
# Crossref 亦可：export CROSSREF_MAILTO='you@example.com'
uv run autopapers papers search -q "transformer" -l 3

# Phase 1 一键：profile → 搜索 →（可选）拉取首篇 PDF
uv run autopapers phase1 run --profile user_profile.json --fetch-first

# PDF 转文本（需依赖已安装）；可选写入解析清单 JSON
uv run autopapers papers parse -i ./data/papers/pdfs/some.pdf --write-manifest

# 批量解析某目录下 PDF → data/papers/parsed/
uv run autopapers papers parse-batch --input-dir ./data/papers/pdfs --write-manifest

# 从检索元数据 + PDF 解析清单合并语料快照（Phase 1 → KG MVP）
uv run autopapers corpus build
# 可选：把用户画像里的关键词并入图中
uv run autopapers corpus build --profile user_profile.json

# Phase 2 占位：生成/确认 proposal（未指定 --corpus 时会自动用 data/kg/corpus-snapshot.json）
uv run autopapers proposal draft --profile user_profile.json
uv run autopapers proposal confirm -i ./data/proposals/proposal-draft.json

# 将 proposal JSON 导出为 Markdown（默认与输入同名的 .md）
uv run autopapers proposal export -i ./data/proposals/proposal-draft.json
```

**Legacy**：`src/paper_fetcher.py` 与 `src/api/` 为早期脚本，仍以 `python src/paper_fetcher.py` 等方式可用，但新开发请以 `autopapers` 为准。

另可按仓库内 `requirements.txt` 使用 `pip`（与 uv 二选一即可）。

## 贡献

欢迎贡献！请查看 [CONTRIBUTING.md](./CONTRIBUTING.md)

## 许可证

MIT License
