# 浏览器 Agent 重构设计文档

> 日期: 2026-06-06
> 版本: v1.1
> 状态: 设计中

---

## 1. 项目愿景

构建一个**像人一样浏览网页的 Agent**——能看懂页面、能点击交互、能提取信息，比人快但不暴露机器人身份。

### 核心原则

| 原则 | 说明 |
|------|------|
| CLI 为主 | 用户日常操作走 CLI 命令，零 Token 消耗；MCP 为辅，仅 AI 编程助手需要时启动 |
| 像人浏览 | 流程骨架保证可靠性，语义理解提供灵活性 |
| 全速优先 | 能快就快，检测到反爬风险才降速 |
| 精确输出 | CLI 直接输出结构化结果，不经过 LLM 翻译 |
| 单一入口 | 所有功能统一到 `agent` 命令 |

---

## 2. 架构总览

### 2.1 感知-决策-执行循环

```
┌──────────────────────────────────────────────────────────┐
│                    BrowsingAgent                          │
│                  （统一 Agent，替代旧 BrowserAgent）        │
│                                                           │
│  ┌───────────┐    ┌───────────┐    ┌───────────────┐     │
│  │  感知层   │───→│  决策层   │───→│    执行层     │     │
│  │ Perceive  │    │  Decide   │    │   Execute     │     │
│  └───────────┘    └───────────┘    └───────────────┘     │
│       ↑                │                  │               │
│       │                ↓                  ↓               │
│  ┌───────────┐    ┌───────────┐    ┌───────────────┐     │
│  │ DOM 语义  │    │ 流程骨架  │    │ 行为模拟器   │     │
│  │ 解析器    │    │ 语义推理  │    │ 速度控制器   │     │
│  │ 元素标注  │    │ 动作规划  │    │ 反爬检测器   │     │
│  │ 可见性    │    │ 循环控制  │    │ 指纹管理器   │     │
│  │ 可交互性  │    │ 错误恢复  │    │ 健康监控器   │     │
│  └───────────┘    └───────────┘    └───────────────┘     │
│                                                           │
│  ┌───────────────────────────────────────────────────┐   │
│  │                  共享 Core 层                      │   │
│  │  BrowserController · Session · Config · Logging   │   │
│  └───────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘

入口层:
  ┌─────────┐    ┌─────────┐
  │  CLI    │    │  MCP    │
  │ (主入口)│    │ (辅入口)│
  └────┬────┘    └────┬────┘
       │              │
       └──────┬───────┘
              ↓
        BrowsingAgent
```

### 2.2 核心循环流程

```
用户指令 (CLI/MCP)
    │
    ↓
┌─────────────┐
│  感知页面   │  DOM 快照 → 语义标注 → 结构化页面描述
└──────┬──────┘
       │
       ↓
┌─────────────┐
│  决策下一步  │  匹配流程骨架 → 语义推理 → 输出动作
└──────┬──────┘
       │
       ↓
┌─────────────┐
│  执行动作   │  行为模拟 → 反爬检测 → 速度控制
└──────┬──────┘
       │
       ↓
┌─────────────┐
│  循环控制   │  检查终止条件 / 重复检测 / 进度评估
└──────┬──────┘
       │
       ↓
  继续循环？──否──→ 输出结果
       │
      是
       ↓
  回到感知页面
```

### 2.3 BrowserController 拆分方案

现有 `BrowserController` 有 1446 行，职责过重。按"彻底拆分"策略，将其拆为 4 个独立模块：

```
BrowserController (拆分前, 1446行)
    │
    ├──→ BrowserController (拆分后, ~500行)
    │    只保留核心浏览器操作：
    │    start/stop, navigate_to, click_selector, fill_input,
    │    scroll_page, press_key, go_back, take_screenshot,
    │    get_page_text/html/title/url, execute_js,
    │    query_element, wait_for_element, new_page, get_pages
    │
    ├──→ HealthMonitor (~300行)
    │    页面健康诊断 + 自动修复：
    │    detect_page_health, diagnose_page_issue, auto_repair,
    │    _repair_wait_render, _repair_reinject_stealth,
    │    _repair_hard_reload, _repair_wait_js_ready,
    │    _repair_renavigate, _repair_wait_and_retry,
    │    _repair_wait_for_captcha_solve, _repair_break_redirect
    │
    ├──→ Session (~200行, 合并现有 session.py)
    │    Cookie/Storage/登录态管理：
    │    save_cookies, load_cookies, save_storage_state,
    │    load_storage_state, auto_detect_login,
    │    filter_expired_cookies, refresh_short_lived_cookies
    │
    └──→ LogCollector (~100行)
         控制台/网络日志收集：
         get_console_logs, get_network_logs,
         get_pending_dialog, handle_dialog,
         get_accessibility_snapshot
```

**拆分原则**：
- BrowserController 只做"操控浏览器"这一件事
- HealthMonitor 由 ExecutionEngine 在执行失败时调用
- Session 由 BrowsingAgent 在需要时调用
- LogCollector 由感知层和反爬检测器调用

### 2.4 BrowsingAgent 替代 BrowserAgent

现有 `BrowserAgent`（agent/core/agent.py，457 行）是 BrowserController 的薄封装，专门给 MCP 用。新架构中由 `BrowsingAgent` 统一替代：

```
旧架构:
  MCP handlers → BrowserAgent (薄封装) → BrowserController
  CLI          → 直接调用 BrowserController

新架构:
  MCP handlers → BrowsingAgent → BrowserController (精简版)
  CLI          → BrowsingAgent → BrowserController (精简版)
```

**BrowsingAgent 的职责**：
- 编排"感知→决策→执行"循环
- 管理 @ref 元素引用（从 PageSnapshot 查找）
- 维护循环状态（步数、历史动作、进度评估）
- 对外提供统一 API（CLI 和 MCP 共用）

---

## 3. 感知层设计

### 3.1 设计原则

- **DOM 优先**：纯 DOM 解析完成 90% 的浏览任务，零 Token 消耗
- **视觉可选**：截图+OCR 仅在 DOM 无法覆盖时启用（验证码、Canvas 内容等）
- **模型无关**：无论 LLM 是否有视觉能力，核心浏览流程都能跑

### 3.2 DOM 语义解析器

```python
class PagePerceiver:
    """页面感知器 — 从 DOM 中提取结构化语义信息"""

    async def perceive(self, page: Page) -> PageSnapshot:
        """感知页面，返回结构化快照"""
        return PageSnapshot(
            url=page.url,
            title=await page.title(),
            elements=await self._annotate_elements(page),
            forms=await self._extract_forms(page),
            pagination=await self._detect_pagination(page),
            dialogs=await self._detect_dialogs(page),
            navigation=await self._detect_nav(page),
            content_type=self._classify_page(page),
        )
```

### 3.3 元素标注系统

对页面中每个可见、可交互元素进行语义标注：

```python
@dataclass
class AnnotatedElement:
    """标注后的页面元素"""
    # 基础属性
    tag: str                    # 标签名: button, a, input, select...
    role: str | None            # ARIA role: button, link, search, navigation...
    text: str                   # 可见文本 / aria-label / title / placeholder
    selector: str               # CSS 选择器（唯一标识）

    # 语义标注
    semantic_type: str          # 语义类型: search_input, login_btn, next_page,
                                #   close_dialog, submit_btn, nav_link...
    confidence: float           # 标注置信度 0-1

    # 交互属性
    is_visible: bool            # viewport 内且非遮挡
    is_interactable: bool       # enabled + 可点击/可输入
    bounding_box: dict | None   # {x, y, width, height}

    # 表单特有
    input_type: str | None      # text, password, email, number...
    options: list[str] | None   # select 的选项列表

    # @ref 引用编号（MCP 兼容）
    ref: int | None = None      # 元素编号，用于 @ref 快捷引用
```

### 3.4 语义类型分类

```python
class SemanticType:
    """元素语义类型枚举"""

    # 导航类
    NAV_LINK = "nav_link"           # 导航链接
    BREADCRUMB = "breadcrumb"       # 面包屑
    TAB = "tab"                     # 标签页切换

    # 搜索类
    SEARCH_INPUT = "search_input"   # 搜索输入框
    SEARCH_BTN = "search_btn"       # 搜索按钮
    FILTER = "filter"               # 筛选器
    SORT = "sort"                   # 排序控件

    # 分页类
    NEXT_PAGE = "next_page"         # 下一页
    PREV_PAGE = "prev_page"         # 上一页
    PAGE_NUMBER = "page_number"     # 页码

    # 表单类
    FORM_INPUT = "form_input"       # 通用输入框
    SUBMIT_BTN = "submit_btn"       # 提交按钮
    SELECT = "select"               # 下拉选择
    CHECKBOX = "checkbox"           # 复选框
    RADIO = "radio"                 # 单选框

    # 对话框类
    CLOSE_DIALOG = "close_dialog"   # 关闭弹窗
    CONFIRM_BTN = "confirm_btn"     # 确认按钮
    CANCEL_BTN = "cancel_btn"       # 取消按钮

    # 列表类
    LIST_ITEM = "list_item"         # 列表项
    CARD = "card"                   # 卡片
    DETAIL_LINK = "detail_link"     # 详情链接

    # 登录类
    LOGIN_BTN = "login_btn"         # 登录按钮
    USERNAME_INPUT = "username_input"
    PASSWORD_INPUT = "password_input"

    # 反爬类
    CAPTCHA = "captcha"             # 验证码
    SLIDER = "slider"               # 滑块验证
    AGREE_BTN = "agree_btn"         # 同意/接受按钮（Cookie 横幅等）
```

