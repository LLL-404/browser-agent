# browser-agent

浏览器自动化 AI Agent 框架 — 提供统一的 **CLI 命令行**、**MCP 协议服务器** 和 **多模式扩展** 能力，支持通过 AI 编辑器或终端控制浏览器完成自动化任务。

## 核心能力

- **浏览器自动化引擎** — 基于 Playwright + Camoufox 双引擎，支持反检测与人类化模拟
- **MCP 协议服务器** — 通过 Model Context Protocol 向 AI 编辑器暴露 20+ 浏览器工具
- **CLI 接口** — 命令行浏览器控制、登录态管理、任务编排
- **多模式扩展** — `modes/` 目录下的业务模式即插即用，每个模式独立注册 MCP 工具和 CLI 命令
- **跨平台会话管理** — Cookie + StorageState 持久化，重启复用登录态
- **页面分析能力** — 任意页面截图、DOM 提取、内容分析

## 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 安装浏览器
playwright install chromium

# 3. 运行 CLI（交互模式）
python -m agent.cli.main browse

# 4. 或启动 MCP 服务器（供 AI 编辑器连接）
python -m agent.mcp.server
```

## 项目结构

```
游览器agent/
├── agent/                    # 核心框架层
│   ├── cli/main.py           #   CLI 入口（argparse，--mode 加载业务模式）
│   ├── core/                 #   浏览器引擎
│   │   ├── browser.py        #     双引擎控制（Camoufox → Playwright 自动回退）
│   │   ├── agent.py          #     高级 Agent 封装（open/close/navigate/click/…）
│   │   ├── session.py        #     会话持久化（Cookie + StorageState）
│   │   ├── anti_detect.py    #     反检测与人类化模拟脚本
│   │   ├── page.py           #     页面操作封装
│   │   ├── capabilities.py   #     能力管理
│   │   └── mcp_config.py     #     MCP 配置加载
│   └── mcp/                  #   MCP 协议层
│       ├── server.py         #     服务器生命周期（stdio/SSE）
│       ├── definitions.py    #     工具定义与 schema
│       ├── handlers.py       #     工具处理函数
│       └── validation.py     #     参数校验
├── modes/                    # 业务模式层（即插即用）
│   ├── __init__.py           #   模式注册规范
│   └── zhipin/               #   BOSS 直聘适配器（示例模式）
│       ├── scraper.py        #     抓取引擎
│       ├── selectors.py      #     DOM 选择器
│       ├── storage.py        #     SQLite 持久化
│       └── ...
├── shared/                   # 共享基础设施
│   ├── config.py             #   YAML 配置加载
│   ├── logging_config.py     #   日志配置
│   ├── retry.py              #   指数退避重试
│   ├── error_handler.py      #   异常分类与恢复
│   ├── exceptions.py         #   异常体系
│   ├── profiler.py           #   性能分析
│   └── fingerprint_manager.py#   浏览器指纹管理
├── config/                   # 开发工具与编辑器配置
├── docs/                     # 项目文档
├── scripts/                  # 辅助工具脚本
└── config.yaml               # 用户配置文件
```

## 用法

### CLI 命令

```bash
# 启动浏览器（交互浏览）
python -m agent.cli.main browse

# 登录指定网站并保存会话
python -m agent.cli.main login --url https://example.com

# 加载业务模式
python -m agent.cli.main --mode zhipin run
```

### MCP 服务器

MCP 服务器通过 stdio 或 SSE 协议向 AI 编辑器暴露工具：

```bash
# stdio 模式（默认，供编辑器集成）
python -m agent.mcp.server

# SSE 模式（远程连接）
python -m agent.mcp.server --port 8080
```

支持的工具类别：浏览器控制、页面分析、会话管理、模式业务工具（按加载的模式动态注册）。

### AI 编辑器集成

在编辑器的 MCP 配置中添加：

```json
{
  "mcpServers": {
    "browser-agent": {
      "command": "python",
      "args": ["-m", "agent.mcp.server"],
      "cwd": "D:\\G\\github\\游览器agent"
    }
  }
}
```

## 配置

编辑 `config.yaml` 设置运行时参数。模式特有配置在各模式的文档中说明。

## 开发

```bash
# 代码检查
.\scripts\dev\dev.bat lint

# 运行测试
.\scripts\dev\dev.bat test

# 类型检查
.\scripts\dev\dev.bat typecheck
```

## 内置模式

| 模式 | 路径 | 说明 |
|------|------|------|
| 空模式 | — | 纯浏览器控制能力，无业务绑定 |
| BOSS 直聘 | `modes/zhipin/` | BOSS直聘岗位搜索与分析（示例模式） |

## 许可证

MIT
