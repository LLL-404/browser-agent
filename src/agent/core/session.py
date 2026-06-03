from __future__ import annotations

import asyncio
import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import aiofiles
from shared.delay import delay
from shared.logging_config import get_logger

logger = get_logger("session")

COOKIE_DIR = Path(__file__).resolve().parent.parent / "sessions"


def _ensure_dir():
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)


def cookie_path(name: str = "boss") -> Path:
    return COOKIE_DIR / f"{name}_cookies.json"


def storage_state_path() -> Path:
    return COOKIE_DIR / "storage_state.json"


def session_profile_dir() -> Path:
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
    valid = [c for c in cookies if not _is_expired(c)]
    removed = len(cookies) - len(valid)
    if removed:
        logger.info("过滤了 %d 个过期 Cookie", removed)
    return valid


async def save_cookies_to_file(cookies: list[dict], name: str = "boss") -> dict:
    _ensure_dir()
    path = cookie_path(name)
    filtered = filter_expired_cookies(cookies)
    data = {"cookies": filtered, "saved_at": datetime.now().isoformat()}
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=2))
    logger.info("已保存 %d 条 Cookie → %s (过滤掉 %d 条过期)", len(filtered), path, len(cookies) - len(filtered))
    return {"ok": True, "path": str(path), "count": len(filtered)}


async def load_cookies_from_file(name: str = "boss") -> list[dict]:
    path = cookie_path(name)
    if not path.exists():
        logger.info("Cookie 文件不存在: %s", path)
        return []
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
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
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("加载 Cookie 文件失败: %s", e)
        return []


def has_saved_cookies(name: str = "boss") -> bool:
    return cookie_path(name).exists()


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


async def load_storage_state() -> dict | None:
    """加载 Playwright storage_state 文件。"""
    path = storage_state_path()
    if not path.exists():
        return None
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()
        data = json.loads(content)
        cookies = data.get("cookies", [])
        valid = filter_expired_cookies(cookies)
        if len(valid) != len(cookies):
            data["cookies"] = valid
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("加载 storage_state 失败: %s", e)
        return None


# ── Smart Login Detection ─────────────────────────────────


class _PageProxy:
    """Thread-safe page wrapper for login detection polling."""

    def __init__(self, page):
        self._page = page

    async def _safe_call(self, fn, default=None):
        try:
            return await fn()
        except Exception:
            return default

    async def get_url(self) -> str:
        return await self._safe_call(self._page.evaluate, "() => window.location.href") or ""

    async def get_cookies(self) -> list[dict]:
        try:
            return await self._page.context.cookies()
        except Exception:
            return []

    async def text_exists(self, text: str) -> bool:
        try:
            el = self._page.get_by_text(text, exact=False).first
            return await el.count() > 0 and await el.is_visible()
        except Exception:
            return False

    async def selector_exists(self, selector: str) -> bool:
        try:
            el = self._page.locator(selector).first
            return await el.count() > 0 and await el.is_visible()
        except Exception:
            return False

    async def selector_disappeared(self, selector: str) -> bool:
        try:
            el = self._page.locator(selector).first
            return await el.count() == 0
        except Exception:
            return True


async def auto_detect_login(
    page,
    timeout: int = 120,
    interval: int = 2,
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

    USER_INDICATORS = [
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
    ]
    LOGIN_BTN_TEXTS = ["登录", "登入", "Sign in", "Log in"]
    LOGIN_BTN_SELECTOR = "button:has-text('{t}'), a:has-text('{t}'), span:has-text('{t}'), div:has-text('{t}')"

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
        except Exception:
            continue

    # Check if already logged in initially
    for sel in USER_INDICATORS:
        try:
            if await proxy.selector_exists(sel):
                logger.info("初始状态即已登录: %s", sel)
                return {"detected": True, "reason": "already_logged_in",
                        "detail": f"初始检测到用户元素: {sel}"}
        except Exception:
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
        if current_url and initial_url and url_has_login:
            if "login" in initial_url.lower() and "login" not in current_url.lower():
                logger.info("检测到登录: URL 从登录页跳转至 %s", current_url)
                return {"detected": True, "reason": "url_change",
                        "detail": f"URL 从登录页跳转至 {current_url}"}

        # ── Signal 2: Custom URL trigger ──
        if custom_url_trigger and current_url:
            if custom_url_trigger in current_url and custom_url_trigger not in initial_url:
                logger.info("检测到登录: URL 匹配 %s", custom_url_trigger)
                return {"detected": True, "reason": "custom",
                        "detail": f"URL 匹配自定义规则: {custom_url_trigger}"}

        # ── Signal 3: Cookie appearance (highest confidence) ──
        if cookie_names:
            try:
                current_cookies = await proxy.get_cookies()
                current_cnames = {c["name"] for c in current_cookies}
                new_cookies = current_cnames - initial_cookie_names
                for target in cookie_names:
                    if target in current_cnames:
                        logger.info("检测到登录: Cookie %s 出现", target)
                        return {"detected": True, "reason": "cookie",
                                "detail": f"检测到 Cookie: {target}"}
            except Exception:
                pass

        # ── Signal 4: DOM appearance (user elements — high confidence) ──
        for sel in USER_INDICATORS:
            try:
                if await proxy.selector_exists(sel):
                    logger.info("检测到登录: 用户元素 %s", sel)
                    return {"detected": True, "reason": "dom_appeared",
                            "detail": f"检测到用户元素: {sel}"}
            except Exception:
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
                except Exception:
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
            except Exception:
                pass

        if custom_dom_disappear and initial_login_btn_exists:
            try:
                if await proxy.selector_disappeared(custom_dom_disappear):
                    logger.info("检测到登录: 自定义元素消失 %s", custom_dom_disappear)
                    return {"detected": True, "reason": "custom",
                            "detail": f"自定义元素消失: {custom_dom_disappear}"}
            except Exception:
                pass

        await asyncio.sleep(interval)


def cleanup_old_profiles(max_age_days: int = 7):
    profiles_dir = COOKIE_DIR / "profiles"
    if not profiles_dir.exists():
        return
    now = datetime.now()
    removed = 0
    for d in profiles_dir.iterdir():
        if d.is_dir():
            age = now - datetime.fromtimestamp(d.stat().st_mtime)
            if age.days >= max_age_days:
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
    if removed:
        logger.info("已清理 %d 个过期 Session 目录", removed)
