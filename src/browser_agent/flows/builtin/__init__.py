"""内置通用流程模板。"""

from __future__ import annotations

from browser_agent.core.decider import ActionType, FlowSkeleton, FlowStep
from browser_agent.core.perceiver import PageType

# ── 通用搜索流程 ──
GENERIC_SEARCH_FLOW = FlowSkeleton(
    name="generic_search",
    description="通用搜索页流程：定位搜索框 → 输入 → 点击搜索 → 等待结果",
    url_pattern="*",
    page_type=PageType.SEARCH_RESULTS,
    steps=[
        FlowStep(action=ActionType.WAIT, target="body", wait_after=0.5),
        FlowStep(
            action=ActionType.TYPE,
            target="input[type='search'], input[placeholder*='搜索'], input[placeholder*='search']",
            value="",
            wait_after=0.5,
        ),
        FlowStep(
            action=ActionType.CLICK,
            target="button[type='submit'], .search-btn, button:has-text('搜索')",
            wait_after=2.0,
            fallback="input[type='search']",
        ),
        FlowStep(
            action=ActionType.EXTRACT,
            target=".result-item, .search-item, .list-item, [class*='result']",
            wait_after=0.5,
        ),
    ],
    on_error="ask_user",
)

# ── 通用登录页流程 ──
GENERIC_LOGIN_FLOW = FlowSkeleton(
    name="generic_login",
    description="通用登录页流程：填写用户名 → 密码 → 点击登录",
    url_pattern="*",
    page_type=PageType.LOGIN,
    steps=[
        FlowStep(action=ActionType.WAIT, target="body", wait_after=0.5),
        FlowStep(
            action=ActionType.TYPE,
            target="input[type='text'], input[name*='user'], input[placeholder*='用户']",
            value="",
            wait_after=0.3,
        ),
        FlowStep(
            action=ActionType.TYPE,
            target="input[type='password']",
            value="",
            wait_after=0.3,
        ),
        FlowStep(
            action=ActionType.CLICK,
            target="button[type='submit'], .login-btn, button:has-text('登录')",
            wait_after=2.0,
        ),
    ],
    on_error="ask_user",
)

# ── 验证码页流程 ──
CAPTCHA_FLOW = FlowSkeleton(
    name="captcha_encountered",
    description="遇到验证码时，暂停等待用户手动处理",
    url_pattern="*",
    page_type=PageType.CAPTCHA,
    steps=[
        FlowStep(action=ActionType.WAIT, target="body", wait_after=30.0),
    ],
    on_error="ask_user",
)

# ── 汇总列表 ──
BUILTIN_FLOWS: list[FlowSkeleton] = [
    GENERIC_SEARCH_FLOW,
    GENERIC_LOGIN_FLOW,
    CAPTCHA_FLOW,
]

__all__ = ["BUILTIN_FLOWS"]
