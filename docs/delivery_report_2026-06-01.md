# 完整架构重构 — 交付报告

**交付时间**: 2026-06-01  
**任务**: 浏览器 Agent 平台化重构（T1–T6）

---

## 变更总览

**旧架构**: `entry/` + `core/` + `sites/` — 紧耦合
**新架构**: `agent/`（通用）+ `modes/`（插件）+ `shared/`（共享）

### T1: agent/core/ — 通用浏览器引擎
- `browser.py`：Camoufox/Playwright 双引擎 BrowserController
- `anti_detect.py`：反检测（JS 伪装/拟人操作/指纹）
- `session.py`：Cookie/StorageState 持久化管理
- `page.py`：通用截图 + HTML 快照（可注入 BOSS 选择器）
- `agent.py`：BrowserAgent 高层封装

### T2: agent/mcp/server.py — 通用 MCP 服务
- 13 个通用浏览器工具（导航/点击/输入/截图/抓取/会话等）
- 模式注册机制：启动时自动扫描 `modes/` 目录，每个子包提供 `get_mcp_tools()`

### T3: agent/cli/main.py — 通用 CLI 入口
- `--mode` 参数分派：`python -m agent.cli.main --mode zhipin stats`
- `browse` 通用子命令

### T4: modes/zhipin/ — BOSS 直聘插件
- `scraper.py`、`selectors.py`、`page_analyzer.py`：抓取引擎
- `pre_filter.py`、`keyword_strategy.py`、`city_codes.py`：数据处理管线
- `storage.py`、`exporter.py`：持久化工具
- `search_flow.py`：交互式搜索流
- `__init__.py`：模式入口（提供 `get_mcp_tools()` + `register_cli()` + `run_cli()`）

### T5: shared/ — 共享基础设施
- `config.py`、`logging_config.py`、`retry.py`
- `error_handler.py`、`exceptions.py`、`profiler.py`
- `fingerprint_manager.py`

### T6: 清理旧目录
- 已删除：`core/`、`entry/`、`cli/`、`mcp_server/`、`sites/`
- 根目录仅保留 5 文件（README.md / pyproject.toml / requirements.txt / config.yaml / .gitignore）+ 6 目录

---

## 新架构目录树

```
boss-job-hunter/
├── agent/                   ← 通用浏览器 Agent（独立于任何业务）
│   ├── core/                ← 浏览器引擎
│   │   ├── browser.py       ← BrowserController（Camoufox/Playwright）
│   │   ├── anti_detect.py   ← 反检测模块
│   │   ├── session.py       ← 会话管理
│   │   ├── page.py          ← 页面分析
│   │   └── agent.py         ← BrowserAgent 封装
│   ├── cli/main.py          ← 通用 CLI（--mode 分派）
│   └── mcp/server.py        ← MCP 服务（13 通用工具 + 模式注册）
│
├── modes/                   ← 业务插件目录
│   ├── zhipin/              ← BOSS 直聘模式
│   │   ├── __init__.py      ← 模式入口（get_mcp_tools / register_cli / run_cli）
│   │   ├── scraper.py       ← 核心抓取（648 行）
│   │   ├── selectors.py     ← DOM 选择器集中管理
│   │   ├── pre_filter.py    ← 预过滤器
│   │   ├── keyword_strategy.py ← 关键词策略
│   │   ├── city_codes.py    ← 城市编码
│   │   ├── exporter.py      ← 数据导出
│   │   ├── storage.py       ← SQLite 存储
│   │   ├── page_analyzer.py ← 页面分析（验证码/反爬检测）
│   │   └── search_flow.py   ← 交互式搜索流
│   └── __init__.py
│
├── shared/                  ← 共享基础设施
│   ├── config.py            ← YAML 配置加载
│   ├── logging_config.py    ← 统一日志
│   ├── retry.py             ← 指数退避重试
│   ├── error_handler.py     ← 异常分类
│   ├── exceptions.py        ← 异常体系
│   ├── profiler.py          ← 性能分析
│   └── fingerprint_manager.py ← 指纹生成
│
├── scripts/                 ← 工具脚本
│   ├── send_report.py       ← 报告发送（Playwright）
│   ├── project_structure_scanner.py ← 结构扫描
│   ├── export_cookies.py
│   ├── login_checker.py
│   └── manual/
│
├── tests/                   ← 自动化测试（52 项）
│   ├── test_core.py            ← 单元测试（14 项）
│   ├── test_integration.py     ← 集成测试（4 项）
│   ├── test_scraper_parse.py   ← Mock 解析测试（1 项）
│   ├── test_selectors.py       ← 选择器测试（18 项）
│   ├── test_session_check.py   ← Cookie 检测测试（8 项）
│   └── test_browser_smoke.py   ← 浏览器冒烟测试（7 项）
│
├── config/
│   ├── ci/ci.yml
│   ├── .pre-commit-config.yaml
│   └── mcp_config.json
├── docs/
├── config.yaml
├── pyproject.toml
├── requirements.txt
├── README.md
└── .gitignore
```

---

## 验证结果

| 测试项 | 结果 |
|--------|------|
| `pytest tests/` | **52/52 通过** |
| `python -m agent.cli.main --help` | 正常输出 |
| `python -m agent.cli.main --mode zhipin stats` | 正常输出 JSON 统计 |
| `from agent.mcp.server import main` | 导入正常 |
| `scripts/manual/verify_system.py` | 全部模块通过 |

---

## 迁移指南

| 旧命令 | 新命令 |
|--------|--------|
| `python -m entry.cli.main` | `python -m agent.cli.main --mode zhipin` |
| `python -m entry.mcp.server` | `python -m agent.mcp.server` |
| `from core.engine.scraper import ...` | `from modes.zhipin.scraper import ...` |
| `from core.infra.config import ...` | `from shared.config import ...` |
| `from core.infra.logging_config import ...` | `from shared.logging_config import ...` |
| `from core.infra.retry import ...` | `from shared.retry import ...` |
| `from core.infra.storage import ...` | `from modes.zhipin.storage import ...` |
| `from core.infra.cookie_manager import ...` | `from agent.core.session import ...` |

---

## 已知问题

- `project_structure_scanner.py` 对新架构的 S2/S3 检测有盲区（Agent/Modes/Shared 模块未识别）
- `agent/mcp/server.py` 需手动测试完整 MCP 协议握手（依赖 AI 编辑器连接）
- 旧数据迁移无需操作（SQLite DB 路径不变，`sessions/` 目录不变）
