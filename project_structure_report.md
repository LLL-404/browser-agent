# 项目结构现状报告

**项目名称**：boss-job-hunter  
**版本**：2.0.0  
**报告生成时间**：2026-06-01  
**报告人**：项目经理  

---

## S1：项目完整目录树

```
D:\G\github\游览器agent\
│
├── .github/workflows/ci.yml          # GitHub Actions CI/CD 流水线
├── .pre-commit-config.yaml           # Pre-commit 钩子配置
├── .gitignore                        # Git 忽略规则
├── pyproject.toml                    # 项目元数据与依赖清单
├── config.yaml                       # 用户可编辑配置
├── requirements.txt                  # 最小生产依赖
├── send_report.py                    # 交付报告发送工具（DeepSeek）
├── export_cookies.py                 # Cookie 导出脚本
├── project_structure_report.md       # 本报告文件
│
├── core/                             # 核心业务逻辑库
│   ├── agent.py                      #   高级浏览器代理（MCP 用）
│   ├── anti_detect.py                #   反检测与人类化脚本
│   ├── browser_controller.py         #   双引擎浏览器控制（Camoufox + Playwright）
│   ├── city_codes.py                 #   BOSS 直聘城市编码
│   ├── config.py                     #   YAML 配置加载器
│   ├── cookie_manager.py             #   Cookie 持久化
│   ├── error_handler.py              #   错误分类与 MCP 格式化
│   ├── exceptions.py                 #   自定义异常体系
│   ├── exporter.py                   #   数据导出（Markdown/JSON）
│   ├── fingerprint_manager.py        #   浏览器指纹生成
│   ├── keyword_strategy.py           #   自适应关键词策略
│   ├── logging_config.py             #   日志配置
│   ├── page_analyzer.py              #   截图+HTML分析
│   ├── pre_filter.py                 #   岗位预过滤
│   ├── profiler.py                   #   性能分析
│   ├── retry.py                      #   指数退避重试
│   ├── scraper.py                    #   核心抓取引擎
│   ├── selectors.py                  #   集中式 DOM 选择器
│   └── storage.py                    #   SQLite 数据库层
│
├── cli/                              # CLI 入口层
│   ├── main.py                       #   主 CLI 入口（argparse）
│   ├── run_search.py                 #   交互式 BOSS 搜索
│   ├── search_all.py                 #   全国校招搜索
│   ├── nationwide.py                 #   全国化学/安全岗位搜索
│   ├── analyze.py                    #   结果分析
│   ├── quick_search.py               #   快速搜索
│   ├── open_boss.py                  #   打开 BOSS 浏览器
│   ├── view_company.py               #   查看公司详情
│   ├── check_camoufox.py             #   检查 Camoufox 可用性
│   └── test_camoufox.py             #   测试 Camoufox 启动
│
├── mcp_server/                       # MCP 协议服务器
│   └── server.py                     #   统一服务器入口（24 个工具）
│
├── sites/                            # 站点插件层
│   └── zhipin/                       #   BOSS 直聘插件
│       └── __init__.py              #   门面模式，重导出 core
│
├── scripts/                          # 工具脚本
│   ├── browser_cleaner.py            #   清理浏览器配置
│   ├── download_camoufox.py          #   下载 Camoufox 浏览器
│   ├── login_checker.py             #   检查登录状态
│   └── save_report_generator.py     #   生成登录保存报告
│
├── tests/                            # 测试套件
│   ├── test_core.py                  #   单元测试（21 个）
│   ├── test_integration.py           #   集成测试（4 个）
│   ├── smoke_test.py                 #   冒烟测试
│   ├── simple_search.py              #   简单搜索测试
│   ├── quick_snap.py                 #   快照测试
│   ├── login_and_save.py            #   登录保存测试
│   ├── verify_login.py              #   登录验证
│   ├── verify_system.py             #   系统验证
│   ├── view_jobs.py                  #   查看岗位测试
│   ├── test_camoufox.py             #   Camoufox 测试
│   ├── test_controller.py            #   控制器测试
│   └── debug/                        #   调试输出目录
│
├── freelance_tools/                  # 兼职工具包（独立子项目）
│   ├── crawler_template.py           #   爬虫模板
│   ├── data_processor.py             #   数据/Excel 处理模板
│   ├── getting_started_guide.md      #   兼职入门指南
│   ├── service_copywriting.md        #   文案模板
│   └── README.md                     #   兼职工具包说明
│
├── data/                             # 运行时数据（已 gitignore）
│   ├── jobs.db                       #   SQLite 数据库
│   ├── logs/                         #   日志文件
│   ├── export/                       #   导出数据
│   ├── screenshots/                  #   截图
│   ├── snapshots/                    #   HTML 快照
│   └── reports/                      #   生成的报告
│
├── docs/                             # 文档（已 gitignore）
│   ├── refactor/iteration_plan.md    #   迭代计划与进度
│   └── superpowers/specs/2026-05-02-boss-job-hunter-design.md  # 设计文档
│
├── sessions/                         # 会话持久化（已 gitignore）
│   └── profiles/                     #   会话配置文件（3 个会话记录）
│
└── browser_profile/                  # 浏览器配置数据（已 gitignore）
    ├── Default/                      #   Chromium 默认配置
    ├── camoufox/                     #   Camoufox 浏览器配置
    └── camoufox_profile/            #   Camoufox 配置副本
```