### 3.5 语义推断规则

元素标注采用**规则优先 + 启发式回退**的策略，不依赖 LLM：

```python
class SemanticInferrer:
    """元素语义推断器"""

    # 规则优先：精确匹配
    RULES = [
        # (匹配条件, 语义类型, 置信度)
        (lambda el: el.tag == "input" and el.input_type == "search", SemanticType.SEARCH_INPUT, 0.95),
        (lambda el: el.role == "search", SemanticType.SEARCH_INPUT, 0.95),
        (lambda el: "搜索" in el.text or "search" in el.text.lower(), SemanticType.SEARCH_BTN, 0.9),
        (lambda el: "下一页" in el.text or "next" in el.text.lower(), SemanticType.NEXT_PAGE, 0.9),
        (lambda el: "登录" in el.text or "login" in el.text.lower(), SemanticType.LOGIN_BTN, 0.9),
        (lambda el: "关闭" in el.text and el.role == "button", SemanticType.CLOSE_DIALOG, 0.85),
        # ... 更多规则
    ]

    # 启发式回退：基于上下文推断
    HEURISTICS = [
        # 输入框在 form 内 → 表单输入
        # 按钮在 dialog 内 → 对话框按钮
        # 链接在 nav 内 → 导航链接
        # 带箭头图标的链接 → 分页
    ]

    def infer(self, element: AnnotatedElement, context: PageContext) -> AnnotatedElement:
        """推断元素语义类型"""
        # 1. 精确规则匹配
        for rule, sem_type, confidence in self.RULES:
            if rule(element):
                element.semantic_type = sem_type
                element.confidence = confidence
                return element

        # 2. 启发式推断
        element.semantic_type = self._heuristic_infer(element, context)
        element.confidence = 0.6  # 启发式置信度较低

        return element
```

### 3.6 页面类型识别

```python
class PageType:
    """页面类型枚举"""
    SEARCH_RESULTS = "search_results"   # 搜索结果页
    DETAIL = "detail"                   # 详情页
    LIST = "list"                       # 列表页
    FORM = "form"                       # 表单页
    LOGIN = "login"                     # 登录页
    CAPTCHA = "captcha"                 # 验证码页
    HOME = "home"                       # 首页
    ERROR = "error"                     # 错误页
    UNKNOWN = "unknown"                 # 未知类型


class PageClassifier:
    """页面类型分类器 — 基于 URL + DOM 特征判断"""

    def classify(self, snapshot: PageSnapshot) -> str:
        # URL 模式匹配（最快）
        if "/login" in snapshot.url:
            return PageType.LOGIN
        if "/search" in snapshot.url or "/job" in snapshot.url:
            return PageType.SEARCH_RESULTS

        # DOM 特征匹配
        if snapshot.pagination and snapshot.elements_by_type(SemanticType.LIST_ITEM):
            return PageType.LIST
        if snapshot.forms and not snapshot.pagination:
            return PageType.FORM

        return PageType.UNKNOWN
```

### 3.7 PageSnapshot 数据结构

```python
@dataclass
class PageSnapshot:
    """页面结构化快照 — 感知层的输出，决策层的输入"""
    url: str
    title: str
    page_type: str                       # PageType 枚举值

    # 标注后的元素列表（按可见性+可交互性过滤）
    elements: list[AnnotatedElement]

    # 语义分组
    forms: list[FormGroup]               # 表单组
    pagination: PaginationInfo | None    # 分页信息
    dialogs: list[AnnotatedElement]      # 弹窗/对话框
    navigation: list[AnnotatedElement]   # 导航元素

    # 页面内容摘要
    main_content: str                    # 主要文本内容（前 2000 字）
    content_type: str                    # 结构化/非结构化/混合

    # 元数据
    timestamp: float
    load_state: str                      # load/domcontentloaded/networkidle

    # 反爬检测相关（从 LogCollector 获取）
    has_captcha: bool = False            # 是否检测到验证码
    has_block_text: bool = False         # 是否检测到封禁文本
    redirect_count: int = 0              # 重定向次数

    def elements_by_type(self, sem_type: str) -> list[AnnotatedElement]:
        """按语义类型筛选元素"""
        return [e for e in self.elements if e.semantic_type == sem_type]

    def find_element(self, sem_type: str, text: str | None = None) -> AnnotatedElement | None:
        """查找指定语义类型的元素，可按文本过滤"""
        candidates = self.elements_by_type(sem_type)
        if text:
            candidates = [e for e in candidates if text in e.text]
        return candidates[0] if candidates else None

    def find_by_ref(self, ref: int) -> AnnotatedElement | None:
        """通过 @ref 编号查找元素（MCP 兼容）"""
        for e in self.elements:
            if e.ref == ref:
                return e
        return None

    def to_text_description(self) -> str:
        """转换为文本描述（供 LLM 推理使用，零截图时）"""
        lines = [f"页面: {self.title} ({self.url})"]
        lines.append(f"类型: {self.page_type}")
        if self.elements:
            lines.append("\n可交互元素:")
            for i, el in enumerate(self.elements, 1):
                ref_tag = f"[@{el.ref}]" if el.ref is not None else ""
                lines.append(f"  [{i}] {el.semantic_type}{ref_tag}: {el.text} ({el.selector})")
        if self.pagination:
            lines.append(f"\n分页: 当前{self.pagination.current}, 共{self.pagination.total}")
        if self.dialogs:
            lines.append(f"\n弹窗: {len(self.dialogs)} 个")
        if self.has_captcha:
            lines.append("\n⚠ 检测到验证码")
        if self.has_block_text:
            lines.append("\n⚠ 检测到封禁文本")
        return "\n".join(lines)
```

### 3.8 @ref 元素引用系统

保留 @ref 作为 MCP 的快捷引用方式，但内部实现改为从 PageSnapshot 查找：

```python
class RefManager:
    """@ref 元素引用管理器 — MCP 兼容层"""

    def __init__(self):
        self._snapshot: PageSnapshot | None = None

    def update(self, snapshot: PageSnapshot):
        """更新快照，自动为可交互元素分配 ref 编号"""
        self._snapshot = snapshot
        for i, el in enumerate(snapshot.elements, 1):
            if el.is_interactable:
                el.ref = i

    def resolve(self, target: str) -> AnnotatedElement | None:
        """解析目标：支持 @ref 编号、语义类型、CSS 选择器"""
        if not self._snapshot:
            return None

        # 1. @ref 编号引用（如 "@3"）
        if target.startswith("@"):
            ref = int(target[1:])
            return self._snapshot.find_by_ref(ref)

        # 2. 语义类型匹配（如 "search_input"）
        element = self._snapshot.find_element(target)
        if element:
            return element

        # 3. CSS 选择器回退
        # 由 ExecutionEngine._resolve_target 处理
        return None
```

### 3.9 视觉增强（可选）

当 LLM 具备视觉能力时，可启用视觉增强：

```python
class VisualEnhancer:
    """视觉增强器 — 可选模块，需要多模态 LLM"""

    def __init__(self, vision_model: str | None = None):
        self.vision_model = vision_model  # None 表示不启用

    async def enhance(self, snapshot: PageSnapshot, screenshot: bytes) -> PageSnapshot:
        """用视觉信息增强 DOM 快照"""
        if not self.vision_model:
            return snapshot  # 无视觉能力，直接返回

        # 1. 验证码识别
        captcha_elements = snapshot.elements_by_type(SemanticType.CAPTCHA)
        if captcha_elements:
            for el in captcha_elements:
                el.captcha_text = await self._ocr_captcha(screenshot, el)

        # 2. 布局理解（DOM 无法判断视觉重叠时）
        # 3. Canvas/图片内容提取

        return snapshot
```

---

## 4. 决策层设计

### 4.1 三级决策架构

```
决策层
├── Level 1: 流程骨架匹配（零 Token，毫秒级）
│   └── 已知网站 → 预定义步骤 → 直接执行
│
├── Level 2: DOM 语义推理（少量 Token，秒级）
│   └── 未知网站 → DOM 结构描述 → LLM 文本推理下一步
│
└── Level 3: 视觉推理（需要多模态 LLM，秒级）
    └── 截图 + DOM → 多模态 LLM 推理
```

**决策优先级**：Level 1 > Level 2 > Level 3，高优先级成功则不调用低优先级。

### 4.2 动作类型

