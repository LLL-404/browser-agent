"""通用 CLI 入口 — 解析全局参数，根据 --mode 加载对应的业务模式。"""
import aiofiles
import argparse
import asyncio
import importlib
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from agent.core.agent import BrowserAgent
from agent.core.browser import BrowserController
from agent.core.session import auto_detect_login
from shared.logging_config import get_logger

logger = get_logger("cli")


async def _login(url: str, save_path: str, cookie_names: list[str] | None = None, headless: bool = False):
    ctrl = BrowserController()
    agent = BrowserAgent(ctrl)

    save_file = Path(save_path)
    save_file.parent.mkdir(parents=True, exist_ok=True)

    result = await agent.open(headless=headless, url=url)
    if not result.get("ok"):
        logger.error("浏览器启动失败: %s", result.get('error', '未知错误'))
        return

    page_title = result.get("title", "N/A")
    page_url = result.get("url", "N/A")
    engine = result.get("engine", "N/A")

    sep = "=" * 55
    print(sep)
    print(f"🔵 {page_title}")
    print(f"   URL: {page_url}")
    print(f"   引擎: {engine}")
    print()
    print("请 Boss 在浏览器中完成登录操作。")
    print("程序将自动检测登录状态并保存。")
    print(sep)
    print()

    # Determine cookie names to watch
    detect_cookies = list(cookie_names) if cookie_names else []

    # Get the page object from the controller
    page = ctrl.page
    if not page:
        logger.error("无法获取浏览器页面对象")
        await agent.close()
        return

    # Build custom rules based on URL
    custom_rules = {}
    if "qcc.com" in url:
        detect_cookies.append("qcc_token")
        detect_cookies.append("QCC_SESSION")
    elif "tianyancha.com" in url:
        detect_cookies.append("tyc_token")
        detect_cookies.append("TYC_SESSION")
    detect_cookies = [c for c in detect_cookies if c]

    # Run auto detect
    info = await auto_detect_login(
        page=page,
        timeout=120,
        interval=2,
        cookie_names=detect_cookies or None,
        custom_rules=custom_rules,
        url_has_login=False,
    )

    detected = info.get("detected", False)
    reason = info.get("reason", "unknown")
    detail = info.get("detail", "")

    if detected:
        print(f"\n✅ 已检测到登录成功（依据: {detail}）")
        print(f"   等待页面稳定后保存登录态...")
        await asyncio.sleep(3)  # let page settle after login redirect
    else:
        print(f"\n⚠️  自动检测超时（120秒），回退到手动模式")
        print(f"   如果已完成登录请按 Enter 键，否则等待自动保存...")
        sep2 = "-" * 40
        print(sep2)
        print("请 Boss 确认是否已登录，完成后按 Enter 键...")
        print(sep2)
        try:
            loop = asyncio.get_running_loop()

            def _readline():
                return sys.stdin.readline()

            await asyncio.wait_for(
                loop.run_in_executor(None, _readline),
                timeout=60,
            )
            print("  接收到确认，正在保存登录态...")
        except asyncio.TimeoutError:
            print("  等待超时（60秒），强制保存当前状态...")
        except (EOFError, KeyboardInterrupt):
            print("  终端输入不可用，尝试保存当前状态...")
        except Exception:
            print("  保存当前状态...")

    # Save as Playwright storage_state (with retry)
    saved = False
    for attempt in range(3):
        try:
            # If page was closed during redirect, get a fresh page from context
            try:
                _ = await page.title()
            except Exception:
                pages = ctrl.get_pages()
                if pages:
                    page = pages[0]
                else:
                    page = await ctrl.new_page() or page
            state = await page.context.storage_state()
            async with aiofiles.open(save_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(state, ensure_ascii=False, indent=2))
            cookie_count = len(state.get("cookies", []))
            print(f"✅ 登录态已保存至 {save_file}")
            print(f"   Cookie 数量: {cookie_count}")
            print(f"   文件大小: {save_file.stat().st_size} bytes")
            saved = True
            break
        except Exception as e:
            if attempt < 2:
                wait = 2 * (attempt + 1)
                logger.info("保存失败 (attempt %d/3): %s，%ds 后重试", attempt + 1, e, wait)
                await asyncio.sleep(wait)
            else:
                logger.error("保存失败 (3次重试后): %s", e)

    try:
        await agent.close()
    except Exception as e:
        logger.debug("关闭浏览器时忽略异常: %s", e)


async def _browse(url: str):
    """启动浏览器打开 URL，等待后保存登录态。"""
    ctrl = BrowserController()
    agent = BrowserAgent(ctrl)

    result = await agent.open(url=url)
    if not result.get("ok"):
        logger.error("浏览器启动失败: %s", result.get('error', '未知错误'))
        return

    print(f"当前页面: {result.get('url', 'N/A')}")
    print(f"页面标题: {result.get('title', 'N/A')}")
    print(f"浏览器引擎: {result.get('engine', 'N/A')}")

    sep = "=" * 50
    print(sep)
    print(f"浏览器已打开 ({url})")
    print("请 Boss 在浏览器中完成操作。")
    print(f"脚本将在 180 秒后自动保存当前会话状态。")
    print(sep)
    print()

    for i in range(180):
        await asyncio.sleep(1)
        if i > 0 and i % 30 == 0:
            print(f"  ⏳ 剩余 {180 - i} 秒后自动保存...")

    domain = urlparse(url).netloc.replace("www.", "").split(".")[0]
    result = await agent.save_session(name=domain)
    if result.get("ok"):
        print(f"✅ 登录态已保存至 sessions/{domain}.json")
        print(f"   Cookie 数量: {result.get('cookies_count', 0)}")
    else:
        logger.error("保存失败: %s", result.get('error', '未知错误'))

    await agent.close()


def _setup_browse_parser(subparsers):
    p = subparsers.add_parser("browse", help="通用浏览器浏览模式")
    p.add_argument("--url", "-u", default="about:blank", help="要打开的 URL")
    return p


def _setup_login_parser(subparsers):
    p = subparsers.add_parser("login", help="智能登录 — 自动检测登录状态并保存")
    p.add_argument("--url", "-u", required=True, help="登录页面 URL")
    p.add_argument("--save", "-s", required=True, help="保存路径（如 sessions/qcc_state.json）")
    p.add_argument("--cookie", "-c", action="append", dest="cookie_names",
                   help="要检测的 Cookie 名称（可重复）")
    p.add_argument("--headless", action="store_true", help="无头模式")
    return p


def main():
    parser = argparse.ArgumentParser(description="通用浏览器自动化助手")
    parser.add_argument("--mode", "-m", default="", help="业务模式 (如 zhipin)")
    subparsers = parser.add_subparsers(dest="command")

    args, _ = parser.parse_known_args()
    mode_val = args.mode

    if mode_val:
        try:
            mod = importlib.import_module(f"modes.{mode_val}")
            if hasattr(mod, "register_cli"):
                mod.register_cli(subparsers)
            args = parser.parse_args()
            if hasattr(mod, "run_cli"):
                sys.exit(asyncio.run(mod.run_cli(args)))
        except ImportError as e:
            logger.error("模式 '%s' 未找到: %s", mode_val, e)
            sys.exit(1)
    else:
        _setup_browse_parser(subparsers)
        _setup_login_parser(subparsers)
        args = parser.parse_args()
        if args.command == "browse":
            asyncio.run(_browse(args.url))
        elif args.command == "login":
            asyncio.run(_login(args.url, args.save, args.cookie_names, args.headless))
        else:
            parser.print_help()


if __name__ == "__main__":
    main()
