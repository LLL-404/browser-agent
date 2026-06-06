"""内置浏览流程骨架（FlowSkeleton）定义。

包含常见浏览模式的可复用流程模板：
  - generic_login       — 通用登录流程
  - generic_search      — 通用搜索流程
  - generic_pagination  — 通用翻页流程
  - captcha_encountered — 验证码处理流程
"""

from __future__ import annotations

from browser_agent.core.decider import ActionType, FlowSkeleton, FlowStep
from browser_agent.core.perceiver import PageType

# =============================================================================
# 通用登录流程
# =============================================================================

generic_login = FlowSkeleton(
    name="generic_login",
    description="通用登录流程：点击用户名输入框 → 输入用户名 → 点击密码输入框 → 输入密码 → 点击登录按钮 → 等待跳转",
    url_pattern="*",
    page_type=PageType.LOGIN,
    steps=[
        FlowStep(
            action=ActionType.WAIT,
            target="body",
            wait_after=0.5,
        ),
        FlowStep(
            action=ActionType.CLICK,
            target=(
                "input[type='text'][name*='user'], "
                "input[type='email'], "
                "input[placeholder*='用户'], "
                "input[placeholder*='账号'], "
                "input[name*='account'], "
                "input[name*='username']"
            ),
            wait_after=0.3,
            fallback="input:not([type='password']):not([type='hidden']):not([type='submit'])",
        ),
        FlowStep(
            action=ActionType.TYPE,
            target=(
                "input[type='text'][name*='user'], "
                "input[type='email'], "
                "input[name*='username'], "
                "input[name*='account']"
            ),
            value="",  # 由调用方注入
            wait_after=0.3,
        ),
        FlowStep(
            action=ActionType.CLICK,
            target="input[type='password']",
            wait_after=0.3,
            fallback="input[name*='pass']",
        ),
        FlowStep(
            action=ActionType.TYPE,
            target="input[type='password']",
            value="",  # 由调用方注入
            wait_after=0.3,
        ),
        FlowStep(
            action=ActionType.CLICK,
            target=(
                "button[type='submit'], "
                "input[type='submit'], "
                ".login-btn, "
                "button:has-text('登录'), "
                "button:has-text('登 录'), "
                "button:has-text('Sign in'), "
                "a:has-text('登录')"
            ),
            wait_after=2.0,
            fallback="form button, form input[type='submit']",
        ),
        FlowStep(
            action=ActionType.WAIT,
            target="body",
            wait_after=2.0,
            condition=":not(form input[type='password'])",
        ),
    ],
    on_error="ask_user",
)

# =============================================================================
# 通用搜索流程
# =============================================================================

generic_search = FlowSkeleton(
    name="generic_search",
    description="通用搜索流程：定位搜索框 → 点击 → 输入查询词 → 点击搜索按钮 → 等待结果 → 提取列表项",
    url_pattern="*",
    page_type=PageType.SEARCH_RESULTS,
    steps=[
        FlowStep(
            action=ActionType.WAIT,
            target="body",
            wait_after=0.5,
        ),
        FlowStep(
            action=ActionType.CLICK,
            target=(
                "input[type='search'], "
                "input[placeholder*='搜索'], "
                "input[placeholder*='search'], "
                "input[name='q'], "
                "input[name='query'], "
                "input[name='keyword'], "
                "input[aria-label*='search'], "
                "input[aria-label*='搜索']"
            ),
            wait_after=0.3,
            fallback=".search-input input, .search-box input",
        ),
        FlowStep(
            action=ActionType.TYPE,
            target=(
                "input[type='search'], "
                "input[name='q'], "
                "input[name='query'], "
                "input[name='keyword']"
            ),
            value="",  # 由调用方注入
            wait_after=0.3,
        ),
        FlowStep(
            action=ActionType.CLICK,
            target=(
                "button[type='submit'], "
                ".search-btn, "
                ".btn-search, "
                "button:has-text('搜索'), "
                "button:has-text('搜 索'), "
                "button:has-text('Search'), "
                "input[type='submit']"
            ),
            wait_after=2.0,
            fallback="form button",
        ),
        FlowStep(
            action=ActionType.WAIT,
            target=(
                ".result-item, "
                ".search-item, "
                ".list-item, "
                "[class*='result'], "
                "li[class*='item']"
            ),
            wait_after=1.0,
            fallback="body",
        ),
        FlowStep(
            action=ActionType.EXTRACT,
            target=(
                ".result-item, "
                ".search-item, "
                ".list-item, "
                "[class*='result'], "
                "li[class*='item']"
            ),
            wait_after=0.5,
        ),
    ],
    on_error="ask_user",
)

# =============================================================================
# 通用翻页流程
# =============================================================================

generic_pagination = FlowSkeleton(
    name="generic_pagination",
    description="通用翻页流程：提取当前页数据 → 点击下一页 → 提取下一页数据",
    url_pattern="*",
    page_type=PageType.LIST,
    steps=[
        FlowStep(
            action=ActionType.WAIT,
            target="body",
            wait_after=0.5,
        ),
        FlowStep(
            action=ActionType.EXTRACT,
            target=(
                ".list-item, "
                ".card, "
                "[class*='list'], "
                "li, "
                "article"
            ),
            wait_after=0.5,
        ),
        FlowStep(
            action=ActionType.CLICK,
            target=(
                "a[rel='next'], "
                ".next, "
                ".next-page, "
                ".pagination .next, "
                "button[aria-label='下一页'], "
                "a:has-text('下一页'), "
                "a:has-text('>'), "
                "a:has-text('»')"
            ),
            value="",
            wait_after=2.0,
            condition=(
                "a[rel='next'], "
                ".next:not(.disabled), "
                ".next-page:not(.disabled), "
                ".pagination .next:not(.disabled)"
            ),
            fallback=(
                ".pager .next, "
                ".paginator .next, "
                "nav a:last-child"
            ),
        ),
        FlowStep(
            action=ActionType.EXTRACT,
            target=(
                ".list-item, "
                ".card, "
                "[class*='list'], "
                "li, "
                "article"
            ),
            wait_after=0.5,
        ),
    ],
    on_error="retry",
)

# =============================================================================
# 验证码处理流程
# =============================================================================

captcha_encountered = FlowSkeleton(
    name="captcha_encountered",
    description="验证码处理流程：等待 → 截图 → 报告用户 → 停止",
    url_pattern="*",
    page_type=PageType.CAPTCHA,
    steps=[
        FlowStep(
            action=ActionType.WAIT,
            target="body",
            wait_after=5.0,
        ),
        FlowStep(
            action=ActionType.SCREENSHOT,
            target="body",
            wait_after=0.5,
        ),
        FlowStep(
            action=ActionType.DONE,
            target="",
            value="captcha_detected: 检测到验证码，已截图，需要用户手动处理",
            wait_after=0.0,
        ),
    ],
    on_error="ask_user",
)

# =============================================================================
# 内置流程集合
# =============================================================================

BUILTIN_FLOWS: list[FlowSkeleton] = [
    generic_login,
    generic_search,
    generic_pagination,
    captcha_encountered,
]

__all__ = ["BUILTIN_FLOWS"]
