# 项目架构概览

## 1. 分层架构图

```
┌──────────────────────────────────────────────────────────────┐
│                        ┌──────────────┐                      │
│  用户入口              │  CLI / MCP   │                      │
│                        │   (agent/)   │                      │
│   ┌────────┐           └──────┬───────┘                      │
│   │ 命令行  │◄───────        │                              │
│   │--mode   │    argparse     │ importlib.import_module       │
│   └────────┘                 │                              │
│            ┌─────────────────┼────────────────────┐          │
│            │    业务模式层    │                    │          │
│            │   (modes/zhipin/)                    │          │
│            │       │                              │          │
│            │       │ 调用 agent/core/ 浏览器能力    │          │
│            │       ▼                              │          │
│            │  ┌──────────────┐   ┌──────────────┐ │          │
│            │  │ 业务逻辑实现   │   │ MCP 工具注册 │ │          │
│            │  │ scraper/     │   │ CLI 命令注册  │ │          │
│            │  │ pre_filter/  │   │              │ │          │
│            │  │ storage/     │   │              │ │          │
│            │  └──────┬───────┘   └──────────────┘ │          │
│            └─────────┼────────────────────────────┘          │
│                      │                                      │
│                      │ 调用                                │
│                      ▼                                      │
│            ┌──────────────────────────┐                     │
│            │   通用浏览器引擎层        │                     │
│            │   (agent/core/)          │                     │
│            │  ┌────────┐ ┌─────────┐  │                     │
│            │  │browser │ │anti_detect│ │                     │
│            │  │ 控制器  │ │ 反检测    │ │                     │
│            │  ├────────┤ ├─────────┤  │                     │
│            │  │session │ │page     │  │                     │
│            │  │ 会话管理│ │ 页面分析  │ │                     │
│            │  └────────┘ └─────────┘  │                     │
│            └──────────┬───────────────┘                     │
│                       │                                     │
│                       │ 使用                                │
│                       ▼                                     │
│            ┌──────────────────────────┐                     │
│            │   共享基础设施层          │                     │
│            │   (shared/)              │                     │
│            │  config / logging /      │                     │
│            │  retry / exceptions /    │                     │
│            │  profiler / fingerprint  │                     │
│            └──────────────────────────┘                     │
└──────────────────────────────────────────────────────────────┘

  ──→ 调用方向（上层→下层）
  - - → 注册/绑定（模式层→入口层反向注册）
```

## 2. 各层职责

| 层 | 目录 | 一句话职责 | 不负责 |
|----|------|-----------|--------|
| **入口层** | `agent/cli/` + `agent/mcp/` | 解析用户输入（CLI 参数或 MCP 协议），分派到对应业务模式 | 不包含任何业务逻辑，不直接调用浏览器底层 API |
| **业务插件层** | `modes/*/` | 实现某个具体业务（如 BOSS 直聘搜索/过滤/分析），向入口层注册工具和命令 | 不操作浏览器原语，不处理 Cookie/反检测细节 |
| **通用浏览器引擎层** | `agent/core/` | 封装 Camoufox 浏览器控制（底层基于 Playwright）、反检测、会话管理，提供与业务无关的浏览器 API | 不包含任何业务词汇（无 "BOSS"/"职位"/"薪资"），不调用 shared/ 以外的模块 |
| **共享基础设施层** | `shared/` | 提供所有模块共用的工具：配置加载、日志、重试、异常体系、指纹生成 | 不依赖任何其他层，不含业务逻辑 |

## 3. 模块职责表

