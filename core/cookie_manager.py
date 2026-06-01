from __future__ import annotations

import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .logging_config import get_logger

logger = get_logger("cookie")

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


def save_cookies_to_file(cookies: list[dict], name: str = "boss") -> dict:
    _ensure_dir()
    path = cookie_path(name)
    filtered = filter_expired_cookies(cookies)
    data = {"cookies": filtered, "saved_at": datetime.now().isoformat()}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("已保存 %d 条 Cookie → %s (过滤掉 %d 条过期)", len(filtered), path, len(cookies) - len(filtered))
    return {"ok": True, "path": str(path), "count": len(filtered)}


def load_cookies_from_file(name: str = "boss") -> list[dict]:
    path = cookie_path(name)
    if not path.exists():
        logger.info("Cookie 文件不存在: %s", path)
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
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


def save_storage_state(cookies: list[dict], origins: list[dict] | None = None) -> dict:
    """保存为 Playwright storage_state 兼容格式。"""
    _ensure_dir()
    path = storage_state_path()
    filtered = filter_expired_cookies(cookies)
    data = {"cookies": filtered, "origins": origins or []}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("已保存 storage_state → %s (%d 条 Cookie)", path, len(filtered))
    return {"ok": True, "path": str(path), "count": len(filtered)}


def load_storage_state() -> dict | None:
    """加载 Playwright storage_state 文件。"""
    path = storage_state_path()
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cookies = data.get("cookies", [])
        valid = filter_expired_cookies(cookies)
        if len(valid) != len(cookies):
            data["cookies"] = valid
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("加载 storage_state 失败: %s", e)
        return None


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
