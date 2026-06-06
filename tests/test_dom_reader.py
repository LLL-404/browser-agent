"""DomReader 单元测试 — 使用 mock 对象，无需真实浏览器。"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.engine.dom_reader import DomReader
from shared.engine.profile import _dict_to_profile

# ── 辅助构造函数 ────────────────────────────────────────────────

def _make_mock_element(text: str = "", attr_value: str = "") -> Any:
    """构造一个 mock 元素，支持 inner_text 和 get_attribute。"""
    el = MagicMock()
    el.inner_text = AsyncMock(return_value=text)
    el.get_attribute = AsyncMock(return_value=attr_value)

    # query_selector / query_selector_all 支持嵌套子元素查询
    async def _query_selector(selector: str):
        return None  # 默认无子元素

    async def _query_selector_all(selector: str):
        return []

    el.query_selector = _query_selector
    el.query_selector_all = _query_selector_all
    return el


def _make_mock_page(url: str = "https://www.zhipin.com/web/geek/job") -> Any:
    """构造一个 mock Page 对象。"""
    page = MagicMock()
    page.url = url

    # query_selector 返回元素或 None
    page.query_selector = AsyncMock(return_value=None)
    # query_selector_all 返回列表
    page.query_selector_all = AsyncMock(return_value=[])
    return page


def _make_profile(dom_overrides: dict | None = None) -> Any:
    """用标准 DOM 配置构建测试用 Profile，支持覆盖。"""
    base: dict = {
        "meta": {"name": "test_site"},
        "navigation": {
            "home": "https://www.zhipin.com",
            "login": "https://www.zhipin.com/login",
        },
        "dom": {
            "list": {
                "card": ".job-card-box",
                "title": ".job-name",
                "title_link": ".job-card-box a",
                "company": ".company-name a",
                "salary": ".salary",
                "tags": ".tag-list li",
            },
            "pagination": {
                "next_button": ".ui-icon-arrow-right",
            },
            "detail": {
                "description": [".job-sec-text", ".job-detail-content"],
                "company": [".company-info a"],
                "recruiter_active": [".recruiter-status"],
                "panel_salary": ".detail-salary",
            },
            "captcha": {
                "indicators": [".verify-img", "#captcha-modal"],
                "keywords": ["验证码", "滑动验证"],
            },
            "login": {
                "user_menu": ".user-menu",
                "page_auth_patterns": ["/login", "/passport"],
                "text_positive": ["已登录", "欢迎"],
                "text_negative": ["请登录", "立即登录"],
            },
        },
    }
    if dom_overrides:
        base["dom"].update(dom_overrides)
    return _dict_to_profile(base)


# ── TestParseCard ────────────────────────────────────────────────

class TestParseCard:
    """卡片解析测试：正常字段、空卡片、相对路径补全、job_id 提取。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.profile = _make_profile()
        self.reader = DomReader(self.profile)

    async def test_normal_card_parsing(self):
        """正常卡片应正确解析所有字段（title/company/salary/tags/href/job_id）。"""
        card = _make_mock_element()

        # 配置 card 内部各子选择器的 mock 返回值
        async def _card_query_selector(selector: str):
            sel_map = {
                ".job-name": _make_mock_element(text="Python 工程师"),
                ".job-card-box a": _make_mock_element(
                    text="Python 工程师",
                    attr_value="/job_detail/abc123.json",
                ),
                ".company-name a": _make_mock_element(text="某科技公司"),
                ".salary": _make_mock_element(text="20K-35K"),
                ".tag-list li": None,  # tags 用 query_selector_all
            }
            return sel_map.get(selector)

        async def _card_query_selector_all(selector: str):
            if selector == ".tag-list li":
                return [
                    _make_mock_element(text="Python"),
                    _make_mock_element(text="Django"),
                ]
            return []

        card.query_selector = _card_query_selector
        card.query_selector_all = _card_query_selector_all

        page = _make_mock_page()
        result = await self.reader.parse_card(card, page)

        assert result["title"] == "Python 工程师"
        assert result["company"] == "某科技公司"
        assert result["salary"] == "20K-35K"
        assert result["tags"] == ["Python", "Django"]
        assert result["href"] == "https://www.zhipin.com/job_detail/abc123.json"
        assert result["job_id"] == "abc123"

    async def test_empty_card_returns_defaults(self):
        """空卡片（无任何子元素）应返回空字符串默认值。"""
        card = _make_mock_element()  # 内部查询全部返回 None
        page = _make_mock_page()
        result = await self.reader.parse_card(card, page)

        assert result["title"] == ""
        assert result["company"] == ""
        assert result["salary"] == ""
        assert result["tags"] == []
        assert result["href"] == ""
        assert result["job_id"] == ""

    async def test_relative_href_completed_to_full_url(self):
        """相对路径 href 应使用 navigation.home 作为 base 补全。"""
        card = _make_mock_element()

        async def _qs(selector: str):
            if selector == ".job-card-box a":
                return _make_mock_element(
                    text="测试职位",
                    attr_value="/job_detail/xyz789.json",
                )
            return None

        card.query_selector = _qs
        page = _make_mock_page()
        result = await self.reader.parse_card(card, page)

        assert result["href"] == "https://www.zhipin.com/job_detail/xyz789.json"
        assert result["job_id"] == "xyz789"

    async def test_absolute_href_unchanged(self):
        """绝对路径 href 不应被修改。"""
        card = _make_mock_element()

        async def _qs(selector: str):
            if selector == ".job-card-box a":
                return _make_mock_element(
                    text="远程职位",
                    attr_value="https://www.zhipin.com/job_detail/remote001.json",
                )
            return None

        card.query_selector = _qs
        page = _make_mock_page()
        result = await self.reader.parse_card(card, page)

        assert result["href"] == "https://www.zhipin.com/job_detail/remote001.json"
        assert result["job_id"] == "remote001"

    async def test_job_id_extraction_from_href(self):
        """job_id 应通过正则 job_detail/([a-zA-Z0-9]+) 从 href 提取。"""
        card = _make_mock_element()

        async def _qs(selector: str):
            if selector == ".job-card-box a":
                return _make_mock_element(
                    attr_value="https://www.zhipin.com/job_detail/AlphaBeta99.json"
                )
            return None

        card.query_selector = _qs
        page = _make_mock_page()
        result = await self.reader.parse_card(card, page)

        assert result["job_id"] == "AlphaBeta99"


