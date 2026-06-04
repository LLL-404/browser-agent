"""FilterChain 过滤链测试。"""
from __future__ import annotations

import pytest
import warnings

from shared.engine.filter_chain import (
    ContainsAnyFilter,
    FilterChain,
    InactiveDaysFilter,
    SalaryThresholdFilter,
)
from shared.engine.profile import FilterRule, SiteProfile


# ── 辅助函数 ────────────────────────────────────────────────────────────────

def _make_profile(filters_yaml: list[dict], global_config: dict | None = None) -> SiteProfile:
    """从 YAML dict 列表构建带 global_config 的 SiteProfile。"""
    rules = [
        FilterRule(
            id=r.get("id", ""),
            type=r.get("type", ""),
            field=r.get("field", ""),
            case_insensitive=r.get("case_insensitive", False),
            config_key=r.get("config_key", ""),
            source=r.get("source", ""),
            max_days_key=r.get("max_days_key", ""),
            reason_template=r.get("reason_template", ""),
        )
        for r in filters_yaml
    ]
    return SiteProfile(filters=rules, _global_config=global_config or {})


def _make_rule(**kwargs) -> FilterRule:
    """快速构造 FilterRule，未传字段使用默认值。"""
    defaults = {
        "id": "",
        "type": "",
        "field": "",
        "case_insensitive": False,
        "config_key": "",
        "source": "",
        "max_days_key": "",
        "reason_template": "",
    }
    defaults.update(kwargs)
    return FilterRule(**defaults)


# ── TestSalaryThresholdFilter ──────────────────────────────────────────────

class TestSalaryThresholdFilter:
    """薪资下限过滤器测试。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.filt = SalaryThresholdFilter()
        self.profile = _make_profile([], global_config={"pre_filters": {"min_salary": 8000}})

    def test_低于阈值跳过(self):
        rule = _make_rule(
            type="salary_threshold",
            field="salary",
            config_key="pre_filters.min_salary",
            reason_template="薪资低于 {threshold}，已过滤",
        )
        job = {"salary": "5K-7K"}
        skip, reason = self.filt.check(job, rule, self.profile)
        assert skip is True
        assert "8000" in reason

    def test_高于阈值通过(self):
        rule = _make_rule(
            type="salary_threshold",
            field="salary",
            config_key="pre_filters.min_salary",
            reason_template="薪资低于 {threshold}，已过滤",
        )
        job = {"salary": "10K-15K"}
        skip, reason = self.filt.check(job, rule, self.profile)
        assert skip is False

    def test_无薪资信息通过(self):
        rule = _make_rule(
            type="salary_threshold",
            field="salary",
            config_key="pre_filters.min_salary",
            reason_template="薪资低于 {threshold}，已过滤",
        )
        job = {"salary": ""}
        skip, reason = self.filt.check(job, rule, self.profile)
        assert skip is False

    def test_刚好等于阈值通过(self):
        rule = _make_rule(
            type="salary_threshold",
            field="salary",
            config_key="pre_filters.min_salary",
            reason_template="薪资低于 {threshold}，已过滤",
        )
        job = {"salary": "8K-10K"}
        skip, reason = self.filt.check(job, rule, self.profile)
        assert skip is False


# ── TestContainsAnyFilter ──────────────────────────────────────────────────

class TestContainsAnyFilter:
    """黑名单关键词匹配过滤器测试。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.filt = ContainsAnyFilter()
        self.profile = _make_profile(
            [],
            global_config={"blacklist_keywords": ["销售", "实习", "外包"]},
        )

    def test_匹配黑名单词(self):
        rule = _make_rule(
            type="contains_any",
            field="title",
            source="blacklist_keywords",
            case_insensitive=False,
            reason_template="包含黑名单关键词: {keyword}",
        )
        job = {"title": "高级销售经理"}
        skip, reason = self.filt.check(job, rule, self.profile)
        assert skip is True
        assert "销售" in reason

    def test_不匹配时通过(self):
        rule = _make_rule(
            type="contains_any",
            field="title",
            source="blacklist_keywords",
            case_insensitive=False,
            reason_template="包含黑名单关键词: {keyword}",
        )
        job = {"title": "后端开发工程师"}
        skip, reason = self.filt.check(job, rule, self.profile)
        assert skip is False

    def test_大小写不敏感(self):
        profile_ci = _make_profile(
            [],
            global_config={"blacklist_keywords": ["SALE"]},
        )
        rule = _make_rule(
            type="contains_any",
            field="title",
            source="blacklist_keywords",
            case_insensitive=True,
            reason_template="包含黑名单关键词: {keyword}",
        )
        job = {"title": "Sale Representative"}
        skip, reason = self.filt.check(job, rule, profile_ci)
        assert skip is True

    def test_空文本不拦截(self):
        rule = _make_rule(
            type="contains_any",
            field="description",
            source="blacklist_keywords",
            case_insensitive=False,
            reason_template="包含黑名单关键词: {keyword}",
        )
        job = {"description": ""}
        skip, reason = self.filt.check(job, rule, self.profile)
        assert skip is False


