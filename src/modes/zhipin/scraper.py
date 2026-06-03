"""核心爬取模块，负责浏览器自动化搜索、列表采集、详情抓取和报告生成。"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Dict

from playwright.async_api import async_playwright, Page

from modes.zhipin.city_codes import get_city_code, get_rent_reference
from shared.config import get_config
from shared.logging_config import get_logger
from modes.zhipin.selectors import (
    JOB_CARD, JOB_TITLE, JOB_TITLE_LINK, COMPANY_NAME, JOB_SALARY, JOB_TAGS,
    NEXT_PAGE_BUTTONS,
    DETAIL_DESC, DETAIL_COMPANY, DETAIL_ACTIVE, DETAIL_PANEL_SALARY,
    CAPTCHA_INDICATORS, CAPTCHA_KEYWORDS,
    LOGIN_USER_MENU, LOGIN_PAGE_AUTH, LOGIN_TEXT_POSITIVE, LOGIN_TEXT_NEGATIVE,
)
from modes.zhipin.storage import (
    init_db, insert_job, update_search_log, get_searched_cities,
    get_unanalyzed_jobs, get_jobs, get_job_by_id,
    batch_update_jobs, JobQuery, get_stats,
)
from modes.zhipin.pre_filter import should_skip_job
from modes.zhipin.keyword_strategy import get_keywords_for_city, get_initial_keyword
from agent.core.anti_detect import (
    random_delay, human_scroll, ANTI_REDIRECT_SCRIPT,
    STEALTH_SCRIPT, build_browser_kwargs,
)
from modes.zhipin.page_analyzer import analyze_page, quick_check
from shared.retry import retry_async

_PLAYWRIGHT_ERRORS = (Exception,)

logger = get_logger("scraper")

__all__ = [
    # 核心功能
    "search_jobs", "analyze_jobs", "import_analysis",
    "generate_report", "generate_chat_prompt", "health_check",
    # 登录与验证
    "is_logged_in", "wait_for_login",
    # 内部工具（供测试使用）
    "_detect_captcha", "_wait_captcha", "_goto_search",
    "_collect_list_page", "_scrape_detail",
]


async def _detect_captcha(page: Page) -> bool:
    for sel in CAPTCHA_INDICATORS:
        try:
            if await page.query_selector(sel):
                return True
        except _PLAYWRIGHT_ERRORS:
            continue
    try:
        page_text = await page.inner_text("body")
        if any(kw in page_text for kw in CAPTCHA_KEYWORDS):
            return True
    except _PLAYWRIGHT_ERRORS:
        pass
    return False


async def _wait_captcha(page: Page):
    cfg: Dict[str, Any] = get_config()
    pause_minutes = cfg.get("runtime", {}).get("captcha_pause_minutes", 5)
    logger.warning("检测到验证码，请在浏览器中手动完成验证。等待 %d 分钟...", pause_minutes)
    for _ in range(pause_minutes * 60, 0, -10):
        await asyncio.sleep(10)
        if not await _detect_captcha(page):
            logger.info("验证码已解除")
            return
    logger.warning("验证码等待超时")


async def is_logged_in(page: Page) -> bool:
    url_lower = page.url.lower()
    if any(p in url_lower for p in LOGIN_PAGE_AUTH) or "about:blank" in url_lower:
        return False
    try:
        body_text = await page.inner_text("body")
        if any(kw in body_text for kw in LOGIN_TEXT_NEGATIVE):
            if any(kw in body_text for kw in LOGIN_TEXT_POSITIVE):
                return True
            return False
        user_menu = await page.query_selector(LOGIN_USER_MENU)
        if user_menu:
            return True
    except _PLAYWRIGHT_ERRORS:
        pass
    return len(url_lower) > 20 and "zhipin.com" in url_lower


async def wait_for_login(page: Page, timeout: int = 300) -> bool:
    logger.info("请在浏览器中登录 BOSS 直聘（扫码/验证码）")
    try:
        async with asyncio.timeout(timeout):
            while True:
                await asyncio.sleep(2)
                current = page.url.lower()
                if "/user/" not in current and "passport" not in current:
                    logger.info("登录成功")
                    return True
    except asyncio.TimeoutError:
        logger.error("登录超时（5分钟）")
        return False


async def _goto_search(page: Page, city: str, keyword: str, max_retries: int = 2):
    city_code = get_city_code(city)
    if not city_code:
        raise ValueError(f"未知城市: {city}")
    url = f"https://www.zhipin.com/web/geek/job?city={city_code}&query={keyword}"

    for attempt in range(max_retries + 1):
        try:
            await page.goto(url, wait_until="networkidle", timeout=20000)
            if "about:blank" not in page.url:
                cfg: Dict[str, Any] = get_config()
                analysis_cfg = cfg.get("page_analysis", {})
                if analysis_cfg.get("enabled", True):
                    check = await quick_check(page)
                    if check["issues"]:
                        logger.warning("页面异常: %s", ", ".join(check["issues"]))
                        analysis = await analyze_page(page, name="anomaly")
                        logger.info("%s", analysis.summary())
                return
        except _PLAYWRIGHT_ERRORS:
            pass
        if attempt < max_retries:
            await asyncio.sleep(1)


async def _extract_salary(card, page: Page | None) -> str:
    salary_el = await card.query_selector(JOB_SALARY)
    if salary_el:
        salary_text = (await salary_el.inner_text()).strip()
        if salary_text:
            return salary_text
    salary_text = await card.evaluate(f"""el => {{
        const s = el.querySelector('{JOB_SALARY}');
        if (!s) return '';
        return (s.textContent || '').trim();
    }}""")
    if salary_text:
        return salary_text
    if page:
        panel_salary = await page.evaluate(f"""() => {{
            const panel = document.querySelector('{DETAIL_PANEL_SALARY}');
            return panel ? panel.textContent.trim() : '';
        }}""")
        if panel_salary:
            return panel_salary
    card_html = await card.evaluate("el => el.outerHTML")
    m = re.search(r'(\d+K?-?\d*K?)', card_html)
    if m:
        return m.group(1)
    return ""


async def _parse_list_card(card, city: str, page: Page | None = None) -> dict | None:
    try:
        await card.hover()
        await asyncio.sleep(0.5)

        title_el = await card.query_selector(JOB_TITLE)
        company_el = await card.query_selector(COMPANY_NAME)
        tag_els = await card.query_selector_all(JOB_TAGS)
        link_el = await card.query_selector(JOB_TITLE_LINK)

        title = (await title_el.inner_text()).strip() if title_el else ""
        company = (await company_el.inner_text()).strip() if company_el else ""
        tags = [(await t.inner_text()).strip() for t in tag_els]
        href = (await link_el.get_attribute("href")) if link_el else ""
        if href and not href.startswith("http"):
            href = "https://www.zhipin.com" + href

        salary_text = await _extract_salary(card, page)

        boss_job_id = None
        if href:
            m = re.search(r'job_detail/([a-zA-Z0-9]+)', href)
            boss_job_id = m.group(1) if m else None

        return {
            "boss_job_id": boss_job_id,
            "title": title,
            "company": company,
            "salary": salary_text,
            "city": city,
            "tags": tags,
            "location": "",
            "recruiter_active": "",
            "job_url": href,
        }
    except _PLAYWRIGHT_ERRORS:
        return None


async def _collect_list_page(page: Page, city: str) -> list[dict]:
    cfg: Dict[str, Any] = get_config()
    max_pages = cfg.get("runtime", {}).get("max_list_pages", 5)
    all_jobs: list[dict] = []

    for page_num in range(max_pages):
        try:
            await page.wait_for_selector(JOB_CARD, timeout=5000)
            cards = await page.query_selector_all(JOB_CARD)
            for card in cards:
                job_data = await _parse_list_card(card, city, page)
                if job_data:
                    all_jobs.append(job_data)

            if page_num < max_pages - 1:
                next_btn = await page.query_selector(NEXT_PAGE_BUTTONS)
                if next_btn:
                    cls = await next_btn.get_attribute("class") or ""
                    if "disabled" in cls:
                        break
                    await next_btn.click()
                    await random_delay((2, 4))
                else:
                    break
        except _PLAYWRIGHT_ERRORS:
            break

    return all_jobs


async def _scrape_detail(page: Page, job_url: str) -> dict[str, str]:
    result: dict[str, str] = {"description": "", "company_info": "", "recruiter_active": ""}
    try:
        await retry_async(
            page.goto, job_url,
            wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(1)

        for sel in DETAIL_DESC:
            try:
                el = await page.wait_for_selector(sel, timeout=3000)
                text = (await el.inner_text()).strip()
                if text and len(text) > 20:
                    result["description"] = text
                    break
            except _PLAYWRIGHT_ERRORS:
                continue

        for sel in DETAIL_COMPANY:
            try:
                el = await page.wait_for_selector(sel, timeout=3000)
                text = (await el.inner_text()).strip()
                if text and len(text) > 10:
                    result["company_info"] = text
                    break
            except _PLAYWRIGHT_ERRORS:
                continue

        for sel in DETAIL_ACTIVE:
            try:
                el = await page.wait_for_selector(sel, timeout=3000)
                text = (await el.inner_text()).strip()
                if text:
                    result["recruiter_active"] = text
                    break
            except _PLAYWRIGHT_ERRORS:
                continue

    except _PLAYWRIGHT_ERRORS:
        pass
    return result


async def _create_browser_context(p, cfg: dict, headless: bool):
    kwargs = build_browser_kwargs(cfg, headless)
    return await p.chromium.launch_persistent_context(**kwargs)


async def _ensure_login(page: Page) -> bool:
    await page.goto("https://www.zhipin.com/", wait_until="domcontentloaded")
    await asyncio.sleep(2)

    url_lower = page.url.lower()
    body_text = ""
    try:
        body_text = await page.inner_text("body")
    except _PLAYWRIGHT_ERRORS:
        pass

    is_login_page = any(p in url_lower for p in LOGIN_PAGE_AUTH)
    has_login_text = "扫码" in body_text or "验证码登录" in body_text

    if is_login_page or has_login_text:
        logger.info("登录已过期，请重新登录")
        logged_in = await wait_for_login(page)
        if not logged_in:
            return False
    return True


async def _process_job_entry(page, j: dict,
                             city_stored: int,
                             quick_mode: bool = True,
                             detail_sem: asyncio.Semaphore | None = None) -> int:
    skip, _ = should_skip_job(
        j["title"], j["company"], j["salary"],
        j["tags"], j["recruiter_active"])
    if skip:
        return city_stored

    if quick_mode:
        if insert_job(j):
            return city_stored + 1
        return city_stored

    if detail_sem:
        async with detail_sem:
            detail = await _scrape_detail(page, j["job_url"])
    else:
        detail = await _scrape_detail(page, j["job_url"])
    j.update(detail)
    if insert_job(j):
        return city_stored + 1
    return city_stored


async def _search_one_city(page, city: str, keywords: list[str] | None,
                           max_detail: int,
                           detail_sem: asyncio.Semaphore | None = None) -> dict[str, int | float]:
    city_stored: int = 0
    city_skipped: int = 0
    city_searched: int = 0
    t_start: float = time.time()

    update_search_log(city, "in_progress")

    if keywords is None:
        probe_kw = get_initial_keyword()
        await _goto_search(page, city, probe_kw)
        await human_scroll(page)
        initial_jobs = await _collect_list_page(page, city)
        city_keywords = get_keywords_for_city(city, len(initial_jobs))
        city_keywords = [k for k in city_keywords if k != probe_kw]

        for j in initial_jobs:
            prev = city_stored
            city_stored = await _process_job_entry(page, j, city_stored, detail_sem=detail_sem)
            if city_stored > prev:
                city_searched += 1
            else:
                city_skipped += 1
            if city_stored >= max_detail:
                break
    else:
        city_keywords = keywords

    for kw in city_keywords:
        if city_stored >= max_detail:
            break
        await _goto_search(page, city, kw)
        await human_scroll(page)
        jobs = await _collect_list_page(page, city)
        city_searched += len(jobs)

        for j in jobs:
            if city_stored >= max_detail:
                break
            prev = city_stored
            city_stored = await _process_job_entry(page, j, city_stored, detail_sem=detail_sem)
            if city_stored == prev:
                city_skipped += 1

        await random_delay()

    elapsed = time.time() - t_start
    update_search_log(city, "done", city_stored)

    return {
        "searched": city_searched,
        "stored": city_stored,
        "skipped": city_skipped,
        "elapsed": elapsed,
    }


async def search_jobs(cities: list[str] | None = None,
                      keywords: list[str] | None = None,
                      max_detail: int | None = None,
                      headless: bool = False,
                      concurrent: bool = True) -> dict:
    """搜索职位（核心入口函数，带性能监控）。"""
    cfg: Dict[str, Any] = get_config()
    init_db()

    if max_detail is None:
        max_detail = cfg.get("runtime", {}).get("max_detail_pages_per_city", 30)

    if cities is None:
        searched = get_searched_cities()
        all_cities: list[str] = []
        for p in ["priority_1", "priority_2", "priority_3", "priority_4"]:
            for c in cfg.get("cities", {}).get(p, []):
                if c not in searched:
                    all_cities.append(c)
        cities = all_cities[:cfg.get("runtime", {}).get("cities_per_session", 3)]

    if not cities:
        return {"error": "没有需要搜索的城市（所有城市已完成）"}

    result: dict[str, object | dict] = {}
    total_start = time.time()

    async with async_playwright() as p:
        context = await _create_browser_context(p, cfg, headless)
        await context.add_init_script(STEALTH_SCRIPT)
        await context.add_init_script(ANTI_REDIRECT_SCRIPT)
        first_page = context.pages[0] if context.pages else await context.new_page()

        try:
            if not await _ensure_login(first_page):
                return {"error": "登录超时，请重试"}

            total: int = len(cities)
            detail_sem: asyncio.Semaphore = asyncio.Semaphore(2)

            if concurrent and total > 1:
                pages: list[object] = [first_page]
                for _ in range(total - 1):
                    pages.append(await context.new_page())

                async def _search(city: str, page) -> dict[str, object | int | float]:
                    try:
                        logger.info("[并发] %s 搜索中...", city)
                        await _goto_search(page, city,
                                          get_initial_keyword() if keywords is None else keywords[0])
                        await asyncio.sleep(0.5)
                        stats = await _search_one_city(page, city, keywords, max_detail, detail_sem)
                        logger.info(
                            "[并发] %s | 搜到 %d 条 | 入库 %d 条 | 耗时 %.0f秒",
                            city, stats["searched"], stats["stored"], stats["elapsed"])
                        return stats
                    except _PLAYWRIGHT_ERRORS as e:
                        logger.error("[并发] %s 搜索异常: %s", city, e)
                        return {
                            "error": str(e), "searched": 0,
                            "stored": 0, "skipped": 0, "elapsed": 0,
                        }

                sem = asyncio.Semaphore(5)
                async def _bounded(city, page):
                    async with sem:
                        return await _search(city, page)
                tasks = [_bounded(city, page) for city, page in zip(cities, pages)]
                results: list[dict | Exception] = await asyncio.gather(*tasks, return_exceptions=True)

                for city, r in zip(cities, results):
                    if isinstance(r, Exception):
                        result[city] = {"error": str(r), "searched": 0, "stored": 0,
                                       "skipped": 0, "elapsed": 0}
                    else:
                        result[city] = r

                # 关闭多余的页面
                for page in pages[1:]:
                    await page.close()
            else:
                for idx, city in enumerate(cities, 1):
                    logger.info("[%d/%d] %s 搜索中...", idx, total, city)
                    stats: dict[str, int | float] = await _search_one_city(
                        first_page, city, keywords, max_detail, detail_sem)
                    result[city] = stats
                    logger.info(
                        "[%d/%d] %s | 搜到 %d 条 | 入库 %d 条 | 耗时 %.0f秒",
                        idx, total, city,
                        stats["searched"], stats["stored"], stats["elapsed"])

        except _PLAYWRIGHT_ERRORS as e:
            logger.error("搜索异常: %s", e)
            result["error"] = str(e)
        finally:
            await context.close()

    total_elapsed = time.time() - total_start
    total_stored: int = sum(r.get("stored", 0) for c, r in result.items() if c != "error")
    total_searched: int = sum(r.get("searched", 0) for c, r in result.items() if c != "error")

    logger.info(
        "搜索完成 | 总耗时 %.0f秒 | 共搜到 %d 条，入库 %d 条",
        total_elapsed, total_searched, total_stored)

    return result


# === AI 分析 / 报告 / 招呼语（保持不变） ===

async def analyze_jobs() -> list[dict]:
    cfg: Dict[str, Any] = get_config()
    batch_size: int = cfg.get("runtime", {}).get("batch_size", 50)
    jobs: list[dict] = get_unanalyzed_jobs(limit=batch_size)
    for j in jobs:
        j["rent_reference"] = get_rent_reference(j.get("city", ""))
    return jobs


async def import_analysis(results: list[dict]) -> tuple[int, int]:
    return batch_update_jobs(results)


def _format_benefit(value: int, label: str) -> str:
    if value == 1:
        return f"✓ {label}"
    if value == -1:
        return f"✗ {label}"
    return f"⚠ {label}未提及"


async def generate_report(min_score: int = 6, city: str | None = None,
                          top: int | None = None) -> str:
    jobs: list[dict] = get_jobs(JobQuery(
        status="analyzed", min_score=min_score, city=city,
        limit=top or 100, exclude_ignored=True))

    if not jobs:
        return "暂无符合条件的推荐职位。"

    lines = [
        "# BOSS 直聘求职推荐报告",
        f"生成时间: {__import__('datetime').datetime.now().isoformat()}",
        f"匹配分数 ≥ {min_score}",
        f"共 {len(jobs)} 条推荐职位",
        "",
    ]

    for i, j in enumerate(jobs, 1):
        benefits = [
            _format_benefit(j.get("five_insurance", 0), "五险一金"),
            _format_benefit(j.get("room_board", 0), "包食宿"),
            _format_benefit(j.get("regular_hours", 0), "朝九晚五/双休"),
        ]
        missing = []
        if j.get("five_insurance") != 1:
            missing.append("五险一金")
        if j.get("room_board") != 1:
            missing.append("包食宿")
        if j.get("regular_hours") != 1:
            missing.append("朝九晚五/双休")
        missing_text = "、".join(missing) if missing else "无"

        lines.append(
            f"### {i}. [{j['title']}]({j.get('job_url', '')}) ★{j.get('match_score', 0)}/10")
        lines.append(
            f"**{j.get('company', '')}** | {j.get('salary', '')} | {j.get('city', '')}"
            f" | 活跃: {j.get('recruiter_active', '未知')}")
        lines.append("")
        diploma_text = (
            "是" if j.get("diploma_ok") == 1
            else "否" if j.get("diploma_ok") == -1
            else "未判断")
        lines.append(f"加班风险: {j.get('overtime_risk', '未判断')} | 大专可投: {diploma_text}")
        lines.append("")
        lines.append("> " + "\n> ".join(benefits))
        lines.append("")
        if j.get("ai_reason"):
            lines.append(f"分析: {j['ai_reason']}")
            lines.append("")
        if missing_text != "无":
            lines.append(f"⚠ 缺失: {missing_text}，投递时可主动询问")
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


async def generate_chat_prompt(job_id: int) -> str | None:
    job = get_job_by_id(job_id)
    if not job:
        return None

    return f"""请为以下职位生成一条 BOSS 直聘招呼语。
