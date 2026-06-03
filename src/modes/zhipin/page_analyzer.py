"""BOSS 直聘页面分析 — 页面类型/验证码/岗位卡片检测。"""
import json
import time
from pathlib import Path
from playwright.async_api import Page

from modes.zhipin.selectors import (
    JOB_CARD, JOB_TITLE, COMPANY_NAME, JOB_SALARY, DETAIL_DESC,
    CAPTCHA_INDICATORS,
)
from agent.core.page import capture_screenshot, capture_html_snapshot, PageAnalysis
from shared.logging_config import get_logger

logger = get_logger("page_analyzer")

SNAPSHOT_DIR = Path("data/snapshots")


def _detect_page_type(url: str) -> tuple[str, str]:
    url_lower = url.lower()
    if any(p in url_lower for p in ["/user/", "passport", "login"]):
        return "登录/注册页", "未登录"
    if "zhipin.com" in url_lower:
        return "BOSS直聘页面", "已登录（推测）"
    return "未知页面", "未知"


async def _detect_captcha_elements(page: Page) -> list[str]:
    issues = []
    for sel in CAPTCHA_INDICATORS:
        try:
            if await page.query_selector(sel):
                issues.append("检测到验证码元素")
                break
        except Exception:
            continue
    return issues


async def _get_dom_structure(page: Page) -> dict:
    structure_js = f"""() => {{
        const result = {{}};
        result.has_body = !!document.body;
        result.body_len = document.body ? document.body.innerText.length : 0;
        const selectors = ['{JOB_CARD}', '{JOB_TITLE}', '{COMPANY_NAME}', '{JOB_SALARY}', '.company-info', '{DETAIL_DESC[0]}', '.boss-active-time'];
        for (const sel of selectors) {{
            try {{ const els = document.querySelectorAll(sel); result[sel] = els.length; }}
            catch(e) {{ result[sel] = 'error'; }}
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
    issues = list(await _detect_captcha_elements(page))
    try:
        body_text = await page.inner_text("body")
        for kw in ["安全验证", "滑块验证", "访问异常", "请求过于频繁", "系统繁忙"]:
            if kw in body_text:
                issues.append(f"检测到反爬文本: '{kw}'")
    except Exception:
        pass
    job_count = None
    try:
        cards = await page.query_selector_all(JOB_CARD)
        if cards is not None:
            job_count = len(cards)
    except Exception:
        pass
    try:
        detail_sel = ", ".join(DETAIL_DESC[:3])
        if await page.query_selector(detail_sel):
            page_type = "职位详情页"
    except Exception:
        pass
    dom = await _get_dom_structure(page)
    analysis = {
        "url": page.url, "title": await page.title(),
        "page_type": page_type, "login_status": login_status,
        "issues": issues, "has_issues": len(issues) > 0,
        "job_count": job_count, "dom_structure": dom,
    }
    try:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        report_path = SNAPSHOT_DIR / f"{name}_analysis.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)
        analysis["report_path"] = str(report_path)
    except Exception as e:
        logger.warning("分析报告保存失败: %s", e)
    return PageAnalysis(screenshot_path, html_snapshot, analysis)


async def quick_check(page: Page) -> dict:
    result = {"page_type": "未知", "login_status": "未知", "issues": [], "job_count": None}
    try:
        url_lower = page.url.lower()
        if any(k in url_lower for k in ["/user/", "passport", "login"]):
            result["page_type"] = "登录/注册页"
            result["login_status"] = "未登录"
        elif "zhipin.com" in url_lower:
            result["page_type"] = "BOSS直聘页面"
            result["login_status"] = "已登录（推测）"
        body_text = await page.inner_text("body")
        for kw in ["验证码", "安全验证", "访问异常"]:
            if kw in body_text:
                result["issues"].append(kw)
        cards = await page.query_selector_all(JOB_CARD)
        if cards is not None:
            result["job_count"] = len(cards)
    except Exception:
        result["issues"].append("检查过程出错")
    return result
