"""日志收集器 — 管理控制台日志、网络日志、对话框和可访问性快照。"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from shared.exceptions import PageNotReadyError
from shared.logging_config import get_logger

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = get_logger("browser")

_PLAYWRIGHT_ERRORS = (Exception,)  # Playwright 可能抛出多种异常，统一兜底


class LogCollector:
    """日志收集器 — 管理控制台日志、网络日志、对话框和可访问性快照。"""

    def __init__(self, page: Page | None = None):
        self._page: Page | None = page
        self._console_logs: list[dict] = []
        self._network_logs: list[dict] = []
        self._pending_dialog: Any = None

    @property
    def page(self) -> Page | None:
        return self._page

    @page.setter
    def page(self, value: Page | None) -> None:
        self._page = value

    def get_console_logs(self, level: str = "info") -> list[dict]:
        levels = {"error": 0, "warning": 1, "info": 2, "debug": 3}
        min_level = levels.get(level, 2)
        result = []
        for log in self._console_logs:
            log_level = levels.get(log.get("type", "info"), 2)
            if log_level <= min_level:
                result.append(log)
        return result

    def get_network_logs(self, include_static: bool = False) -> list[dict]:
        if include_static:
            return list(self._network_logs)
        static_types = {"image", "font", "stylesheet", "media"}
        return [r for r in self._network_logs
                if r.get("resource_type", "") not in static_types]

    async def get_pending_dialog(self) -> dict | None:
        if self._pending_dialog:
            return {
                "type": self._pending_dialog.get("type"),
                "message": self._pending_dialog.get("message"),
                "default_value": self._pending_dialog.get("default_value"),
            }
        return None

    async def get_accessibility_snapshot(self) -> dict | None:
        if not self._page:
            raise PageNotReadyError(
                "页面未初始化，请先调用 start() 启动浏览器",
                error_code="PAGE_NOT_READY",
            )
        try:
            tree = await self._page.accessibility.snapshot()
            if not tree:
                return {"role": "RootWebArea", "children": []}

            def flatten(node, depth=0, max_depth=10):
                if depth > max_depth:
                    return None
                entry = {
                    "role": node.get("role", ""),
                    "name": node.get("name", ""),
                    "value": node.get("value", ""),
                    "description": node.get("description", ""),
                    "focused": node.get("focused", False),
                    "focussable": node.get("focusable", False),
                    "depth": depth,
                }
                children = node.get("children", [])
                if isinstance(children, list):
                    flat_kids = []
                    for child in children:
                        kid = flatten(child, depth + 1, max_depth)
                        if kid:
                            flat_kids.append(kid)
                    entry["children"] = flat_kids
                return entry

            return flatten(tree)
        except Exception as e:
            logger.warning("无障碍树获取失败: %s", e)
            return None

    async def handle_dialog(self, accept: bool, prompt_text: str = "") -> bool:
        d = self._pending_dialog
        if d is None:
            return False
        dialog = d.get("_dialog")
        if dialog is None:
            return False
        try:
            if accept:
                await dialog.accept(prompt_text if prompt_text else None)
            else:
                await dialog.dismiss()
            self._pending_dialog = None
            return True
        except _PLAYWRIGHT_ERRORS as e:
            logger.warning("处理对话框失败: %s", e)
            return False

    def _setup_page_listeners(self, page):
        self._console_logs = []
        self._network_logs = []
        self._pending_dialog = None

        page.on("console", lambda msg: self._console_logs.append({
            "type": msg.type, "text": msg.text,
            "location": msg.location, "timestamp": time.time(),
        }) if self._console_logs is not None else None)

        page.on("dialog", lambda d: setattr(self, "_pending_dialog", {
            "type": d.type, "message": d.message,
            "default_value": d.default_value, "_dialog": d,
        }))

        page.on("request", lambda req: (
            len(self._network_logs) < 500 and self._network_logs.append({
                "url": req.url, "method": req.method,
                "resource_type": req.resource_type,
                "type": "request", "timestamp": time.time(),
            })
        ) if self._network_logs is not None else None)

        page.on("response", lambda res: (
            len(self._network_logs) < 500 and self._network_logs.append({
                "url": res.url, "status": res.status,
                "type": "response", "timestamp": time.time(),
            })
        ) if self._network_logs is not None else None)