# ── TestCaptchaDetection ─────────────────────────────────────────

class TestCaptchaDetection:
    """验证码检测测试：选择器命中、关键词命中、无验证码。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.profile = _make_profile()
        self.reader = DomReader(self.profile)

    async def test_detected_by_css_indicator(self):
        """CSS 指示器命中时应返回 True。"""
        page = _make_mock_page()

        # .verify-img 命中
        call_count = [0]

        async def _qs(selector: str):
            call_count[0] += 1
            if selector == ".verify-img":
                return _make_mock_element()  # 命中
            if selector == "#captcha-modal":
                return None
            if selector == "body":
                return _make_mock_element(text="正常页面内容")
            return None

        page.query_selector = _qs
        result = await self.reader.detect_captcha(page)
        assert result is True

    async def test_detected_by_body_keyword(self):
        """body 文本包含关键词时应返回 True（即使 CSS 选择器未命中）。"""
        page = _make_mock_page()

        async def _qs(selector: str):
            if selector in (".verify-img", "#captcha-modal"):
                return None  # CSS 指示器均未命中
            if selector == "body":
                return _make_mock_element(text="请完成滑动验证后继续")
            return None

        page.query_selector = _qs
        result = await self.reader.detect_captcha(page)
        assert result is True

    async def test_no_captcha_when_clean(self):
        """页面干净（无指示器、无关键词）时应返回 False。"""
        page = _make_mock_page()

        async def _qs(selector: str):
            if selector in (".verify-img", "#captcha-modal"):
                return None
            if selector == "body":
                return _make_mock_element(text="职位列表页面")
            return None

        page.query_selector = _qs
        result = await self.reader.detect_captcha(page)
        assert result is False

    async def test_no_captcha_config_returns_false(self):
        """captcha 配置为空时始终返回 False。"""
        empty_profile = _make_profile(dom_overrides={
            "captcha": {"indicators": [], "keywords": []}
        })
        reader = DomReader(empty_profile)
        page = _make_mock_page()
        result = await reader.detect_captcha(page)
        assert result is False


# ── TestLoginDetection ───────────────────────────────────────────

class TestLoginDetection:
    """登录状态检测测试：已登录、未登录、URL 匹配、文本关键词。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.profile = _make_profile()
        self.reader = DomReader(self.profile)

    async def test_logged_in_via_user_menu(self):
        """user_menu 元素存在时应判定为已登录。"""
        page = _make_mock_page(url="https://www.zhipin.com/web/geek/job")

        async def _qs(selector: str):
            if selector == ".user-menu":
                return _make_mock_element(text="用户菜单")
            if selector == "body":
                return _make_mock_element(text="欢迎回来")
            return None

        page.query_selector = _qs
        result = await self.reader.detect_login_state(page)
        assert result is True

    async def test_not_logged_in_on_login_page(self):
        """URL 包含 login page_auth_patterns 时应判定为未登录。"""
        page = _make_mock_page(url="https://www.zhipin.com/login?redirect=/")

        async def _qs(selector: str):
            if selector == "body":
                return _make_mock_element(text="请登录以继续浏览")
            return None

        page.query_selector = _qs
        result = await self.reader.detect_login_state(page)
        assert result is False

    async def test_not_logged_in_by_negative_keyword(self):
        """页面文本含 text_negative 关键词时应判定为未登录。"""
        page = _make_mock_page(url="https://www.zhipin.com/web/geek/job")

        async def _qs(selector: str):
            if selector == ".user-menu":
                return None  # 无 user_menu
            if selector == "body":
                return _make_mock_element(text="请登录后查看完整职位信息")
            return None

        page.query_selector = _qs
        result = await self.reader.detect_login_state(page)
        assert result is False

    async def test_logged_in_by_positive_keyword(self):
        """页面文本含 text_positive 关键词且无负面信号时应判定为已登录。"""
        page = _make_mock_page(url="https://www.zhipin.com/web/geek/job")

        async def _qs(selector: str):
            if selector == ".user-menu":
                return None
            if selector == "body":
                return _make_mock_element(text="欢迎回来，张三")
            return None

        page.query_selector = _qs
        result = await self.reader.detect_login_state(page)
        assert result is True

    async def test_default_not_logged_in(self):
        """无法确定时保守返回 False（未登录）。"""
        page = _make_mock_page(url="https://www.zhipin.com/web/geek/job")

        async def _qs(selector: str):
            if selector == "body":
                return _make_mock_element(text="普通页面内容")
            return None

        page.query_selector = _qs
        result = await self.reader.detect_login_state(page)
        assert result is False