---

## S2：核心模块边界与状态

| 模块 | 路径 | 功能边界 | 当前状态 | 主要负责人 | 备注 |
|------|------|---------|---------|-----------|------|
| **core** | core/ | 核心业务逻辑，含浏览器控制、抓取引擎、存储、反检测、重试等19个文件 | ✅ 已完成 | 项目经理 | 结构清晰，各项职责分明 |
| **cli** | cli/ | CLI 命令行入口，10个脚本覆盖搜索、分析、查看等场景 | ✅ 已完成 | 项目经理 | |
| **mcp_server** | mcp_server/ | MCP 协议服务器，暴露24个工具（9个BOSS + 13个浏览器 + 2个性能） | ✅ 已完成 | 项目经理 | 统一入口 server.py |
| **sites** | sites/ | 站点插件层，意图支持多站点，实际仅实现 BOSS 直聘 | 🟡 待扩展 | 项目经理 | 目录结构预留多站点，但仅 zhipin/ 有内容 |
| **scripts** | scripts/ | 工具脚本，清理、下载、检查等辅助功能 | ✅ 已完成 | 项目经理 | 4个独立脚本 |
| **tests** | tests/ | 测试套件，25个测试覆盖核心模块 | 🟡 部分覆盖 | 项目经理 | 浏览器交互和 MCP 服务无测试 |
| **freelance_tools** | freelance_tools/ | 兼职接单工具包，与项目核心无关 | ✅ 已完成 | 项目经理 | 独立的子项目嵌入在仓库中 |
| **send_report.py** | 根目录 | DeepSeek 报告发送工具 | ✅ 已完成 | 项目经理 | 需注意存在跨项目路径依赖 |

---

## S3：关键依赖与接口

### 外部依赖

| 名称 | 版本要求 | 用途 | 是否必需 |
|------|---------|------|---------|
| playwright | >=1.40.0 | 浏览器自动化引擎 | ✅ 必需 |
| camoufox | >=0.3.0 | C++反检测浏览器（可选回退） | ❌ 可选（缺失时用 Playwright） |
| mcp (Python SDK) | >=1.0.0 | Model Context Protocol 框架 | ✅ 必需 |
| PyYAML | >=6.0 | YAML 配置解析 | ✅ 必需 |
| aiofiles | >=23.0 | 异步文件 I/O | ✅ 必需 |
| httpx | >=0.27.0 | 异步 HTTP 客户端 | ✅ 必需 |
| pytest | >=8.0 | 测试框架 | ❌ 仅开发 |
| ruff | >=0.4.0 | Python 代码检查/格式化 | ❌ 仅开发 |
| mypy | >=1.10 | 静态类型检查 | ❌ 仅开发 |
| pre-commit | >=3.7 | Pre-commit 钩子 | ❌ 仅开发 |

