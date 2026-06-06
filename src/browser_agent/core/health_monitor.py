"""页面健康监控与自动修复模块。

从 BrowserController 中提取的页面诊断、健康检测和自动修复逻辑，
通过组合方式持有 BrowserController 引用，而非继承。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from browser_agent.core.anti_detect import STEALTH_SCRIPT
from shared.logging_config import get_logger

if TYPE_CHECKING:
    from browser_agent.core.browser import BrowserController

logger = get_logger("health_monitor")


class HealthMonitor:
    """页面健康监控器，负责诊断页面问题并执行自动修复。

    持有 BrowserController 引用以访问页面、网络日志等共享资源。
    """

    # 反爬/空白页检测关键词，覆盖主流平台常见拦截文案
    _BLANK_PAGE_KEYWORDS = [
        "安全验证", "滑块验证", "访问异常", "请求过于频繁", "系统繁忙",
        "人机验证", "请稍后重试", "网络连接失败", "页面加载中",
        "403 Forbidden", "404 Not Found", "502 Bad Gateway",
        "Access Denied", "Service Unavailable",
        "您的访问被限制", "当前网络环境异常", "请使用手机扫码登录",
    ]

    # 各类问题的修复策略（按优先级排序）
    _REPAIR_STRATEGIES: dict[str, list[dict]] = {
        # 每个策略: {"name": 描述, "fn": 修复方法名, "args": 参数}
        "anti_crawl": [
            {
                "name": "等待页面渲染完成",
                "fn": "_repair_wait_render",
            },
            {
                "name": "重新注入反检测脚本",
                "fn": "_repair_reinject_stealth",
            },
            {
                "name": "硬刷新页面（清除缓存）",
                "fn": "_repair_hard_reload",
            },
        ],
        "blank_or_empty": [
            {
                "name": "等待 JS 渲染完成",
                "fn": "_repair_wait_js_ready",
            },
            {
                "name": "硬刷新页面",
                "fn": "_repair_hard_reload",
            },
            {
                "name": "重新导航到目标URL",
                "fn": "_repair_renavigate",
            },
        ],
        "network_blocked": [
            {
                "name": "等待后重试",
                "fn": "_repair_wait_and_retry",
            },
            {
                "name": "硬刷新页面",
                "fn": "_repair_hard_reload",
            },
        ],
        "captcha_required": [
            {
                "name": "等待用户手动处理验证码",
                "fn": "_repair_wait_for_captcha_solve",
            },
        ],
        "redirect_loop": [
            {
                "name": "终止重定向链并重新导航",
                "fn": "_repair_break_redirect",
            },
        ],
    }

    def __init__(self, controller: BrowserController) -> None:
        """初始化健康监控器。

        Args:
            controller: BrowserController 实例，用于访问页面和共享资源。
        """
        self._controller = controller

    async def detect_page_health(self) -> dict[str, Any]:
        """检测当前页面是否为空白页、被反爬拦截或加载异常。

        Returns:
            包含 healthy/is_blank/issues/url/title/body_len/has_body 的诊断字典。
        """
        page = self._controller.require_page()
        result: dict[str, Any] = {
            "healthy": True,
            "is_blank": False,
            "issues": [],
            "url": "",
            "title": "",
            "body_len": 0,
            "has_body": False,
        }

        try:
            result["url"] = page.url
            result["title"] = await page.title() or ""
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        # 检查1: URL 是否为 about:blank 或空
        if not result["url"] or result["url"].startswith("about:"):
            result["healthy"] = False
            result["is_blank"] = True
            result["issues"].append(f"空白页 URL: {result['url'] or '(empty)'}")
            return result

        # 检查2: body 是否存在及其内容长度
        try:
            has_body_el = await page.query_selector("body")
            if has_body_el is None:
                result["healthy"] = False
                result["is_blank"] = True
                result["issues"].append("DOM 中无 body 元素")
                return result

            result["has_body"] = True
            body_text = await page.inner_text("body") or ""
            result["body_len"] = len(body_text.strip())

            if result["body_len"] < 100:
                result["healthy"] = False
                result["is_blank"] = True
                result["issues"].append(f"body 内容过短 ({result['body_len']} 字符)")
                if body_text.strip():
                    result["issues"].append(f"内容预览: {body_text.strip()[:80]}")
                return result
        except Exception as e:  # pylint: disable=broad-exception-caught
            result["healthy"] = False
            result["issues"].append(f"读取 body 失败: {e}")
            return result

        # 检查3: 反爬拦截关键词
        try:
            for kw in self._BLANK_PAGE_KEYWORDS:
                if kw in body_text:
                    result["healthy"] = False
                    result["issues"].append(f"检测到反爬/异常文本: '{kw}'")
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        # 检查4: 页面加载状态
        try:
            loading_state = await page.evaluate(
                "() => document.readyState"
            )
            if loading_state == "loading":
                result["issues"].append("页面仍在加载中 (readyState=loading)")
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        if result["issues"]:
            result["healthy"] = False

        return result

    async def diagnose_page_issue(self, url: str | None = None) -> dict[str, Any]:
        """对当前页面进行深度诊断，确定问题的根因类别。

        不仅检测症状，还分析：
        - 是否被反爬拦截（验证码/WAF）
        - JS 资源是否正常加载
        - 网络请求是否有大量失败
        - 是否陷入重定向循环
        - Cookie/Session 是否过期

        Args:
            url: 原始目标 URL（用于判断是否被重定向）。

        Returns:
            {
                "diagnosis": str,          # 根因类别
                "confidence": float,       # 置信度 0-1
                "symptoms": list[str],     # 症状列表
                "details": dict,           # 详细诊断数据
                "suggested_repair": list,  # 建议的修复策略
            }
        """
        page = self._controller.require_page()
        target_url = url or ""

        # ── 收集多维度诊断数据 ──
        symptoms: list[str] = []
        details: dict[str, Any] = {}
        diagnosis = "unknown"
        confidence = 0.0

        # 1. 基础健康检测
        health = await self.detect_page_health()
        symptoms.extend(health["issues"])
        details["health"] = health

        # 如果页面完全健康，直接返回
        if health["healthy"]:
            return {
                "diagnosis": "normal",
                "confidence": 1.0,
                "symptoms": [],
                "details": details,
                "suggested_repair": [],
            }

        current_url = health.get("url", "")

        # 2. 检测重定向循环
        details["redirect_info"] = {}
        if target_url and current_url and target_url != current_url:
            details["redirect_info"]["from"] = target_url
            details["redirect_info"]["to"] = current_url
            # 判断是否跳转到登录页或验证页
            login_indicators = ["login", "passport", "verify", "captcha", "security"]
            is_login_redirect = any(ind in current_url.lower() for ind in login_indicators)
            if is_login_redirect:
                symptoms.append(f"被重定向到认证/验证页: {current_url}")
                details["redirect_info"]["type"] = "auth_redirect"

        # 3. 检测 JS 加载状态和错误
        js_diagnosis = await page.evaluate("""() => {
            const info = {};
            // 脚本加载情况
            const scripts = document.querySelectorAll('script[src]');
            info.total_scripts = scripts.length;
            // 控制台错误数量（通过 window.onerror 计数）
            info.js_errors = window.__playwright_error_count || 0;
            // 关键全局对象是否存在
            info.has_vue = typeof Vue !== 'undefined' || !!document.querySelector('[data-v-]');
            info.has_react = typeof React !== 'undefined' || !!document.querySelector('[data-reactroot], [data-reactid]');
            // DOM 就绪状态
            info.ready_state = document.readyState;
            // 可见元素数量
            info.visible_elements = document.querySelectorAll('body *').length;
            // 图片加载情况
            const images = document.querySelectorAll('img');
            info.total_images = images.length;
            let loaded_imgs = 0;
            images.forEach(img => { if (img.complete && img.naturalWidth > 0) loaded_imgs++; });
            info.loaded_images = loaded_imgs;
            return info;
        }""")
        details["js_status"] = js_diagnosis

        if js_diagnosis.get("visible_elements", 0) < 10:
            symptoms.append(f"DOM 元素过少 ({js_diagnosis['visible_elements']} 个)")
        if js_diagnosis.get("ready_state") == "loading":
            symptoms.append("JS 仍在执行中")

        # 4. 检测网络请求失败情况
        failed_requests = [r for r in self._controller.get_network_logs() if r.get("status", 0) >= 400]
        details["failed_requests_count"] = len(failed_requests)
        if failed_requests:
            # 统计失败类型
            status_codes = [r.get("status") for r in failed_requests]
            details["failed_status_codes"] = status_codes[:10]
            if any(s == 403 for s in status_codes):
                symptoms.append(f"存在 {sum(1 for s in status_codes if s == 403)} 个 403 请求（WAF 拦截）")
            if any(s in (500, 502, 503, 504) for s in status_codes):
                symptoms.append("存在服务端错误响应 (5xx)")

        # 5. 检测 WebDriver 暴露情况
        try:
            wd_value = await page.evaluate("navigator.webdriver")
            if wd_value is not None and wd_value is not True:
                details["webdriver_hidden"] = True
            else:
                details["webdriver_hidden"] = False
                symptoms.append("navigator.webdriver 未被隐藏（可能被检测）")
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        # 6. 检测验证码元素
        captcha_selectors = [
            ".geetest_panel", ".geetest_radar_tip", "#captcha",
            ".verify-img-panel", ".tc-fg-group", ".yidun_bgimg",
            ".captcha-container", "[class*=captcha]", "[class*=geetest]",
            "[class*=verify]", "[id*=captcha]", "[id*=verify]",
        ]
        captcha_found = []
        for sel in captcha_selectors:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    captcha_found.append(sel)
            except Exception:  # pylint: disable=broad-exception-caught
                continue
        if captcha_found:
            symptoms.append(f"检测到验证码组件: {', '.join(captcha_found[:3])}")
            details["captcha_elements"] = captcha_found

        # ── 综合判定根因 ──
        body_text = ""
        try:
            body_text = (await page.inner_text("body") or "").strip()
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        # 规则引擎：按优先级匹配根因
        if captcha_found:
            diagnosis = "captcha_required"
            confidence = 0.9
        elif any(kw in body_text for kw in ["安全验证", "滑块验证", "人机验证", "验证码"]):
            diagnosis = "anti_crawl"
            confidence = 0.85
        elif any(kw in body_text for kw in ["403 Forbidden", "Access Denied", "您的访问被限制", "当前网络环境异常"]):
            diagnosis = "network_blocked"
            confidence = 0.85
        elif health.get("is_blank") or health.get("body_len", 0) < 100:
            if js_diagnosis.get("visible_elements", 0) < 5:
                diagnosis = "blank_or_empty"
                confidence = 0.8
            else:
                diagnosis = "anti_crawl"
                confidence = 0.7
        elif details.get("redirect_info", {}).get("type") == "auth_redirect":
            diagnosis = "session_expired"
            confidence = 0.75
        elif len(failed_requests) > 5 and any(r.get("status") == 403 for r in failed_requests):
            diagnosis = "network_blocked"
            confidence = 0.8
        else:
            diagnosis = "unknown"
            confidence = 0.5

        # 获取建议的修复策略
        suggested_repair = self._REPAIR_STRATEGIES.get(diagnosis, [])

        logger.info(
            "页面诊断完成: %s (置信度 %.0f%%) — %s",
            diagnosis, confidence * 100,
            "; ".join(symptoms) if symptoms else "无明显问题",
        )

        return {
            "diagnosis": diagnosis,
            "confidence": confidence,
            "symptoms": symptoms,
            "details": details,
            "suggested_repair": suggested_repair,
        }

    # ── 修复方法实现 ────────────────────────────────────────

    async def _repair_wait_render(self, page, **_kwargs) -> bool:
        """等待页面异步渲染完成（SPA 应用常见）。"""
        try:
            # 等待 body 内有足够多的可见元素
            await page.wait_for_function(
                "() => document.querySelectorAll('body *').length > 20",
                timeout=8000,
            )
            logger.info("[修复] 页面已渲染出足够元素")
            return True
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning("[修复] 等待渲染超时")
            return False

    async def _repair_reinject_stealth(self, page, **_kwargs) -> bool:
        """重新注入反检测脚本。"""
        try:
            await page.add_init_script(STEALTH_SCRIPT)
            # 注入后需要刷新才能生效
            await page.reload(wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(2)
            logger.info("[修复] 反检测脚本已重新注入并刷新页面")
            return True
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("[修复] 反检测脚本注入失败: %s", e)
            return False

    async def _repair_hard_reload(self, page, **_kwargs) -> bool:
        """强制硬刷新（绕过缓存）。"""
        try:
            # 使用 JavaScript 强制刷新，绕过缓存
            await page.evaluate(
                "() => { location.reload(true); }"
            )
            await page.wait_for_load_state("domcontentloaded", timeout=20000)
            await asyncio.sleep(3)
            logger.info("[修复] 已执行硬刷新")
            return True
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("[修复] 硬刷新失败: %s", e)
            return False

    async def _repair_wait_js_ready(self, page, **_kwargs) -> bool:
        """等待 JS 完全就绪。"""
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
            await asyncio.sleep(2)
            logger.info("[修复] JS 已完全就绪 (networkidle)")
            return True
        except Exception:  # pylint: disable=broad-exception-caught
            # networkidle 超时再等一次 domcontentloaded
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
                await asyncio.sleep(5)
                logger.info("[修复] 等待超时但 DOM 已就绪")
                return True
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.warning("[修复] 等待 JS 就绪失败: %s", e)
                return False

    async def _repair_renavigate(self, page, url="", **kwargs) -> bool:
        """重新导航到目标 URL。"""
        target = kwargs.get("target_url") or url
        if not target:
            target = page.url
        try:
            await page.goto(target, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(3)
            logger.info("[修复] 已重新导航到 %s", target[:60])
            return True
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("[修复] 重新导航失败: %s", e)
            return False

    async def _repair_wait_and_retry(self, _page, **kwargs) -> bool:
        """等待一段时间后让浏览器自然恢复。"""
        delay_sec = kwargs.get("delay", 5)
        logger.info("[修复] 等待 %d 秒后检查...", delay_sec)
        await asyncio.sleep(delay_sec)
        return True  # 总是返回 True，让外层再次检测

    async def _repair_wait_for_captcha_solve(self, page, **kwargs) -> bool:
        """等待用户手动通过验证码。"""
        max_wait = kwargs.get("max_wait", 120)  # 最长等待 2 分钟
        logger.info("[修复] 等待用户手动处理验证码（最长 %d 秒）...", max_wait)

        # 定期检测验证码是否消失
        for i in range(max_wait // 5):
            await asyncio.sleep(5)
            # 检查验证码元素是否仍然可见
            still_visible = False
            for sel in [".geetest_panel", ".tc-fg-group", ".yidun_bgimg", ".captcha-container"]:
                try:
                    el = await page.query_selector(sel)
                    if el and await el.is_visible():
                        still_visible = True
                        break
                except Exception:  # pylint: disable=broad-exception-caught
                    continue
            if not still_visible:
                logger.info("[修复] 验证码已通过")
                await asyncio.sleep(2)  # 验证码通过后等页面跳转
                return True
            if (i + 1) % 6 == 0:  # 每 30 秒提示一次
                logger.info("[修复] 仍在等待验证码... (%d/%d秒)", (i + 1) * 5, max_wait)

        logger.warning("[修复] 验证码等待超时 (%d 秒)", max_wait)
        return False

    async def _repair_break_redirect(self, page, **kwargs) -> bool:
        """打断重定向循环，直接导航到目标 URL。"""
        target = kwargs.get("target_url", "")
        if not target:
            logger.warning("[修复] 无法打断重定向：缺少目标 URL")
            return False
        try:
            # 先禁用所有事件监听器，防止重定向
            await page.evaluate("""
                () => {
                    // 拦截 location 变更
                    Object.defineProperty(window, 'location', {
                        configurable: true,
                        get: () => window.__originalLocation || window.location,
                    });
                }
            """)
            await page.goto(target, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(3)
            logger.info("[修复] 已打断重定向并重新导航")
            return True
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("[修复] 打断重定向失败: %s", e)
            return False

    async def _execute_repair(
        self,
        strategy: dict,
        page,
        target_url: str = "",
    ) -> tuple[bool, str]:
        """执行单个修复策略。

        Returns:
            (成功与否, 策略描述)
        """
        fn_name = strategy.get("fn", "")
        name = strategy.get("name", fn_name)
        repair_fn = getattr(self, fn_name, None)

        if repair_fn is None:
            logger.error("[修复] 未知修复方法: %s", fn_name)
            return False, f"{name} (方法不存在)"

        try:
            result = await repair_fn(page=page, target_url=target_url)
            status = "成功" if result else "失败"
            logger.info("[修复] 策略 [%s]: %s", name, status)
            return result, name
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("[修复] 策略 [%s] 异常: %s", name, e)
            return False, f"{name} ({e})"

    async def auto_repair(
        self,
        url: str = "",
        max_repair_rounds: int = 3,
    ) -> dict[str, Any]:
        """自动诊断页面问题并尝试修复。

        流程：诊断 → 选择策略 → 执行修复 → 再次诊断 → 循环直到健康或达到上限

        Args:
            url: 原始目标 URL。
            max_repair_rounds: 最大修复轮次。

        Returns:
            {
                "repaired": bool,       # 最终是否修复成功
                "rounds": int,          # 实际执行的轮次
                "initial_diagnosis": dict,  # 初始诊断结果
                "final_health": dict,       # 最终健康状态
                "repairs_attempted": list,  # 尝试过的修复记录
            }
        """
        page = self._controller.require_page()
        repairs_attempted: list[dict] = []

        # 第一步：初始诊断
        diag = await self.diagnose_page_issue(url=url)
        initial_diag = diag.copy()

        if diag["diagnosis"] == "normal":
            return {
                "repaired": True,
                "rounds": 0,
                "initial_diagnosis": initial_diag,
                "final_health": await self.detect_page_health(),
                "repairs_attempted": [],
            }

        logger.info(
            "=== 自动修复启动 === 诊断: %s (置信度 %.0f%%) | 症状: %s",
            diag["diagnosis"], diag["confidence"] * 100,
            "; ".join(diag["symptoms"])[:200],
        )

        strategies = diag.get("suggested_repair", [])
        if not strategies:
            logger.warning("无可用修复策略，诊断结果: %s", diag["diagnosis"])
            return {
                "repaired": False,
                "rounds": 0,
                "initial_diagnosis": initial_diag,
                "final_health": await self.detect_page_health(),
                "repairs_attempted": [],
            }

        # 第二步：按轮次执行修复
        strat_idx = 0
        for round_num in range(1, max_repair_rounds + 1):
            if strat_idx >= len(strategies):
                # 所有策略都试过了，从头再来一轮
                strat_idx = 0
                logger.info("[修复 第%d轮] 所有策略已遍历，重新开始", round_num)

            strategy = strategies[strat_idx]
            success, desc = await self._execute_repair(strategy, page, url)
            repairs_attempted.append({
                "round": round_num,
                "strategy": desc,
                "success": success,
            })

            # 修复后重新检测健康状态
            health = await self.detect_page_health()
            if health["healthy"]:
                logger.info(
                    "=== 修复成功 === 共 %d 轮, 最后策略: %s",
                    round_num, desc,
                )
                return {
                    "repaired": True,
                    "rounds": round_num,
                    "initial_diagnosis": initial_diag,
                    "final_health": health,
                    "repairs_attempted": repairs_attempted,
                }

            # 不健康则继续下一个策略
            strat_idx += 1
            logger.info(
                "[修复 第%d轮] 修复后仍未健康: %s",
                round_num, "; ".join(health.get("issues", []))[:100],
            )

        # 所有轮次用尽
        final_health = await self.detect_page_health()
        logger.error(
            "=== 修复失败 === 共尝试 %d 次, 最终状态: %s",
            len(repairs_attempted),
            "; ".join(final_health.get("issues", []))[:200],
        )
        return {
            "repaired": False,
            "rounds": len(repairs_attempted),
            "initial_diagnosis": initial_diag,
            "final_health": final_health,
            "repairs_attempted": repairs_attempted,
        }
