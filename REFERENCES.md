# 参考项目与技术资源

## 核心参考项目

### 1. AutoResearchClaw

**GitHub**: https://github.com/aiming-lab/AutoResearchClaw

**核心贡献**：
- 多智能体辩论 (Debate) 机制
- 后台探针哨兵 (Sentinel) 机制
- 23 阶段辩论流程

**借鉴要点**：
- 激进派/保守派/刺客三方对抗的选题机制
- 实验过程中的异常监控与熔断

---

### 2. FARS

**GitLab**: https://gitlab.com/fars-a

**核心贡献**：
- Git 级全链路透明度
- 科研过程的完整版本控制

**借鉴要点**：
- 每一次试错都自动 Commit
- 过程可回溯、可审计

---

### 3. PaperClaw

**GitHub**: https://github.com/meowscles69/PaperClaw

**核心贡献**：
- 模块化技能库 (Skills) 架构
- 替代全能型 Agent

**借鉴要点**：
- 按需调用特定技能（如 profile-parsing, literature-review）
- 提高单个 Agent 的执行专注度

---

### 4. Governed Memory

**GitHub**: https://github.com/personizeai/governed-memory

**核心贡献**：
- 双态分层记忆架构
- 强 Schema 约束与开放集事实分离

**借鉴要点**：
- 硬约束条件（如硬件限制）作为不可逾越的边界
- 分层治理路由，精准的规则分发
- 实体级隔离，防止记忆幻觉与跨界污染

---

## 技术文章

### Anthropic Harness 设计

**链接**: https://www.anthropic.com/engineering/harness-design-long-running-apps

**核心洞察**：
- 上下文焦虑 (Context Anxiety) 问题
- 物理隔离的 Generator-Evaluator 闭环
- 规划者的边界克制 (Scope Restraint)
- 脚手架的动态退坡

**借鉴要点**：
- 上下文硬重置 + 结构化状态握手
- 执行者与评估者物理隔离
- 可插拔的 Harness 组件设计

---

### Cursor 极速正则检索

**链接**: https://cursor.com/en-US/blog/fast-regex-search

**核心技术**：
- 稀疏 N-gram (Sparse N-grams) 索引
- 概率掩码 (Probabilistic Masks)

**借鉴要点**：
- 毫秒级本地代码库检索
- 适用于多智能体高频探测场景

---

## 数据源

### AMiner API

**文档**: https://www.aminer.cn/open/docs?id=64f03e746221825d961dbde4

**核心能力**：
- 学术关系元数据
- 引用网络图谱
- 学者画像
- 领域发展脉络

**系统角色**：知识图谱骨架初始化、精准定点

---

### Anna's Archive SciDB

**链接**: https://annas-archive.gl/scidb

**核心能力**：
- 汇集 Sci-Hub、LibGen、Crossref 等来源
- 无视付费墙的 PDF 获取
- 海量全文本地化数据库

**系统角色**：重火力弹药库，提供论文全文

---

## 补充数据源

| 数据源 | 用途 | 优先级 |
|--------|------|--------|
| arXiv API | 30 天内新鲜预印本 | 高 |
| HuggingFace Papers | AI 领域前沿论文 | 高 |
| Semantic Scholar | 补充引用网络 | 中 |

---

## PDF 解析工具

| 工具 | 特点 |
|------|------|
| Nougat | Meta 出品，公式解析优秀 |
| Marker | 高保真 PDF 转 Markdown |
| Grobid | 学术论文专用解析器 |

---

## 技术栈参考

### 向量数据库

- Chroma
- FAISS
- Milvus

### 知识图谱

- Neo4j
- NetworkX

### 沙盒环境

- Docker
- Firecracker (microVM)

### 任务队列

- Celery
- RabbitMQ

---

## 相关论文

待补充：系统涉及的核心算法与架构论文
