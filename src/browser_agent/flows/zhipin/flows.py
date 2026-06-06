"""BOSS 直聘预定义浏览流程模板。

包含两个核心流程：
  - zhipin_search  — 职位搜索流程：首页 → 搜索 → 提取结果列表 → 翻页
  - zhipin_detail  — 职位详情流程：详情页 → 提取职位信息
"""

from __future__ import annotations

from browser_agent.core.decider import ActionType, FlowSkeleton, FlowStep
from browser_agent.core.perceiver import PageType

# ── BOSS 直聘搜索流程 ──
zhipin_search = FlowSkeleton(
    name="zhipin_search",
    description="BOSS 直聘职位搜索流程：搜索关键词 → 提取结果列表 → 翻页浏览",
    url_pattern="*zhipin.com*",
    page_type=PageType.HOME,
    steps=[
        # 1. 等待页面加载完成
        FlowStep(
            action=ActionType.WAIT,
            target="body",
            wait_after=1.0,
        ),
        # 2. 点击搜索输入框
        FlowStep(
            action=ActionType.CLICK,
            target=(
                ".search-form input, "
                ".ipt-search, "
                "input[placeholder*='搜索职位'], "
                "input[placeholder*='搜索'], "
                "input[name='query']"
            ),
            wait_after=0.3,
            fallback=(
                "input[type='search'], "
                "input[class*='search']"
            ),
        ),
        # 3. 输入搜索关键词（value 由调用方注入）
        FlowStep(
            action=ActionType.TYPE,
            target=(
                ".search-form input, "
                ".ipt-search, "
                "input[placeholder*='搜索职位'], "
                "input[name='query']"
            ),
            value="",  # 由调用方注入
            wait_after=0.5,
        ),
        # 4. 点击搜索按钮
        FlowStep(
            action=ActionType.CLICK,
            target=(
                ".btn-search, "
                "button:has-text('搜索'), "
                ".search-btn, "
                "button[type='submit']"
            ),
            wait_after=2.0,
            fallback=".search-form button, .search-box button",
        ),
        # 5. 等待搜索结果加载
        FlowStep(
            action=ActionType.WAIT,
            target=".job-list-box, .job-list, .search-job-result",
            wait_after=1.0,
            fallback="body",
        ),
        # 6. 提取当前页职位列表数据（条件：在搜索结果页）
        FlowStep(
            action=ActionType.EXTRACT,
            target=(
                ".job-card-wrapper, "
                ".job-list li, "
                ".job-list-box .job-primary, "
                "[class*='job-card']"
            ),
            wait_after=0.5,
            condition=(
                ".job-list-box, "
                ".job-list, "
                ".search-job-result"
            ),
        ),
        # 7. 翻页 — 点击下一页（条件：存在可点击的下一页，回退：停止翻页）
        FlowStep(
            action=ActionType.CLICK,
            target=(
                ".page .next, "
                ".pagination .next, "
                "a:has-text('下一页'), "
                ".next-page:not(.disabled)"
            ),
            wait_after=1.5,
            condition=(
                ".page .next:not(.disabled), "
                ".pagination .next:not(.disabled), "
                ".next-page:not(.disabled)"
            ),
            fallback="stop",
        ),
        # 8. 翻页后提取新一页数据
        FlowStep(
            action=ActionType.EXTRACT,
            target=(
                ".job-card-wrapper, "
                ".job-list li, "
                ".job-list-box .job-primary, "
                "[class*='job-card']"
            ),
            wait_after=0.5,
            condition=(
                ".job-list-box, "
                ".job-list, "
                ".search-job-result"
            ),
        ),
    ],
    on_error="ask_user",
)

# ── BOSS 直聘职位详情流程 ──
zhipin_detail = FlowSkeleton(
    name="zhipin_detail",
    description="BOSS 直聘职位详情页流程：进入详情页 → 提取职位信息",
    url_pattern="*zhipin.com/job_detail*",
    page_type=PageType.DETAIL,
    steps=[
        # 1. 等待详情页核心内容加载
        FlowStep(
            action=ActionType.WAIT,
            target=(
                ".job-detail, "
                ".job-banner, "
                ".detail-content, "
                ".job-sec"
            ),
            wait_after=1.0,
            fallback="body",
        ),
        # 2. 滚动页面以触发懒加载内容
        FlowStep(
            action=ActionType.SCROLL,
            target="",
            value="400",
            wait_after=0.5,
        ),
        # 3. 提取职位详细信息
        FlowStep(
            action=ActionType.EXTRACT,
            target=(
                ".job-detail, "
                ".job-banner, "
                ".detail-content, "
                ".job-sec"
            ),
            wait_after=0.5,
        ),
        # 4. 完成
        FlowStep(
            action=ActionType.DONE,
            target="",
            wait_after=0,
        ),
    ],
    on_error="ask_user",
)

# ── 汇总列表 ──
ZHIPIN_FLOWS: list[FlowSkeleton] = [zhipin_search, zhipin_detail]

__all__ = ["ZHIPIN_FLOWS"]
