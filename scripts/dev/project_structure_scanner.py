"""
project_structure_scanner.py — 项目结构自动扫描与报告生成工具

功能：
  P1: 生成目录树，附带目录职责说明
  P2: 核心模块边界识别与状态推断（自动识别新架构三层结构）
  P3: 外部依赖、环境变量、MCP 接口列表（含通用工具 + 各模式工具）
  P4: 技术栈识别
  P5: 已知问题（TODO/FIXME/HACK/XXX）汇总
  P6: 文档与配置文件索引
  P7: 新架构适配 — 支持 agent/modes/shared 模块识别，MCP 工具多来源检测

用法：
  python scripts/project_structure_scanner.py                    # 保存到 docs/structure_reports/
  python scripts/project_structure_scanner.py --dry-run          # 仅终端输出，不保存
  python scripts/project_structure_scanner.py --output custom.md # 指定输出路径

输出格式：Markdown，模板为 S1-S6 结构化报告。
保留策略：最近 10 份报告保留，更早的自动归档至 archive/。
"""

import os
import re
import sys
import ast
import argparse
import datetime
import shutil
import textwrap
import tomllib
from pathlib import Path
from collections import OrderedDict

# ── 项目根路径 ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── 排除规则（基于 .gitignore + 默认排除） ─────────────────
DEFAULT_EXCLUDE_DIRS = {
    ".git", ".venv", "__pycache__", ".pytest_cache",
    ".vscode", ".idea", ".trae", ".browser-data",
    "browser_profile", "node_modules", ".mypy_cache",
    ".ruff_cache", "htmlcov", ".github",
    "data", "sessions",
}
DEFAULT_EXCLUDE_FILES = {
    "*.pyc", "*.pyo", "*.log", "*.tmp", "*.png", "*.html",
}
DEFAULT_EXCLUDE_PREFIXES = {"."}  # hidden files/dirs


def parse_gitignore(root: Path) -> tuple[set, set, set]:
    """Parse .gitignore and return (dir_patterns, file_patterns, prefix_patterns)."""
    dir_patterns = set()
    file_patterns = set()
    prefix_patterns = set()
    gitignore_path = root / ".gitignore"
    if not gitignore_path.exists():
        return dir_patterns, file_patterns, prefix_patterns
    for line in gitignore_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("/"):
            dir_patterns.add(line.rstrip("/"))
        elif line.startswith("*."):
            file_patterns.add(line)
        elif line.startswith("."):
            prefix_patterns.add(line)
        else:
            dir_patterns.add(line)
    return dir_patterns, file_patterns, prefix_patterns


def is_excluded(name: str, is_dir: bool, dir_pat: set, file_pat: set, prefix_pat: set) -> bool:
    """Check if a file/dir should be excluded from scanning."""
    if name in DEFAULT_EXCLUDE_DIRS:
        return True
    if name in DEFAULT_EXCLUDE_FILES:
        return True
    if name in dir_pat and is_dir:
        return True
    if f"*.{name.split('.')[-1]}" in file_pat and not is_dir:
        return True
    if any(name.startswith(p) for p in prefix_pat):
        if is_dir and name.startswith("."):
            return True
        if not is_dir and name.startswith("."):
            return True
    return False


# ── 描述提取 ──────────────────────────────────────────────
DIR_DESCRIPTIONS = {
    "agent": "通用浏览器 Agent 层，独立于任何业务，提供完整的浏览器自动化能力",
    "agent/core": "浏览器引擎核心：Camoufox/Playwright 双引擎控制器、反检测、会话管理、页面分析",
    "agent/mcp": "MCP 协议服务器，通过 Model Context Protocol 暴露通用浏览器自动化能力（13 个工具）",
    "agent/cli": "通用 CLI 入口，--mode 参数分派，支持 browse 子命令",
    "modes": "业务插件注册目录，每个子包提供 get_mcp_tools() / register_cli() / run_cli() 接口",
    "modes/zhipin": "BOSS 直聘业务插件，独立注册 10 个 MCP 工具和 8 个 CLI 子命令",
    "shared": "共享基础设施层，提供配置加载、日志、重试、异常体系、性能分析、指纹生成等底层能力",
    "scripts": "辅助工具脚本，含报告发送、结构扫描、登录检查、Cookie 导出等",
    "scripts/manual": "手动测试脚本，用于调试和验证特定功能",
    "tests": "自动化测试套件，含单元测试和集成测试",
    "docs": "项目文档，含迭代计划、设计文档、算法复杂度说明",
    "config": "开发工具与 CI 配置，含 Pre-commit 钩子和 MCP 连接配置",
}


