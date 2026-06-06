"""会话管理模块 — Cookie 持久化、状态保存与恢复。

提供浏览器会话的持久化存储能力，支持：
- Cookie 文件的读写
- 会话状态的保存与恢复
- 定时刷新机制
"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import aiofiles

from shared.delay import delay, get_delay
from shared.error_handler import classify_playwright_error, handle_session_error, safe_call
from shared.exceptions import BrowserCrashError
from shared.logging_config import get_logger

logger = get_logger("session")

COOKIE_DIR = Path(__file__).resolve().parent.parent / "sessions"


def _ensure_dir():
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)


def cookie_path(name: str = "boss") -> Path:
    """获取 Cookie 文件路径。"""
    return COOKIE_DIR / f"{name}_cookies.json"


def storage_state_path() -> Path:
    """获取 storage_state 文件路径。"""
    return COOKIE_DIR / "storage_state.json"


def session_profile_dir() -> Path:
    """创建并返回会话临时目录。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
    d = COOKIE_DIR / "profiles" / f"session_{ts}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _is_expired(cookie: dict) -> bool:
    expires = cookie.get("expires")
    if expires is None:
        return False
    try:
        exp = float(expires)
        if exp <= 0:
            return False
        return exp < time.time()
    except (ValueError, TypeError):
        return False


def filter_expired_cookies(cookies: list[dict]) -> list[dict]:
    """过滤已过期的 Cookie。"""
    valid = [c for c in cookies if not _is_expired(c)]
    removed = len(cookies) - len(valid)
    if removed:
        logger.info("过滤了 %d 个过期 Cookie", removed)
    return valid


@handle_session_error(default_return={"ok": False, "error": "保存 Cookie 失败"})
async def save_cookies_to_file(cookies: list[dict], name: str = "boss") -> dict:
    """保存 Cookie 到文件。"""
    _ensure_dir()
    path = cookie_path(name)
    filtered = filter_expired_cookies(cookies)
    data = {"cookies": filtered, "saved_at": datetime.now().isoformat()}
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=2))
    logger.info("已保存 %d 条 Cookie → %s (过滤掉 %d 条过期)", len(filtered), path, len(cookies) - len(filtered))
    return {"ok": True, "path": str(path), "count": len(filtered)}


@handle_session_error(default_return=[])
async def load_cookies_from_file(name: str = "boss") -> list[dict]:
    """从文件加载 Cookie。"""
    path = cookie_path(name)
    if not path.exists():
        logger.info("Cookie 文件不存在: %s", path)
        return []

    async with aiofiles.open(path, encoding="utf-8") as f:
        content = await f.read()
    data = json.loads(content)
    cookies = data.get("cookies", [])
    valid = filter_expired_cookies(cookies)
    expired_count = len(cookies) - len(valid)
    if expired_count:
        logger.warning("从 %s 加载了 %d 条 Cookie，其中 %d 条已过期已过滤", path, len(cookies), expired_count)
    else:
        logger.info("从 %s 加载了 %d 条 Cookie", path, len(cookies))
    return valid


def has_saved_cookies(name: str = "boss") -> bool:
    """检查是否已有保存的 Cookie 文件。"""
    return cookie_path(name).exists()


@handle_session_error(default_return={"ok": False, "error": "保存 storage_state 失败"})
async def save_storage_state(cookies: list[dict], origins: list[dict] | None = None) -> dict:
    """保存为 Playwright storage_state 兼容格式。"""
    _ensure_dir()
    path = storage_state_path()
    filtered = filter_expired_cookies(cookies)
    data = {"cookies": filtered, "origins": origins or []}
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=2))
    logger.info("已保存 storage_state → %s (%d 条 Cookie)", path, len(filtered))
    return {"ok": True, "path": str(path), "count": len(filtered)}


@handle_session_error(default_return=None)
async def load_storage_state() -> dict | None:
    """加载 Playwright storage_state 文件。"""
    path = storage_state_path()
    if not path.exists():
        return None

    async with aiofiles.open(path, encoding="utf-8") as f:
        content = await f.read()
    data = json.loads(content)
    cookies = data.get("cookies", [])
    valid = filter_expired_cookies(cookies)
    if len(valid) != len(cookies):
        data["cookies"] = valid
    return data


# ── Short-Lived Cookie Refresh ────────────────────────────────

# 短效 Cookie 配置：名称 → {典型有效期(秒), 刷新URL, 说明}
# 当 Cookie 剩余有效期不足 threshold_ratio 时，自动访问 refresh_url 获取新值
SHORT_LIVED_COOKIE_RULES: dict[str, dict] = {
    "acw_tc": {
        "typical_ttl": 86400,       # 24 小时（阿里云 WAF 令牌）
        "refresh_url": None,       # None 表示访问任意同域页面即可刷新
        "description": "阿里云 WAF 反爬令牌",
    },
}


