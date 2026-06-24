"""浏览器控制器 — 基于 Camoufox（C++引擎）的浏览器自动化。

Camoufox 在 C++ 引擎层面提供反检测能力，底层使用 Playwright Page API。
"""

from __future__ import annotations

import asyncio
import functools
from typing import TYPE_CHECKING, Any

from browser_agent.core.health_monitor import HealthMonitor
from browser_agent.core.log_collector import LogCollector
from browser_agent.core.session import SessionManager
from shared.error_handler import classify_playwright_error
from shared.exceptions import (
    BrowserCrashError,
    ElementNotFoundError,
    ElementNotInteractableError,
    NavigationTimeoutError,
    PageNotReadyError,
)
from shared.logging_config import get_logger

if TYPE_CHECKING:
    from playwright.async_api import Page as _Page


from camoufox import AsyncCamoufox
from camoufox.addons import DefaultAddons

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
        self._browser: AsyncCamoufox | None = None
        self._page: _Page | None = None
        self._engine: str | None = "camoufox"
        self._is_running: bool = False
        # 子模块（组合模式）
        self._log_collector = LogCollector()
        self._health_monitor = HealthMonitor(self)
        self._session_manager = SessionManager(self)
        # 向后兼容属性（委托给 LogCollector）
        self._console_logs = self._log_collector._console_logs
        self._network_logs = self._log_collector._network_logs
        self._pending_dialog = self._log_collector._pending_dialog

    def _require_page(self) -> _Page:
        """确保页面已初始化，否则抛出 PageNotReadyError。"""
        if not self._page:
            raise PageNotReadyError(
                "页面未初始化，请先调用 start() 启动浏览器",
                error_code="PAGE_NOT_READY",
            )
        return self._page

    def require_page(self) -> _Page:
        """确保页面已初始化，否则抛出 PageNotReadyError。公共接口。"""
        return self._require_page()

    @property
    def engine(self) -> str | None:
        """返回当前已启动的浏览器引擎名称。"""
        return self._engine

    @property
    def is_running(self) -> bool:
        """返回浏览器是否处于运行状态。"""
        return self._is_running

    async def start(self, headless: bool = False,
                    profile_name: str | None = None) -> bool:
        """启动 Camoufox 浏览器。

        Args:
            headless: 是否以无头模式启动。
            profile_name: 持久化 profile 名称（如 "zhipin"），
                          启用后浏览器状态会跨重启保留。
        """
        if self._is_running:
            return True

        try:
            result = await self._start_camoufox(headless, profile_name=profile_name)
            if result:
                self._engine = "camoufox"
                self._is_running = True
                logger.info("Camoufox 启动成功")
            return result
        except (RuntimeError, OSError, AttributeError) as e:
            logger.error("Camoufox 启动异常: %s", e)
            return False

    async def _start_camoufox(self, headless: bool,
                              profile_name: str | None = None) -> bool:
        try:
            from shared.fingerprint_manager import generate_camoufox_opts  # pylint: disable=import-outside-toplevel
            opts = {
                "headless": headless,
                "humanize": True,
                "geoip": False,  # GeoIP 数据库缺失，暂时关闭
                "block_images": False,
                "enable_cache": False,
                "exclude_addons": [DefaultAddons.UBO],
                **generate_camoufox_opts(),
            }
            if profile_name:
                from browser_agent.core.session import persistent_profile_dir  # pylint: disable=import-outside-toplevel
                udir = persistent_profile_dir(profile_name)
                opts["user_data_dir"] = str(udir)
                opts["persistent_context"] = True
            elif not headless:
                from browser_agent.core.session import (  # pylint: disable=import-outside-toplevel
                    cleanup_old_profiles,
                    session_profile_dir,
                )
                udir = session_profile_dir()
                opts["user_data_dir"] = str(udir)
                opts["persistent_context"] = True
                cleanup_old_profiles()
            else:
                opts["persistent_context"] = False
            logger.info("正在启动 Camoufox (headless=%s)...", headless)
            self._browser = await AsyncCamoufox(**opts).__aenter__()  # pylint: disable=unnecessary-dunder-call

            # 先尝试获取已有的页面（避免持久化会话恢复导致多个标签页）
            try:
                pages = getattr(self._browser, 'pages', None)
                if pages and isinstance(pages, list) and pages:
                    self._page = pages[0]
                    # 关闭多余的初始页面
                    for page in pages:
                        if page != self._page:
                            await page.close()
                else:
                    self._page = await self._browser.new_page()
            except Exception:  # pylint: disable=broad-exception-caught
                # 如果获取 pages 失败，回退到创建新页面
                self._page = await self._browser.new_page()

            await self._setup_page_listeners(self._page)

            from browser_agent.core.session import (  # pylint: disable=import-outside-toplevel
                has_saved_cookies,
                load_cookies_from_file,
            )
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

    async def click_selector(self, selector: str, timeout: int = 10000) -> bool:
        """通过 CSS 选择器点击元素。"""
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
        """查找指定选择器是否存在。"""
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
        """向输入框填充文本。"""
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
        """获取页面可见文本内容。"""
        text = await self._require_page().inner_text("body")
        return text[:max_len] if text else ""

    @_handle_errors(default_return="", crash_msg="获取页面标题")
    async def get_page_title(self) -> str:
        """获取页面标题。"""
        return await self._require_page().title() or ""

    @_handle_errors(default_return="", crash_msg="获取当前URL")
    async def get_current_url(self) -> str:
        """获取当前页面 URL。"""
        return self._require_page().url

    async def get_detection_status(self) -> dict:
        """获取反检测状态检查结果。"""
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

    async def detect_page_health(self) -> dict[str, Any]:
        """检测当前页面是否为空白页、被反爬拦截或加载异常。

        Returns:
            包含 healthy/is_blank/issues/url/title/body_len/has_body 的诊断字典。
        """
        return await self._health_monitor.detect_page_health()

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
        return await self._health_monitor.diagnose_page_issue(url=url)

    # ── 修复方法实现 ────────────────────────────────────────

    async def _repair_wait_render(self, page, **kwargs) -> bool:
        """等待页面异步渲染完成（SPA 应用常见）。"""
        return await self._health_monitor._repair_wait_render(page=page, **kwargs)  # pylint: disable=protected-access

    async def _repair_reinject_stealth(self, page, **kwargs) -> bool:
        """重新注入反检测脚本。"""
        return await self._health_monitor._repair_reinject_stealth(page=page, **kwargs)  # pylint: disable=protected-access

    async def _repair_hard_reload(self, page, **kwargs) -> bool:
        """强制硬刷新（绕过缓存）。"""
        return await self._health_monitor._repair_hard_reload(page=page, **kwargs)  # pylint: disable=protected-access

    async def _repair_wait_js_ready(self, page, **kwargs) -> bool:
        """等待 JS 完全就绪。"""
        return await self._health_monitor._repair_wait_js_ready(page=page, **kwargs)  # pylint: disable=protected-access

    async def _repair_renavigate(self, page, url="", **kwargs) -> bool:
        """重新导航到目标 URL。"""
        return await self._health_monitor._repair_renavigate(page=page, url=url, **kwargs)  # pylint: disable=protected-access

    async def _repair_wait_and_retry(self, page, **kwargs) -> bool:
        """等待一段时间后让浏览器自然恢复。"""
        return await self._health_monitor._repair_wait_and_retry(page=page, **kwargs)  # pylint: disable=protected-access

    async def _repair_wait_for_captcha_solve(self, page, **kwargs) -> bool:
        """等待用户手动通过验证码。"""
        return await self._health_monitor._repair_wait_for_captcha_solve(page=page, **kwargs)  # pylint: disable=protected-access

    async def _repair_break_redirect(self, page, **kwargs) -> bool:
        """打断重定向循环，直接导航到目标 URL。"""
        return await self._health_monitor._repair_break_redirect(page=page, **kwargs)  # pylint: disable=protected-access

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
        return await self._health_monitor._execute_repair(  # pylint: disable=protected-access
            strategy=strategy, page=page, target_url=target_url,
        )

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
        return await self._health_monitor.auto_repair(url=url, max_repair_rounds=max_repair_rounds)

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

                logger.error(
                    "自动修复失败: %s",
                    repair_result["final_health"].get("issues", []),
                )
                if attempt < max_retries:
                    await asyncio.sleep(3 * attempt)
                    continue
                return False

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
        """获取页面 DOM 结构信息。"""
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
        """保存页面截图到指定路径。"""
        page = self._require_page()
        try:
            await page.screenshot(path=path)
            return True
        except _PLAYWRIGHT_ERRORS as e:
            exc_cls = classify_playwright_error(e)
            if exc_cls is BrowserCrashError:
                logger.error("浏览器崩溃: %s", e)
                raise exc_cls(f"浏览器崩溃: {e}") from e
            if exc_cls is NavigationTimeoutError:
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
            if attribute == "outerHTML":
                html = await el.evaluate("el => el.outerHTML")
                return {"found": True, "selector": selector, "html": html}
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
        """悬停到指定元素上。"""
        await self._require_page().hover(selector, timeout=timeout)
        return True

    @_handle_errors(default_return=False, crash_msg="选择选项")
    async def select_option_value(self, selector: str, value: str, timeout: int = 10000) -> bool:
        """选择下拉框选项。"""
        await self._require_page().select_option(selector, value, timeout=timeout)
        return True

    @_handle_errors(default_return=False, crash_msg="后退")
    async def go_back(self) -> bool:
        """返回上一页。"""
        await self._require_page().go_back(wait_until="domcontentloaded")
        return True

    @_handle_errors(default_return=False, crash_msg="文件上传")
    async def set_file_inputs(self, selector: str, paths: list[str]) -> bool:
        """设置文件上传。"""
        await self._require_page().set_input_files(selector, paths)
        return True

    def get_console_logs(self, level: str = "info") -> list[dict]:
        """获取控制台日志。"""
        return self._log_collector.get_console_logs(level=level)

    def get_network_logs(self, include_static: bool = False) -> list[dict]:
        """获取网络请求日志。"""
        return self._log_collector.get_network_logs(include_static=include_static)

    async def get_pending_dialog(self) -> dict | None:
        """获取待处理的对话框。"""
        return await self._log_collector.get_pending_dialog()

    async def get_accessibility_snapshot(self) -> dict | None:
        """获取可访问性快照。"""
        return await self._log_collector.get_accessibility_snapshot()

    async def handle_dialog(self, accept: bool, prompt_text: str = "") -> bool:
        """处理浏览器对话框。"""
        return await self._log_collector.handle_dialog(accept=accept, prompt_text=prompt_text)

    async def save_cookies(self) -> list[dict]:
        """保存当前页面的 cookies。"""
        return await self._session_manager.save_cookies()

    async def load_cookies(self, cookies: list[dict]) -> bool:
        """恢复 cookies 到当前上下文。"""
        return await self._session_manager.load_cookies(cookies=cookies)

    async def save_local_storage(self) -> dict[str, str]:
        """保存当前页面的 localStorage。"""
        return await self._session_manager.save_local_storage()

    async def load_local_storage(self, data: str) -> bool:
        """恢复 localStorage 数据。"""
        return await self._session_manager.load_local_storage(data=data)

    async def get_interactive_elements(self) -> list[dict]:
        """提取页面中所有可交互元素及其唯一 CSS 选择器。"""
        return await self._session_manager.get_interactive_elements()

    async def _setup_page_listeners(self, page):
        self._log_collector._setup_page_listeners(page)  # pylint: disable=protected-access
        self._log_collector.page = page

    def _release_resources(self):
        """释放所有内部引用，确保不再持有浏览器资源。"""
        self._browser = None
        self._page = None
        self._is_running = False

    async def _safe_close_browser(self):
        try:
            await asyncio.wait_for(
                self._browser.__aexit__(None, None, None),
                timeout=10)
        except (TimeoutError, RuntimeError, OSError):
            logger.warning("静默关闭浏览器超时或失败")

    async def stop(self) -> bool:
        """停止浏览器并释放资源。"""
        if not self._is_running:
            return True
        try:
            async with asyncio.timeout(10):
                await self._browser.__aexit__(None, None, None)
            self._release_resources()
            logger.info("浏览器已关闭")
            return True
        except TimeoutError:
            logger.warning("关闭浏览器超时，强制释放资源")
            self._release_resources()
            return False
        except (RuntimeError, OSError) as e:
            logger.warning("关闭浏览器异常: %s", e)
            self._release_resources()
            return False
