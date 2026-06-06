"""QCC（企查查）特定的 DOM 语义规则。

针对企查查网站的 DOM 结构定制语义推断规则，
扩展默认的 SemanticInferrer 规则集以更好地识别 QCC 页面元素。
"""

from __future__ import annotations

from browser_agent.core.perceiver import SemanticType

# ── QCC 特定语义规则 ──
# 每条规则格式: (lambda el, semantic_type, confidence)
# 规则按优先级降序排列，匹配首个后停止
QCC_RULES: list[tuple] = [
    # ── QCC 搜索相关 ──
    (
        lambda el: (
            el.get("tag", "") == "input"
            and (
                "qcc" in (el.get("class_list", "") or "").lower()
                or "#searchKey" in (el.get("selector", "") or "")
            )
        ),
        SemanticType.SEARCH_INPUT,
        0.85,
    ),
    (
        lambda el: (
            el.get("tag", "") in ("button", "a")
            and (
                "btn-search" in (el.get("class_list", "") or "").lower()
                or "search-btn" in (el.get("class_list", "") or "").lower()
            )
        ),
        SemanticType.SEARCH_BTN,
        0.85,
    ),

    # ── QCC 企业列表项 ──
    (
        lambda el: (
            el.get("tag", "") in ("div", "li", "a")
            and (
                "company-item" in (el.get("class_list", "") or "").lower()
                or "result-item" in (el.get("class_list", "") or "").lower()
            )
        ),
        SemanticType.CARD,
        0.80,
    ),

    # ── QCC 企业详情链接 ──
    (
        lambda el: (
            el.get("tag", "") == "a"
            and (
                "/company/" in (el.get("selector", "") or "")
                or "/firm/" in (el.get("selector", "") or "")
            )
            and "company" in (el.get("class_list", "") or "").lower()
        ),
        SemanticType.DETAIL_LINK,
        0.85,
    ),

    # ── QCC 筛选/Tab ──
    (
        lambda el: (
            el.get("tag", "") in ("a", "button", "span")
            and (
                "filter" in (el.get("class_list", "") or "").lower()
                or "tab" in (el.get("class_list", "") or "").lower()
            )
            and "qcc" in (el.get("class_list", "") or "").lower()
        ),
        SemanticType.TAB,
        0.80,
    ),

    # ── QCC 导航链接 ──
    (
        lambda el: (
            el.get("tag", "") == "a"
            and any(
                kw in (el.get("class_list", "") or "").lower()
                for kw in ("breadcrumb", "nav-item", "nav-link")
            )
        ),
        SemanticType.NAV_LINK,
        0.80,
    ),
]


class QccSemanticRules:
    """QCC 语义规则管理器。

    提供 QCC 特定的语义规则，可注入到 SemanticInferrer 中
    以增强对企查查页面 DOM 元素的识别能力。

    使用方式:
        inferrer = SemanticInferrer()
        qcc_rules = QccSemanticRules()
        inferrer.register_rules(qcc_rules.get_rules())
    """

    def __init__(self) -> None:
        self._rules: list[tuple] = list(QCC_RULES)

    def get_rules(self) -> list[tuple]:
        """获取 QCC 语义规则列表。"""
        return self._rules

    def add_rule(self, rule_fn, semantic_type: str, confidence: float) -> None:
        """添加自定义规则（追加到末尾）。"""
        self._rules.append((rule_fn, semantic_type, confidence))

    def insert_rule(self, index: int, rule_fn, semantic_type: str, confidence: float) -> None:
        """在指定位置插入规则（优先级更高）。"""
        self._rules.insert(index, (rule_fn, semantic_type, confidence))

    def reset(self) -> None:
        """重置为默认规则集。"""
        self._rules = list(QCC_RULES)

    def __len__(self) -> int:
        return len(self._rules)
