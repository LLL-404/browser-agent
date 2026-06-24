# Browser Agent

<p align="center">
  <strong>浏览器自动化 AI Agent 框架</strong><br>
  Camoufox C++ 级反检测 · 感知→决策→执行循环 · MCP 协议 · 即插即用业务模式
</p>

<p align="center">
  <a href="#核心能力">核心能力</a> •
  <a href="#快速启动">快速启动</a> •
  <a href="#使用指南">使用指南</a> •
  <a href="#架构说明">架构</a> •
  <a href="#配置说明">配置</a> •
  <a href="#许可证">许可证</a>
</p>

## 核心能力

- **Camoufox 单引擎** — C++ 级反检测浏览器，无 JS 注入回退
- **感知→决策→执行循环** — `perceiver` → `decider` → `executor` 三步循环，FlowSkeleton 流程骨架自动匹配
- **MCP 协议服务器** — 向 AI 编辑器暴露 27+ 浏览器工具，stdio/SSE 双模式
- **CLI 工具链** — 8 个子命令：浏览/提取/交互/登录/快照/监控/对话/服务器
- **会话持久化** — Cookie + StorageState 双机制，跨重启复用
- **反检测与人类化** — 指纹伪装、行为模拟、速度控制
- **合规访问** — 政府网站频率限制
- **业务模式即插即用** — `modes/` 下独立注册 MCP 工具 + CLI 命令
- **流程骨架 (FlowSkeleton)** — `flows/` 下预置通用登录/搜索/翻页/验证码流程

## 快速启动

### 环境要求

- Python 3.11+
- Windows / macOS / Linux

### 安装步骤

```bash
# 1. 克隆仓库
git clone https://github.com/LLL-404/browser-agent.git
cd browser-agent

# 2. 安装依赖
pip install -r requirements.txt
# 或可编辑安装（推荐）
pip install -e .

# 3. 验证安装
agent --help
```

### 快速上手

```bash
# 智能浏览指定 URL
agent browse https://example.com

# 提取页面元素
agent extract https://example.com "h2.title" --fields innerText, href

# 登录并保存会话
agent login https://example.com/login

# 启动 MCP 服务器（供 AI 编辑器连接）
agent server

# 对话模式
agent chat
```

## 使用指南

### CLI 命令

主 CLI 入口 `agent`：

```bash
agent --help                     # 查看帮助

agent browse <url> [task]        # 智能浏览，可选任务描述
agent extract <url> <selector>   # 从页面提取数据（CSS 选择器）
agent login <url>                # 手动登录并保存 session
agent snapshot [url]             # 获取页面结构快照
agent interact click/type/scroll/press  # 单步交互
agent monitor check/stats/clean  # 浏览器健康监控
agent chat                       # LLM 对话 Agent
agent server                     # 启动 MCP 服务器
```

### CLI 示例

```bash
# 浏览 + 自动执行任务
agent browse https://www.zhipin.com "帮我搜索深圳的Python岗位，列出薪资"

# 提取数据
agent extract https://news.ycombinator.com "tr.athing" --fields innerText --limit 10 -o hn.json

# 单步交互
agent interact click ".search-button" --url https://example.com
agent interact type "#search-input" "browser agent"

# 对话模式（支持 /tone /load /sources /auto /help /exit）
agent chat --tone professional
```

### MCP 服务器

MCP 服务器支持两种运行模式：

#### 1. stdio 模式（推荐，供 AI 编辑器集成）

```bash
agent server
# 或
python -m browser_agent.mcp.server
```

#### 2. SSE 模式（远程连接）

```bash
python -m browser_agent.mcp.server --port 8080 --host 0.0.0.0
```

启动后 MCP 服务器会自动管理浏览器生命周期，无需手动调用 `browser_open`。

#### AI 编辑器配置

在 Cursor、Windsurf 等支持 MCP 的编辑器中：

```json
{
  "mcpServers": {
    "browser-agent": {
      "command": "python",
      "args": ["-m", "browser_agent.mcp.server"],
      "cwd": "D:\\G\\github\\游览器agent",
      "env": {
        "PYTHONPATH": "D:\\G\\github\\游览器agent\\src"
      }
    }
  }
}
```

#### MCP 工具列表（27 个）

