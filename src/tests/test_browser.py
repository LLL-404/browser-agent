"""Tests for agent/core/browser.py — BrowserController unit tests."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, PropertyMock

from agent.core.browser import BrowserController


@pytest.fixture
def ctrl():
    c = BrowserController()
    page = AsyncMock()
    page.url = "https://example.com"
    page.title = AsyncMock(return_value="Test Page")
    page.inner_text = AsyncMock(return_value="Hello World")
    page.content = AsyncMock(return_value="<html><body>Hello</body></html>")
    page.goto = AsyncMock(return_value=None)
    page.click = AsyncMock(return_value=None)
    page.fill = AsyncMock(return_value=None)
    page.query_selector = AsyncMock(return_value=MagicMock())
    page.query_selector.return_value.inner_text = AsyncMock(return_value="item")
    page.query_selector_all = AsyncMock(return_value=[MagicMock(), MagicMock()])
    page.wait_for_selector = AsyncMock(return_value=MagicMock())
    page.screenshot = AsyncMock(return_value=b"png-data")
    page.evaluate = AsyncMock(return_value="result")
    page.hover = AsyncMock(return_value=None)
    page.select_option = AsyncMock(return_value=None)
    page.go_back = AsyncMock(return_value=None)
    page.set_input_files = AsyncMock(return_value=None)
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock(return_value=None)
    page.get_by_text = MagicMock()
    page.get_by_text.return_value.first.click = AsyncMock(return_value=None)

    browser = MagicMock()
    browser.cookies = AsyncMock(return_value=[{"name": "x", "value": "y"}])
    browser.add_cookies = AsyncMock(return_value=None)
    browser.close = AsyncMock(return_value=None)

    c._page = page
    c._browser = browser
    c._is_running = True
    c._engine = "playwright"
    c._pw = MagicMock()
    c._pw.stop = AsyncMock(return_value=None)
    return c


class TestRequirePage:
    def test_returns_page(self, ctrl):
        assert ctrl._require_page() is ctrl._page

    def test_raises_when_none(self):
        c = BrowserController()
        with pytest.raises(Exception):
            c._require_page()


class TestNavigate:
    @pytest.mark.parametrize("success", [True, False])
    async def test_navigate_to(self, ctrl, success):
        if not success:
            ctrl._page.goto.side_effect = Exception("timeout")
        result = await ctrl.navigate_to("https://example.com")
        assert result is success


class TestClick:
    @pytest.mark.parametrize("success", [True, False])
    async def test_click_selector(self, ctrl, success):
        if not success:
            ctrl._page.click.side_effect = Exception("not found")
        result = await ctrl.click_selector("#btn")
        assert result is success


class TestFindSelector:
    async def test_found(self, ctrl):
        ctrl._page.query_selector.return_value = MagicMock()
        assert await ctrl.find_selector("#btn") is True

    async def test_not_found(self, ctrl):
        ctrl._page.query_selector.return_value = None
        assert await ctrl.find_selector("#btn") is False

    async def test_error(self, ctrl):
        ctrl._page.query_selector.side_effect = Exception("crash")
        assert await ctrl.find_selector("#btn") is False


class TestFillInput:
    @pytest.mark.parametrize("success", [True, False])
    async def test_fill(self, ctrl, success):
        if not success:
            ctrl._page.fill.side_effect = Exception("not found")
        result = await ctrl.fill_input("#input", "hello")
        assert result is success


class TestDecoratedMethods:
    async def test_get_page_text(self, ctrl):
        text = await ctrl.get_page_text(10)
        assert text == "Hello Worl"

    async def test_get_page_text_empty(self, ctrl):
        ctrl._page.inner_text.return_value = ""
        assert await ctrl.get_page_text() == ""

    async def test_get_page_title(self, ctrl):
        assert await ctrl.get_page_title() == "Test Page"

    async def test_get_current_url(self, ctrl):
        assert await ctrl.get_current_url() == "https://example.com"

    async def test_scroll_page(self, ctrl):
        assert await ctrl.scroll_page(500) is True

    async def test_press_key(self, ctrl):
        assert await ctrl.press_key("Enter") is True

    async def test_hover_selector(self, ctrl):
        assert await ctrl.hover_selector("#btn") is True

    async def test_select_option_value(self, ctrl):
        assert await ctrl.select_option_value("#sel", "opt1") is True

    async def test_go_back(self, ctrl):
        assert await ctrl.go_back() is True

    async def test_set_file_inputs(self, ctrl):
        assert await ctrl.set_file_inputs("#upload", ["a.pdf"]) is True

    async def test_get_page_html(self, ctrl):
        html = await ctrl.get_page_html()
        assert html == "<html><body>Hello</body></html>"


class TestDecoratedErrorPath:
    async def test_get_page_text_error(self, ctrl):
        ctrl._page.inner_text.side_effect = Exception("err")
        assert await ctrl.get_page_text() == ""

    async def test_get_page_title_error(self, ctrl):
        ctrl._page.title.side_effect = Exception("err")
        assert await ctrl.get_page_title() == ""

    async def test_get_current_url_error(self, ctrl):
        ctrl._page = MagicMock()
        ctrl._page.url = "x"
        type(ctrl._page).url = PropertyMock(side_effect=Exception("err"))
        ctrl._require_page = MagicMock(return_value=ctrl._page)
        assert await ctrl.get_current_url() == ""

    async def test_scroll_error(self, ctrl):
        ctrl._page.evaluate.side_effect = Exception("err")
        assert await ctrl.scroll_page(500) is False


class TestScreenshot:
    async def test_take_screenshot_success(self, ctrl):
        assert await ctrl.take_screenshot("shot.png") is True
        ctrl._page.screenshot.assert_awaited_once_with(path="shot.png")

    async def test_take_screenshot_failure(self, ctrl):
        ctrl._page.screenshot.side_effect = Exception("err")
        assert await ctrl.take_screenshot("shot.png") is False

    async def test_get_page_screenshot_bytes_success(self, ctrl):
        data = await ctrl.get_page_screenshot_bytes(full_page=True)
        assert data == b"png-data"
        ctrl._page.screenshot.assert_awaited_once_with(type="png", full_page=True)

    async def test_get_page_screenshot_bytes_failure(self, ctrl):
        ctrl._page.screenshot.side_effect = Exception("err")
        assert await ctrl.get_page_screenshot_bytes() is None


class TestExecuteJS:
    async def test_without_args(self, ctrl):
        result = await ctrl.execute_js("1+1")
        assert result == {"result": "result"}
        ctrl._page.evaluate.assert_awaited_once_with("1+1")

    async def test_with_args(self, ctrl):
        ctrl._page.evaluate.return_value = "clicked"
        result = await ctrl.execute_js("(sel) => document.querySelector(sel).click()", "#btn")
        ctrl._page.evaluate.assert_awaited_once_with("(sel) => document.querySelector(sel).click()", "#btn")
        assert result == {"result": "clicked"}

    async def test_error(self, ctrl):
        ctrl._page.evaluate.side_effect = Exception("err")
        result = await ctrl.execute_js("bad()")
        assert "error" in result


class TestQueryElement:
    async def test_found_inner_text(self, ctrl):
        ctrl._page.query_selector.return_value = MagicMock()
        ctrl._page.query_selector.return_value.inner_text = AsyncMock(return_value="Hello")
        result = await ctrl.query_element("#btn", "innerText")
        assert result["found"] is True
        assert result["text"] == "Hello"

    async def test_not_found(self, ctrl):
        ctrl._page.query_selector.return_value = None
        result = await ctrl.query_element("#btn")
        assert result["found"] is False

    async def test_error(self, ctrl):
        ctrl._page.query_selector.side_effect = Exception("err")
        result = await ctrl.query_element("#btn")
        assert "error" in result


class TestWaitForElement:
    async def test_found(self, ctrl):
        result = await ctrl.wait_for_element("#btn")
        assert result["found"] is True

    async def test_not_found(self, ctrl):
        ctrl._page.wait_for_selector.return_value = None
        result = await ctrl.wait_for_element("#missing")
        assert result["found"] is False

    async def test_error(self, ctrl):
        ctrl._page.wait_for_selector.side_effect = Exception("timeout")
        result = await ctrl.wait_for_element("#btn")
        assert result["found"] is False
        assert "error" in result


class TestClickByText:
    async def test_clicked(self, ctrl):
        result = await ctrl.click_by_text("Submit")
        assert result["clicked"] is True

    async def test_error(self, ctrl):
        ctrl._page.get_by_text.return_value.first.click.side_effect = Exception("err")
        result = await ctrl.click_by_text("Submit")
        assert result["clicked"] is False


class TestGetConsoleLogs:
    def test_empty(self, ctrl):
        assert ctrl.get_console_logs() == []

    def test_filter_by_level(self, ctrl):
        ctrl._console_logs = [
            {"type": "error", "text": "err1"},
            {"type": "warning", "text": "warn1"},
            {"type": "info", "text": "info1"},
            {"type": "debug", "text": "debug1"},
        ]
        errors = ctrl.get_console_logs("error")
        assert len(errors) == 1
        assert errors[0]["type"] == "error"

        warns = ctrl.get_console_logs("warning")
        assert len(warns) == 2

        infos = ctrl.get_console_logs("info")
        assert len(infos) == 3

        debugs = ctrl.get_console_logs("debug")
        assert len(debugs) == 4


class TestGetNetworkLogs:
    def test_empty(self, ctrl):
        assert ctrl.get_network_logs() == []

    def test_filter_static(self, ctrl):
        ctrl._network_logs = [
            {"url": "doc.html", "resource_type": "document"},
            {"url": "img.png", "resource_type": "image"},
            {"url": "font.woff", "resource_type": "font"},
            {"url": "api/data", "resource_type": "fetch"},
        ]
        filtered = ctrl.get_network_logs(include_static=False)
        assert len(filtered) == 2
        assert filtered[0]["resource_type"] == "document"
        assert filtered[1]["resource_type"] == "fetch"

    def test_include_static(self, ctrl):
        ctrl._network_logs = [
            {"url": "img.png", "resource_type": "image"},
            {"url": "doc.html", "resource_type": "document"},
        ]
        all_ = ctrl.get_network_logs(include_static=True)
        assert len(all_) == 2


class TestGetPendingDialog:
    async def test_no_dialog(self, ctrl):
        ctrl._pending_dialog = None
        assert await ctrl.get_pending_dialog() is None

    async def test_with_dialog(self, ctrl):
        ctrl._pending_dialog = {"type": "alert", "message": "hi", "default_value": ""}
        d = await ctrl.get_pending_dialog()
        assert d["type"] == "alert"
        assert d["message"] == "hi"


class TestHandleDialog:
    async def test_no_pending(self, ctrl):
        ctrl._pending_dialog = None
        assert await ctrl.handle_dialog(True) is False

    async def test_accept(self, ctrl):
        dialog = AsyncMock()
        ctrl._pending_dialog = {"_dialog": dialog}
        assert await ctrl.handle_dialog(True) is True
        dialog.accept.assert_awaited_once_with(None)

    async def test_dismiss(self, ctrl):
        dialog = AsyncMock()
        ctrl._pending_dialog = {"_dialog": dialog}
        assert await ctrl.handle_dialog(False) is True
        dialog.dismiss.assert_awaited_once()

    async def test_error(self, ctrl):
        dialog = AsyncMock()
        dialog.accept.side_effect = Exception("err")
        ctrl._pending_dialog = {"_dialog": dialog}
        assert await ctrl.handle_dialog(True) is False


class TestCookies:
    async def test_save_cookies(self, ctrl):
        cookies = await ctrl.save_cookies()
        assert len(cookies) == 1
        assert cookies[0]["name"] == "x"

    async def test_save_cookies_no_browser(self, ctrl):
        ctrl._browser = None
        assert await ctrl.save_cookies() == []

    async def test_load_cookies(self, ctrl):
        assert await ctrl.load_cookies([{"name": "a"}]) is True
        ctrl._browser.add_cookies.assert_awaited_once()

    async def test_load_cookies_no_browser(self, ctrl):
        assert await ctrl.load_cookies([]) is False


class TestLocalStorage:
    async def test_save(self, ctrl):
        ctrl._page.evaluate.return_value = '{"key":"val"}'
        result = await ctrl.save_local_storage()
        assert result == '{"key":"val"}'

    async def test_save_no_page(self, ctrl):
        ctrl._page = None
        assert await ctrl.save_local_storage() == {}

    async def test_load(self, ctrl):
        assert await ctrl.load_local_storage('{"key":"val"}') is True

    async def test_load_no_page(self, ctrl):
        ctrl._page = None
        assert await ctrl.load_local_storage('{"key":"val"}') is False


class TestGetInteractiveElements:
    async def test_returns_list(self, ctrl):
        ctrl._page.evaluate.return_value = [{"ref": "@e1", "tag": "button"}]
        result = await ctrl.get_interactive_elements()
        assert len(result) == 1
        assert result[0]["ref"] == "@e1"

    async def test_no_page(self, ctrl):
        ctrl._page = None
        assert await ctrl.get_interactive_elements() == []

    async def test_error(self, ctrl):
        ctrl._page.evaluate.side_effect = Exception("err")
        assert await ctrl.get_interactive_elements() == []


class TestGetDomStructure:
    async def test_basic(self, ctrl):
        ctrl._page.query_selector.return_value = MagicMock()
        ctrl._page.query_selector.return_value.inner_text = AsyncMock(return_value="text")
        result = await ctrl.get_dom_structure()
        assert result["has_body"] is True
        assert result["body_len"] == 4

    async def test_with_selectors(self, ctrl):
        ctrl._page.query_selector_all.return_value = [MagicMock(), MagicMock()]
        result = await ctrl.get_dom_structure(["button", "a"])
        assert result["button"] == 2

    async def test_error_safe(self, ctrl):
        ctrl._page.query_selector.side_effect = Exception("err")
        result = await ctrl.get_dom_structure()
        assert result["has_body"] is False


class TestStop:
    async def test_playwright_path(self, ctrl):
        browser = ctrl._browser
        pw = ctrl._pw
        assert await ctrl.stop() is True
        browser.close.assert_awaited_once()
        pw.stop.assert_awaited_once()

    async def test_camoufox_path(self, ctrl):
        ctrl._engine = "camoufox"
        ctrl._browser = AsyncMock()
        assert await ctrl.stop() is True

    async def test_not_running(self, ctrl):
        ctrl._is_running = False
        assert await ctrl.stop() is True

    async def test_timeout(self, ctrl):
        ctrl._browser.close.side_effect = RuntimeError("timeout")
        ctrl._pw.stop.side_effect = RuntimeError("timeout")
        assert await ctrl.stop() is False

    async def test_release_resources_on_stop(self, ctrl):
        await ctrl.stop()
        assert ctrl._is_running is False
        assert ctrl._browser is None
        assert ctrl._page is None
        assert ctrl._engine is None


class TestAccessibilitySnapshot:
    async def test_success(self, ctrl):
        ctrl._page.accessibility.snapshot = AsyncMock(return_value={
            "role": "RootWebArea", "name": "page", "children": [],
        })
        result = await ctrl.get_accessibility_snapshot()
        assert result["role"] == "RootWebArea"

    async def test_empty(self, ctrl):
        ctrl._page.accessibility.snapshot = AsyncMock(return_value=None)
        result = await ctrl.get_accessibility_snapshot()
        assert result["role"] == "RootWebArea"

    async def test_error(self, ctrl):
        ctrl._page.accessibility.snapshot = AsyncMock(side_effect=Exception("err"))
        assert await ctrl.get_accessibility_snapshot() is None