```python
class ActionType:
    """Agent 可执行的动作类型"""
    CLICK = "click"               # 点击元素
    TYPE = "type"                 # 输入文本
    SCROLL = "scroll"             # 滚动页面
    NAVIGATE = "navigate"         # 导航到 URL
    WAIT = "wait"                 # 等待（元素/导航/时间）
    EXTRACT = "extract"           # 提取数据
    SCREENSHOT = "screenshot"     # 截图
    HOVER = "hover"               # 悬停
    SELECT = "select"             # 下拉选择
    PRESS_KEY = "press_key"       # 按键
    DIALOG = "dialog"             # 处理对话框
    GO_BACK = "go_back"           # 返回上一页
    SWITCH_TAB = "switch_tab"     # 切换标签页
    DONE = "done"                 # 任务完成
    NOOP = "noop"                 # 无操作（等待/思考）


@dataclass
class Action:
    """Agent 动作"""
    type: str                              # ActionType 枚举值
    target: str | None = None              # 目标元素选择器 / @ref / 语义类型
    value: str | None = None               # 输入值 / URL / 等待时间
    params: dict | None = None             # 额外参数
    reason: str = ""                       # 决策原因（用于日志）
    confidence: float = 1.0                # 决策置信度
```

### 4.3 流程骨架

流程骨架是预定义的浏览步骤序列，用于已知网站：

```python
@dataclass
class FlowStep:
    """流程步骤"""
    action: str                    # ActionType
    target: str                    # 选择器 / 语义类型 / @ref
    value: str | None = None       # 输入值
    wait_after: float = 0.5        # 执行后等待时间（秒）
    fallback: str | None = None    # 失败时的回退步骤描述
    condition: str | None = None   # 执行条件 / 循环条件
    # condition 语义：
    #   "page_type == search_results" → 仅在搜索结果页执行
    #   "has_next_page" → 有下一页时执行（循环语义：条件为真则重复）
    #   None → 无条件执行


@dataclass
class FlowSkeleton:
    """流程骨架"""
    name: str
    description: str
    url_pattern: str               # 匹配的 URL 模式
    page_type: str                 # 匹配的页面类型
    steps: list[FlowStep]
    on_error: str = "ask_user"     # 错误策略: stop/retry/skip/ask_user
```

**示例：BOSS直聘搜索流程骨架**

```python
zhipin_search_flow = FlowSkeleton(
    name="zhipin_search",
    description="BOSS直聘职位搜索",
    url_pattern="zhipin.com",
    page_type=PageType.HOME,
    steps=[
        FlowStep(action="wait", target="domcontentloaded", wait_after=1.0),
        FlowStep(action="click", target=SemanticType.SEARCH_INPUT, wait_after=0.3),
        FlowStep(action="type", target=SemanticType.SEARCH_INPUT, value="{{keyword}}", wait_after=0.5),
        FlowStep(action="click", target=SemanticType.SEARCH_BTN, wait_after=2.0),
        FlowStep(action="wait", target="networkidle", wait_after=1.0),
        # 提取当前页数据（条件：在搜索结果页）
        FlowStep(action="extract", target=".job-list li", condition="page_type == search_results"),
        # 翻页循环（条件：有下一页时重复执行 click + extract）
        FlowStep(action="click", target=SemanticType.NEXT_PAGE, wait_after=1.5,
                 condition="has_next_page", fallback="stop"),
        FlowStep(action="extract", target=".job-list li",
                 condition="page_type == search_results"),
    ],
    on_error="ask_user",
)
```

**condition 循环语义**：当 FlowStep 的 condition 为真时，该步骤会重复执行。决策引擎在每次循环前重新评估 condition。condition 为假时跳过该步骤，继续执行后续步骤。

### 4.4 流程骨架注册表

```python
class FlowRegistry:
    """流程骨架注册表"""

    def __init__(self):
        self._flows: list[FlowSkeleton] = []
        self._load_builtin_flows()

    def _load_builtin_flows(self):
        """加载内置流程骨架"""
        self.register(zhipin_search_flow)
        self.register(zhipin_detail_flow)
        self.register(qcc_search_flow)
        # ...

    def register(self, flow: FlowSkeleton):
        self._flows.append(flow)

    def match(self, url: str, page_type: str) -> FlowSkeleton | None:
        """根据 URL 和页面类型匹配流程骨架"""
        for flow in self._flows:
            if flow.url_pattern in url and flow.page_type == page_type:
                return flow
        return None
```

### 4.5 语义推理器

当流程骨架无法匹配时，使用 DOM 语义描述 + LLM 推理：

```python
# LLM 输出的 JSON Schema
ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["click", "type", "scroll", "navigate", "wait",
                     "extract", "hover", "select", "press_key",
                     "dialog", "go_back", "switch_tab", "done"]
        },
        "target": {"type": ["string", "null"]},
        "value": {"type": ["string", "null"]},
        "reason": {"type": "string"},
    },
    "required": ["action"],
}


class SemanticDecider:
    """语义推理决策器 — 基于 DOM 文本描述 + LLM"""

    def __init__(self, llm_client=None):
        self.llm = llm_client
        self._action_history: list[Action] = []  # 最近 5 步历史

    async def decide(self, snapshot: PageSnapshot, task: str) -> Action:
        """根据页面快照和任务目标，推理下一步动作"""
        if not self.llm:
            return Action(type=ActionType.NOOP, reason="无 LLM 可用，无法推理")

        # 构造提示词（纯文本，不消耗视觉 Token）
        page_desc = snapshot.to_text_description()
        history_desc = self._format_history()

        prompt = f"""你是一个浏览器自动化 Agent。根据当前页面状态和任务目标，决定下一步操作。

任务: {task}

当前页面:
{page_desc}

最近操作历史:
{history_desc}

请输出下一步操作的 JSON，严格遵循以下格式:
{json.dumps(ACTION_SCHEMA, ensure_ascii=False, indent=2)}

规则:
1. 优先使用语义类型匹配（如 search_input, next_page）
2. 可用 @ref 编号引用元素（如 @3）
3. 只操作可见且可交互的元素
4. 如果任务已完成，输出 {{"action": "done"}}
5. 如果遇到验证码，输出 {{"action": "wait", "value": "5"}}
6. 不要输出上面未列出的 action 类型"""

        response = await self.llm.chat(prompt)
        action = self._parse_action(response)

        # 记录历史
        self._action_history.append(action)
        if len(self._action_history) > 5:
            self._action_history.pop(0)

        return action

    def _format_history(self) -> str:
        """格式化最近操作历史"""
        if not self._action_history:
            return "（无历史操作）"
        lines = []
        for i, a in enumerate(self._action_history, 1):
            lines.append(f"  {i}. {a.type}: {a.target or ''} {a.value or ''} — {a.reason}")
        return "\n".join(lines)

    def _parse_action(self, response: str) -> Action:
        """解析 LLM 输出为 Action，解析失败返回 NOOP"""
        try:
            data = json.loads(response)
            return Action(
                type=data.get("action", "noop"),
                target=data.get("target"),
                value=data.get("value"),
                reason=data.get("reason", ""),
            )
        except (json.JSONDecodeError, KeyError):
            return Action(type=ActionType.NOOP, reason=f"LLM 输出解析失败: {response[:100]}")
```

### 4.6 循环控制（智能护栏）