| 类别 | 工具 |
|------|------|
| **浏览器控制** | `browser_open` `browser_close` `browser_navigate` `browser_navigate_back` `browser_resize` |
| **页面交互** | `browser_click` `browser_type` `browser_hover` `browser_select_option` `browser_fill_form` `browser_file_upload` `browser_press_key` `browser_scroll` |
| **页面信息** | `browser_snapshot` `browser_take_screenshot` `browser_text` `browser_html` `browser_url` |
| **等待/弹窗** | `browser_wait_navigation` `browser_wait_selector` `browser_handle_dialog` |
| **会话管理** | `browser_cookie_list` `browser_cookie_get` `browser_cookie_set` `browser_storage_state` `browser_storage_state_set` `browser_localstorage_get` `browser_localstorage_set` |
| **DevTools** | `browser_console_messages` `browser_network_requests` `browser_evaluate` `browser_investigate` |
| **视觉** | `browser_click_coordinate` `browser_drag_coordinate` `browser_hover_coordinate` `browser_screenshot_save` |
| **PDF** | `browser_pdf_save` |
| **CDP** | `devtools_capture_profiling` `devtools_collect_garbage` `devtools_enable_device_emulation` `devtools_reset_device_emulation` `devtools_send_command` `devtools_set_location` |

### 对话式 Agent

```bash
# 启动聊天 Agent
agent chat

# 指定语气
agent chat --tone professional
```

聊天内支持：
- `/tone <预设>` — 切换语气（professional / friendly / detailed / humorous）
- `/load <路径>` — 加载知识文档
- `/sources` — 查看知识来源
- `/auto` — 切换自动确认模式
- `/help` — 显示帮助
- `/exit` — 退出

## 项目结构

