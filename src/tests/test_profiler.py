"""Tests for shared/profiler.py — performance profiling utilities."""
from __future__ import annotations

import pytest

from shared.profiler import (
    clear_stats,
    get_hot_functions,
    get_stats,
    profile_async,
    profile_sync,
    record_execution,
)


@pytest.fixture(autouse=True)
def _reset_stats():
    clear_stats()
    yield
    clear_stats()


class TestRecordExecution:
    def test_record_success(self):
        record_execution("foo", 0.5, success=True)
        stats = get_stats()
        assert "foo" in stats
        assert stats["foo"]["count"] == 1
        assert stats["foo"]["total_time"] == 0.5
        assert stats["foo"]["failures"] == 0

    def test_record_failure(self):
        record_execution("bar", 1.0, success=False)
        stats = get_stats()
        assert stats["bar"]["failures"] == 1
        assert stats["bar"]["count"] == 1

    def test_record_multiple_calls(self):
        record_execution("baz", 0.3)
        record_execution("baz", 0.7)
        stats = get_stats()
        assert stats["baz"]["count"] == 2
        assert stats["baz"]["total_time"] == 1.0
        assert stats["baz"]["min_time"] == 0.3
        assert stats["baz"]["max_time"] == 0.7


class TestProfileSync:
    def test_success_path(self):
        @profile_sync(threshold=0.0)
        def add(a, b):
            return a + b

        result = add(2, 3)
        assert result == 5
        stats = get_stats()
        assert "add" in stats
        assert stats["add"]["count"] == 1

    def test_failure_path(self):
        @profile_sync(threshold=0.0)
        def will_fail():
            raise ValueError("oops")

        with pytest.raises(ValueError, match="oops"):
            will_fail()
        stats = get_stats()
        assert stats["will_fail"]["failures"] == 1

    def test_threshold_below(self):
        @profile_sync(threshold=10.0)
        def fast():
            return 1

        fast()
        assert get_stats() == {}

    def test_threshold_above(self):
        @profile_sync(threshold=0.0)
        def slow():
            import time
            time.sleep(0.01)
            return 1

        slow()
        assert get_stats()["slow"]["count"] == 1


class TestProfileAsync:
    @pytest.mark.asyncio
    async def test_success_path(self):
        @profile_async(threshold=0.0)
        async def fetch():
            return 42

        result = await fetch()
        assert result == 42
        stats = get_stats()
        assert "fetch" in stats
        assert stats["fetch"]["count"] == 1

    @pytest.mark.asyncio
    async def test_failure_path(self):
        @profile_async(threshold=0.0)
        async def crash():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            await crash()
        stats = get_stats()
        assert stats["crash"]["failures"] == 1

    @pytest.mark.asyncio
    async def test_threshold_suppresses(self):
        @profile_async(threshold=100.0)
        async def quick():
            return 0

        await quick()
        assert get_stats() == {}


class TestHotFunctions:
    def test_empty(self):
        assert get_hot_functions() == []

    def test_ordering(self):
        record_execution("slow", 5.0)
        record_execution("fast", 0.1)
        record_execution("medium", 2.0)
        hot = get_hot_functions(top_n=2)
        assert [h["name"] for h in hot] == ["slow", "medium"]

    def test_top_n(self):
        for i in range(10):
            record_execution(f"f{i}", float(i))
        hot = get_hot_functions(top_n=3)
        assert len(hot) == 3
        assert hot[0]["name"] == "f9"


class TestGenerateReport:
    def test_empty_report(self):
        from shared.profiler import generate_report
        report = generate_report()
        assert "暂无数据" in report

    def test_report_with_data(self):
        from shared.profiler import generate_report
        record_execution("test_func", 2.5)
        record_execution("test_func", 0.5, success=False)
        report = generate_report()
        assert "test_func" in report
        assert "性能分析报告" in report
        assert "2.5" in report or "2.500" in report
        assert "50.0%" in report  # 1/2 success rate

    def test_report_lists_bottlenecks(self):
        from shared.profiler import generate_report
        record_execution("slowpoke", 3.0)
        report = generate_report()
        assert "slowpoke" in report
