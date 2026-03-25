# 贡献指南

感谢你对 AutoPapers 的兴趣！

## 如何贡献

### 报告问题

- 在 Issues 中搜索是否已有相关问题
- 使用清晰的标题描述问题
- 提供复现步骤和环境信息

### 提交代码

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

### 代码规范

- 遵循 PEP 8 (Python)
- 添加必要的文档字符串
- 保持函数单一职责

### 开发环境

```bash
# 克隆仓库
git clone https://github.com/yyleave/AutoPapers.git
cd AutoPapers

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 安装开发依赖
pip install -r requirements-dev.txt
```

### 项目结构

```
AutoPapers/
├── docs/                   # 文档
├── src/                    # 源代码
│   ├── agents/            # Agent 定义
│   ├── skills/            # 技能模块
│   ├── sandbox/           # 沙盒环境
│   ├── memory/            # 记忆管理
│   └── utils/             # 工具函数
├── tests/                  # 测试
├── examples/               # 示例
└── configs/                # 配置文件
```

## 联系方式

- GitHub Issues: 问题讨论
- 仓库维护者: @yyleave
