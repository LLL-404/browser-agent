"""BOSS 直聘特定的 DOM 语义规则。

针对 BOSS 直聘网站的 DOM 结构定制语义推断规则，
扩展默认的 SemanticInferrer 规则集以更好地识别 BOSS 直聘页面元素。
"""

from __future__ import annotations

from browser_agent.core.perceiver import SemanticType

# ── BOSS 直聘特定语义规则 ──
# 每条规则格式: (lambda el, semantic_type, confidence)
# 规则按优先级降序排列，匹配首个后停止
#
# 注意：el 是一个 dict，包含 tag、class_list、selector、text 等字段，
# 与 SemanticInferrer 中的 _text_contains / _tag_is 等辅助函数兼容。
ZHIPIN_RULES: list[tuple] = [
    # ── 搜索输入框 ──
    (
        lambda el: (
            el.get("tag", "") == "input"
            and (
                "ipt-search" in (el.get("class_list", "") or "").lower()
                or "search-form" in (el.get("class_list", "") or "").lower()
                or "keyword" in (el.get("class_list", "") or "").lower()
            )
        ),
        SemanticType.SEARCH_INPUT,
        0.90,
    ),
    # ── 搜索按钮 ──
    (
        lambda el: (
            el.get("tag", "") in ("button", "a", "span")
            and (
                "btn-search" in (el.get("class_list", "") or "").lower()
                or "search-btn" in (el.get("class_list", "") or "").lower()
            )
        ),
        SemanticType.SEARCH_BTN,
        0.90,
    ),
    # ── 职位列表项 ──
    (
        lambda el: (
            el.get("tag", "") in ("li", "div")
            and (
                "job-card" in (el.get("class_list", "") or "").lower()
                or "job-primary" in (el.get("class_list", "") or "").lower()
                or "job-list" in (el.get("class_list", "") or "").lower()
            )
        ),
        SemanticType.LIST_ITEM,
        0.85,
    ),
    # ── 职位卡片 ──
    (
        lambda el: (
            el.get("tag", "") in ("div", "li")
            and (
                "job-card-wrapper" in (el.get("class_list", "") or "").lower()
                or "card-wrapper" in (el.get("class_list", "") or "").lower()
            )
        ),
        SemanticType.CARD,
        0.85,
    ),
    # ── 职位详情链接 ──
    (
        lambda el: (
            el.get("tag", "") == "a"
            and (
                "/job_detail/" in (el.get("selector", "") or "")
                or "job-name" in (el.get("class_list", "") or "").lower()
                or "job-title" in (el.get("class_list", "") or "").lower()
            )
        ),
        SemanticType.DETAIL_LINK,
        0.85,
    ),
    # ── 翻页 — 下一页 ──
    (
        lambda el: (
            el.get("tag", "") in ("a", "button", "span")
            and (
                "next" in (el.get("class_list", "") or "").lower()
                or "page-next" in (el.get("class_list", "") or "").lower()
            )
            and "disabled" not in (el.get("class_list", "") or "").lower()
        ),
        SemanticType.NEXT_PAGE,
        0.80,
    ),
    # ── 翻页 — 上一页 ──
    (
        lambda el: (
            el.get("tag", "") in ("a", "button", "span")
            and (
                "prev" in (el.get("class_list", "") or "").lower()
                or "page-prev" in (el.get("class_list", "") or "").lower()
            )
            and "disabled" not in (el.get("class_list", "") or "").lower()
        ),
        SemanticType.PREV_PAGE,
        0.80,
    ),
    # ── 筛选/排序控件 ──
    (
        lambda el: (
            el.get("tag", "") in ("a", "button", "span", "select")
            and (
                "filter" in (el.get("class_list", "") or "").lower()
                or "sort" in (el.get("class_list", "") or "").lower()
                or "condition" in (el.get("class_list", "") or "").lower()
            )
        ),
        SemanticType.FILTER,
        0.75,
    ),
    # ── 导航 Tab（首页/搜索/公司等） ──
    (
        lambda el: (
            el.get("tag", "") in ("a", "li", "span")
            and (
                "nav-item" in (el.get("class_list", "") or "").lower()
                or "tab" in (el.get("class_list", "") or "").lower()
                or "menu-item" in (el.get("class_list", "") or "").lower()
            )
        ),
        SemanticType.TAB,
        0.80,
    ),
    # ── 导航链接（顶部导航栏） ──
    (
        lambda el: (
            el.get("tag", "") == "a"
            and (
                "nav" in (el.get("class_list", "") or "").lower()
                or "header" in (el.get("class_list", "") or "").lower()
            )
        ),
        SemanticType.NAV_LINK,
        0.80,
    ),
    # ── 登录按钮 ──
    (
        lambda el: (
            el.get("tag", "") in ("a", "button", "span")
            and (
                "btn-login" in (el.get("class_list", "") or "").lower()
                or "login-btn" in (el.get("class_list", "") or "").lower()
                or "register" in (el.get("class_list", "") or "").lower()
            )
        ),
        SemanticType.LOGIN_BTN,
        0.85,
    ),
    # ── 弹窗关闭按钮 ──
    (
        lambda el: (
            el.get("tag", "") in ("a", "button", "span", "i")
            and (
                "dialog-close" in (el.get("class_list", "") or "").lower()
                or "modal-close" in (el.get("class_list", "") or "").lower()
                or "close-btn" in (el.get("class_list", "") or "").lower()
            )
        ),
        SemanticType.CLOSE_DIALOG,
        0.80,
    ),
    # ── 职位详情区域 ──
    (
        lambda el: (
            el.get("tag", "") in ("div", "section")
            and (
                "job-detail" in (el.get("class_list", "") or "").lower()
                or "job-banner" in (el.get("class_list", "") or "").lower()
                or "detail-content" in (el.get("class_list", "") or "").lower()
            )
        ),
        SemanticType.CARD,
        0.80,
    ),
    # ── 公司信息区域 ──
    (
        lambda el: (
            el.get("tag", "") in ("div", "section", "a")
            and (
                "company-info" in (el.get("class_list", "") or "").lower()
                or "company-header" in (el.get("class_list", "") or "").lower()
                or "business-info" in (el.get("class_list", "") or "").lower()
            )
        ),
        SemanticType.CARD,
        0.80,
    ),
]


class ZhipinSemanticRules:
    """BOSS 直聘语义规则管理器。

    提供 BOSS 直聘特定的语义规则，可注入到 SemanticInferrer 中
    以增强对 BOSS 直聘页面 DOM 元素的识别能力。

    使用方式:
        inferrer = SemanticInferrer()
        zhipin_rules = ZhipinSemanticRules()
        inferrer.register_rules(zhipin_rules.get_rules())
    """

    def __init__(self) -> None:
        self._rules: list[tuple] = list(ZHIPIN_RULES)

    def get_rules(self) -> list[tuple]:
        """获取 BOSS 直聘语义规则列表。"""
        return self._rules

    def add_rule(self, rule_fn, semantic_type: str, confidence: float) -> None:
        """添加自定义规则（追加到末尾）。"""
        self._rules.append((rule_fn, semantic_type, confidence))

    def insert_rule(self, index: int, rule_fn, semantic_type: str, confidence: float) -> None:
        """在指定位置插入规则（优先级更高）。"""
        self._rules.insert(index, (rule_fn, semantic_type, confidence))

    def reset(self) -> None:
        """重置为默认规则集。"""
        self._rules = list(ZHIPIN_RULES)

    def __len__(self) -> int:
        return len(self._rules)
