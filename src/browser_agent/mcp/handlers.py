"""MCP 工具处理函数 — 每个工具一个独立 Handler，通过 TOOL_HANDLERS 注册。"""
from __future__ import annotations

import dataclasses
import json as _json
from pathlib import Path
from typing import Any, Callable

import aiofiles
from shared.logging_config import get_logger
from shared.error_handler import classify_playwright_error, format_error_for_mcp
from shared.exceptions import BrowserAutomationError
from browser_agent.core.browser import BrowserController
from browser_agent.core.agent import BrowserAgent, BrowsingAgent

logger = get_logger("handlers")

# ── Agent 切换标志 ──
_use_new_agent: bool = True  # pylint: disable=invalid-name


def _get_agent() -> BrowserAgent | BrowsingAgent:
    """创建 Agent 实例，根据 _use_new_agent 标志选择 BrowsingAgent 或 BrowserAgent。"""
    bc = BrowserController()
    if _use_new_agent:
        return BrowsingAgent(bc)
    return BrowserAgent(bc)


async def _safe_call(agent, ctrl, args, fn):
    """统一包装 handler 调用：异常 → format_error_for_mcp 格式。"""
    try:
        return await fn(agent, ctrl, args)
    except BrowserAutomationError as e:
        return {"ok": False, **e.to_dict(), "recovery_hint": ""}
    except Exception as e:  # pylint: disable=broad-exception-caught
        exc_type = classify_playwright_error(e)
        if exc_type is not BrowserAutomationError:
            err = exc_type(str(e), error_code="EXEC_ERROR")
            return {"ok": False, **format_error_for_mcp(err)}
        return {"ok": False, "error": str(e), "error_code": "UNEXPECTED"}

# ── Alias map ──
TOOL_ALIASES: dict[str, str] = {
    "browser_type_text": "browser_type",
    "browser_screenshot": "browser_take_screenshot",
    "browser_press": "browser_press_key",
    "browser_save_state": "browser_storage_state",
    "browser_get_cookies": "browser_cookie_list",
    "browser_cookies": "browser_cookie_list",
}

# ── Storage state helpers ──