def get_dir_description(rel_path: str) -> str:
    if rel_path in DIR_DESCRIPTIONS:
        return DIR_DESCRIPTIONS[rel_path]
    # Try to extract from __init__.py docstring
    init_file = PROJECT_ROOT / rel_path / "__init__.py"
    if init_file.exists():
        doc = extract_docstring(init_file)
        if doc:
            return doc
    return "待补充"


def extract_docstring(filepath: Path) -> str | None:
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
        node = ast.parse(content)
        if isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
            return node.body[0].value.value.strip().split("\n")[0]
    except Exception:
        pass
    return None


# ── P1: 目录树 ──────────────────────────────────────────
def scan_tree(root: Path) -> str:
    dir_pat, file_pat, prefix_pat = parse_gitignore(root)
    lines = ["```"]
    lines.append("browser-agent/")

    def walk(path: Path, prefix: str = "", depth: int = 0):
        if depth > 4:
            return
        try:
            entries = sorted(
                [e for e in path.iterdir() if not is_excluded(e.name, e.is_dir(), dir_pat, file_pat, prefix_pat)],
                key=lambda x: (not x.is_dir(), x.name.lower()),
            )
        except PermissionError:
            return

        for i, entry in enumerate(entries):
            is_last = (i == len(entries) - 1)
            node = "└── " if is_last else "├── "
            connector = "    " if is_last else "│   "
            name = entry.name + "/" if entry.is_dir() else entry.name

            if entry.is_dir():
                rel = entry.relative_to(root).as_posix()
                desc = get_dir_description(rel)
                lines.append(f"{prefix}{node}{name}  # {desc}")
                walk(entry, prefix + connector, depth + 1)
            else:
                lines.append(f"{prefix}{node}{name}")

    walk(root)
    lines.append("```")
    return "\n".join(lines)


# ── P2: 模块状态 ──────────────────────────────────────────
def get_module_status(module_path: Path) -> dict:
    """Infer module status based on mtime and TODO density.
    
    Status thresholds:
      - Active (活跃): at least one .py file modified within last 30 days
      - To-be-confirmed (待确认): last modification > 90 days ago, or has TODO/FIXME > 5
      - To-be-developed (待开发): only __init__.py exists, no other .py files
    """
    now = datetime.datetime.now()
    py_files = list(module_path.rglob("*.py"))
    if not py_files:
        return {"status": "待确认", "reason": "目录下无 Python 文件"}

    # Only __init__.py
    if len(py_files) == 1 and py_files[0].name == "__init__.py":
        return {"status": "待开发", "reason": "仅含 __init__.py，无实际模块代码"}

    # Check last modification time
    max_mtime = max(f.stat().st_mtime for f in py_files)
    last_modified = datetime.datetime.fromtimestamp(max_mtime)
    days_since = (now - last_modified).days

    # Count TODO/FIXME
    todo_count = 0
    for f in py_files:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
            todo_count += len(re.findall(r"#\s*(TODO|FIXME)", content))
        except Exception:
            pass

    if days_since <= 30:
        status = "活跃"
        reason = f"最近修改距今 {days_since} 天内"
    elif days_since > 90:
        status = "待确认"
        reason = f"最近修改距今 {days_since} 天，超过 90 天阈值"
    else:
        status = "活跃" if todo_count > 0 else "待确认"
        reason = f"最近修改距今 {days_since} 天"

    if todo_count > 5:
        reason += f"，含 {todo_count} 个 TODO/FIXME"
        if status == "活跃":
            reason += "（开发中）"

    return {"status": status, "reason": reason, "file_count": len(py_files), "todo_count": todo_count, "last_modified": last_modified.strftime("%Y-%m-%d")}


