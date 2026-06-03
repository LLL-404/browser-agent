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

    def __init__(
        self,
        message: str,
        error_code: str,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": str(self),
            "details": self.details,
        }


# ── 网络相关异常 ──────────────────────────────────────────────


class NetworkError(BrowserAutomationError):
    """网络操作异常基类。"""


class NavigationTimeoutError(NetworkError):
    """页面导航超时。"""


class NavigationFailedError(NetworkError):
    """页面导航失败（非超时原因）。"""


class ConnectionRefusedError(NetworkError):
    """连接被拒绝。"""


# ── 元素操作异常 ────────────────────────────────────────────


class ElementNotFoundError(BrowserAutomationError):
    """元素未找到。"""


class ElementNotInteractableError(BrowserAutomationError):
    """元素不可交互（被遮挡、disabled、hidden 等）。"""


class ElementClickFailedError(BrowserAutomationError):
    """元素点击操作失败。"""


class ElementFillFailedError(BrowserAutomationError):
    """输入框填充失败。"""


# ── 浏览器状态异常 ──────────────────────────────────────────


class BrowserStartError(BrowserAutomationError):
    """浏览器启动失败。"""


class BrowserCrashError(BrowserAutomationError):
    """浏览器崩溃。"""


class PageNotReadyError(BrowserAutomationError):
    """页面未就绪（未初始化或已关闭）。"""


class BrowserAlreadyRunningError(BrowserAutomationError):
    """浏览器已在运行中。"""


# ── 配置与验证异常 ──────────────────────────────────────────


class ConfigurationError(BrowserAutomationError):
    """配置加载或解析错误。"""


class ValidationError(BrowserAutomationError):
    """数据验证失败。"""


# ── 反爬虫相关异常 ──────────────────────────────────────────


class CaptchaDetectedError(BrowserAutomationError):
    """检测到验证码。"""


class AccessBlockedError(BrowserAutomationError):
    """访问被拒绝（IP 封禁、账号限制等）。"""


class LoginRequiredError(BrowserAutomationError):
    """需要登录。"""


# ── 操作级轻量异常标记（用于非致命场景） ─────────────────


class OperationWarning(Exception):
    """操作级警告 — 不被视为致命错误，仅用于传递上下文。

    与 BrowserAutomationError 体系独立，用于那些"不算失败但需要提醒"的场景。
    """

    def __init__(self, message: str, context: dict[str, Any] | None = None):
        super().__init__(message)
        self.context = context or {}