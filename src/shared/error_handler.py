"""统一异常处理工具。

提供异常分类、转换和恢复建议等通用功能，
减少各模块中重复的异常处理样板代码。
"""

from __future__ import annotations

import asyncio
from typing import Any

from shared.exceptions import (
    BrowserAutomationError,
    PageNotReadyError,
    NavigationTimeoutError,
    NavigationFailedError,
    ElementNotFoundError,
    ElementNotInteractableError,
    BrowserCrashError,
)
from shared.logging_config import get_logger

logger = get_logger("error_handler")

_ERROR_RECOVERY_HINTS: dict[str, str] = {
    "PAGE_NOT_READY": "请先调用 open() 启动浏览器并导航到页面",
    "NAV_TIMEOUT": "网络较慢或目标网站响应超时，请稍后重试或增加超时时间",
    "NAV_FAILED": "导航失败，请检查 URL 是否正确或网络连接是否正常",
    "CONNECTION_REFUSED": "连接被拒绝，目标网站可能不可用或需要代理",
    "ELEMENT_NOT_FOUND": "元素未找到，页面结构可能已变化，请检查选择器是否正确",
    "ELEMENT_NOT_INTERACTABLE": "元素被遮挡或不可交互，请先滚动页面或等待元素可见",
    "CLICK_FAILED": "点击失败，请确认元素存在且可交互",
    "FILL_FAILED": "输入失败，请确认输入框存在且可编辑",
    "BROWSER_START_FAILED": "浏览器启动失败，请检查浏览器环境配置",
    "BROWSER_CRASHED": "浏览器已崩溃，请重新启动浏览器",
    "BROWSER_ALREADY_RUNNING": "浏览器已在运行中，无需重复启动",
    "CAPTCHA_DETECTED": "检测到验证码，请手动在浏览器中完成验证",
    "ACCESS_BLOCKED": "访问被拒绝，可能 IP 被封禁或需要登录",
    "LOGIN_REQUIRED": "需要登录，请先完成登录操作",
    "CONFIG_ERROR": "配置错误，请检查 config.yaml 文件是否正确",
    "VALIDATION_ERROR": "数据验证失败，请检查输入参数",
}


def get_recovery_hint(error: BrowserAutomationError) -> str:
    """根据异常错误码返回恢复建议。"""
    return _ERROR_RECOVERY_HINTS.get(
        error.error_code,
        "请稍后重试，如持续出现此问题请联系技术支持",
    )


def format_error_for_mcp(error: Exception) -> dict[str, Any]:
    """将异常转换为适合 MCP 接口返回的 dict 格式。

    如果是 BrowserAutomationError，包含完整的错误码、详情和恢复建议。
    如果是普通 Exception，仅包含错误消息。
    """
    if isinstance(error, BrowserAutomationError):
        result = error.to_dict()
        result["recovery_hint"] = get_recovery_hint(error)
        return result
    return {
        "error_code": "UNEXPECTED_ERROR",
        "message": str(error),
        "details": {"exception_type": type(error).__name__},
        "recovery_hint": "发生未预期错误，请稍后重试",
    }


def classify_playwright_error(error: Exception) -> type[BrowserAutomationError]:
    """根据 Playwright 异常消息归类为对应的自定义异常类型。

    用于在 BrowserController 中将底层 Playwright 异常
    转换为业务级异常。
    """
    msg = str(error).lower()

    if "timeout" in msg or isinstance(error, (asyncio.TimeoutError, TimeoutError)):
        return NavigationTimeoutError
    if "not found" in msg or "no element" in msg or "resolve" in msg:
        return ElementNotFoundError
    if "interactable" in msg or "click intercepted" in msg or "visible" in msg:
        return ElementNotInteractableError
    if "target closed" in msg or "crashed" in msg or "detached" in msg:
        return BrowserCrashError
    if "net::" in msg or "connection" in msg or "dns" in msg:
        return NavigationFailedError
    return BrowserAutomationError