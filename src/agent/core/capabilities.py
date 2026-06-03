"""Capabilities 系统 — 按能力组管理 MCP 工具的可见性。

每组能力对应一组工具名称。默认仅启用 CORE。
"""
from __future__ import annotations

from typing import Set

# ── Capability groups ──
CORE: Set[str] = {
    # lifecycle
    "browser_open", "browser_close",
    # navigation
    "browser_navigate", "browser_navigate_back", "browser_resize",
    # element interaction
    "browser_click", "browser_type", "browser_hover",
    "browser_select_option", "browser_fill_form", "browser_file_upload",
    # keyboard
    "browser_press_key",
    # page info
    "browser_snapshot", "browser_take_screenshot",
    "browser_text", "browser_html", "browser_url",
    # scroll
    "browser_scroll",
    # wait
    "browser_wait_navigation", "browser_wait_selector",
    # dialog
    "browser_handle_dialog",
    # evaluate
    "browser_evaluate",
    # cookie / storage
    "browser_cookie_list", "browser_cookie_get", "browser_cookie_set",
    "browser_storage_state", "browser_storage_state_set",
    "browser_localstorage_get", "browser_localstorage_set",
    # console / network
    "browser_console_messages", "browser_network_requests",
}

VISION: Set[str] = {
    "browser_click_coordinate",
    "browser_drag_coordinate",
    "browser_hover_coordinate",
    "browser_screenshot_save",
}

PDF: Set[str] = {
    "browser_pdf_save",
}

DEVTOOLS: Set[str] = {
    "devtools_capture_profiling",
    "devtools_collect_garbage",
    "devtools_enable_device_emulation",
    "devtools_reset_device_emulation",
    "devtools_send_command",
    "devtools_set_location",
}

# ── Mapping ──
CAPABILITY_TO_TOOLS: dict[str, Set[str]] = {
    "core": CORE,
    "vision": VISION,
    "pdf": PDF,
    "devtools": DEVTOOLS,
}


def is_tool_enabled(tool_name: str, enabled_caps: list[str]) -> bool:
    """Check if a tool is allowed given the enabled capabilities."""
    if not enabled_caps:
        return tool_name in CORE
    for cap in enabled_caps:
        cap = cap.strip().lower()
        tools = CAPABILITY_TO_TOOLS.get(cap)
        if tools and tool_name in tools:
            return True
    return False


def filter_tools(tool_list: list, enabled_caps: list[str]) -> list:
    """Filter a list of Tool objects by enabled capabilities."""
    return [t for t in tool_list if is_tool_enabled(t.name, enabled_caps)]
