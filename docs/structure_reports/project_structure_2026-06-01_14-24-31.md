# 项目结构现状报告

**生成时间**：2026-06-01 14:24:30

---

## S1：项目目录树

```
boss-job-hunter/
├── agent/  # 通用浏览器 Agent 层，独立于任何业务，提供完整的浏览器自动化能力
│   ├── cli/  # 通用 CLI 入口，--mode 参数分派，支持 browse 子命令
│   │   └── main.py
│   ├── core/  # 浏览器引擎核心：Camoufox/Playwright 双引擎控制器、反检测、会话管理、页面分析
│   │   ├── agent.py
│   │   ├── anti_detect.py
│   │   ├── browser.py
│   │   ├── page.py
│   │   └── session.py
│   └── mcp/  # MCP 协议服务器，通过 Model Context Protocol 暴露通用浏览器自动化能力（13 个工具）
│       └── server.py
├── config/  # 开发工具与 CI 配置，含 Pre-commit 钩子和 MCP 连接配置
│   ├── ci/  # 待补充
│   │   └── ci.yml
│   ├── .pre-commit-config.yaml
│   └── mcp_config.json
├── docs/  # 项目文档，含迭代计划、设计文档、算法复杂度说明
│   ├── refactor/  # 待补充
│   │   └── iteration_plan.md
│   ├── structure_reports/  # 待补充
│   │   ├── project_structure_2026-06-01_13-49-36.md
│   │   ├── project_structure_2026-06-01_13-51-13.md
│   │   ├── project_structure_2026-06-01_14-02-55.md
│   │   └── project_structure_2026-06-01_14-22-13.md
│   ├── superpowers/  # 待补充
│   │   └── specs/  # 待补充
│   │       └── 2026-05-02-boss-job-hunter-design.md
│   ├── algorithm_complexity.md
│   └── delivery_report_2026-06-01.md
├── modes/  # 业务插件注册目录，每个子包提供 get_mcp_tools() / register_cli() / run_cli() 接口
│   ├── zhipin/  # BOSS 直聘业务插件，独立注册 10 个 MCP 工具和 8 个 CLI 子命令
│   │   ├── __init__.py
│   │   ├── city_codes.py
│   │   ├── exporter.py
│   │   ├── keyword_strategy.py
│   │   ├── page_analyzer.py
│   │   ├── pre_filter.py
│   │   ├── scraper.py
│   │   ├── search_flow.py
│   │   ├── selectors.py
│   │   └── storage.py
│   └── __init__.py
├── scripts/  # 辅助工具脚本，含报告发送、结构扫描、登录检查、Cookie 导出等
│   ├── manual/  # 手动测试脚本，用于调试和验证特定功能
│   │   ├── debug_buttons.py
│   │   ├── debug_deepseek.py
│   │   ├── login_and_save.py
│   │   ├── quick_snap.py
│   │   ├── show_tree.py
│   │   ├── simple_search.py
│   │   ├── smoke_test.py
│   │   ├── test_camoufox.py
│   │   ├── test_controller.py
│   │   ├── verify_login.py
│   │   ├── verify_system.py
│   │   └── view_jobs.py
│   ├── browser_cleaner.py
│   ├── current_structure.md
│   ├── delivery_report.md
│   ├── delivery_template.md
│   ├── dev.bat
│   ├── download_camoufox.py
│   ├── export_cookies.py
│   ├── login_checker.py
│   ├── project_structure_report.md
│   ├── project_structure_scanner.py
│   ├── r6_r11_confirmation.md
│   ├── refresh_deepseek_login.py
│   ├── save_report_generator.py
│   ├── scanner_plan.md
│   └── send_report.py
├── shared/  # 共享基础设施层，提供配置加载、日志、重试、异常体系、性能分析、指纹生成等底层能力
│   ├── config.py
│   ├── error_handler.py
│   ├── exceptions.py
│   ├── fingerprint_manager.py
│   ├── logging_config.py
│   ├── profiler.py
│   └── retry.py
├── tests/  # 自动化测试套件，含单元测试和集成测试
│   ├── debug/  # 待补充
│   ├── output/  # 待补充
│   ├── test_browser_smoke.py
│   ├── test_core.py
│   ├── test_integration.py
│   ├── test_scraper_parse.py
│   ├── test_selectors.py
│   └── test_session_check.py
├── .gitignore
├── config.yaml
├── pyproject.toml
├── README.md
└── requirements.txt
```

## S2：核心模块状态

| 模块 | 状态 | 文件数 | TODO数 | 最近修改 | 说明 |
|------|------|--------|--------|---------|------|
| `agent/core` | 活跃 | 5 | 0 | 2026-06-01 | 最近修改距今 0 天内 |
| `agent/mcp` | 活跃 | 1 | 0 | 2026-06-01 | 最近修改距今 0 天内 |
| `agent/cli` | 活跃 | 1 | 0 | 2026-06-01 | 最近修改距今 0 天内 |
| `modes/zhipin` | 活跃 | 10 | 0 | 2026-06-01 | 最近修改距今 0 天内 |
| `shared` | 活跃 | 7 | 0 | 2026-06-01 | 最近修改距今 0 天内 |
| `scripts` | 活跃 | 20 | 0 | 2026-06-01 | 最近修改距今 0 天内 |
| `tests` | 活跃 | 6 | 0 | 2026-06-01 | 最近修改距今 0 天内 |
| `agent` | 活跃 | 7 | 0 | 2026-06-01 | 最近修改距今 0 天内 |
| `modes` | 活跃 | 11 | 0 | 2026-06-01 | 最近修改距今 0 天内 |

