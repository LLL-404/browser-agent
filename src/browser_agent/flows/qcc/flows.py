"""QCC（企查查）预定义浏览流程模板。"""

from __future__ import annotations

from browser_agent.core.decider import ActionType, FlowSkeleton, FlowStep
from browser_agent.core.perceiver import PageType

# ── QCC 搜索流程 ──
QCC_SEARCH_FLOW = FlowSkeleton(
    name="qcc_search",
    description="企查查企业搜索流程：输入公司名称 → 搜索 → 提取结果列表",
    url_pattern="*qcc.com*",
    page_type=PageType.HOME,
    steps=[
        FlowStep(
            action=ActionType.WAIT,
            target="body",
            wait_after=0.5,
        ),
        FlowStep(
            action=ActionType.CLICK,
            target="#searchKey, input[placeholder*='企业'], input[placeholder*='搜索']",
            wait_after=0.5,
            fallback="input[type='search']",
        ),
        FlowStep(
            action=ActionType.TYPE,
            target="#searchKey, input[placeholder*='企业'], input[placeholder*='搜索']",
            value="",  # 由调用方注入公司名称
            wait_after=0.5,
        ),
        FlowStep(
            action=ActionType.CLICK,
            target=".btn-search, button:has-text('搜索'), .search-btn",
            wait_after=2.0,
            fallback="button[type='submit']",
        ),
        FlowStep(
            action=ActionType.WAIT,
            target=".search-result, .company-list, .result-list",
            wait_after=1.0,
            fallback="body",
        ),
        FlowStep(
            action=ActionType.EXTRACT,
            target=".search-result .company-item, [class*='company-item'], [class*='result-item']",
            wait_after=0.5,
        ),
        FlowStep(
            action=ActionType.DONE,
            target="",
            wait_after=0,
        ),
    ],
    on_error="retry",
)

# ── QCC 企业详情流程 ──
QCC_DETAIL_FLOW = FlowSkeleton(
    name="qcc_detail",
    description="企查查企业详情页流程：进入详情页 → 提取企业信息",
    url_pattern="*qcc.com/company*",
    page_type=PageType.DETAIL,
    steps=[
        FlowStep(
            action=ActionType.WAIT,
            target=".company-header, .company-info, .company-basic",
            wait_after=1.0,
            fallback="body",
        ),
        FlowStep(
            action=ActionType.EXTRACT,
            target=".company-header, .company-info, .company-basic",
            wait_after=0.5,
        ),
        FlowStep(
            action=ActionType.DONE,
            target="",
            wait_after=0,
        ),
    ],
    on_error="ask_user",
)

# ── 汇总列表 ──
QCC_FLOWS: list[FlowSkeleton] = [QCC_SEARCH_FLOW, QCC_DETAIL_FLOW]

__all__ = ["QCC_FLOWS"]