def scan_module_status(root: Path) -> list[dict]:
    new_architecture_modules = [
        "agent/core",
        "agent/mcp",
        "agent/cli",
        "modes/zhipin",
        "shared",
        "scripts",
        "tests",
    ]
    results = []
    for rel in new_architecture_modules:
        path = root / rel
        if path.exists():
            info = get_module_status(path)
            info["name"] = rel
            info["path"] = rel
            results.append(info)

    # Auto-detect any new modules not in the predefined list
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if entry.name in DEFAULT_EXCLUDE_DIRS:
            continue
        # Check if top-level dir has .py files
        if list(entry.rglob("*.py")):
            rel = entry.relative_to(root).as_posix()
            if rel not in [r["name"] for r in results] and rel not in ("docs", "config"):
                results.append(get_module_status(entry) | {"name": rel, "path": rel})

    return results


# ── P3: 依赖与接口 ──────────────────────────────────────────
def scan_dependencies(root: Path) -> dict:
    result = {"pyproject": [], "requirements": [], "env_vars": []}

    # pyproject.toml
    pyproj = root / "pyproject.toml"
    if pyproj.exists():
        try:
            with open(pyproj, "rb") as f:
                data = tomllib.load(f)
            deps = data.get("project", {}).get("dependencies", [])
            opt_deps = data.get("project", {}).get("optional-dependencies", {})
            for d in deps:
                result["pyproject"].append(d)
            for group, group_deps in opt_deps.items():
                for d in group_deps:
                    result["pyproject"].append(f"[{group}] {d}")
        except Exception as e:
            result["pyproject"].append(f"解析失败：{e}")

    # requirements.txt
    req = root / "requirements.txt"
    if req.exists():
        try:
            for line in req.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    result["requirements"].append(line)
        except Exception as e:
            result["requirements"].append(f"解析失败：{e}")

    # Environment variables
    for pyfile in root.rglob("*.py"):
        if any(p in str(pyfile) for p in [".venv", "__pycache__", ".git"]):
            continue
        try:
            content = pyfile.read_text(encoding="utf-8", errors="replace")
            for match in re.finditer(r'(?:os\.getenv|os\.environ(?:\.get)?)\s*\(\s*["\'](\w+)["\']', content):
                var = match.group(1)
                rel = pyfile.relative_to(root).as_posix()
                entry = {"var": var, "file": rel, "line": content[:match.start()].count("\n") + 1}
                if entry not in result["env_vars"]:
                    result["env_vars"].append(entry)
        except Exception:
            pass

    return result


def _extract_tools_from_file(filepath: Path) -> list[dict]:
    """Extract MCP tool definitions from a Python file using regex."""
    tools = []
    if not filepath.exists():
        return tools
    try:
        content = filepath.read_text(encoding="utf-8")
        pattern = r'types\.Tool\(\s*\n?\s*name\s*=\s*["\']([^"\']+)["\']'
        for match in re.finditer(pattern, content):
            name = match.group(1)
            desc_match = re.search(
                rf'name\s*=\s*["\']{re.escape(name)}["\'].*?description\s*=\s*["\']([^"\']+)["\']',
                content[match.start():match.start() + 500],
                re.DOTALL,
            )
            desc = desc_match.group(1) if desc_match else ""
            tools.append({"name": name, "description": desc})
    except Exception as e:
        tools.append({"name": f"扫描失败：{e}", "description": ""})
    return tools


def scan_mcp_tools(root: Path) -> dict:
    """Scan MCP tools from both generic and mode-specific sources."""
    # 1) Generic browser tools from agent/mcp/server.py
    generic_tools = _extract_tools_from_file(root / "agent" / "mcp" / "server.py")

    # 2) Mode-specific tools from each modes/*/__init__.py
    mode_tools = {}
    modes_dir = root / "modes"
    if modes_dir.exists():
        for entry in sorted(modes_dir.iterdir()):
            if entry.is_dir():
                init_file = entry / "__init__.py"
                if init_file.exists():
                    tools = _extract_tools_from_file(init_file)
                    if tools:
                        mode_tools[entry.name] = tools

    return {"generic": generic_tools, "modes": mode_tools}


