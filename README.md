# Browser Agent

<p align="center">
  <strong>浏览器自动化 AI Agent 框架</strong><br>
  统一的 CLI 命令行、MCP 协议服务器和多模式扩展能力
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

- **双引擎浏览器自动化** — Camoufox (C++级反检测) + Playwright (JS引擎) 双引擎自动回退
- **MCP 协议服务器** — 向 AI 编辑器暴露 40+ 浏览器工具，支持 stdio 和 SSE 两种传输模式
- **CLI 接口** — 完整的命令行工具链，支持浏览器控制、登录态管理、任务编排
- **多模式扩展** — `modes/` 目录下即插即用的业务模式，每个模式独立注册 MCP 工具和 CLI 命令
- **会话持久化** — Cookie + StorageState 双机制，跨平台重启复用登录态
- **页面分析能力** — 截图、DOM 提取、内容分析、健康检测
- **反检测与人类化** — 浏览器指纹伪装、行为模拟、速度控制
- **合规访问限制** — 政府网站访问频率限制，符合合规要求
- **对话式 Agent** — 集成 LLM 支持的聊天 Agent，可调用工具执行任务

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
# 或使用可编辑安装（推荐）
pip install -e .

# 3. 安装浏览器
playwright install chromium

# 4. 验证安装
agent --help
```

### 快速上手

```bash
# 启动浏览器交互模式
agent browse

# 启动 MCP 服务器（供 AI 编辑器连接）
python -m browser_agent.mcp.server

# 使用 BOSS 直聘模式搜索岗位
agent --mode zhipin search
```

## 使用指南

### CLI 命令

主 CLI 入口为 `agent` 命令（通过 `pip install -e .` 注册）：

```bash
# 查看帮助
agent --help

# 通用浏览器命令
agent browse                    # 启动浏览器交互浏览
agent login --url <URL>        # 登录网站并保存会话
agent check                    # 检查系统健康状态

# 加载业务模式
agent --mode zhipin search     # BOSS 直聘搜索
agent --mode zhipin stats      # 查看搜索统计
agent --mode zhipin report     # 生成分析报告
```

#### BOSS 直聘模式 (zhipin)

```bash
# 登录并保存会话
agent --mode zhipin login

# 搜索岗位
agent --mode zhipin search --cities "深圳,广州" --keywords "普工,仓管"

# 查看统计
agent --mode zhipin stats

# 生成报告
agent --mode zhipin report --output ./report.md
```

### MCP 服务器

MCP 服务器支持两种运行模式：

#### 1. stdio 模式（推荐，供 AI 编辑器集成）

```bash
python -m browser_agent.mcp.server
```

#### 2. SSE 模式（远程连接）

```bash
python -m browser_agent.mcp.server --port 8080 --transport sse
```

#### AI 编辑器配置

在 Cursor、Windsurf 或其他支持 MCP 的编辑器配置中添加：

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

#### MCP 工具列表

| 类别 | 工具 | 说明 |
|------|------|------|
| 浏览器控制 | `browser_open` | 启动浏览器 |
| | `browser_close` | 关闭浏览器 |
| | `browser_navigate` | 导航到 URL |
| | `browser_navigate_back` | 后退 |
| 页面交互 | `browser_click` | 点击元素 |
| | `browser_type` | 输入文本 |
| | `browser_hover` | 悬停元素 |
| | `browser_scroll` | 滚动页面 |
| 页面信息 | `browser_snapshot` | 获取页面快照 |
| | `browser_take_screenshot` | 截图 |
| | `browser_text` | 获取文本内容 |
| | `browser_html` | 获取 HTML |
| | `browser_url` | 获取当前 URL |
| 会话管理 | `browser_cookie_list` | 列出 Cookie |
| | `browser_cookie_get` | 获取 Cookie |
| | `browser_cookie_set` | 设置 Cookie |
| | `browser_storage_state_save` | 保存会话状态 |
| | `browser_storage_state_load` | 加载会话状态 |
| 页面分析 | `browser_analyze_page` | 完整页面分析 |
| | `browser_quick_check` | 快速健康检查 |

### 对话式 Agent

```bash
# 启动聊天 Agent
agent chat

