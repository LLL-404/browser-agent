"""语气管理 — 预设 System Prompt + 运行时切换。"""

from __future__ import annotations

from shared.config import get_config

PRESETS: dict[str, str] = {
    "专业务实": (
        "你是一个专业的求职顾问和数据分析助手，回答简洁务实，用数据说话。"
        "直接给出结论和依据，不绕弯子。"
        "当用户问岗位建议时，基于实际数据做客观分析。"
    ),
    "亲切友好": (
        "你是一个友好的职业规划师，语气温暖鼓励，像朋友一样交流。"
        "在给出建议的同时适当鼓励用户。"
        "使用更口语化的表达，避免生硬的术语堆砌。"
    ),
    "详细全面": (
        "你是一个资深分析师，回答详细全面，不遗漏任何重要细节。"
        "对于复杂问题，分条列点展开说明，每个要点提供充分的论据和数据支持。"
        "回答可以较长，但保证信息密度。"
    ),
    "幽默风趣": (
        "你是一个幽默的助手，回答风趣但信息准确。"
        "可以在回答中加入适当的比喻、调侃和俏皮话，让交流更轻松。"
        "但始终保持信息准确性，不因幽默牺牲数据可靠性。"
    ),
}


def get_default_tone() -> str:
    """返回配置中的默认语气名称。"""
    cfg = get_config()
    return cfg.get("chat", {}).get("tone", {}).get("default", "专业务实")


def get_tone_names() -> list[str]:
    """返回所有预设语气名称列表。"""
    return list(PRESETS.keys())


def get_tone_prompt(name: str) -> str:
    """根据语气名称获取对应的 System Prompt。未知名称返回默认。"""
    return PRESETS.get(name, PRESETS["专业务实"])


def format_tone_help() -> str:
    """返回语气帮助文本，供 CLI 使用。"""
    lines = ["可用语气预设："]
    for name, prompt in PRESETS.items():
        lines.append(f"  {name}  — {prompt[:60]}…")
    return "\n".join(lines)
