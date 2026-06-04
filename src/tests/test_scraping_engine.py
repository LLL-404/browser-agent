"""ScrapingEngine 主引擎测试 — 使用 mock 对象，不启动真实浏览器。"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from shared.engine.scraping_engine import CityResult, ScrapingEngine
from shared.engine.profile import SiteProfile, FilterRule


# ── 辅助函数 ────────────────────────────────────────────────────────────────

def _make_profile(filters_yaml: list[dict] | None = None,
                  global_config: dict | None = None) -> SiteProfile:
    """构建带过滤规则和全局配置的测试用 SiteProfile。"""
    rules = []
    if filters_yaml:
        for r in filters_yaml:
            rules.append(FilterRule(
                id=r.get("id", ""),
                type=r.get("type", ""),
                field=r.get("field", ""),
                case_insensitive=r.get("case_insensitive", False),
                config_key=r.get("config_key", ""),
                source=r.get("source", ""),
                max_days_key=r.get("max_days_key", ""),
                reason_template=r.get("reason_template", ""),
            ))
    return SiteProfile(filters=rules, _global_config=global_config or {})


# ── TestCityResult ─────────────────────────────────────────────────────────

class TestCityResult:
    """CityResult 数据容器测试。"""

    def test_默认值(self):
        """默认参数应全为零/空。"""
        result = CityResult("北京")
        d = result.to_dict()
        assert d["searched"] == 0
        assert d["stored"] == 0
        assert d["skipped"] == 0
        assert d["elapsed"] == 0.0

    def test_自定义值(self):
        """传入自定义值后 to_dict 应正确反映。"""
        result = CityResult("上海", searched=50, stored=30, skipped=10, elapsed=12.5)
        d = result.to_dict()
        assert d["searched"] == 50
        assert d["stored"] == 30
        assert d["skipped"] == 10
        assert d["elapsed"] == 12.5

    def test_to_dict返回独立副本(self):
        """多次调用 to_dict 应返回相同值，且修改不影响原对象。"""
        result = CityResult("深圳", searched=1)
        d1 = result.to_dict()
        d2 = result.to_dict()
        assert d1 is not d2  # 不同实例
        assert d1 == d2     # 内容相同

    def test_city属性保留(self):
        """city 字段应作为属性可访问。"""
        result = CityResult("杭州")
        assert result.city == "杭州"


# ── TestEngineInit ──────────────────────────────────────────────────────────

class TestEngineInit:
    """引擎初始化与组件组装测试。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.profile = _make_profile()
        self.engine = ScrapingEngine(self.profile)

    def test_组件正确创建(self):
        """所有子组件应在 __init__ 中完成初始化。"""
        assert self.engine.url_builder is not None
        assert self.engine.dom_reader is not None
        assert self.engine.filter_chain is not None
        assert self.engine.report_builder is not None
        assert self.engine.adapter is not None

    def test_profile传递给各组件(self):
        """同一 profile 实例应传递给所有子组件。"""
        assert self.engine.url_builder.profile is self.profile
        assert self.engine.dom_reader._profile is self.profile
        assert self.engine.filter_chain._profile is self.profile
        assert self.engine.report_builder.profile is self.profile

    def test_url_builder类型(self):
        """url_builder 应为 UrlBuilder 实例。"""
        from shared.engine.url_builder import UrlBuilder
        assert isinstance(self.engine.url_builder, UrlBuilder)

    def test_dom_reader类型(self):
        """dom_reader 应为 DomReader 实例。"""
        from shared.engine.dom_reader import DomReader
        assert isinstance(self.engine.dom_reader, DomReader)

    def test_filter_chain类型(self):
        """filter_chain 应为 FilterChain 实例。"""
        from shared.engine.filter_chain import FilterChain
        assert isinstance(self.engine.filter_chain, FilterChain)

    def test_report_builder类型(self):
        """report_builder 应为 ReportBuilder 实例。"""
        from shared.engine.report_builder import ReportBuilder
        assert isinstance(self.engine.report_builder, ReportBuilder)

    def test_adapter类型(self):
        """adapter 应为 DefaultAdapter 实例。"""
        from shared.engine.adapter_protocol import DefaultAdapter
        assert isinstance(self.engine.adapter, DefaultAdapter)

    def test_filter_rules注入到chain(self):
        """profile.filters 中的规则应被注入到 filter_chain。"""
        rules_cfg = [
            {
                "id": "r1",
                "type": "contains_any",
                "field": "title",
                "source": "kw_list",
                "reason_template": "命中关键词: {keyword}",
            },
        ]
        profile = _make_profile(
            rules_cfg,
            global_config={"kw_list": ["实习"]},
        )
        engine = ScrapingEngine(profile)
        # 链中应有 1 条有效条目
        assert len(engine.filter_chain._entries) == 1


