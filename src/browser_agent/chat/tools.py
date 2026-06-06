"""CLI 工具管理 — 白名单命令执行，路径安全限制。"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from shared.logging_config import get_logger

logger = get_logger("chat.tools")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

WHITELIST: list[dict] = [
    {"pattern": "agent-cli --mode zhipin search", "risk": "low", "desc": "触发 BOSS 直聘搜索"},
    {"pattern": "agent-cli --mode zhipin stats", "risk": "low", "desc": "查看搜索统计"},
    {"pattern": "send-report", "risk": "low", "desc": "发送交付报告"},
    {"pattern": "cat", "risk": "low", "desc": "读取文件内容"},
    {"pattern": "type", "risk": "low", "desc": "读取文件内容 (Windows)"},
    {"pattern": "ls", "risk": "low", "desc": "列出目录"},
    {"pattern": "dir", "risk": "low", "desc": "列出目录 (Windows)"},
    {"pattern": "wc -l", "risk": "low", "desc": "统计行数"},
    {"pattern": "grep -r", "risk": "medium", "desc": "递归搜索文件内容"},
    {"pattern": "findstr", "risk": "medium", "desc": "搜索文件内容 (Windows)"},
    {"pattern": "python", "risk": "medium", "desc": "运行 Python 脚本"},
]

BLOCKED_COMMANDS = [
    "rm ", "del ", "rd ", "rmdir ", "sudo ", "chmod ", "chown ",
    "pip install", "pip3 install", "npm install",
    "git push", "git commit", "git merge",
    "curl ", "wget ", "Invoke-WebRequest",
    "format ", "diskpart", "reg ", "regedit",
    "shutdown", "restart", "taskkill",
]

BLOCKED_PATHS = [
    "/etc/", "/sys/", "/proc/", "/dev/",
    "~/.ssh", "/root/", "C:\\Windows\\", "C:\\Program Files",
    "AppData", "ProgramData",
]


def _is_path_safe(cmd: str) -> bool:
    for bp in BLOCKED_PATHS:
        if bp.lower() in cmd.lower():
            return False
    return True


def _matches_whitelist(cmd: str) -> dict | None:
    cmd_stripped = cmd.strip()
    cmd_lower = cmd_stripped.lower()
    for entry in WHITELIST:
        pat = entry["pattern"].rstrip()
        pat_lower = pat.lower()
        if cmd_lower == pat_lower or cmd_lower.startswith(pat_lower + " "):
            return entry
    return None


def _is_blocked(cmd: str) -> str | None:
    cmd_lower = cmd.lower().strip()
    for bc in BLOCKED_COMMANDS:
        bc_lower = bc.lower().rstrip()
        if cmd_lower == bc_lower or cmd_lower.startswith(bc_lower + " "):
            return bc
    return None


def execute(cmd: str, timeout: int = 30, show_terminal: bool | None = None) -> dict:
    """执行白名单命令，返回结果。

    对长时间运行的程序（browser agent、report 等）自动打开新终端窗口。
    可通过 show_terminal=True 强制显示终端，False 强制后台执行。

    返回:
        {"ok": True, "output": "...", "returncode": 0} 或
        {"ok": False, "error": "拒绝原因"}
    """
    # 检查黑名单
    blocked = _is_blocked(cmd)
    if blocked:
        msg = f"命令被禁止: {blocked}"
        logger.warning("工具调用被拒绝: %s", cmd)
        return {"ok": False, "error": msg, "returncode": -1}

    # 检查白名单
    match = _matches_whitelist(cmd)
    if not match:
        msg = "命令不在白名单中，请使用允许的命令"
        logger.warning("工具调用不在白名单: %s", cmd)
        return {"ok": False, "error": msg, "returncode": -1}

    # 路径安全检查
    if not _is_path_safe(cmd):
        msg = "路径超出项目范围，拒绝执行"
        return {"ok": False, "error": msg, "returncode": -1}

    logger.info("执行工具命令: %s (风险: %s, %s)", cmd, match["risk"], match["desc"])

    # Windows 兼容：翻译 Unix 命令
    translated = cmd
    if os.name == "nt":
        tokens = translated.split(None, 1)
        if tokens:
            first = tokens[0].lower()
            rest = tokens[1] if len(tokens) > 1 else ""
            unix_to_win = {"ls": "dir", "cat": "type"}
            if first in unix_to_win:
                if rest:
                    translated = f"{unix_to_win[first]} {rest}"
                else:
                    translated = unix_to_win[first]
                # dir 命令将 / 视为开关，需要用 .\ 前缀
                if first == "ls" and rest:
                    translated = f'dir "{rest}"'

    try:
        # 自动检测是否需要显示终端，或由调用方指定
        if show_terminal is None:
            show_terminal = any(kw in cmd for kw in ["agent-cli", "send-report"])
        creation_flags = 0
        if os.name == "nt" and show_terminal:
            creation_flags = subprocess.CREATE_NEW_CONSOLE  # 0x00000010

        if show_terminal:
            logger.info("启动终端窗口执行: %s", cmd)
            subprocess.Popen(  # pylint: disable=consider-using-with
                translated,
                shell=True,
                creationflags=creation_flags,
                cwd=str(PROJECT_ROOT),
            )
            return {
                "ok": True,
                "output": "",
                "returncode": 0,
                "note": "已在新的终端窗口中启动，请切换到该窗口查看输出",
            }

        result = subprocess.run(  # pylint: disable=subprocess-run-check
            translated,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(PROJECT_ROOT),
        )
        output = result.stdout
        if result.stderr:
            output += "\n[stderr]\n" + result.stderr

        return {
            "ok": result.returncode == 0,
            "output": output.strip(),
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"执行超时 ({timeout}秒)", "returncode": -1}
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("工具执行异常: %s", e)
        return {"ok": False, "error": str(e), "returncode": -1}


def format_tool_prompt() -> str:
    """返回工具能力说明，供 Agent System Prompt 使用。"""
    lines = ["可用工具命令："]
    for entry in WHITELIST:
        lines.append(f"  {entry['pattern']}  — {entry['desc']} (风险: {entry['risk']})")
    return "\n".join(lines)
