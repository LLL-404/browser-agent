"""MCP Handler 单元测试 — mock 隔离测试各 handler 的正常路径与异常路径。"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from browser_agent.mcp.handlers import (
    TOOL_ALIASES,
    TOOL_HANDLERS,
    _click,
    _click_coordinate,
    _close,
    _console_messages,
    _cookie_get,
    _cookie_list,
    _cookie_set,
    _drag_coordinate,
    _evaluate,
    _file_upload,
    _fill_form,
    _handle_dialog,
    _hover,
    _hover_coordinate,
    _html,
    _localstorage_get,
    _localstorage_set,
    _navigate,
    _navigate_back,
    _network_requests,
    _open,
    _pdf_save,
    _press_key,
    _resize,
    _screenshot_save,
    _scroll,
    _select_option,
    _snapshot,
    _storage_state,
    _take_screenshot,
    _text,
    _type,
    _url,
    _wait_navigation,
    _wait_selector,
)


@pytest.fixture
def mock_page():
    p = AsyncMock()
    p.url = "https://example.com"
    p.context.cookies.return_value = []
    return p


@pytest.fixture
def mock_ctrl(mock_page):
    ctrl = MagicMock()
    ctrl.page = mock_page
    ctrl.require_page.return_value = mock_page
    ctrl.go_back = AsyncMock(return_value=True)
    ctrl.get_current_url = AsyncMock(return_value="https://example.com")
    ctrl.hover_selector = AsyncMock(return_value=True)
    ctrl.select_option_value = AsyncMock(return_value=True)
    ctrl.fill_input = AsyncMock(return_value=True)
    ctrl.set_file_inputs = AsyncMock(return_value=True)
    ctrl.save_cookies = AsyncMock(return_value=[])
    ctrl.save_local_storage = AsyncMock(return_value="{}")
    ctrl.get_console_logs = MagicMock(return_value=[])
    ctrl.get_network_logs = MagicMock(return_value=[])
    ctrl.handle_dialog = AsyncMock(return_value=True)
    ctrl.hover_selector = AsyncMock(return_value=True)
    return ctrl


@pytest.fixture
def mock_agent(mock_ctrl):
    agent = MagicMock()
    agent.ctrl = mock_ctrl
    agent.open = AsyncMock(return_value={"ok": True, "engine": "playwright"})
    agent.close = AsyncMock(return_value={"ok": True})
    agent.navigate = AsyncMock(return_value={"ok": True, "url": "https://example.com"})
    agent.click = AsyncMock(return_value={"ok": True})
    agent.type_text = AsyncMock(return_value={"ok": True})
    agent.press = AsyncMock(return_value={"ok": True})
    agent.snapshot = AsyncMock(return_value={"url": "https://example.com", "mode": "auto"})
    agent.screenshot = AsyncMock(return_value={"ok": True, "format": "png"})
    agent.text = AsyncMock(return_value={"text": "hello"})
    agent.html = AsyncMock(return_value={"html": "<html>"})
    agent.url = AsyncMock(return_value={"url": "https://example.com"})
    agent.scroll = AsyncMock(return_value={"ok": True, "delta": 500})
    agent.wait = AsyncMock(return_value={"ok": True, "found": True})
    agent.execute_js = AsyncMock(return_value={"result": "ok"})
    return agent


# ── TOOL_HANDLERS registry integrity ──


class TestRegistry:
    def test_all_handlers_registered(self):
        """All 44 handlers present in TOOL_HANDLERS."""
        assert len(TOOL_HANDLERS) == 44

    def test_all_aliases_resolve(self):
        """Every alias points to a real handler."""
        for old, new in TOOL_ALIASES.items():
            assert new in TOOL_HANDLERS, f"Alias {old} -> {new} resolves to missing handler"

    def test_no_orphan_definitions(self):
        """All handler functions referenced in TOOL_HANDLERS are callable."""
        for name, handler in TOOL_HANDLERS.items():
            assert callable(handler), f"Handler for {name} is not callable"


# ── Normal path tests ──


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_open(self, mock_agent, mock_ctrl):
        r = await _open(mock_agent, mock_ctrl, {"url": "https://example.com"})
        assert r["ok"] is True
        mock_agent.open.assert_awaited_with(headless=False, url="https://example.com", use_system_browser=False)

    @pytest.mark.asyncio
    async def test_close(self, mock_agent, mock_ctrl):
        r = await _close(mock_agent, mock_ctrl, {})
        assert r["ok"] is True
        mock_agent.close.assert_awaited_once()


class TestNavigation:
    @pytest.mark.asyncio
    async def test_navigate(self, mock_agent, mock_ctrl):
        r = await _navigate(mock_agent, mock_ctrl, {"url": "https://example.com"})
        assert r["ok"] is True

    @pytest.mark.asyncio
    async def test_navigate_back(self, mock_agent, mock_ctrl):
        r = await _navigate_back(mock_agent, mock_ctrl, {})
        assert r["ok"] is True
        mock_ctrl.go_back.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_resize(self, mock_agent, mock_ctrl, mock_page):
        r = await _resize(mock_agent, mock_ctrl, {"width": 1920, "height": 1080})
        assert r["ok"] is True
        mock_page.set_viewport_size.assert_awaited_with({"width": 1920, "height": 1080})


class TestInteraction:
    @pytest.mark.asyncio
    async def test_click(self, mock_agent, mock_ctrl):
        r = await _click(mock_agent, mock_ctrl, {"ref": "@e1"})
        assert r["ok"] is True
        mock_agent.click.assert_awaited_with(target="@e1")

    @pytest.mark.asyncio
    async def test_type(self, mock_agent, mock_ctrl):
        r = await _type(mock_agent, mock_ctrl, {"selector": "#input", "text": "hello"})
        assert r["ok"] is True

    @pytest.mark.asyncio
    async def test_hover(self, mock_agent, mock_ctrl):
        r = await _hover(mock_agent, mock_ctrl, {"selector": "#btn"})
        assert r["ok"] is True

    @pytest.mark.asyncio
    async def test_select_option(self, mock_agent, mock_ctrl):
        r = await _select_option(mock_agent, mock_ctrl, {"selector": "#sel", "value": "opt1"})
        assert r["ok"] is True

    @pytest.mark.asyncio
    async def test_fill_form(self, mock_agent, mock_ctrl):
        fields = [{"ref": "#name", "value": "Alice"}, {"ref": "#email", "value": "a@b.com"}]
        r = await _fill_form(mock_agent, mock_ctrl, {"fields": fields})
        assert r["ok"] is True
        assert len(r["fields"]) == 2

    @pytest.mark.asyncio
    async def test_file_upload(self, mock_agent, mock_ctrl):
        r = await _file_upload(
            mock_agent, mock_ctrl,
            {"selector": "#file", "paths": ["/tmp/a.txt"]},
        )
        assert r["ok"] is True

    @pytest.mark.asyncio
    async def test_press_key(self, mock_agent, mock_ctrl):
        r = await _press_key(mock_agent, mock_ctrl, {"key": "Enter"})
        assert r["ok"] is True
        mock_agent.press.assert_awaited_with("Enter")


class TestPageInfo:
    @pytest.mark.asyncio
    async def test_snapshot(self, mock_agent, mock_ctrl):
        r = await _snapshot(mock_agent, mock_ctrl, {})
        assert r["url"] == "https://example.com"

    @pytest.mark.asyncio
    async def test_screenshot(self, mock_agent, mock_ctrl):
        r = await _take_screenshot(mock_agent, mock_ctrl, {})
        assert r["ok"] is True

    @pytest.mark.asyncio
    async def test_text(self, mock_agent, mock_ctrl):
        r = await _text(mock_agent, mock_ctrl, {})
        assert r["text"] == "hello"

    @pytest.mark.asyncio
    async def test_html(self, mock_agent, mock_ctrl):
        r = await _html(mock_agent, mock_ctrl, {})
        assert "html" in r

    @pytest.mark.asyncio
    async def test_url(self, mock_agent, mock_ctrl):
        r = await _url(mock_agent, mock_ctrl, {})
        assert r["url"] == "https://example.com"

    @pytest.mark.asyncio
    async def test_scroll(self, mock_agent, mock_ctrl):
        r = await _scroll(mock_agent, mock_ctrl, {"delta_y": 300})
        assert r["ok"] is True


class TestWait:
    @pytest.mark.asyncio
    async def test_wait_navigation(self, mock_agent, mock_ctrl, mock_page):
        r = await _wait_navigation(mock_agent, mock_ctrl, {"timeout": 5000})
        assert r["ok"] is True
        mock_page.wait_for_load_state.assert_awaited_with("networkidle", timeout=5000)

    @pytest.mark.asyncio
    async def test_wait_selector(self, mock_agent, mock_ctrl):
        r = await _wait_selector(mock_agent, mock_ctrl, {"selector": "#foo", "timeout": 5000})
        assert r["ok"] is True


class TestDialog:
    @pytest.mark.asyncio
    async def test_handle_dialog(self, mock_agent, mock_ctrl):
        r = await _handle_dialog(mock_agent, mock_ctrl, {"accept": True, "prompt_text": ""})
        assert r["ok"] is True
        mock_ctrl.handle_dialog.assert_awaited_with(True, "")


class TestEvaluate:
    @pytest.mark.asyncio
    async def test_evaluate(self, mock_agent, mock_ctrl):
        r = await _evaluate(mock_agent, mock_ctrl, {"expression": "1+1"})
        assert r["result"] == "ok"


class TestStorage:
    @pytest.mark.asyncio
    async def test_cookie_list(self, mock_agent, mock_ctrl):
        r = await _cookie_list(mock_agent, mock_ctrl, {})
        assert "cookies" in r

    @pytest.mark.asyncio
    async def test_cookie_get(self, mock_agent, mock_ctrl):
        mock_ctrl.save_cookies.return_value = [{"name": "session", "value": "abc"}]
        r = await _cookie_get(mock_agent, mock_ctrl, {"name": "session"})
        assert r["found"] is True
        assert r["cookie"]["value"] == "abc"

    @pytest.mark.asyncio
    async def test_cookie_get_not_found(self, mock_agent, mock_ctrl):
        mock_ctrl.save_cookies.return_value = []
        r = await _cookie_get(mock_agent, mock_ctrl, {"name": "nonexistent"})
        assert r["found"] is False
        assert r["cookie"] is None

    @pytest.mark.asyncio
    async def test_cookie_set(self, mock_agent, mock_ctrl, mock_page):
        r = await _cookie_set(mock_agent, mock_ctrl, {"name": "test", "value": "val"})
        assert r["ok"] is True

    @pytest.mark.asyncio
    async def test_localstorage_get(self, mock_agent, mock_ctrl):
        r = await _localstorage_get(mock_agent, mock_ctrl, {})
        assert "localStorage" in r

    @pytest.mark.asyncio
    async def test_localstorage_set(self, mock_agent, mock_ctrl, mock_page):
        r = await _localstorage_set(mock_agent, mock_ctrl, {"key": "k", "value": "v"})
        assert r["ok"] is True
        mock_page.evaluate.assert_awaited_with(
            "(k,v) => window.localStorage.setItem(k, v)", "k", "v")


class TestConsoleNetwork:
    @pytest.mark.asyncio
    async def test_console_messages(self, mock_agent, mock_ctrl):
        r = await _console_messages(mock_agent, mock_ctrl, {"level": "info"})
        assert "messages" in r
        assert r["count"] == 0

    @pytest.mark.asyncio
    async def test_network_requests(self, mock_agent, mock_ctrl):
        r = await _network_requests(mock_agent, mock_ctrl, {"static": False})
        assert "requests" in r


class TestVision:
    @pytest.mark.asyncio
    async def test_click_coordinate(self, mock_agent, mock_ctrl, mock_page):
        r = await _click_coordinate(mock_agent, mock_ctrl, {"x": 100, "y": 200})
        assert r["ok"] is True
        mock_page.mouse.click.assert_awaited_with(100, 200, button="left")

    @pytest.mark.asyncio
    async def test_drag_coordinate(self, mock_agent, mock_ctrl, mock_page):
        r = await _drag_coordinate(
            mock_agent, mock_ctrl,
            {"start_x": 0, "start_y": 0, "end_x": 100, "end_y": 100},
        )
        assert r["ok"] is True

    @pytest.mark.asyncio
    async def test_hover_coordinate(self, mock_agent, mock_ctrl, mock_page):
        r = await _hover_coordinate(mock_agent, mock_ctrl, {"x": 50, "y": 50})
        assert r["ok"] is True

    @pytest.mark.asyncio
    async def test_screenshot_save(self, mock_agent, mock_ctrl, mock_page):
        r = await _screenshot_save(mock_agent, mock_ctrl, {"path": "/tmp/test.png"})
        assert r["ok"] is True
        mock_page.screenshot.assert_awaited_with(path="/tmp/test.png", full_page=False)


class TestPdf:
    @pytest.mark.asyncio
    async def test_pdf_save(self, mock_agent, mock_ctrl, mock_page):
        r = await _pdf_save(mock_agent, mock_ctrl, {"path": "/tmp/test.pdf"})
        assert r["ok"] is True
        mock_page.pdf.assert_awaited_with(path="/tmp/test.pdf")


# ── Error path tests ──


class TestErrors:
    @pytest.mark.asyncio
    async def test_storage_state_no_save_path(self, mock_agent, mock_ctrl):
        r = await _storage_state(mock_agent, mock_ctrl, {"save_path": ""})
        assert r["ok"] is False
        assert "save_path is required" in str(r.get("error", ""))

    @pytest.mark.asyncio
    async def test_storage_state_no_browser(self, mock_agent, mock_ctrl):
        mock_ctrl.page = None
        r = await _storage_state(mock_agent, mock_ctrl, {"save_path": "/tmp/s.json"})
        assert r["ok"] is False
        assert "browser not open" in str(r.get("error", ""))

    @pytest.mark.asyncio
    async def test_navigate_no_url(self, mock_agent, mock_ctrl):
        r = await _navigate(mock_agent, mock_ctrl, {"url": ""})
        # navigate with empty URL should not crash
        assert "ok" in r

    @pytest.mark.asyncio
    async def test_click_no_target(self, mock_agent, mock_ctrl):
        r = await _click(mock_agent, mock_ctrl, {})
        assert r["ok"] is True  # uses empty string as target, agent.click handles it

    @pytest.mark.asyncio
    async def test_cookie_set_no_page(self, mock_agent, mock_ctrl):
        mock_ctrl.page = None
        r = await _cookie_set(mock_agent, mock_ctrl, {"name": "x", "value": "y"})
        assert r["ok"] is False

    @pytest.mark.asyncio
    async def test_fill_form_empty_fields(self, mock_agent, mock_ctrl):
        r = await _fill_form(mock_agent, mock_ctrl, {"fields": []})
        assert "fields" in r

    @pytest.mark.asyncio
    async def test_vision_missing_coords(self, mock_agent, mock_ctrl, mock_page):
        r = await _click_coordinate(mock_agent, mock_ctrl, {})
        assert r["ok"] is True  # defaults to 0,0

    @pytest.mark.asyncio
    async def test_with_timeout_error(self, mock_agent, mock_ctrl, mock_page):
        """Simulate timeout error in _safe_call wrapper."""
        mock_page.wait_for_load_state.side_effect = TimeoutError("timeout")
        r = await _wait_navigation(mock_agent, mock_ctrl, {"timeout": 100})
        assert r["ok"] is False


# ── Injection defense tests ──


class TestInjectionDefense:
    @pytest.mark.asyncio
    async def test_localstorage_set_injection(self, mock_agent, mock_ctrl, mock_page):
        """JS injection in localStorage key/value should be blocked."""
        malicious = "'); alert('xss'); ("
        r = await _localstorage_set(mock_agent, mock_ctrl, {"key": malicious, "value": malicious})
        assert r["ok"] is True
        # Verify evaluate was called with args, not string interpolation
        call_args = mock_page.evaluate.await_args
        assert call_args is not None
        args, _kwargs = call_args
        assert args[0] == "(k,v) => window.localStorage.setItem(k, v)"
        assert args[1] == malicious
        assert args[2] == malicious

    def test_alias_chain(self):
        """No alias chain loops."""
        _visited: set[str] = set()
        for old, new in TOOL_ALIASES.items():
            chain = {old, new}
            current = new
            while current in TOOL_ALIASES:
                current = TOOL_ALIASES[current]
                assert current not in chain, f"Alias loop detected: {old} -> ... -> {current}"
                chain.add(current)