# ── P4: 技术栈 ──────────────────────────────────────────
def scan_tech_stack(root: Path) -> dict:
    stack = {
        "language": "",
        "framework": [],
        "database": [],
        "middleware": [],
        "core_deps": [],
    }

    pyproj = root / "pyproject.toml"
    if pyproj.exists():
        try:
            with open(pyproj, "rb") as f:
                data = tomllib.load(f)
            stack["language"] = f"Python {data.get('project', {}).get('requires-python', '>=3.11')}"
            for d in data.get("project", {}).get("dependencies", []):
                stack["core_deps"].append(d)
        except Exception:
            stack["language"] = "Python >=3.11"

    # Detect frameworks from imports
    all_imports = set()
    for pyfile in root.rglob("*.py"):
        if any(p in str(pyfile) for p in [".venv", "__pycache__", ".git"]):
            continue
        try:
            content = pyfile.read_text(encoding="utf-8", errors="replace")
            for match in re.finditer(r'^import (\w+)|^from (\w+)', content, re.MULTILINE):
                mod = match.group(1) or match.group(2)
                all_imports.add(mod)
        except Exception:
            pass

    framework_map = {
        "playwright": "Playwright（浏览器自动化）",
        "mcp": "MCP Python SDK（Model Context Protocol）",
        "camoufox": "Camoufox（反检测浏览器）",
    }
    db_map = {
        "sqlite3": "SQLite（本地存储）",
        "sqlite": "SQLite",
    }
    middleware_map = {
        "httpx": "httpx（HTTP 客户端）",
        "aiofiles": "aiofiles（异步文件 I/O）",
        "yaml": "PyYAML（配置管理）",
    }

    for mod, label in framework_map.items():
        if any(mod in i for i in all_imports):
            stack["framework"].append(label)

    for mod, label in db_map.items():
        if any(mod in i for i in all_imports):
            stack["database"].append(label)

    for mod, label in middleware_map.items():
        if any(mod in i for i in all_imports):
            stack["middleware"].append(label)

    if not stack["framework"]:
        stack["framework"].append("Playwright（浏览器自动化）")
        stack["framework"].append("MCP Python SDK（Model Context Protocol）")

    if not stack["database"]:
        stack["database"].append("SQLite（本地存储）")

    return stack


# ── P5: 已知问题 ──────────────────────────────────────────
def scan_known_issues(root: Path) -> list[dict]:
    issues = []
    markers = ["TODO", "FIXME", "HACK", "XXX"]
    pattern = re.compile(r"(#\s*(" + "|".join(markers) + r")\s*:\s*(.*)|#\s*(" + "|".join(markers) + r")\s+(.*))")

    for pyfile in root.rglob("*.py"):
        if any(p in str(pyfile) for p in [".venv", "__pycache__", ".git"]):
            continue
        try:
            content = pyfile.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(content.splitlines(), 1):
                match = pattern.search(line)
                if match:
                    marker = match.group(2) or match.group(4)
                    text = (match.group(3) or match.group(5) or "").strip()
                    rel = pyfile.relative_to(root).as_posix()
                    issues.append({
                        "file": rel,
                        "line": i,
                        "marker": marker,
                        "text": text,
                    })
        except Exception:
            pass

    return issues


# ── P6: 文档与配置索引 ──────────────────────────────────────────
def scan_docs_config(root: Path) -> list[dict]:
    dir_pat, file_pat, prefix_pat = parse_gitignore(root)
    entries: list[dict] = []
    seen = set()
    scan_dirs = ["docs", "config", "."]

    for scan_dir in scan_dirs:
        target = root / scan_dir
        if not target.exists():
            continue
        for f in sorted(target.rglob("*")):
            if not f.is_file():
                continue
            if f.suffix not in (".md", ".yaml", ".yml", ".json", ".toml"):
                continue
            rel = f.relative_to(root).as_posix()
            if rel.startswith(".") and rel != ".gitignore":
                continue
            if any(p in rel for p in [".venv", "__pycache__", ".git", "browser_profile", "sessions"]):
                continue

            # Check gitignore
            parts = Path(rel).parts
            excluded = False
            for part in parts:
                if is_excluded(part, True, dir_pat, file_pat, prefix_pat):
                    excluded = True
                    break
            if excluded:
                continue

            if rel in seen:
                continue
            seen.add(rel)

            desc = infer_file_description(f)
            entries.append({
                "path": rel,
                "type": f.suffix.lstrip("."),
                "description": desc,
            })

    return entries