```
browser-agent/
├── src/
│   ├── browser_agent/              # 核心框架层
│   │   ├── cli/main.py             #   CLI 入口（argparse，8 个子命令）
│   │   ├── core/                   #   浏览器引擎核心（感知→决策→执行）
│   │   │   ├── browser.py          #     Camoufox 引擎控制器
│   │   │   ├── agent.py            #     高级 Agent 封装（BrowsingAgent）
│   │   │   ├── session.py          #     会话持久化（Cookie + StorageState）
│   │   │   ├── anti_detect.py      #     反检测与人类化模拟
│   │   │   ├── page.py             #     页面操作封装
│   │   │   ├── perceiver.py        #     感知层：页面分析/分类/信息提取
│   │   │   ├── decider.py          #     决策层：FlowSkeleton 匹配 + 动作选择
│   │   │   ├── executor.py         #     执行层：动作执行与行为模拟
│   │   │   ├── health_monitor.py   #     健康监控与自动修复
│   │   │   ├── capabilities.py     #     能力管理与工具分组
│   │   │   ├── ref_manager.py      #     元素引用管理 (@e1 引用系统)
│   │   │   ├── log_collector.py    #     日志收集器
│   │   │   └── mcp_config.py       #     MCP 配置加载
│   │   ├── mcp/                    #   MCP 协议层
│   │   │   ├── server.py           #     服务器生命周期管理
│   │   │   ├── definitions.py      #     27+ 工具定义与 schema
│   │   │   ├── handlers.py         #     工具处理函数
│   │   │   └── validation.py       #     参数校验
│   │   ├── chat/                   #   对话式 Agent
│   │   │   ├── engine.py           #     LLM 引擎
│   │   │   ├── knowledge.py        #     知识库
│   │   │   ├── tools.py            #     工具调用
│   │   │   ├── tone.py             #     语气预设
│   │   │   └── cli.py              #     聊天 CLI
│   │   └── flows/                  #   流程骨架（FlowSkeleton）
│   │       ├── builtin.py          #     通用流程模板（登录/搜索/翻页/验证码）
│   │       ├── builtin/            #     Flow 扩展模块
│   │       ├── zhipin/             #     BOSS 直聘语义流程
│   │       └── qcc/                #     企查查语义流程
│   ├── modes/                      # 业务模式层（即插即用）
│   │   ├── __init__.py             #   模式注册规范（get_mcp_tools / handle_mcp_call）
│   │   └── zhipin/                 #   BOSS 直聘适配器
│   │       ├── scraper.py          #     抓取引擎
│   │       ├── pipeline.py         #     数据处理管道
│   │       ├── search_flow.py      #     搜索流程
│   │       ├── smart_hunt.py       #     智能猎头模式
│   │       ├── selectors.py        #     DOM 选择器
│   │       ├── page_analyzer.py    #     页面分析
│   │       ├── storage.py          #     SQLite 持久化
│   │       ├── exporter.py         #     数据导出
│   │       ├── gov_verify.py       #     政务网站验证处理
│   │       ├── pre_filter.py       #     前置过滤
│   │       ├── keyword_strategy.py #     关键词策略
│   │       └── city_codes.py       #     城市代码
│   └── shared/                     # 共享基础设施
│       ├── config.py               #   YAML 配置加载
│       ├── logging_config.py       #   统一日志配置
│       ├── retry.py                #   指数退避重试
│       ├── error_handler.py        #   异常分类与恢复
│       ├── exceptions.py           #   异常体系
│       ├── profiler.py             #   性能分析
│       ├── delay.py                #   统一延迟工具
│       ├── fingerprint_manager.py  #   浏览器指纹管理
│       ├── gov_site_limiter.py     #   政府网站访问限制
│       └── gov_site_decorator.py   #   政府网站装饰器
├── tests/                          # 测试
│   ├── test_browser.py             #   浏览器核心测试
│   ├── test_core.py                #   核心模块测试
│   ├── test_mcp_handlers.py        #   MCP 处理器测试
│   ├── test_browser_smoke.py       #   冒烟测试
│   ├── test_integration.py         #   集成测试
│   ├── test_session_check.py       #   会话检测测试
│   ├── test_scraper_parse.py       #   抓取解析测试
│   ├── test_selectors.py           #   选择器测试
│   ├── test_fingerprint_manager.py #   指纹管理测试
│   └── test_profiler.py            #   性能分析测试
├── config/                         # 配置文件
│   ├── mcp_config.json             #   MCP 服务器配置
│   ├── .pre-commit-config.yaml     #   Git hooks
│   ├── profiles/                   #   站点配置（YAML）
│   │   └── zhipin.yaml
│   └── ci/                         #   CI 配置
├── docs/                           # 文档
│   ├── 技术文档/
│   ├── 计划/
│   └── superpowers/
├── scripts/                        # 实用脚本
│   ├── browser/                    #   浏览器工具（download_camoufox.py 等）
│   ├── login/                      #   登录辅助
│   ├── dev/                        #   开发工具
│   ├── report/                     #   报告生成
│   ├── opencode/                   #   Agent 重启脚本
│   ├── run_hunt.bat                #   Windows 一键猎头
│   ├── run_search.bat              #   Windows 一键搜索
│   └── zhipin-cli.bat              #   Windows BOSS 直聘 CLI
├── data/                           # 运行时数据
│   ├── browser-data/               #   浏览器运行时数据
│   ├── logs/                       #   运行日志
│   ├── screenshots/                #   截图
│   ├── snapshots/                  #   页面快照
│   ├── export/                     #   导出文件
│   ├── reports/                    #   报告
│   └── 沟通记录/                   #   跨 Agent 沟通记录
├── config.yaml                     # 用户运行时配置
├── pyproject.toml                  # 项目元数据 + 工具链配置（ruff/mypy/pytest）
├── requirements.txt                # 依赖列表
├── LICENSE                         # MIT 许可证
├── CONTRIBUTING.md                 # 贡献指南
├── AGENTS.md                       # Agent 协作约定（给 AI 开发助手阅读）
└── README.md                       # 本文档
```

## 架构说明

### 四层架构

