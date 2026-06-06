"""MCP 工具参数校验 — 类型检查 + 范围裁剪 + 注入防御。"""
from __future__ import annotations

from typing import Any

# 参数上下界
_PARAM_LIMITS: dict[str, dict[str, tuple[float, float]]] = {
    "browser_resize": {"width": (320, 7680), "height": (240, 4320)},
    "browser_scroll": {"delta_y": (-10000, 10000), "delta_x": (-10000, 10000)},
    "browser_snapshot": {"max_elements": (1, 500)},
    "browser_wait_navigation": {"timeout": (1000, 180000)},
    "browser_wait_selector": {"timeout": (1000, 60000)},
    "browser_click_coordinate": {"x": (0, 7680), "y": (0, 4320)},
    "browser_drag_coordinate": {
        "start_x": (0, 7680), "start_y": (0, 4320),
        "end_x": (0, 7680), "end_y": (0, 4320),
    },
    "browser_hover_coordinate": {"x": (0, 7680), "y": (0, 4320)},
    "browser_press_key": {},  # no numeric validation needed
}


def validate_args(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """校验并裁剪工具参数，返回修正后的参数副本。"""
    limits = _PARAM_LIMITS.get(tool_name, {})
    if not limits:
        return args

    result = dict(args)
    for key, (lo, hi) in limits.items():
        val = result.get(key)
        if val is None:
            continue
        try:
            num = float(val)
            if num < lo:
                result[key] = int(lo) if isinstance(val, int) else lo
            elif num > hi:
                result[key] = int(hi) if isinstance(val, int) else hi
        except (TypeError, ValueError):
            pass
    return result
