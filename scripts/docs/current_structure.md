# 当前项目结构（2026-06-01 最新）

执行 R6–R10（三层架构分层）+ R11–R13（根目录精简）后，当前结构如下：

## 根目录文件

```
.pre-commit-config.yaml   # Pre-commit 钩子
config.yaml               # 用户配置
mcp_config.json           # MCP 连接配置
pyproject.toml            # 项目元数据
requirements.txt          # 依赖
README.md                 # 文档
.gitignore                # Git 忽略规则
```

## 目录结构

```
boss-job-hunter/
├── entry/                # 入口层
│   ├── cli/              #   CLI 命令行
│   │   ├── main.py       #     10 个子命令
│   │   ├── run_search.py #     交互式 BOSS 搜索
│   │   └── ...
│   └── mcp_server/       #   MCP 服务器
│       └── server.py     #     24 个工具
│
├── core/                 # 业务逻辑
│   ├── engine/           #   抓取引擎
│   ├── pipeline/         #   数据管线
│   ├── infra/            #   基础设施
│   └── adapters/zhipin/  #   BOSS 适配器
│
├── scripts/              # 辅助工具
│   ├── tests/            #   测试套件
│   ├── docs/             #   设计文档
│   ├── manual/           #   手动测试脚本
│   ├── send_report.py    #   报告发送
│   ├── login_checker.py  #   登录检查
│   └── ...
│
└── sessions/             # 运行时数据（storage_state.json）
```

## 关键指标

- 根目录一级文件夹：**3 个**（entry/、core/、scripts/）
- 单元测试：**25/25 通过**（`pytest scripts/tests/`）
- CLI 入口：`python -m entry.cli.main`
- MCP 入口：`python -m entry.mcp_server.server`
- 登录态：Cookie + localStorage 双恢复，跨工具共享

---

*由 `scripts/send_report.py` 自动发送。*