```
┌─────────────────────────────────────────────────────────┐
│                    用户界面层 (UI)                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │
│  │     CLI     │  │  MCP Server │  │  Chat Agent     │ │
│  └─────────────┘  └─────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                   业务模式层 (Modes)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   zhipin     │  │    qcc       │  │  (更多模式)  │ │
│  │  (BOSS直聘)  │  │   (企查查)   │  │              │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                 核心引擎层 (Core)                        │
│  ┌───────────────────────────────────────────────────┐ │
│  │       感知 (Perceiver) → 决策 (Decider) → 执行    │ │
│  │                              (Executor)            │ │
│  │       循环驱动，FlowSkeleton 自动匹配页面类型      │ │
│  └───────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────┐ │
│  │  浏览器控制器 (BrowserController)                 │ │
│  │  Camoufox C++ 引擎 · 无 JS 注入回退              │ │
│  └───────────────────────────────────────────────────┘ │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ 会话管理     │  │ 反检测       │  │ 健康监控     │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                 共享基础设施层 (Shared)                  │
│  ┌───────────────────────────────────────────────────┐ │
│  │  配置管理 | 日志 | 重试 | 异常 | 性能分析 | 延迟  │ │
│  └───────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────┐ │
│  │  指纹管理 | 政府网站频率限制                       │ │
│  └───────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 关键设计特点

1. **Camoufox 单引擎** — C++ 级反检测，Playwright 兼容 API，零 JS 注入
2. **感知→决策→执行循环** — `perceiver.py` 分析页面 → `decider.py` 匹配 FlowSkeleton → `executor.py` 执行动作
3. **FlowSkeleton 流程骨架** — `flows/` 下声明式流程模板，按 URL 模式 + 页面类型自动匹配
4. **业务模式协议** — `modes/` 下每个包实现 `get_mcp_tools()` + `handle_mcp_call()`，即插即用
5. **能力组合系统** — `capabilities.py` 按功能分组管理 MCP 工具，动态启用/禁用
6. **Python 3.11+** — 现代异步编程风格，完整类型注解

## 配置说明

主配置文件为 `config.yaml`，包含以下主要配置项：

### 日志配置

```yaml
logging:
  level: INFO  # DEBUG | INFO | WARNING | ERROR
```

### 运行时延迟

```yaml
runtime:
  delays:
    page_ready: 1           # 页面加载后等待
    navigation: 0.5         # 导航后等待
    page_stable: 3          # 等待页面稳定
    # ... 更多配置
```

### 政府网站限制

```yaml
government_site:
  enabled: true
  domains:
    - "gov.cn"
    - "caac.gov.cn"
    # ...
  rate_limit:
    max_requests_per_minute: 5
    max_requests_per_hour: 30
    min_interval_ms: 3000
```

### BOSS 直聘配置

```yaml
modes:
  zhipin:
    search:
      education: "大专"
      keywords:
        L1: ["普工", "操作工", ...]
        L2: ["仓管", "质检", ...]
      cities:
        priority_1: ["深圳", "广州", ...]
        # ...
```

## 开发指南

### 代码质量工具

```bash
# 代码检查
ruff check src/

# 自动修复
ruff check --fix src/

# 格式化
ruff format src/

# 类型检查
mypy src/
```

### 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_browser.py -v

# 覆盖率报告
pytest --cov=src --cov-report=html
```

### 创建新业务模式

在 `src/modes/` 下创建新目录，例如 `my_mode/`：

```python
# src/modes/my_mode/__init__.py

def get_mcp_tools():
    """返回模式的 MCP 工具定义"""
    return []

def handle_mcp_call(tool_name, args):
    """处理 MCP 工具调用"""
    pass

def register_cli(subparsers):
    """注册 CLI 子命令"""
    pass

def run_cli(args):
    """运行 CLI 命令"""
    pass
```

## 常见问题

### Q: Camoufox 安装失败怎么办？

A: 确保已安装：`pip install camoufox`，然后运行 `python scripts/browser/download_camoufox.py`。

### Q: 如何保存和恢复登录态？

A: 使用 `agent login <url>` 手动登录后自动保存 session。下次浏览同域名会自动恢复。

### Q: MCP 工具没有显示在编辑器中？

A: 请检查：
1. `cwd` 配置是否指向项目根目录
2. `PYTHONPATH` 是否包含 `src` 目录
3. 服务器启动日志是否有错误

### Q: 旧版 `agent --mode zhipin` 还能用吗？

A: `--mode` 参数已废弃。直接使用 `agent browse https://www.zhipin.com "任务描述"`。

## 贡献指南

欢迎贡献代码！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详细的贡献流程。

## 许可证

[MIT License](LICENSE) © 2026 Browser Agent Contributors

---

<p align="center">
  如有问题，欢迎提交 Issue 或 Pull Request！
</p>