```python
@dataclass
class LoopState:
    """循环状态 — 跟踪 Agent 的执行进度"""
    step_count: int = 0                # 已执行步数
    max_steps: int = 50                # 最大步数
    start_time: float = 0.0            # 开始时间
    timeout_secs: float = 300.0        # 总超时（秒）

    # 重复检测
    recent_actions: list[str] = field(default_factory=list)  # 最近 10 步动作摘要
    repeat_threshold: int = 3          # 连续相同动作阈值

    # 进度评估
    eval_interval: int = 5             # 每 N 步评估一次
    last_eval_step: int = 0            # 上次评估的步数
    no_progress_count: int = 0         # 连续无进展次数
    no_progress_threshold: int = 2     # 连续 N 次无进展则停止

    # 进度描述历史（供 LLM 评估）
    progress_snapshots: list[str] = field(default_factory=list)


class LoopController:
    """循环控制器 — 智能护栏，防止 Agent 停不下来"""

    def __init__(self, max_steps: int = 50, timeout_secs: float = 300.0):
        self.state = LoopState(
            max_steps=max_steps,
            timeout_secs=timeout_secs,
            start_time=time.time(),
        )

    def should_continue(self, action: Action) -> tuple[bool, str]:
        """判断是否应该继续循环，返回 (继续?, 原因)"""
        self.state.step_count += 1

        # 1. 最大步数检查
        if self.state.step_count >= self.state.max_steps:
            return False, f"达到最大步数 {self.state.max_steps}"

        # 2. 总超时检查
        elapsed = time.time() - self.state.start_time
        if elapsed >= self.state.timeout_secs:
            return False, f"超过总超时 {self.state.timeout_secs}s"

        # 3. 重复动作检测
        action_summary = f"{action.type}:{action.target}"
        self.state.recent_actions.append(action_summary)
        if len(self.state.recent_actions) > 10:
            self.state.recent_actions.pop(0)

        if len(self.state.recent_actions) >= self.state.repeat_threshold:
            last_n = self.state.recent_actions[-self.state.repeat_threshold:]
            if len(set(last_n)) == 1:
                return False, f"连续 {self.state.repeat_threshold} 次相同动作: {action_summary}"

        # 4. 任务完成
        if action.type == ActionType.DONE:
            return False, "任务完成"

        return True, ""

    async def evaluate_progress(self, snapshot: PageSnapshot, task: str,
                                 llm_client=None) -> tuple[bool, str]:
        """每 N 步评估一次任务进度（需要 LLM）"""
        steps_since_eval = self.state.step_count - self.state.last_eval_step
        if steps_since_eval < self.state.eval_interval:
            return True, ""

        self.state.last_eval_step = self.state.step_count

        if not llm_client:
            return True, ""  # 无 LLM，跳过进度评估

        # 记录当前快照摘要
        current_summary = f"URL={snapshot.url}, type={snapshot.page_type}, elements={len(snapshot.elements)}"
        self.state.progress_snapshots.append(current_summary)

        # 让 LLM 评估进度
        prompt = f"""任务: {task}
已执行 {self.state.step_count} 步。
之前的页面状态: {self.state.progress_snapshots[:-1][-3:] if len(self.state.progress_snapshots) > 1 else '无'}
当前页面状态: {current_summary}

任务是否有进展？回答 JSON: {{"progress": true/false, "reason": "原因"}}"""

        try:
            response = await llm_client.chat(prompt)
            data = json.loads(response)
            if not data.get("progress", True):
                self.state.no_progress_count += 1
                if self.state.no_progress_count >= self.state.no_progress_threshold:
                    return False, f"连续 {self.state.no_progress_count} 次评估无进展"
            else:
                self.state.no_progress_count = 0
        except (json.JSONDecodeError, KeyError):
            pass  # 评估失败，不中断

        return True, ""
```

### 4.7 错误恢复

```python
class ErrorRecovery:
    """错误恢复 — 执行失败时的回退策略"""

    @staticmethod
    async def handle_failure(action: Action, error: str, snapshot: PageSnapshot,
                              flow: FlowSkeleton | None = None) -> Action:
        """处理动作执行失败，返回下一步动作"""

        # 1. 如果在流程骨架中，查找 fallback
        if flow:
            current_step = None
            for step in flow.steps:
                if step.action == action.type:
                    current_step = step
                    break

            if current_step and current_step.fallback:
                # 执行 fallback 指定的动作
                if current_step.fallback == "stop":
                    return Action(type=ActionType.DONE, reason=f"流程回退: 停止 ({error})")
                elif current_step.fallback == "skip":
                    return Action(type=ActionType.NOOP, reason=f"流程回退: 跳过 ({error})")
                else:
                    # fallback 是一个动作描述，交给语义推理
                    return Action(type=ActionType.NOOP,
                                  reason=f"流程回退: {current_step.fallback} ({error})")

        # 2. 特定错误类型的自动处理
        if "Session 过期" in error or "登录页" in error:
            return Action(type=ActionType.NOOP, reason="Session 过期，需要重新登录")

        if "验证码" in error:
            return Action(type=ActionType.WAIT, value="5", reason="遇到验证码，等待 5 秒")

        if "元素未找到" in error:
            return Action(type=ActionType.NOOP, reason="元素未找到，可能页面已变化")

        # 3. 无自动恢复策略，暂停并报告给用户
        return Action(
            type=ActionType.NOOP,
            reason=f"执行失败，需要用户介入: {error}\n"
                   f"  失败动作: {action.type} → {action.target}\n"
                   f"  当前页面: {snapshot.url} ({snapshot.page_type})\n"
                   f"  可交互元素: {len(snapshot.elements)} 个"
        )
```

### 4.8 决策调度器

```python
class DecisionEngine:
    """决策调度器 — 统一调度三级决策 + 循环控制 + 错误恢复"""

    def __init__(self, flow_registry: FlowRegistry, semantic_decider: SemanticDecider,
                 loop_controller: LoopController):
        self.flow_registry = flow_registry
        self.semantic_decider = semantic_decider
        self.loop = loop_controller
        self._current_flow: FlowSkeleton | None = None
        self._flow_step_index: int = 0

    async def decide(self, snapshot: PageSnapshot, task: str) -> Action:
        """决策下一步动作"""

        # Level 1: 流程骨架匹配
        if self._current_flow is None:
            self._current_flow = self.flow_registry.match(snapshot.url, snapshot.page_type)

        if self._current_flow:
            action = self._execute_flow_step(snapshot)
            if action is not None:
                return action
            # 流程执行完毕或失败，清除当前流程
            self._current_flow = None

        # Level 2: DOM 语义推理
        action = await self.semantic_decider.decide(snapshot, task)
        if action.type != ActionType.NOOP:
            return action

        # Level 3: 视觉推理（如果可用）
        # 由 SemanticDecider 内部判断是否启用视觉

        # 无法决策，暂停并通知用户
        return Action(type=ActionType.NOOP, reason="无法决策，需要用户介入")

    async def run_loop(self, agent: "BrowsingAgent", task: str) -> dict:
        """运行完整的 感知-决策-执行 循环"""
        results = []

        while True:
            # 1. 感知
            snapshot = await agent.perceive()

            # 2. 决策
            action = await self.decide(snapshot, task)

            # 3. 循环控制检查
            should_continue, reason = self.loop.should_continue(action)
            if not should_continue:
                return {"ok": action.type == ActionType.DONE, "reason": reason, "results": results}

            # 4. 进度评估
            should_continue, reason = await self.loop.evaluate_progress(
                snapshot, task, self.semantic_decider.llm)
            if not should_continue:
                return {"ok": False, "reason": reason, "results": results}

            # 5. 执行
            result = await agent.execute(action)

            # 6. 错误恢复
            if not result.get("ok", True):
                recovery_action = await ErrorRecovery.handle_failure(
                    action, result.get("error", "未知错误"), snapshot, self._current_flow)
                if recovery_action.type == ActionType.NOOP:
                    # 需要用户介入，暂停循环
                    return {"ok": False, "reason": recovery_action.reason, "results": results}
                # 执行恢复动作
                action = recovery_action
                result = await agent.execute(action)

            results.append(result)
```

---

## 5. 执行层设计

### 5.1 三速模型

```
┌──────────────────────────────────────────────────────┐
│                   SpeedController                     │
│                                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ TURBO    │  │ NORMAL   │  │ STEALTH          │   │
│  │ 全速执行 │  │ 适度延迟 │  │ 拟人化行为       │   │
│  └──────────┘  └──────────┘  └──────────────────┘   │
│                                                       │
│  触发条件:        触发条件:        触发条件:           │
│  - 数据提取       - 页面导航       - 反爬检测触发     │
│  - DOM 解析       - 表单填写       - 政府网站         │
│  (无人类可观测)    (服务器可观测)   (主动检测环境)     │
└──────────────────────────────────────────────────────┘
```

**关键洞察**：不是所有操作都需要模拟人类。只有**服务器能观测到的行为**才需要拟人化。

**TURBO 模式的精细化规则**：TURBO 不是"所有操作都零延迟"，而是只对**服务器不可观测**的操作零延迟：

| 操作类型 | 服务器可观测？ | TURBO 延迟 | NORMAL 延迟 | STEALTH 延迟 |
|---------|-------------|-----------|------------|-------------|
| DOM 解析/数据提取 | 否 | 0ms | 0ms | 0ms |
| 页面导航 | 是（HTTP 请求） | 300-800ms | 300-800ms | 1000-3000ms |
| 点击按钮 | 是（点击事件） | 200-500ms | 200-500ms | 500-1500ms |
| 表单输入 | 是（input 事件） | 逐字 50-120ms | 逐字 50-120ms | 逐字 80-200ms |
| 滚动浏览 | 是（scroll 事件） | 300-600ms | 300-600ms | 500-1200ms |
| 翻页 | 是（导航+点击） | 500-1500ms | 500-1500ms | 2000-5000ms |
| 验证码页面 | 是（强检测） | — | — | 2-5s + 行为模拟 |
| 政府网站 | 是（合规要求） | — | — | 3-10s + 限流 |

**注意**：TURBO 和 NORMAL 的延迟实际上相同——因为导航、点击、输入都是服务器可观测的。TURBO 的真正优势在于**跳过行为模拟**（不做贝塞尔曲线鼠标移动、不做打错修正），直接用 Playwright 原生操作。

### 5.2 速度控制器