| 目录 | 职责 | 允许依赖 | 禁止依赖 |
|------|------|---------|---------|
| `agent/cli/main.py` | 解析 `--mode` + 子命令，importlib 加载模式，分派到 `run_cli()` | `shared/`、`modes/`（通过 importlib） | 不允许直接 import 任何 `modes/zhipin/` 下的具体模块；不允许直接 import 浏览器库 |
| `agent/mcp/server.py` | 启动 MCP 服务，注册通用浏览器工具（12 个）+ 扫描 `modes/` 注册模式工具 | `shared/`、`agent/core/`、`modes/`（通过 pkgutil 动态扫描） | 不允许硬编码业务工具名 |
| `agent/core/browser.py` | Camoufox 引擎控制器（启动/导航/点击/截图/Cookie） | `shared/`、`camoufox` | 不允许出现 "zhipin""BOSS""job" 等业务词汇 |
| `agent/core/anti_detect.py` | 反检测 JS 注入、拟人操作、指纹伪装 | `shared/` | 不允许业务相关判断 |
| `agent/core/session.py` | Cookie/StorageState 持久化管理 | `shared/` | 不允许业务相关判断 |
| `agent/core/page.py` | 截图、HTML 快照、通用页面分析 | `shared/`、`agent/core/browser.py` | 不允许硬编码业务选择器 |
| `agent/core/agent.py` | BrowserAgent 高层封装（组合 browser + session + page） | `agent/core/` 子模块 | 不允许直接依赖浏览器底层 API |
| `modes/zhipin/__init__.py` | 模式入口：导出业务函数、注册 MCP 工具（10 个）、注册 CLI 子命令 | `modes/zhipin/` 子模块、`mcp.types`、`agent/core/` | 不允许直接操作浏览器底层 API |
| `modes/zhipin/scraper.py` | BOSS 直聘搜索/采集/分析/报告（648 行核心业务） | `modes/zhipin/` 子模块、`agent/core/anti_detect`、`shared/` | 不允许直接 import 浏览器库（通过 agent 间接使用） |
| `modes/zhipin/selectors.py` | BOSS 直聘所有 DOM 选择器集中管理 | 纯常量无依赖 | 无 |
| `modes/zhipin/storage.py` | SQLite CRUD：岗位数据持久化 | `shared/` | 不允许 import 浏览器模块 |
| `modes/zhipin/pre_filter.py` | 薪资/标题/公司/活跃度四规则过滤 | `shared/config.py` | 无 |
| `modes/zhipin/keyword_strategy.py` | 按城市搜索结果量自适应选关键词 | `shared/config.py` | 无 |
| `modes/zhipin/city_codes.py` | 城市→编码映射 + 租金参考数据 | 无（纯数据） | 无 |
| `modes/zhipin/exporter.py` | 分析结果导入导出 | `modes/zhipin/storage.py` | 无 |
| `modes/zhipin/page_analyzer.py` | BOSS 页面类型/验证码/反爬检测 | `modes/zhipin/selectors.py`、`agent/core/page.py` | 无 |
| `shared/config.py` | YAML 配置加载与缓存 | `pyyaml` | 不依赖任何项目模块 |
| `shared/logging_config.py` | 统一日志格式与输出 | `logging` 标准库 | 不依赖任何项目模块 |
| `shared/retry.py` | 指数退避重试装饰器 | 无（纯函数） | 不依赖任何项目模块 |
| `shared/exceptions.py` | 浏览器自动化异常体系 | 无 | 不依赖任何项目模块 |

## 4. 交付链路

报告交付支持**两条路径**，按优先级序使用：

### 路径 A：对话内直接交付（首选）

当监管（Boss）与项目经理使用同一 AI 平台时适用。

- **方式**：对话流中以纯文本交付报告内容，不依赖外部工具
- **优势**：零环境依赖、零网络故障点、零浏览器兼容问题
- **触发条件**：监管与项目经理共享同一 AI 会话
- **验证**：本次 O1-O3 指令的交付即走此路径

### 路径 B：`scripts/send_report.py` 浏览器自动发送（备选）

当监管与项目经理使用**不同平台**，或对话内交付不可用时启用。

- **方式**：浏览器模拟操作，自动填入 DeepSeek 网页端输入框并发送
- **命令**：`python scripts/send_report.py <报告文件> [--headless]`
- **依赖**：Camoufox 浏览器、`sessions/storage_state.json` 登录态
- **注意事项**：
  - 依赖浏览器环境（Camoufox 浏览器二进制、屏幕分辨率等）
  - 依赖 DeepSeek 网页端 UI 结构（CSS 选择器可能随改版失效）
  - 依赖登录态有效（需定期刷新 Cookie）
  - 支持 `--headless` 参数静默发送

### 路径选择决策树

```
是否同一 AI 平台？
├── 是 → 路径 A：对话内直接交付
└── 否 → 路径 B：send_report.py 浏览器发送
         ├── 发送成功 → 完成
         └── 发送失败 → 手动复制报告内容并粘贴至监管会话
```

## 5. 关键设计约束

1.  **Agent 层不允许出现业务词汇**。`agent/core/` 下的任何文件不得包含 "BOSS"、"zhipin"、"job"、"职位"、"薪资" 等业务字符串。业务选择器通过参数注入，而非硬编码。

2.  **业务层不允许直接操作浏览器底层 API**。`modes/zhipin/` 调用 `agent/core/` 的封装方法（如 `agent.navigate()`），不得直接操作底层浏览器 SDK。

3.  **依赖方向只能向下**。`shared/` 不依赖任何其他层；`agent/core/` 依赖 `shared/` 但不依赖 `modes/`；`modes/` 依赖 `agent/core/` 和 `shared/`；`agent/cli/` 和 `agent/mcp/` 通过动态加载（importlib/pkgutil）调用 `modes/`，而非静态 import。

4.  **模式注册是反向的**。业务层不主动启动——入口层（CLI/MCP）启动后通过 `importlib.import_module("modes.x")` 发现模式，模式通过 `get_mcp_tools()` / `register_cli()` 向入口层注册能力。

5.  **配置只有一份来源**。所有运行时配置从 `config.yaml` 加载，通过 `shared.config.get_config()` 获取。模块不得自己硬编码配置值或读取其他配置文件。