# ── TestInactiveDaysFilter ─────────────────────────────────────────────────

class TestInactiveDaysFilter:
    """招聘者活跃度过滤器测试。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.filt = InactiveDaysFilter()
        self.profile = _make_profile(
            [],
            global_config={"pre_filters": {"max_inactive_days": 30}},
        )

    def test_超过最大天数跳过(self):
        rule = _make_rule(
            type="inactive_days",
            field="recruiter_active",
            max_days_key="pre_filters.max_inactive_days",
            reason_template="招聘者 {days} 天未活跃（上限 {max_days}）",
        )
        job = {"recruiter_active": "2个月前"}
        skip, reason = self.filt.check(job, rule, self.profile)
        assert skip is True
        assert "60" in reason  # 2个月 = 60天

    def test_在限制内通过(self):
        rule = _make_rule(
            type="inactive_days",
            field="recruiter_active",
            max_days_key="pre_filters.max_inactive_days",
            reason_template="招聘者 {days} 天未活跃（上限 {max_days}）",
        )
        job = {"recruiter_active": "3天前"}
        skip, reason = self.filt.check(job, rule, self.profile)
        assert skip is False

    def test_今日活跃通过(self):
        rule = _make_rule(
            type="inactive_days",
            field="recruiter_active",
            max_days_key="pre_filters.max_inactive_days",
            reason_template="招聘者 {days} 天未活跃（上限 {max_days}）",
        )
        job = {"recruiter_active": "今日活跃"}
        skip, reason = self.filt.check(job, rule, self.profile)
        assert skip is False

    def test_无法解析时不拦截(self):
        rule = _make_rule(
            type="inactive_days",
            field="recruiter_active",
            max_days_key="pre_filters.max_inactive_days",
            reason_template="招聘者 {days} 天未活跃（上限 {max_days}）",
        )
        job = {"recruiter_active": "未知格式"}
        skip, reason = self.filt.check(job, rule, self.profile)
        assert skip is False


# ── TestChainOrdering ──────────────────────────────────────────────────────

class TestChainOrdering:
    """过滤器链排序与短路行为测试。"""

    def test_第一条命中规则生效(self):
        """第一条规则命中时应立即返回，后续规则不再执行。"""
        rules_cfg = [
            {
                "id": "r1",
                "type": "contains_any",
                "field": "title",
                "source": "kw1",
                "case_insensitive": False,
                "reason_template": "命中规则1: {keyword}",
            },
            {
                "id": "r2",
                "type": "salary_threshold",
                "field": "salary",
                "config_key": "min_sal",
                "reason_template": "薪资过低: {threshold}",
            },
        ]
        profile = _make_profile(
            rules_cfg,
            global_config={
                "kw1": ["销售"],
                "min_sal": 99999,
            },
        )
        chain = FilterChain(profile.filters, profile)

        # title 命中 contains_any → 短路返回，不会检查 salary
        job = {"title": "销售专员", "salary": "5K"}
        skip, reason = chain.evaluate(job)
        assert skip is True
        assert "规则1" in reason

    def test_空规则全部通过(self):
        profile = _make_profile([])
        chain = FilterChain(profile.filters, profile)
        skip, reason = chain.evaluate({"title": "任意职位"})
        assert skip is False
        assert reason == ""

    def test_无命中全部通过(self):
        rules_cfg = [
            {
                "id": "r1",
                "type": "contains_any",
                "field": "title",
                "source": "kw",
                "case_insensitive": False,
                "reason_template": "命中: {keyword}",
            },
        ]
        profile = _make_profile(rules_cfg, global_config={"kw": ["销售"]})
        chain = FilterChain(profile.filters, profile)
        skip, reason = chain.evaluate({"title": "Python工程师"})
        assert skip is False

    def test_未知规则类型被跳过(self):
        rules_cfg = [
            {
                "id": "unknown_r",
                "type": "nonexistent_type",
                "field": "x",
                "reason_template": "不应执行到这里",
            },
        ]
        profile = _make_profile(rules_cfg)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            chain = FilterChain(profile.filters, profile)
            assert len(w) == 1
            assert "未知过滤规则类型" in str(w[0].message)

        # 未知类型被跳过后，链为空，应全部通过
        skip, reason = chain.evaluate({"x": "anything"})
        assert skip is False

    def test_register_rule_type扩展(self):
        """register_rule_type 应能注册新的过滤器类型。"""
        from shared.engine.filter_chain import BaseFilter

        class DummyFilter(BaseFilter):
            def check(self, job, rule, profile):
                return True, "dummy"

        FilterChain.register_rule_type("dummy", DummyFilter)
        rules_cfg = [
            {
                "id": "d1",
                "type": "dummy",
                "field": "",
                "reason_template": "",
            },
        ]
        profile = _make_profile(rules_cfg)
        chain = FilterChain(profile.filters, profile)
        skip, reason = chain.evaluate({})
        assert skip is True
        assert reason == "dummy"
