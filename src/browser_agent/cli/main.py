"""统一 CLI 入口 — agent 命令行工具，提供浏览/提取/交互/登录/快照/监控/对话/服务器等子命令。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

from browser_agent.core.agent import BrowsingAgent
from browser_agent.core.browser import BrowserController
from browser_agent.core.session import auto_detect_login
from shared.logging_config import get_logger, setup_logging

logger = get_logger("cli")


# ════════════════════════════════════════════════════════════════════
# 辅助函数
# ════════════════════════════════════════════════════════════════════

def _fmt(data, fmt: str) -> str:
    """按指定格式输出数据。"""
    if fmt == "json":
        return json.dumps(data, ensure_ascii=False, indent=2)
    if isinstance(data, dict):
        return json.dumps(data, ensure_ascii=False, indent=2)
    return str(data)


async def _safe_close(agent):
    """安全关闭 agent，忽略所有异常。"""
    try:
        await agent.close()
    except Exception:  # pylint: disable=broad-exception-caught
        pass


# ════════════════════════════════════════════════════════════════════
# 子命令实现
# ════════════════════════════════════════════════════════════════════

async def _cmd_browse(args) -> None:
    agent = BrowsingAgent(max_steps=args.max_steps, timeout_secs=args.timeout)
    try:
        result = await agent.run(task=args.task, url=args.url, headless=args.headless)
        print(_fmt(result, args.format))
        if not result.get("ok"):
            sys.exit(1)
    except KeyboardInterrupt:
        print(json.dumps({"ok": False, "error": "用户中断"}, ensure_ascii=False))
        sys.exit(1)
    finally:
        await _safe_close(agent)


async def _cmd_extract(args) -> None:
    agent = BrowsingAgent()
    try:
        await agent.open(headless=args.headless, url=args.url)
        if not agent.is_running:
            print(json.dumps({"ok": False, "error": "浏览器启动失败"}, ensure_ascii=False))
            sys.exit(1)

        fields = [f.strip() for f in args.fields.split(",")] if args.fields else None
        result = await agent.extract(selector=args.selector, fields=fields, limit=args.limit)

        if args.format == "json":
            output = json.dumps(result, ensure_ascii=False, indent=2)
        elif args.format == "csv":
            lines = [",".join(result.get("fields", []))]
            for row in result.get("results", []):
                lines.append(",".join(str(c) for c in row))
            output = "\n".join(lines)
        else:  # table
            rows = result.get("results", [])
            field_names = result.get("fields", [])
            lines = []
            if field_names:
                lines.append(" | ".join(field_names))
                lines.append("-" * 40)
            for row in rows:
                lines.append(" | ".join(str(c) for c in row))
            lines.append(f"\n共 {len(rows)} 条 (总计 {result.get('total', 0)} 条)")
            output = "\n".join(lines)

        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
            print(f"结果已保存至 {args.output}")
        else:
            print(output)
    except KeyboardInterrupt:
        print(json.dumps({"ok": False, "error": "用户中断"}, ensure_ascii=False))
        sys.exit(1)
    finally:
        await _safe_close(agent)


async def _cmd_interact(args) -> None:
    agent = BrowsingAgent()
    try:
        if args.url:
            await agent.open(headless=args.headless, url=args.url)
        elif not agent.is_running:
            await agent.open(headless=args.headless)

        if not agent.is_running:
            print(json.dumps({"ok": False, "error": "浏览器启动失败"}, ensure_ascii=False))
            sys.exit(1)

        action = args.action
        if action == "click":
            result = await agent.click(args.selector)
        elif action == "type":
            result = await agent.type_text(args.selector, args.text)
        elif action == "scroll":
            result = await agent.scroll(args.delta)
        elif action == "press":
            result = await agent.press(args.key)
        else:
            print(json.dumps({"ok": False, "error": f"未知操作: {action}"}, ensure_ascii=False))
            sys.exit(1)

        print(_fmt(result, getattr(args, "format", "text")))
        if not result.get("ok"):
            sys.exit(1)
    except KeyboardInterrupt:
        print(json.dumps({"ok": False, "error": "用户中断"}, ensure_ascii=False))
        sys.exit(1)
    finally:
        await _safe_close(agent)


async def _cmd_login(args) -> None:
    import aiofiles  # pylint: disable=import-outside-toplevel

    ctrl = BrowserController()
    agent = BrowsingAgent(controller=ctrl)

    session_name = args.name or urlparse(args.url).netloc.replace("www.", "").split(".")[0]
    save_file = Path(f"./sessions/{session_name}.json")
    save_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = await agent.open(headless=args.headless, url=args.url)
        if not result.get("ok"):
            logger.error("浏览器启动失败: %s", result.get("error", "未知错误"))
            print(json.dumps({"ok": False, "error": "浏览器启动失败"}, ensure_ascii=False))
            sys.exit(1)

        page_title = result.get("title", "N/A")
        page_url = result.get("url", "N/A")
        engine = result.get("engine", "N/A")

        sep = "=" * 55
        print(sep)
        print(f"🔵 {page_title}")
        print(f"   URL: {page_url}")
        print(f"   引擎: {engine}")
        print()
        print("请在浏览器中完成登录操作。")
        print("程序将自动检测登录状态并保存。")
        print(sep)
        print()

        page = ctrl.page
        if not page:
            logger.error("无法获取浏览器页面对象")
            print(json.dumps({"ok": False, "error": "无法获取页面"}, ensure_ascii=False))
            sys.exit(1)

        detect_cookies = [args.cookie] if args.cookie else []
        info = await auto_detect_login(
            page=page, timeout=120, interval=2,
            cookie_names=detect_cookies or None, url_has_login=False,
        )

        detected = info.get("detected", False)
        detail = info.get("detail", "")

        if detected:
            print(f"\n✅ 已检测到登录成功（依据: {detail}）")
            await asyncio.sleep(3)
        else:
            print("\n⚠️  自动检测超时（120秒），回退到手动模式")
            print("如果已完成登录请按 Enter 键...")
            try:
                loop = asyncio.get_running_loop()
                await asyncio.wait_for(
                    loop.run_in_executor(None, sys.stdin.readline),
                    timeout=60,
                )
            except (TimeoutError, EOFError, KeyboardInterrupt):
                pass
            print("正在保存登录态...")

        for attempt in range(3):
            try:
                try:
                    _ = await page.title()
                except Exception:  # pylint: disable=broad-exception-caught
                    pages = ctrl.get_pages()
                    page = pages[0] if pages else await ctrl.new_page() or page

                state = await page.context.storage_state()
                async with aiofiles.open(save_file, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(state, ensure_ascii=False, indent=2))
                cookie_count = len(state.get("cookies", []))
                print(f"✅ 登录态已保存至 {save_file}")
                print(f"   Cookie 数量: {cookie_count}")
                break
            except Exception as e:  # pylint: disable=broad-exception-caught
                if attempt < 2:
                    logger.info("保存失败 (attempt %d/3): %s", attempt + 1, e)
                    await asyncio.sleep(2 * (attempt + 1))
                else:
                    logger.error("保存失败: %s", e)
                    print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
                    sys.exit(1)
    except KeyboardInterrupt:
        print(json.dumps({"ok": False, "error": "用户中断"}, ensure_ascii=False))
        sys.exit(1)
    finally:
        await _safe_close(agent)


async def _cmd_snapshot(args) -> None:
    agent = BrowsingAgent()
    try:
        if args.url:
            await agent.open(headless=args.headless, url=args.url)
        elif not agent.is_running:
            await agent.open(headless=args.headless)

        if not agent.is_running:
            print(json.dumps({"ok": False, "error": "浏览器启动失败"}, ensure_ascii=False))
            sys.exit(1)

        snapshot = await agent.snapshot(mode="auto")

        if args.format == "json":
            output = json.dumps(snapshot, ensure_ascii=False, indent=2)
        else:
            lines = [
                f"URL: {snapshot.get('url', 'N/A')}",
                f"标题: {snapshot.get('title', 'N/A')}",
                f"模式: {snapshot.get('mode', 'N/A')}",
            ]
            if snapshot.get("elements"):
                lines.append("\n--- 可交互元素 ---")
                lines.append(snapshot["elements"])
            if snapshot.get("text"):
                lines.append("\n--- 页面文本 ---")
                lines.append(snapshot["text"][:2000])
            if snapshot.get("accessibility"):
                lines.append("\n--- 无障碍树 ---")
                lines.append(str(snapshot["accessibility"])[:2000])
            output = "\n".join(lines)

        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
            print(f"快照已保存至 {args.output}")
        else:
            print(output)

        if args.screenshot:
            import base64  # pylint: disable=import-outside-toplevel
            scr = await agent.screenshot()
            if scr.get("ok"):
                img_data = base64.b64decode(scr["base64"])
                Path(args.screenshot).write_bytes(img_data)
                print(f"截图已保存至 {args.screenshot}")
            else:
                print(f"截图失败: {scr.get('error', '未知错误')}")
    except KeyboardInterrupt:
        print(json.dumps({"ok": False, "error": "用户中断"}, ensure_ascii=False))
        sys.exit(1)
    finally:
        await _safe_close(agent)


async def _cmd_monitor(args) -> None:
    ctrl = BrowserController()

    if args.action == "check":
        if ctrl.is_running:
            page = ctrl.page
            if page:
                try:
                    health = await ctrl.detect_page_health()
                except Exception:  # pylint: disable=broad-exception-caught
                    health = {"healthy": False, "issues": ["无法获取页面状态"]}
            else:
                health = {"healthy": False, "issues": ["无活动页面"]}
            print(_fmt({"ok": True, "running": True, "engine": ctrl.engine, "health": health}, args.format))
        else:
            print(_fmt({"ok": True, "running": False, "message": "浏览器未运行"}, args.format))

    elif args.action == "stats":
        print(_fmt({"ok": True, "running": ctrl.is_running, "engine": ctrl.engine, "message": "统计功能开发中"}, args.format))

    elif args.action == "clean":
        print(_fmt({"ok": True, "message": "清理功能开发中"}, args.format))

    else:
        print(_fmt({"ok": False, "error": f"未知操作: {args.action}"}, args.format))
        sys.exit(1)


async def _cmd_chat(args) -> None:
    from browser_agent.chat.cli import ChatCLI  # pylint: disable=import-outside-toplevel
    cli = ChatCLI(tone=args.tone)
    await cli.interactive_loop()


async def _cmd_server(args) -> None:
    argv = []
    if args.port:
        argv.extend(["--port", str(args.port)])
    if args.host:
        argv.extend(["--host", args.host])
    if args.headless:
        argv.append("--headless")

    from browser_agent.mcp.server import main as mcp_main  # pylint: disable=import-outside-toplevel
    await mcp_main(argv)


# ════════════════════════════════════════════════════════════════════
# 参数解析器
# ════════════════════════════════════════════════════════════════════

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent", description="通用浏览器自动化助手")
    sub = parser.add_subparsers(dest="command", required=True)

    # ── browse ──
    b = sub.add_parser("browse", help="智能浏览 — 浏览指定URL并执行任务")
    b.add_argument("url", help="目标 URL")
    b.add_argument("task", help="任务描述")
    b.add_argument("--headless", action="store_true", help="无头模式")
    b.add_argument("--speed", choices=["turbo", "normal", "stealth"], default="normal")
    b.add_argument("--max-steps", type=int, default=50, help="最大步骤数")
    b.add_argument("--timeout", type=int, default=300, help="超时时间（秒）")
    b.add_argument("--format", "-f", choices=["json", "text"], default="json")

    # ── extract ──
    e = sub.add_parser("extract", help="数据提取 — 从页面提取数据")
    e.add_argument("url", help="目标 URL")
    e.add_argument("selector", help="CSS 选择器")
    e.add_argument("--fields", help="提取字段，逗号分隔（如 innerText,href,src）")
    e.add_argument("--limit", type=int, default=20, help="提取数量上限")
    e.add_argument("--output", "-o", help="输出文件路径")
    e.add_argument("--format", "-f", choices=["json", "csv", "table"], default="table")
    e.add_argument("--headless", action="store_true", help="无头模式")

    # ── interact ──
    i = sub.add_parser("interact", help="单步交互 — 点击/输入/滚动/按键")
    i_sub = i.add_subparsers(dest="action", required=True)

    click_p = i_sub.add_parser("click", help="点击元素")
    click_p.add_argument("selector", help="CSS 选择器")
    click_p.add_argument("--headless", action="store_true")
    click_p.add_argument("--url", help="先导航到此 URL")
    click_p.add_argument("--format", "-f", choices=["json", "text"], default="text")

    type_p = i_sub.add_parser("type", help="输入文本")
    type_p.add_argument("selector", help="CSS 选择器")
    type_p.add_argument("text", help="输入文本")
    type_p.add_argument("--headless", action="store_true")
    type_p.add_argument("--url", help="先导航到此 URL")
    type_p.add_argument("--format", "-f", choices=["json", "text"], default="text")

    scroll_p = i_sub.add_parser("scroll", help="滚动页面")
    scroll_p.add_argument("delta", nargs="?", type=int, default=500, help="滚动距离（正=向下）")
    scroll_p.add_argument("--headless", action="store_true")
    scroll_p.add_argument("--url", help="先导航到此 URL")
    scroll_p.add_argument("--format", "-f", choices=["json", "text"], default="text")

    press_p = i_sub.add_parser("press", help="按键")
    press_p.add_argument("key", help="键名（如 Enter, Tab, Escape）")
    press_p.add_argument("--headless", action="store_true")
    press_p.add_argument("--url", help="先导航到此 URL")
    press_p.add_argument("--format", "-f", choices=["json", "text"], default="text")

    # ── login ──
    l = sub.add_parser("login", help="登录管理 — 手动登录并保存 session")
    l.add_argument("url", help="登录页面 URL")
    l.add_argument("--name", help="Session 名称（默认从 URL 提取）")
    l.add_argument("--cookie", help="要检测的 Cookie 名称")
    l.add_argument("--headless", action="store_true", help="无头模式")

    # ── snapshot ──
    s = sub.add_parser("snapshot", help="页面快照 — 获取页面结构快照")
    s.add_argument("url", nargs="?", help="目标 URL（可选，不提供则使用当前页面）")
    s.add_argument("--format", "-f", choices=["json", "text"], default="text")
    s.add_argument("--output", "-o", help="输出文件路径")
    s.add_argument("--screenshot", help="截图保存路径")
    s.add_argument("--headless", action="store_true", help="无头模式")

    # ── monitor ──
    m = sub.add_parser("monitor", help="健康监控 — 检查浏览器状态")
    m_sub = m.add_subparsers(dest="action", required=True)

    m_check = m_sub.add_parser("check", help="检查浏览器状态")
    m_check.add_argument("--format", "-f", choices=["json", "text"], default="text")

    m_stats = m_sub.add_parser("stats", help="查看统计信息")
    m_stats.add_argument("--format", "-f", choices=["json", "text"], default="text")

    m_clean = m_sub.add_parser("clean", help="清理浏览器缓存")
    m_clean.add_argument("--format", "-f", choices=["json", "text"], default="text")

    # ── chat ──
    c = sub.add_parser("chat", help="对话模式 — 启动对话 Agent")
    c.add_argument("--tone", help="语气预设")
    c.add_argument("--temperature", type=float, default=0.7, help="温度参数")

    # ── server ──
    sv = sub.add_parser("server", help="MCP 服务器 — 启动 MCP 服务器")
    sv.add_argument("--port", type=int, default=8080, help="监听端口")
    sv.add_argument("--host", default="localhost", help="监听地址")
    sv.add_argument("--headless", action="store_true", help="无头模式")

    return parser


# ════════════════════════════════════════════════════════════════════
# 主入口
# ════════════════════════════════════════════════════════════════════

def main() -> None:
    """CLI 主入口：解析参数并分发到对应子命令。"""
    setup_logging()
    parser = _build_parser()
    args = parser.parse_args()

    command_map = {
        "browse": _cmd_browse,
        "extract": _cmd_extract,
        "interact": _cmd_interact,
        "login": _cmd_login,
        "snapshot": _cmd_snapshot,
        "monitor": _cmd_monitor,
        "chat": _cmd_chat,
        "server": _cmd_server,
    }

    handler = command_map.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    try:
        asyncio.run(handler(args))
    except KeyboardInterrupt:
        print("\n已取消")
        sys.exit(1)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("CLI 执行异常: %s", e)
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
