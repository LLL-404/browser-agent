"""执行层 — 动作执行引擎、行为模拟与速度控制。

负责将决策层的 Action 转换为实际的浏览器操作，包括：
- SpeedController: 速度模式控制（TURBO/NORMAL/STEALTH）
- BehaviorSimulator: 拟人化行为模拟（贝塞尔鼠标、打字错误、分段滚动）
- ExecutionEngine: 统一调度，协调 BrowserController、速度控制、行为模拟与反爬检测
"""

from __future__ import annotations

import asyncio
import math
import random
from typing import TYPE_CHECKING, Any

from shared.logging_config import get_logger

if TYPE_CHECKING:
    from browser_agent.core.anti_detect import AntiDetectSystem
    from browser_agent.core.browser import BrowserController

logger = get_logger("executor")

# ── 兼容性：Action / PageSnapshot 可能尚未定义实体模块 ──────────
# 在 TYPE_CHECKING 下声明，运行时不强依赖。
if TYPE_CHECKING:
    from dataclasses import dataclass as _dc

    @_dc
    class Action:
        type: str
        target: str | None = None
        value: str | None = None
        params: dict | None = None
        reason: str = ""
        confidence: float = 1.0

    @_dc
    class PageSnapshot:
        url: str
        title: str
        page_type: str = "unknown"
        elements: list[Any] = []
        forms: list[Any] = []
        pagination: Any | None = None
        dialogs: list[Any] = []
        navigation: list[Any] = []
        main_content: str = ""
        content_type: str = "mixed"
        timestamp: float = 0.0
        load_state: str = "load"
        has_captcha: bool = False
        has_block_text: bool = False
        redirect_count: int = 0

        def elements_by_type(self, sem_type: str) -> list[Any]:
            return [e for e in self.elements
                    if getattr(e, "semantic_type", "") == sem_type]

    class RefManager:
        _snapshot: PageSnapshot | None

        def __init__(self) -> None: ...
        def update(self, _snapshot: PageSnapshot) -> None: ...
        def resolve(self, _target: str) -> Any | None: ...


# ========================================================================
#  SpeedController — 速度模式控制
# ========================================================================

class SpeedController:
    """控制执行速度，支持 TURBO / NORMAL / STEALTH 三种模式。

    三种模式的区别：
    - TURBO:  跳过行为模拟，最小延迟，适合批量数据采集
    - NORMAL: 中等延迟，基础行为模拟，适合日常使用
    - STEALTH: 完整拟人化行为，高延迟，适合反爬严格的网站
    """

    MODES: dict[str, dict[str, float]] = {
        "TURBO":   {"nav": 0.5,  "click": 0.1,  "type": 0.05},
        "NORMAL":  {"nav": 1.0,  "click": 0.3,  "type": 0.1},
        "STEALTH": {"nav": 2.0,  "click": 0.8,  "type": 0.15},
    }

    _DEFAULT_DELAY = 0.5

    def __init__(self, mode: str = "NORMAL") -> None:
        self._mode = mode.upper() if mode.upper() in self.MODES else "NORMAL"
        self._risk_level = 0

    # ── 公开接口 ──────────────────────────────────────────────

    def get_delay(self, action_type: str) -> float:
        """返回指定动作类型在当前模式下的延迟（秒）。"""
        return self.MODES.get(self._mode, self.MODES["NORMAL"]).get(
            action_type, self._DEFAULT_DELAY,
        )

    def set_mode(self, mode: str) -> None:
        """切换速度模式。"""
        upper = mode.upper()
        if upper in self.MODES:
            self._mode = upper
            logger.debug("速度模式切换为 %s", upper)
        else:
            logger.warning("未知模式 %s，保持为 %s", mode, self._mode)

    def should_simulate(self) -> bool:
        """当前是否应该启用行为模拟（STEALTH 模式为 True）。"""
        return self._mode == "STEALTH"

    def set_risk_level(self, level: int) -> None:
        """根据反爬风险等级自动调整模式。"""
        self._risk_level = level
        if level >= 3:
            self.set_mode("STEALTH")
        elif level >= 1:
            self.set_mode("NORMAL")
        else:
            self.set_mode("TURBO")

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def risk_level(self) -> int:
        return self._risk_level


# ========================================================================
#  BehaviorSimulator — 拟人化行为模拟
# ========================================================================

