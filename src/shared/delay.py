"""统一延迟工具 — 替代代码中的硬编码 asyncio.sleep。

用法:
    from shared.delay import delay, get_delay, random_delay

    await delay("page_ready")           # 使用配置值
    await delay("login_timeout", 30)    # 自定义覆盖
    await random_delay(2, 5)            # 随机范围
"""

from __future__ import annotations

import asyncio
import random
from typing import Optional

from shared.config import get_config

_DEFAULT_SECONDS = 1.0


def get_delay(name: str) -> float:
    """获取指定名称的延迟时间（秒），未配置时回退默认值。"""
    cfg = get_config()
    delays = cfg.get("runtime", {}).get("delays", {})
    return float(delays.get(name, _DEFAULT_SECONDS))


async def delay(name: str, custom_seconds: Optional[float] = None) -> None:
    """执行命名延迟等待。

    Args:
        name: 延迟配置名称（如 "page_ready", "navigation"）
        custom_seconds: 可选的自定义值，优先使用
    """
    seconds = custom_seconds if custom_seconds is not None else get_delay(name)
    await asyncio.sleep(seconds)


async def random_delay(min_seconds: float = 2, max_seconds: float = 5) -> None:
    """在区间内随机等待。"""
    await asyncio.sleep(random.uniform(min_seconds, max_seconds))
