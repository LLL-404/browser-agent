"""核心模块单元测试 — 测试不依赖浏览器的纯逻辑模块。"""

import unittest
import asyncio

from modes.zhipin.pre_filter import parse_salary_min, should_skip_job, _parse_inactive_days
from modes.zhipin.keyword_strategy import get_keywords_for_city, get_initial_keyword
from modes.zhipin.city_codes import get_city_code, get_rent_reference
from shared.retry import retry_async, MAX_RETRIES, _backoff_delay


class TestPreFilter(unittest.TestCase):

    def test_parse_salary_min_k_format(self):
        self.assertEqual(parse_salary_min("4K-6K"), 4000)
        self.assertEqual(parse_salary_min("3K-5K"), 3000)
        self.assertEqual(parse_salary_min("10k-15k"), 10000)

    def test_parse_salary_min_num_format(self):
        self.assertEqual(parse_salary_min("3000-5000元/月"), 3000)
        self.assertEqual(parse_salary_min("5500元"), 5500)

    def test_parse_salary_min_empty(self):
        self.assertIsNone(parse_salary_min(""))
        self.assertIsNone(parse_salary_min(None))

    def test_parse_salary_min_single_k(self):
        self.assertEqual(parse_salary_min("12K"), 12000)

    def test_parse_inactive_days_today(self):
        self.assertEqual(_parse_inactive_days("今日活跃"), 0)
        self.assertEqual(_parse_inactive_days("刚刚在线"), 0)
        self.assertEqual(_parse_inactive_days("3小时前来过"), 0)

    def test_parse_inactive_days_explicit(self):
        self.assertEqual(_parse_inactive_days("3天前来过"), 3)
        self.assertEqual(_parse_inactive_days("2周前来过"), 14)
        self.assertEqual(_parse_inactive_days("1个月前来过"), 30)

    def test_parse_inactive_days_fallback(self):
        self.assertEqual(_parse_inactive_days("昨天活跃"), 1)
        self.assertEqual(_parse_inactive_days("周前在线"), 7)
        self.assertEqual(_parse_inactive_days("月前活跃"), 30)

    def test_should_skip_salary_too_low(self):
        skip, reason = should_skip_job("普工", "某某公司", "2K-3K", [], "")
        if skip:
            self.assertIn("低于", reason)

    def test_should_skip_blacklist_title(self):
        skip, reason = should_skip_job("机器学习工程师", "某某公司", "8K-12K", [], "")
        if skip:
            self.assertIn("门槛高于大专", reason)


class TestKeywordStrategy(unittest.TestCase):

    def test_get_initial_keyword(self):
        kw = get_initial_keyword()
        self.assertIsInstance(kw, str)
        self.assertGreater(len(kw), 0)

    def test_get_keywords_rich_city(self):
        kws = get_keywords_for_city("深圳", 150)
        self.assertIsInstance(kws, list)
        self.assertGreater(len(kws), 1)

    def test_get_keywords_poor_city(self):
        kws = get_keywords_for_city("小城市", 3)
        self.assertIsInstance(kws, list)
        self.assertGreater(len(kws), 1)


class TestCityCodes(unittest.TestCase):

    def test_known_city(self):
        code = get_city_code("深圳")
        self.assertEqual(code, "101280600")

    def test_unknown_city(self):
        code = get_city_code("火星")
        self.assertIsNone(code)

    def test_get_rent_reference(self):
        ref = get_rent_reference("深圳")
        self.assertIsInstance(ref, dict)
        self.assertIn("label", ref)

    def test_get_rent_reference_none(self):
        ref = get_rent_reference("火星")
        self.assertIsInstance(ref, dict)


class TestRetry(unittest.IsolatedAsyncioTestCase):

    async def test_retry_success_first_try(self):
        call_count = 0
        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await retry_async(succeed)
        self.assertEqual(result, "ok")
        self.assertEqual(call_count, 1)

    async def test_retry_success_after_failures(self):
        call_count = 0
        async def fail_twice_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("临时错误")
            return "recovered"

        result = await retry_async(fail_twice_then_succeed, max_retries=3)
        self.assertEqual(result, "recovered")
        self.assertEqual(call_count, 3)

    async def test_retry_all_fail(self):
        async def always_fail():
            raise RuntimeError("永久错误")

        with self.assertRaises(RuntimeError):
            await retry_async(always_fail, max_retries=2)

    def test_backoff_delay_increases(self):
        d0 = _backoff_delay(0)
        d1 = _backoff_delay(1)
        d2 = _backoff_delay(2)
        self.assertLess(d0, d1)
        self.assertLess(d1, d2)

    def test_max_retries_constant(self):
        self.assertEqual(MAX_RETRIES, 3)


if __name__ == "__main__":
    unittest.main()
