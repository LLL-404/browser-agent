"""通用浏览器自动化 Agent — 提供面向 MCP 的高层操作。

包装 BrowserController，所有方法返回 dict 以便 JSON 序列化。
IDE 内置 AI 通过 MCP 调用这些方法，实现"描述 → 执行"的自动化流程。
"""

from __future__ import annotations

import asyncio
import json as _json
from typing import TYPE_CHECKING, Any

import aiofiles

from browser_agent.core.browser import BrowserController
from browser_agent.core.decider import (
    ActionType,
    DecisionEngine,
    ErrorRecovery,
    FlowRegistry,
    LoopController,
)
from browser_agent.core.executor import (
    BehaviorSimulator,
    ExecutionEngine,
    SpeedController,
)
from browser_agent.core.perceiver import PagePerceiver
from browser_agent.core.ref_manager import RefManager
from shared.delay import delay
from shared.error_handler import format_error_for_mcp
from shared.exceptions import BrowserAutomationError
from shared.logging_config import get_logger

if TYPE_CHECKING:
    from browser_agent.core.perceiver import PageSnapshot

logger = get_logger("agent")

SESSION_DIR = "./sessions"


class BrowserAgent:
    """通用浏览器 Agent — 浏览器控制 + 页面交互 + 数据提取的统一入口。"""

    def __init__(self, controller: BrowserController | None = None):
        self._ctrl = controller or BrowserController()
        self._step_count = 0
        self._refs: list[dict] = []

    # ── 生命周期 ──────────────────────────────────────────────

    @property
    def ctrl(self) -> BrowserController:
        """返回底层浏览器控制器实例。"""
        return self._ctrl

    @property
    def is_running(self) -> bool:
        """返回浏览器是否正在运行。"""
        return self._ctrl.is_running

    async def open(self, headless: bool = False,
                   url: str = "about:blank") -> dict[str, Any]:
        """启动浏览器并导航到指定 URL。"""
        if not self._ctrl.is_running:
            started = await self._ctrl.start(headless=headless)
            if not started:
                return {"ok": False, "error": "浏览器启动失败"}
        nav = await self._ctrl.navigate_to(url)
        await delay("page_ready")
        page = {
            "ok": nav,
            "url": await self._ctrl.get_current_url(),
            "title": await self._ctrl.get_page_title(),
            "engine": self._ctrl.engine,
        }
        return page

    async def close(self) -> dict[str, Any]:
        """关闭浏览器。"""
        ok = await self._ctrl.stop()
        return {"ok": ok, "message": "浏览器已关闭" if ok else "关闭失败"}

    async def navigate(self, url: str) -> dict[str, Any]:
        """导航到指定 URL。"""
        self._step_count += 1
        try:
            ok = await self._ctrl.navigate_to(url)
            self._refs = []
            await delay("navigation")
            return {
                "ok": ok,
                "url": await self._ctrl.get_current_url(),
                "title": await self._ctrl.get_page_title(),
                "step": self._step_count,
            }
        except BrowserAutomationError as e:
            error = format_error_for_mcp(e)
            error["step"] = self._step_count
            error["ok"] = False
            return error
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("导航时发生未预期异常: %s", e)
            return {
                "ok": False,
                "error": str(e),
                "step": self._step_count,
            }

    # ── Ref 系统 ──────────────────────────────────────────────

    def _resolve_ref(self, target: str) -> str | None:
        if not target.startswith("@"):
            return target
        for r in self._refs:
            if r["ref"] == target:
                return r["selector"]
        return None

    def _render_elements_text(self) -> str:
        if not self._refs:
            return "（无可交互元素）"
        lines = []
        for r in self._refs:
            parts = [r["ref"]]
            parts.append(f"[{r['tag']}]")
            if r.get("text"):
                text = r["text"].replace("\n", " ").strip()
                if len(text) > 60:
                    text = text[:60] + "..."
                parts.append(f'"{text}"')
            if r.get("placeholder"):
                parts.append(f"placeholder={r['placeholder']}")
            if r.get("aria_label"):
                parts.append(f"aria={r['aria_label']}")
            lines.append("  ".join(parts))
        return "\n".join(lines)

    # ── 页面交互 ──────────────────────────────────────────────

    async def click(self, target: str,
                    mode: str = "selector") -> dict[str, Any]:
        """点击元素。支持 @e1 ref 或 CSS 选择器。"""
        self._step_count += 1
        if mode == "text":
            result = await self._ctrl.click_by_text(target)
            result["step"] = self._step_count
            return result
        selector = self._resolve_ref(target) or target
        ok = await self._ctrl.click_selector(selector)
        return {"ok": ok, "selector": selector, "step": self._step_count}

    async def type_text(self, selector: str,
                        text: str, _clear: bool = True) -> dict[str, Any]:
        """在输入框中输入文本。支持 @e1 ref 或 CSS 选择器。"""
        self._step_count += 1
        sel = self._resolve_ref(selector) or selector
        ok = await self._ctrl.fill_input(sel, text)
        return {"ok": ok, "selector": sel, "text": text,
                "step": self._step_count}

    async def press(self, key: str = "Enter") -> dict[str, Any]:
        """模拟按键。"""
        self._step_count += 1
        ok = await self._ctrl.press_key(key)
        return {"ok": ok, "key": key, "step": self._step_count}

    async def scroll(self, delta: int = 500) -> dict[str, Any]:
        """滚动页面。"""
        self._step_count += 1
        ok = await self._ctrl.scroll_page(delta)
        return {"ok": ok, "delta": delta, "step": self._step_count}

    async def select(self, selector: str,
                     value: str) -> dict[str, Any]:
        """选择下拉框选项。支持 @e1 ref 或 CSS 选择器。"""
        self._step_count += 1
        sel = self._resolve_ref(selector) or selector
        ok = await self._ctrl.select_option_value(sel, value)
        return {"ok": ok, "selector": sel, "value": value,
                "step": self._step_count}

    # ── 语义定位 ──────────────────────────────────────────────

    async def find(self, target_type: str = "text",
                   target: str = "",
                   action: str = "click",
                   value: str = "") -> dict[str, Any]:
        """通过语义定位元素并执行操作。

        target_type: text / label / placeholder / role / testid
        target: 定位值
        action: click / fill / select
        value: 填充值（仅在 action=fill 时需要）
        """
        self._step_count += 1
        if not self._ctrl.page:
            return {"ok": False, "error": "页面未初始化", "step": self._step_count}

        page = self._ctrl.page
        try:
            if target_type == "text":
                locator = page.get_by_text(target, exact=False)
            elif target_type == "label":
                locator = page.get_by_label(target, exact=False)
            elif target_type == "placeholder":
                locator = page.get_by_placeholder(target)
            elif target_type == "role":
                parts = target.split(",")
                role = parts[0].strip()
                name = parts[1].strip() if len(parts) > 1 else ""
                locator = page.get_by_role(role, name=name)
            elif target_type == "testid":
                locator = page.get_by_test_id(target)
            else:
                return {"ok": False, "error": f"未知定位方式: {target_type}",
                        "step": self._step_count}

            count = await locator.count()
            if count == 0:
                return {"ok": False, "error": f"未找到元素 ({target_type}={target})",
                        "step": self._step_count}

            if action == "click":
                await locator.first.click()
                return {"ok": True, "action": "click",
                        "target_type": target_type, "target": target,
                        "step": self._step_count}
            if action == "fill":
                await locator.first.fill(value)
                return {"ok": True, "action": "fill",
                        "target_type": target_type, "target": target,
                        "value": value, "step": self._step_count}
            return {"ok": False, "error": f"未知操作: {action}",
                    "step": self._step_count}
        except Exception as e:  # pylint: disable=broad-exception-caught
            return {"ok": False, "error": str(e), "step": self._step_count}

    # ── 等待 ──────────────────────────────────────────────────

    async def wait(self, selector: str,
                   timeout: int = 10000) -> dict[str, Any]:
        """等待指定元素出现。支持 @e1 ref 或 CSS 选择器。"""
        sel = self._resolve_ref(selector) or selector
        result = await self._ctrl.wait_for_element(sel, timeout)
        result["step"] = self._step_count
        return result

    async def wait_load(self, ms: int = 1500) -> dict[str, Any]:
        """等待页面加载一段时间（毫秒）。"""
        await asyncio.sleep(ms / 1000)
        return {"ok": True, "waited_ms": ms, "step": self._step_count}

    # ── 页面状态 ──────────────────────────────────────────────

    async def snapshot(self,
                       max_length: int = 3000,
                       mode: str = "auto") -> dict[str, Any]:
        """获取当前页面结构快照。

        mode: "auto" — 优先无障碍树，回退到 DOM
              "accessibility" — 仅无障碍树
              "dom" — 仅 DOM + 可交互元素（旧模式）
        """
        url = await self._ctrl.get_current_url()
        title = await self._ctrl.get_page_title()

        if mode in ("auto", "accessibility"):
            a11y = await self._ctrl.get_accessibility_snapshot()
            if a11y and mode == "accessibility":
                return {"url": url, "title": title, "accessibility": a11y, "mode": "accessibility"}

        elements = await self._ctrl.get_interactive_elements()
        self._refs = elements
        dom = await self._ctrl.get_dom_structure()
        text = await self._ctrl.get_page_text(max_length)
        result = {
            "url": url,
            "title": title,
            "elements": self._render_elements_text(),
            "dom": dom,
            "text": text,
            "mode": "dom",
        }
        if a11y and mode == "auto":
            result["accessibility"] = a11y
        return result

    async def html(self, max_len: int = 8000) -> dict[str, Any]:
        """获取当前页面 HTML。"""
        return {"ok": True, "html": await self._ctrl.get_page_html(max_len)}

    async def text(self, max_len: int = 3000) -> dict[str, Any]:
        """获取当前页面文本。"""
        return {"ok": True, "text": await self._ctrl.get_page_text(max_len)}

    async def url(self) -> dict[str, Any]:
        """获取当前页面 URL 和标题。"""
        return {
            "ok": True,
            "url": await self._ctrl.get_current_url(),
            "title": await self._ctrl.get_page_title(),
        }

    async def screenshot(self, full_page: bool = False) -> dict[str, Any]:
        """获取当前页面截图（base64）。"""
        import base64  # pylint: disable=import-outside-toplevel
        buf = await self._ctrl.get_page_screenshot_bytes(full_page)
        if buf is None:
            return {"ok": False, "error": "截图失败"}
        b64 = base64.b64encode(buf).decode("utf-8")
        return {"ok": True, "format": "png", "base64": b64,
                "data_uri": f"data:image/png;base64,{b64}"}

    # ── Session 持久化 ────────────────────────────────────────

    async def save_session(self, name: str = "default") -> dict[str, Any]:
        """保存当前会话的 cookies 和 localStorage。"""
        import os  # pylint: disable=import-outside-toplevel
        cookies = await self._ctrl.save_cookies()
        ls_str = await self._ctrl.save_local_storage()
        data = {
            "cookies": cookies,
            "local_storage": ls_str,
            "url": await self._ctrl.get_current_url(),
        }
        os.makedirs(SESSION_DIR, exist_ok=True)
        path = f"{SESSION_DIR}/{name}.json"
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(_json.dumps(data, ensure_ascii=False, indent=2))
        return {"ok": True, "path": path, "cookies_count": len(cookies),
                "step": self._step_count}

    async def load_session(self, name: str = "default") -> dict[str, Any]:
        """恢复指定会话的 cookies 和 localStorage。"""
        import os  # pylint: disable=import-outside-toplevel
        path = f"{SESSION_DIR}/{name}.json"
        if not os.path.exists(path):
            return {"ok": False, "error": f"会话文件不存在: {path}",
                    "step": self._step_count}
        try:
            async with aiofiles.open(path, encoding="utf-8") as f:
                content = await f.read()
            data = _json.loads(content)
            if data.get("cookies"):
                await self._ctrl.load_cookies(data["cookies"])
            if data.get("local_storage"):
                await self._ctrl.load_local_storage(data["local_storage"])
            url = data.get("url", "")
            if url:
                await self._ctrl.navigate_to(url)
                await delay("session_restore")
            return {"ok": True, "url": url,
                    "cookies_restored": len(data.get("cookies", [])),
                    "step": self._step_count}
        except (OSError, _json.JSONDecodeError) as e:
            return {"ok": False, "error": str(e), "step": self._step_count}

    async def list_sessions(self) -> dict[str, Any]:
        """列出所有已保存的会话。"""
        import glob as _glob  # pylint: disable=import-outside-toplevel
        import os  # pylint: disable=import-outside-toplevel
        files = _glob.glob(f"{SESSION_DIR}/*.json")
        sessions = []
        for f in files:
            name = os.path.splitext(os.path.basename(f))[0]
            mtime = os.path.getmtime(f)
            try:
                async with aiofiles.open(f, encoding="utf-8") as _f:
                    content = await _f.read()
                data = _json.loads(content)
                url = data.get("url", "")
                cc = len(data.get("cookies", []))
            except (OSError, _json.JSONDecodeError):
                url = ""
                cc = 0
            sessions.append({
                "name": name,
                "url": url,
                "cookies": cc,
                "modified": mtime,
            })
        sessions.sort(key=lambda s: s["modified"], reverse=True)
        return {"sessions": sessions, "total": len(sessions)}

    # ── 数据提取 ──────────────────────────────────────────────

    async def extract(self, selector: str,
                      fields: list[str] | None = None,
                      limit: int = 20) -> dict[str, Any]:
        """批量提取所有匹配元素的内容。"""
        self._step_count += 1
        if fields is None:
            fields = ["innerText"]

        js = """
        ([sel, lim, flds]) => {
          const els = document.querySelectorAll(sel);
          const results = [];
          const limitNum = Math.min(els.length, lim);
          for (let i = 0; i < limitNum; i++) {
            const el = els[i];
            const row = flds.map(f => {
              if (f === 'innerText' || f === 'textContent') return (el[f] || '').trim();
              if (f === 'href') return el.href || el.getAttribute('href') || '';
              if (f === 'src') return el.src || el.getAttribute('src') || '';
              if (f === 'outerHTML') return el.outerHTML || '';
              return el.getAttribute(f) || el[f] || '';
            });
            results.push(row);
          }
          return { total: els.length, returned: limitNum, results: results, fields: flds };
        }
        """
        result = await self._ctrl.execute_js(js, [selector, limit, fields])
        data = result.get("result", {"error": "提取失败"}) if isinstance(result, dict) else {}
        if isinstance(data, dict):
            data["step"] = self._step_count
        return data

    async def extract_table(self, rows_selector: str,
                            columns: dict[str, str],
                            limit: int = 30) -> dict[str, Any]:
        """从表格/列表结构结构化提取数据。"""
        self._step_count += 1
        js = """
        ([sel, lim, cols]) => {
          const rows = document.querySelectorAll(sel);
          const results = [];
          const limitNum = Math.min(rows.length, lim);
          for (let i = 0; i < limitNum; i++) {
            const rowEl = rows[i];
            const item = {};
            for (const [name, colSel] of Object.entries(cols)) {
              const cell = rowEl.querySelector(colSel);
              item[name] = cell ? (cell.innerText || cell.textContent || '').trim() : '';
            }
            results.push(item);
          }
          return { total: rows.length, returned: limitNum, results: results };
        }
        """
        result = await self._ctrl.execute_js(js, [rows_selector, limit, columns])
        data = result.get("result", {}) if isinstance(result, dict) else {}
        if isinstance(data, dict):
            data["step"] = self._step_count
        return data

    # ── JS 执行 ───────────────────────────────────────────────

    async def execute_js(self, expression: str) -> dict[str, Any]:
        """在页面中执行 JavaScript 表达式。"""
        self._step_count += 1
        result = await self._ctrl.execute_js(expression)
        if isinstance(result, dict):
            result["step"] = self._step_count
        return result

    # ── 智能批量 ──────────────────────────────────────────────

    async def loop_extract(self, page_count: int,
                           row_selector: str,
                           columns: dict[str, str],
                           next_btn: str = "") -> dict[str, Any]:
        """翻页批量提取（适用于搜索结果列表）。"""
        all_rows = []
        actual_pages = 0
        for pg in range(page_count):
            actual_pages = pg + 1
            data = await self.extract_table(row_selector, columns, limit=50)
            rows = data.get("results", [])
            if rows:
                for r in rows:
                    r["_page"] = actual_pages
                all_rows.extend(rows)
            if pg < page_count - 1 and next_btn:
                clicked = await self._ctrl.click_selector(next_btn)
                if not clicked:
                    break
                await delay("pagination")
            else:
                break
        return {"pages": actual_pages, "total_rows": len(all_rows),
                "results": all_rows, "step": self._step_count}


