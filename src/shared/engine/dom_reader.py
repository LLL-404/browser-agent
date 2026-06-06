"""DOM 读取器 — 基于 Profile.dom 配置驱动，零硬编码选择器。

所有 CSS 选择器均来自 SiteProfile.dom 配置，
通过 fallback 链机制保证不同站点结构的兼容性。
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from shared.engine.profile import SiteProfile


class DomReader:
    """声明式 DOM 读取器 — 所有选择器来自 Profile.dom 配置。"""

    # 从 href 中提取 boss_job_id 的正则
    _RE_JOB_ID = re.compile(r"job_detail/([a-zA-Z0-9]+)")

    def __init__(self, profile: SiteProfile) -> None:
        self._profile = profile
        self._dom = profile.dom
        self._home = profile.navigation.home

    # ── 公开方法：列表采集 ─────────────────────────────────────

    async def collect_cards(self, page: Any) -> list[Any]:
        """用 dom.list.card 选择器采集卡片元素列表。"""
        selector = self._dom.list.card
        if not selector:
            return []
        return await page.query_selector_all(selector)

    async def parse_card(self, card: Any, _page: Any) -> dict[str, Any]:
        """用 dom.list.* 选择器解析单张卡片字段。

        返回字典包含：title, company, salary, tags, href, job_id
        """
        lst = self._dom.list

        title = await self._safe_text(card, lst.title)

        # href 优先从 title_link 取，回退到 card 内首个 <a>
        href = ""
        if lst.title_link:
            href = await self._safe_attr(card, lst.title_link, "href") or ""
        if not href:
            href = await self._safe_attr(card, "a", "href") or ""

        # 相对路径补全为完整 URL
        if href and not href.startswith(("http://", "https://", "//")):
            href = urljoin(self._home, href)

        # 从 href 正则提取 job_id
        job_id = ""
        if href:
            m = self._RE_JOB_ID.search(href)
            if m:
                job_id = m.group(1)

        return {
            "title": title,
            "company": await self._safe_text(card, lst.company),
            "salary": await self._safe_text(card, lst.salary),
            "tags": await self._safe_texts(card, lst.tags) if lst.tags else [],
            "href": href,
            "job_id": job_id,
        }

    # ── 公开方法：详情采集 ─────────────────────────────────────

    async def scrape_detail(self, page: Any, url: str) -> dict[str, Any]:
        """用 dom.detail.* 选择器提取详情页字段。

        每个字段都有 fallback 链（detail.description 是选择器列表），
        按配置顺序依次尝试直到命中有效结果。
        """
        detail_cfg = self._dom.detail

        description = await self._try_selectors(
            page, detail_cfg.description, min_length=10
        )
        company = await self._try_selectors(
            page, detail_cfg.company, min_length=1
        )
        recruiter_active = await self._try_selectors(
            page, detail_cfg.recruiter_active, min_length=1
        )
        panel_salary = ""
        if detail_cfg.panel_salary:
            el = await page.query_selector(detail_cfg.panel_salary)
            if el:
                panel_salary = await el.inner_text() or ""

        return {
            "url": url,
            "description": description,
            "company": company,
            "recruiter_active": recruiter_active,
            "panel_salary": panel_salary,
        }

    # ── 公开方法：状态检测 ─────────────────────────────────────

    async def detect_captcha(self, page: Any) -> bool:
        """基于 dom.captcha 配置检测验证码（选择器 + 关键词双重检测）。

        先检查 indicators 中的 CSS 选择器是否命中页面元素，
        再检查 body 文本中是否包含 keywords 关键词。
        """
        captcha_cfg = self._dom.captcha

        # 第一层：CSS 选择器指示器
        for indicator in captcha_cfg.indicators:
            el = await page.query_selector(indicator)
            if el is not None:
                return True

        # 第二层：body 文本关键词匹配
        if captcha_cfg.keywords:
            body_el = await page.query_selector("body")
            if body_el:
                body_text = await body_el.inner_text() or ""
                for kw in captcha_cfg.keywords:
                    if kw in body_text:
                        return True

        return False

    async def detect_login_state(self, page: Any) -> bool:
        """基于 dom.login 配置检测登录状态。

        检查逻辑：
        1. 当前 URL 是否在 login.page_auth_patterns 中 → 未登录
        2. user_menu 元素是否存在 → 存在则已登录
        3. 页面文本是否包含 text_negative 关键词 → 未登录
        4. 页面文本是否包含 text_positive 关键词 → 已登录
        """
        login_cfg = self._dom.login
        current_url = page.url or ""

        # 1) URL 命中认证页模式 → 判定未登录
        for pattern in login_cfg.page_auth_patterns:
            if pattern and pattern in current_url:
                return False

        # 2) user_menu 元素存在 → 已登录
        if login_cfg.user_menu:
            menu_el = await page.query_selector(login_cfg.user_menu)
            if menu_el is not None:
                return True

        # 3/4) 文本关键词判断
        body_el = await page.query_selector("body")
        body_text = ""
        if body_el:
            body_text = await body_el.inner_text() or ""

        # 负面关键词优先级更高（明确表示未登录）
        for kw in login_cfg.text_negative:
            if kw and kw in body_text:
                return False

        for kw in login_cfg.text_positive:
            if kw and kw in body_text:
                return True

        # 无法确定时默认未登录（保守策略）
        return False

    # ── 内部工具方法 ───────────────────────────────────────────

    @staticmethod
    async def _safe_text(element: Any, selector: str) -> str:
        """安全查询子元素文本，查询失败返回空字符串。"""
        if not selector or not element:
            return ""
        try:
            el = await element.query_selector(selector)
            if el:
                return await el.inner_text() or ""
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        return ""

    @staticmethod
    async def _safe_texts(element: Any, selector: str) -> list[str]:
        """安全查询多个子元素文本列表，查询失败返回空列表。"""
        if not selector or not element:
            return []
        try:
            elements = await element.query_selector_all(selector)
            results = []
            for el in elements:
                text = await el.inner_text()
                if text:
                    results.append(text.strip())
            return results
        except Exception:  # pylint: disable=broad-exception-caught
            return []

    @staticmethod
    async def _safe_attr(element: Any, selector: str, attr: str) -> str:
        """安全查询子元素属性值，查询失败返回空字符串。"""
        if not selector or not element:
            return ""
        try:
            el = await element.query_selector(selector)
            if el:
                val = await el.get_attribute(attr)
                return val or ""
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        return ""

    async def _try_selectors(
        self, page: Any, selectors: list[str], min_length: int = 1
    ) -> str:
        """按配置的选择器列表顺序尝试，返回第一个有效结果。

        Args:
            page: Playwright Page 对象
            selectors: 选择器列表（fallback 链）
            min_length: 文本最小有效长度阈值

        Returns:
            命中的文本内容，全部失败返回空字符串
        """
        for sel in selectors:
            if not sel:
                continue
            try:
                el = await page.query_selector(sel)
                if el:
                    text = await el.inner_text() or ""
                    if len(text.strip()) >= min_length:
                        return text.strip()
            except Exception:  # pylint: disable=broad-exception-caught
                continue
        return ""