def check_short_lived_cookies(
    cookies: list[dict],
    rules: dict[str, dict] | None = None,
    threshold_ratio: float = 0.2,
) -> list[dict]:
    """检查短效 Cookie 是否即将过期。

    Args:
        cookies: 当前 Cookie 列表。
        rules: 自定义规则，默认使用 SHORT_LIVED_COOKIE_RULES。
        threshold_ratio: 剩余有效期低于此比例时视为需刷新（0.2 = 剩余 < 20% 时触发）。

    Returns:
        需要刷新的 Cookie 信息列表，每项含 name、expires、remaining_sec、need_refresh。
    """
    _rules = rules or SHORT_LIVED_COOKIE_RULES
    now = time.time()
    stale = []
    for c in cookies:
        name = c.get("name", "")
        if name not in _rules:
            continue
        rule = _rules[name]
        expires = c.get("expires")
        if expires is None:
            continue
        try:
            exp = float(expires)
            if exp <= 0:
                continue
            ttl = rule["typical_ttl"]
            remaining = exp - now
            ratio = remaining / ttl if ttl > 0 else 1.0
            need_refresh = ratio < threshold_ratio or remaining <= 0
            stale.append({
                "name": name,
                "value_preview": (c.get("value", "")[:16] + "..."),
                "domain": c.get("domain", ""),
                "expires": expires,
                "remaining_sec": max(0, int(remaining)),
                "ratio": round(ratio, 2),
                "need_refresh": need_refresh,
                "description": rule["description"],
            })
        except (ValueError, TypeError):
            continue
    return stale


async def refresh_short_lived_cookies(
    page,
    target_url: str,
    rules: dict[str, dict] | None = None,
    timeout_ms: int | None = None,
) -> dict[str, Any]:
    """通过访问目标页面刷新短效 Cookie。

    访问页面后，WAF/CDN 会自动下发新的 acw_tc 等令牌。
    然后从浏览器上下文中提取最新 Cookie 并保存到 storage_state。

    Args:
        page: 已打开的 Playwright 页面对象。
        target_url: 要访问的目标 URL（如 https://www.qcc.com）。
        rules: 自定义规则。
        timeout_ms: 导航超时时间（毫秒），默认从配置获取。

    Returns:
        {"ok": bool, "refreshed": [...], "unchanged": [...], "error": str|None}
    """
    from shared.config import get_config  # pylint: disable=import-outside-toplevel

    _rules = rules or SHORT_LIVED_COOKIE_RULES
    rule_names = set(_rules.keys())

    # 获取配置的导航超时时间
    cfg = get_config()
    timeout = timeout_ms if timeout_ms is not None else cfg.get("session", {}).get("navigation_timeout", 20000)

    # 记录刷新前的 Cookie 快照
    try:
        old_cookies = await page.context.cookies()
        old_values = {c["name"]: c.get("value") for c in old_cookies}
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("获取旧 Cookie 失败，跳过对比: %s", e)
        return {"ok": False, "error": str(e), "refreshed": [], "unchanged": []}

    # 访问目标页面触发 WAF 下发新令牌
    try:
        await page.goto(target_url, wait_until="domcontentloaded", timeout=timeout)
        await delay("page_ready")
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("访问 %s 失败: %s", target_url, e)
        return {"ok": False, "error": f"导航失败: {e}", "refreshed": [], "unchanged": []}

    # 提取刷新后的 Cookie
    try:
        new_cookies = await page.context.cookies()
    except Exception as e:  # pylint: disable=broad-exception-caught
        return {"ok": False, "error": f"提取新 Cookie 失败: {e}", "refreshed": [], "unchanged": []}

    # 对比差异
    refreshed = []
    unchanged = []
    for c in new_cookies:
        name = c["name"]
        if name not in rule_names:
            continue
        new_val = c.get("value")
        old_val = old_values.get(name)
        if new_val != old_val:
            refreshed.append({
                "name": name,
                "domain": c.get("domain", ""),
                "new_value_preview": (new_val[:20] + "..."),
                "expires": c.get("expires"),
                "description": _rules[name]["description"],
            })
            logger.info("短效 Cookie [%s] 已刷新 → %s...", name, new_val[:12])
        else:
            unchanged.append({"name": name})

    # 自动保存更新后的 storage_state
    try:
        state = await page.context.storage_state()
        await save_storage_state(
            state.get("cookies", []),
            state.get("origins", []),
        )
        logger.info("已保存刷新后的 storage_state（含 %d 条 Cookie）", len(state.get("cookies", [])))
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("保存刷新后的 storage_state 失败: %s", e)

    return {
        "ok": True,
        "refreshed": refreshed,
        "unchanged": unchanged,
        "total_cookies": len(new_cookies),
        "error": None,
    }


