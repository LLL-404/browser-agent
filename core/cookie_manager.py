from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .logging_config import get_logger

logger = get_logger("cookie")

COOKIE_DIR = Path("./sessions")


def _ensure_dir():
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)


def cookie_path(name: str = "boss") -> Path:
    return COOKIE_DIR / f"{name}_cookies.json"


def session_profile_dir() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
    d = COOKIE_DIR / "profiles" / f"session_{ts}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_cookies_to_file(cookies: list[dict], name: str = "boss") -> dict:
    _ensure_dir()
    path = cookie_path(name)
    data = {"cookies": cookies, "saved_at": datetime.now().isoformat()}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("已保存 %d 条 Cookie → %s", len(cookies), path)
    return {"ok": True, "path": str(path), "count": len(cookies)}


def load_cookies_from_file(name: str = "boss") -> list[dict]:
    path = cookie_path(name)
    if not path.exists():
        logger.info("Cookie 文件不存在: %s", path)
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cookies = data.get("cookies", [])
        logger.info("从 %s 加载了 %d 条 Cookie", path, len(cookies))
        return cookies
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("加载 Cookie 文件失败: %s", e)
        return []


def has_saved_cookies(name: str = "boss") -> bool:
    return cookie_path(name).exists()


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
                import shutil
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
    if removed:
        logger.info("已清理 %d 个过期 Session 目录", removed)