# 一次性提问
agent chat --query "帮我搜索深圳的普工岗位"
```

聊天命令支持：
- `/tone <预设>` — 切换语气（专业务实/亲切友好/详细全面/幽默风趣）
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
│   │   ├── cli/main.py             #   CLI 入口（argparse + 模式加载）
│   │   ├── core/                   #   浏览器引擎核心
│   │   │   ├── browser.py          #     双引擎控制器（Camoufox → Playwright）
│   │   │   ├── agent.py            #     高级 Agent 封装
│   │   │   ├── session.py          #     会话持久化（Cookie + StorageState）
│   │   │   ├── anti_detect.py      #     反检测与人类化模拟
│   │   │   ├── page.py             #     页面操作封装
│   │   │   ├── perceiver.py        #     页面感知与分析
│   │   │   ├── executor.py         #     动作执行与行为模拟
│   │   │   ├── decider.py          #     决策引擎与流程编排
│   │   │   ├── health_monitor.py   #     健康监控与自动修复
│   │   │   ├── capabilities.py     #     能力管理与工具分组
│   │   │   ├── ref_manager.py      #     元素引用管理
│   │   │   ├── log_collector.py    #     日志收集器
│   │   │   └── mcp_config.py       #     MCP 配置加载
│   │   ├── mcp/                    #   MCP 协议层
│   │   │   ├── server.py           #     服务器生命周期
│   │   │   ├── definitions.py      #     工具定义与 schema
│   │   │   ├── handlers.py         #     工具处理函数
│   │   │   └── validation.py       #     参数校验
│   │   ├── chat/                   #   对话式 Agent
│   │   │   ├── engine.py           #     LLM 引擎
│   │   │   ├── knowledge.py        #     知识库
│   │   │   ├── tools.py            #     工具调用
│   │   │   ├── tone.py             #     语气预设
│   │   │   └── cli.py              #     聊天 CLI
│   │   └── flows/                  #   流程骨架
│   │       ├── builtin.py          #     通用流程模板
│   │       └── zhipin/             #     BOSS 直聘流程
│   ├── modes/                      # 业务模式层（即插即用）
│   │   ├── __init__.py             #   模式注册规范
│   │   └── zhipin/                 #   BOSS 直聘适配器
│   │       ├── scraper.py          #     抓取引擎
│   │       ├── search_flow.py      #     搜索流程
│   │       ├── selectors.py        #     DOM 选择器
│   │       ├── page_analyzer.py    #     页面分析
│   │       ├── storage.py          #     SQLite 持久化
│   │       ├── exporter.py         #     数据导出
│   │       ├── pre_filter.py       #     前置过滤（废弃）
│   │       ├── keyword_strategy.py #     关键词策略
│   │       └── city_codes.py       #     城市代码
│   ├── shared/                     # 共享基础设施
│   │   ├── config.py               #   YAML 配置加载
│   │   ├── logging_config.py       #   统一日志配置
│   │   ├── retry.py                #   指数退避重试
│   │   ├── error_handler.py        #   异常分类与恢复
│   │   ├── exceptions.py           #   异常体系
│   │   ├── profiler.py             #   性能分析
│   │   ├── delay.py                #   统一延迟工具
│   │   ├── fingerprint_manager.py  #   浏览器指纹管理
│   │   ├── gov_site_limiter.py     #   政府网站访问限制
│   │   ├── gov_site_decorator.py   #   政府网站装饰器
│   │   └── engine/                 #   通用抓取引擎
│   │       ├── scraping_engine.py  #     声明式抓取引擎
│   │       ├── profile.py          #     站点配置文件
│   │       ├── dom_reader.py       #     DOM 读取器
│   │       ├── url_builder.py      #     URL 构建器
│   │       ├── filter_chain.py     #     过滤链
│   │       ├── report_builder.py   #     报告生成器
│   │       └── adapter_protocol.py #     适配器协议
│   └── cli/                        # CLI 工具（旧版，保留兼容）
│       └── main.py
├── tests/                          # 测试
│   ├── test_browser.py
│   ├── test_core.py
│   ├── test_mcp_handlers.py
│   └── ...
├── config/                         # 配置
│   ├── mcp_config.json
│   └── .pre-commit-config.yaml
├── profiles/                       # 站点配置（如果存在）
│   └── zhipin.yaml
├── docs/                           # 文档
│   ├── 交付报告/
│   ├── 技术文档/
│   ├── 分析报告/
│   ├── 计划/
│   └── 运行结果/
├── scripts/                        # 工具脚本
│   ├── login/
│   ├── dev/
│   ├── report/
│   └── browser/
├── data/                           # 数据目录（运行时生成）
│   ├── jobs.db
│   ├── logs/
│   ├── screenshots/
│   ├── snapshots/
│   └── export/
├── config.yaml                     # 用户配置
├── pyproject.toml                  # 项目元数据
├── requirements.txt                # 依赖
├── zhipin-cli.bat                  # Windows 快捷启动
├── LICENSE                         # MIT 许可证
├── CONTRIBUTING.md                 # 贡献指南
└── README.md                       # 本文档
```

## 架构说明

### 三层架构

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
│                 共享基础设施层 (Shared)                  │
│  ┌───────────────────────────────────────────────────┐ │
│  │  配置管理 | 日志 | 重试 | 异常 | 性能分析 | 延迟  │ │
│  └───────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────┐ │
│  │           声明式抓取引擎 (Scraping Engine)        │ │
│  │  站点配置 → DOM读取 → 过滤链 → 报告生成          │ │
│  └───────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                 核心引擎层 (Core)                        │
│  ┌───────────────────────────────────────────────────┐ │
│  │  感知层 (Perceiver) → 决策层 (Decider) → 执行层    │ │
│  │                              (Executor)            │ │
│  └───────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────┐ │
│  │  浏览器控制器 (BrowserController)                 │ │
│  │  Camoufox (优先) ←→ Playwright (回退)             │ │
│  └───────────────────────────────────────────────────┘ │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ 会话管理     │  │ 反检测       │  │ 健康监控     │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 关键设计特点

1. **双引擎回退机制** — Camoufox 提供 C++ 级反检测，失败时自动回退到 Playwright
2. **声明式抓取引擎** — 通过 YAML 配置定义站点结构，零代码适配新站点
3. **能力组合系统** — 按功能分组管理 MCP 工具，支持动态启用/禁用
4. **政府网站合规访问** — 内置频率限制和访问控制
5. **Python 3.11+** — 现代异步编程风格，完整类型注解

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

A: Camoufox 是可选依赖，如果安装失败，系统会自动回退到 Playwright。你可以放心使用。

### Q: 如何保存和恢复登录态？

A: 使用 `agent login` 命令登录后，系统会自动保存会话。下次启动时会自动恢复。

### Q: MCP 工具没有显示在编辑器中？

A: 请检查：
1. `cwd` 配置是否指向项目根目录
2. `PYTHONPATH` 是否包含 `src` 目录
3. 服务器启动日志是否有错误

## 贡献指南

欢迎贡献代码！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详细的贡献流程。

## 许可证

[MIT License](LICENSE) © 2026 Browser Agent Contributors

---

<p align="center">
  如有问题，欢迎提交 Issue 或 Pull Request！
</p>