### 对外提供的接口（MCP Tools）

| 工具名称 | 协议 | 鉴权 | 说明 |
|---------|------|------|------|
| search_jobs | MCP (stdio) | 无 | BOSS 岗位搜索 |
| list_jobs | MCP (stdio) | 无 | 轻量岗位列表 |
| get_job_detail | MCP (stdio) | 无 | 岗位详情 |
| analyze_jobs | MCP (stdio) | 无 | 分析结果推送 |
| boss_get_stats | MCP (stdio) | 无 | 统计概览 |
| update_status | MCP (stdio) | 无 | 更新岗位状态 |
| boss_generate_report | MCP (stdio) | 无 | 生成推荐报告 |
| generate_chat_prompt | MCP (stdio) | 无 | 生成打招呼文案 |
| filter_jobs | MCP (stdio) | 无 | 全国结果过滤 |
| browser_* (13个) | MCP (stdio) | 无 | 浏览器自动化操作 |

### 调用的外部接口

| 地址 | 协议 | 用途 | 对接状态 | 说明 |
|------|------|------|---------|------|
| https://www.zhipin.com/ | HTTPS | BOSS 直聘岗位搜索 | ✅ 已完成 | 核心业务依赖 |
| https://chat.deepseek.com/a/chat/s/... | Playwright | 报告发送至监管会话 | ✅ 已完成 | send_report.py 使用 |
| https://github.com/daijro/camoufox/releases/ | HTTPS | 下载 Camoufox 浏览器 | ✅ 已完成 | 可选依赖 |

---

## S4：技术栈与环境配置

| 类别 | 技术 | 版本 | 备注 |
|------|------|------|------|
| 语言 | Python | >=3.11 | 当前使用 Python 3.14 编译 |
| 浏览器自动化 | Playwright | >=1.40.0（已安装 1.59.0） | 主引擎 |
| 反检测浏览器 | Camoufox | >=0.3.0（已安装 0.4.11） | 可选，自动回退 |
| MCP 框架 | mcp (Python SDK) | >=1.0.0（已安装 1.27.0） | |
| 配置解析 | PyYAML | >=6.0（已安装 6.0.3） | |
| 异步 I/O | aiofiles | >=23.0 | |
| HTTP 客户端 | httpx | >=0.27.0 | |
| 数据库 | SQLite | stdlib | WAL 模式 |
| 代码检查 | Ruff | >=0.4.0 | 开发依赖 |
| 类型检查 | MyPy | >=1.10 | 开发依赖 |
| 测试 | pytest | >=8.0 | 开发依赖 |
| CI | GitHub Actions | - | Windows-latest + Ubuntu-latest |

**环境差异**：
- **本地开发**：Windows 10/11，Python 3.11+，直接运行
- **CI**：Windows-latest + Ubuntu-latest 双平台，自动安装 Chromium + Firefox
- **线上**：当前无线上部署（项目为本地 CLI 工具 + MCP 本地服务）
- **Docker**：无容器化方案

**环境变量**：

| 变量名 | 用途 | 默认值 |
|--------|------|--------|
| SEND_REPORT_URL | 覆盖 DeepSeek 会话 URL | 无 |

---

## S5：已知问题与风险

