# 开发计划 · project_structure_scanner.py

**时间**：2026-06-01

## 架构：单文件脚本，6 个扫描模块

**实现路径**：纯标准库，无新增依赖。

## 各模块方案

| 模块 | 实现方式 |
|------|---------|
| **P1 目录树** | `os.walk` + 解析 `.gitignore` → 树形输出，从 `__init__.py` docstring 提取目录说明 |
| **P2 模块状态** | 检查 `__init__.py` 版本标记 + `os.path.getmtime` + TODO 密度 → 活跃/待开发/待确认 |
| **P3 依赖/接口** | `tomllib` 解析 `pyproject.toml` + pip 格式解析 `requirements.txt`；正则提取 `types.Tool(name=...)` |
| **P4 技术栈** | 从 `pyproject.toml` 的 `requires-python` + dependencies + import 扫描推断 |
| **P5 已知问题** | 全局扫描 `TODO`/`FIXME`/`HACK`/`XXX` 注释，附文件路径行号 |
| **P6 配置索引** | glob 扫描 `docs/` `config/` 根目录 `.md` `.yaml` `.json` `.toml`，从头部注释提取说明 |

## CLI 接口

```
python scripts/project_structure_scanner.py          # 保存到 docs/structure_reports/
python scripts/project_structure_scanner.py --dry-run # 仅终端输出
python scripts/project_structure_scanner.py -o custom.md
```

**保留策略**：最多 10 份报告，旧报告自动归档至 `archive/`。

---

*等待 Boss 审批后开始编码。*
