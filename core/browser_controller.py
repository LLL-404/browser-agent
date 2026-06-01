"""浏览器控制器 — 支持 Camoufox（C++引擎）和 Playwright（JS引擎）双引擎回退。

优先使用 Camoufox 获得 C++ 级别的反检测能力，不可用时回退到 Playwright。
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol, TYPE_CHECKING, runtime_checkable

from playwright.async_api import async_playwright

from .anti_detect import build_browser_kwargs
from .config import get_config
from .error_handler import classify_playwright_error
from .exceptions import (
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
from .logging_config import get_logger
from .selectors import DOM_STRUCTURE_SELECTORS

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


class BrowserController:
    """统一管理浏览器生命周期并提供常用页面操作。"""

    def __init__(self):
        self._browser: _BrowserLike | None = None
        self._page: _Page | None = None
        self._pw: Any | None = None
        self._engine: str | None = None
        self._is_running: bool = False
        self._has_camoufox: bool = HAS_CAMOUFOX

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
            from .fingerprint_manager import generate_camoufox_opts
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
                from .cookie_manager import (cleanup_old_profiles,
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

            from .cookie_manager import (has_saved_cookies,
                                         load_cookies_from_file)
            if has_saved_cookies():
                cookies = load_cookies_from_file()
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
            raise

    async def _start_playwright(self, headless: bool) -> bool:
        try:
            self._pw = await async_playwright().__aenter__()

            cfg = get_config()
            kwargs = build_browser_kwargs(cfg, headless)

            self._browser = await self._pw.chromium.launch_persistent_context(**kwargs)
            self._page = self._browser.pages[0] if self._browser.pages else await self._browser.new_page()
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

    async def navigate_to(self, url: str, timeout: int = 30000) -> bool:
        page = self._require_page()
        try:
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

    async def get_page_text(self, max_len: int = 2000) -> str:
        page = self._require_page()
        try:
            text = await page.inner_text("body")
            return text[:max_len] if text else ""
        except _PLAYWRIGHT_ERRORS as e:
            exc_cls = classify_playwright_error(e)
            if exc_cls is BrowserCrashError:
                logger.error("浏览器崩溃: %s", e)
                raise exc_cls(f"浏览器崩溃: {e}") from e
            logger.warning("获取页面文本失败: %s", e)
            return ""

    async def get_page_title(self) -> str:
        page = self._require_page()
        try:
            return await page.title() or ""
        except _PLAYWRIGHT_ERRORS as e:
            exc_cls = classify_playwright_error(e)
            if exc_cls is BrowserCrashError:
                logger.error("浏览器崩溃: %s", e)
                raise exc_cls(f"浏览器崩溃: {e}") from e
            logger.warning("获取页面标题失败: %s", e)
            return ""

    async def get_current_url(self) -> str:
        page = self._require_page()
        try:
            return page.url
        except _PLAYWRIGHT_ERRORS as e:
            exc_cls = classify_playwright_error(e)
            if exc_cls is BrowserCrashError:
                logger.error("浏览器崩溃: %s", e)
                raise exc_cls(f"浏览器崩溃: {e}") from e
            logger.warning("获取当前URL失败: %s", e)
            return ""

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

    async def get_dom_structure(self) -> dict:
        page = self._require_page()
        result = {}
        for sel in DOM_STRUCTURE_SELECTORS:
            try:
                count = len(await page.query_selector_all(sel))
                result[sel] = count
            except _PLAYWRIGHT_ERRORS as e:
                exc_cls = classify_playwright_error(e)
                if exc_cls is BrowserCrashError:
                    logger.error("浏览器崩溃: %s", e)
                    raise exc_cls(f"浏览器崩溃: {e}") from e
                logger.warning("查询 DOM 选择器 %s 失败: %s", sel, e)
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

    async def get_page_html(self, max_len: int = 10000) -> str | None:
        """获取当前页面 HTML 源码，超长时截断。"""
        page = self._require_page()
        try:
            html = await page.content()
            return html[:max_len] if len(html) > max_len else html
        except _PLAYWRIGHT_ERRORS as e:
            exc_cls = classify_playwright_error(e)
            if exc_cls is BrowserCrashError:
                logger.error("浏览器崩溃: %s", e)
                raise exc_cls(f"浏览器崩溃: {e}") from e
            logger.warning("获取HTML失败: %s", e)
            return None

    async def execute_js(self, expression: str):
        """在页面上执行 JS 表达式，返回执行结果。"""
        page = self._require_page()
        try:
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

    async def scroll_page(self, delta_y: int = 500) -> bool:
        """滚动页面。delta_y 为正向下滚动，为负向上滚动。"""
        page = self._require_page()
        try:
            await page.evaluate(f"window.scrollBy(0, {delta_y})")
            return True
        except _PLAYWRIGHT_ERRORS as e:
            exc_cls = classify_playwright_error(e)
            if exc_cls is BrowserCrashError:
                logger.error("浏览器崩溃: %s", e)
                raise exc_cls(f"浏览器崩溃: {e}") from e
            logger.warning("滚动失败: %s", e)
            return False

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

    async def press_key(self, key: str = "Enter") -> bool:
        """模拟键盘按键。"""
        page = self._require_page()
        try:
            await page.keyboard.press(key)
            return True
        except _PLAYWRIGHT_ERRORS as e:
            exc_cls = classify_playwright_error(e)
            if exc_cls is BrowserCrashError:
                logger.error("浏览器崩溃: %s", e)
                raise exc_cls(f"浏览器崩溃: {e}") from e
            logger.warning("按键 %s 失败: %s", key, e)
            return False

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

    def _release_resources(self):
        """释放所有内部引用，确保不再持有浏览器资源。"""
        self._browser = None
        self._page = None
        self._is_running = False
        self._engine = None

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
                        await pw.__aexit__(None, None, None)
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
