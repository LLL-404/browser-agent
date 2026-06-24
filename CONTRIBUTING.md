# Contributing to Browser Agent

欢迎贡献代码！请阅读以下指南，确保您的贡献符合项目规范。

## 项目简介

Browser Agent 是一个基于 Playwright 和 Camoufox 的浏览器自动化 AI Agent 框架，支持 CLI、MCP Server 和 Chat Agent 三种交互模式。

## 如何贡献

### 1. Fork 仓库

首先，点击 GitHub 页面上的 "Fork" 按钮，将仓库 fork 到您自己的账户。

### 2. 克隆仓库

```bash
git clone https://github.com/your-username/browser-agent.git
cd browser-agent
```

### 3. 创建开发分支

```bash
git checkout -b feature/your-feature-name
```

分支命名规范：
- `feature/xxx` - 新功能
- `bugfix/xxx` - 修复 bug
- `docs/xxx` - 文档更新
- `refactor/xxx` - 代码重构

### 4. 安装依赖

**推荐**（含开发工具）：
```bash
pip install -e ".[dev]"
playwright install
```

**仅核心依赖**：
```bash
pip install -r requirements.txt
# 或
pip install -e .
playwright install
```

环境要求：**Python 3.11+**

### 5. 开发与测试

运行测试：
```bash
pytest                           # 全部测试
pytest -m "not integration"     # 跳过需要真实浏览器的集成测试
pytest --cov=src                 # 生成覆盖率报告
```

代码检查：
```bash
ruff check src/                  # 检查
ruff check --fix src/            # 自动修复
ruff format src/                 # 格式化
```

类型检查：
```bash
mypy src/
```

### 6. 提交代码

提交信息遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范：
- `feat` - 新功能
- `fix` - 修复 bug
- `docs` - 文档更新
- `refactor` - 代码重构
- `test` - 测试更新
- `chore` - 构建/工具更新

### 7. 推送分支并创建 PR

```bash
git push origin feature/your-feature-name
```

在 GitHub 上创建 Pull Request，描述您的更改内容。

## 代码风格指南

### Python 代码规范

- 使用 **Python 3.11+**
- 遵循 PEP 8 规范
- 使用类型注解（`from __future__ import annotations` + 现代 `X | Y` 语法）
- 使用 `async/await` 进行异步编程
- 避免使用 `except Exception`，应捕获具体异常类型（ruff 规则 E722）
- 行宽限制 120 字符

### 代码结构

```
src/
├── browser_agent/          # 核心框架
│   ├── cli/                #   CLI 入口（agent 命令）
│   ├── core/               #   浏览器引擎（感知/决策/执行循环）
│   ├── mcp/                #   MCP 协议服务器
│   ├── chat/               #   对话式 Agent
│   └── flows/              #   流程骨架模板
├── modes/                  # 业务模式（zhipin 等）
├── shared/                 # 共享基础设施
│   ├── config.py           #   YAML 配置加载
│   ├── logging_config.py    #   统一日志
│   ├── exceptions.py        #   异常体系
│   └── retry.py             #   重试机制
└── tests/                  # 测试
```

### 测试规范

- 所有新功能必须添加单元测试
- 测试文件放在 `tests/` 目录
- 使用 pytest + pytest-asyncio 框架
- 集成测试（需真实浏览器）标记 `@pytest.mark.integration`

## 报告问题

请在 GitHub Issues 提交，包含：问题描述、复现步骤、预期行为、实际行为、环境信息（Python 版本、操作系统）。

## 许可证

项目采用 MIT 许可证，所有贡献代码将遵循相同的许可证。
