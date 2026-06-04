"""浏览器控制器 — 支持 Camoufox（C++引擎）和 Playwright（JS引擎）双引擎回退。

优先使用 Camoufox 获得 C++ 级别的反检测能力，不可用时回退到 Playwright。
"""

from __future__ import annotations

import asyncio
import functools
import time
from typing import Any, Protocol, TYPE_CHECKING, runtime_checkable

from playwright.async_api import async_playwright

from agent.core.anti_detect import build_browser_kwargs
from shared.config import get_config
from shared.error_handler import classify_playwright_error
from shared.exceptions import (
    BrowserAutomationError,
    BrowserCrashError,
    BrowserStartError,
    ElementClickFailedError,
    ElementFillFailedError,
    ElementNotFoundError,
    ElementNotInteractableError,
    NavigationFailedError,
    NavigationTimeoutError,
    PageNotReadyError,
)
from shared.logging_config import get_logger

if TYPE_CHECKING:
    from playwright.async_api import Page as _Page


@runtime_checkable
class _BrowserLike(Protocol):
    """AsyncCamoufox 和 BrowserContext 的公共接口协议。"""

    async def new_page(self) -> _Page: ...
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool | None: ...
    async def close(self) -> None: ...
    @property
    def pages(self) -> list[_Page]: ...


try:
    from camoufox import AsyncCamoufox
    from camoufox.addons import DefaultAddons
    HAS_CAMOUFOX = True
except ImportError:
    HAS_CAMOUFOX = False

logger = get_logger("browser")

_PLAYWRIGHT_ERRORS = (Exception,)  # Playwright 可能抛出多种异常，统一兜底