```python
class SpeedController:
    """速度控制器 — 根据操作类型和风险等级自动调速"""

    # 各档位的延迟参数（毫秒）
    # TURBO: 跳过行为模拟，但导航/点击仍有最小延迟
    # NORMAL: 标准拟人延迟
    # STEALTH: 强拟人延迟 + 行为模拟
    PROFILES = {
        "turbo": {
            "navigate": (300, 800),
            "click": (200, 500),
            "type_per_char": (50, 120),
            "scroll_segment": (300, 600),
            "page_turn": (500, 1500),
            "simulate_mouse": False,     # 不做贝塞尔曲线鼠标移动
            "simulate_typo": False,      # 不做打错修正
            "simulate_scroll": False,    # 不做分段滚动
        },
        "normal": {
            "navigate": (300, 800),
            "click": (200, 500),
            "type_per_char": (50, 120),
            "scroll_segment": (300, 600),
            "page_turn": (500, 1500),
            "simulate_mouse": True,
            "simulate_typo": True,
            "simulate_scroll": True,
        },
        "stealth": {
            "navigate": (1000, 3000),
            "click": (500, 1500),
            "type_per_char": (80, 200),
            "scroll_segment": (500, 1200),
            "page_turn": (2000, 5000),
            "simulate_mouse": True,
            "simulate_typo": True,
            "simulate_scroll": True,
        },
    }

    def __init__(self, default_speed: str = "normal"):
        self._current_speed = default_speed
        self._risk_level = 0  # 0-4，由反爬检测器更新

    @property
    def current_speed(self) -> str:
        """当前实际速度（可能被风险等级覆盖）"""
        if self._risk_level >= 2:
            return "stealth"
        return self._current_speed

    @property
    def should_simulate(self) -> dict:
        """当前速度档位的行为模拟开关"""
        profile = self.PROFILES[self.current_speed]
        return {
            "mouse": profile.get("simulate_mouse", True),
            "typo": profile.get("simulate_typo", True),
            "scroll": profile.get("simulate_scroll", True),
        }

    def get_delay(self, operation: str) -> float:
        """获取操作延迟（秒）"""
        profile = self.PROFILES[self.current_speed]
        value = profile.get(operation, 0)
        if isinstance(value, tuple):
            return random.uniform(*value) / 1000
        return value / 1000

    def set_risk_level(self, level: int):
        """由反爬检测器调用，更新风险等级"""
        self._risk_level = min(level, 4)
```

### 5.3 行为模拟引擎

```
BehaviorSimulator
├── 鼠标行为
│   ├── 自然轨迹移动（贝塞尔曲线，不是直线）
│   ├── 随机微抖动（人类手部自然震颤 ±2px）
│   ├── 点击前悬停（hover 100-300ms 再 click）
│   └── 滚轮滚动（分段 + 随机速度 + 偶尔回滚）
│
├── 键盘行为
│   ├── 逐字输入（每字 50-120ms，中文略慢）
│   ├── 偶尔退格修正（1-3% 概率打错再删）
│   ├── 输入间随机停顿（思考停顿 200-800ms）
│   └── Tab/Enter 切换（不用 JS 直接触发）
│
├── 浏览行为
│   ├── 页面加载后"扫视"（先滚动到底再回到关注区域）
│   ├── 随机鼠标游走（浏览时鼠标缓慢移动）
│   └── 停顿阅读（长内容区域停留 1-3s）
│
└── 时序行为
    ├── 操作间隔随机化（正态分布，不是均匀分布）
    ├── 会话节奏模拟（前快后慢，模拟疲劳）
    └── 偶尔"走神"（随机 2-5s 无操作）
```

```python
class BehaviorSimulator:
    """行为模拟引擎 — 模拟人类操作模式"""

    def __init__(self, speed_controller: SpeedController):
        self.speed = speed_controller

    async def human_click(self, page: Page, element: AnnotatedElement):
        """拟人化点击：贝塞尔曲线移动 + 悬停 + 点击"""
        if not self.speed.should_simulate["mouse"]:
            # TURBO 模式：直接点击
            await page.click(element.selector)
            return

        if not element.bounding_box:
            await page.click(element.selector)
            return

        target_x, target_y = self._random_point_in_box(element.bounding_box)
        current_x, current_y = await self._get_mouse_position(page)

        # 贝塞尔曲线移动
        await self._bezier_move(page, current_x, current_y, target_x, target_y)

        # 悬停
        await asyncio.sleep(random.uniform(0.1, 0.3))

        # 点击
        await page.click(element.selector)

    async def human_type(self, page: Page, selector: str, text: str):
        """拟人化输入：逐字 + 随机停顿 + 偶尔打错"""
        await page.click(selector)
        await asyncio.sleep(random.uniform(0.1, 0.2))

        simulate_typo = self.speed.should_simulate["typo"]

        for i, char in enumerate(text):
            # 1-3% 概率打错（仅 TURBO 以外的模式）
            if simulate_typo and random.random() < 0.02 and len(char.encode('utf-8')) == 1:
                wrong_char = self._nearby_key(char)
                await page.keyboard.type(wrong_char)
                await asyncio.sleep(random.uniform(0.05, 0.15))
                await page.keyboard.press("Backspace")
                await asyncio.sleep(random.uniform(0.05, 0.1))

            await page.keyboard.type(char)

            # 随机停顿
            delay = self.speed.get_delay("type_per_char")
            # 中文输入略慢
            if len(char.encode('utf-8')) > 1:
                delay *= 1.5
            # 偶尔思考停顿
            if random.random() < 0.05:
                delay += random.uniform(0.2, 0.8)
            await asyncio.sleep(delay)

    async def human_scroll(self, page: Page, distance: int = 0):
        """拟人化滚动：分段 + 随机速度 + 偶尔回滚"""
        if not self.speed.should_simulate["scroll"]:
            # TURBO 模式：直接滚动
            await page.evaluate(f"window.scrollBy(0, {distance or 500})")
            return

        if distance == 0:
            distance = random.randint(300, 800)

        segments = random.randint(3, 6)
        per_segment = distance // segments

        for i in range(segments):
            # 偶尔回滚一小段
            if random.random() < 0.1 and i > 0:
                await page.evaluate(f"window.scrollBy(0, {-random.randint(30, 80)})")
                await asyncio.sleep(random.uniform(0.2, 0.4))

            await page.evaluate(f"window.scrollBy(0, {per_segment + random.randint(-30, 30)})")
            await asyncio.sleep(self.speed.get_delay("scroll_segment"))

    async def _bezier_move(self, page, x1, y1, x2, y2, steps=20):
        """贝塞尔曲线鼠标移动"""
        # 控制点：在起终点之间随机偏移
        cx1 = x1 + (x2 - x1) * 0.3 + random.uniform(-50, 50)
        cy1 = y1 + (y2 - y1) * 0.3 + random.uniform(-50, 50)
        cx2 = x1 + (x2 - x1) * 0.7 + random.uniform(-30, 30)
        cy2 = y1 + (y2 - y1) * 0.7 + random.uniform(-30, 30)

        for i in range(1, steps + 1):
            t = i / steps
            # 三次贝塞尔曲线
            x = (1-t)**3 * x1 + 3*(1-t)**2*t * cx1 + 3*(1-t)*t**2 * cx2 + t**3 * x2
            y = (1-t)**3 * y1 + 3*(1-t)**2*t * cy1 + 3*(1-t)*t**2 * cy2 + t**3 * y2
            # 添加微抖动
            x += random.uniform(-2, 2)
            y += random.uniform(-2, 2)
            await page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.01, 0.04))
```

### 5.4 反爬检测系统

```python
class AntiDetectSystem:
    """反爬检测系统 — 持续监控 + 自动响应"""

    # 检测规则
    CAPTCHA_PATTERNS = [
        ".captcha", "#captcha", ".verify-code", ".slider-verify",
        "img[src*='captcha']", ".geetest", ".nc-container",
    ]
    BLOCK_TEXT_PATTERNS = [
        "操作频繁", "请稍后再试", "访问过于频繁", "请求过于频繁",
        "验证码", "人机验证", "安全验证",
    ]
    CAPTCHA_URL_PATTERNS = [
        "/captcha", "/verify", "/check", "/security-check",
    ]
    LOGIN_URL_PATTERNS = [
        "/login", "/signin", "/auth",
    ]

    def __init__(self, speed_controller: SpeedController,
                 log_collector: "LogCollector | None" = None):
        self.speed = speed_controller
        self.log_collector = log_collector  # 从 BrowserController 拆分出的日志模块
        self._risk_level = 0
        self._consecutive_risks = 0

    async def check(self, page: Page, snapshot: PageSnapshot) -> int:
        """检测当前页面的反爬风险等级，返回 0-4"""
        risk = 0

        # 1. URL 异常检测
        if any(p in snapshot.url for p in self.CAPTCHA_URL_PATTERNS):
            risk = max(risk, 2)
        if any(p in snapshot.url for p in self.LOGIN_URL_PATTERNS):
            # 非预期的登录跳转 = session 过期
            risk = max(risk, 1)

        # 2. 验证码元素检测
        for pattern in self.CAPTCHA_PATTERNS:
            if await page.query_selector(pattern):
                risk = max(risk, 2)
                snapshot.has_captcha = True
                break

        # 3. 封禁文本检测
        page_text = snapshot.main_content
        for pattern in self.BLOCK_TEXT_PATTERNS:
            if pattern in page_text:
                risk = max(risk, 2)
                snapshot.has_block_text = True
                break

        # 4. 网络状态检测（通过 LogCollector）
        if self.log_collector:
            network_logs = await self.log_collector.get_network_logs()
            for log in network_logs:
                if log.get("status") in (429, 403):
                    risk = max(risk, 3)
                    break

        # 更新风险等级
        if risk > 0:
            self._consecutive_risks += 1
            if self._consecutive_risks >= 3:
                risk = max(risk, 4)  # 连续 3 次风险 → 封禁级
        else:
            self._consecutive_risks = 0

        self._risk_level = risk
        self.speed.set_risk_level(risk)
        return risk

    async def respond(self, risk_level: int, page: Page) -> str:
        """根据风险等级执行响应策略"""
        if risk_level == 0:
            return "正常"
        elif risk_level == 1:
            # 轻度：降速
            return "降速 (STEALTH)"
        elif risk_level == 2:
            # 中度：降速 + 随机浏览行为
            await self._simulate_browsing(page)
            return "降速 + 模拟浏览"
        elif risk_level == 3:
            # 重度：暂停 + 换指纹
            await asyncio.sleep(random.uniform(30, 120))
            return "暂停 30-120s + 换指纹"
        else:
            # 封禁：停止
            return "停止任务 + 保存现场"

    async def _simulate_browsing(self, page: Page):
        """模拟随机浏览行为（降低可疑度）"""
        # 随机滚动
        await page.evaluate(f"window.scrollBy(0, {random.randint(-200, 500)})")
        await asyncio.sleep(random.uniform(2, 5))
        # 随机移动鼠标
        await page.mouse.move(random.randint(100, 800), random.randint(100, 600))
        await asyncio.sleep(random.uniform(1, 3))
```