# ── Smart Login Detection ─────────────────────────────────


class _PageProxy:
    """Thread-safe page wrapper for login detection polling."""

    def __init__(self, page):
        self._page = page

    @safe_call(default_return="")
    async def get_url(self) -> str:
        """获取当前页面 URL。"""
        return await self._page.evaluate("() => window.location.href") or ""

    @safe_call(default_return=[])
    async def get_cookies(self) -> list[dict]:
        """获取当前上下文的所有 Cookie。"""
        return await self._page.context.cookies()

    @safe_call(default_return=False)
    async def text_exists(self, text: str) -> bool:
        """检查指定文本是否在页面中可见。"""
        el = self._page.get_by_text(text, exact=False).first
        return await el.count() > 0 and await el.is_visible()

    @safe_call(default_return=False)
    async def selector_exists(self, selector: str) -> bool:
        """检查指定选择器是否在页面中可见。"""
        el = self._page.locator(selector).first
        return await el.count() > 0 and await el.is_visible()

    @safe_call(default_return=True)
    async def selector_disappeared(self, selector: str) -> bool:
        """检查指定选择器是否已从页面消失。"""
        el = self._page.locator(selector).first
        return await el.count() == 0


async def auto_detect_login(
    page,
    timeout: int = 120,  # noqa: ASYNC109
    interval: int | None = None,
    cookie_names: list[str] | None = None,
    custom_rules: dict | None = None,
    url_has_login: bool = True,
) -> dict[str, Any]:
    """智能检测登录状态变化。

    先等待页面渲染稳定后记录初始状态，然后轮询以下信号：
      1. URL 变化: 从含 login 的 URL 跳转至不含 login 的 URL
      2. Cookie 出现: 指定名称的 Cookie 出现（最高优先级，避免误报）
      3. DOM 出现: 用户信息元素出现（退出登录/头像等 — 高确定性）
      4. DOM 消失: 登录按钮/链接消失（仅当初始状态确认存在时触发）
      5. 自定义规则

    Args:
        page: Playwright page 对象
        timeout: 最大等待秒数（默认 120）
        interval: 轮询间隔秒数（默认 2）
        cookie_names: 检测的 Cookie 名称列表
        custom_rules: 自定义规则 dict:
            "url_trigger": URL 包含此子串时触发
            "dom_appear": 此选择器出现时触发
            "dom_disappear": 此选择器消失时触发（需先确认初始存在）
        url_has_login: 初始 URL 是否包含 login

    Returns:
        {"detected": bool, "reason": str, "detail": str}
    """
    proxy = _PageProxy(page)

    # 获取配置的轮询间隔，支持自定义覆盖
    poll_interval = interval if interval is not None else get_delay("login_poll")

    # 从配置中读取登录检测选择器
    from shared.config import get_config  # pylint: disable=import-outside-toplevel
    cfg = get_config()
    login_detection_cfg = cfg.get("session", {}).get("login_detection", {})

    USER_INDICATORS = login_detection_cfg.get("user_indicators", [  # pylint: disable=invalid-name
        "button:has-text('退出')",
        "a:has-text('退出')",
        "span:has-text('退出')",
        "button:has-text('登出')",
        "a:has-text('登出')",
        "span:has-text('登出')",
        "a[href*='user/center']",
        "a[href*='user_center']",
        ".top-user-name",
        ".login-user-name",
        ".header-user-name",
    ])
    LOGIN_BTN_TEXTS = login_detection_cfg.get(  # pylint: disable=invalid-name
        "login_button_texts", ["登录", "登入", "Sign in", "Log in"])
    LOGIN_BTN_SELECTOR = "button:has-text('{t}'), a:has-text('{t}'), span:has-text('{t}'), div:has-text('{t}')"  # pylint: disable=invalid-name

    if cookie_names is None:
        cookie_names = []
    if custom_rules is None:
        custom_rules = {}

    custom_url_trigger = custom_rules.get("url_trigger", "")
    custom_dom_appear = custom_rules.get("dom_appear", "")
    custom_dom_disappear = custom_rules.get("dom_disappear", "")

    # ── Phase 1: Wait for page to settle, capture initial state ──
    await delay("page_stable")
    initial_url = await proxy.get_url()
    initial_cookies = await proxy.get_cookies()
    initial_cookie_names = {c["name"] for c in initial_cookies}

    # Check if login button exists initially
    initial_login_btn_exists = False
    for t in LOGIN_BTN_TEXTS:
        try:
            sel = LOGIN_BTN_SELECTOR.format(t=t)
            if await proxy.selector_exists(sel):
                initial_login_btn_exists = True
                break
        except Exception:  # pylint: disable=broad-exception-caught
            continue

    # Check if already logged in initially
    for sel in USER_INDICATORS:
        try:
            if await proxy.selector_exists(sel):
                logger.info("初始状态即已登录: %s", sel)
                return {"detected": True, "reason": "already_logged_in",
                        "detail": f"初始检测到用户元素: {sel}"}
        except Exception:  # pylint: disable=broad-exception-caught
            continue

    logger.info("开始检测登录: url=%s, timeout=%ds, login_btn_exists=%s",
                initial_url, timeout, initial_login_btn_exists)

    started_at = time.time()
    while True:
        elapsed = time.time() - started_at
        if elapsed >= timeout:
            logger.warning("登录检测超时 (%ds)", timeout)
            return {"detected": False, "reason": "timeout",
                    "detail": f"等待 {timeout}s 未检测到登录"}

        current_url = await proxy.get_url()

        # ── Signal 1: URL change (login page → non-login page) ──
        if current_url and initial_url and url_has_login and \
        "login" in initial_url.lower() and "login" not in current_url.lower():
            logger.info("检测到登录: URL 从登录页跳转至 %s", current_url)
            return {"detected": True, "reason": "url_change",
                    "detail": f"URL 从登录页跳转至 {current_url}"}

        # ── Signal 2: Custom URL trigger ──
        if custom_url_trigger and current_url and \
        custom_url_trigger in current_url and custom_url_trigger not in initial_url:
            logger.info("检测到登录: URL 匹配 %s", custom_url_trigger)
            return {"detected": True, "reason": "custom",
                    "detail": f"URL 匹配自定义规则: {custom_url_trigger}"}

        # ── Signal 3: Cookie appearance (highest confidence) ──
        if cookie_names:
            try:
                current_cookies = await proxy.get_cookies()
                current_cnames = {c["name"] for c in current_cookies}
                _new_cookies = current_cnames - initial_cookie_names
                for target in cookie_names:
                    if target in current_cnames:
                        logger.info("检测到登录: Cookie %s 出现", target)
                        return {"detected": True, "reason": "cookie",
                                "detail": f"检测到 Cookie: {target}"}
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        # ── Signal 4: DOM appearance (user elements — high confidence) ──
        for sel in USER_INDICATORS:
            try:
                if await proxy.selector_exists(sel):
                    logger.info("检测到登录: 用户元素 %s", sel)
                    return {"detected": True, "reason": "dom_appeared",
                            "detail": f"检测到用户元素: {sel}"}
            except Exception:  # pylint: disable=broad-exception-caught
                continue

        # ── Signal 5: Login button disappeared (only if we confirmed it existed) ──
        if initial_login_btn_exists:
            still_exists = False
            for t in LOGIN_BTN_TEXTS:
                try:
                    sel = LOGIN_BTN_SELECTOR.format(t=t)
                    if await proxy.selector_exists(sel):
                        still_exists = True
                        break
                except Exception:  # pylint: disable=broad-exception-caught
                    continue
            if not still_exists:
                logger.info("检测到登录: 登录按钮消失")
                return {"detected": True, "reason": "dom_disappeared",
                        "detail": "登录按钮/链接从页面消失"}

        # ── Signal 6: Custom DOM rules ──
        if custom_dom_appear:
            try:
                if await proxy.selector_exists(custom_dom_appear):
                    logger.info("检测到登录: 自定义元素 %s", custom_dom_appear)
                    return {"detected": True, "reason": "custom",
                            "detail": f"自定义元素出现: {custom_dom_appear}"}
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        if custom_dom_disappear and initial_login_btn_exists:
            try:
                if await proxy.selector_disappeared(custom_dom_disappear):
                    logger.info("检测到登录: 自定义元素消失 %s", custom_dom_disappear)
                    return {"detected": True, "reason": "custom",
                            "detail": f"自定义元素消失: {custom_dom_disappear}"}
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        await asyncio.sleep(poll_interval)