| # | 问题描述 | 严重程度 | 影响范围 | 应对方案 |
|---|---------|---------|---------|---------|
| 1 | **项目未初始化 Git 仓库**。无版本控制、无提交历史、无法协作。 | 🔴 致命 | 全体开发 | 待确认。.gitignore 和 .pre-commit-config.yaml 均已存在但无效。建议立即 git init。 |
| 2 | **send_report.py 存在跨项目路径依赖**。BROWSER_DATA_DIR 硬编码指向 D:/G/novel/短故事/agent/.browser-data | 🟡 一般 | 报告发送功能 | 应改为相对路径或可配置项 |
| 3 | **send_report.py 引用了不存在的 llm_config.py**。虽然 fallback 了默认 URL，但导入异常可能影响后续扩展 | 🟡 一般 | 报告发送功能 | 待确认是否需要创建该文件 |
| 4 | **浏览器交互代码零测试覆盖**。25个测试仅覆盖 pre_filter、storage、keyword_strategy、city_codes、retry | 🟡 一般 | 浏览器相关功能 | 待规划 Playwright 集成测试 |
| 5 | **BOSS 直聘 DOM 变动风险**。选择器集中在 selectors.py，站点改版将直接导致抓取失效 | 🟡 一般 | 全部抓取功能 | 需建立选择器变更告警机制 |
| 6 | **docs/ 目录被 gitignore**。设计文档和迭代计划不会进入版本控制 | 🟢 改进 | 文档管理 | 建议取消 gitignore |
| 7 | **freelance_tools/ 嵌入主仓库**。独立无关的子项目增加了仓库噪声 | 🟢 改进 | 代码维护 | 建议迁出为独立仓库 |
| 8 | **重试次数硬编码**。core/retry.py 中 MAX_RETRIES=3 不可配置 | 🟢 改进 | 重试逻辑 | 建议改为可配置参数 |
| 9 | **无 README.md**。新人无法快速了解项目概览 | 🟢 改进 | 新人上手 | 待补充 |
| 10 | **无 Docker 化**。无法在隔离环境运行 | 🟢 改进 | 部署灵活性 | 当前本地工具，低优先级 |

---

## S6：代码仓库与文档索引

### 仓库信息

| 项目 | 状态 |
|------|------|
| Git 仓库 | ❌ **未初始化** |
| 远程地址 | 无 |
| 分支 | 无 |
| 分支保护规则 | 无 |
| .gitignore | ✅ 已存在 |
| .pre-commit-config.yaml | ✅ 已存在（但无法生效） |
| GitHub Actions | ✅ 配置已就绪（但从未运行） |

### 文档索引

| 文档名称 | 路径 | 类型 | 状态 | 说明 |
|---------|------|------|------|------|
| 系统设计文档 | docs/superpowers/specs/2026-05-02-boss-job-hunter-design.md | 设计文档 | ✅ 有效 | 完整系统架构、MCP 工具规格、数据库 Schema |
| 迭代计划 | docs/refactor/iteration_plan.md | 计划文档 | ✅ 有效 | 迭代1-3完成进度，2026-05-07 完成 |
| 项目规则 | .trae/rules/project_rules.md | IDE 规则 | ✅ 有效 | 岗位筛选标准 |
| 兼职工具包说明 | freelance_tools/README.md | 说明文档 | ✅ 有效 | 独立子项目文档 |
| 兼职入门指南 | freelance_tools/getting_started_guide.md | 指南 | ✅ 有效 | |
| 文案模板 | freelance_tools/service_copywriting.md | 模板 | ✅ 有效 | |
| CI 配置 | .github/workflows/ci.yml | 配置 | ✅ 有效 | lint→test→security→build |
| Pre-commit 配置 | .pre-commit-config.yaml | 配置 | ✅ 有效 | ruff→mypy→bandit |
| Pyproject 配置 | pyproject.toml | 配置 | ✅ 有效 | 全部工具配置集中管理 |
| 用户配置 | config.yaml | 配置 | ✅ 有效 | 含中文注释的用户配置 |

**缺失文档**：
- 根目录 README.md：❌ 无
- API 参考文档：❌ 无
- 安装/部署指南：❌ 无
- LICENSE 文件：❌ 无（pyproject.toml 声明 MIT 但无文件）
- 变更日志：❌ 无

---

## 汇总说明

本报告为项目截至 2026-06-01 的真实快照。重点风险项：

1. **项目无 Git 版本控制** — 这是最严重的问题，建议优先处理
2. **浏览器交互代码无测试覆盖** — 下一阶段应补充 Playwright 集成测试
3. **send_report.py 存在路径和依赖隐患** — 需修复跨项目硬编码路径
4. **文档散落且部分被 gitignore** — 建议统一文档管理策略

以上内容均为实地探查所得，未做任何虚报或补写。
