"""适配器协议单元测试 — 覆盖 DefaultAdapter 与 Registry。"""
from __future__ import annotations

import unittest

# 确保可导入（项目根目录已在 sys.path 中）
from src.shared.engine.adapter_protocol import (
    DefaultAdapter,
    SiteAdapter,
    get_adapter,
    register_adapter,
)


class TestDefaultAdapterSalary(unittest.TestCase):
    """薪资解析测试"""

    def setUp(self) -> None:
        self.adapter = DefaultAdapter()

    def test_k_format(self) -> None:
        """K 格式：4K-6K → 4000"""
        self.assertEqual(self.adapter.parse_salary("4K-6K"), 4000)

    def test_k_format_lowercase(self) -> None:
        """小写 k 也应识别"""
        self.assertEqual(self.adapter.parse_salary("8k-12k"), 8000)

    def test_number_format(self) -> None:
        """纯数字格式"""
        self.assertEqual(self.adapter.parse_salary("5000-7000"), 5000)

    def test_empty_input(self) -> None:
        """空输入返回 None"""
        self.assertIsNone(self.adapter.parse_salary(""))
        self.assertIsNone(self.adapter.parse_salary(None))  # type: ignore[arg-type]

    def test_case_insensitive(self) -> None:
        """大小写不敏感"""
        self.assertEqual(self.adapter.parse_salary("10K"), 10000)
        self.assertEqual(self.adapter.parse_salary("10k"), 10000)

    def test_single_number_no_range(self) -> None:
        """单个数字无范围"""
        self.assertEqual(self.adapter.parse_salary("6000"), 6000)


class TestDefaultAdapterInactiveDays(unittest.TestCase):
    """活跃时间解析测试"""

    def setUp(self) -> None:
        self.adapter = DefaultAdapter()

    def test_today_level(self) -> None:
        """今日级别关键词 → 0"""
        for text in ("今日", "刚刚", "5分钟前", "2小时前"):
            with self.subTest(text=text):
                self.assertEqual(self.adapter.parse_inactive_days(text), 0)

    def test_days_format(self) -> None:
        """天数格式"""
        self.assertEqual(self.adapter.parse_inactive_days("3天前"), 3)
        self.assertEqual(self.adapter.parse_inactive_days("15天前活跃"), 15)

    def test_weeks_format(self) -> None:
        """周数格式 × 7"""
        self.assertEqual(self.adapter.parse_inactive_days("2周前"), 14)
        self.assertEqual(self.adapter.parse_inactive_days("1周前活跃"), 7)

    def test_months_format(self) -> None:
        """月数格式 × 30"""
        self.assertEqual(self.adapter.parse_inactive_days("2个月前"), 60)
        self.assertEqual(self.adapter.parse_inactive_days("1个月前活跃"), 30)

    def test_fallback_keywords(self) -> None:
        """fallback 关键词映射"""
        self.assertEqual(self.adapter.parse_inactive_days("昨天"), 1)
        self.assertEqual(self.adapter.parse_inactive_days("周前"), 7)
        self.assertEqual(self.adapter.parse_inactive_days("月前"), 30)

    def test_empty_input(self) -> None:
        """空输入返回 None"""
        self.assertIsNone(self.adapter.parse_inactive_days(""))
        self.assertIsNone(self.adapter.parse_inactive_days(None))  # type: ignore[arg-type]

    def test_unrecognized_format(self) -> None:
        """无法识别的格式返回 None"""
        self.assertIsNone(self.adapter.parse_inactive_days("未知格式"))


class TestAdapterRegistry(unittest.TestCase):
    """注册表测试"""

    def tearDown(self) -> None:
        # 清理 registry，避免跨测试污染
        from src.shared.engine.adapter_protocol import _ADAPTER_REGISTRY

        _ADAPTER_REGISTRY.clear()

    def test_register_and_get(self) -> None:
        """注册自定义适配器后能正确获取"""

        class CustomAdapter:
            def parse_salary(self, text: str) -> int | None:
                return 99999

            def parse_inactive_days(self, text: str) -> int | None:
                return -1

        register_adapter("test_site", CustomAdapter())
        adapter = get_adapter("test_site")
        self.assertEqual(adapter.parse_salary("anything"), 99999)
        self.assertEqual(adapter.parse_inactive_days("anything"), -1)

    def test_fallback_to_default(self) -> None:
        """未注册站点回退到 DefaultAdapter"""
        adapter = get_adapter("nonexistent_site")
        self.assertIsInstance(adapter, DefaultAdapter)
        self.assertEqual(adapter.parse_salary("5K-8K"), 5000)
        self.assertEqual(adapter.parse_inactive_days("3天前"), 3)


if __name__ == "__main__":
    unittest.main()
