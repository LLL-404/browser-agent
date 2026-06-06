"""决策层 — 动作生成、流程编排、循环控制与错误恢复。

层级结构:
  Level 1: FlowRegistry  — 预定义流程匹配（模板驱动）
  Level 2: SemanticDecider — LLM 语义推理（智能决策）
  Level 3: 视觉推理（预留，暂未实现）
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from shared.logging_config import get_logger

if TYPE_CHECKING:
    from browser_agent.core.perceiver import PageSnapshot

logger = get_logger("decider")

# =============================================================================
# ActionType — 动作类型常量
# =============================================================================


class ActionType:
    """浏览器操作动作类型常量。"""

    CLICK: str = "click"
    TYPE: str = "type"
    SCROLL: str = "scroll"
    NAVIGATE: str = "navigate"
    WAIT: str = "wait"
    EXTRACT: str = "extract"
    SCREENSHOT: str = "screenshot"
    HOVER: str = "hover"
    SELECT: str = "select"
    PRESS_KEY: str = "press_key"
    DIALOG: str = "dialog"
    GO_BACK: str = "go_back"
    SWITCH_TAB: str = "switch_tab"
    DONE: str = "done"
    NOOP: str = "noop"


# =============================================================================
# Action — 原子动作
# =============================================================================


@dataclass
class Action:
    """单个浏览器操作动作。

    Attributes:
        type: 动作类型，取 ActionType 中的常量值。
        target: 目标元素选择器或 URL。
        value: 操作值（如输入文本、滚动像素）。
        params: 额外参数（如 wait_after、modifiers）。
        reason: 执行此动作的决策理由。
        confidence: 决策置信度 [0.0, 1.0]。
    """

    type: str
    target: str | None = None
    value: str | None = None
    params: dict | None = None
    reason: str = ""
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典，排除 None 值字段。"""
        result: dict[str, Any] = {"type": self.type}
        if self.target is not None:
            result["target"] = self.target
        if self.value is not None:
            result["value"] = self.value
        if self.params:
            result["params"] = self.params
        if self.reason:
            result["reason"] = self.reason
        result["confidence"] = self.confidence
        return result

    @classmethod
    def noop(cls, reason: str = "") -> Action:
        """快捷构造空操作。"""
        return cls(type=ActionType.NOOP, reason=reason, confidence=0.0)

    @classmethod
    def done(cls, reason: str = "") -> Action:
        """快捷构造任务完成动作。"""
        return cls(type=ActionType.DONE, reason=reason, confidence=1.0)


# =============================================================================
# FlowStep / FlowSkeleton — 流程模板
# =============================================================================


@dataclass
class FlowStep:
    """流程中的单个步骤定义。

    Attributes:
        action: 动作类型（ActionType 常量）。
        target: 目标选择器或 URL。
        value: 可选的操作值。
        wait_after: 步骤执行后等待时间（秒）。
        fallback: 失败时的回退策略（选择器或 URL）。
        condition: 可选的前置条件（选择器表达式）。
    """

    action: str
    target: str
    value: str | None = None
    wait_after: float = 0.5
    fallback: str | None = None
    condition: str | None = None


@dataclass
class FlowSkeleton:
    """预定义浏览流程模板。

    Attributes:
        name: 流程名称（如 "zhipin_search"）。
        description: 流程描述。
        url_pattern: 匹配的 URL 模式（支持通配符 *）。
        page_type: 匹配的页面类型（PageType 常量）。
        steps: 流程步骤列表。
        on_error: 出错时的行为（ask_user / retry / skip / abort）。
    """

    name: str
    description: str
    url_pattern: str
    page_type: str
    steps: list[FlowStep]
    on_error: str = "ask_user"


# =============================================================================
# FlowRegistry — 流程注册与匹配
# =============================================================================