async def _save_state(agent, save_path: str) -> dict:
    if not save_path:
        return {"ok": False, "error": "save_path is required"}
    try:
        page = agent.ctrl.page
        if not page:
            return {"ok": False, "error": "browser not open"}
        state = await page.context.storage_state()
        path = Path(save_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(_json.dumps(state, ensure_ascii=False, indent=2))
        return {
            "ok": True, "path": str(path),
            "cookies": len(state.get("cookies", [])),
            "size": path.stat().st_size,
        }
    except Exception as e:  # pylint: disable=broad-exception-caught
        return {"ok": False, "error": str(e)}


async def _load_state(agent, load_path: str) -> dict:
    if not load_path:
        return {"ok": False, "error": "load_path is required"}
    try:
        path = Path(load_path)
        if not path.exists():
            return {"ok": False, "error": f"file not found: {load_path}"}
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()
        data = _json.loads(content)
        page = agent.ctrl.page
        if not page:
            return {"ok": False, "error": "browser not open"}
        ctx = page.context
        if data.get("cookies"):
            await ctx.add_cookies(data["cookies"])
        if data.get("origins"):
            for origin in data["origins"]:
                for storage in origin.get("localStorage", []):
                    await page.evaluate(
                        "(k,v) => window.localStorage.setItem(k, v)",
                        storage["name"], storage["value"])
        return {
            "ok": True,
            "cookies_restored": len(data.get("cookies", [])),
            "origins_restored": len(data.get("origins", [])),
        }
    except Exception as e:  # pylint: disable=broad-exception-caught
        return {"ok": False, "error": str(e)}

# ── Handler type ──
Handler = Callable[[Any, Any, dict], Any]

# ── Lifecycle ──


async def _open(agent, _ctrl, args):
    return await agent.open(
        headless=args.get("headless", False),
        url=args.get("url", "about:blank"),
    )


async def _close(agent, _ctrl, _args):
    return await agent.close()

# ── Navigation ──


async def _navigate(agent, _ctrl, args):
    return await agent.navigate(args.get("url", ""))


async def _navigate_back(_agent, ctrl, _args):
    ok = await ctrl.go_back()
    return {"ok": ok, "url": await ctrl.get_current_url() if ok else ""}


async def _resize(_agent, ctrl, args):
    w, h = args.get("width", 1280), args.get("height", 720)
    try:
        page = ctrl.require_page()
        await page.set_viewport_size({"width": w, "height": h})
        return {"ok": True, "width": w, "height": h}
    except Exception as e:  # pylint: disable=broad-exception-caught
        return {"ok": False, "error": str(e)}

# ── Element interaction ──


async def _click(agent, _ctrl, args):
    return await agent.click(target=args.get("ref") or args.get("selector", ""))


async def _type(agent, _ctrl, args):
    sel = args.get("selector", "")
    text = args.get("text", "")
    clear = args.get("clear", True)
    return await agent.type_text(sel, text, clear=clear)


async def _hover(_agent, ctrl, args):
    sel = args.get("selector", "")
    ok = await ctrl.hover_selector(sel)
    return {"ok": ok, "selector": sel}


async def _select_option(_agent, ctrl, args):
    sel = args.get("selector", "")
    val = args.get("value", "")
    ok = await ctrl.select_option_value(sel, val)
    return {"ok": ok, "selector": sel, "value": val}


async def _fill_form(_agent, ctrl, args):
    fields = args.get("fields", [])
    results = []
    for field in fields:
        sel = field.get("ref", "")
        val = field.get("value", "")
        ok = await ctrl.fill_input(sel, val)
        results.append({"selector": sel, "value": val, "ok": ok})
    return {"ok": all(r["ok"] for r in results), "fields": results}


async def _file_upload(_agent, ctrl, args):
    sel = args.get("selector", "")
    paths = args.get("paths", [])
    ok = await ctrl.set_file_inputs(sel, paths)
    return {"ok": ok, "selector": sel, "files": len(paths)}

# ── Keyboard ──


async def _press_key(agent, _ctrl, args):
    key = args.get("key", "Enter")
    return await agent.press(key)

# ── Page info ──


async def _snapshot(agent, _ctrl, args):
    mode = args.get("mode", "auto")
    if mode not in ("auto", "dom", "accessibility"):
        mode = "auto"
    return await agent.snapshot(max_length=args.get("max_elements", 3000), mode=mode)


async def _take_screenshot(agent, _ctrl, args):
    return await agent.screenshot(full_page=args.get("full_page", False))


async def _text(agent, _ctrl, _args):
    return await agent.text()


async def _html(agent, _ctrl, _args):
    return await agent.html()


async def _url(agent, _ctrl, _args):
    return await agent.url()

# ── Scroll ──


async def _scroll(agent, _ctrl, args):
    dy = args.get("delta_y", 500)
    return await agent.scroll(delta=dy)

# ── Wait ──


async def _wait_navigation(_agent, ctrl, args):
    timeout = args.get("timeout", 30000)
    try:
        page = ctrl.require_page()
        await page.wait_for_load_state("networkidle", timeout=timeout)
        return {"ok": True, "url": page.url}
    except Exception as e:  # pylint: disable=broad-exception-caught
        return {"ok": False, "error": str(e)}


async def _wait_selector(agent, _ctrl, args):
    sel = args.get("selector", "")
    timeout = args.get("timeout", 10000)
    return await agent.wait(sel, timeout)

# ── Dialog ──


async def _handle_dialog(_agent, ctrl, args):
    accept = args.get("accept", True)
    prompt_text = args.get("prompt_text", "")
    ok = await ctrl.handle_dialog(accept, prompt_text)
    return {"ok": ok, "accept": accept}

# ── Evaluate ──


async def _evaluate(agent, _ctrl, args):
    expr = args.get("expression", "")
    if not expr and args.get("filename"):
        try:
            expr = Path(args["filename"]).read_text(encoding="utf-8")
        except Exception as e:  # pylint: disable=broad-exception-caught
            return {"ok": False, "error": f"读取文件失败: {e}"}
    return await agent.execute_js(expr)

# ── Cookie / Storage ──


async def _cookie_list(_agent, ctrl, _args):
    cookies = await ctrl.save_cookies()
    return {"ok": True, "cookies": cookies, "count": len(cookies)}


async def _cookie_get(_agent, ctrl, args):
    name_filter = args.get("name", "")
    cookies = await ctrl.save_cookies()
    found = [c for c in cookies if c.get("name") == name_filter]
    return {
        "ok": True, "name": name_filter,
        "cookie": found[0] if found else None,
        "found": len(found) > 0,
    }


async def _cookie_set(_agent, ctrl, args):
    page = ctrl.page
    if not page:
        return {"ok": False, "error": "browser not open"}
    cookie = {}
    for k in ("name", "value", "url", "domain", "path"):
        if args.get(k):
            cookie[k] = args[k]
    try:
        await page.context.add_cookies([cookie])
        return {"ok": True, "cookie": cookie}
    except Exception as e:  # pylint: disable=broad-exception-caught
        return {"ok": False, "error": str(e)}


async def _storage_state(agent, _ctrl, args):
    return await _save_state(agent, args.get("save_path", ""))


async def _storage_state_set(agent, _ctrl, args):
    return await _load_state(agent, args.get("load_path", ""))


async def _localstorage_get(_agent, ctrl, _args):
    data = await ctrl.save_local_storage()
    return {"ok": True, "localStorage": data}


async def _localstorage_set(_agent, ctrl, args):
    page = ctrl.page
    if not page:
        return {"ok": False, "error": "browser not open"}
    key = args.get("key", "")
    value = args.get("value", "")
    try:
        await page.evaluate("(k,v) => window.localStorage.setItem(k, v)", key, value)
        return {"ok": True, "key": key}
    except Exception as e:  # pylint: disable=broad-exception-caught
        return {"ok": False, "error": str(e)}

# ── Console / Network ──


async def _console_messages(_agent, ctrl, args):
    level = args.get("level", "info")
    logs = ctrl.get_console_logs(level)
    return {"ok": True, "messages": logs, "count": len(logs), "level": level}


async def _network_requests(_agent, ctrl, args):
    include_static = args.get("static", False)
    logs = ctrl.get_network_logs(include_static)
    return {"ok": True, "requests": logs, "count": len(logs)}

# ── Vision ──


async def _click_coordinate(_agent, ctrl, args):
    page = ctrl.require_page()
    x, y = args.get("x", 0), args.get("y", 0)
    button = args.get("button", "left")
    try:
        await page.mouse.click(x, y, button=button)
        return {"ok": True, "x": x, "y": y, "button": button}
    except Exception as e:  # pylint: disable=broad-exception-caught
        return {"ok": False, "error": str(e)}


async def _drag_coordinate(_agent, ctrl, args):
    page = ctrl.require_page()
    sx, sy = args.get("start_x", 0), args.get("start_y", 0)
    ex, ey = args.get("end_x", 0), args.get("end_y", 0)
    try:
        await page.mouse.move(sx, sy)
        await page.mouse.down()
        await page.mouse.move(ex, ey)
        await page.mouse.up()
        return {"ok": True, "from": {"x": sx, "y": sy}, "to": {"x": ex, "y": ey}}
    except Exception as e:  # pylint: disable=broad-exception-caught
        return {"ok": False, "error": str(e)}


async def _hover_coordinate(_agent, ctrl, args):
    page = ctrl.require_page()
    x, y = args.get("x", 0), args.get("y", 0)
    try:
        await page.mouse.move(x, y)
        return {"ok": True, "x": x, "y": y}
    except Exception as e:  # pylint: disable=broad-exception-caught
        return {"ok": False, "error": str(e)}


async def _screenshot_save(_agent, ctrl, args):
    page = ctrl.require_page()
    path = args.get("path", "")
    full_page = args.get("full_page", False)
    if not path:
        path = "screenshot.png"
    try:
        await page.screenshot(path=path, full_page=full_page)
        return {"ok": True, "path": path}
    except Exception as e:  # pylint: disable=broad-exception-caught
        return {"ok": False, "error": str(e)}

# ── PDF ──


async def _pdf_save(_agent, ctrl, args):
    page = ctrl.require_page()
    path = args.get("path", "page.pdf")
    try:
        await page.pdf(path=path)
        return {"ok": True, "path": path}
    except Exception as e:  # pylint: disable=broad-exception-caught
        return {"ok": False, "error": str(e)}

# ── DevTools ──


async def _devtools_dispatcher(_agent, ctrl, args, tool_name: str):  # pylint: disable=too-many-return-statements
    page = ctrl.require_page()
    try:
        cdp = await page.context.new_cdp_session(page)
        if tool_name == "devtools_capture_profiling":
            await cdp.send("Profiler.start")
            return {"ok": True}
        if tool_name == "devtools_collect_garbage":
            await cdp.send("HeapProfiler.collectGarbage")
            return {"ok": True}
        if tool_name == "devtools_enable_device_emulation":
            await cdp.send("Emulation.setDeviceMetricsOverride", {
                "width": args.get("width", 375), "height": args.get("height", 812),
                "deviceScaleFactor": args.get("device_scale_factor", 2.0), "mobile": True,
            })
            return {"ok": True}
        if tool_name == "devtools_reset_device_emulation":
            await cdp.send("Emulation.clearDeviceMetricsOverride")
            return {"ok": True}
        if tool_name == "devtools_send_command":
            result = await cdp.send(args.get("cmd", ""), args.get("params", {}))
            return {"ok": True, "result": result}
        if tool_name == "devtools_set_location":
            await cdp.send("Emulation.setGeolocationOverride", {
                "latitude": args.get("latitude", 0),
                "longitude": args.get("longitude", 0),
                "accuracy": 100,
            })
            return {"ok": True}
    except Exception as e:  # pylint: disable=broad-exception-caught
        return {"ok": False, "error": str(e)}
    return None


async def _devtools_capture_profiling(agent, ctrl, args):
    return await _devtools_dispatcher(agent, ctrl, args, "devtools_capture_profiling")


async def _devtools_collect_garbage(agent, ctrl, args):
    return await _devtools_dispatcher(agent, ctrl, args, "devtools_collect_garbage")


async def _devtools_enable_device_emulation(agent, ctrl, args):
    return await _devtools_dispatcher(agent, ctrl, args, "devtools_enable_device_emulation")


async def _devtools_reset_device_emulation(agent, ctrl, args):
    return await _devtools_dispatcher(agent, ctrl, args, "devtools_reset_device_emulation")


async def _devtools_send_command(agent, ctrl, args):
    return await _devtools_dispatcher(agent, ctrl, args, "devtools_send_command")


async def _devtools_set_location(agent, ctrl, args):
    return await _devtools_dispatcher(agent, ctrl, args, "devtools_set_location")

# ── BrowsingAgent 专属 ──


async def _browse(agent, _ctrl, args):
    """执行浏览任务：感知→决策→执行 循环。"""
    return await agent.browse(task=args["task"], url=args.get("url"))


async def _get_snapshot(agent, _ctrl, _args):
    """获取当前页面的结构化感知快照（PageSnapshot）。"""
    snapshot = await agent.get_snapshot()
    if snapshot is None:
        return {"ok": False, "error": "浏览器未打开或页面不可用"}
    data = dataclasses.asdict(snapshot)
    data["ok"] = True
    return data

# ── Handler registry ──

def _safe_handler(fn: Handler) -> Handler:
    """Wrap a raw handler with _safe_call for unified error handling."""
    async def wrapper(agent, ctrl, args):
        return await _safe_call(agent, ctrl, args, fn)
    return wrapper

TOOL_HANDLERS: dict[str, Handler] = {
    "browser_open": _safe_handler(_open),
    "browser_close": _safe_handler(_close),
    "browser_navigate": _safe_handler(_navigate),
    "browser_navigate_back": _safe_handler(_navigate_back),
    "browser_resize": _safe_handler(_resize),
    "browser_click": _safe_handler(_click),
    "browser_type": _safe_handler(_type),
    "browser_hover": _safe_handler(_hover),
    "browser_select_option": _safe_handler(_select_option),
    "browser_fill_form": _safe_handler(_fill_form),
    "browser_file_upload": _safe_handler(_file_upload),
    "browser_press_key": _safe_handler(_press_key),
    "browser_snapshot": _safe_handler(_snapshot),
    "browser_take_screenshot": _safe_handler(_take_screenshot),
    "browser_text": _safe_handler(_text),
    "browser_html": _safe_handler(_html),
    "browser_url": _safe_handler(_url),
    "browser_scroll": _safe_handler(_scroll),
    "browser_wait_navigation": _safe_handler(_wait_navigation),
    "browser_wait_selector": _safe_handler(_wait_selector),
    "browser_handle_dialog": _safe_handler(_handle_dialog),
    "browser_evaluate": _safe_handler(_evaluate),
    "browser_cookie_list": _safe_handler(_cookie_list),
    "browser_cookie_get": _safe_handler(_cookie_get),
    "browser_cookie_set": _safe_handler(_cookie_set),
    "browser_storage_state": _safe_handler(_storage_state),
    "browser_storage_state_set": _safe_handler(_storage_state_set),
    "browser_localstorage_get": _safe_handler(_localstorage_get),
    "browser_localstorage_set": _safe_handler(_localstorage_set),
    "browser_console_messages": _safe_handler(_console_messages),
    "browser_network_requests": _safe_handler(_network_requests),
    "browser_click_coordinate": _safe_handler(_click_coordinate),
    "browser_drag_coordinate": _safe_handler(_drag_coordinate),
    "browser_hover_coordinate": _safe_handler(_hover_coordinate),
    "browser_screenshot_save": _safe_handler(_screenshot_save),
    "browser_pdf_save": _safe_handler(_pdf_save),
    "devtools_capture_profiling": _safe_handler(_devtools_capture_profiling),
    "devtools_collect_garbage": _safe_handler(_devtools_collect_garbage),
    "devtools_enable_device_emulation": _safe_handler(_devtools_enable_device_emulation),
    "devtools_reset_device_emulation": _safe_handler(_devtools_reset_device_emulation),
    "devtools_send_command": _safe_handler(_devtools_send_command),
    "devtools_set_location": _safe_handler(_devtools_set_location),
    "browser_browse": _safe_handler(_browse),
    "browser_get_snapshot": _safe_handler(_get_snapshot),
}
