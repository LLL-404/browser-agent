"""登录态检测测试 — 测试 Cookie 过期检测和 session 有效性判断逻辑。"""
import time
import json
import tempfile

import pytest
from pathlib import Path


def _make_cookie(name="test_cookie", value="test", expires=None):
    c = {"name": name, "value": value, "domain": ".zhipin.com", "path": "/"}
    if expires is not None:
        c["expires"] = expires
    return c


class TestSessionCheck:
    def test_expired_cookie(self):
        from agent.core.session import _is_expired
        past = time.time() - 3600
        cookie = _make_cookie(expires=past)
        assert _is_expired(cookie) is True

    def test_valid_cookie(self):
        from agent.core.session import _is_expired
        future = time.time() + 86400
        cookie = _make_cookie(expires=future)
        assert _is_expired(cookie) is False

    def test_cookie_no_expires(self):
        from agent.core.session import _is_expired
        cookie = _make_cookie()
        cookie.pop("expires", None)
        assert _is_expired(cookie) is False

    def test_cookie_zero_expires(self):
        from agent.core.session import _is_expired
        cookie = _make_cookie(expires=0)
        assert _is_expired(cookie) is False

    def test_filter_mixed_cookies(self):
        from agent.core.session import filter_expired_cookies
        past = time.time() - 3600
        future = time.time() + 86400
        cookies = [
            _make_cookie("valid1", expires=future),
            _make_cookie("expired1", expires=past),
            _make_cookie("valid2", expires=future),
        ]
        valid = filter_expired_cookies(cookies)
        assert len(valid) == 2
        names = [c["name"] for c in valid]
        assert "valid1" in names
        assert "valid2" in names
        assert "expired1" not in names

    def test_has_saved_cookies_no_file(self):
        from agent.core.session import has_saved_cookies
        assert has_saved_cookies("nonexistent_test") is False

    async def test_load_storage_state_missing(self):
        from agent.core.session import load_storage_state
        result = await load_storage_state()
        assert result is None or isinstance(result, dict)

    def test_all_expired_filtered(self):
        from agent.core.session import filter_expired_cookies
        past = time.time() - 3600
        cookies = [
            _make_cookie("a", expires=past),
            _make_cookie("b", expires=past - 7200),
        ]
        valid = filter_expired_cookies(cookies)
        assert len(valid) == 0
