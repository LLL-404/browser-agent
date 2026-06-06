"""通用页面分析模块 — 截图 + HTML 快照，不绑定任何业务页面结构。"""
import time
from pathlib import Path

from playwright.async_api import Page

from shared.logging_config import get_logger

logger = get_logger("page")

SCREENSHOT_DIR = Path("data/screenshots")
SNAPSHOT_DIR = Path("data/snapshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


class PageAnalysis:
    def __init__(self, screenshot_path: str | None, html_snapshot: str | None, analysis: dict):
        self.screenshot_path = screenshot_path
        self.html_snapshot = html_snapshot
        self.analysis = analysis

    def has_issues(self) -> bool:
        return self.analysis.get("has_issues", False)

    def summary(self) -> str:
        parts = []
        a = self.analysis
        if a.get("page_type"):
            parts.append(f"页面类型: {a['page_type']}")
        if a.get("issues"):
            parts.append(f"异常: {', '.join(a['issues'])}")
        return " | ".join(parts) if parts else "无分析数据"


async def capture_screenshot(page: Page, name: str = "page") -> str | None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = str(SCREENSHOT_DIR / f"{name}_{ts}.png")
    try:
        await page.screenshot(path=path, full_page=True)
        return path
    except Exception as e:
        logger.warning("截图失败: %s", e)
        return None


async def capture_html_snapshot(page: Page, max_len: int = 50000) -> str | None:
    try:
        html = await page.content()
        if len(html) > max_len:
            half = max_len // 2
            html = html[:half] + "\n<!-- ... 省略 ... -->\n" + html[-half:]
        return html
    except Exception as e:
        logger.warning("HTML快照获取失败: %s", e)
        return None
