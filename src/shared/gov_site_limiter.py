"""政府网站访问限制工具 — 确保合规访问政府网站。

提供以下功能：
1. 识别政府网站域名
2. 访问频率限制（每分钟/每小时请求数限制）
3. 自动延长延迟时间
4. 请求间隔控制
"""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse

from shared.config import get_config


class GovernmentSiteLimiter:
    """政府网站访问限制器 — 单例模式"""

    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self._request_timestamps = []  # pylint: disable=attribute-defined-outside-init
        self._last_request_time = 0  # pylint: disable=attribute-defined-outside-init
        self._enabled = True  # pylint: disable=attribute-defined-outside-init
        self._domains = []  # pylint: disable=attribute-defined-outside-init
        self._load_config()

    def _load_config(self):
        """加载政府网站配置"""
        cfg = get_config()
        gov_cfg = cfg.get("government_site", {})
        self._enabled = gov_cfg.get("enabled", True)  # pylint: disable=attribute-defined-outside-init
        self._domains = gov_cfg.get("domains", [])  # pylint: disable=attribute-defined-outside-init
        self._max_requests_per_minute = gov_cfg.get("rate_limit", {}).get("max_requests_per_minute", 5)  # pylint: disable=attribute-defined-outside-init
        self._max_requests_per_hour = gov_cfg.get("rate_limit", {}).get("max_requests_per_hour", 30)  # pylint: disable=attribute-defined-outside-init
        self._min_interval_ms = gov_cfg.get("rate_limit", {}).get("min_interval_ms", 3000)  # pylint: disable=attribute-defined-outside-init
        self._delays = gov_cfg.get("delays", {})  # pylint: disable=attribute-defined-outside-init

    def is_government_site(self, url: str) -> bool:
        """判断 URL 是否为政府网站"""
        if not self._enabled:
            return False

        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            return any(gov_domain.lower() in domain for gov_domain in self._domains)
        except Exception:  # pylint: disable=broad-exception-caught
            return False

    def _cleanup_timestamps(self):
        """清理过期的请求时间戳"""
        now = time.time()
        # 保留最近1小时的请求记录
        self._request_timestamps = [t for t in self._request_timestamps if now - t < 3600]  # pylint: disable=attribute-defined-outside-init

    def _get_request_count(self, seconds: int) -> int:
        """获取指定时间范围内的请求数量"""
        self._cleanup_timestamps()
        threshold = time.time() - seconds
        return len([t for t in self._request_timestamps if t >= threshold])

    def _check_rate_limit(self) -> float:
        """检查速率限制，返回需要等待的时间（秒）"""
        now = time.time()
        wait_time = 0.0

        # 检查最小请求间隔
        time_since_last = (now - self._last_request_time) * 1000
        if time_since_last < self._min_interval_ms:
            wait_time = max(wait_time, (self._min_interval_ms - time_since_last) / 1000)

        # 检查每分钟限制
        requests_in_minute = self._get_request_count(60)
        if requests_in_minute >= self._max_requests_per_minute:
            # 计算需要等待到下一分钟的时间
            oldest_time = self._request_timestamps[-self._max_requests_per_minute]
            wait_until = oldest_time + 60
            wait_time = max(wait_time, wait_until - now)

        # 检查每小时限制
        requests_in_hour = self._get_request_count(3600)
        if requests_in_hour >= self._max_requests_per_hour:
            # 计算需要等待到下一小时的时间
            oldest_time = self._request_timestamps[-self._max_requests_per_hour]
            wait_until = oldest_time + 3600
            wait_time = max(wait_time, wait_until - now)

        return wait_time

    async def wait_if_needed(self, url: str) -> dict:
        """如果是政府网站，执行必要的等待并记录请求"""
        if not self.is_government_site(url):
            return {
                "is_gov_site": False,
                "waited_seconds": 0,
                "rate_limited": False
            }

        wait_time = self._check_rate_limit()
        if wait_time > 0:
            await asyncio.sleep(wait_time)

        # 记录请求
        now = time.time()
        self._request_timestamps.append(now)
        self._last_request_time = now  # pylint: disable=attribute-defined-outside-init

        return {
            "is_gov_site": True,
            "waited_seconds": wait_time,
            "rate_limited": wait_time > 0,
            "requests_in_minute": self._get_request_count(60),
            "requests_in_hour": self._get_request_count(3600)
        }

    def get_delay(self, delay_name: str, default: float = 1.0) -> float:
        """获取政府网站专用延迟时间"""
        return self._delays.get(delay_name, default)

    async def gov_delay(self, delay_name: str, custom_seconds: float | None = None) -> None:
        """执行政府网站专用延迟"""
        seconds = custom_seconds if custom_seconds is not None else self.get_delay(delay_name)
        await asyncio.sleep(seconds)


# 便捷函数
async def check_gov_site_limit(url: str) -> dict:
    """检查并等待政府网站访问限制"""
    limiter = GovernmentSiteLimiter()
    return await limiter.wait_if_needed(url)


def is_gov_domain(url: str) -> bool:
    """判断 URL 是否为政府网站域名"""
    limiter = GovernmentSiteLimiter()
    return limiter.is_government_site(url)


async def gov_safe_delay(url: str, delay_name: str = "page_ready") -> None:
    """针对政府网站的安全延迟 — 先检查速率限制，再执行延迟"""
    limiter = GovernmentSiteLimiter()
    await limiter.wait_if_needed(url)
    await limiter.gov_delay(delay_name)
