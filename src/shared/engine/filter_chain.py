"""过滤链 — 解释执行 Profile.filters 声明的规则列表。"""
from __future__ import annotations

import logging
import warnings
from abc import ABC, abstractmethod
from typing import Any

from shared.engine.adapter_protocol import DefaultAdapter
from shared.engine.profile import FilterRule, SiteProfile

logger = logging.getLogger(__name__)


class BaseFilter(ABC):
    """过滤器基类，所有具体过滤器必须实现 check 方法。"""

    @abstractmethod
    def check(self, job: dict[str, Any], rule: FilterRule, profile: SiteProfile) -> tuple[bool, str]:
        """
        执行过滤检查。

        Returns:
            (skip, reason) — skip=True 表示命中过滤条件应跳过该职位，
            reason 为跳过原因说明（skip=False 时可为空字符串）。
        """


class SalaryThresholdFilter(BaseFilter):
    """薪资下限过滤 — 职位薪资低于阈值时跳过。"""

    def __init__(self, adapter: DefaultAdapter | None = None):
        self._adapter = adapter or DefaultAdapter()

    def check(self, job: dict[str, Any], rule: FilterRule, profile: SiteProfile) -> tuple[bool, str]:
        threshold = profile.get_global(rule.config_key)
        if threshold is None:
            return False, ""

        salary_text = job.get(rule.field, "")
        parsed = self._adapter.parse_salary(str(salary_text))
        if parsed is None:
            # 无法解析薪资信息时不拦截，交给后续处理
            return False, ""

        if parsed < int(threshold):
            reason = rule.reason_template.format(threshold=threshold)
            return True, reason

        return False, ""


class ContainsAnyFilter(BaseFilter):
    """黑名单关键词匹配 — 职位文本包含任一关键词时跳过。"""

    def check(self, job: dict[str, Any], rule: FilterRule, profile: SiteProfile) -> tuple[bool, str]:
        blacklist: list[str] | None = profile.get_global(rule.source)
        if not blacklist:
            return False, ""

        text = str(job.get(rule.field, ""))
        if not text:
            return False, ""

        search_text = text.lower() if rule.case_insensitive else text
        keywords = [kw.lower() for kw in blacklist] if rule.case_insensitive else blacklist

        for kw in keywords:
            if kw in search_text:
                reason = rule.reason_template.format(keyword=kw)
                return True, reason

        return False, ""


class InactiveDaysFilter(BaseFilter):
    """招聘者活跃度过滤 — 活跃天数超过上限时跳过。"""

    def __init__(self, adapter: DefaultAdapter | None = None):
        self._adapter = adapter or DefaultAdapter()

    def check(self, job: dict[str, Any], rule: FilterRule, profile: SiteProfile) -> tuple[bool, str]:
        max_days_raw = profile.get_global(rule.max_days_key)
        if max_days_raw is None:
            return False, ""

        max_days = int(max_days_raw)
        active_text = str(job.get(rule.field, ""))
        parsed = self._adapter.parse_inactive_days(active_text)

        if parsed is None:
            return False, ""

        if parsed > max_days:
            reason = rule.reason_template.format(days=parsed, max_days=max_days)
            return True, reason

        return False, ""


class FilterChain:
    """有序过滤器链 — 按声明顺序依次执行，任一命中即短路返回。"""

    _RULE_TYPES: dict[str, type[BaseFilter]] = {
        "salary_threshold": SalaryThresholdFilter,
        "contains_any": ContainsAnyFilter,
        "inactive_days": InactiveDaysFilter,
    }

    def __init__(self, rules: list[FilterRule], profile: SiteProfile):
        self._profile = profile
        self._entries: list[tuple[FilterRule, BaseFilter]] = []
        for rule in rules:
            filter_cls = self._RULE_TYPES.get(rule.type)
            if filter_cls is None:
                warnings.warn(f"未知过滤规则类型 '{rule.type}' (id={rule.id})，已跳过", stacklevel=2)
                continue
            self._entries.append((rule, filter_cls()))

    def evaluate(self, job: dict[str, Any]) -> tuple[bool, str]:
        """
        对职位执行完整过滤链。

        Returns:
            (should_skip, reason) — should_skip=True 时 reason 说明跳过原因。
        """
        for rule, filt in self._entries:
            skip, reason = filt.check(job, rule, self._profile)
            if skip:
                return True, reason
        return False, ""

    @classmethod
    def register_rule_type(cls, name: str, filter_class: type[BaseFilter]) -> None:
        """注册新的过滤器类型到规则映射表。"""
        cls._RULE_TYPES[name] = filter_class
