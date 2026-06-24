# Browser Agent — Agent 协作约定

## 项目概述

浏览器自动化 AI Agent 框架（Python 3.11+），Camoufox 单引擎（C++ 级反检测），三种交互模式（CLI / MCP Server / Chat Agent）。

## 入口命令

```bash
agent browse <url>                    # 启动浏览器浏览
agent login --url <url>               # 登录并保存会话
agent extract <url> <selector>        # 数据提取
agent snapshot <url>                  # 页面快照
agent chat                            # 对话模式
python -m browser_agent.mcp.server    # MCP 服务器
```

## 包结构

```
src/browser_agent/   # 核心框架（cli / core / mcp / chat / flows）
src/modes/           # 业务模式（zhipin 等，即插即用）
src/shared/          # 共享基础设施（config / logging / exceptions / retry）
tests/               # 测试（pytest + pytest-asyncio）
```

## 开发工具链

```bash
ruff check src/        # lint（零错误门禁）
ruff format src/       # format
mypy src/              # 类型检查
pytest -m "not integration"  # 跳过集成测试
```

## 架构约定

- **感知→决策→执行循环**：`core/perceiver.py` → `core/decider.py` → `core/executor.py`
- **浏览器控制**：`core/browser.py`（Camoufox 引擎）+ `health_monitor.py` + `session.py`
- **流程骨架**：`flows/` 目录下定义 FlowSkeleton，决策引擎按 URL 自动匹配
- **业务模式协议**：`modes/` 下每个子包实现 `get_mcp_tools()` + `handle_mcp_call()`

## 关键配置

- `config.yaml` — 运行时配置（延迟/日志/政府网站限制/业务模式参数）
- `pyproject.toml` — 包元数据 + 依赖 + 工具链配置（ruff/mypy/pytest/coverage）
- `.gitignore` — 覆盖 `.coverage`/`.playwright*`/`.ruff_cache/` 等运行时产物

## 注意事项

- `src/shared/engine/` 已标记 deprecated，新代码应使用 `core/decider` 的 FlowSkeleton 架构
- `agent --mode zhipin` 替代了过渡期脚本 `hunt.py`（已删除）
- 测试中标记 `@pytest.mark.integration` 的用例需要真实浏览器环境