# ── TestCollectCards ──────────────────────────────────────────────

class TestCollectCards:
    """collect_cards 列表采集测试。"""

    async def test_collects_cards_with_valid_selector(self):
        """有效选择器应返回卡片列表。"""
        profile = _make_profile()
        reader = DomReader(profile)
        page = _make_mock_page()

        fake_cards = [_make_mock_element(), _make_mock_element()]
        page.query_selector_all = AsyncMock(return_value=fake_cards)

        cards = await reader.collect_cards(page)
        assert len(cards) == 2

    async def test_empty_selector_returns_empty_list(self):
        """空选择器配置应返回空列表。"""
        profile = _make_profile(dom_overrides={"list": {"card": ""}})
        reader = DomReader(profile)
        page = _make_mock_page()

        cards = await reader.collect_cards(page)
        assert cards == []


# ── TestScrapeDetail ─────────────────────────────────────────────

class TestScrapeDetail:
    """详情页采集测试：fallback 链机制。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.profile = _make_profile()
        self.reader = DomReader(self.profile)

    async def test_detail_fallback_chain_first_hit(self):
        """fallback 链中第一个有效选择器应被使用。"""
        page = _make_mock_page()

        call_log = []

        async def _qs(selector: str):
            call_log.append(selector)
            if selector == ".job-sec-text":
                return _make_mock_element(text="这是职位描述的详细内容，足够长")
            if selector == ".detail-salary":
                return _make_mock_element(text="25K-40K")
            return None

        page.query_selector = _qs
        result = await self.reader.scrape_detail(page, "https://example.com/job/1")

        assert result["description"] == "这是职位描述的详细内容，足够长"
        assert result["panel_salary"] == "25K-40K"
        assert ".job-detail-content" not in call_log  # 第一个命中后不应继续尝试

    async def test_detail_fallback_to_second_selector(self):
        """第一个选择器无效时应回退到第二个。"""
        page = _make_mock_page()

        async def _qs(selector: str):
            if selector == ".job-sec-text":
                return _make_mock_element(text="短")  # 低于 min_length=10
            if selector == ".job-detail-content":
                return _make_mock_element(text="这是完整的职位描述内容，满足长度要求")
            return None

        page.query_selector = _qs
        result = await self.reader.scrape_detail(page, "https://example.com/job/2")

        assert "完整" in result["description"]

    async def test_detail_all_selectors_fail_returns_empty(self):
        """所有选择器失败时字段应为空字符串。"""
        page = _make_mock_page()
        page.query_selector = AsyncMock(return_value=None)
        result = await self.reader.scrape_detail(page, "https://example.com/job/3")

        assert result["description"] == ""
        assert result["company"] == ""
        assert result["recruiter_active"] == ""
        assert result["panel_salary"] == ""