# =============================================================================
# BrowsingAgent — 新一代浏览 Agent，整合感知/决策/执行分层架构
# =============================================================================


class BrowsingAgent:
    """新一代浏览 Agent — 感知→决策→执行 三层架构。

    整合了 PagePerceiver、DecisionEngine、ExecutionEngine 等模块，
    同时保持与旧版 BrowserAgent 的 MCP 接口兼容。
    """

    def __init__(
        self,
        controller: BrowserController | None = None,
        llm_client: Any = None,
        max_steps: int = 50,
        timeout_secs: float = 300.0,
    ) -> None:
        # ── 核心组件 ──
        self._ctrl = controller or BrowserController()
        self._perceiver = PagePerceiver()
        self._ref_manager = RefManager()

        # 决策层
        flow_registry = FlowRegistry()
        self._decider = DecisionEngine(
            flow_registry=flow_registry,
            llm_client=llm_client,
        )

        # 执行层
        speed_ctrl = SpeedController()
        behavior_sim = BehaviorSimulator()
        self._executor = ExecutionEngine(
            browser=self._ctrl,
            speed_controller=speed_ctrl,
            behavior_simulator=behavior_sim,
            ref_manager=self._ref_manager,
        )

        # 循环控制与错误恢复
        self._loop_controller = LoopController(
            max_steps=max_steps, timeout_secs=timeout_secs,
        )
        self._error_recovery = ErrorRecovery()

        # ── 向后兼容属性 ──
        self._step_count = 0
        self._refs: list[dict] = []
        self._max_steps = max_steps

    # ── 生命周期 ──────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        """返回浏览器是否正在运行。"""
        return self._ctrl.is_running

    # ── 核心循环 ──────────────────────────────────────────────

    async def run(
        self,
        task: str,
        url: str | None = None,
        headless: bool = False,
    ) -> dict[str, Any]:
        """执行浏览任务的主循环：感知 → 决策 → 执行 → 循环控制。

        Args:
            task: 任务描述。
            url: 起始 URL（可选）。
            headless: 是否以无头模式启动浏览器。

        Returns:
            包含 ok, task, steps, url, title, summary, results 的结果字典。
        """
        # 1. 启动浏览器
        if not self._ctrl.is_running:
            started = await self._ctrl.start(headless=headless)
            if not started:
                return {
                    "ok": False, "task": task, "steps": 0,
                    "error": "浏览器启动失败",
                }

        # 2. 导航到起始 URL
        if url:
            await self._ctrl.navigate_to(url)
            await delay("navigation")

        # 3. 主循环
        steps = 0
        results: list[dict[str, Any]] = []
        _last_snapshot: PageSnapshot | None = None

        while steps < self._max_steps:
            # a. 感知 — 获取页面快照
            page = self._ctrl.page
            if page is None:
                await asyncio.sleep(0.5)
                continue

            snapshot = await self._perceiver.perceive(page)
            self._ref_manager.update(snapshot)
            _last_snapshot = snapshot

            # b. 决策 — 决定下一步动作
            action = await self._decider.decide(
                snapshot, task, self._loop_controller,
            )

            # c. 执行 — 执行动作
            try:
                exec_result = await self._executor.execute(action, snapshot)
                results.append(exec_result)
                steps += 1
            except Exception as e:  # pylint: disable=broad-exception-caught
                # 执行失败时使用错误恢复策略
                recovery_action = await self._error_recovery.handle_failure(
                    action, str(e), snapshot,
                    self._decider.current_flow,
                )
                if recovery_action.type == ActionType.NOOP:
                    break
                try:
                    exec_result = await self._executor.execute(
                        recovery_action, snapshot,
                    )
                    results.append(exec_result)
                    steps += 1
                except Exception:  # pylint: disable=broad-exception-caught
                    break

            # d. 如果动作是 DONE，退出循环
            if action.type == ActionType.DONE:
                break

            # e. 循环控制 — 检查是否应继续
            should_cont, reason = self._loop_controller.should_continue(action)
            if not should_cont:
                if reason:
                    results.append({"info": reason})
                break

        # 4. 构建返回结果
        current_url = ""
        current_title = ""
        try:
            current_url = await self._ctrl.get_current_url()
            current_title = await self._ctrl.get_page_title()
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        return {
            "ok": True,
            "task": task,
            "steps": steps,
            "url": current_url,
            "title": current_title,
            "summary": f"用 {steps} 步完成任务",
            "results": results,
        }

    async def browse(
        self,
        task: str,
        url: str | None = None,
        headless: bool = False,
    ) -> dict[str, Any]:
        """run() 的别名，语义更清晰的浏览入口。"""
        return await self.run(task=task, url=url, headless=headless)

    async def get_snapshot(self) -> PageSnapshot | None:
        """获取当前页面的感知快照。"""
        page = self._ctrl.page
        if page is None:
            return None
        return await self._perceiver.perceive(page)

    # ── 向后兼容：Ref 系统 ────────────────────────────────────

    def _resolve_ref(self, target: str) -> str | None:
        """解析 @ref 引用，返回实际 CSS 选择器。"""
        if not target.startswith("@"):
            return target
        for r in self._refs:
            if r["ref"] == target:
                return r["selector"]
        return None

    def _render_elements_text(self) -> str:
        """将可交互元素列表渲染为可读文本。"""
        if not self._refs:
            return "（无可交互元素）"
        lines = []
        for r in self._refs:
            parts = [r["ref"]]
            parts.append(f"[{r['tag']}]")
            if r.get("text"):
                text = r["text"].replace("\n", " ").strip()
                if len(text) > 60:
                    text = text[:60] + "..."
                parts.append(f'"{text}"')
            if r.get("placeholder"):
                parts.append(f"placeholder={r['placeholder']}")
            if r.get("aria_label"):
                parts.append(f"aria={r['aria_label']}")
            lines.append("  ".join(parts))
        return "\n".join(lines)

    # ── 向后兼容：生命周期 ────────────────────────────────────

    async def open(
        self, headless: bool = False, url: str = "about:blank",
    ) -> dict[str, Any]:
        """启动浏览器并导航到指定 URL。"""
        if not self._ctrl.is_running:
            started = await self._ctrl.start(headless=headless)
            if not started:
                return {"ok": False, "error": "浏览器启动失败"}
        nav = await self._ctrl.navigate_to(url)
        await delay("page_ready")
        return {
            "ok": nav,
            "url": await self._ctrl.get_current_url(),
            "title": await self._ctrl.get_page_title(),
            "engine": self._ctrl.engine,
        }

    async def close(self) -> dict[str, Any]:
        """关闭浏览器。"""
        ok = await self._ctrl.stop()
        return {"ok": ok, "message": "浏览器已关闭" if ok else "关闭失败"}

    # ── 向后兼容：导航 ────────────────────────────────────────

    async def navigate(self, url: str) -> dict[str, Any]:
        """导航到指定 URL。"""
        self._step_count += 1
        try:
            ok = await self._ctrl.navigate_to(url)
            self._refs = []
            await delay("navigation")
            return {
                "ok": ok,
                "url": await self._ctrl.get_current_url(),
                "title": await self._ctrl.get_page_title(),
                "step": self._step_count,
            }
        except BrowserAutomationError as e:
            error = format_error_for_mcp(e)
            error["step"] = self._step_count
            error["ok"] = False
            return error
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("导航时发生未预期异常: %s", e)
            return {"ok": False, "error": str(e), "step": self._step_count}

    # ── 向后兼容：页面交互 ────────────────────────────────────

    async def click(
        self, target: str, mode: str = "selector",
    ) -> dict[str, Any]:
        """点击元素。支持 @e1 ref 或 CSS 选择器。"""
        self._step_count += 1
        if mode == "text":
            result = await self._ctrl.click_by_text(target)
            result["step"] = self._step_count
            return result
        selector = self._resolve_ref(target) or target
        ok = await self._ctrl.click_selector(selector)
        return {"ok": ok, "selector": selector, "step": self._step_count}

    async def type_text(
        self, selector: str, text: str, _clear: bool = True,
    ) -> dict[str, Any]:
        """在输入框中输入文本。支持 @e1 ref 或 CSS 选择器。"""
        self._step_count += 1
        sel = self._resolve_ref(selector) or selector
        ok = await self._ctrl.fill_input(sel, text)
        return {
            "ok": ok, "selector": sel, "text": text,
            "step": self._step_count,
        }

    async def press(self, key: str = "Enter") -> dict[str, Any]:
        """模拟按键。"""
        self._step_count += 1
        ok = await self._ctrl.press_key(key)
        return {"ok": ok, "key": key, "step": self._step_count}

    async def scroll(self, delta: int = 500) -> dict[str, Any]:
        """滚动页面。"""
        self._step_count += 1
        ok = await self._ctrl.scroll_page(delta)
        return {"ok": ok, "delta": delta, "step": self._step_count}

    async def select(
        self, selector: str, value: str,
    ) -> dict[str, Any]:
        """选择下拉框选项。支持 @e1 ref 或 CSS 选择器。"""
        self._step_count += 1
        sel = self._resolve_ref(selector) or selector
        ok = await self._ctrl.select_option_value(sel, value)
        return {
            "ok": ok, "selector": sel, "value": value,
            "step": self._step_count,
        }

    # ── 向后兼容：语义定位 ────────────────────────────────────

    async def find(
        self,
        target_type: str = "text",
        target: str = "",
        action: str = "click",
        value: str = "",
    ) -> dict[str, Any]:
        """通过语义定位元素并执行操作。"""
        self._step_count += 1
        if not self._ctrl.page:
            return {"ok": False, "error": "页面未初始化", "step": self._step_count}

        page = self._ctrl.page
        try:
            if target_type == "text":
                locator = page.get_by_text(target, exact=False)
            elif target_type == "label":
                locator = page.get_by_label(target, exact=False)
            elif target_type == "placeholder":
                locator = page.get_by_placeholder(target)
            elif target_type == "role":
                parts = target.split(",")
                role = parts[0].strip()
                name = parts[1].strip() if len(parts) > 1 else ""
                locator = page.get_by_role(role, name=name)
            elif target_type == "testid":
                locator = page.get_by_test_id(target)
            else:
                return {
                    "ok": False, "error": f"未知定位方式: {target_type}",
                    "step": self._step_count,
                }

            count = await locator.count()
            if count == 0:
                return {
                    "ok": False,
                    "error": f"未找到元素 ({target_type}={target})",
                    "step": self._step_count,
                }

            if action == "click":
                await locator.first.click()
                return {
                    "ok": True, "action": "click",
                    "target_type": target_type, "target": target,
                    "step": self._step_count,
                }
            if action == "fill":
                await locator.first.fill(value)
                return {
                    "ok": True, "action": "fill",
                    "target_type": target_type, "target": target,
                    "value": value, "step": self._step_count,
                }
            return {
                "ok": False, "error": f"未知操作: {action}",
                "step": self._step_count,
            }
        except Exception as e:  # pylint: disable=broad-exception-caught
            return {"ok": False, "error": str(e), "step": self._step_count}

    # ── 向后兼容：等待 ────────────────────────────────────────

    async def wait(
        self, selector: str, timeout: int = 10000,
    ) -> dict[str, Any]:
        """等待指定元素出现。支持 @e1 ref 或 CSS 选择器。"""
        sel = self._resolve_ref(selector) or selector
        result = await self._ctrl.wait_for_element(sel, timeout)
        result["step"] = self._step_count
        return result

    async def wait_load(self, ms: int = 1500) -> dict[str, Any]:
        """等待页面加载一段时间（毫秒）。"""
        await asyncio.sleep(ms / 1000)
        return {"ok": True, "waited_ms": ms, "step": self._step_count}

    # ── 向后兼容：页面状态 ────────────────────────────────────

    async def snapshot(
        self, max_length: int = 3000, mode: str = "auto",
    ) -> dict[str, Any]:
        """获取当前页面结构快照。"""
        url = await self._ctrl.get_current_url()
        title = await self._ctrl.get_page_title()

        if mode in ("auto", "accessibility"):
            a11y = await self._ctrl.get_accessibility_snapshot()
            if a11y and mode == "accessibility":
                return {
                    "url": url, "title": title,
                    "accessibility": a11y, "mode": "accessibility",
                }

        elements = await self._ctrl.get_interactive_elements()
        self._refs = elements
        dom = await self._ctrl.get_dom_structure()
        text = await self._ctrl.get_page_text(max_length)
        result: dict[str, Any] = {
            "url": url,
            "title": title,
            "elements": self._render_elements_text(),
            "dom": dom,
            "text": text,
            "mode": "dom",
        }
        if a11y and mode == "auto":
            result["accessibility"] = a11y
        return result

    async def html(self, max_len: int = 8000) -> dict[str, Any]:
        """获取当前页面 HTML。"""
        return {"ok": True, "html": await self._ctrl.get_page_html(max_len)}

    async def text(self, max_len: int = 3000) -> dict[str, Any]:
        """获取当前页面文本。"""
        return {"ok": True, "text": await self._ctrl.get_page_text(max_len)}

    async def url(self) -> dict[str, Any]:
        """获取当前页面 URL 和标题。"""
        return {
            "ok": True,
            "url": await self._ctrl.get_current_url(),
            "title": await self._ctrl.get_page_title(),
        }

    async def screenshot(self, full_page: bool = False) -> dict[str, Any]:
        """获取当前页面截图（base64）。"""
        import base64  # pylint: disable=import-outside-toplevel
        buf = await self._ctrl.get_page_screenshot_bytes(full_page)
        if buf is None:
            return {"ok": False, "error": "截图失败"}
        b64 = base64.b64encode(buf).decode("utf-8")
        return {
            "ok": True, "format": "png", "base64": b64,
            "data_uri": f"data:image/png;base64,{b64}",
        }

    # ── 向后兼容：Session 持久化 ──────────────────────────────

    async def save_session(self, name: str = "default") -> dict[str, Any]:
        """保存当前会话的 cookies 和 localStorage。"""
        import os  # pylint: disable=import-outside-toplevel
        cookies = await self._ctrl.save_cookies()
        ls_str = await self._ctrl.save_local_storage()
        data = {
            "cookies": cookies,
            "local_storage": ls_str,
            "url": await self._ctrl.get_current_url(),
        }
        os.makedirs(SESSION_DIR, exist_ok=True)
        path = f"{SESSION_DIR}/{name}.json"
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(_json.dumps(data, ensure_ascii=False, indent=2))
        return {
            "ok": True, "path": path,
            "cookies_count": len(cookies), "step": self._step_count,
        }

    async def load_session(self, name: str = "default") -> dict[str, Any]:
        """恢复指定会话的 cookies 和 localStorage。"""
        import os  # pylint: disable=import-outside-toplevel
        path = f"{SESSION_DIR}/{name}.json"
        if not os.path.exists(path):
            return {
                "ok": False, "error": f"会话文件不存在: {path}",
                "step": self._step_count,
            }
        try:
            async with aiofiles.open(path, encoding="utf-8") as f:
                content = await f.read()
            data = _json.loads(content)
            if data.get("cookies"):
                await self._ctrl.load_cookies(data["cookies"])
            if data.get("local_storage"):
                await self._ctrl.load_local_storage(data["local_storage"])
            url = data.get("url", "")
            if url:
                await self._ctrl.navigate_to(url)
                await delay("session_restore")
            return {
                "ok": True, "url": url,
                "cookies_restored": len(data.get("cookies", [])),
                "step": self._step_count,
            }
        except (OSError, _json.JSONDecodeError) as e:
            return {"ok": False, "error": str(e), "step": self._step_count}

    async def list_sessions(self) -> dict[str, Any]:
        """列出所有已保存的会话。"""
        import glob as _glob  # pylint: disable=import-outside-toplevel
        import os  # pylint: disable=import-outside-toplevel
        files = _glob.glob(f"{SESSION_DIR}/*.json")
        sessions = []
        for f in files:
            name = os.path.splitext(os.path.basename(f))[0]
            mtime = os.path.getmtime(f)
            try:
                async with aiofiles.open(f, encoding="utf-8") as _f:
                    content = await _f.read()
                data = _json.loads(content)
                url = data.get("url", "")
                cc = len(data.get("cookies", []))
            except (OSError, _json.JSONDecodeError):
                url = ""
                cc = 0
            sessions.append({
                "name": name,
                "url": url,
                "cookies": cc,
                "modified": mtime,
            })
        sessions.sort(key=lambda s: s["modified"], reverse=True)
        return {"sessions": sessions, "total": len(sessions)}

    # ── 向后兼容：数据提取 ────────────────────────────────────

    async def extract(
        self,
        selector: str,
        fields: list[str] | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """批量提取所有匹配元素的内容。"""
        self._step_count += 1
        if fields is None:
            fields = ["innerText"]

        js = """
        ([sel, lim, flds]) => {
          const els = document.querySelectorAll(sel);
          const results = [];
          const limitNum = Math.min(els.length, lim);
          for (let i = 0; i < limitNum; i++) {
            const el = els[i];
            const row = flds.map(f => {
              if (f === 'innerText' || f === 'textContent') return (el[f] || '').trim();
              if (f === 'href') return el.href || el.getAttribute('href') || '';
              if (f === 'src') return el.src || el.getAttribute('src') || '';
              if (f === 'outerHTML') return el.outerHTML || '';
              return el.getAttribute(f) || el[f] || '';
            });
            results.push(row);
          }
          return { total: els.length, returned: limitNum, results: results, fields: flds };
        }
        """
        result = await self._ctrl.execute_js(js, [selector, limit, fields])
        data = result.get("result", {"error": "提取失败"}) if isinstance(result, dict) else {}
        if isinstance(data, dict):
            data["step"] = self._step_count
        return data

    async def extract_table(
        self,
        rows_selector: str,
        columns: dict[str, str],
        limit: int = 30,
    ) -> dict[str, Any]:
        """从表格/列表结构结构化提取数据。"""
        self._step_count += 1
        js = """
        ([sel, lim, cols]) => {
          const rows = document.querySelectorAll(sel);
          const results = [];
          const limitNum = Math.min(rows.length, lim);
          for (let i = 0; i < limitNum; i++) {
            const rowEl = rows[i];
            const item = {};
            for (const [name, colSel] of Object.entries(cols)) {
              const cell = rowEl.querySelector(colSel);
              item[name] = cell ? (cell.innerText || cell.textContent || '').trim() : '';
            }
            results.push(item);
          }
          return { total: rows.length, returned: limitNum, results: results };
        }
        """
        result = await self._ctrl.execute_js(js, [rows_selector, limit, columns])
        data = result.get("result", {}) if isinstance(result, dict) else {}
        if isinstance(data, dict):
            data["step"] = self._step_count
        return data

    # ── 向后兼容：JS 执行 ─────────────────────────────────────

    async def execute_js(self, expression: str) -> dict[str, Any]:
        """在页面中执行 JavaScript 表达式。"""
        self._step_count += 1
        result = await self._ctrl.execute_js(expression)
        if isinstance(result, dict):
            result["step"] = self._step_count
        return result

    # ── 向后兼容：智能批量 ────────────────────────────────────

    async def loop_extract(
        self,
        page_count: int,
        row_selector: str,
        columns: dict[str, str],
        next_btn: str = "",
    ) -> dict[str, Any]:
        """翻页批量提取（适用于搜索结果列表）。"""
        all_rows = []
        actual_pages = 0
        for pg in range(page_count):
            actual_pages = pg + 1
            data = await self.extract_table(row_selector, columns, limit=50)
            rows = data.get("results", [])
            if rows:
                for r in rows:
                    r["_page"] = actual_pages
                all_rows.extend(rows)
            if pg < page_count - 1 and next_btn:
                clicked = await self._ctrl.click_selector(next_btn)
                if not clicked:
                    break
                await delay("pagination")
            else:
                break
        return {
            "pages": actual_pages, "total_rows": len(all_rows),
            "results": all_rows, "step": self._step_count,
        }
