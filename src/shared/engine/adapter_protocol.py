# src/shared/engine/adapter_protocol.py
"""站点适配器协议 — 仅当 YAML 无法表达时才需要实现。"""
from __future__ import annotations

import re
from typing import Protocol, runtime_checkable


@runtime_checkable
class SiteAdapter(Protocol):
    """可选适配器接口。引擎在需要时调用，未实现则跳过。"""

    def parse_salary(self, text: str) -> int | None:
        """从薪资文本提取最低月薪。如 '4K-6K' → 4000"""
        ...  # pylint: disable=unnecessary-ellipsis

    def parse_inactive_days(self, text: str) -> int | None:
        """从活跃时间文本提取天数。如 '3天前' → 3, '刚刚' → 0"""
        ...  # pylint: disable=unnecessary-ellipsis


class DefaultAdapter:
    """默认适配器 — 覆盖 80% 常见招聘网站的解析逻辑。"""

    _RE_SALARY_K = re.compile(r"(\d+)\s*[Kk]")
    _RE_SALARY_NUM = re.compile(r"(\d+)")
    _RE_DAY = re.compile(r"(\d+)\s*天")
    _RE_WEEK = re.compile(r"(\d+)\s*周")
    _RE_MONTH = re.compile(r"(\d+)\s*个月")

    def parse_salary(self, text: str) -> int | None:
        """从薪资文本提取最低月薪，支持 K 和纯数字两种格式。"""
        if not text:
            return None
        nums = self._RE_SALARY_K.findall(text)
        if nums:
            return int(nums[0]) * 1000
        nums = self._RE_SALARY_NUM.findall(text)
        if len(nums) >= 1:
            return int(nums[0])
        return None

    def parse_inactive_days(self, text: str) -> int | None:
        """从活跃时间文本提取天数，支持天/周/月及常见口语表达。"""
        if not text:
            return None
        text = text.strip()
        if any(kw in text for kw in ("今日", "刚刚", "分钟", "小时")):
            return 0
        patterns = [
            (self._RE_DAY, 1),
            (self._RE_WEEK, 7),
            (self._RE_MONTH, 30),
        ]
        for pat, multiplier in patterns:
            m = re.search(pat, text)
            if m:
                return int(m.group(1)) * multiplier
        fallback_map = {"昨天": 1, "周前": 7, "月前": 30}
        for keyword, days in fallback_map.items():
            if keyword in text:
                return days
        return None


_ADAPTER_REGISTRY: dict[str, SiteAdapter] = {}


def register_adapter(site_name: str, adapter: SiteAdapter) -> None:
    """注册站点适配器到全局注册表。"""
    _ADAPTER_REGISTRY[site_name] = adapter


def get_adapter(site_name: str) -> SiteAdapter:
    """获取站点适配器，未注册时返回默认适配器。"""
    return _ADAPTER_REGISTRY.get(site_name, DefaultAdapter())