要求：
- 突出自身优势（大专学历，能吃苦，稳定性好，服从安排）
- 围绕职位描述中的技能要求做简短回应
- 1-2 句话，控制在 50 字以内
- 不虚假夸大，实事求是

职位: {job.get('title', '')}
公司: {job.get('company', '')}
薪资: {job.get('salary', '')}
城市: {job.get('city', '')}
描述: {job.get('description', '')[:500]}

请直接输出招呼语，不要带引号和其他说明。"""


async def health_check() -> dict:
    """启动前健康检查：浏览器可用、BOSS直聘可访问、数据库正常。

    返回:
        {"healthy": bool, "checks": dict, "issues": list}
    """
    checks = {}
    issues = []

    # 1. 数据库检查
    try:
        init_db()
        stats = get_stats()
        checks["database"] = {"ok": True, "total_jobs": stats.get("total_jobs", 0)}
    except _PLAYWRIGHT_ERRORS as e:
        checks["database"] = {"ok": False, "error": str(e)}
        issues.append(f"数据库异常: {e}")

    # 2. 浏览器可用性检查
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            await browser.close()
        checks["browser"] = {"ok": True, "engine": "playwright"}
    except _PLAYWRIGHT_ERRORS as e:
        checks["browser"] = {"ok": False, "error": str(e)}
        issues.append(f"浏览器不可用: {e}")

    # 3. BOSS直聘可达性检查
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.zhipin.com",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            checks["network"] = {"ok": resp.status_code == 200, "status": resp.status_code}
            if resp.status_code != 200:
                issues.append(f"BOSS直聘返回状态码 {resp.status_code}")
    except Exception as e:
        checks["network"] = {"ok": False, "error": str(e)}
        issues.append(f"无法访问BOSS直聘: {e}")

    # 4. Camoufox 可用性检查
    try:
        __import__("camoufox")
        checks["camoufox"] = {"ok": True}
    except ImportError:
        checks["camoufox"] = {"ok": False, "note": "未安装，将使用 Playwright 回退"}

    healthy = all(check.get("ok", False) or "note" in check
                  for check in checks.values())
    return {"healthy": healthy, "checks": checks, "issues": issues}
