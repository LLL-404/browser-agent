"""验证 `.understand-anything/knowledge-graph.json` 与源码一致性。

用法：
  python scripts/opencode/verify_knowledge_graph.py
  python scripts/opencode/verify_knowledge_graph.py --fix

钩子入口（AGENTS.md）：
  python -m scripts.opencode.verify_knowledge_graph
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
GRAPH = BASE / ".understand-anything" / "knowledge-graph.json"


def _check(cond: bool, field: str, detail: str) -> str | None:
    return None if cond else f"[MISMATCH] {field}: {detail}"


def _line_of(path: Path, class_name: str) -> int:
    """Return the 1-indexed line where `class <class_name>` is defined."""
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip().startswith(f"class {class_name}(") or line.strip() == f"class {class_name}:":
            return i
    return -1


def _find_flow_line(path: Path, flow_name: str) -> int:
    """Return the line of FlowSkeleton registration by name."""
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if f'name="{flow_name}"' in line or f"name='{flow_name}'" in line:
            return i
    return -1


def verify() -> list[str]:
    errors: list[str] = []
    if not GRAPH.exists():
        return [f"Graph file not found: {GRAPH}"]

    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    packages = {p["name"]: p for p in graph.get("packages", [])}

    # ── 1. Line numbers of 14 core classes ──
    class_checks = {
        "BrowsingAgent":     ("src/browser_agent/core/agent.py",     523),
        "BrowserAgent":      ("src/browser_agent/core/agent.py",     65),
        "BrowserController": ("src/browser_agent/core/browser.py",   55),
        "PagePerceiver":     ("src/browser_agent/core/perceiver.py", 444),
        "SemanticInferrer":  ("src/browser_agent/core/perceiver.py", 134),
        "PageClassifier":    ("src/browser_agent/core/perceiver.py", 277),
        "DecisionEngine":    ("src/browser_agent/core/decider.py",   922),
        "FlowRegistry":      ("src/browser_agent/core/decider.py",   150),
        "SemanticDecider":   ("src/browser_agent/core/decider.py",   688),
        "LoopController":    ("src/browser_agent/core/decider.py",   377),
        "ErrorRecovery":     ("src/browser_agent/core/decider.py",   502),
        "ExecutionEngine":   ("src/browser_agent/core/executor.py",  332),
        "SpeedController":   ("src/browser_agent/core/executor.py",  80),
        "BehaviorSimulator": ("src/browser_agent/core/executor.py",  147),
    }
    for cls_name, (rel_path, expected_line) in class_checks.items():
        full_path = BASE / rel_path
        actual = _line_of(full_path, cls_name)
        err = _check(
            actual == expected_line,
            f"class {cls_name} line",
            f"expected {expected_line}, got {actual}",
        )
        if err:
            errors.append(err)

    # ── 2. MCP tool definitions count ──
    defs_file = BASE / "src/browser_agent/mcp/definitions.py"
    defs_text = defs_file.read_text(encoding="utf-8")
    actual_tool_count = defs_text.count("types.Tool(")

    mcp_pkg = packages.get("browser_agent.mcp", {})
    mcp_entities = mcp_pkg.get("entities", {})
    claimed_defs = mcp_entities.get("tool_definitions_count", 0)
    err = _check(
        actual_tool_count == claimed_defs,
        "tool_definitions_count",
        f"expected {actual_tool_count}, graph says {claimed_defs}",
    )
    if err:
        errors.append(err)

    # ── 3. MCP tool names ──
    actual_tool_names = set(re.findall(r'name="(\w+)"', defs_text))
    graph_tool_names = set(mcp_entities.get("tools", []))
    missing_in_graph = actual_tool_names - graph_tool_names
    extra_in_graph = graph_tool_names - actual_tool_names
    if missing_in_graph:
        errors.append(f"[MISMATCH] MCP tools missing from graph: {sorted(missing_in_graph)}")
    if extra_in_graph:
        errors.append(f"[MISMATCH] MCP tools in graph but not in definitions: {sorted(extra_in_graph)}")

    # ── 4. zhipin_search flow line ──
    flows_pkg = packages.get("browser_agent.flows", {})
    for flow in flows_pkg.get("entities", {}).get("flows", []):
        if flow["name"] == "zhipin_search":
            decider = BASE / "src/browser_agent/core/decider.py"
            actual_line = _find_flow_line(decider, "zhipin_search")
            claimed_line = int(flow["file"].split(":")[1])
            err = _check(
                actual_line == claimed_line,
                f"flow zhipin_search line",
                f"expected {actual_line}, graph says {claimed_line}",
            )
            if err:
                errors.append(err)
            break

    # ── 5. shared.engine deprecated ──
    engine_dir = BASE / "src/shared/engine"
    err = _check(
        not engine_dir.exists(),
        "shared.engine deprecated",
        f"directory still exists at {engine_dir}",
    )
    if err:
        errors.append(err)

    # ── 6. modes.zhipin submodule accuracy ──
    zhipin_dir = BASE / "src/modes/zhipin"
    actual_modules = sorted(
        p.stem for p in zhipin_dir.glob("*.py") if p.stem != "__pycache__"
    )
    zhipin_pkg = packages.get("modes.zhipin", {})
    graph_modules = sorted(zhipin_pkg.get("submodules", []))
    missing_mods = set(graph_modules) - set(actual_modules)
    extra_mods = set(actual_modules) - set(graph_modules)
    if missing_mods:
        errors.append(f"[MISMATCH] modes.zhipin submodules in graph not found: {sorted(missing_mods)}")
    if extra_mods:
        errors.append(f"[MISMATCH] modes.zhipin actual modules missing from graph: {sorted(extra_mods)}")

    # ── 7. Architecture layer classes exist ──
    layer_checks = {
        "Agent Layer":     "BrowsingAgent",
        "Perceive Layer":  "PagePerceiver",
        "Decide Layer":    "DecisionEngine",
        "Execute Layer":   "ExecutionEngine",
        "Browser Layer":   "BrowserController",
    }
    for layer_name, expected_class in layer_checks.items():
        found = False
        for pkg in packages.values():
            classes = pkg.get("entities", {}).get("classes", {})
            if expected_class in classes:
                found = True
                break
        err = _check(found, f"layer {layer_name}", f"class {expected_class} not found in any package")
        if err:
            errors.append(err)

    return errors


def main() -> None:
    errors = verify()
    if errors:
        print(f"Knowledge Graph Verification: {len(errors)} issue(s) found\n")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)
    else:
        print("Knowledge Graph Verification: ALL CHECKS PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