### 5.5 指纹管理（统一到 anti_detect）

将 `shared/fingerprint_manager.py` 的功能统一到反检测模块：

```python
class FingerprintManager:
    """指纹管理器 — 统一管理浏览器指纹随机化和轮换"""

    def __init__(self):
        self._current_opts: dict | None = None

    def generate_camoufox_opts(self) -> dict:
        """生成 Camoufox 随机指纹参数"""
        self._current_opts = {
            "os": random.choice(["win", "macos", "linux"]),
            "window_size": random.choice([
                (1920, 1080), (1366, 768), (1536, 864), (1440, 900),
            ]),
            "screen": {...},
        }
        return self._current_opts

    def random_user_agent(self) -> str:
        """生成随机 User-Agent"""
        ...

    def rotate(self) -> dict:
        """轮换指纹（Level 3 风险时调用）"""
        return self.generate_camoufox_opts()
```

### 5.6 执行引擎

```python
class ExecutionEngine:
    """执行引擎 — 统一调度行为模拟、速度控制、反爬检测、健康监控"""

    def __init__(self, browser: BrowserController,
                 log_collector: LogCollector,
                 health_monitor: HealthMonitor):
        self.browser = browser
        self.log_collector = log_collector
        self.health = health_monitor
        self.behavior = BehaviorSimulator(SpeedController())
        self.anti_detect = AntiDetectSystem(self.behavior.speed, log_collector)
        self.perceiver = PagePerceiver()

    async def execute(self, action: Action) -> dict:
        """执行一个动作"""
        page = self.browser.page

        # 执行前：反爬检测
        snapshot = await self.perceiver.perceive(page)
        risk = await self.anti_detect.check(page, snapshot)
        if risk >= 2:
            response = await self.anti_detect.respond(risk, page)
            logger.warning("反爬检测: Level %d → %s", risk, response)
            if risk >= 4:
                return {"ok": False, "error": "被封禁，任务终止", "risk_level": risk}

        # 执行动作
        result = await self._do_action(action)

        # 执行失败时：尝试健康修复
        if not result.get("ok", True):
            repair_result = await self.health.auto_repair(page.url)
            if repair_result.get("ok"):
                # 修复成功，重试动作
                result = await self._do_action(action)

        # 执行后：延迟
        delay = self.behavior.speed.get_delay(self._action_to_operation(action))
        if delay > 0:
            await asyncio.sleep(delay)

        return result

    async def _do_action(self, action: Action) -> dict:
        """根据动作类型分发执行"""
        page = self.browser.page

        if action.type == ActionType.CLICK:
            element = await self._resolve_target(action.target)
            if element:
                await self.behavior.human_click(page, element)
                return {"ok": True, "action": "click", "target": action.target}
            return {"ok": False, "error": f"元素未找到: {action.target}"}

        elif action.type == ActionType.TYPE:
            await self.behavior.human_type(page, action.target, action.value)
            return {"ok": True, "action": "type", "target": action.target}

        elif action.type == ActionType.SCROLL:
            await self.behavior.human_scroll(page, int(action.value or 500))
            return {"ok": True, "action": "scroll"}

        elif action.type == ActionType.NAVIGATE:
            await self.browser.navigate_to(action.value)
            return {"ok": True, "action": "navigate", "url": action.value}

        elif action.type == ActionType.EXTRACT:
            data = await self._extract_data(action.target, action.params)
            return {"ok": True, "action": "extract", "data": data}

        # ... 其他动作类型

    async def _resolve_target(self, target: str) -> AnnotatedElement | None:
        """解析目标：支持 @ref、语义类型、CSS 选择器"""
        page = self.browser.page
        snapshot = await self.perceiver.perceive(page)

        # 1. @ref 编号引用
        if target.startswith("@"):
            ref = int(target[1:])
            element = snapshot.find_by_ref(ref)
            if element:
                return element

        # 2. 语义类型匹配
        element = snapshot.find_element(target)
        if element:
            return element

        # 3. CSS 选择器回退
        el = await page.query_selector(target)
        if el:
            box = await el.bounding_box()
            return AnnotatedElement(
                tag=await el.evaluate("e => e.tagName.toLowerCase()"),
                text=await el.inner_text() if await el.is_visible() else "",
                selector=target,
                semantic_type="unknown",
                confidence=0,
                is_visible=await el.is_visible(),
                is_interactable=await el.is_enabled(),
                bounding_box=box,
            )
        return None
```

---

## 6. CLI 命令体系

### 6.1 命令总览

```
agent                          # 显示帮助
agent <subcommand> [options]   # 子命令模式（精确，零 Token）
agent "<自然语言>"              # 对话模式（模糊需求，消耗 Token）
```

### 6.2 核心子命令

#### `browse` — 交互式浏览

最核心的命令，像人一样打开页面、理解、交互。

```bash
# 打开页面并进入交互浏览模式（REPL）
agent browse https://zhipin.com

# 带任务浏览：Agent 自动完成任务
agent browse https://zhipin.com --task "搜索深圳普工职位"

# 带流程骨架浏览
agent browse https://zhipin.com --flow zhipin_search

# 指定速度档位
agent browse https://zhipin.com --speed stealth

# 无头模式
agent browse https://zhipin.com --task "搜索" --headless
```

**交互模式**（无 `--task` 时）：进入 REPL，用户实时指挥 Agent：
```
agent browse https://zhipin.com
> 找到搜索框并输入"深圳"
✅ 已在搜索框输入"深圳"
> 点击搜索
✅ 已点击搜索按钮，等待结果加载...
> 提取当前页面所有职位
📊 提取到 30 条职位数据
> 下一页
✅ 已翻到第 2 页
> exit
```

**选项**：

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--task, -t` | 任务描述（自动模式） | 无（进入 REPL） |
| `--flow, -f` | 流程骨架名称 | 自动匹配 |
| `--speed` | 速度档位 turbo/normal/stealth | normal |
| `--headless` | 无头模式 | false |
| `--max-steps` | 最大执行步数 | 50 |
| `--timeout` | 总超时时间（秒） | 300 |

---

#### `extract` — 精准数据提取

不需要交互，直接从页面提取结构化数据。

```bash
# 提取页面文本
agent extract https://example.com/article

# 用选择器提取
agent extract https://zhipin.com/job/123 --selector ".job-detail"

# 提取列表数据（自动翻页）
agent extract https://zhipin.com/web/geek/job \
  --list ".job-list li" \
  --fields "title=.job-name,salary=.salary,company=.company-name" \
  --pages 5

# 输出格式
agent extract https://example.com --format json    # json/csv/table(默认)
```

**选项**：

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--selector, -s` | CSS 选择器 | body |
| `--list, -l` | 列表项选择器 | 无 |
| `--fields` | 字段映射 name=selector | 无 |
| `--pages` | 翻页数 | 1 |
| `--format` | 输出格式 table/json/csv | table |
| `--output, -o` | 输出文件 | stdout |
| `--speed` | 速度档位 | turbo |

---

#### `interact` — 执行交互流程

预定义的交互流程，适合重复性操作。

```bash
# 登录
agent interact --flow login --url https://zhipin.com

# 搜索+采集
agent interact --flow zhipin_search \
  --params '{"city":"深圳","keyword":"普工","pages":5}'

# 自定义流程文件
agent interact --flow-file my_flow.yaml
```

