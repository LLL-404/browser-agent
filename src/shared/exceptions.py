"""浏览器自动化异常体系。

提供分层清晰的异常类型，替代之前过度宽泛的 Exception 捕获模式。
每个异常都包含 error_code 和 details，便于上层调用者进行差异化处理和日志分析。
"""

from __future__ import annotations

from typing import Any


class BrowserAutomationError(Exception):
    """浏览器自动化基础异常类。

    所有自定义异常的基类，提供统一的 error_code 和 details 属性，
    以及 to_dict() 方法用于 JSON 序列化（适配 MCP 接口）。
    """

    _default_error_code: str = "BROWSER_ERROR"

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.error_code = error_code or self._default_error_code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """将异常序列化为 JSON 兼容的字典（适配 MCP 接口）。"""
        return {
            "error_code": self.error_code,
            "message": str(self),
            "details": self.details,
        }


# ── 网络相关异常 ──────────────────────────────────────────────


class NetworkError(BrowserAutomationError):
    """网络操作异常基类。"""
    _default_error_code = "NETWORK_ERROR"


class NavigationTimeoutError(NetworkError):
    """页面导航超时。"""
    _default_error_code = "NAV_TIMEOUT"


class NavigationFailedError(NetworkError):
    """页面导航失败（非超时原因）。"""
    _default_error_code = "NAV_FAILED"


class BrowserConnectionRefusedError(NetworkError):
    """连接被拒绝。"""
    _default_error_code = "CONN_REFUSED"


# ── 元素操作异常 ────────────────────────────────────────────


class ElementNotFoundError(BrowserAutomationError):
    """元素未找到。"""
    _default_error_code = "ELEM_NOT_FOUND"


class ElementNotInteractableError(BrowserAutomationError):
    """元素不可交互（被遮挡、disabled、hidden 等）。"""
    _default_error_code = "ELEM_NOT_INTERACTABLE"


class ElementClickFailedError(BrowserAutomationError):
    """元素点击操作失败。"""
    _default_error_code = "ELEM_CLICK_FAILED"


class ElementFillFailedError(BrowserAutomationError):
    """输入框填充失败。"""
    _default_error_code = "ELEM_FILL_FAILED"


# ── 浏览器状态异常 ──────────────────────────────────────────


class BrowserStartError(BrowserAutomationError):
    """浏览器启动失败。"""
    _default_error_code = "BROWSER_START_FAILED"


class BrowserCrashError(BrowserAutomationError):
    """浏览器崩溃。"""
    _default_error_code = "BROWSER_CRASH"


class PageNotReadyError(BrowserAutomationError):
    """页面未就绪（未初始化或已关闭）。"""
    _default_error_code = "PAGE_NOT_READY"


class BrowserAlreadyRunningError(BrowserAutomationError):
    """浏览器已在运行中。"""
    _default_error_code = "BROWSER_ALREADY_RUNNING"


# ── 配置与验证异常 ──────────────────────────────────────────


class ConfigurationError(BrowserAutomationError):
    """配置加载或解析错误。"""
    _default_error_code = "CONFIG_ERROR"


class ValidationError(BrowserAutomationError):
    """数据验证失败。"""
    _default_error_code = "VALIDATION_ERROR"


# ── 反爬虫相关异常 ──────────────────────────────────────────


class CaptchaDetectedError(BrowserAutomationError):
    """检测到验证码。"""
    _default_error_code = "CAPTCHA_DETECTED"


class AccessBlockedError(BrowserAutomationError):
    """访问被拒绝（IP 封禁、账号限制等）。"""
    _default_error_code = "ACCESS_BLOCKED"


class LoginRequiredError(BrowserAutomationError):
    """需要登录。"""
    _default_error_code = "LOGIN_REQUIRED"


# ── 操作级轻量异常标记（用于非致命场景） ─────────────────


class OperationWarning(Exception):
    """操作级警告 — 不被视为致命错误，仅用于传递上下文。

    与 BrowserAutomationError 体系独立，用于那些"不算失败但需要提醒"的场景。
    """

    def __init__(self, message: str, context: dict[str, Any] | None = None):
        super().__init__(message)
        self.context = context or {}