def cleanup_old_profiles(max_age_days: int | None = None):
    """清理超过指定天数的旧会话目录。"""
    from shared.config import get_config  # pylint: disable=import-outside-toplevel

    cfg = get_config()
    days = max_age_days if max_age_days is not None else (
        cfg.get("session", {}).get("cleanup", {}).get("max_age_days", 7)
    )

    profiles_dir = COOKIE_DIR / "profiles"
    if not profiles_dir.exists():
        return
    now = datetime.now()
    removed = 0
    for d in profiles_dir.iterdir():
        if d.is_dir():
            age = now - datetime.fromtimestamp(d.stat().st_mtime)
            if age.days >= days:
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
    if removed:
        logger.info("已清理 %d 个过期 Session 目录", removed)


# ── SessionManager ─────────────────────────────────────────

class SessionManager:
    """管理浏览器会话的 Cookie、localStorage 和可交互元素。

    从 BrowserController 中提取出来的纯会话管理层，
    通过 page_accessor 与实际的浏览器页面解耦。
    """

    def __init__(self, page_accessor):
        """初始化 SessionManager。

        Args:
            page_accessor: 返回 page 的可调用对象，或直接的 page 对象，
                           或具有 .page 属性的 BrowserController 实例。
        """
        self._page_accessor = page_accessor

    def _get_page(self):
        """获取当前的 Playwright page 实例。"""
        if callable(self._page_accessor):
            return self._page_accessor()
        # 支持 BrowserController 风格（有 .page 属性）
        if hasattr(self._page_accessor, "page"):
            return self._page_accessor.page
        return self._page_accessor

    def _get_context(self):
        """获取当前的 browser context。"""
        page = self._get_page()
        if page:
            return page.context
        return None

    async def save_cookies(self) -> list[dict]:
        """保存当前页面的 cookies。"""
        ctx = self._get_context()
        if not ctx:
            return []
        try:
            if hasattr(ctx, 'cookies'):
                return await ctx.cookies()
            return []
        except Exception as e:  # pylint: disable=broad-exception-caught
            exc_cls = classify_playwright_error(e)
            if exc_cls is BrowserCrashError:
                logger.error("浏览器崩溃: %s", e)
                raise exc_cls(f"浏览器崩溃: {e}") from e
            logger.warning("保存 cookies 失败: %s", e)
            return []

    async def load_cookies(self, cookies: list[dict]) -> bool:
        """恢复 cookies 到当前上下文。"""
        if not cookies:
            return False
        ctx = self._get_context()
        if not ctx:
            return False
        try:
            if hasattr(ctx, 'add_cookies'):
                await ctx.add_cookies(cookies)
                return True
            return False
        except Exception as e:  # pylint: disable=broad-exception-caught
            exc_cls = classify_playwright_error(e)
            if exc_cls is BrowserCrashError:
                logger.error("浏览器崩溃: %s", e)
                raise exc_cls(f"浏览器崩溃: {e}") from e
            logger.warning("加载 cookies 失败: %s", e)
            return False

    async def save_local_storage(self) -> dict[str, str]:
        """保存当前页面的 localStorage。"""
        page = self._get_page()
        if not page:
            return {}
        try:
            return await page.evaluate(
                "JSON.stringify(window.localStorage)"
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            exc_cls = classify_playwright_error(e)
            if exc_cls is BrowserCrashError:
                logger.error("浏览器崩溃: %s", e)
                raise exc_cls(f"浏览器崩溃: {e}") from e
            logger.warning("保存 localStorage 失败: %s", e)
            return {}

    async def load_local_storage(self, data: str) -> bool:
        """恢复 localStorage 数据。"""
        if not data:
            return False
        page = self._get_page()
        if not page:
            return False
        try:
            await page.evaluate(f"""
                (() => {{
                    const data = JSON.parse({data!r});
                    for (const [k, v] of Object.entries(data)) {{
                        window.localStorage.setItem(k, v);
                    }}
                }})()
            """)
            return True
        except Exception as e:  # pylint: disable=broad-exception-caught
            exc_cls = classify_playwright_error(e)
            if exc_cls is BrowserCrashError:
                logger.error("浏览器崩溃: %s", e)
                raise exc_cls(f"浏览器崩溃: {e}") from e
            logger.warning("加载 localStorage 失败: %s", e)
            return False

    async def get_interactive_elements(self) -> list[dict]:
        """提取页面中所有可交互元素及其唯一 CSS 选择器。"""
        page = self._get_page()
        if not page:
            return []
        try:
            return await page.evaluate("""
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
        except Exception as e:  # pylint: disable=broad-exception-caught
            exc_cls = classify_playwright_error(e)
            if exc_cls is BrowserCrashError:
                logger.error("浏览器崩溃: %s", e)
                raise exc_cls(f"浏览器崩溃: {e}") from e
            logger.warning("获取可交互元素失败: %s", e)
            return []
