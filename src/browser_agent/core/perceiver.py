"""感知层 — 页面元素标注、语义推断、页面分类与快照生成。"""
from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import Page

from shared.logging_config import get_logger

logger = get_logger("perceiver")


# =============================================================================
# 常量定义
# =============================================================================

class PageType:
    """页面类型枚举常量。"""
    SEARCH_RESULTS = "search_results"
    DETAIL = "detail"
    LIST = "list"
    FORM = "form"
    LOGIN = "login"
    CAPTCHA = "captcha"
    HOME = "home"
    ERROR = "error"
    UNKNOWN = "unknown"


class SemanticType:
    """语义类型常量，用于标注元素的功能角色。"""
    NAV_LINK = "nav_link"
    BREADCRUMB = "breadcrumb"
    TAB = "tab"
    SEARCH_INPUT = "search_input"
    SEARCH_BTN = "search_btn"
    FILTER = "filter"
    SORT = "sort"
    NEXT_PAGE = "next_page"
    PREV_PAGE = "prev_page"
    PAGE_NUMBER = "page_number"
    FORM_INPUT = "form_input"
    SUBMIT_BTN = "submit_btn"
    SELECT = "select"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    CLOSE_DIALOG = "close_dialog"
    CONFIRM_BTN = "confirm_btn"
    CANCEL_BTN = "cancel_btn"
    LIST_ITEM = "list_item"
    CARD = "card"
    DETAIL_LINK = "detail_link"
    LOGIN_BTN = "login_btn"
    USERNAME_INPUT = "username_input"
    PASSWORD_INPUT = "password_input"
    CAPTCHA = "captcha"
    SLIDER = "slider"
    AGREE_BTN = "agree_btn"


# =============================================================================
# 数据类
# =============================================================================

@dataclass
class AnnotatedElement:
    """标注后的页面元素。"""
    tag: str
    role: str
    text: str
    selector: str
    semantic_type: str
    confidence: float
    is_visible: bool
    is_interactable: bool
    bounding_box: dict[str, float] | None = None
    input_type: str = ""
    options: list[str] = field(default_factory=list)
    ref: int | None = None


@dataclass
class FormGroup:
    """表单组，将关联的表单元素与提交按钮聚合。"""
    elements: list[AnnotatedElement]
    submit_button: AnnotatedElement | None = None


@dataclass
class PaginationInfo:
    """分页信息。"""
    current: int
    total: int | None = None
    next_element: AnnotatedElement | None = None
    prev_element: AnnotatedElement | None = None
    page_elements: list[AnnotatedElement] = field(default_factory=list)


# =============================================================================
# 规则匹配辅助
# =============================================================================

def _text_contains(el: dict, *keywords: str) -> bool:
    """检查元素文本/placeholder/aria-label 是否包含任一关键词。"""
    text_sources = [
        (el.get("text") or "").lower(),
        (el.get("placeholder") or "").lower(),
        (el.get("aria_label") or "").lower(),
    ]
    combined = " ".join(filter(None, text_sources))
    return any(kw in combined for kw in keywords)


def _tag_is(el: dict, *tags: str) -> bool:
    return el.get("tag", "").lower() in tags


def _role_is(el: dict, *roles: str) -> bool:
    return el.get("role", "").lower() in roles


def _attr_contains(el: dict, attr: str, *keywords: str) -> bool:
    val = (el.get(attr) or "").lower()
    return any(kw in val for kw in keywords)


# =============================================================================
# SemanticInferrer — 语义推断器
# =============================================================================