class FlowRegistry:
    """预定义浏览流程的注册与匹配引擎。

    通过 URL 模式和页面类型匹配最合适的流程模板，
    减少对 LLM 的依赖，提升常见场景的执行效率。
    """

    def __init__(self) -> None:
        self._flows: list[FlowSkeleton] = []
        self._load_builtin_flows()

    def register(self, flow: FlowSkeleton) -> None:
        """注册一个流程模板。"""
        self._flows.append(flow)
        logger.debug("注册流程: %s (pattern=%s, page_type=%s)",
                     flow.name, flow.url_pattern, flow.page_type)

    def match(self, url: str, page_type: str) -> FlowSkeleton | None:
        """根据 URL 和页面类型匹配最合适的流程。

        匹配优先级:
          1. 精确匹配 URL 模式 + 页面类型
          2. 仅匹配 URL 模式
          3. 仅匹配页面类型

        Returns:
            匹配到的 FlowSkeleton，无匹配时返回 None。
        """
        candidates: list[tuple[int, FlowSkeleton]] = []

        for flow in self._flows:
            url_match = self._url_matches(url, flow.url_pattern)
            type_match = flow.page_type == page_type

            if url_match and type_match:
                candidates.append((3, flow))
            elif url_match:
                candidates.append((2, flow))
            elif type_match:
                candidates.append((1, flow))

        if not candidates:
            logger.debug("无匹配流程: url=%s, page_type=%s", url, page_type)
            return None

        # 按优先级降序，取最高
        candidates.sort(key=lambda x: x[0], reverse=True)
        best = candidates[0][1]
        logger.info("匹配流程: %s (priority=%d)", best.name, candidates[0][0])
        return best

    @staticmethod
    def _url_matches(url: str, pattern: str) -> bool:
        """检查 URL 是否匹配模式（支持 * 通配符）。"""
        if pattern == "*":
            return True
        if "*" not in pattern:
            return pattern in url
        # 简单通配符匹配
        import fnmatch
        return fnmatch.fnmatch(url, pattern)

    def _load_builtin_flows(self) -> None:
        """加载内置的预定义流程模板。"""

        # ── BOSS 直聘搜索流程 ──
        self.register(FlowSkeleton(
            name="zhipin_search",
            description="BOSS 直聘职位搜索流程：搜索关键词 → 筛选 → 浏览结果",
            url_pattern="*zhipin.com/web/geek/job*",
            page_type="search_results",
            steps=[
                FlowStep(
                    action=ActionType.WAIT,
                    target=".search-job-result",
                    wait_after=1.0,
                    fallback=".job-list-box",
                ),
                FlowStep(
                    action=ActionType.TYPE,
                    target=".ipt-search",
                    value="",  # 由调用方注入
                    wait_after=0.5,
                    condition="input.ipt-search",
                ),
                FlowStep(
                    action=ActionType.CLICK,
                    target=".btn-search",
                    wait_after=2.0,
                    fallback="button:has-text('搜索')",
                ),
                FlowStep(
                    action=ActionType.WAIT,
                    target=".job-list-box .job-card-wrapper",
                    wait_after=1.0,
                ),
                FlowStep(
                    action=ActionType.EXTRACT,
                    target=".job-card-wrapper",
                    wait_after=0.5,
                ),
                FlowStep(
                    action=ActionType.SCROLL,
                    target="",
                    value="500",
                    wait_after=0.5,
                ),
            ],
            on_error="retry",
        ))

        # ── 通用搜索流程 ──
        self.register(FlowSkeleton(
            name="generic_search",
            description="通用搜索页流程：定位搜索框 → 输入 → 点击搜索 → 等待结果",
            url_pattern="*",
            page_type="search_results",
            steps=[
                FlowStep(
                    action=ActionType.WAIT,
                    target="body",
                    wait_after=0.5,
                ),
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
        ))

        # ── 登录页流程 ──
        self.register(FlowSkeleton(
            name="generic_login",
            description="通用登录页流程：填写用户名 → 密码 → 点击登录",
            url_pattern="*",
            page_type="login",
            steps=[
                FlowStep(
                    action=ActionType.WAIT,
                    target="body",
                    wait_after=0.5,
                ),
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
        ))

        # ── 验证码页流程 ──
        self.register(FlowSkeleton(
            name="captcha_encountered",
            description="遇到验证码时，暂停等待用户手动处理",
            url_pattern="*",
            page_type="captcha",
            steps=[
                FlowStep(
                    action=ActionType.WAIT,
                    target="body",
                    wait_after=30.0,
                ),
            ],
            on_error="ask_user",
        ))

        logger.info("已加载 %d 个内置流程", len(self._flows))


# =============================================================================
# LoopState — 循环状态
# =============================================================================


@dataclass
class LoopState:
    """Agent 主循环的运行状态追踪。

    记录步数、时间、重复检测、进度评估等关键指标，
    由 LoopController 消费以判断是否应继续循环。
    """

    step_count: int = 0
    max_steps: int = 50
    start_time: float = 0.0
    timeout_secs: float = 300.0
    recent_actions: list[str] = field(default_factory=list)
    repeat_threshold: int = 3
    eval_interval: int = 5
    last_eval_step: int = 0
    no_progress_count: int = 0
    no_progress_threshold: int = 2
    progress_snapshots: list[str] = field(default_factory=list)


# =============================================================================
# LoopController — 循环控制器
# =============================================================================


class LoopController:
    """主循环控制器，负责判断是否应继续执行下一步。

    核心检查:
      - 最大步数限制
      - 超时限制
      - 重复动作检测
      - 进度评估（每 N 步评估一次）
    """

    def __init__(self, max_steps: int = 50, timeout_secs: float = 300.0) -> None:
        self._state = LoopState(
            max_steps=max_steps,
            timeout_secs=timeout_secs,
            start_time=time.time(),
        )

    @property
    def state(self) -> LoopState:
        return self._state

    def should_continue(self, action: Action) -> tuple[bool, str]:
        """判断是否应继续循环。

        Returns:
            (是否继续, 停止原因) 元组。
        """
        state = self._state
        state.step_count += 1

        # 如果动作是 DONE，直接停止
        if action.type == ActionType.DONE:
            return False, "任务已完成"

        # 检查最大步数
        if state.step_count >= state.max_steps:
            return False, f"已达到最大步数限制 ({state.max_steps})"

        # 检查超时
        elapsed = time.time() - state.start_time
        if elapsed >= state.timeout_secs:
            return False, f"已超时 ({elapsed:.1f}s >= {state.timeout_secs}s)"

        # 检查重复动作
        if self._detect_repeat(action):
            return False, f"检测到重复动作模式: {action.type}"

        # 定期进度评估
        if state.step_count - state.last_eval_step >= state.eval_interval:
            state.last_eval_step = state.step_count
            # 进度评估需要 snapshot，此处仅标记需要评估
            logger.debug("触发放进度评估 (step=%d)", state.step_count)

        return True, ""

    def evaluate_progress(self, snapshot_text: str) -> bool:
        """评估是否有实质性进展。

        比较当前快照与历史快照，判断页面内容是否发生变化。
        通过 progress_snapshots 追踪内容变化。

        Returns:
            True 表示有进展，False 表示无进展。
        """
        state = self._state
        # 首次评估，记录快照
        if not state.progress_snapshots:
            state.progress_snapshots.append(snapshot_text)
            return True

        last = state.progress_snapshots[-1]
        # 简单比较：文本变化超过 10% 视为有进展
        if len(last) > 0:
            diff_ratio = self._text_diff_ratio(last, snapshot_text)
            if diff_ratio < 0.1:
                state.no_progress_count += 1
                logger.warning("无进展 (no_progress=%d/%d)",
                               state.no_progress_count, state.no_progress_threshold)
                if state.no_progress_count >= state.no_progress_threshold:
                    return False
            else:
                state.no_progress_count = 0
                state.progress_snapshots.append(snapshot_text)
                # 限制快照列表长度
                if len(state.progress_snapshots) > 5:
                    state.progress_snapshots = state.progress_snapshots[-5:]
        else:
            state.progress_snapshots.append(snapshot_text)

        return True

    @staticmethod
    def _text_diff_ratio(a: str, b: str) -> float:
        """计算两段文本的差异比例（简化版）。"""
        if a == b:
            return 0.0
        shorter = min(len(a), len(b))
        if shorter == 0:
            return 1.0
        # 计算不同字符数
        diff_count = sum(1 for ca, cb in zip(a, b, strict=False) if ca != cb)
        diff_count += abs(len(a) - len(b))
        return diff_count / max(len(a), len(b))

    def _detect_repeat(self, action: Action) -> bool:
        """检测是否陷入重复动作模式。"""
        state = self._state
        state.recent_actions.append(action.type)
        if len(state.recent_actions) > state.repeat_threshold * 3:
            state.recent_actions = state.recent_actions[-state.repeat_threshold * 3:]

        if len(state.recent_actions) < state.repeat_threshold:
            return False

        # 检查最近 N 个动作是否完全相同
        recent = state.recent_actions[-state.repeat_threshold:]
        return len(set(recent)) == 1


# =============================================================================
# ErrorRecovery — 错误恢复
# =============================================================================


class ErrorRecovery:
    """静态错误恢复策略。

    根据错误类型和当前流程上下文，生成最优的恢复动作。
    """

    # 错误关键词 → 恢复建议映射
    ERROR_PATTERNS: dict[str, str] = {
        "session": "session_expired",
        "过期": "session_expired",
        "expired": "session_expired",
        "验证码": "captcha",
        "captcha": "captcha",
        "verification": "captcha",
        "not found": "element_not_found",
        "未找到": "element_not_found",
        "element not found": "element_not_found",
        "timeout": "timeout",
        "超时": "timeout",
        "blocked": "access_blocked",
        "封禁": "access_blocked",
        "403": "access_blocked",
        "429": "rate_limited",
        "rate limit": "rate_limited",
    }

    @staticmethod
    async def handle_failure(
        action: Action,
        error: str,
        _snapshot: PageSnapshot,
        flow: FlowSkeleton | None = None,
    ) -> Action:
        """根据错误上下文生成恢复动作。

        恢复优先级:
          1. 流程中有 fallback → 使用 fallback 重试
          2. 特定错误类型 → 对应恢复策略
          3. 默认 → NOOP 并附上错误原因

        Args:
            action: 触发失败的动作。
            error: 错误消息字符串。
            snapshot: 当前页面快照。
            flow: 当前匹配的流程模板（可选）。

        Returns:
            恢复动作。
        """
        error_lower = error.lower()

        # 优先级 1: 流程回退
        if flow is not None:
            # 查找当前步骤索引（通过 action 匹配）
            for step in flow.steps:
                if step.action == action.type:
                    if step.fallback:
                        logger.info("使用流程回退: %s → %s", action.type, step.fallback)
                        return Action(
                            type=ActionType.CLICK if step.action == ActionType.CLICK else step.action,
                            target=step.fallback,
                            reason=f"回退策略: {step.fallback}",
                            confidence=0.7,
                        )
                    break

        # 优先级 2: 特定错误类型
        error_type = ErrorRecovery._classify_error(error_lower)

        if error_type == "session_expired":
            logger.warning("Session 过期，返回 NOOP 等待用户处理")
            return Action(
                type=ActionType.NOOP,
                reason="Session 已过期，需要重新登录",
                confidence=0.0,
            )

        if error_type == "captcha":
            logger.warning("检测到验证码，返回 WAIT 等待用户处理")
            return Action(
                type=ActionType.WAIT,
                target="body",
                value="30",
                reason="检测到验证码，等待 30 秒供用户手动处理",
                confidence=0.5,
                params={"wait_seconds": 30},
            )

        if error_type == "element_not_found":
            logger.warning("元素未找到: %s", action.target)
            return Action(
                type=ActionType.NOOP,
                reason=f"元素未找到: {action.target}，页面结构可能已变化",
                confidence=0.0,
            )

        if error_type == "timeout":
            logger.warning("操作超时: %s", action.type)
            return Action(
                type=ActionType.WAIT,
                target="body",
                value="3",
                reason="操作超时，等待 3 秒后重试",
                confidence=0.4,
                params={"wait_seconds": 3},
            )

        if error_type == "access_blocked":
            logger.warning("访问被拒绝")
            return Action(
                type=ActionType.NOOP,
                reason="访问被拒绝，可能需要更换 IP 或登录",
                confidence=0.0,
            )

        if error_type == "rate_limited":
            logger.warning("触发频率限制")
            return Action(
                type=ActionType.WAIT,
                target="body",
                value="10",
                reason="触发频率限制，等待 10 秒",
                confidence=0.5,
                params={"wait_seconds": 10},
            )

        # 优先级 3: 默认 — NOOP
        logger.error("未分类错误，返回 NOOP: %s", error)
        return Action(
            type=ActionType.NOOP,
            reason=f"未处理的错误: {error[:100]}",
            confidence=0.0,
        )

    @staticmethod
    def _classify_error(error_lower: str) -> str:
        """根据错误消息关键词分类错误类型。"""
        for keyword, error_type in ErrorRecovery.ERROR_PATTERNS.items():
            if keyword in error_lower:
                return error_type
        return "unknown"


# =============================================================================
# SemanticDecider — LLM 语义决策
# =============================================================================


# 用于约束 LLM 输出的 JSON Schema
ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                ActionType.CLICK, ActionType.TYPE, ActionType.SCROLL,
                ActionType.NAVIGATE, ActionType.WAIT, ActionType.EXTRACT,
                ActionType.SCREENSHOT, ActionType.HOVER, ActionType.SELECT,
                ActionType.PRESS_KEY, ActionType.DIALOG, ActionType.GO_BACK,
                ActionType.SWITCH_TAB, ActionType.DONE, ActionType.NOOP,
            ],
            "description": "要执行的动作类型",
        },
        "target": {
            "type": "string",
            "description": "目标元素选择器、URL 或按键名",
        },
        "value": {
            "type": "string",
            "description": "操作值（输入文本、滚动距离等）",
        },
        "reason": {
            "type": "string",
            "description": "执行此动作的决策理由",
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "决策置信度",
        },
    },
    "required": ["action", "reason"],
}


