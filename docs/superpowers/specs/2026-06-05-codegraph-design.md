# CodeGraph 技术设计文档

**版本**：1.0  
**日期**：2026-06-05  
**状态**：草稿

---

## 1. 概述

### 1.1 项目背景

参考 GitHub 25k stars 的 [colbymchenry/codegraph](https://github.com/colbymchenry/codegraph)，在 `游览器agent` 项目中实现一个轻量级的代码图谱服务。主要面向 AI Agent（MCP 协议），支持中英双语搜索和增量更新。

### 1.2 核心目标

- 为 AI Agent 提供预索引的代码结构知识图谱
- 支持中英双语搜索和命名
- 实现增量文件监视，自动更新索引
- 减少 AI Agent 的工具调用次数（目标：减少 60%+）

### 1.3 设计原则

- **轻量优先**：纯 Python 实现，依赖最小化
- **增量更新**：文件监视 + 防抖机制
- **AI 友好**：结构化 JSON + MCP 协议双轨输出
- **双语支持**：英文原名 + 中文别名

---

## 2. 技术架构

### 2.1 模块结构

```
src/codegraph/
├── __init__.py
├── parser/                 # AST 解析层
│   ├── __init__.py
│   ├── python_parser.py   # Python AST 解析器
│   └── visitor.py         # AST Visitor（收集节点）
├── storage/               # 存储层
│   ├── __init__.py
│   ├── indexer.py         # 索引构建器
│   └── db.py             # SQLite FTS5 持久化
├── analysis/             # 分析层
│   ├── __init__.py
│   ├── call_graph.py     # 调用图构建
│   └── dependencies.py   # 依赖分析
├── api/                  # MCP API 层
│   ├── __init__.py
│   ├── search.py         # 搜索接口
│   ├── context.py        # 上下文接口
│   └── navigation.py     # 导航接口
├── watcher/              # 文件监视层
│   ├── __init__.py
│   └── file_watcher.py   # Windows ReadDirectoryChangesW
├── models.py             # 数据模型（节点、边）
├── config.py             # 配置管理
└── cli.py                # 命令行入口
```

### 2.2 数据模型

#### 节点（Node）

```python
class CodeNode:
    id: str              # 唯一标识 "file:line" 或 "file:class:method"
    name: str            # 英文名称
    name_zh: str         # 中文别名（如 "查找用户"）
    type: str            # 'function' | 'class' | 'module' | 'import' | 'decorator'
    file: str            # 文件路径（相对路径）
    line: int            # 行号
    end_line: int       # 结束行号
    docstring: str       # 文档字符串
    signature: str       # 函数签名
    children: list[str]  # 子节点 IDs
    decorators: list[str]  # 装饰器列表
```

#### 边（Edge）

```python
class CodeEdge:
    source: str          # 源节点 ID
    target: str          # 目标节点 ID
    type: str            # 'calls' | 'imports' | 'inherits' | 'uses' | 'decorates'
```

### 2.3 MCP 工具定义

| 工具名 | 参数 | 返回 | 说明 |
|--------|------|------|------|
| `codegraph_search` | query: str, lang?: str | list[Node] | 中英双语搜索符号 |
| `codegraph_context` | node_id: str, depth?: int | ContextBundle | 完整上下文包 |
| `codegraph_callers` | node_id: str | list[Edge] | 查找调用者 |
| `codegraph_callees` | node_id: str | list[Edge] | 查找被调用者 |
| `codegraph_impact` | node_id: str | ImpactResult | 影响范围分析 |
| `codegraph_node` | node_id: str | Node | 单个符号详情 |
| `codegraph_files` | path?: str | list[str] | 文件结构树 |
| `codegraph_status` | - | StatusResult | 索引健康状态 |

### 2.4 ContextBundle 结构（核心）

```json
{
  "node": { /* CodeNode */ },
  "callers": [ /* 上一层调用链 */ ],
  "callees": [ /* 下一层被调用 */ ],
  "code_snippet": "def find_user(id): ...",
  "related": [ /* 相关符号（同文件/同名） */ ],
  "hints": "可追问: this.method 的参数格式"
}
```

---

## 3. 核心功能

### 3.1 Python AST 解析

- 使用 Python 内置 `ast` 模块
- 支持：函数、类、方法、导入、装饰器
- 自动生成中文别名（简单翻译规则）
- 容错处理：语法错误的文件也提取部分结构

### 3.2 增量更新机制

**文件监视**：
- Windows: `ReadDirectoryChangesW` API
- 防抖时间：2秒（可配置）
- 监控事件：CREATE / MODIFY / DELETE / RENAME

**更新策略**：
- 单文件变更：只重索引该文件
- 删除文件：移除相关节点和边
- 新增文件：解析并插入
- 跨文件 import：重新解析受影响文件

### 3.3 中英双语搜索

**索引阶段**：
- 英文名称直接索引
- 中文别名作为附加字段

**搜索阶段**：
- 用户输入中文 → 翻译为英文关键词 → FTS5 搜索
- 用户输入英文 → 直接 FTS5 搜索
- 结果合并去重

### 3.4 中文别名生成规则

```python
# 简单翻译规则（可扩展）
TRANSLATIONS = {
    'get': '获取',
    'set': '设置',
    'find': '查找',
    'search': '搜索',
    'create': '创建',
    'delete': '删除',
    'update': '更新',
    'list': '列表',
    'add': '添加',
    'remove': '移除',
    'load': '加载',
    'save': '保存',
    'init': '初始化',
    'start': '启动',
    'stop': '停止',
    'open': '打开',
    'close': '关闭',
    'connect': '连接',
    'disconnect': '断开',
    'parse': '解析',
    'build': '构建',
    'run': '运行',
    'execute': '执行',
    'handle': '处理',
    'process': '处理',
    'validate': '验证',
    'check': '检查',
    'verify': '验证',
    'format': '格式化',
}

def translate(name: str) -> str:
    """将英文驼峰转为中文"""
    # 1. 下划线分割
    # 2. 每个词翻译
    # 3. 拼接
```

---

## 4. 存储设计

### 4.1 SQLite Schema

```sql
-- 节点表
CREATE TABLE nodes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_zh TEXT,
    type TEXT NOT NULL,
    file TEXT NOT NULL,
    line INTEGER NOT NULL,
    end_line INTEGER,
    docstring TEXT,
    signature TEXT,
    decorators TEXT,  -- JSON 数组
    children TEXT     -- JSON 数组
);

-- 边表
CREATE TABLE edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    type TEXT NOT NULL,
    FOREIGN KEY (source) REFERENCES nodes(id),
    FOREIGN KEY (target) REFERENCES nodes(id)
);

-- FTS5 全文索引
CREATE VIRTUAL TABLE nodes_fts USING fts5(
    name, name_zh, docstring,
    content='nodes',
    content_rowid='rowid'
);

-- 文件索引（快速查找）
CREATE TABLE files (
    path TEXT PRIMARY KEY,
    mtime REAL,
    hash TEXT
);
```

### 4.2 索引文件位置

```
.codegraph/
├── index.db          # SQLite 数据库
├── config.json       # 排除规则等配置
└── watcher.lock      # 文件锁
```

---

## 5. 配置

### 5.1 排除规则（.codegraphignore）

```
# 模式同 .gitignore
__pycache__/
*.pyc
.pytest_cache/
.venv/
venv/
node_modules/
.git/
.browser_profile*/
docs/
*.md
```

### 5.2 配置文件

```json
{
  "exclude_patterns": [
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    ".venv",
    "venv",
    "node_modules",
    ".git"
  ],
  "include_extensions": [".py"],
  "watch_debounce_ms": 2000,
  "max_file_size_kb": 5120
}
```

---

## 6. CLI 命令

```bash
# 初始化索引
codegraph init

# 全量索引
codegraph index

# 增量监听（后台）
codegraph watch

# 搜索
codegraph search "用户"

# 查看符号上下文
codegraph context src/agent/core/browser.py:BrowserController

# 查看状态
codegraph status

# 清理索引
codegraph clean
```

---

## 7. MCP 服务

### 7.1 启动方式

```bash
# 作为 MCP 服务器启动
codegraph serve --mcp

# 同时启动 Web 可视化（可选）
codegraph serve --mcp --web
```

### 7.2 MCP 协议集成

参考 [codegraph MCP server](https://github.com/colbymchenry/codegraph) 的 8 个工具设计，实现精简版：

```python
# MCP 工具定义示例
TOOLS = [
    {
        "name": "codegraph_search",
        "description": "搜索代码符号（中英双语）",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "limit": {"type": "integer", "default": 20}
            }
        }
    },
    # ... 其他工具
]
```

---

## 8. 性能目标

| 指标 | 目标 |
|------|------|
| 全量索引（1000 文件） | < 30 秒 |
| 单文件增量更新 | < 500ms |
| 搜索响应时间 | < 100ms |
| 内存占用 | < 200MB（10000 文件） |

---

## 9. 依赖

```python
# 核心依赖（最小化）
- Python >= 3.7（内置 ast 模块）
- sqlite3（Python 内置）

# 可选依赖
- watchfiles  # 文件监视（跨平台）
- fastapi     # Web 可视化（可选）
- pyvis       # 图形可视化（可选）
```

---

## 10. 实现计划

### Phase 1：核心解析（约 2 天）
- [ ] 数据模型定义
- [ ] Python AST 解析器
- [ ] 节点/边提取逻辑

### Phase 2：存储层（约 1 天）
- [ ] SQLite 数据库初始化
- [ ] FTS5 全文索引
- [ ] 索引构建器

### Phase 3：MCP API（约 2 天）
- [ ] MCP 服务器框架
- [ ] 8 个工具实现
- [ ] 中英双语搜索

### Phase 4：增量更新（约 1 天）
- [ ] 文件监视器
- [ ] 防抖机制
- [ ] 增量重索引

### Phase 5：CLI 和测试（约 1 天）
- [ ] 命令行接口
- [ ] 单元测试
- [ ] 集成测试

---

## 11. 参考资料

- [colbymchenry/codegraph](https://github.com/colbymchenry/codegraph) - 25k stars MCP 代码图谱
- [Python ast 模块文档](https://docs.python.org/3/library/ast.html)
- [SQLite FTS5](https://www.sqlite.org/fts5.html)