class SemanticInferrer:
    """基于规则和启发式方法推断页面元素的语义类型。"""

    # 规则列表: (lambda el, confidence, semantic_type)，按优先级排列
    RULES: list[tuple[Any, str, float]] = [
        # ── 导航类 ──
        (lambda el: _role_is(el, "navigation") or _tag_is(el, "nav"), SemanticType.NAV_LINK, 0.9),
        (lambda el: _attr_contains(el, "class", "breadcrumb", "breadcrumbs"),
         SemanticType.BREADCRUMB, 0.85),
        (lambda el: _role_is(el, "tab") or _attr_contains(el, "role", "tab"),
         SemanticType.TAB, 0.9),

        # ── 搜索类 ──
        (lambda el: (_tag_is(el, "input") and _text_contains(el, "search", "搜索")) or
         _attr_contains(el, "type", "search"),
         SemanticType.SEARCH_INPUT, 0.85),
        (lambda el: _tag_is(el, "button", "a") and _text_contains(el, "search", "搜索", "查找"),
         SemanticType.SEARCH_BTN, 0.8),

        # ── 筛选/排序类 ──
        (lambda el: _text_contains(el, "filter", "筛选", "filters") and _tag_is(el, "button", "a", "select"),
         SemanticType.FILTER, 0.75),
        (lambda el: _text_contains(el, "sort", "排序", "order by") and _tag_is(el, "button", "a", "select"),
         SemanticType.SORT, 0.75),

        # ── 分页类 ──
        (lambda el: _tag_is(el, "button", "a") and _text_contains(el, "next", "下一页", "»", ">"),
         SemanticType.NEXT_PAGE, 0.7),
        (lambda el: _tag_is(el, "button", "a") and _text_contains(el, "prev", "上一页", "«", "<"),
         SemanticType.PREV_PAGE, 0.7),
        (lambda el: (_tag_is(el, "button", "a", "span") and
         (el.get("text") or "").strip().isdigit() and
         _attr_contains(el, "class", "page", "pagination")),
         SemanticType.PAGE_NUMBER, 0.65),

        # ── 表单类 ──
        (lambda el: _tag_is(el, "input") and _attr_contains(el, "type", "text", "email", "tel", "number"),
         SemanticType.FORM_INPUT, 0.7),
        (lambda el: _tag_is(el, "button", "input") and
         _text_contains(el, "submit", "提交", "保存", "save") or _attr_contains(el, "type", "submit"),
         SemanticType.SUBMIT_BTN, 0.8),
        (lambda el: _tag_is(el, "select"),
         SemanticType.SELECT, 0.95),
        (lambda el: _tag_is(el, "input") and _attr_contains(el, "type", "checkbox"),
         SemanticType.CHECKBOX, 0.95),
        (lambda el: _tag_is(el, "input") and _attr_contains(el, "type", "radio"),
         SemanticType.RADIO, 0.95),

        # ── 弹窗类 ──
        (lambda el: _text_contains(el, "close", "关闭", "×", "x") and
         _tag_is(el, "button", "a", "span") and
         not _text_contains(el, "close dialog", "close window"),
         SemanticType.CLOSE_DIALOG, 0.75),
        (lambda el: _text_contains(el, "confirm", "确认", "ok", "确定") and _tag_is(el, "button"),
         SemanticType.CONFIRM_BTN, 0.8),
        (lambda el: _text_contains(el, "cancel", "取消") and _tag_is(el, "button", "a"),
         SemanticType.CANCEL_BTN, 0.8),

        # ── 列表/卡片类 ──
        (lambda el: _role_is(el, "listitem") or _tag_is(el, "li"),
         SemanticType.LIST_ITEM, 0.7),
        (lambda el: _attr_contains(el, "class", "card"),
         SemanticType.CARD, 0.7),
        (lambda el: _tag_is(el, "a") and _attr_contains(el, "href", "/") and
         _attr_contains(el, "class", "title", "link", "detail"),
         SemanticType.DETAIL_LINK, 0.7),

        # ── 登录类 ──
        (lambda el: _text_contains(el, "login", "登录", "sign in") and _tag_is(el, "button", "a"),
         SemanticType.LOGIN_BTN, 0.85),
        (lambda el: _tag_is(el, "input") and
         _text_contains(el, "username", "用户名", "email", "account", "账号"),
         SemanticType.USERNAME_INPUT, 0.85),
        (lambda el: _tag_is(el, "input") and
         _text_contains(el, "password", "密码", "passwd"),
         SemanticType.PASSWORD_INPUT, 0.85),

        # ── 验证码 / 行为验证 ──
        (lambda el: _text_contains(el, "captcha", "验证码", "verification"),
         SemanticType.CAPTCHA, 0.8),
        (lambda el: _attr_contains(el, "class", "slider", "slide", "drag") and _tag_is(el, "div"),
         SemanticType.SLIDER, 0.75),
        (lambda el: _text_contains(el, "agree", "同意", "accept") and
         (_tag_is(el, "input", "button") or _attr_contains(el, "type", "checkbox")),
         SemanticType.AGREE_BTN, 0.75),
    ]

    # 启发式规则（基于上下文的后处理），格式: (lambda element, context_elements, bool, confidence, semantic_type)
    HEURISTICS: list[tuple[Any, str, float]] = []

    def __init__(self):
        self._rules = list(self.RULES)

    def infer(self, element: dict, _context: list[dict] | None = None) -> AnnotatedElement:
        """对原始元素执行语义推断，返回标注后的 AnnotatedElement。

        参数:
            element: 从 page.evaluate 获得的原始元素字典。
            context: 周围元素列表，用于上下文推断（可选）。

        返回:
            填充了语义类型的 AnnotatedElement。
        """
        semantic_type = SemanticType.NAV_LINK  # 默认回退类型
        confidence = 0.0

        for rule_fn, sem_type, conf in self._rules:
            try:
                if rule_fn(element):
                    semantic_type = sem_type
                    confidence = conf
                    break  # 按优先级取首个匹配
            except Exception:  # pylint: disable=broad-exception-caught
                continue

        # 构建 AnnotatedElement
        bbox = element.get("bounding_box")
        if bbox and isinstance(bbox, dict):
            bounding_box = {"x": bbox.get("x", 0), "y": bbox.get("y", 0),
                            "width": bbox.get("width", 0), "height": bbox.get("height", 0)}
        else:
            bounding_box = None

        return AnnotatedElement(
            tag=element.get("tag", ""),
            role=element.get("role", ""),
            text=element.get("text", ""),
            selector=element.get("selector", ""),
            semantic_type=semantic_type,
            confidence=confidence,
            is_visible=element.get("is_visible", False),
            is_interactable=element.get("is_interactable", False),
            bounding_box=bounding_box,
            input_type=element.get("input_type", ""),
            options=list(element.get("options", []) or []),
            ref=element.get("ref"),
        )


