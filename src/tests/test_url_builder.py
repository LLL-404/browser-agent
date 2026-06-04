"""UrlBuilder 单元测试 — 覆盖搜索 URL 构建、优先级排序、空模板 fallback。"""
from __future__ import annotations

import pytest

from shared.engine.profile import (
    NavigationConfig,
    SiteProfile,
    UrlTemplate,
    UrlsConfig,
)
from shared.engine.url_builder import UrlBuilder


# ── 辅助工厂：快速构造带指定配置的 SiteProfile ─────────────────────────

def _make_profile(
    home: str = "https://example.com",
    login: str = "https://example.com/login",
    search_templates: list[UrlTemplate] | None = None,
) -> SiteProfile:
    """构造用于测试的 SiteProfile 实例。"""
    return SiteProfile(
        navigation=NavigationConfig(home=home, login=login),
        urls=UrlsConfig(search=search_templates or []),
    )


# ── TestBuildSearch ───────────────────────────────────────────────────────


class TestBuildSearch:
    """build_search() 的各种场景。"""

    def test_single_template(self):
        """单模板应正确格式化 city_code 与 keyword。"""
        profile = _make_profile(search_templates=[
            UrlTemplate(template="/s?city={city_code}&q={keyword}", priority=1),
        ])
        builder = UrlBuilder(profile)
        url = builder.build_search("101", "python")
        assert url == "https://example.com/s?city=101&q=python"

    def test_multiple_templates_uses_highest_priority(self):
        """多模板时应取 priority 最小的（最高优先级）。"""
        profile = _make_profile(search_templates=[
            UrlTemplate(template="/api/v2?c={city_code}&k={keyword}", priority=2),
            UrlTemplate(template="/web/search?c={city_code}&k={keyword}", priority=1),
        ])
        builder = UrlBuilder(profile)
        url = builder.build_search("102", "golang")
        assert url == "https://example.com/web/search?c=102&k=golang"

    def test_specified_priority(self):
        """显式传入 priority 时应匹配对应模板，找不到则 fallback 到最高优先级。"""
        profile = _make_profile(search_templates=[
            UrlTemplate(template="/p1?c={city_code}&k={keyword}", priority=1),
            UrlTemplate(template="/p3?c={city_code}&k={keyword}", priority=3),
            UrlTemplate(template="/p2?c={city_code}&k={keyword}", priority=2),
        ])
        builder = UrlBuilder(profile)

        # 匹配到 priority=2
        url = builder.build_search("103", "rust", priority=2)
        assert url == "https://example.com/p2?c=103&k=rust"

        # 请求不存在的 priority，应 fallback 到 priority=1
        url_fallback = builder.build_search("103", "rust", priority=99)
        assert url_fallback == "https://example.com/p1?c=103&k=rust"

    def test_empty_templates_fallback(self):
        """search 模板列表为空时使用默认 URL 格式。"""
        profile = _make_profile(search_templates=[])
        builder = UrlBuilder(profile)
        url = builder.build_search("104", "java")
        assert url == "https://example.com/web/search?city=104&query=java"


# ── TestGetAllSearchUrls ──────────────────────────────────────────────────


class TestGetAllSearchUrls:
    """get_all_search_urls() 应按 priority 升序返回所有 URL。"""

    def test_sorted_by_priority(self):
        """返回结果必须按 priority 从小到大排列。"""
        profile = _make_profile(search_templates=[
            UrlTemplate(template="/b?c={city_code}&k={keyword}", priority=5),
            UrlTemplate(template="/a?c={city_code}&k={keyword}", priority=1),
            UrlTemplate(template="/c?c={city_code}&k={keyword}", priority=10),
        ])
        builder = UrlBuilder(profile)
        results = builder.get_all_search_urls("200", "dev")

        priorities = [r[0] for r in results]
        assert priorities == [1, 5, 10]

        urls = [r[1] for r in results]
        assert urls[0] == "https://example.com/a?c=200&k=dev"
        assert urls[1] == "https://example.com/b?c=200&k=dev"
        assert urls[2] == "https://example.com/c?c=200&k=dev"

    def test_empty_returns_empty_list(self):
        """无模板时返回空列表。"""
        profile = _make_profile(search_templates=[])
        builder = UrlBuilder(profile)
        assert builder.get_all_search_urls("200", "x") == []


# ── TestHomeAndLoginUrls ──────────────────────────────────────────────────


class TestHomeAndLoginUrls:
    """get_home_url / get_login_url 应原样返回 Profile 中配置的地址。"""

    def test_home_url(self):
        profile = _make_profile(
            home="https://my.site.com/",
            login="https://auth.my.site.com",
        )
        builder = UrlBuilder(profile)
        assert builder.get_home_url() == "https://my.site.com/"

    def test_login_url(self):
        profile = _make_profile(
            home="https://my.site.com",
            login="https://auth.my.site.com/sso",
        )
        builder = UrlBuilder(profile)
        assert builder.get_login_url() == "https://auth.my.site.com/sso"
