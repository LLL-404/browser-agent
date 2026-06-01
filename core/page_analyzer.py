"""页面分析模块 — 截图+HTML源码分析，让AI同时"看"和"读"页面。"""

import json
import logging
import time
from pathlib import Path
from playwright.async_api import Page

from .selectors import JOB_CARD, JOB_TITLE, COMPANY_NAME, JOB_SALARY, DETAIL_DESC

logger = logging.getLogger("boss_job_hunter.page_analyzer")

SCREENSHOT_DIR = Path("data/screenshots")
SNAPSHOT_DIR = Path("data/snapshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


class PageAnalysis:
    """页面分析结果，包含截图路径、HTML快照和分析报告。"""

    def __init__(self, screenshot_path: str | None, html_snapshot: str | None,
                 analysis: dict):
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
        if a.get("login_status"):
            parts.append(f"登录状态: {a['login_status']}")
        if a.get("issues"):
            parts.append(f"异常: {', '.join(a['issues'])}")
        if a.get("job_count") is not None:
            parts.append(f"职位数: {a['job_count']}")
        return " | ".join(parts) if parts else "分析完成"


async def capture_screenshot(page: Page, name: str = "auto") -> str | None:
    try:
        ts = int(time.time())
        path = SCREENSHOT_DIR / f"{name}_{ts}.png"
        await page.screenshot(path=str(path), full_page=False)
        return str(path)
    except Exception as e:
        logger.warning("截图失败: %s", e)
        return None


async def capture_html_snapshot(page: Page, max_len: int = 10000) -> str | None:
    try:
        html = await page.content()
        if len(html) > max_len:
            half = max_len // 2
            html = html[:half] + "\n<!-- ... 中间省略 ... -->\n" + html[-half:]
        return html
    except Exception as e:
        logger.warning("HTML快照获取失败: %s", e)
        return None


def _detect_page_type(url: str) -> tuple[str, str]:
    url_lower = url.lower()
    if "/user/" in url_lower or "passport" in url_lower or "login" in url_lower:
        return "登录/注册页", "未登录"
    if "zhipin.com" in url_lower:
        return "BOSS直聘页面", "已登录（推测）"
    return "未知页面", "未知"


async def _detect_captcha_elements(page: Page) -> list[str]:
    from .selectors import CAPTCHA_INDICATORS
    issues = []
    for sel in CAPTCHA_INDICATORS:
        try:
            if await page.query_selector(sel):
                issues.append("检测到验证码元素")
                break
        except Exception:
            continue
    return issues


def _detect_anti_scrape_text(body_text: str) -> list[str]:
    issues = []
    error_kw = ["安全验证", "滑块验证", "访问异常", "请求过于频繁",
                "账号异常", "请稍后再试", "系统繁忙"]
    for kw in error_kw:
        if kw in body_text:
            issues.append(f"检测到反爬文本: '{kw}'")
    return issues


async def _get_dom_structure(page: Page) -> dict:
    structure_js = f"""() => {{
        const result = {{}};
        result.has_body = !!document.body;
        result.body_len = document.body ? document.body.innerText.length : 0;
        const selectors = [
            '{JOB_CARD}', '{JOB_TITLE}', '{COMPANY_NAME}',
            '{JOB_SALARY}', '.company-info', '{DETAIL_DESC[0]}',
            '.boss-active-time'
        ];
        for (const sel of selectors) {{
            try {{
                const els = document.querySelectorAll(sel);
                result[sel] = els.length;
            }} catch (e) {{
                result[sel] = 'error';
            }}
        }}
        return result;
    }}"""
    try:
        return await page.evaluate(structure_js)
    except Exception as e:
        logger.warning("DOM结构获取失败: %s", e)
        return {"error": "无法获取DOM结构"}


async def analyze_page(page: Page, name: str = "auto") -> PageAnalysis:
    screenshot_path = await capture_screenshot(page, name)
    html_snapshot = await capture_html_snapshot(page)

    page_type, login_status = _detect_page_type(page.url)
    issues: list[str] = []

    issues.extend(await _detect_captcha_elements(page))

    try:
        body_text: str = await page.inner_text("body")
        issues.extend(_detect_anti_scrape_text(body_text))
    except Exception as e:
        logger.warning("反爬文本检测失败: %s", e)

    has_issues = len(issues) > 0

    job_count = None
    try:
        cards = await page.query_selector_all(JOB_CARD)
        if cards is not None:
            job_count = len(cards)
    except Exception as e:
        logger.warning("职位计数失败: %s", e)

    try:
        detail_sel = ", ".join(DETAIL_DESC[:3])
        if await page.query_selector(detail_sel):
            page_type = "职位详情页"
    except Exception as e:
        logger.warning("详情页检测失败: %s", e)

    dom_structure = await _get_dom_structure(page)

    analysis = {
        "url": page.url,
        "title": await page.title(),
        "page_type": page_type,
        "login_status": login_status,
        "issues": issues,
        "has_issues": has_issues,
        "job_count": job_count,
        "dom_structure": dom_structure,
    }

    try:
        report_path = SNAPSHOT_DIR / f"{name}_analysis.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)
        analysis["report_path"] = str(report_path)
    except Exception as e:
        logger.warning("分析报告保存失败: %s", e)

    return PageAnalysis(screenshot_path, html_snapshot, analysis)


async def quick_check(page: Page) -> dict[str, str | list | int | None]:
    result: dict[str, str | list | int | None] = {"page_type": "未知", "login_status": "未知",
              "issues": [], "job_count": None}

    try:
        url_lower: str = page.url.lower()
        if any(k in url_lower for k in ["/user/", "passport", "login"]):
            result["page_type"] = "登录/注册页"
            result["login_status"] = "未登录"
        elif "zhipin.com" in url_lower:
            result["page_type"] = "BOSS直聘页面"
            result["login_status"] = "已登录（推测）"

        body_text: str = await page.inner_text("body")
        for kw in ["验证码", "安全验证", "访问异常"]:
            if kw in body_text:
                result["issues"].append(kw)

        cards = await page.query_selector_all(JOB_CARD)
        if cards is not None:
            result["job_count"] = len(cards)
    except Exception as e:
        logger.warning("快速检查失败: %s", e)
        result["issues"].append("检查过程出错")

    return result
