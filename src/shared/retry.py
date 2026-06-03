"""指数退避重试模块，为关键网络操作提供自动重试能力。

最大重试 3 次（硬编码），带随机抖动避免雷群效应。
"""

import asyncio
import random

from shared.logging_config import get_logger

logger = get_logger("retry")

MAX_RETRIES = 3
BASE_DELAY = 1.0
MAX_DELAY = 30.0


def _backoff_delay(attempt: int) -> float:
    """计算第 attempt 次重试的等待秒数（指数退避 + 随机抖动）。"""
    delay = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
    jitter = random.uniform(0, delay * 0.5)
    return delay + jitter


async def retry_async(func, *args, max_retries: int = MAX_RETRIES, **kwargs):
    """异步重试包装器：执行 func(*args, **kwargs)，失败时指数退避重试。

    参数:
        func: 可等待的异步函数。
        *args: 传递给 func 的位置参数。
        max_retries: 最大重试次数（默认 3）。
        **kwargs: 传递给 func 的关键字参数。

    返回:
        func 的返回值。若所有重试均失败则抛出最后一个异常。
    """
    last_exc = None
    func_name = getattr(func, "__name__", str(func))

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exc = e
            if attempt < max_retries:
                delay = _backoff_delay(attempt)
                logger.warning(
                    "%s 第 %d/%d 次失败: %s，%.1f秒后重试",
                    func_name, attempt + 1, max_retries, e, delay)
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "%s 重试 %d 次全部失败: %s",
                    func_name, max_retries, e)

    raise last_exc