def infer_file_description(filepath: Path) -> str:
    """Infer file description from head comment or filename."""
    known_descriptions = {
        "README.md": "项目入口文档",
        "config.yaml": "用户配置文件（搜索/城市/过滤/运行时/代理/页面分析）",
        "pyproject.toml": "项目元数据、依赖声明、工具配置",
        "requirements.txt": "最小生产依赖",
        ".gitignore": "Git 忽略规则",
        "config/.pre-commit-config.yaml": "Pre-commit 钩子配置（ruff → mypy → bandit）",
        "config/mcp_config.json": "AI 编辑器 MCP 服务连接配置",
    }

    rel = filepath.relative_to(PROJECT_ROOT).as_posix()
    if rel in known_descriptions:
        return known_descriptions[rel]

    # Try first line comment
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
        lines = content.strip().splitlines()
        if lines:
            first = lines[0].strip()
            if first.startswith("#"):
                return first.lstrip("# ").strip()
            if first.startswith("/*"):
                return first.strip("/* ").strip()
    except Exception:
        pass

    # Fallback: filename-based
    name = filepath.stem.replace("-", " ").replace("_", " ").title()
    return name


# ── 输出管理 ──────────────────────────────────────────
def manage_output_reports(output_dir: Path, max_keep: int = 10):
    """Keep newest max_keep reports, archive older ones."""
    if not output_dir.exists():
        return
    archive_dir = output_dir / "archive"
    reports = sorted(
        [f for f in output_dir.iterdir() if f.suffix == ".md" and f.is_file()],
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )
    if len(reports) > max_keep:
        archive_dir.mkdir(parents=True, exist_ok=True)
        for old in reports[max_keep:]:
            dest = archive_dir / old.name
            shutil.move(str(old), str(dest))


def generate_timestamp() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