## S3：外部依赖与接口

### pyproject.toml 依赖

- `playwright>=1.40.0`
- `camoufox>=0.3.0`
- `mcp>=1.0.0`
- `pyyaml>=6.0`
- `aiofiles>=23.0`
- `httpx>=0.27.0`
- `[dev] pytest>=8.0`
- `[dev] pytest-cov>=5.0`
- `[dev] pytest-asyncio>=0.24`
- `[dev] ruff>=0.4.0`
- `[dev] mypy>=1.10`
- `[dev] pre-commit>=3.7`

### requirements.txt 依赖

- `playwright>=1.45.0`
- `pyyaml>=6.0`
- `mcp>=1.0.0`
- `camoufox>=135.0.1    # 可选：C++引擎级反检测增强，缺失时自动回退到 Playwright`

### 环境变量

（未检测到环境变量引用）

### MCP 对外接口

#### 通用浏览器工具（agent/mcp/server.py）

| 工具名称 | 说明 |
|----------|------|
| `browser_open` | 启动浏览器并导航到指定URL |
| `browser_close` | 关闭浏览器 |
| `browser_navigate` | 导航到指定URL |
| `browser_click` | 点击页面元素 |
| `browser_type_text` | 在输入框中输入文本 |
| `browser_screenshot` | 截取当前页面截图 |
| `browser_snapshot` | 获取页面结构快照 |
| `browser_press` | 模拟键盘按键 |
| `browser_scroll` | 滚动页面 |
| `browser_url` | 获取当前页面URL和标题 |
| `browser_text` | 获取页面纯文本 |
| `browser_html` | 获取页面HTML源码 |

共 **12** 个通用工具

#### `zhipin` 模式工具（modes/zhipin/__init__.py）

| 工具名称 | 说明 |
|----------|------|
| `search_jobs` | 在BOSS直聘搜索职位并存入数据库 |
| `list_jobs` | 查询职位列表（轻量，不含完整描述） |
| `get_job_detail` | 读取单条职位完整信息 |
| `analyze_jobs` | 获取待分析职位数据，AI分析后写回数据库 |
| `boss_get_stats` | 获取求职数据统计概览 |
| `update_status` | 更新职位状态追踪投递进展 |
| `boss_generate_report` | 生成 BOSS 直聘推荐报告 |
| `generate_chat_prompt` | 为指定职位生成招呼语 prompt |
| `filter_jobs` | 从全国搜索结果中按条件筛选、评分、排名 |
| `health_check` | 检查 BOSS 直聘服务是否可用 |

共 **10** 个 zhipin 模式工具


## S4：技术栈

- **语言**：Python >=3.11
- **主框架**：Playwright（浏览器自动化）、MCP Python SDK（Model Context Protocol）、Camoufox（反检测浏览器）
- **数据库**：SQLite（本地存储）、SQLite
- **中间件**：PyYAML（配置管理）

**核心依赖**：
  - `playwright>=1.40.0`
  - `camoufox>=0.3.0`
  - `mcp>=1.0.0`
  - `pyyaml>=6.0`
  - `aiofiles>=23.0`
  - `httpx>=0.27.0`

## S5：已知问题（TODO/FIXME/HACK/XXX）

（未发现 TODO/FIXME/HACK/XXX 标记）

## S6：文档与配置索引

| 文件 | 类型 | 说明 |
|------|------|------|
| `docs/algorithm_complexity.md` | md | 核心算法复杂度说明 |
| `docs/delivery_report_2026-06-01.md` | md | 完整架构重构 — 交付报告 |
| `docs/refactor/iteration_plan.md` | md | BOSS 直聘求职助手 — 功能迭代改进计划 |
| `docs/structure_reports/project_structure_2026-06-01_13-49-36.md` | md | 项目结构现状报告 |
| `docs/structure_reports/project_structure_2026-06-01_13-51-13.md` | md | 项目结构现状报告 |
| `docs/structure_reports/project_structure_2026-06-01_14-02-55.md` | md | 项目结构现状报告 |
| `docs/structure_reports/project_structure_2026-06-01_14-22-13.md` | md | 项目结构现状报告 |
| `docs/superpowers/specs/2026-05-02-boss-job-hunter-design.md` | md | BOSS 直聘求职助手 — 设计规格 |
| `config/.pre-commit-config.yaml` | yaml | Pre-commit 钩子配置（ruff → mypy → bandit） |
| `config/ci/ci.yml` | yml | ============================================================================= |
| `config/mcp_config.json` | json | AI 编辑器 MCP 服务连接配置 |
| `config.yaml` | yaml | 用户配置文件（搜索/城市/过滤/运行时/代理/页面分析） |
| `pyproject.toml` | toml | 项目元数据、依赖声明、工具配置 |
| `README.md` | md | 项目入口文档 |
| `scripts/current_structure.md` | md | 当前项目结构（2026-06-01 最新） |
| `scripts/delivery_report.md` | md | 追缴交付 · 算法复杂度说明 + 结构扫描程序源码 |
| `scripts/delivery_template.md` | md | {任务标题} |
| `scripts/project_structure_report.md` | md | 项目结构重组完成报告 |
| `scripts/r6_r11_confirmation.md` | md | R6-R11 架构重组完成确认 |
| `scripts/scanner_plan.md` | md | 开发计划 · project_structure_scanner.py |

共 **20** 个文件

---

*由 `scripts/project_structure_scanner.py` 自动生成*