# =============================================================================
# PageClassifier — 页面分类器
# =============================================================================

class PageClassifier:
    """基于快照信息判断当前页面类型。"""

    def classify(self, snapshot: PageSnapshot) -> str:
        """根据快照中的元素分布推断页面类型，返回 PageType 常量值。"""
        elements = snapshot.elements
        element_count = len(elements)

        # 空页面 → 错误页
        if element_count == 0:
            return PageType.ERROR

        sem_counts = self._count_semantic_types(elements)

        # 验证码优先
        if sem_counts.get(SemanticType.CAPTCHA, 0) >= 1 or sem_counts.get(SemanticType.SLIDER, 0) >= 1:
            return PageType.CAPTCHA

        # 登录页
        login_score = (sem_counts.get(SemanticType.USERNAME_INPUT, 0) +
                       sem_counts.get(SemanticType.PASSWORD_INPUT, 0) +
                       sem_counts.get(SemanticType.LOGIN_BTN, 0))
        if login_score >= 2:
            return PageType.LOGIN

        # 表单页
        form_score = (sem_counts.get(SemanticType.FORM_INPUT, 0) +
                      sem_counts.get(SemanticType.SUBMIT_BTN, 0) +
                      sem_counts.get(SemanticType.SELECT, 0) +
                      sem_counts.get(SemanticType.CHECKBOX, 0) +
                      sem_counts.get(SemanticType.RADIO, 0))
        if form_score >= 3:
            return PageType.FORM

        # 搜索结果页
        search_score = (sem_counts.get(SemanticType.SEARCH_INPUT, 0) +
                        sem_counts.get(SemanticType.SEARCH_BTN, 0))
        card_score = sem_counts.get(SemanticType.CARD, 0) + sem_counts.get(SemanticType.LIST_ITEM, 0)
        if search_score >= 1 and card_score >= 3:
            return PageType.SEARCH_RESULTS

        # 首页
        nav_score = (sem_counts.get(SemanticType.NAV_LINK, 0) +
                     sem_counts.get(SemanticType.TAB, 0) +
                     sem_counts.get(SemanticType.BREADCRUMB, 0))
        if nav_score >= 3 and card_score < 5:
            return PageType.HOME

        # 列表页
        list_score = (sem_counts.get(SemanticType.LIST_ITEM, 0) +
                      sem_counts.get(SemanticType.CARD, 0))
        pagination = sem_counts.get(SemanticType.NEXT_PAGE, 0) or sem_counts.get(SemanticType.PREV_PAGE, 0)
        if list_score >= 5:
            return PageType.LIST
        if pagination and list_score >= 2:
            return PageType.LIST

        # 详情页
        detail_score = sem_counts.get(SemanticType.DETAIL_LINK, 0)
        if detail_score <= 2 and list_score < 5 and nav_score < 5:
            return PageType.DETAIL

        return PageType.UNKNOWN

    @staticmethod
    def _count_semantic_types(elements: list[AnnotatedElement]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for el in elements:
            counts[el.semantic_type] = counts.get(el.semantic_type, 0) + 1
        return counts


# =============================================================================
# PageSnapshot — 页面快照
# =============================================================================

@dataclass
class PageSnapshot:
    """页面感知结果的完整快照。"""
    url: str
    title: str
    page_type: str = PageType.UNKNOWN
    elements: list[AnnotatedElement] = field(default_factory=list)
    forms: list[FormGroup] = field(default_factory=list)
    pagination: PaginationInfo | None = None
    dialogs: list[AnnotatedElement] = field(default_factory=list)
    navigation: list[AnnotatedElement] = field(default_factory=list)
    main_content: str = ""
    content_type: str = ""
    timestamp: float = field(default_factory=time.time)
    load_state: str = "loading"
    has_captcha: bool = False
    has_block_text: bool = False
    redirect_count: int = 0

    def elements_by_type(self, sem_type: str) -> list[AnnotatedElement]:
        """获取指定语义类型的所有元素。"""
        return [el for el in self.elements if el.semantic_type == sem_type]

    def find_element(self, sem_type: str, text: str | None = None) -> AnnotatedElement | None:
        """查找指定语义类型的元素，可选按文本过滤。"""
        for el in self.elements:
            if el.semantic_type != sem_type:
                continue
            if text is None or text.lower() in el.text.lower():
                return el
        return None

    def find_by_ref(self, ref: int) -> AnnotatedElement | None:
        """通过引用编号查找元素。"""
        for el in self.elements:
            if el.ref == ref:
                return el
        return None

    def to_text_description(self) -> str:
        """生成人类可读的页面文本描述。

        格式: "  [i] semantic_type[@ref]: text (selector)"
        """
        lines = []
        lines.append(f"URL: {self.url}")
        lines.append(f"标题: {self.title}")
        lines.append(f"页面类型: {self.page_type}")
        lines.append(f"加载状态: {self.load_state}")

        if self.elements:
            lines.append(f"\n元素 ({len(self.elements)}):")
            for i, el in enumerate(self.elements):
                ref_str = f"@{el.ref}" if el.ref is not None else ""
                bufs = []
                if el.text:
                    bufs.append(el.text)
                if el.selector:
                    bufs.append(el.selector)
                line = f"  [{i}] {el.semantic_type}{ref_str}: {' | '.join(bufs)}"
                lines.append(line)

        if self.forms:
            lines.append(f"\n表单 ({len(self.forms)}):")
            for fi, form in enumerate(self.forms):
                lines.append(f"  表单 {fi}: {len(form.elements)} 个元素, "
                             f"提交按钮={'有' if form.submit_button else '无'}")

        if self.navigation:
            lines.append(f"\n导航 ({len(self.navigation)}):")
            for nav in self.navigation:
                lines.append(f"  - {nav.semantic_type}: {nav.text}")

        if self.pagination:
            pag = self.pagination
            lines.append(f"\n分页: 当前 {pag.current}, "
                         f"共 {pag.total if pag.total is not None else '?'} 页")

        if self.dialogs:
            lines.append(f"\n弹窗 ({len(self.dialogs)}):")
            for dlg in self.dialogs:
                lines.append(f"  - {dlg.semantic_type}: {dlg.text}")

        return "\n".join(lines)


# =============================================================================
# PagePerceiver — 页面感知器（主入口）
# =============================================================================

@dataclass
class PagePerceiver:
    """页面感知器，整合语义推断与页面分类，生成 PageSnapshot。"""

    inferrer: SemanticInferrer = field(default_factory=SemanticInferrer)
    classifier: PageClassifier = field(default_factory=PageClassifier)

    async def perceive(self, page: Page) -> PageSnapshot:
        """对当前页面执行完整感知，返回 PageSnapshot。"""
        url = page.url
        title = ""
        with contextlib.suppress(Exception):
            title = await page.title()

        # 各感知步骤可并行执行
        elements, forms, pagination, dialogs, nav_elements = await asyncio_gather_optional(
            self._annotate_elements(page),
            self._extract_forms(page),
            self._detect_pagination(page),
            self._detect_dialogs(page),
            self._detect_nav(page),
        )

        # 主内容
        main_content = ""
        try:
            main_content = await page.evaluate("document.body?.innerText || ''")
            main_content = main_content[:5000]
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        # 内容类型
        content_type = ""
        with contextlib.suppress(Exception):
            content_type = await page.evaluate(
                "document.contentType || document.documentElement?.getAttribute('lang') || ''"
            )

        # 验证码检测
        has_captcha = any(
            el.semantic_type in (SemanticType.CAPTCHA, SemanticType.SLIDER)
            for el in elements
        )

        # 封禁文本检测
        has_block_text = self._detect_block_text(main_content)

        # 加载状态
        load_state = await self._get_load_state(page)

        # 构建快照
        snapshot = PageSnapshot(
            url=url,
            title=title,
            elements=elements,
            forms=forms,
            pagination=pagination,
            dialogs=dialogs,
            navigation=nav_elements,
            main_content=main_content,
            content_type=content_type,
            load_state=load_state,
            has_captcha=has_captcha,
            has_block_text=has_block_text,
        )

        # 分类页面
        snapshot.page_type = self.classifier.classify(snapshot)

        return snapshot

    async def _annotate_elements(self, page: Page) -> list[AnnotatedElement]:
        """通过 JS 获取页面中所有可见可交互元素，并用 SemanticInferrer 标注。"""
        try:
            raw_elements = await page.evaluate(self._JS_EXTRACT_ELEMENTS)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("元素提取失败: %s", e)
            return []

        annotated: list[AnnotatedElement] = []
        for i, raw in enumerate(raw_elements):
            el = self.inferrer.infer(raw)
            el.ref = i  # 分配引用编号
            annotated.append(el)

        return annotated

    async def _extract_forms(self, page: Page) -> list[FormGroup]:
        """检测并聚合页面中的表单元素。"""
        try:
            form_data = await page.evaluate(self._JS_EXTRACT_FORMS)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("表单提取失败: %s", e)
            return []

        forms: list[FormGroup] = []
        for fd in form_data:
            elements: list[AnnotatedElement] = []
            submit_btn: AnnotatedElement | None = None
            for raw in fd.get("elements", []):
                el = self.inferrer.infer(raw)
                elements.append(el)
                if el.semantic_type == SemanticType.SUBMIT_BTN:
                    submit_btn = el

            # 如果元素中没有找到提交按钮，尝试在表单内指定
            submit_raw = fd.get("submit_button")
            if submit_btn is None and submit_raw:
                submit_btn = self.inferrer.infer(submit_raw)

            forms.append(FormGroup(elements=elements, submit_button=submit_btn))

        return forms

    async def _detect_pagination(self, page: Page) -> PaginationInfo | None:
        """检测页面分页信息。"""
        try:
            pag_data = await page.evaluate(self._JS_EXTRACT_PAGINATION)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("分页检测失败: %s", e)
            return None

        if not pag_data:
            return None

        page_elements = [self.inferrer.infer(raw) for raw in pag_data.get("pages", [])]

        next_raw = pag_data.get("next")
        next_element = self.inferrer.infer(next_raw) if next_raw else None

        prev_raw = pag_data.get("prev")
        prev_element = self.inferrer.infer(prev_raw) if prev_raw else None

        return PaginationInfo(
            current=pag_data.get("current", 1),
            total=pag_data.get("total"),
            next_element=next_element,
            prev_element=prev_element,
            page_elements=page_elements,
        )

    async def _detect_dialogs(self, page: Page) -> list[AnnotatedElement]:
        """检测页面中的弹窗/模态框。"""
        dialogs: list[AnnotatedElement] = []
        try:
            dialog_elements = await page.evaluate(self._JS_EXTRACT_DIALOGS)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("弹窗检测失败: %s", e)
            return dialogs

        for raw in dialog_elements:
            dialogs.append(self.inferrer.infer(raw))

        return dialogs

    async def _detect_nav(self, page: Page) -> list[AnnotatedElement]:
        """检测导航元素。"""
        nav_items: list[AnnotatedElement] = []
        try:
            nav_elements = await page.evaluate(self._JS_EXTRACT_NAV)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("导航检测失败: %s", e)
            return nav_items

        for raw in nav_elements:
            nav_items.append(self.inferrer.infer(raw))

        return nav_items

    async def _classify_page(self, page: Page) -> str:
        """对页面进行快速分类（轻量级，不需要完整快照）。"""
        try:
            body_text = await page.evaluate("document.body?.innerText?.substring(0, 2000) || ''")
        except Exception:  # pylint: disable=broad-exception-caught
            return PageType.UNKNOWN

        body_lower = body_text.lower()

        # 快速启发式
        if any(kw in body_lower for kw in ("验证码", "captcha", "slider verification")):
            return PageType.CAPTCHA
        if any(kw in body_lower for kw in ("登录", "sign in", "log in")):
            return PageType.LOGIN
        if any(kw in body_lower for kw in ("404", "not found", "500", "error")):
            return PageType.ERROR

        return PageType.UNKNOWN

    async def _get_load_state(self, page: Page) -> str:
        """获取当前页面加载状态。"""
        try:
            ready_state = await page.evaluate("document.readyState")
            return str(ready_state)
        except Exception:  # pylint: disable=broad-exception-caught
            return "unknown"

    @staticmethod
    def _detect_block_text(content: str) -> bool:
        """检测内容中是否包含反爬/封禁相关文本。"""
        if not content:
            return False
        content_lower = content.lower()
        block_keywords = [
            "access denied", "访问被拒绝", "您的访问被拒绝",
            "too many requests", "请求过于频繁",
            "ip blocked", "ip 被封", "您的ip",
            "verify you are human", "请证明你是人类",
            "suspicious activity", "异常活动",
        ]
        return any(kw in content_lower for kw in block_keywords)

    # ── JS 提取脚本 ──

    _JS_EXTRACT_ELEMENTS = """
    () => {
        const SELECTORS = [
            'a[href]', 'button', 'input:not([type="hidden"])', 'select', 'textarea',
            '[role="button"]', '[role="link"]', '[role="tab"]', '[role="menuitem"]',
            '[onclick]', '[tabindex]:not([tabindex="-1"])',
            'li[class]', 'div[class*="card"]', 'article',
            'nav a', 'header a', 'footer a',
            '[class*="btn"]:not(script):not(style)', '[class*="button"]:not(script):not(style)',
        ];

        const elements = document.querySelectorAll(SELECTORS.join(','));
        const results = [];
        const seen = new Set();

        elements.forEach((el) => {
            // 跳过不可见、不可交互或重复元素
            if (!el.checkVisibility || !el.checkVisibility({ visibilityProperty: true, contentVisibilityAuto: true })) {
                return;
            }
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return;

            const selector = generateSelector(el);
            if (seen.has(selector)) return;
            seen.add(selector);

            const text = (el.textContent || '').trim().substring(0, 200).replace(/\\s+/g, ' ');
            const role = el.getAttribute('role') || el.getAttribute('aria-role') || '';
            const inputType = el.tagName === 'INPUT' ? (el.type || 'text') : '';
            const options = el.tagName === 'SELECT'
                ? Array.from(el.options).map(o => o.textContent || o.value)
                : [];

            results.push({
                tag: el.tagName.toLowerCase(),
                role: role,
                text: text,
                placeholder: el.placeholder || el.getAttribute('aria-label') || '',
                aria_label: el.getAttribute('aria-label') || '',
                selector: selector,
                is_visible: true,
                is_interactable: el.isConnected && !el.disabled && !el.hasAttribute('aria-disabled'),
                bounding_box: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
                input_type: inputType,
                options: options,
                class_list: Array.from(el.classList || []).join(' '),
            });
        });

        function generateSelector(el) {
            // 生成一个稳定的 CSS 选择器
            if (el.id) return '#' + CSS.escape(el.id);
            const path = [];
            let current = el;
            while (current && current !== document.body && current !== document.documentElement) {
                let segment = current.tagName.toLowerCase();
                if (current.id) {
                    path.unshift('#' + CSS.escape(current.id));
                    break;
                }
                const parent = current.parentElement;
                if (parent) {
                    const siblings = Array.from(parent.children).filter(
                        c => c.tagName === current.tagName
                    );
                    if (siblings.length > 1) {
                        const idx = siblings.indexOf(current) + 1;
                        segment += ':nth-of-type(' + idx + ')';
                    }
                }
                path.unshift(segment);
                current = current.parentElement;
            }
            return path.join(' > ');
        }

        return results;
    }
    """

    _JS_EXTRACT_FORMS = """
    () => {
        const forms = document.querySelectorAll('form');
        const result = [];
        forms.forEach((form) => {
            const inputs = form.querySelectorAll('input:not([type="hidden"]), select, textarea, button');
            const elements = [];
            let submitButton = null;
            inputs.forEach((el) => {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return;
                const item = {
                    tag: el.tagName.toLowerCase(),
                    role: el.getAttribute('role') || '',
                    text: el.tagName === 'BUTTON'
                        ? (el.textContent || '').trim().substring(0, 200)
                        : (el.previousElementSibling?.textContent || el.closest('label')?.textContent || '').trim().substring(0, 200),
                    placeholder: el.placeholder || '',
                    aria_label: el.getAttribute('aria-label') || '',
                    selector: el.id ? '#' + CSS.escape(el.id) : el.tagName.toLowerCase() + '[name="' + (el.name || '') + '"]',
                    is_visible: true,
                    is_interactable: !el.disabled,
                    input_type: el.tagName === 'INPUT' ? (el.type || 'text') : '',
                    options: el.tagName === 'SELECT' ? Array.from(el.options).map(o => o.text) : [],
                };
                if (el.type === 'submit' || el.tagName === 'BUTTON') {
                    submitButton = item;
                }
                elements.push(item);
            });
            result.push({ elements: elements, submit_button: submitButton });
        });
        return result;
    }
    """

    _JS_EXTRACT_PAGINATION = """
    () => {
        // 查找常见分页容器
        const selectors = [
            '[class*="pagination"]', '[class*="pager"]', '[class*="page-nav"]',
            '[aria-label*="page"]', '[aria-label*="分页"]',
            'nav[aria-label*="pagination"]',
        ];
        let container = null;
        for (const sel of selectors) {
            container = document.querySelector(sel);
            if (container) break;
        }
        if (!container) return null;

        const links = container.querySelectorAll('a, button, span[class*="page"]');
        const result = { current: 1, total: null, next: null, prev: null, pages: [] };

        links.forEach((el) => {
            const text = (el.textContent || '').trim();
            const isNext = /next|下一页|»|>/i.test(text);
            const isPrev = /prev|上一页|«|</i.test(text);
            const num = parseInt(text, 10);

            const item = {
                tag: el.tagName.toLowerCase(),
                role: el.getAttribute('role') || '',
                text: text,
                placeholder: '',
                aria_label: el.getAttribute('aria-label') || '',
                selector: el.tagName.toLowerCase() + ':has-text("' + text + '")',
                is_visible: true,
                is_interactable: !el.disabled,
                input_type: '',
                options: [],
            };

            if (isNext) result.next = item;
            else if (isPrev) result.prev = item;
            else if (!isNaN(num)) {
                result.pages.push(item);
                if (el.classList.contains('active') || el.classList.contains('current') ||
                    el.getAttribute('aria-current') === 'page') {
                    result.current = num;
                }
                // 估算最大页码
                if (result.total === null || num > (result.total || 0)) {
                    result.total = num;
                }
            }
        });

        return result;
    }
    """

    _JS_EXTRACT_DIALOGS = """
    () => {
        const selectors = [
            '[role="dialog"]', '[role="alertdialog"]', '.modal', '.dialog',
            '[class*="modal"]', '[class*="dialog"]', '[class*="popup"]',
            '[class*="overlay"]', '[aria-modal="true"]',
        ];
        const results = [];
        const seen = new Set();

        selectors.forEach((sel) => {
            document.querySelectorAll(sel).forEach((el) => {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return;
                const id = el.id || ('dialog-' + results.length);
                if (seen.has(id)) return;
                seen.add(id);

                results.push({
                    tag: el.tagName.toLowerCase(),
                    role: el.getAttribute('role') || 'dialog',
                    text: (el.textContent || '').trim().substring(0, 300).replace(/\\s+/g, ' '),
                    placeholder: '',
                    aria_label: el.getAttribute('aria-label') || '',
                    selector: el.id ? '#' + CSS.escape(el.id) : el.tagName.toLowerCase() + '[role="' + (el.getAttribute('role') || 'dialog') + '"]',
                    is_visible: true,
                    is_interactable: true,
                    input_type: '',
                    options: [],
                });
            });
        });

        return results;
    }
    """

    _JS_EXTRACT_NAV = """
    () => {
        const selectors = [
            'nav a', 'nav button',
            '[role="navigation"] a', '[role="navigation"] button',
            'header a', 'header button',
            '.navbar a', '.navbar button',
            '[class*="nav"] a:not([class*="footer"])',
            '[class*="menu"] a',
            '.breadcrumb a', '.breadcrumb span',
            '[role="tab"]',
        ];
        const results = [];
        const seen = new Set();

        document.querySelectorAll(selectors.join(',')).forEach((el) => {
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return;
            const text = (el.textContent || '').trim().substring(0, 200).replace(/\\s+/g, ' ');
            if (seen.has(text)) return;
            seen.add(text);

            results.push({
                tag: el.tagName.toLowerCase(),
                role: el.getAttribute('role') || '',
                text: text,
                placeholder: '',
                aria_label: el.getAttribute('aria-label') || '',
                selector: el.tagName.toLowerCase() + ':has-text("' + text.replace(/"/g, '\\\\"') + '")',
                is_visible: true,
                is_interactable: !el.disabled,
                input_type: '',
                options: [],
            });
        });

        return results;
    }
    """


# =============================================================================
# 辅助函数
# =============================================================================

async def asyncio_gather_optional(*coros) -> list[Any]:
    """并发执行多个协程，忽略单个失败并返回 None 占位。"""
    import asyncio  # pylint: disable=import-outside-toplevel
    results: list[Any] = []
    wrapped = [_or_none(c) for c in coros]
    gathered = await asyncio.gather(*wrapped)
    results = list(gathered)
    return results


async def _or_none(coro):
    """包装协程，异常时返回 None。"""
    try:
        return await coro
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("子任务失败: %s", e)
        return None