class BehaviorSimulator:
    """模拟人类浏览器操作行为。

    提供：
    - 贝塞尔曲线鼠标移动
    - 带随机间隔和打字的键盘输入
    - 分段滚动（带偶尔回滚）
    """

    # 常见打字错误映射（键盘邻键）
    _TYPO_MAP: dict[str, str] = {
        "a": "s", "b": "n", "c": "v", "d": "f", "e": "r",
        "f": "g", "g": "h", "h": "j", "i": "o", "j": "k",
        "k": "l", "l": "k", "m": "n", "n": "m", "o": "p",
        "p": "o", "q": "w", "r": "e", "s": "d", "t": "y",
        "u": "i", "v": "c", "w": "e", "x": "z", "y": "t",
        "z": "x",
    }

    _TYPING_DELAY_BASE = 80   # 基础打字延迟（毫秒）
    _TYPING_DELAY_VAR = 40    # 延迟波动范围（毫秒）
    _TYPO_PROBABILITY = 0.03  # 打字错误概率
    _MOUSE_STEPS = 20         # 贝塞尔曲线采样点数

    # ── 公开模拟方法 ──────────────────────────────────────────

    async def simulate_click(self, page: Any, target: str) -> dict:
        """拟人化点击：先贝塞尔移动鼠标到位，再点击目标元素。"""
        try:
            element = await page.query_selector(target)
            if element is None:
                return {"ok": False, "error": f"元素未找到: {target}"}

            box = await element.bounding_box()
            if box is None:
                # 无法获取位置，退化为普通点击
                await element.click()
                return {"ok": True, "action": "click", "target": target}

            # 在元素内部随机选择目标点
            tx = box["x"] + random.uniform(5, max(5, box["width"] - 5))
            ty = box["y"] + random.uniform(5, max(5, box["height"] - 5))

            # 当前鼠标位置作为起点
            cursor = await page.evaluate(
                "() => ({x: window._cursorX || 0, y: window._cursorY || 0})",
            )
            sx = cursor.get("x", tx)
            sy = cursor.get("y", ty)

            await self._bezier_move(page, sx, sy, tx, ty)

            # 点击前微小停顿
            await asyncio.sleep(self._natural_delay(80, 0.5) / 1000)
            await element.click()

            # 更新记录的鼠标位置
            await page.evaluate(
                f"window._cursorX = {tx}; window._cursorY = {ty};",
            )
            return {"ok": True, "action": "click", "target": target}
        except Exception as e:
            logger.warning("拟人化点击失败: %s", e)
            return {"ok": False, "error": str(e)}

    async def simulate_type(self, page: Any, target: str, text: str) -> dict:
        """拟人化输入：逐字符键入，带随机间隔和偶尔的打字错误。"""
        try:
            if not text:
                return {"ok": True, "action": "type", "target": target, "text": ""}

            element = await page.query_selector(target)
            if element is None:
                return {"ok": False, "error": f"元素未找到: {target}"}

            await element.click()
            await asyncio.sleep(self._natural_delay(200, 0.3) / 1000)

            i = 0
            while i < len(text):
                ch = text[i]

                # 模拟打字错误：有一定概率打出邻键，然后删除重打
                if (random.random() < self._TYPO_PROBABILITY
                        and ch.lower() in self._TYPO_MAP):
                    typo_ch = self._TYPO_MAP[ch.lower()]
                    if ch.isupper():
                        typo_ch = typo_ch.upper()
                    await page.keyboard.type(typo_ch)
                    await asyncio.sleep(self._natural_delay(100, 0.5) / 1000)
                    await page.keyboard.press("Backspace")
                    await asyncio.sleep(self._natural_delay(80, 0.5) / 1000)

                await page.keyboard.type(ch)
                i += 1

                # 逐字符延迟
                delay_ms = self._natural_delay(
                    self._TYPING_DELAY_BASE, self._TYPING_DELAY_VAR / self._TYPING_DELAY_BASE,
                )
                await asyncio.sleep(delay_ms / 1000)

            return {"ok": True, "action": "type", "target": target, "text": text}
        except Exception as e:
            logger.warning("拟人化输入失败: %s", e)
            return {"ok": False, "error": str(e)}

    async def simulate_scroll(self, page: Any, delta_y: int) -> dict:
        """拟人化滚动：分段滚动，中间可能有微小停顿或回滚。"""
        try:
            segments = random.randint(3, 6)
            remaining = delta_y
            for seg in range(segments):
                if remaining == 0:
                    break

                # 每段滚动量（含随机波动）
                if seg == segments - 1:
                    step = remaining
                else:
                    step = int(remaining * random.uniform(0.15, 0.4))
                step = max(-abs(step), min(abs(step), step))  # 保证方向一致
                step = step if abs(step) >= 5 else remaining

                await page.evaluate(f"window.scrollBy(0, {step})")
                remaining -= step

                # 段间延迟
                await asyncio.sleep(self._natural_delay(80, 0.6) / 1000)

                # 偶尔回滚一点（模拟人类阅读时上下扫视）
                if random.random() < 0.15 and abs(remaining) > 20:
                    rollback = int(random.uniform(-30, -10))
                    await page.evaluate(f"window.scrollBy(0, {rollback})")
                    await asyncio.sleep(self._natural_delay(50, 0.5) / 1000)

            return {"ok": True, "action": "scroll", "delta_y": delta_y}
        except Exception as e:
            logger.warning("拟人化滚动失败: %s", e)
            return {"ok": False, "error": str(e)}

    # ── 贝塞尔曲线鼠标移动 ────────────────────────────────────

    async def _bezier_move(
        self, page: Any,
        x1: float, y1: float,
        x2: float, y2: float,
    ) -> None:
        """使用三次贝塞尔曲线移动鼠标，模拟人类轨迹。"""
        # 生成两个随机控制点，形成自然的曲线
        cp1x = x1 + (x2 - x1) * random.uniform(0.2, 0.4) + random.uniform(-30, 30)
        cp1y = y1 + (y2 - y1) * random.uniform(0.2, 0.4) + random.uniform(-30, 30)
        cp2x = x1 + (x2 - x1) * random.uniform(0.6, 0.8) + random.uniform(-30, 30)
        cp2y = y1 + (y2 - y1) * random.uniform(0.6, 0.8) + random.uniform(-30, 30)

        for i in range(self._MOUSE_STEPS):
            t = i / (self._MOUSE_STEPS - 1)
            px = self._bezier_point(t, x1, cp1x, cp2x, x2)
            py = self._bezier_point(t, y1, cp1y, cp2y, y2)
            await page.mouse.move(px, py)
            # 起步和收尾稍慢，中段稍快
            delay = 0.01 + 0.02 * (1 - abs(2 * t - 1))
            await asyncio.sleep(delay)

    @staticmethod
    def _bezier_point(t: float, p0: float, p1: float, p2: float, p3: float) -> float:
        """三次贝塞尔曲线计算：B(t) = (1-t)³P0 + 3(1-t)²tP1 + 3(1-t)t²P2 + t³P3"""
        u = 1 - t
        return u * u * u * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t * t * t * p3

    @staticmethod
    def _natural_delay(base_ms: float, variance: float = 0.3) -> float:
        """生成正态分布延迟，模拟人类反应时间的不确定性。

        使用 Box-Muller 变换生成正态分布随机数，裁切到 [0, 2*base_ms]。
        """
        u1 = random.random()
        u2 = random.random()
        # 标准正态分布
        z = math.sqrt(-2 * math.log(max(u1, 0.0001))) * math.cos(2 * math.pi * u2)
        delay = base_ms + z * base_ms * variance
        return max(0, min(delay, base_ms * 2))


