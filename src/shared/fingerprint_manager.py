from __future__ import annotations

from random import choice, randint
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
    w, h = choice(WINDOW_PRESETS)

    screen_w = w + randint(0, 400)
    screen_h = h + randint(20, 200)

    return dict(
        window=(w, h),
        os=[choice(OS_WEIGHTED)],
        screen=dict(
            width=screen_w,
            height=screen_h,
            availWidth=screen_w,
            availHeight=screen_h - randint(30, 60),
            colorDepth=24,
            pixelDepth=24,
        ),
    )


FALLBACK_UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
]


def random_user_agent() -> str:
    return choice(FALLBACK_UA_LIST)