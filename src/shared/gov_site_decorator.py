"""政府网站访问限制装饰器 — 简化政府网站访问限制的使用。

使用示例：
    @gov_site_rate_limit
    async def fetch_gov_data(url):
        # 访问政府网站的代码
        pass
"""

from __future__ import annotations

import asyncio
import functools
import logging

from shared.gov_site_limiter import check_gov_site_limit, gov_safe_delay

logger = logging.getLogger(__name__)


def gov_site_rate_limit(func=None, *, delay_name: str = "page_ready"):
    """装饰器：自动对政府网站应用访问限制。
    
    Args:
        delay_name: 延迟配置名称，默认为 "page_ready"
    
    使用示例：
        @gov_site_rate_limit
        async def fetch_data(url):
            pass
        
        @gov_site_rate_limit(delay_name="navigation")
        async def navigate_to(url):
            pass
    """
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            url = _extract_url_from_args(args, kwargs)

            if url:
                # 检查并等待速率限制
                result = await check_gov_site_limit(url)
                if result["is_gov_site"]:
                    if result["rate_limited"]:
                        logger.info(f"政府网站速率限制触发，已等待 {result['waited_seconds']:.2f} 秒")
                    logger.info(f"政府网站访问 - 过去1分钟: {result['requests_in_minute']}次, "
                                f"过去1小时: {result['requests_in_hour']}次")

            # 执行原函数
            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            url = _extract_url_from_args(args, kwargs)

            if url:
                # 同步版本：检查但不等待（同步代码中不应该访问政府网站）
                from shared.gov_site_limiter import is_gov_domain
                if is_gov_domain(url):
                    logger.warning("同步函数尝试访问政府网站，请使用异步版本")

            return func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    if func is None:
        return decorator
    return decorator(func)


def gov_site_delay(delay_name: str = "page_ready"):
    """装饰器：在函数执行后添加政府网站专用延迟。
    
    Args:
        delay_name: 延迟配置名称
    """
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)

            url = _extract_url_from_args(args, kwargs)
            if url:
                from shared.gov_site_limiter import is_gov_domain
                if is_gov_domain(url):
                    await gov_safe_delay(url, delay_name)

            return result

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            return result

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def _extract_url_from_args(args, kwargs) -> str | None:
    """从函数参数中提取 URL"""
    # 检查第一个位置参数是否是 URL
    if args:
        first_arg = args[0]
        if isinstance(first_arg, str) and (first_arg.startswith("http://") or first_arg.startswith("https://")):
            return first_arg

    # 检查关键字参数
    for key in ["url", "target_url", "page_url", "link"]:
        if key in kwargs and isinstance(kwargs[key], str):
            return kwargs[key]

    return None