# ========================================================================
#  ExecutionEngine — 动作执行引擎
# ========================================================================

class ExecutionEngine:
    """统一调度 BrowserController、SpeedController、BehaviorSimulator。

    职责：
    1. 解析 Action 中的 target（@ref / 语义类型 / CSS 选择器）
    2. 根据速度模式决定是否启用行为模拟
    3. 分发到对应的 _execute_* 方法
    4. 执行前后附加反爬检测与延迟
    """

    def __init__(
        self,
        browser: BrowserController,
        speed_controller: SpeedController,
        behavior_simulator: BehaviorSimulator,
        ref_manager: RefManager,
        anti_detect_system: AntiDetectSystem | None = None,
    ) -> None:
        self._browser = browser
        self._speed = speed_controller
        self._behavior = behavior_simulator
        self._ref_manager = ref_manager
        self._anti_detect = anti_detect_system

    # ── 主入口 ────────────────────────────────────────────────

    async def execute(self, action: Action, snapshot: PageSnapshot) -> dict:
        """执行一个动作，返回执行结果。"""
        action_type = action.type.lower()
        target = self._resolve_target(action, snapshot)
        value = action.value
        params = action.params or {}
        simulate = self._speed.should_simulate()

        handler_map = {
            "click":       self._execute_click,
            "type":        self._execute_type,
            "scroll":      self._execute_scroll,
            "navigate":    self._execute_navigate,
            "wait":        self._execute_wait,
            "extract":     self._execute_extract,
            "screenshot":  self._execute_screenshot,
            "hover":       self._execute_hover,
            "select":      self._execute_select,
            "press_key":   self._execute_press_key,
            "dialog":      self._execute_dialog,
            "go_back":     self._execute_go_back,
            "switch_tab":  self._execute_switch_tab,
            "done":        lambda *_: {"ok": True, "action": "done"},
            "noop":        lambda *_: {"ok": True, "action": "noop"},
        }

        handler = handler_map.get(action_type)
        if handler is None:
            return {"ok": False, "error": f"未知动作类型: {action_type}"}

        logger.debug(
            "执行动作: %s target=%s simulate=%s mode=%s",
            action_type, target, simulate, self._speed.mode,
        )

        try:
            result = await handler(self._browser, target, value, simulate, params)
        except Exception as e:
            logger.exception("执行 %s 时发生未预期异常", action_type)
            result = {"ok": False, "error": str(e)}

        result.setdefault("action", action_type)
        return result

    # ── target 解析 ───────────────────────────────────────────

    def _resolve_target(self, action: Action, snapshot: PageSnapshot) -> str:
        """将 Action 的 target 字段解析为可用的 CSS 选择器。

        解析优先级：
        1. @ref 编号 → 通过 RefManager 查找
        2. 语义类型 → 通过 PageSnapshot 查找
        3. CSS 选择器 → 直接使用
        """
        target = action.target or ""

        # @ref 引用
        if target.startswith("@"):
            try:
                resolved = self._ref_manager.resolve(target)
                if resolved is not None:
                    selector = getattr(resolved, "selector", "")
                    if selector:
                        return selector
            except Exception:
                pass
            return target

        # 语义类型匹配
        try:
            elements = snapshot.elements_by_type(target)
            if elements:
                selector = getattr(elements[0], "selector", "")
                if selector:
                    return selector
        except Exception:
            pass

        # CSS 选择器直接使用
        return target

    # ── 各动作执行方法 ────────────────────────────────────────

    async def _execute_click(
        self, controller: BrowserController,
        target: str, _value: str | None,
        simulate: bool, _params: dict,
    ) -> dict:
        if not target:
            return {"ok": False, "error": "click 缺少 target"}
        page = controller.page
        if page is None:
            return {"ok": False, "error": "页面未初始化"}

        if simulate:
            result = await self._behavior.simulate_click(page, target)
        else:
            ok = await controller.click_selector(target)
            result = {"ok": ok, "target": target}

        await asyncio.sleep(self._speed.get_delay("click"))
        return result

    async def _execute_type(
        self, controller: BrowserController,
        target: str, value: str | None,
        simulate: bool, _params: dict,
    ) -> dict:
        if not target:
            return {"ok": False, "error": "type 缺少 target"}
        text = value or ""
        page = controller.page
        if page is None:
            return {"ok": False, "error": "页面未初始化"}

        if simulate:
            result = await self._behavior.simulate_type(page, target, text)
        else:
            ok = await controller.fill_input(target, text)
            result = {"ok": ok, "target": target, "text": text}

        await asyncio.sleep(self._speed.get_delay("type"))
        return result

    async def _execute_scroll(
        self, controller: BrowserController,
        _target: str, value: str | None,
        simulate: bool, _params: dict,
    ) -> dict:
        try:
            delta_y = int(value) if value else 300
        except (ValueError, TypeError):
            delta_y = 300

        page = controller.page
        if page is None:
            return {"ok": False, "error": "页面未初始化"}

        if simulate:
            result = await self._behavior.simulate_scroll(page, delta_y)
        else:
            ok = await controller.scroll_page(delta_y)
            result = {"ok": ok, "delta_y": delta_y}

        return result

    async def _execute_navigate(
        self, controller: BrowserController,
        target: str, _value: str | None,
        _simulate: bool, _params: dict,
    ) -> dict:
        url = target or _value or ""
        if not url:
            return {"ok": False, "error": "navigate 缺少 URL"}

        ok = await controller.navigate_to(url)
        await asyncio.sleep(self._speed.get_delay("nav"))
        return {
            "ok": ok,
            "url": url,
            "current_url": await controller.get_current_url() if ok else "",
        }

    async def _execute_wait(
        self, _controller: BrowserController,
        _target: str, value: str | None,
        _simulate: bool, _params: dict,
    ) -> dict:
        try:
            seconds = float(value) if value else 1.0
        except (ValueError, TypeError):
            seconds = 1.0

        seconds = max(0.1, min(seconds, 60.0))  # 限制在 0.1~60 秒
        await asyncio.sleep(seconds)
        return {"ok": True, "waited": seconds}

    async def _execute_extract(
        self, controller: BrowserController,
        target: str, _value: str | None,
        _simulate: bool, _params: dict,
    ) -> dict:
        if not target:
            return {"ok": False, "error": "extract 缺少 target"}

        page = controller.page
        if page is None:
            return {"ok": False, "error": "页面未初始化"}

        try:
            elements = await page.query_selector_all(target)
            results = []
            for el in elements[:50]:  # 限制提取数量
                text = ""
                try:
                    text = await el.inner_text()
                except Exception:
                    pass
                href = ""
                try:
                    href = await el.get_attribute("href") or ""
                except Exception:
                    pass
                results.append({"text": text.strip(), "href": href})
            return {"ok": True, "count": len(results), "results": results}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _execute_screenshot(
        self, controller: BrowserController,
        target: str, _value: str | None,
        _simulate: bool, _params: dict,
    ) -> dict:
        path = target or "screenshot.png"
        ok = await controller.take_screenshot(path)
        return {"ok": ok, "path": path}

    async def _execute_hover(
        self, controller: BrowserController,
        target: str, _value: str | None,
        _simulate: bool, _params: dict,
    ) -> dict:
        if not target:
            return {"ok": False, "error": "hover 缺少 target"}
        ok = await controller.hover_selector(target)
        return {"ok": ok, "target": target}

    async def _execute_select(
        self, controller: BrowserController,
        target: str, value: str | None,
        _simulate: bool, _params: dict,
    ) -> dict:
        if not target:
            return {"ok": False, "error": "select 缺少 target"}
        if not value:
            return {"ok": False, "error": "select 缺少 value"}
        ok = await controller.select_option_value(target, value)
        return {"ok": ok, "target": target, "value": value}

    async def _execute_press_key(
        self, controller: BrowserController,
        _target: str, value: str | None,
        _simulate: bool, _params: dict,
    ) -> dict:
        key = value or "Enter"
        ok = await controller.press_key(key)
        return {"ok": ok, "key": key}

    async def _execute_dialog(
        self, controller: BrowserController,
        _target: str, _value: str | None,
        _simulate: bool, params: dict,
    ) -> dict:
        accept = params.get("accept", True)
        prompt_text = params.get("prompt_text", "")
        ok = await controller.handle_dialog(accept=accept, prompt_text=prompt_text)
        return {"ok": ok, "accepted": accept}

    async def _execute_go_back(
        self, controller: BrowserController,
        _target: str, _value: str | None,
        _simulate: bool, _params: dict,
    ) -> dict:
        ok = await controller.go_back()
        return {"ok": ok}

    async def _execute_switch_tab(
        self, controller: BrowserController,
        target: str, _value: str | None,
        _simulate: bool, _params: dict,
    ) -> dict:
        """切换标签页。target 为目标标签页索引（0-based）或 URL 片段。"""
        pages = controller.get_pages()
        if not pages:
            return {"ok": False, "error": "没有可用的标签页"}

        try:
            # 尝试按索引切换
            idx = int(target)
            if 0 <= idx < len(pages):
                page = pages[idx]
                await page.bring_to_front()
                return {"ok": True, "tab_index": idx, "url": page.url}
            return {"ok": False, "error": f"标签页索引越界: {idx}/{len(pages)}"}
        except ValueError:
            # 按 URL 片段模糊匹配
            for i, page in enumerate(pages):
                if target in page.url:
                    await page.bring_to_front()
                    return {"ok": True, "tab_index": i, "url": page.url}
            return {"ok": False, "error": f"未找到匹配的标签页: {target}"}
