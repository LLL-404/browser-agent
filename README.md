# boss-job-hunter

基于浏览器自动化的 BOSS 直聘岗位搜索与分析工具，通过 MCP 协议向 AI 编辑器暴露浏览器和搜索能力。

## 技术栈

- Python >=3.11
- Playwright（浏览器自动化）
- Camoufox（可选反检测浏览器，自动回退 Playwright）
- MCP Python SDK（Model Context Protocol 服务）
- SQLite（本地存储）
- PyYAML（配置管理）

## 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 安装浏览器
playwright install chromium

# 3. 配置
#    编辑 config.yaml，设置搜索关键词和目标城市

# 4. 运行 CLI 交互搜索
python -m entry.cli.main search

# 5. 或启动 MCP 服务器（供 AI 编辑器使用）
python -m entry.mcp.server
```

## 项目结构

```
游览器agent/
├── .github/workflows/          # GitHub Actions CI 流水线
│   └── ci.yml
├── agent/                      # 代理层（CLI + MCP + 核心引擎）
│   ├── cli/                    #   CLI 命令行入口
│   │   └── main.py             #     主入口（argparse）
│   ├── core/                   #   核心引擎
│   │   ├── agent.py            #     高级浏览器代理（MCP 用）
│   │   ├── anti_detect.py      #     反检测与人类化模拟
│   │   ├── browser.py          #     双引擎浏览器控制
│   │   ├── page.py             #     页面操作封装
│   │   └── session.py          #     会话管理
│   └── mcp/                    #   MCP 协议服务器
│       └── server.py           #     统一服务入口（24 个工具）
├── modes/                      # 站点模式层
│   └── zhipin/                 #   BOSS 直聘适配器
│       ├── scraper.py          #     核心抓取引擎
│       ├── selectors.py        #     DOM 选择器集中管理
│       ├── page_analyzer.py    #     页面分析器
│       ├── pre_filter.py       #     岗位预过滤
│       ├── keyword_strategy.py #     自适应关键词策略
│       ├── city_codes.py       #     城市编码映射
│       ├── storage.py          #     SQLite 持久化
│       ├── exporter.py         #     数据导出
│       └── search_flow.py      #     搜索流程编排
├── shared/                     # 共享基础设施
│   ├── config.py               #     YAML 配置加载
│   ├── logging_config.py       #     日志配置
│   ├── retry.py                #     指数退避重试
│   ├── error_handler.py        #     异常分类与恢复
│   ├── exceptions.py           #     异常体系定义
│   ├── profiler.py             #     性能分析工具
│   └── fingerprint_manager.py  #     浏览器指纹管理
├── config/                     # 开发工具配置
│   ├── ci/                     #   CI 相关配置
│   │   └── ci.yml
│   ├── .pre-commit-config.yaml #   Pre-commit 钩子配置
│   └── mcp_config.json         #   AI 编辑器 MCP 服务连接配置
├── docs/                       # 项目文档
│   ├── refactor/               #   迭代计划与进度
│   ├── structure_reports/      #   项目结构报告
│   └── superpowers/specs/      #   设计文档
├── scripts/                    # 辅助工具脚本
│   ├── manual/                 #   手动测试脚本
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
│   ├── send_report.py          #   交付报告自动发送
│   ├── login_checker.py        #   登录状态检查
│   ├── refresh_deepseek_login.py # DeepSeek 登录刷新
│   ├── export_cookies.py       #   Cookie 导出
│   ├── browser_cleaner.py      #   浏览器清理
│   ├── download_camoufox.py    #   Camoufox 下载
│   ├── save_report_generator.py # 登录保存报告
│   ├── dev.bat                 #   Windows 开发工具集
│   ├── delivery_template.md    #   交付模板
│   └── project_structure_report.md # 项目结构报告
├── tests/                      # 测试套件
│   ├── test_core.py            #   单元测试
│   ├── test_integration.py     #   集成测试
│   ├── test_scraper_parse.py   #   解析器测试
│   ├── test_selectors.py       #   选择器测试
│   ├── test_session_check.py   #   会话检查测试
│   └── test_browser_smoke.py   #   浏览器冒烟测试
├── config.yaml                 # 用户配置（搜索/城市/过滤/运行时）
├── pyproject.toml              # 项目元数据、依赖声明、工具配置
├── requirements.txt            # 最小生产依赖
├── .gitignore                  # Git 忽略规则
└── README.md                   # 本文件
```


## 配置文件索引

| 文件 | 路径 | 说明 |
|------|------|------|
| 用户配置 | `config.yaml` | 搜索参数、城市、过滤规则、运行时参数、代理、页面分析 |
| 项目元数据 | `pyproject.toml` | 依赖声明、工具配置（ruff, mypy, pytest, coverage） |
| 依赖锁 | `requirements.txt` | 最小生产依赖 |
| Pre-commit | `config/.pre-commit-config.yaml` | 代码检查钩子（ruff → mypy → bandit） |
| CI | `.github/workflows/ci.yml` | GitHub Actions 流水线 |
| MCP 配置 | `config/mcp_config.json` | AI 编辑器 MCP 服务连接配置（Cursor/Windsurf/Trae） |

### 用户配置（config.yaml）

编辑 `config.yaml` 设置以下内容：
- **search**：搜索关键词（三级优先级）、期望学历、期望福利
- **cities**：目标城市（按优先级分四组）
- **pre_filters**：薪资下限、标题/公司黑名单、福利标签白名单
- **runtime**：BOSS 直聘 URL、每会话城市数、翻页延迟、验证码等待等
- **proxy**：代理服务器配置（默认关闭）
- **page_analysis**：自动页面分析（截图 + HTML 快照）开关与参数

## 报告发送配置

`scripts/send_report.py` 用于向 DeepSeek 监管会话自动发送交付报告，通过 Playwright 操作浏览器完成。

**浏览器数据目录**：`browser_profile/playwright_send/`（已在 `.gitignore` 中）

- 该目录与主项目的 `browser_profile/persistent/` 共用同一套浏览器配置，**一次登录，全工具可用**
- 登录态自动保存至 `sessions/storage_state.json`，每次启动时自动加载

**使用方式**：

```bash
# 发送报告（自动发送，无需确认）
python scripts/send_report.py <报告文件路径>