**流程定义文件**（YAML）：
```yaml
name: zhipin_search
description: BOSS直聘职位搜索
url_pattern: zhipin.com
steps:
  - action: wait
    target: domcontentloaded
    wait_after: 1.0
  - action: click
    target: search_input
    wait_after: 0.3
  - action: type
    target: search_input
    value: "{{keyword}}"
    wait_after: 0.5
  - action: click
    target: search_btn
    wait_after: 2.0
  - action: wait
    target: networkidle
    wait_after: 1.0
  - action: extract
    target: ".job-list li"
    fields:
      title: ".job-name"
      salary: ".salary"
    condition: page_type == search_results
  - action: click
    target: next_page
    wait_after: 1.5
    condition: has_next_page
    fallback: stop
  - action: extract
    target: ".job-list li"
    condition: page_type == search_results
```

---

#### `login` — 登录管理

```bash
# 交互式登录
agent login https://zhipin.com

# 检查登录状态
agent login --check https://zhipin.com

# 列出已保存的登录态
agent login --list

# 删除登录态
agent login --remove zhipin
```

---

#### `snapshot` — 页面快照

获取页面的结构化理解，不执行任何操作。

```bash
# DOM 语义快照
agent snapshot https://zhipin.com

# 只输出可交互元素
agent snapshot https://zhipin.com --type interactive

# 页面结构树
agent snapshot https://zhipin.com --type tree

# 保存到文件
agent snapshot https://zhipin.com --save snapshot.json
```

**输出示例**：
```
页面: BOSS直聘 (https://www.zhipin.com)
类型: home

可交互元素:
  [1] search_input  [@1] 搜索框 ".search-input"
  [2] search_btn    [@2] 搜索   ".search-btn"
  [3] nav_link      [@3] 城市选择 ".city-select"
  [4] login_btn     [@4] 登录   ".login-btn"

表单:
  搜索: .search-input (text)

分页: 无
弹窗: 无
```

---

#### `monitor` — 页面监控

```bash
# 等待元素出现
agent monitor https://example.com --wait-selector ".result-loaded"

# 监控变化
agent monitor https://example.com/price --watch ".price" --interval 30

# 等待内容变化
agent monitor https://example.com --wait-change --timeout 120
```

---

#### `chat` — 对话模式

```bash
# 单次问答
agent chat "帮我查一下深圳普工的平均薪资"

# 交互式对话
agent chat --interactive

# 指定模型
agent chat --model deepseek-chat "分析这个职位"
```

---

#### `server` — MCP 服务

```bash
# stdio 模式
agent server

# SSE 模式
agent server --port 8080

# 指定能力
agent server --capabilities core,vision,devtools
```

---

### 6.3 辅助子命令

```bash
agent check          # 健康检查
agent stats          # 统计信息
agent clean          # 清理缓存
agent --version      # 版本
```

### 6.4 全局选项

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--mode, -m` | 业务模式 (zhipin, qcc, tyc...) | 自动检测 |
| `--speed` | 速度档位 turbo/normal/stealth | normal |
| `--headless` | 无头模式 | false |
| `--output, -o` | 输出文件路径 | stdout |
| `--format` | 输出格式 table/json/csv/raw | table |
| `--verbose, -v` | 详细日志 | false |
| `--quiet, -q` | 静默模式 | false |
| `--config, -c` | 指定配置文件 | 默认 |

### 6.5 命令与架构映射

```
CLI 命令          感知层              决策层              执行层
─────────────────────────────────────────────────────────────────
browse --task    DOM快照+语义标注    流程骨架+语义推理    行为模拟+反爬检测
extract          DOM快照+选择器      直接提取(无决策)     全速提取(TURBO)
interact --flow  DOM快照            流程文件驱动         按流程执行
login            DOM快照            等待登录检测         保存登录态
snapshot         DOM快照+语义标注    无(只读)            无(只读)
monitor          DOM快照+diff       变化检测            等待/通知
chat             (由LLM决定)        LLM推理             LLM生成动作
server           (MCP协议)          MCP分发             MCP handlers
```

### 6.6 输出设计

1. **默认简洁**：只输出关键信息，一行一条
2. **`--verbose` 详细**：输出每一步操作细节
3. **`--quiet` 纯数据**：只输出最终结果，适合管道
4. **`--format json`**：结构化输出，适合程序间传递
5. **进度指示**：长时间操作显示进度（`[3/10]`）

```bash
# 简洁模式（默认）
$ agent extract https://zhipin.com --list ".job-list li" --pages 5
[1/5] 提取 30 条...
[2/5] 提取 30 条...
✅ 共 150 条，已保存到 output.json

# 静默模式（管道友好）
$ agent extract https://zhipin.com --list ".job-list li" --format json --quiet
[{"title":"仓库普工","salary":"5-6K",...},...]

# 详细模式（调试用）
$ agent browse https://zhipin.com --task "搜索深圳普工" -v
[12:30:01] 启动浏览器 (Camoufox, 指纹: Win10/Chrome125)
[12:30:03] 导航到 https://www.zhipin.com (等待: domcontentloaded)
[12:30:04] DOM 快照: 347 个节点, 12 个可交互元素
[12:30:04] 决策: 匹配流程骨架 zhipin_search → 步骤 1/5
[12:30:05] 点击 search_input (置信度: 0.95)
[12:30:05] 输入 "深圳" (逐字, 6字, 0.8s)
[12:30:06] 点击 search_btn
[12:30:08] 等待搜索结果加载...
[12:30:09] DOM 快照: 512 个节点, 15 个可交互元素
[12:30:09] 决策: 流程步骤 6/7 → extract
[12:30:10] 提取 30 条数据
[12:30:11] 点击 next_page
[12:30:13] 反爬检测: Level 2 → 降速 + 模拟浏览
[12:30:18] 提取 30 条数据
...
[12:30:45] 任务完成: 5 页 150 条, 耗时 44s
```

---

## 7. MCP 定位

### 7.1 MCP 为辅

MCP Server 保留，但定位从"主要交互方式"降级为"AI 编程助手的辅助接口"。

### 7.2 MCP 与 CLI 共享 BrowsingAgent

```
CLI 入口 ──→ BrowsingAgent ──→ BrowserController (精简版)
                                    ↑