class SemanticDecider:
    """基于 LLM 的语义决策器。

    将页面文本描述和任务目标发送给 LLM，
    由 LLM 推理出下一步最优动作。

    在没有匹配流程模板时作为 Level 2 回退。
    """

    def __init__(self, llm_client: Any = None) -> None:
        """初始化语义决策器。

        Args:
            llm_client: LLM 客户端（兼容 OpenAI 接口风格）。
                        传入 None 时使用静态规则回退。
        """
        self._llm = llm_client
        self._history: list[dict[str, str]] = []
        self._max_history = 10

    async def decide(self, snapshot: PageSnapshot, task: str) -> Action:
        """基于页面快照和任务目标，使用 LLM 决定下一步动作。

        Args:
            snapshot: 当前页面感知快照。
            task: 用户任务描述。

        Returns:
            决策出的 Action。
        """
        page_desc = snapshot.to_text_description()

        if self._llm is None:
            # 无 LLM 时使用静态规则回退
            return self._static_fallback(snapshot, task)

        prompt = self._build_prompt(page_desc, task)

        try:
            response = await self._call_llm(prompt)
            action = self._parse_action(response)
            self._add_to_history(prompt, response)
            return action
        except Exception as e:
            logger.warning("LLM 决策失败，使用静态回退: %s", e)
            return self._static_fallback(snapshot, task)

    def _build_prompt(self, page_desc: str, task: str) -> str:
        """构建发送给 LLM 的提示词。"""
        history_text = self._format_history()

        return f"""你是一个浏览器自动化 Agent。根据当前页面信息决定下一步操作。

## 任务目标
{task}

## 历史操作
{history_text if history_text else "（无历史）"}

## 当前页面信息
{page_desc}

## 可用动作
- click: 点击元素（需要 target 选择器）
- type: 输入文本（需要 target 选择器 + value 文本）
- scroll: 滚动页面（需要 value 像素值，如 "500" 或 "-500"）
- navigate: 导航到 URL（需要 target URL）
- wait: 等待（需要 value 秒数）
- extract: 提取数据（需要 target 选择器）
- screenshot: 截图
- hover: 悬停元素（需要 target 选择器）
- select: 选择下拉选项（需要 target 选择器 + value 选项值）
- press_key: 按键（需要 target 键名，如 "Enter"）
- dialog: 处理弹窗
- go_back: 返回上一页
- switch_tab: 切换标签页
- done: 任务完成
- noop: 不操作（遇到问题时）

## 输出格式
请以 JSON 格式输出，包含 action、target、value、reason、confidence 字段。
只输出 JSON，不要包含其他文字。"""

    def _format_history(self) -> str:
        """格式化历史操作记录为文本。"""
        if not self._history:
            return ""
        lines = []
        for i, entry in enumerate(self._history[-self._max_history:], 1):
            # 提取 prompt 中的关键信息
            lines.append(f"  步骤 {i}: {entry.get('response', '')[:100]}")
        return "\n".join(lines)

    def _parse_action(self, response: str) -> Action:
        """从 LLM 响应中解析 Action 对象。

        支持纯 JSON 和包含 markdown 代码块的响应格式。
        """
        # 尝试提取 JSON 代码块
        response = response.strip()
        if response.startswith("```"):
            # 移除 markdown 代码块标记
            lines = response.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            response = "\n".join(lines)

        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            # 尝试提取第一个 JSON 对象
            import re
            match = re.search(r'\{[^{}]*\}', response)
            if match:
                data = json.loads(match.group())
            else:
                logger.warning("无法解析 LLM 响应: %s", response[:200])
                return Action.noop(reason="LLM 响应解析失败")

        action_type = data.get("action", ActionType.NOOP)
        # 验证动作类型
        valid_types = {
            ActionType.CLICK, ActionType.TYPE, ActionType.SCROLL,
            ActionType.NAVIGATE, ActionType.WAIT, ActionType.EXTRACT,
            ActionType.SCREENSHOT, ActionType.HOVER, ActionType.SELECT,
            ActionType.PRESS_KEY, ActionType.DIALOG, ActionType.GO_BACK,
            ActionType.SWITCH_TAB, ActionType.DONE, ActionType.NOOP,
        }
        if action_type not in valid_types:
            logger.warning("未知动作类型: %s，回退到 NOOP", action_type)
            action_type = ActionType.NOOP

        return Action(
            type=action_type,
            target=data.get("target"),
            value=data.get("value"),
            reason=data.get("reason", ""),
            confidence=float(data.get("confidence", 0.5)),
        )

    def _add_to_history(self, prompt: str, response: str) -> None:
        """记录决策历史。"""
        self._history.append({"prompt": prompt, "response": response})
        if len(self._history) > self._max_history * 2:
            self._history = self._history[-self._max_history:]

    async def _call_llm(self, prompt: str) -> str:
        """调用 LLM 获取决策响应。"""
        if self._llm is None:
            raise RuntimeError("LLM 客户端未配置")

        # 兼容 OpenAI 接口风格
        if hasattr(self._llm, "chat"):
            result = await self._llm.chat(prompt)
        elif hasattr(self._llm, "complete"):
            result = await self._llm.complete(prompt)
        elif callable(self._llm):
            result = await self._llm(prompt)
        else:
            raise RuntimeError("不支持的 LLM 客户端接口")

        return str(result) if result else ""

    def _static_fallback(self, snapshot: PageSnapshot, task: str) -> Action:
        """无 LLM 时的静态规则回退决策。

        基于页面类型和任务关键词做简单规则匹配。
        """
        page_type = snapshot.page_type
        task_lower = task.lower()

        # 搜索类任务
        if any(kw in task_lower for kw in ("搜索", "search", "查找", "find")):
            search_input = snapshot.find_element("search_input")
            if search_input and search_input.selector:
                return Action(
                    type=ActionType.TYPE,
                    target=search_input.selector,
                    value=task,
                    reason="定位到搜索框，准备输入关键词",
                    confidence=0.7,
                )
            return Action(
                type=ActionType.TYPE,
                target="input[type='search'], input[placeholder*='搜索']",
                value=task,
                reason="尝试通用搜索框输入",
                confidence=0.4,
            )

        # 登录类页面
        if page_type == "login":
            return Action(
                type=ActionType.NOOP,
                reason="检测到登录页面，需要用户提供凭据",
                confidence=0.0,
            )

        # 验证码页面
        if page_type == "captcha":
            return Action(
                type=ActionType.WAIT,
                target="body",
                value="30",
                reason="检测到验证码，等待手动处理",
                confidence=0.5,
                params={"wait_seconds": 30},
            )

        # 提取数据类任务
        if any(kw in task_lower for kw in ("提取", "extract", "抓取", "scrape", "采集")) and snapshot.elements:
            return Action(
                type=ActionType.EXTRACT,
                target=".result-item, [class*='result'], [class*='list']",
                reason="尝试提取页面数据",
                confidence=0.5,
            )

        # 默认：滚动查看更多内容
        return Action(
            type=ActionType.SCROLL,
            value="500",
            reason="默认操作：向下滚动查看更多内容",
            confidence=0.3,
        )