# ── TestFilterIntegration ───────────────────────────────────────────────────

class TestFilterIntegration:
    """filter_chain 在引擎中的集成测试 — 验证端到端过滤流程。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        rules_cfg = [
            {
                "id": "salary_r",
                "type": "salary_threshold",
                "field": "salary",
                "config_key": "pre_filters.min_salary",
                "reason_template": "薪资低于 {threshold}",
            },
            {
                "id": "blacklist_r",
                "type": "contains_any",
                "field": "title",
                "source": "blacklist_kw",
                "case_insensitive": True,
                "reason_template": "包含黑名单词: {keyword}",
            },
        ]
        self.profile = _make_profile(
            rules_cfg,
            global_config={
                "pre_filters": {"min_salary": 8000},
                "blacklist_kw": ["实习", "外包"],
            },
        )
        self.engine = ScrapingEngine(self.profile)

    def test_合法职位通过全部过滤器(self):
        """满足薪资且不含黑名单词的职位不应被跳过。"""
        job = {"title": "Python开发工程师", "salary": "15K-25K"}
        skip, reason = self.engine.filter_chain.evaluate(job)
        assert skip is False
        assert reason == ""

    def test_低薪职位被拦截(self):
        """低于薪资阈值的职位应被 salary_threshold 拦截。"""
        job = {"title": "Python工程师", "salary": "5K-7K"}
        skip, reason = self.engine.filter_chain.evaluate(job)
        assert skip is True
        assert "8000" in reason or "threshold" in reason.lower()

    def test_黑名单关键词被拦截(self):
        """标题含黑名单词的职位应被 contains_any 拦截（即使薪资达标）。"""
        job = {"title": "Java实习生", "salary": "10K-15K"}
        skip, reason = self.engine.filter_chain.evaluate(job)
        assert skip is True
        assert "实习" in reason

    def test_多条规则短路行为(self):
        """首条命中规则应立即返回，后续不再执行。"""
        # 薪资低 + 标题含黑名单 → salary_threshold 先命中（规则顺序优先）
        job = {"title": "销售实习生", "salary": "3K-5K"}
        skip, reason = self.engine.filter_chain.evaluate(job)
        assert skip is True
        # 第一条是 salary_threshold 规则，应因薪资原因被拦截
        assert "8000" in reason or "threshold" in reason.lower()

    def test_空过滤器链全部通过(self):
        """无过滤规则的引擎应对任何职位放行。"""
        empty_profile = _make_profile([])
        empty_engine = ScrapingEngine(empty_profile)
        job = {"title": "任意职位", "salary": "0K"}
        skip, reason = empty_engine.filter_chain.evaluate(job)
        assert skip is False

    @pytest.mark.asyncio
    async def test_engine_check_login委托给dom_reader(self):
        """_check_login 方法应委托给 dom_reader.detect_login_state。"""
        mock_page = MagicMock()
        self.engine.dom_reader.detect_login_state = AsyncMock(return_value=True)

        result = await self.engine._check_login(mock_page)
        assert result is True
        self.engine.dom_reader.detect_login_state.assert_called_once_with(mock_page)

    @pytest.mark.asyncio
    async def test_engine_check_login未登录(self):
        """detect_login_state 返回 False 时 _check_login 也应返回 False。"""
        mock_page = MagicMock()
        self.engine.dom_reader.detect_login_state = AsyncMock(return_value=False)

        result = await self.engine._check_login(mock_page)
        assert result is False
