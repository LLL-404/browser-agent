"""性能分析工具，用于函数级计时、热点识别和性能报告生成。"""

from __future__ import annotations

import asyncio
import functools
import threading
import time
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

from shared.logging_config import get_logger

logger = get_logger("profiler")

P = ParamSpec("P")
R = TypeVar("R")

# 全局性能统计存储
_stats: dict[str, dict[str, Any]] = {}
_sync_lock = threading.Lock()
_async_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    """获取或创建异步锁（延迟初始化避免模块加载问题）。"""
    global _async_lock
    if _async_lock is None:
        _async_lock = asyncio.Lock()
    return _async_lock


def record_execution(func_name: str, duration: float, success: bool = True) -> None:
    """记录一次函数执行的性能数据。"""
    with _sync_lock:
        if func_name not in _stats:
            _stats[func_name] = {
                "count": 0,
                "total_time": 0.0,
                "min_time": float("inf"),
                "max_time": 0.0,
                "failures": 0,
            }

        stat = _stats[func_name]
        stat["count"] += 1
        stat["total_time"] += duration
        stat["min_time"] = min(stat["min_time"], duration)
        stat["max_time"] = max(stat["max_time"], duration)
        if not success:
            stat["failures"] += 1


async def async_record_execution(
    func_name: str, duration: float, success: bool = True
) -> None:
    """线程安全版本的执行记录（用于异步上下文）。"""
    lock = _get_lock()
    async with lock:
        record_execution(func_name, duration, success)


class profile_async:
    """异步函数性能分析装饰器。

    用法:
        @profile_async()
        async def my_function():
            ...

        @profile_async(threshold=1.0)  # 只记录超过 1 秒的调用
        async def slow_function():
            ...
    """

    def __init__(self, threshold: float = 0.0):
        """
        Args:
            threshold: 最小记录阈值（秒），低于此值不记录，0 表示全部记录
        """
        self.threshold = threshold

    def __call__(self, func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                duration = time.perf_counter() - start
                if duration >= self.threshold:
                    await async_record_execution(
                        func.__name__, duration, success=True
                    )
                return result
            except Exception:
                duration = time.perf_counter() - start
                if duration >= self.threshold:
                    await async_record_execution(
                        func.__name__, duration, success=False
                    )
                raise

        return wrapper


class profile_sync:
    """同步函数性能分析装饰器。

    用法:
        @profile_sync()
        def my_function():
            ...
    """

    def __init__(self, threshold: float = 0.0):
        self.threshold = threshold

    def __call__(self, func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                duration = time.perf_counter() - start
                if duration >= self.threshold:
                    record_execution(func.__name__, duration, success=True)
                return result
            except Exception:
                duration = time.perf_counter() - start
                if duration >= self.threshold:
                    record_execution(func.__name__, duration, success=False)
                raise

        return wrapper


def get_stats() -> dict[str, dict[str, Any]]:
    """获取所有函数的性能统计数据。"""
    return dict(_stats)


def get_hot_functions(top_n: int = 10) -> list[dict[str, Any]]:
    """识别热点函数（按总耗时排序）。

    Args:
        top_n: 返回前 N 个热点函数

    Returns:
        热点函数列表，每项包含函数名和统计信息
    """
    sorted_funcs = sorted(
        _stats.items(),
        key=lambda x: x[1]["total_time"],
        reverse=True,
    )[:top_n]

    return [
        {
            "name": name,
            **stat,
            "avg_time": stat["total_time"] / max(stat["count"], 1),
            "success_rate": (stat["count"] - stat["failures"]) / max(stat["count"], 1),
        }
        for name, stat in sorted_funcs
    ]


def generate_report() -> str:
    """生成 Markdown 格式的性能报告。"""
    if not _stats:
        return "# 性能报告\n\n暂无数据。\n"

    hot = get_hot_functions(20)
    total_calls = sum(s["count"] for s in _stats.values())
    total_time = sum(s["total_time"] for s in _stats.values())

    lines = [
        "# 性能分析报告",
        f"生成时间: {__import__('datetime').datetime.now().isoformat()}",
        "",
        "## 总览",
        f"- 总调用次数: {total_calls}",
        f"- 总耗时: {total_time:.2f} 秒",
        f"- 监控函数数: {len(_stats)}",
        "",
        "## 🔥 热点函数 TOP 10（按总耗时排序）",
        "",
        "| 函数名 | 调用次数 | 总耗时(秒) | 平均耗时(秒) | 最大耗时(秒) | 成功率 |",
        "|--------|----------|------------|--------------|--------------|--------|",
    ]

    for func in hot[:10]:
        lines.append(
            f"| `{func['name']}` | {func['count']} | {func['total_time']:.3f} "
            f"| {func['avg_time']:.3f} | {func['max_time']:.3f} "
            f"| {func['success_rate']*100:.1f}% |"
        )

    # 识别潜在瓶颈（平均耗时 > 1秒）
    bottlenecks = [f for f in hot if f["avg_time"] > 1.0]
    if bottlenecks:
        lines.append("")
        lines.append("## ⚠️ 潜在性能瓶颈（平均耗时 > 1秒）")
        lines.append("")
        for func in bottlenecks:
            lines.append(
                f"- **{func['name']}**: 平均 {func['avg_time']:.2f}s "
                f"(共 {func['count']} 次)"
            )

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*报告由 `core/profiler` 模块自动生成*")

    return "\n".join(lines)


def clear_stats() -> None:
    """清除所有性能统计数据（用于测试或重置）。"""
    global _stats
    _stats.clear()