# 手动确认模式
python scripts/send_report.py <报告文件路径> --confirm

# 指定会话 URL（覆盖默认）
python scripts/send_report.py <报告文件路径> --url <DeepSeek会话链接>
```

首次运行如检测到未登录，会自动打开浏览器窗口，按终端提示手动登录即可。登录态保存后可跨会话复用。

## MCP 连接说明

本项目的 MCP 服务器通过 `mcp_config.json` 向 AI 编辑器暴露浏览器自动化和 BOSS 搜索能力（共 24 个工具）。

**支持的编辑器**：Cursor、Windsurf、Trae

**配置方式**：将 `mcp_config.json` 的内容复制到编辑器的 MCP 配置文件中：

- **Cursor**：`Cursor Settings` → `MCP Servers` → 添加新服务器，填入配置
- **Windsurf**：`~/.codeium/windsurf/mcp_config.json`
- **Trae**：编辑器设置 → MCP 配置

配置内容示例（`mcp_config.json`）：

```json
{
  "mcpServers": {
    "boss-job-hunter": {
      "command": "python",
      "args": ["-u", "entry/mcp/server.py"],
      "env": { "PYTHONIOENCODING": "utf-8" },
      "cwd": "d:\\G\\github\\游览器agent"
    }
  }
}
```

配置完成后重启编辑器，即可在 AI 对话中使用搜索岗位、浏览器控制等工具。

## 测试

```bash
pytest tests/
```
