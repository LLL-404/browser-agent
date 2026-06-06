# src/shared/engine/scraping_engine.py
"""通用爬取主引擎 — 读取 SiteProfile，按声明式流程执行。"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from browser_agent.core.anti_detect import human_scroll, random_delay
from shared.delay import delay
from shared.engine.adapter_protocol import DefaultAdapter
from shared.engine.dom_reader import DomReader
from shared.engine.filter_chain import FilterChain
from shared.engine.profile import SiteProfile
from shared.engine.report_builder import ReportBuilder
from shared.engine.url_builder import UrlBuilder
from shared.logging_config import get_logger

logger = get_logger("engine")


class CityResult:
    """单城市搜索结果。"""
    def __init__(self, city: str, searched: int = 0, stored: int = 0,
                 skipped: int = 0, elapsed: float = 0):
        self.city = city
        self.searched = searched
        self.stored = stored
        self.skipped = skipped
        self.elapsed = elapsed

    def to_dict(self) -> dict:
        """将城市搜索结果转为字典格式。"""
        return {"searched": self.searched, "stored": self.stored,
                "skipped": self.skipped, "elapsed": self.elapsed}


class ScrapingEngine:
    """通用爬取引擎 — 通过 SiteProfile 驱动全部行为。"""

    def __init__(self, profile: SiteProfile):
        self.profile = profile
        self.url_builder = UrlBuilder(profile)
        self.dom_reader = DomReader(profile)
        self.filter_chain = FilterChain(profile.filters, profile)
        self.report_builder = ReportBuilder(profile)
        self.adapter = DefaultAdapter()

    async def run(self, cities=None, keywords=None, max_detail=None,
                  headless=False) -> dict[str, Any]:
        """主入口：导航 → 登录检测 → 逐城市搜索。"""
        from playwright.async_api import async_playwright  # pylint: disable=import-outside-toplevel

        from browser_agent.core.anti_detect import ANTI_REDIRECT_SCRIPT, STEALTH_SCRIPT, build_browser_kwargs  # pylint: disable=import-outside-toplevel
        from modes.zhipin.storage import get_searched_cities, init_db  # pylint: disable=import-outside-toplevel

        cfg_dict = self.profile._global_config or {}  # pylint: disable=protected-access
        init_db()

        if max_detail is None:
            max_detail = cfg_dict.get("runtime", {}).get("max_detail_pages_per_city", 30)

        if cities is None:
            searched = get_searched_cities()
            all_cities = []
            for p in ["priority_1", "priority_2", "priority_3", "priority_4"]:
                for c in cfg_dict.get("cities", {}).get(p, []):
                    if c not in searched:
                        all_cities.append(c)
            cities_per_session = cfg_dict.get("runtime", {}).get("cities_per_session", 3)
            cities = all_cities[:cities_per_session]

        if not cities:
            return {"error": "没有需要搜索的城市"}

        result = {}
        total_start = time.time()

        async with async_playwright() as p:
            kwargs = build_browser_kwargs(cfg_dict, headless)
            context = await p.chromium.launch_persistent_context(**kwargs)
            await context.add_init_script(STEALTH_SCRIPT)
            await context.add_init_script(ANTI_REDIRECT_SCRIPT)
            first_page = context.pages[0] if context.pages else await context.new_page()

            try:
                await first_page.goto(self.url_builder.get_home_url(),
                                      wait_until="domcontentloaded")
                await delay("login_wait")

                if not await self._check_login(first_page):
                    logger.info("等待用户登录...")
                    await self._wait_for_login(first_page)

                for idx, city in enumerate(cities, 1):
                    logger.info("[%d/%d] %s 搜索中...", idx, len(cities), city)
                    stats = await self._search_city(
                        first_page, city, keywords, max_detail)
                    result[city] = stats.to_dict()
                    logger.info("[%d/%d] %s | 搜到 %d | 入库 %d | %.0fs",
                                idx, len(cities), city,
                                stats.searched, stats.stored, stats.elapsed)
            finally:
                await context.close()

        total_elapsed = time.time() - total_start
        total_stored = sum(r.get("stored", 0) for r in result.values() if isinstance(r, dict))
        total_searched = sum(r.get("searched", 0) for r in result.values() if isinstance(r, dict))
        logger.info("搜索完成 | %.0fs | 共搜到 %d，入库 %d",
                     total_elapsed, total_searched, total_stored)
        return result

    async def generate_report(self, *args, **kwargs) -> str:
        """委托给 ReportBuilder。"""
        from modes.zhipin.storage import JobQuery, get_jobs  # pylint: disable=import-outside-toplevel
        jobs = get_jobs(JobQuery(status="analyzed", exclude_ignored=True))
        return self.report_builder.generate(jobs, *args, **kwargs)

    async def _check_login(self, page) -> bool:
        return await self.dom_reader.detect_login_state(page)

    async def _wait_for_login(self, page, timeout: int = 300) -> bool:
        logger.info("请在浏览器中登录...")
        try:
            async with asyncio.timeout(timeout):
                while True:
                    await delay("login_poll")
                    if await self._check_login(page):
                        logger.info("登录成功")
                        return True
        except TimeoutError:
            logger.error("登录超时")
            return False

    async def _search_city(self, page, city: str, keywords,
                           max_detail: int) -> CityResult:
        from modes.zhipin.city_codes import get_city_code  # pylint: disable=import-outside-toplevel
        from modes.zhipin.keyword_strategy import get_initial_keyword  # pylint: disable=import-outside-toplevel
        from modes.zhipin.storage import insert_job, update_search_log  # pylint: disable=import-outside-toplevel

        t_start = time.time()
        stored = skipped = searched = 0
        update_search_log(city, "in_progress")

        city_code = get_city_code(city)
        if not city_code:
            return CityResult(city, elapsed=time.time() - t_start)

        search_kws = keywords if keywords else [get_initial_keyword()]

        for kw in search_kws:
            if stored >= max_detail:
                break

            # 多模板 URL fallback
            search_urls = self.url_builder.get_all_search_urls(city_code, kw)
            navigated = False
            for _prio, url in search_urls:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await delay("page_stable")
                    if "about:blank" not in page.url:
                        navigated = True
                        break
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.debug("导航失败: %s", e)
            if not navigated:
                continue

            await human_scroll(page)
            cards = await self.dom_reader.collect_cards(page)
            searched += len(cards)

            for card in cards:
                if stored >= max_detail:
                    break
                job = await self.dom_reader.parse_card(card, page)
                job["city"] = city
                skip, _ = self.filter_chain.evaluate(job)
                if skip:
                    skipped += 1
                    continue
                if insert_job(job):
                    stored += 1
            await random_delay()

        elapsed = time.time() - t_start
        update_search_log(city, "done", stored)
        return CityResult(city, searched, stored, skipped, elapsed)
