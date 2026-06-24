"""浏览器指纹伪装模块 — 生成随机化的浏览器配置参数。

通过随机选择窗口尺寸、操作系统、硬件并发数等参数，
模拟真实用户的浏览器环境，降低被识别为自动化工具的风险。
"""

from __future__ import annotations

from random import choice
from typing import Any

from shared.logging_config import get_logger

logger = get_logger("fingerprint")

WINDOW_PRESETS = [
    (1366, 768),
    (1440, 900),
    (1536, 864),
    (1600, 900),
    (1680, 1050),
    (1920, 1080),
    (1920, 1200),
    (2560, 1440),
]

OS_WEIGHTED = ["windows"] * 14 + ["macos"] * 3 + ["linux"] * 1

HARDWARE_CONCURRENCY = [4, 6, 8, 8, 8, 12, 16]
DEVICE_MEMORY = [4, 8, 8, 8, 16]
PIXEL_RATIOS = [1.0, 1.0, 1.25, 1.5, 1.5, 2.0]


def generate_camoufox_opts() -> dict[str, Any]:
    """生成随机化的 Camoufox 浏览器配置参数。"""
    w, h = choice(WINDOW_PRESETS)

    return {
        "window": (w, h),
        "os": [choice(OS_WEIGHTED)],
        # 不传 screen 参数，让 Camoufox 自行生成指纹
    }


FALLBACK_UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
]


def random_user_agent() -> str:
    """从预定义列表中随机返回一个 User-Agent 字符串。"""
    return choice(FALLBACK_UA_LIST)