def _handle_errors(default_return, crash_msg="操作失败"):
    """装饰器：统一处理 Playwright 异常的样板代码。"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            try:
                return await func(self, *args, **kwargs)
            except _PLAYWRIGHT_ERRORS as e:
                exc_cls = classify_playwright_error(e)
                if exc_cls is BrowserCrashError:
                    logger.error("%s: %s", crash_msg, e)
                    raise exc_cls(f"{crash_msg}: {e}") from e
                logger.warning("%s: %s", crash_msg, e)
                return default_return
        return wrapper
    return decorator


class BrowserController:
    """统一管理浏览器生命周期并提供常用页面操作。"""

    def __init__(self):
        self._browser: _BrowserLike | None = None
        self._page: _Page | None = None
        self._pw: Any | None = None
        self._engine: str | None = None
        self._is_running: bool = False
        self._has_camoufox: bool = HAS_CAMOUFOX
        self._console_logs: list[dict] = []
        self._network_logs: list[dict] = []
        self._pending_dialog: Any = None

    def _require_page(self) -> _Page:
        """确保页面已初始化，否则抛出 PageNotReadyError。"""
        if not self._page:
            raise PageNotReadyError(
                "页面未初始化，请先调用 start() 启动浏览器",
                error_code="PAGE_NOT_READY",
            )
        return self._page

    @property
    def engine(self) -> str | None:
        """返回当前已启动的浏览器引擎名称。"""
        return self._engine

    @property
    def is_running(self) -> bool:
        """返回浏览器是否处于运行状态。"""
        return self._is_running

    @property
    def has_camoufox(self) -> bool:
        """返回当前环境是否可用 Camoufox。"""
        return self._has_camoufox

    async def start(self, headless: bool = False,
                    use_camoufox: bool = True) -> bool:
        """按优先级启动 Camoufox 或 Playwright。"""
        if self._is_running:
            return True

        if use_camoufox and self._has_camoufox:
            try:
                result = await self._start_camoufox(headless)
                if result:
                    self._engine = "camoufox"
                    self._is_running = True
                    logger.info("Camoufox 启动成功")
                    return True
                logger.info("Camoufox 启动失败，回退到 Playwright")
            except (RuntimeError, OSError) as e:
                logger.warning("Camoufox 启动异常: %s", e)

        result = await self._start_playwright(headless)
        if result:
            self._engine = "playwright"
            self._is_running = True
            logger.info("Playwright 启动成功")
        return result

    async def _start_camoufox(self, headless: bool) -> bool:
        try:
            from shared.fingerprint_manager import generate_camoufox_opts
            persistent = not headless
            opts = dict(
                headless=headless,
                humanize=True,
                geoip=True,
                block_images=False,
                enable_cache=False,
                exclude_addons=[DefaultAddons.UBO],
                **generate_camoufox_opts(),
            )
            if persistent:
                from agent.core.session import (cleanup_old_profiles,
                                                  session_profile_dir)
                udir = session_profile_dir()
                opts["user_data_dir"] = str(udir)
                opts["persistent_context"] = True
                cleanup_old_profiles()
            else:
                opts["persistent_context"] = False
            logger.info("正在启动 Camoufox (headless=%s)...", headless)
            self._browser = await AsyncCamoufox(**opts).__aenter__()
            self._page = await self._browser.new_page()
            await self._setup_page_listeners(self._page)

            from agent.core.session import (has_saved_cookies,
                                              load_cookies_from_file)
            if has_saved_cookies():
                cookies = await load_cookies_from_file()
                if cookies:
                    ctx = self._browser
                    if hasattr(ctx, 'add_cookies'):
                        await ctx.add_cookies(cookies)
                        logger.info("已注入 %d 条 Cookie，跳过登录", len(cookies))
            return True
        except (RuntimeError, OSError):
            logger.warning("Camoufox _start_camoufox 异常: RuntimeError/OSError", exc_info=True)
            if self._browser is not None:
                await self._safe_close_browser()
            raise
        except Exception:
            logger.warning("Camoufox _start_camoufox 异常(未预期类型):", exc_info=True)
            if self._browser is not None:
                await self._safe_close_browser()
            raise

    async def _start_playwright(self, headless: bool) -> bool:
        try:
            self._pw = await async_playwright().__aenter__()

            cfg = get_config()
            kwargs = build_browser_kwargs(cfg, headless)

            self._browser = await self._pw.chromium.launch_persistent_context(**kwargs)
            self._page = self._browser.pages[0] if self._browser.pages else await self._browser.new_page()
            await self._setup_page_listeners(self._page)
            return True
        except (RuntimeError, OSError):
            if getattr(self, "_pw", None) is not None:
                await self._pw.__aexit__(None, None, None)
                self._pw = None
            raise

    @property
    def page(self):
        """返回当前活动页面对象。"""
        return self._page

    def get_pages(self) -> list:
        """返回浏览器上下文中的所有页面列表。"""
        if self._browser and hasattr(self._browser, 'pages'):
            return self._browser.pages
        return []

    async def new_page(self):
        """创建新页面。"""
        if self._browser:
            return await self._browser.new_page()
        return None

    async def navigate_to(self, url: str, timeout: int = 30000) -> bool:
        page = self._require_page()
        try:
            self._console_logs = []
            self._network_logs = []
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            return True
        except _PLAYWRIGHT_ERRORS as e:
            exc_cls = classify_playwright_error(e)
            if exc_cls is NavigationTimeoutError:
                logger.warning("导航到 %s 超时(%.0fs)", url[:80], timeout / 1000)
            else:
                logger.warning("导航到 %s 失败: %s", url[:80], e)
            return False

    async def click_selector(self, selector: str, timeout: int = 10000) -> bool:
        page = self._require_page()
        try:
            await page.click(selector, timeout=timeout)
            return True
        except _PLAYWRIGHT_ERRORS as e:
            exc_cls = classify_playwright_error(e)
            if exc_cls is ElementNotFoundError:
                logger.warning("点击失败 — 元素 %s 未找到", selector)
            elif exc_cls is ElementNotInteractableError:
                logger.warning("点击失败 — 元素 %s 不可交互: %s", selector, e)
            else:
                logger.warning("点击选择器 %s 失败: %s", selector, e)
            return False

    async def find_selector(self, selector: str) -> bool:
        page = self._require_page()
        try:
            return await page.query_selector(selector) is not None
        except _PLAYWRIGHT_ERRORS as e:
            exc_cls = classify_playwright_error(e)
            if exc_cls is BrowserCrashError:
                logger.error("浏览器崩溃: %s", e)
                raise exc_cls(f"浏览器崩溃: {e}") from e
            logger.warning("查找选择器 %s 失败: %s", selector, e)
            return False

    async def fill_input(self, selector: str, value: str) -> bool:
        page = self._require_page()
        try:
            await page.fill(selector, value)
            return True
        except _PLAYWRIGHT_ERRORS as e:
            exc_cls = classify_playwright_error(e)
            if exc_cls is ElementNotFoundError:
                logger.warning("填充失败 — 输入框 %s 未找到", selector)
            else:
                logger.warning("填充输入框 %s 失败: %s", selector, e)
            return False

    @_handle_errors(default_return="", crash_msg="获取页面文本")
    async def get_page_text(self, max_len: int = 2000) -> str:
        text = await self._require_page().inner_text("body")
        return text[:max_len] if text else ""

    @_handle_errors(default_return="", crash_msg="获取页面标题")
    async def get_page_title(self) -> str:
        return await self._require_page().title() or ""

    @_handle_errors(default_return="", crash_msg="获取当前URL")
    async def get_current_url(self) -> str:
        return self._require_page().url

    async def get_detection_status(self) -> dict:
        page = self._require_page()
        checks = {}
        checks_to_run = [
            ("webdriver", "navigator.webdriver"),
            ("chrome", "typeof window.chrome"),
            ("plugins", "navigator.plugins.length"),
            ("user_agent", "navigator.userAgent.substring(0, 100)"),
        ]
        for key, expr in checks_to_run:
            try:
                checks[key] = await page.evaluate(expr)
            except _PLAYWRIGHT_ERRORS as e:
                exc_cls = classify_playwright_error(e)
                if exc_cls is BrowserCrashError:
                    logger.error("浏览器崩溃: %s", e)
                    raise exc_cls(f"浏览器崩溃: {e}") from e
                logger.warning("检测 %s 失败: %s", key, e)
                checks[key] = "error"
        return checks

    # ── 页面健康诊断与自动修复 ──────────────────────────────

    # 反爬/空白页检测关键词，覆盖主流平台常见拦截文案
    _BLANK_PAGE_KEYWORDS = [
        "安全验证", "滑块验证", "访问异常", "请求过于频繁", "系统繁忙",
        "人机验证", "请稍后重试", "网络连接失败", "页面加载中",
        "403 Forbidden", "404 Not Found", "502 Bad Gateway",
        "Access Denied", "Service Unavailable",
        "您的访问被限制", "当前网络环境异常", "请使用手机扫码登录",
    ]

    # 各类问题的修复策略（按优先级排序）
    _REPAIR_STRATEGIES: dict[str, list[dict]] = {
        # 每个策略: {"name": 描述, "fn": 修复方法名, "args": 参数}
        "anti_crawl": [
            {
                "name": "等待页面渲染完成",
                "fn": "_repair_wait_render",
            },
            {
                "name": "重新注入反检测脚本",
                "fn": "_repair_reinject_stealth",
            },
            {
                "name": "硬刷新页面（清除缓存）",
                "fn": "_repair_hard_reload",
            },
        ],
        "blank_or_empty": [
            {
                "name": "等待 JS 渲染完成",
                "fn": "_repair_wait_js_ready",
            },
            {
                "name": "硬刷新页面",
                "fn": "_repair_hard_reload",
            },
            {
                "name": "重新导航到目标URL",
                "fn": "_repair_renavigate",
            },
        ],
        "network_blocked": [
            {
                "name": "等待后重试",
                "fn": "_repair_wait_and_retry",
            },
            {
                "name": "硬刷新页面",
                "fn": "_repair_hard_reload",
            },
        ],
        "captcha_required": [
            {
                "name": "等待用户手动处理验证码",
                "fn": "_repair_wait_for_captcha_solve",
            },
        ],
        "redirect_loop": [
            {
                "name": "终止重定向链并重新导航",
                "fn": "_repair_break_redirect",
            },
        ],
    }

    async def detect_page_health(self) -> dict[str, Any]:
        """检测当前页面是否为空白页、被反爬拦截或加载异常。

        Returns:
            包含 healthy/is_blank/issues/url/title/body_len/has_body 的诊断字典。
        """
        page = self._require_page()
        result: dict[str, Any] = {
            "healthy": True,
            "is_blank": False,
            "issues": [],
            "url": "",
            "title": "",
            "body_len": 0,
            "has_body": False,
        }

        try:
            result["url"] = page.url
            result["title"] = await page.title() or ""
        except Exception:
            pass

        # 检查1: URL 是否为 about:blank 或空
        if not result["url"] or result["url"].startswith("about:"):
            result["healthy"] = False
            result["is_blank"] = True
            result["issues"].append(f"空白页 URL: {result['url'] or '(empty)'}")
            return result

        # 检查2: body 是否存在及其内容长度
        try:
            has_body_el = await page.query_selector("body")
            if has_body_el is None:
                result["healthy"] = False
                result["is_blank"] = True
                result["issues"].append("DOM 中无 body 元素")
                return result

            result["has_body"] = True
            body_text = await page.inner_text("body") or ""
            result["body_len"] = len(body_text.strip())

            if result["body_len"] < 100:
                result["healthy"] = False
                result["is_blank"] = True
                result["issues"].append(f"body 内容过短 ({result['body_len']} 字符)")
                if body_text.strip():
                    result["issues"].append(f"内容预览: {body_text.strip()[:80]}")
                return result
        except Exception as e:
            result["healthy"] = False
            result["issues"].append(f"读取 body 失败: {e}")
            return result

        # 检查3: 反爬拦截关键词
        try:
            for kw in self._BLANK_PAGE_KEYWORDS:
                if kw in body_text:
                    result["healthy"] = False
                    result["issues"].append(f"检测到反爬/异常文本: '{kw}'")
        except Exception:
            pass

        # 检查4: 页面加载状态
        try:
            loading_state = await page.evaluate(
                "() => document.readyState"
            )
            if loading_state == "loading":
                result["issues"].append("页面仍在加载中 (readyState=loading)")
        except Exception:
            pass

        if result["issues"]:
            result["healthy"] = False

        return result

    async def diagnose_page_issue(self, url: str | None = None) -> dict[str, Any]:
        """对当前页面进行深度诊断，确定问题的根因类别。

        不仅检测症状，还分析：
        - 是否被反爬拦截（验证码/WAF）
        - JS 资源是否正常加载
        - 网络请求是否有大量失败
        - 是否陷入重定向循环
        - Cookie/Session 是否过期

        Args:
            url: 原始目标 URL（用于判断是否被重定向）。

        Returns:
            {
                "diagnosis": str,          # 根因类别
                "confidence": float,       # 置信度 0-1
                "symptoms": list[str],     # 症状列表
                "details": dict,           # 详细诊断数据
                "suggested_repair": list,  # 建议的修复策略
            }
        """
        from agent.core.anti_detect import STEALTH_SCRIPT

        page = self._require_page()
        target_url = url or ""

        # ── 收集多维度诊断数据 ──
        symptoms: list[str] = []
        details: dict[str, Any] = {}
        diagnosis = "unknown"
        confidence = 0.0

        # 1. 基础健康检测
        health = await self.detect_page_health()
        symptoms.extend(health["issues"])
        details["health"] = health

        # 如果页面完全健康，直接返回
        if health["healthy"]:
            return {
                "diagnosis": "normal",
                "confidence": 1.0,
                "symptoms": [],
                "details": details,
                "suggested_repair": [],
            }

        current_url = health.get("url", "")

        # 2. 检测重定向循环
        details["redirect_info"] = {}
        if target_url and current_url and target_url != current_url:
            details["redirect_info"]["from"] = target_url
            details["redirect_info"]["to"] = current_url
            # 判断是否跳转到登录页或验证页
            login_indicators = ["login", "passport", "verify", "captcha", "security"]
            is_login_redirect = any(ind in current_url.lower() for ind in login_indicators)
            if is_login_redirect:
                symptoms.append(f"被重定向到认证/验证页: {current_url}")
                details["redirect_info"]["type"] = "auth_redirect"

        # 3. 检测 JS 加载状态和错误
        js_diagnosis = await page.evaluate("""() => {
            const info = {};
            // 脚本加载情况
            const scripts = document.querySelectorAll('script[src]');
            info.total_scripts = scripts.length;
            // 控制台错误数量（通过 window.onerror 计数）
            info.js_errors = window.__playwright_error_count || 0;
            // 关键全局对象是否存在
            info.has_vue = typeof Vue !== 'undefined' || !!document.querySelector('[data-v-]');
            info.has_react = typeof React !== 'undefined' || !!document.querySelector('[data-reactroot], [data-reactid]');
            // DOM 就绪状态
            info.ready_state = document.readyState;
            // 可见元素数量
            info.visible_elements = document.querySelectorAll('body *').length;
            // 图片加载情况
            const images = document.querySelectorAll('img');
            info.total_images = images.length;
            let loaded_imgs = 0;
            images.forEach(img => { if (img.complete && img.naturalWidth > 0) loaded_imgs++; });
            info.loaded_images = loaded_imgs;
            return info;
        }""")
        details["js_status"] = js_diagnosis

        if js_diagnosis.get("visible_elements", 0) < 10:
            symptoms.append(f"DOM 元素过少 ({js_diagnosis['visible_elements']} 个)")
        if js_diagnosis.get("ready_state") == "loading":
            symptoms.append("JS 仍在执行中")

        # 4. 检测网络请求失败情况
        failed_requests = [r for r in self._network_logs if r.get("status", 0) >= 400]
        details["failed_requests_count"] = len(failed_requests)
        if failed_requests:
            # 统计失败类型
            status_codes = [r.get("status") for r in failed_requests]
            details["failed_status_codes"] = status_codes[:10]
            if any(s == 403 for s in status_codes):
                symptoms.append(f"存在 {sum(1 for s in status_codes if s == 403)} 个 403 请求（WAF 拦截）")
            if any(s in (500, 502, 503, 504) for s in status_codes):
                symptoms.append("存在服务端错误响应 (5xx)")

        # 5. 检测 WebDriver 暴露情况
        try:
            wd_value = await page.evaluate("navigator.webdriver")
            if wd_value is not None and wd_value is not True:
                details["webdriver_hidden"] = True
            else:
                details["webdriver_hidden"] = False
                symptoms.append("navigator.webdriver 未被隐藏（可能被检测）")
        except Exception:
            pass

        # 6. 检测验证码元素
        captcha_selectors = [
            ".geetest_panel", ".geetest_radar_tip", "#captcha",
            ".verify-img-panel", ".tc-fg-group", ".yidun_bgimg",
            ".captcha-container", "[class*=captcha]", "[class*=geetest]",
            "[class*=verify]", "[id*=captcha]", "[id*=verify]",
        ]
        captcha_found = []
        for sel in captcha_selectors:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    captcha_found.append(sel)
            except Exception:
                continue
        if captcha_found:
            symptoms.append(f"检测到验证码组件: {', '.join(captcha_found[:3])}")
            details["captcha_elements"] = captcha_found

        # ── 综合判定根因 ──
        body_text = ""
        try:
            body_text = (await page.inner_text("body") or "").strip()
        except Exception:
            pass

        # 规则引擎：按优先级匹配根因
        if captcha_found:
            diagnosis = "captcha_required"
            confidence = 0.9
        elif any(kw in body_text for kw in ["安全验证", "滑块验证", "人机验证", "验证码"]):
            diagnosis = "anti_crawl"
            confidence = 0.85
        elif any(kw in body_text for kw in ["403 Forbidden", "Access Denied", "您的访问被限制", "当前网络环境异常"]):
            diagnosis = "network_blocked"
            confidence = 0.85
        elif health.get("is_blank") or health.get("body_len", 0) < 100:
            if js_diagnosis.get("visible_elements", 0) < 5:
                diagnosis = "blank_or_empty"
                confidence = 0.8
            else:
                diagnosis = "anti_crawl"
                confidence = 0.7
        elif details.get("redirect_info", {}).get("type") == "auth_redirect":
            diagnosis = "session_expired"
            confidence = 0.75
        elif len(failed_requests) > 5 and any(r.get("status") == 403 for r in failed_requests):
            diagnosis = "network_blocked"
            confidence = 0.8
        else:
            diagnosis = "unknown"
            confidence = 0.5

        # 获取建议的修复策略
        suggested_repair = self._REPAIR_STRATEGIES.get(diagnosis, [])

        logger.info(
            "页面诊断完成: %s (置信度 %.0f%%) — %s",
            diagnosis, confidence * 100,
            "; ".join(symptoms) if symptoms else "无明显问题",
        )

        return {
            "diagnosis": diagnosis,
            "confidence": confidence,
            "symptoms": symptoms,
            "details": details,
            "suggested_repair": suggested_repair,
        }

    # ── 修复方法实现 ────────────────────────────────────────

    async def _repair_wait_render(self, page, **kwargs) -> bool:
        """等待页面异步渲染完成（SPA 应用常见）。"""
        try:
            # 等待 body 内有足够多的可见元素
            await page.wait_for_function(
                "() => document.querySelectorAll('body *').length > 20",
                timeout=8000,
            )
            logger.info("[修复] 页面已渲染出足够元素")
            return True
        except Exception:
            logger.warning("[修复] 等待渲染超时")
            return False

    async def _repair_reinject_stealth(self, page, **kwargs) -> bool:
        """重新注入反检测脚本。"""
        from agent.core.anti_detect import STEALTH_SCRIPT
        try:
            await page.add_init_script(STEALTH_SCRIPT)
            # 注入后需要刷新才能生效
            await page.reload(wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(2)
            logger.info("[修复] 反检测脚本已重新注入并刷新页面")
            return True
        except Exception as e:
            logger.warning("[修复] 反检测脚本注入失败: %s", e)
            return False

    async def _repair_hard_reload(self, page, **kwargs) -> bool:
        """强制硬刷新（绕过缓存）。"""
        try:
            # 使用 JavaScript 强制刷新，绕过缓存
            await page.evaluate(
                "() => { location.reload(true); }"
            )
            await page.wait_for_load_state("domcontentloaded", timeout=20000)
            await asyncio.sleep(3)
            logger.info("[修复] 已执行硬刷新")
            return True
        except Exception as e:
            logger.warning("[修复] 硬刷新失败: %s", e)
            return False

    async def _repair_wait_js_ready(self, page, **kwargs) -> bool:
        """等待 JS 完全就绪。"""
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
            await asyncio.sleep(2)
            logger.info("[修复] JS 已完全就绪 (networkidle)")
            return True
        except Exception:
            # networkidle 超时再等一次 domcontentloaded
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
                await asyncio.sleep(5)
                logger.info("[修复] 等待超时但 DOM 已就绪")
                return True
            except Exception as e:
                logger.warning("[修复] 等待 JS 就绪失败: %s", e)
                return False

    async def _repair_renavigate(self, page, url="", **kwargs) -> bool:
        """重新导航到目标 URL。"""
        target = kwargs.get("target_url") or url
        if not target:
            target = page.url
        try:
            await page.goto(target, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(3)
            logger.info("[修复] 已重新导航到 %s", target[:60])
            return True
        except Exception as e:
            logger.warning("[修复] 重新导航失败: %s", e)
            return False

    async def _repair_wait_and_retry(self, page, **kwargs) -> bool:
        """等待一段时间后让浏览器自然恢复。"""
        delay_sec = kwargs.get("delay", 5)
        logger.info("[修复] 等待 %d 秒后检查...", delay_sec)
        await asyncio.sleep(delay_sec)
        return True  # 总是返回 True，让外层再次检测

    async def _repair_wait_for_captcha_solve(self, page, **kwargs) -> bool:
        """等待用户手动通过验证码。"""
        max_wait = kwargs.get("max_wait", 120)  # 最长等待 2 分钟
        logger.info("[修复] 等待用户手动处理验证码（最长 %d 秒）...", max_wait)

        # 定期检测验证码是否消失
        for i in range(max_wait // 5):
            await asyncio.sleep(5)
            # 检查验证码元素是否仍然可见
            still_visible = False
            for sel in [".geetest_panel", ".tc-fg-group", ".yidun_bgimg", ".captcha-container"]:
                try:
                    el = await page.query_selector(sel)
                    if el and await el.is_visible():
                        still_visible = True
                        break
                except Exception:
                    continue
            if not still_visible:
                logger.info("[修复] 验证码已通过")
                await asyncio.sleep(2)  # 验证码通过后等页面跳转
                return True
            if (i + 1) % 6 == 0:  # 每 30 秒提示一次
                logger.info("[修复] 仍在等待验证码... (%d/%d秒)", (i + 1) * 5, max_wait)

        logger.warning("[修复] 验证码等待超时 (%d 秒)", max_wait)
        return False

    async def _repair_break_redirect(self, page, **kwargs) -> bool:
        """打断重定向循环，直接导航到目标 URL。"""
        target = kwargs.get("target_url", "")
        if not target:
            logger.warning("[修复] 无法打断重定向：缺少目标 URL")
            return False
        try:
            # 先禁用所有事件监听器，防止重定向
            await page.evaluate("""
                () => {
                    // 拦截 location 变更
                    Object.defineProperty(window, 'location', {
                        configurable: true,
                        get: () => window.__originalLocation || window.location,
                    });
                }
            """)
            await page.goto(target, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(3)
            logger.info("[修复] 已打断重定向并重新导航")
            return True
        except Exception as e:
            logger.warning("[修复] 打断重定向失败: %s", e)
            return False

    async def _execute_repair(
        self,
        strategy: dict,
        page,
        target_url: str = "",
    ) -> tuple[bool, str]:
        """执行单个修复策略。

        Returns:
            (成功与否, 策略描述)
        """
        fn_name = strategy.get("fn", "")
        name = strategy.get("name", fn_name)
        repair_fn = getattr(self, fn_name, None)

        if repair_fn is None:
            logger.error("[修复] 未知修复方法: %s", fn_name)
            return False, f"{name} (方法不存在)"

        try:
            result = await repair_fn(page=page, target_url=target_url)
            status = "成功" if result else "失败"
            logger.info("[修复] 策略 [%s]: %s", name, status)
            return result, name
        except Exception as e:
            logger.error("[修复] 策略 [%s] 异常: %s", name, e)
            return False, f"{name} ({e})"

    async def auto_repair(
        self,
        url: str = "",
        max_repair_rounds: int = 3,
    ) -> dict[str, Any]:
        """自动诊断页面问题并尝试修复。

        流程：诊断 → 选择策略 → 执行修复 → 再次诊断 → 循环直到健康或达到上限

        Args:
            url: 原始目标 URL。
            max_repair_rounds: 最大修复轮次。

        Returns:
            {
                "repaired": bool,       # 最终是否修复成功
                "rounds": int,          # 实际执行的轮次
                "initial_diagnosis": dict,  # 初始诊断结果
                "final_health": dict,       # 最终健康状态
                "repairs_attempted": list,  # 尝试过的修复记录
            }
        """
        page = self._require_page()
        repairs_attempted: list[dict] = []

        # 第一步：初始诊断
        diag = await self.diagnose_page_issue(url=url)
        initial_diag = diag.copy()

        if diag["diagnosis"] == "normal":
            return {
                "repaired": True,
                "rounds": 0,
                "initial_diagnosis": initial_diag,
                "final_health": await self.detect_page_health(),
                "repairs_attempted": [],
            }

        logger.info(
            "=== 自动修复启动 === 诊断: %s (置信度 %.0f%%) | 症状: %s",
            diag["diagnosis"], diag["confidence"] * 100,
            "; ".join(diag["symptoms"])[:200],
        )

        strategies = diag.get("suggested_repair", [])
        if not strategies:
            logger.warning("无可用修复策略，诊断结果: %s", diag["diagnosis"])
            return {
                "repaired": False,
                "rounds": 0,
                "initial_diagnosis": initial_diag,
                "final_health": await self.detect_page_health(),
                "repairs_attempted": [],
            }

        # 第二步：按轮次执行修复
        strat_idx = 0
        for round_num in range(1, max_repair_rounds + 1):
            if strat_idx >= len(strategies):
                # 所有策略都试过了，从头再来一轮
                strat_idx = 0
                logger.info("[修复 第%d轮] 所有策略已遍历，重新开始", round_num)

            strategy = strategies[strat_idx]
            success, desc = await self._execute_repair(strategy, page, url)
            repairs_attempted.append({
                "round": round_num,
                "strategy": desc,
                "success": success,
            })

            # 修复后重新检测健康状态
            health = await self.detect_page_health()
            if health["healthy"]:
                logger.info(
                    "=== 修复成功 === 共 %d 轮, 最后策略: %s",
                    round_num, desc,
                )
                return {
                    "repaired": True,
                    "rounds": round_num,
                    "initial_diagnosis": initial_diag,
                    "final_health": health,
                    "repairs_attempted": repairs_attempted,
                }

            # 不健康则继续下一个策略
            strat_idx += 1
            logger.info(
                "[修复 第%d轮] 修复后仍未健康: %s",
                round_num, "; ".join(health.get("issues", []))[:100],
            )

        # 所有轮次用尽
        final_health = await self.detect_page_health()
        logger.error(
            "=== 修复失败 === 共尝试 %d 次, 最终状态: %s",
            len(repairs_attempted),
            "; ".join(final_health.get("issues", []))[:200],
        )
        return {
            "repaired": False,
            "rounds": len(repairs_attempted),
            "initial_diagnosis": initial_diag,
            "final_health": final_health,
            "repairs_attempted": repairs_attempted,
        }

    async def navigate_to(
        self,
        url: str,
        timeout: int = 30000,
        *,
        check_health: bool = True,
        auto_repair: bool = True,
        max_retries: int = 2,
    ) -> bool:
        """导航到指定 URL，可选自动诊断+修复页面问题。

        Args:
            url: 目标 URL。
            timeout: 导航超时（毫秒）。
            check_health: 导航后是否执行页面健康检测。
            auto_repair: 检测到问题时是否自动诊断并尝试修复。
            max_retries: 导航本身失败时的最大重试次数。
        """
        page = self._require_page()

        for attempt in range(1, max_retries + 1):
            try:
                self._console_logs = []
                self._network_logs = []
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            except _PLAYWRIGHT_ERRORS as e:
                exc_cls = classify_playwright_error(e)
                if exc_cls is NavigationTimeoutError:
                    logger.warning(
                        "导航到 %s 超时(%.0fs) [第%d/%d次]",
                        url[:80], timeout / 1000, attempt, max_retries,
                    )
                else:
                    logger.warning(
                        "导航到 %s 失败: %s [第%d/%d次]",
                        url[:80], e, attempt, max_retries,
                    )
                if attempt < max_retries:
                    await asyncio.sleep(2 * attempt)
                    continue
                return False

            # 健康检测
            if not check_health:
                return True

            health = await self.detect_page_health()
            if health["healthy"]:
                return True

            # 页面不健康：进入诊断+修复流程
            if auto_repair:
                logger.warning(
                    "页面不健康 [第%d次导航]，启动自动诊断与修复...",
                    attempt,
                )
                repair_result = await self.auto_repair(url=url)
                if repair_result["repaired"]:
                    logger.info(
                        "自动修复成功! 诊断=%s, 用时=%d轮",
                        repair_result["initial_diagnosis"].get("diagnosis"),
                        repair_result["rounds"],
                    )
                    return True
                else:
                    logger.error(
                        "自动修复失败: %s",
                        repair_result["final_health"].get("issues", []),
                    )
                    if attempt < max_retries:
                        await asyncio.sleep(3 * attempt)
                        continue
                    return False
            else:
                # 不自动修复，仅记录警告
                logger.warning(
                    "页面健康检测未通过 [第%d/%d次]: %s",
                    attempt, max_retries,
                    "; ".join(health["issues"]),
                )
                if attempt < max_retries:
                    await asyncio.sleep(2 * attempt)
                    continue

        return False

    async def get_dom_structure(self, selectors: list[str] | None = None) -> dict:
        page = self._require_page()
        result: dict = {"has_body": False, "body_len": 0}
        try:
            result["has_body"] = bool(await page.query_selector("body"))
            body = await page.query_selector("body")
            if body:
                result["body_len"] = len(await body.inner_text())
        except _PLAYWRIGHT_ERRORS:
            pass
        if selectors:
            for sel in selectors:
                try:
                    count = len(await page.query_selector_all(sel))
                    result[sel] = count
                except _PLAYWRIGHT_ERRORS:
                    result[sel] = "error"
        return result

    async def take_screenshot(self, path: str) -> bool:
        page = self._require_page()
        try:
            await page.screenshot(path=path)
            return True
        except _PLAYWRIGHT_ERRORS as e:
            exc_cls = classify_playwright_error(e)
            if exc_cls is BrowserCrashError:
                logger.error("浏览器崩溃: %s", e)
                raise exc_cls(f"浏览器崩溃: {e}") from e
            elif exc_cls is NavigationTimeoutError:
                logger.warning("截图超时: %s", e)
            else:
                logger.warning("截图失败: %s", e)
            return False

    @_handle_errors(default_return=None, crash_msg="获取HTML")
    async def get_page_html(self, max_len: int = 10000) -> str | None:
        """获取当前页面 HTML 源码，超长时截断。"""
        html = await self._require_page().content()
        return html[:max_len] if len(html) > max_len else html

    async def execute_js(self, expression: str, *args):
        """在页面上执行 JS 表达式，返回执行结果。

        支持通过 args 传递参数（Playwright 自动 JSON 序列化，避免注入）。
        """
        page = self._require_page()
        try:
            if args:
                result = await page.evaluate(expression, *args)
            else:
                result = await page.evaluate(expression)
            return {"result": result}
        except _PLAYWRIGHT_ERRORS as e:
            exc_cls = classify_playwright_error(e)
            if exc_cls is BrowserCrashError:
                logger.error("浏览器崩溃: %s", e)
                raise exc_cls(f"浏览器崩溃: {e}") from e
            logger.warning("JS执行失败: %s", e)
            return {"error": str(e)}

    async def query_element(self, selector: str,
                            attribute: str = "innerText") -> dict:
        """查询 DOM 元素并返回指定属性值。"""
        page = self._require_page()
        try:
            el = await page.query_selector(selector)
            if not el:
                return {"found": False, "selector": selector}
            if attribute == "innerText":
                text = await el.inner_text()
                return {"found": True, "selector": selector, "text": text}
            elif attribute == "outerHTML":
                html = await el.evaluate("el => el.outerHTML")
                return {"found": True, "selector": selector, "html": html}
            else:
                val = await el.get_attribute(attribute)
                return {"found": True, "selector": selector, "value": val}
        except _PLAYWRIGHT_ERRORS as e:
            exc_cls = classify_playwright_error(e)
            if exc_cls is BrowserCrashError:
                logger.error("浏览器崩溃: %s", e)
                raise exc_cls(f"浏览器崩溃: {e}") from e
            logger.warning("查询元素失败: %s", e)
            return {"error": str(e)}

    async def get_page_screenshot_bytes(self,
                                        full_page: bool = False) -> bytes | None:
        """截取页面截图，返回 PNG 字节数据（用于 base64 编码）。"""
        page = self._require_page()
        try:
            return await page.screenshot(type="png", full_page=full_page)
        except _PLAYWRIGHT_ERRORS as e:
            exc_cls = classify_playwright_error(e)
            if exc_cls is BrowserCrashError:
                logger.error("浏览器崩溃: %s", e)
                raise exc_cls(f"浏览器崩溃: {e}") from e
            logger.warning("截图失败: %s", e)
            return None

    @_handle_errors(default_return=False, crash_msg="滚动")
    async def scroll_page(self, delta_y: int = 500) -> bool:
        """滚动页面。delta_y 为正向下滚动，为负向上滚动。"""
        await self._require_page().evaluate(f"window.scrollBy(0, {delta_y})")
        return True

    async def wait_for_element(self, selector: str,
                               timeout: int = 10000) -> dict:
        """等待指定元素出现，返回结果。"""
        page = self._require_page()
        try:
            el = await page.wait_for_selector(selector, timeout=timeout)
            return {"found": el is not None, "selector": selector}
        except _PLAYWRIGHT_ERRORS as e:
            exc_cls = classify_playwright_error(e)
            if exc_cls is BrowserCrashError:
                logger.error("浏览器崩溃: %s", e)
                raise exc_cls(f"浏览器崩溃: {e}") from e
            return {"found": False, "selector": selector, "error": str(e)}

    @_handle_errors(default_return=False, crash_msg="按键")
    async def press_key(self, key: str = "Enter") -> bool:
        """模拟键盘按键。"""
        await self._require_page().keyboard.press(key)
        return True

    async def click_by_text(self, text: str, timeout: int = 5000) -> dict:
        """通过文本内容查找并点击元素。"""
        page = self._require_page()
        try:
            el = page.get_by_text(text, exact=False)
            await el.first.click(timeout=timeout)
            return {"clicked": True, "text": text}
        except _PLAYWRIGHT_ERRORS as e:
            exc_cls = classify_playwright_error(e)
            if exc_cls is BrowserCrashError:
                logger.error("浏览器崩溃: %s", e)
                raise exc_cls(f"浏览器崩溃: {e}") from e
            return {"clicked": False, "text": text, "error": str(e)}

    @_handle_errors(default_return=False, crash_msg="悬停")
    async def hover_selector(self, selector: str, timeout: int = 10000) -> bool:
        await self._require_page().hover(selector, timeout=timeout)
        return True

    @_handle_errors(default_return=False, crash_msg="选择选项")
    async def select_option_value(self, selector: str, value: str, timeout: int = 10000) -> bool:
        await self._require_page().select_option(selector, value, timeout=timeout)
        return True

    @_handle_errors(default_return=False, crash_msg="后退")
    async def go_back(self) -> bool:
        await self._require_page().go_back(wait_until="domcontentloaded")
        return True

    @_handle_errors(default_return=False, crash_msg="文件上传")
    async def set_file_inputs(self, selector: str, paths: list[str]) -> bool:
        await self._require_page().set_input_files(selector, paths)
        return True

    def get_console_logs(self, level: str = "info") -> list[dict]:
        levels = {"error": 0, "warning": 1, "info": 2, "debug": 3}
        min_level = levels.get(level, 2)
        result = []
        for log in self._console_logs:
            log_level = levels.get(log.get("type", "info"), 2)
            if log_level <= min_level:
                result.append(log)
        return result

    def get_network_logs(self, include_static: bool = False) -> list[dict]:
        if include_static:
            return list(self._network_logs)
        static_types = {"image", "font", "stylesheet", "media"}
        return [r for r in self._network_logs
                if r.get("resource_type", "") not in static_types]

    async def get_pending_dialog(self) -> dict | None:
        if self._pending_dialog:
            return {
                "type": self._pending_dialog.get("type"),
                "message": self._pending_dialog.get("message"),
                "default_value": self._pending_dialog.get("default_value"),
            }
        return None

    async def get_accessibility_snapshot(self) -> dict | None:
        page = self._require_page()
        try:
            tree = await page.accessibility.snapshot()
            if not tree:
                return {"role": "RootWebArea", "children": []}

            def flatten(node, depth=0, max_depth=10):
                if depth > max_depth:
                    return None
                entry = {
                    "role": node.get("role", ""),
                    "name": node.get("name", ""),
                    "value": node.get("value", ""),
                    "description": node.get("description", ""),
                    "focused": node.get("focused", False),
                    "focussable": node.get("focusable", False),
                    "depth": depth,
                }
                children = node.get("children", [])
                if isinstance(children, list):
                    flat_kids = []
                    for child in children:
                        kid = flatten(child, depth + 1, max_depth)
                        if kid:
                            flat_kids.append(kid)
                    entry["children"] = flat_kids
                return entry

            return flatten(tree)
        except Exception as e:
            logger.warning("无障碍树获取失败: %s", e)
            return None

    async def handle_dialog(self, accept: bool, prompt_text: str = "") -> bool:
        d = self._pending_dialog
        if d is None:
            return False
        dialog = d.get("_dialog")
        if dialog is None:
            return False
        try:
            if accept:
                await dialog.accept(prompt_text if prompt_text else None)
            else:
                await dialog.dismiss()
            self._pending_dialog = None
            return True
        except _PLAYWRIGHT_ERRORS as e:
            logger.warning("处理对话框失败: %s", e)
            return False

    async def save_cookies(self) -> list[dict]:
        """保存当前页面的 cookies。"""
        if not self._browser:
            return []
        try:
            ctx = self._browser
            if hasattr(ctx, 'cookies'):
                return await ctx.cookies()
            return []
        except _PLAYWRIGHT_ERRORS as e:
            exc_cls = classify_playwright_error(e)
            if exc_cls is BrowserCrashError:
                logger.error("浏览器崩溃: %s", e)
                raise exc_cls(f"浏览器崩溃: {e}") from e
            logger.warning("保存 cookies 失败: %s", e)
            return []

    async def load_cookies(self, cookies: list[dict]) -> bool:
        """恢复 cookies 到当前上下文。"""
        if not self._browser or not cookies:
            return False
        try:
            ctx = self._browser
            if hasattr(ctx, 'add_cookies'):
                await ctx.add_cookies(cookies)
                return True
            return False
        except _PLAYWRIGHT_ERRORS as e:
            exc_cls = classify_playwright_error(e)
            if exc_cls is BrowserCrashError:
                logger.error("浏览器崩溃: %s", e)
                raise exc_cls(f"浏览器崩溃: {e}") from e
            logger.warning("加载 cookies 失败: %s", e)
            return False

    async def save_local_storage(self) -> dict[str, str]:
        """保存当前页面的 localStorage。"""
        if not self._page:
            return {}
        try:
            return await self._page.evaluate(
                "JSON.stringify(window.localStorage)"
            )
        except _PLAYWRIGHT_ERRORS as e:
            exc_cls = classify_playwright_error(e)
            if exc_cls is BrowserCrashError:
                logger.error("浏览器崩溃: %s", e)
                raise exc_cls(f"浏览器崩溃: {e}") from e
            logger.warning("保存 localStorage 失败: %s", e)
            return {}

    async def load_local_storage(self, data: str) -> bool:
        """恢复 localStorage 数据。"""
        if not self._page or not data:
            return False
        try:
            await self._page.evaluate(f"""
                (() => {{
                    const data = JSON.parse({data!r});
                    for (const [k, v] of Object.entries(data)) {{
                        window.localStorage.setItem(k, v);
                    }}
                }})()
            """)
            return True
        except _PLAYWRIGHT_ERRORS as e:
            exc_cls = classify_playwright_error(e)
            if exc_cls is BrowserCrashError:
                logger.error("浏览器崩溃: %s", e)
                raise exc_cls(f"浏览器崩溃: {e}") from e
            logger.warning("加载 localStorage 失败: %s", e)
            return False

    async def get_interactive_elements(self) -> list[dict]:
        """提取页面中所有可交互元素及其唯一 CSS 选择器。"""
        if not self._page:
            return []
        try:
            return await self._page.evaluate("""
                (() => {
                    const interactiveTags = ['a', 'button', 'input', 'select',
                        'textarea'];
                    const results = [];
                    let refCounter = 1;

                    function buildSelector(el) {
                        if (el.id) return '#' + CSS.escape(el.id);
                        const path = [];
                        let current = el;
                        while (current && current !== document.body
                               && current !== document.documentElement) {
                            let tag = current.tagName.toLowerCase();
                            if (current.id) {
                                path.unshift('#' + CSS.escape(current.id));
                                break;
                            }
                            const parent = current.parentElement;
                            if (parent) {
                                const siblings = Array.from(parent.children);
                                const sameTag = siblings.filter(
                                    s => s.tagName === current.tagName);
                                if (sameTag.length > 1) {
                                    const idx = sameTag.indexOf(current) + 1;
                                    tag += ':nth-of-type(' + idx + ')';
                                }
                            }
                            path.unshift(tag);
                            current = parent;
                        }
                        return path.join(' > ');
                    }

                    function isInteractive(el) {
                        const tag = el.tagName.toLowerCase();
                        if (interactiveTags.includes(tag)) return true;
                        const role = el.getAttribute('role') || '';
                        if (['button','link','checkbox','radio','tab',
                            'menuitem','option'].includes(role)) return true;
                        if (el.hasAttribute('onclick')) return true;
                        const tab = el.getAttribute('tabindex');
                        if (tab && parseInt(tab) >= 0) return true;
                        if (el.isContentEditable) return true;
                        return false;
                    }

                    function walk(el) {
                        if (!el || !el.tagName) return;
                        if (isInteractive(el)) {
                            const sel = buildSelector(el);
                            if (sel) {
                                const text = (el.innerText || el.textContent
                                    || '').trim().substring(0, 120);
                                const placeholder = el.getAttribute('placeholder') || '';
                                const aria = el.getAttribute('aria-label') || '';
                                results.push({
                                    ref: '@e' + (refCounter++),
                                    tag: el.tagName.toLowerCase(),
                                    text: text,
                                    type: el.type || '',
                                    placeholder: placeholder,
                                    aria_label: aria,
                                    selector: sel,
                                    role: el.getAttribute('role') || '',
                                });
                            }
                            return;
                        }
                        for (let child of el.children) walk(child);
                    }

                    walk(document.body);
                    return results;
                })()
            """)
        except _PLAYWRIGHT_ERRORS as e:
            exc_cls = classify_playwright_error(e)
            if exc_cls is BrowserCrashError:
                logger.error("浏览器崩溃: %s", e)
                raise exc_cls(f"浏览器崩溃: {e}") from e
            logger.warning("获取可交互元素失败: %s", e)
            return []

    async def _setup_page_listeners(self, page):
        self._console_logs = []
        self._network_logs = []
        self._pending_dialog = None

        page.on("console", lambda msg: self._console_logs.append({
            "type": msg.type, "text": msg.text,
            "location": msg.location, "timestamp": time.time(),
        }) if self._console_logs is not None else None)

        page.on("dialog", lambda d: setattr(self, "_pending_dialog", {
            "type": d.type, "message": d.message,
            "default_value": d.default_value, "_dialog": d,
        }))

        page.on("request", lambda req: (
            len(self._network_logs) < 500 and self._network_logs.append({
                "url": req.url, "method": req.method,
                "resource_type": req.resource_type,
                "type": "request", "timestamp": time.time(),
            })
        ) if self._network_logs is not None else None)

        page.on("response", lambda res: (
            len(self._network_logs) < 500 and self._network_logs.append({
                "url": res.url, "status": res.status,
                "type": "response", "timestamp": time.time(),
            })
        ) if self._network_logs is not None else None)

    def _release_resources(self):
        """释放所有内部引用，确保不再持有浏览器资源。"""
        self._browser = None
        self._page = None
        self._is_running = False
        self._engine = None
        self._console_logs = []
        self._network_logs = []
        self._pending_dialog = None

    async def _safe_close_browser(self):
        try:
            await asyncio.wait_for(
                self._browser.__aexit__(None, None, None),
                timeout=10)
        except (asyncio.TimeoutError, RuntimeError, OSError):
            logger.warning("静默关闭浏览器超时或失败")

    async def stop(self) -> bool:
        if not self._is_running:
            return True
        try:
            if self._engine == "camoufox":
                async with asyncio.timeout(10):
                    await self._browser.__aexit__(None, None, None)
            else:
                async with asyncio.timeout(10):
                    ctx = getattr(self, "_browser", None)
                    if ctx is not None:
                        await ctx.close()
                    pw = getattr(self, "_pw", None)
                    if pw is not None:
                        await pw.stop()
            self._release_resources()
            logger.info("浏览器已关闭")
            return True
        except asyncio.TimeoutError:
            logger.warning("关闭浏览器超时，强制释放资源")
            self._release_resources()
            return False
        except (RuntimeError, OSError) as e:
            logger.warning("关闭浏览器异常: %s", e)
            self._release_resources()
            return False
