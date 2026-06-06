# Contributing to Browser Agent

欢迎贡献代码！请阅读以下指南，确保您的贡献符合项目规范。

## 项目简介

Browser Agent 是一个基于 Playwright 和 Camoufox 的浏览器自动化框架，主要用于网页爬取、数据采集和自动化测试。

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

```bash
pip install -r requirements.txt
playwright install
```

### 5. 开发与测试

确保您的代码通过所有测试：

```bash
pytest
```

检查代码风格：

```bash
ruff check src/
```

### 6. 提交代码

提交信息遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

```bash
git add .
git commit -m "feat: 添加新功能描述"
```

提交类型：
- `feat` - 新功能
- `fix` - 修复 bug
- `docs` - 文档更新
- `refactor` - 代码重构
- `test` - 测试更新
- `chore` - 构建/工具更新

### 7. 推送分支

```bash
git push origin feature/your-feature-name
```

### 8. 创建 Pull Request

在 GitHub 上创建 Pull Request，描述您的更改内容。

## 代码风格指南

### Python 代码规范

- 使用 Python 3.7+
- 遵循 PEP 8 规范
- 使用类型注解
- 使用 `async/await` 进行异步编程
- 避免使用 `except Exception`，应捕获具体异常类型

### 代码结构

```
src/
├── agent/           # 核心代理逻辑
├── modes/           # 业务模式（如 zhipin）
├── shared/          # 共享工具和引擎
└── cli/             # 命令行接口
```

### 测试规范

- 所有新功能必须添加单元测试
- 测试文件放在 `tests/` 目录
- 使用 pytest 框架

## 报告问题

如果您发现 bug 或有功能建议，请在 GitHub Issues 中提交。

### Issue 模板

- **问题描述**: 清晰描述问题
- **复现步骤**: 详细说明如何复现
- **预期行为**: 期望的结果
- **实际行为**: 当前的结果
- **环境信息**: Python 版本、操作系统等

## 行为准则

请遵守 [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/0/code_of_conduct/)。

## 许可证

项目采用 MIT 许可证，所有贡献代码将遵循相同的许可证。
