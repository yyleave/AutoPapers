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

## 快速开始

```bash
# 克隆仓库
git clone https://github.com/yyleave/AutoPapers.git
cd AutoPapers

# 安装依赖 (待实现)
pip install -r requirements.txt

# 运行 (待实现)
python main.py
```

## 贡献

欢迎贡献！请查看 [CONTRIBUTING.md](./CONTRIBUTING.md)

## 许可证

MIT License