# ── 报告生成 ──────────────────────────────────────────
def generate_report(root: Path) -> str:
    sections = []

    # Header
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sections.append(f"# 项目结构现状报告\n")
    sections.append(f"**生成时间**：{ts}\n")
    sections.append("---\n")

    # S1: 目录树
    sections.append("## S1：项目目录树\n")
    try:
        sections.append(scan_tree(root))
    except Exception as e:
        sections.append(f"> ⚠️ 扫描失败：{e}\n")
    sections.append("")

    # S2: 模块状态
    sections.append("## S2：核心模块状态\n")
    sections.append("| 模块 | 状态 | 文件数 | TODO数 | 最近修改 | 说明 |")
    sections.append("|------|------|--------|--------|---------|------|")
    try:
        for mod in scan_module_status(root):
            sections.append(
                f"| `{mod['name']}` | {mod['status']} | {mod.get('file_count', '-')} | "
                f"{mod.get('todo_count', '-')} | {mod.get('last_modified', '-')} | {mod['reason']} |"
            )
    except Exception as e:
        sections.append(f"| ⚠️ 扫描失败：{e} | | | | | |")
    sections.append("")

    # S3: 依赖与接口
    sections.append("## S3：外部依赖与接口\n")

    deps = scan_dependencies(root)

    sections.append("### pyproject.toml 依赖\n")
    if deps["pyproject"]:
        for d in deps["pyproject"]:
            sections.append(f"- `{d}`")
    else:
        sections.append("（无）")
    sections.append("")

    sections.append("### requirements.txt 依赖\n")
    if deps["requirements"]:
        for d in deps["requirements"]:
            sections.append(f"- `{d}`")
    else:
        sections.append("（无）")
    sections.append("")

    sections.append("### 环境变量\n")
    if deps["env_vars"]:
        sections.append("| 变量名 | 引用文件 | 行号 |")
        sections.append("|--------|---------|------|")
        for ev in sorted(deps["env_vars"], key=lambda x: x["var"]):
            sections.append(f"| `{ev['var']}` | `{ev['file']}` | {ev['line']} |")
    else:
        sections.append("（未检测到环境变量引用）")
    sections.append("")

    sections.append("### MCP 对外接口\n")
    mcp_data = scan_mcp_tools(root)
    generic_tools = mcp_data.get("generic", [])
    mode_tools = mcp_data.get("modes", {})

    if generic_tools:
        sections.append("#### 通用浏览器工具（agent/mcp/server.py）\n")
        sections.append("| 工具名称 | 说明 |")
        sections.append("|----------|------|")
        for t in generic_tools:
            desc_short = t["description"].split(".")[0] if t["description"] else ""
            sections.append(f"| `{t['name']}` | {desc_short} |")
        sections.append(f"\n共 **{len(generic_tools)}** 个通用工具\n")

    if mode_tools:
        for mode_name, tools in mode_tools.items():
            sections.append(f"#### `{mode_name}` 模式工具（modes/{mode_name}/__init__.py）\n")
            sections.append("| 工具名称 | 说明 |")
            sections.append("|----------|------|")
            for t in tools:
                desc_short = t["description"].split(".")[0] if t["description"] else ""
                sections.append(f"| `{t['name']}` | {desc_short} |")
            sections.append(f"\n共 **{len(tools)}** 个 {mode_name} 模式工具\n")

    if not generic_tools and not mode_tools:
        sections.append("（未检测到 MCP 工具注册）")
    sections.append("")

    # S4: 技术栈
    tech = scan_tech_stack(root)
    sections.append("## S4：技术栈\n")
    sections.append(f"- **语言**：{tech['language']}")
    sections.append(f"- **主框架**：{'、'.join(tech['framework']) if tech['framework'] else '无'}")
    sections.append(f"- **数据库**：{'、'.join(tech['database']) if tech['database'] else '无'}")
    sections.append(f"- **中间件**：{'、'.join(tech['middleware']) if tech['middleware'] else '无'}")
    if tech["core_deps"]:
        sections.append("\n**核心依赖**：")
        for d in tech["core_deps"]:
            sections.append(f"  - `{d}`")
    sections.append("")

    # S5: 已知问题
    sections.append("## S5：已知问题（TODO/FIXME/HACK/XXX）\n")
    issues = scan_known_issues(root)
    if issues:
        sections.append(f"共发现 **{len(issues)}** 处标记：\n")
        sections.append("| 文件 | 行号 | 标记 | 内容 |")
        sections.append("|------|------|------|------|")
        for iss in issues:
            text_short = iss["text"][:60] + "..." if len(iss["text"]) > 60 else iss["text"]
            sections.append(f"| `{iss['file']}` | {iss['line']} | `{iss['marker']}` | {text_short} |")
    else:
        sections.append("（未发现 TODO/FIXME/HACK/XXX 标记）")
    sections.append("")

    # S6: 文档与配置索引
    sections.append("## S6：文档与配置索引\n")
    docs = scan_docs_config(root)
    if docs:
        sections.append("| 文件 | 类型 | 说明 |")
        sections.append("|------|------|------|")
        for d in docs:
            sections.append(f"| `{d['path']}` | {d['type']} | {d['description']} |")
        sections.append(f"\n共 **{len(docs)}** 个文件")
    else:
        sections.append("（未发现文档或配置文件）")
    sections.append("")

    # Footer
    sections.append("---\n")
    sections.append(f"*由 `scripts/project_structure_scanner.py` 自动生成*")

    return "\n".join(sections)


# ── CLI ──────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="项目结构自动扫描与报告生成",
    )
    parser.add_argument("--output", "-o", help="输出文件路径（默认自动生成至 docs/structure_reports/）")
    parser.add_argument("--dry-run", action="store_true", help="仅打印到终端，不保存文件")
    args = parser.parse_args()

    report = generate_report(PROJECT_ROOT)

    if args.dry_run:
        print(report)
        return

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(f"✅ 报告已保存至 {output_path}")
    else:
        output_dir = PROJECT_ROOT / "docs" / "structure_reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = generate_timestamp()
        output_path = output_dir / f"project_structure_{timestamp}.md"
        output_path.write_text(report, encoding="utf-8")
        manage_output_reports(output_dir)
        print(f"✅ 报告已保存至 {output_path}")

    print(f"📊 P1-P7 全部完成")


if __name__ == "__main__":
    main()