MCP Server ──→ MCP Handlers ───────┘
```

- CLI 和 MCP 共享 `BrowsingAgent`、`BrowserController`、`PagePerceiver` 等核心层
- MCP handlers 调用与 CLI 相同的 BrowsingAgent API，不重复实现逻辑
- 旧的 `BrowserAgent`（薄封装层）删除，MCP handlers 直接调用 BrowsingAgent
- MCP 工具数量保持在 40 个以内

### 7.3 @ref 兼容

MCP 的 @ref 元素引用系统保留为 selector 的别名：
- `get_interactive_elements()` 返回带 ref 编号的元素列表
- 后续操作可用 `@3` 引用，由 `RefManager` 解析为实际 selector
- 内部实现统一走 `PageSnapshot.find_by_ref()`

### 7.4 MCP 工具精简方向

现有 40 个 MCP 工具可以进一步按"感知-决策-执行"归类：

| 类别 | 工具 | 说明 |
|------|------|------|
| 感知 | browser_snapshot, browser_debug_info | 页面感知 |
| 导航 | browser_navigate, browser_go_back | 页面导航 |
| 交互 | browser_click, browser_type, browser_press_key, browser_fill_form, browser_select_option, browser_hover, browser_drag_coordinate, browser_click_coordinate, browser_hover_coordinate | 页面交互 |
| 等待 | browser_wait_navigation, browser_wait_selector | 等待条件 |
| 数据 | browser_take_screenshot, browser_text, browser_html, browser_cookie_list, browser_storage_state, browser_localstorage | 数据获取 |
| 对话 | browser_handle_dialog | 对话框处理 |
| DevTools | devtools_execute | 开发者工具 |
| 视觉 | browser_visual_analyze, browser_element_screenshot, browser_compare_visual | 视觉分析 |
| PDF | browser_pdf_export | PDF 导出 |
| 模式 | zhipin_* (9个) | 业务模式 |

---

## 8. 与现有代码的整合

### 8.1 BrowserController 拆分方案

| 拆分后模块 | 来源 | 职责 |
|-----------|------|------|
| `BrowserController` (精简版) | `browser.py` 核心操作 | 启动/停止、导航、点击、输入、滚动、截图、JS执行 |
| `HealthMonitor` | `browser.py` 诊断修复部分 | 页面健康检测、自动修复循环、7个修复策略 |
| `Session` | `browser.py` Cookie/Storage + `session.py` | Cookie管理、Storage管理、登录检测、短效Cookie刷新 |
| `LogCollector` | `browser.py` 日志部分 | 控制台日志、网络日志、对话框、无障碍树 |

### 8.2 modes/ → 新架构迁移方案

按架构重新分配，每个文件归入对应层：

| 现有文件 | 新归属 | 说明 |
|---------|-------|------|
| `modes/zhipin/selectors.py` | `flows/zhipin/semantic_rules.py` | CSS 选择器 → 感知层的语义推断规则 |
| `modes/zhipin/search_flow.py` | `flows/zhipin/flows.py` | 搜索流程 → FlowSkeleton 定义 |
| `modes/zhipin/page_analyzer.py` | `perceiver.py` 的站点特化规则 | 页面分析 → 感知层的站点特化标注 |
| `modes/zhipin/scraper.py` | **删除** | 直接操作 Playwright 的旧爬虫，由新引擎替代 |
| `modes/zhipin/storage.py` | `modes/zhipin/storage.py` (保留) | 数据库存储，业务基础设施，不属于任何层 |
| `modes/zhipin/exporter.py` | `modes/zhipin/exporter.py` (保留) | 数据导出，业务基础设施 |
| `modes/zhipin/city_codes.py` | `modes/zhipin/city_codes.py` (保留) | 城市编码，业务数据 |
| `modes/zhipin/keyword_strategy.py` | `modes/zhipin/keyword_strategy.py` (保留) | 关键词策略，业务逻辑 |
| `modes/zhipin/pre_filter.py` | `modes/zhipin/pre_filter.py` (保留) | 预过滤，业务逻辑 |
| `modes/zhipin/__init__.py` | `flows/zhipin/__init__.py` | MCP 工具注册接口保留 |

**迁移后的目录结构**：

```
src/
├── agent/
│   ├── cli/main.py              # 统一 agent 入口
│   ├── core/
│   │   ├── browser.py           # BrowserController (精简版, ~500行)
│   │   ├── health_monitor.py    # HealthMonitor (新增, 从browser.py拆出)
│   │   ├── log_collector.py     # LogCollector (新增, 从browser.py拆出)
│   │   ├── session.py           # Session (合并现有session.py + browser.py的Cookie部分)
│   │   ├── perceiver.py         # PagePerceiver (新增)
│   │   ├── decider.py           # DecisionEngine + SemanticDecider + LoopController (新增)
│   │   ├── executor.py          # ExecutionEngine + BehaviorSimulator + SpeedController (新增)
│   │   ├── anti_detect.py       # AntiDetectSystem + FingerprintManager + STEALTH_SCRIPT (升级)
│   │   ├── ref_manager.py       # RefManager (新增, @ref 兼容层)
│   │   ├── agent.py             # BrowsingAgent (重写, 替代旧BrowserAgent)
│   │   ├── capabilities.py      # MCP 能力组 (保留)
│   │   └── mcp_config.py        # MCP 配置 (保留)
│   ├── mcp/
│   │   ├── definitions.py       # 工具 Schema (保留)
│   │   ├── handlers.py          # 处理函数 (改为调用 BrowsingAgent)
│   │   ├── server.py            # MCP 服务器 (保留, 入口改为 agent server)
│   │   └── validation.py        # 参数校验 (保留)
│   └── flows/                   # 流程骨架 (新增)
│       ├── __init__.py
│       ├── builtin.py           # 通用流程骨架（登录、搜索、翻页）
│       ├── zhipin/              # BOSS直聘
│       │   ├── __init__.py
│       │   ├── flows.py         # FlowSkeleton 定义
│       │   └── semantic_rules.py # 语义推断规则
│       └── qcc/                 # 企查查
│           ├── __init__.py
│           └── flows.py
├── modes/                       # 业务支持 (保留, 存放非架构层的业务逻辑)
│   └── zhipin/
│       ├── storage.py
│       ├── exporter.py
│       ├── city_codes.py
│       ├── keyword_strategy.py
│       └── pre_filter.py
├── shared/
│   ├── config.py                # 保留
│   ├── delay.py                 # 升级为 SpeedController 的基础设施
│   ├── error_handler.py         # 保留
│   ├── exceptions.py            # 保留
│   ├── logging_config.py        # 保留
│   ├── profiler.py              # 保留
│   ├── retry.py                 # 保留
│   ├── gov_site_decorator.py    # 保留, 作为 AntiDetectSystem Level 2 的特例
│   ├── gov_site_limiter.py      # 保留, 作为 AntiDetectSystem Level 2 的特例
│   └── engine/                  # **废弃**, 功能由新架构替代
│       └── (标记为 deprecated, 不再新用)
└── chat/                        # 合并为 agent chat 子命令
    └── cli.py                   # 保留对话引擎, CLI 入口合并
```

### 8.3 废弃模块

| 废弃模块 | 替代方案 | 说明 |
|---------|---------|------|
| `shared/engine/scraping_engine.py` | `BrowsingAgent` 循环 | 声明式爬取引擎由新架构替代 |
| `shared/engine/dom_reader.py` | `PagePerceiver` | DOM 读取由感知层替代 |
| `shared/engine/profile.py` | `FlowSkeleton` + 语义规则 | 站点画像由流程骨架替代 |
| `shared/engine/filter_chain.py` | `modes/` 业务层 | 过滤逻辑保留在业务层 |
| `shared/engine/adapter_protocol.py` | `FlowSkeleton` | 站点适配由流程骨架替代 |
| `shared/engine/url_builder.py` | `FlowSkeleton` | URL 构建由流程骨架替代 |
| `shared/engine/report_builder.py` | `modes/` 业务层 | 报告构建保留在业务层 |
| `shared/fingerprint_manager.py` | `anti_detect.py` 中的 `FingerprintManager` | 指纹管理统一到反检测模块 |
| `agent/core/agent.py` (旧 BrowserAgent) | `agent/core/agent.py` (新 BrowsingAgent) | 薄封装层由统一 Agent 替代 |

### 8.4 pyproject.toml 变更

```toml
[project.scripts]
agent = "agent.cli.main:main"
# 删除: agent-cli, chat-agent, send-report
```

### 8.5 迁移策略

分阶段迁移，每阶段可独立验证：

**阶段 1**：拆分 BrowserController（精简核心 + HealthMonitor + Session + LogCollector）
**阶段 2**：新增感知层 + 决策层 + 执行层（纯新增，不影响现有代码）
**阶段 3**：重写 BrowsingAgent 替代旧 BrowserAgent
**阶段 4**：重写 CLI 入口，合并三个 CLI 为统一 `agent` 命令
**阶段 5**：迁移 modes/ → flows/，废弃 shared/engine/
**阶段 6**：升级行为模拟（贝塞尔曲线、拟人输入）
**阶段 7**：MCP 适配新架构（handlers 改为调用 BrowsingAgent）

---

## 9. 开放问题

### 已解决

| 问题 | 决策 |
|------|------|
| BrowserController 拆分策略 | 彻底拆分为 4 个模块 |
| BrowserAgent vs BrowsingAgent | BrowsingAgent 替代 BrowserAgent |
| 循环控制机制 | 智能护栏（最大步数+超时+重复检测+每5步LLM进度评估） |
| 错误恢复策略 | 回退+暂停问用户 |
| modes/ → flows/ 迁移 | 按架构重新分配 |
| shared/engine/ 处理 | 新架构替代，旧引擎废弃 |
| fingerprint_manager 归属 | 统一到 anti_detect |
| @ref 系统去留 | 保留为 selector 的别名 |
| FlowSkeleton 循环机制 | 用 condition 控制循环 |
| LLM 输出约束 | 严格 JSON Schema + 最近5步上下文 |
| 项目路径标准化 | 包名 `agent` → `browser_agent`；`src/tests/` → `tests/`；`src/scripts/` → `scripts/`；`src/chat/` → `browser_agent/chat/`；`browser_profile_qcc/` → `data/profiles/qcc/` |

### 待解决

1. **流程骨架的存储格式**：Python 代码 vs YAML 文件 vs 数据库？倾向 Python 代码（类型安全 + IDE 支持），但 YAML 更适合非开发者编辑
2. **语义推理的 LLM 选择**：默认用哪个模型？是否支持配置？
3. **REPL 交互模式的实现**：用 prompt_toolkit 还是自研轻量 REPL？
4. **流程骨架的热加载**：是否支持运行时添加新流程骨架？
5. **多标签页管理**：browse 模式下如何处理新标签页打开？
6. **循环依赖问题**：`scraping_engine.py` 反向依赖 `modes/zhipin/*`，废弃时需要清理

---

## 附录 A：术语表

| 术语 | 说明 |
|------|------|
| BrowsingAgent | 统一 Agent，替代旧 BrowserAgent，编排感知-决策-执行循环 |
| 流程骨架 | 预定义的浏览步骤序列，用于已知网站 |
| 语义类型 | 元素的功能语义标注（如 search_input, next_page） |
| PageSnapshot | 页面结构化快照，感知层的输出 |
| Action | Agent 的动作，决策层的输出 |
| TURBO/NORMAL/STEALTH | 三种速度档位 |
| 风险等级 | 反爬检测的 0-4 级风险评级 |
| @ref | 元素编号引用，MCP 兼容的快捷定位方式 |
| 智能护栏 | 循环控制机制：步数限制+超时+重复检测+进度评估 |
| HealthMonitor | 从 BrowserController 拆出的页面健康诊断+自动修复模块 |
