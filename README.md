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
python -m cli.main search

# 5. 或启动 MCP 服务器（供 AI 编辑器使用）
python -m mcp_server.server
```

## 项目结构

| 目录 | 说明 |
|------|------|
| core/ | 核心逻辑：浏览器控制、抓取引擎、存储、反检测 |
| cli/ | 命令行入口，支持搜索、分析、查看等操作 |
| mcp_server/ | MCP 协议服务器，暴露 24 个工具 |
| sites/ | 站点插件层（当前仅 BOSS 直聘） |
| scripts/ | 辅助脚本 |
| tests/ | 测试套件 |
| freelance_tools/ | 兼职接单工具包（独立子项目） |

## 配置

编辑 `config.yaml` 设置搜索参数、城市过滤、代理等。

## 测试

```bash
pytest tests/
```