# =============================================================================
# DecisionEngine — 决策引擎（主入口）
# =============================================================================


class DecisionEngine:
    """分层决策引擎，协调多级决策策略。

    决策层级:
      Level 1: FlowRegistry  — 预定义流程模板匹配（快速、确定性强）
      Level 2: SemanticDecider — LLM 语义推理（灵活、智能）
      Level 3: 视觉推理（预留，暂未实现）

    使用方式:
        engine = DecisionEngine()
        action = await engine.decide(snapshot, "搜索 Python 职位")
    """

    def __init__(
        self,
        flow_registry: FlowRegistry | None = None,
        llm_client: Any = None,
    ) -> None:
        self._flow_registry = flow_registry or FlowRegistry()
        self._semantic_decider = SemanticDecider(llm_client=llm_client)
        self._current_flow: FlowSkeleton | None = None
        self._current_step_index: int = 0

    @property
    def current_flow(self) -> FlowSkeleton | None:
        """当前匹配的流程模板。"""
        return self._current_flow

    @property
    def current_step_index(self) -> int:
        """当前流程步骤索引。"""
        return self._current_step_index

    async def decide(
        self,
        snapshot: PageSnapshot,
        task: str,
        loop_controller: LoopController | None = None,
    ) -> Action:
        """根据页面快照和任务目标，决定下一步最优动作。

        决策流程:
          1. 尝试匹配预定义流程 (Level 1)
          2. 回退到 LLM 语义决策 (Level 2)
          3. 视觉推理 (Level 3, 预留)

        Args:
            snapshot: 当前页面感知快照。
            task: 用户任务描述。
            loop_controller: 循环控制器（可选），用于检查进度。

        Returns:
            决策出的 Action。
        """
        # ── Level 1: 流程匹配 ──
        flow = self._flow_registry.match(snapshot.url, snapshot.page_type)

        if flow is not None:
            # 如果切换到新流程，重置步骤索引
            if self._current_flow is None or self._current_flow.name != flow.name:
                self._current_flow = flow
                self._current_step_index = 0
                logger.info("进入流程: %s (共 %d 步)", flow.name, len(flow.steps))

            action = self._get_next_flow_step(flow)
            if action is not None:
                logger.info("Level 1 (流程): %s → %s → %s",
                            flow.name, action.type, action.target or "")
                return action

            # 流程步骤已耗尽，重置
            logger.info("流程 %s 步骤已耗尽，回退到语义决策", flow.name)
            self._current_flow = None
            self._current_step_index = 0

        # ── Level 2: 语义决策 ──
        logger.info("Level 2 (语义): 使用 LLM 进行决策")
        action = await self._semantic_decider.decide(snapshot, task)

        # 进度评估（如果有 loop_controller）
        if loop_controller is not None:
            progress_ok = loop_controller.evaluate_progress(
                snapshot.to_text_description()
            )
            if not progress_ok:
                logger.warning("进度评估失败，可能陷入循环，建议 NOOP")
                # 不强制覆盖，但降低置信度
                action.confidence = min(action.confidence, 0.3)

        return action

    def _get_next_flow_step(self, flow: FlowSkeleton) -> Action | None:
        """从流程中获取下一步动作。

        Returns:
            下一个 Action，如果步骤已耗尽返回 None。
        """
        if self._current_step_index >= len(flow.steps):
            return None

        step = flow.steps[self._current_step_index]
        self._current_step_index += 1

        return Action(
            type=step.action,
            target=step.target,
            value=step.value,
            reason=f"流程 [{flow.name}] 步骤 {self._current_step_index}/{len(flow.steps)}",
            confidence=0.9,
            params={
                "wait_after": step.wait_after,
                "fallback": step.fallback,
                "condition": step.condition,
            } if (step.fallback or step.condition) else None,
        )

    def reset_flow(self) -> None:
        """重置当前流程状态。"""
        self._current_flow = None
        self._current_step_index = 0
        logger.debug("流程状态已重置")
