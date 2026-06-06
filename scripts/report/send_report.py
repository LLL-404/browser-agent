#!/usr/bin/env python3
"""发送交付报告到 DeepSeek 监管会话。

用法:
    python scripts/send_report.py <报告文件> [--url URL] [--confirm] [--headless]

流程:
    1. 读取报告 → 2. 自动填入 DeepSeek 输入框 → 3. 自动发送

注意事项:
    - 共享登录态文件: sessions/storage_state.json
    - 浏览器数据目录: browser_profile/playwright_send/
    - 支持 --headless 参数（无需 GUI 时静默发送）
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

# ── 默认值 ─────────────────────────────────────────────────

DEFAULT_URL = "https://chat.deepseek.com/a/chat/s/6ba0590c-3d11-4a43-8d02-4ecb95bcd10b"
SHARED_BROWSER_DIR = Path("browser_profile/playwright_send")
STORAGE_STATE_PATH = Path("sessions/storage_state.json")

# 输入框选择器优先级
INPUT_SELECTORS = [
    "div.ProseMirror[contenteditable='true']",
    "textarea[data-testid='chat-input']",
    "#chat-input",
    "textarea[placeholder]",
    "div[contenteditable='true']",
]

# 发送按钮选择器
SEND_BUTTON_SELECTORS = [
    "button[aria-label='发送']",
    "button[aria-label='Send']",
    "div.send-button",
    "button.send-btn",
]

# 已登录页面的正面特征
LOGGED_IN_INDICATORS = [
    "div.ProseMirror[contenteditable='true']",
    "textarea[data-testid='chat-input']",
    "textarea[placeholder]",
]

# login page URL patterns
LOGIN_URL_INDICATORS = ["login", "signin", "auth", "signup"]

_context_ref = None


def _signal_handler(sig, frame):
    if _context_ref:
        try:
            _save_state(_context_ref)
        except Exception:
            pass
    print("\n被中断，登录状态已保存。")
    sys.exit(0)


def _storage_state_path() -> Path:
    return STORAGE_STATE_PATH.resolve()


def _is_login_page(page) -> bool:
    url = page.url.lower()
    for kw in LOGIN_URL_INDICATORS:
        if kw in url:
            return True
    return False


def _check_session_valid(page) -> bool:
    if _is_login_page(page):
        return False
    for sel in LOGGED_IN_INDICATORS:
        try:
            if page.locator(sel).count() > 0:
                return True
        except Exception:
            continue
    return False


def parse_report(report_path: str) -> dict:
    text = Path(report_path).read_text(encoding="utf-8")
    lines = text.strip().split("\n")
    task = ""
    for i, line in enumerate(lines):
        if line.startswith("#") and i < 3:
            continue
        if line.strip().startswith("**任务**"):
            task = line.split(":", 1)[-1].strip()
            break
        if "任务" in line:
            task = line.strip()[:80]
    ts = time.strftime("%Y-%m-%d %H:%M")
    return {"time": ts, "task": task or "架构重组", "text": text}


def format_summary(info: dict) -> str:
    sep = "=" * 60
    return (
        f"{sep}\n"
        f"交付报告已填入输入框，内容摘要：\n"
        f"  交付时间：{info['time']}\n"
        f"  任务描述：{info['task']}\n"
        f"{sep}"
    )


def _try_selectors(page, selectors: list[str], timeout: int = 2000):
    for sel in selectors:
        loc = page.locator(sel)
        try:
            loc.wait_for(state="visible", timeout=timeout)
            return loc
        except Exception:
            continue
    return None


def _save_state(context):
    path = _storage_state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(path))
        print(f"登录状态已保存 → {path}")
    except Exception as e:
        print(f"保存登录状态失败: {e}")


def _restore_storage_state(context, page, url: str):
    """从 storage_state.json 恢复 Cookie + localStorage。"""
    state_path = _storage_state_path()
    if not state_path.exists():
        return False
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        cookies = state.get("cookies", [])
        if cookies:
            context.add_cookies(cookies)

        origins = state.get("origins", [])
        for origin_data in origins:
            origin = origin_data.get("origin", "")
            ls_items = origin_data.get("localStorage", [])
            if ls_items and origin:
                try:
                    page.goto(origin, wait_until="domcontentloaded", timeout=15000)
                    for item in ls_items:
                        try:
                            page.evaluate(
                                "([k, v]) => window.localStorage.setItem(k, v)",
                                [item["name"], item["value"]],
                            )
                        except Exception:
                            continue
                except Exception:
                    continue
        return True
    except Exception:
        return False


def send_report(report_path: str, url: str = DEFAULT_URL, auto: bool = True,
                headless: bool = False) -> int:
    report_file = Path(report_path)
    if not report_file.exists():
        print(f"错误：报告文件不存在：{report_path}")
        return 1

    report_text = report_file.read_text(encoding="utf-8")
    info = parse_report(report_path)

    SHARED_BROWSER_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(SHARED_BROWSER_DIR),
            headless=headless,
            viewport={"width": 1280, "height": 800},
        )

        page = context.pages[0] if context.pages else context.new_page()

        # 优先恢复 storage_state（含 Cookie + localStorage）
        restored = _restore_storage_state(context, page, url)

        global _context_ref
        _context_ref = context
        signal.signal(signal.SIGINT, _signal_handler)

        try:
            # 导航到会话 URL
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(3)

            if not _check_session_valid(page):
                print("\n⚠️ DeepSeek 登录态已失效，请在浏览器中手动登录。")
                print("登录完成后按回车继续...")
                try:
                    input()
                except EOFError:
                    print("错误：EOF when reading a line")
                page.wait_for_load_state("domcontentloaded", timeout=30000)
                _save_state(context)
                if not _check_session_valid(page):
                    print("错误：登录失败，无法继续。")
                    print(f"交付报告已保存至：{report_path}")
                    print("请手动复制内容发送至监管会话。")
                    return 1

            input_loc = _try_selectors(page, INPUT_SELECTORS, timeout=3000)
            if not input_loc:
                print(f"\n错误：无法定位DeepSeek输入框。可能网页结构已变更。")
                print(f"交付报告已保存至：{report_path}")
                print("请手动复制内容发送至监管会话。")
                _save_state(context)
                return 2

            send_text = f"项目负责人交付\n\n{report_text}"
            input_loc.click()
            input_loc.fill(send_text)

            print(format_summary(info))

            if auto:
                page.keyboard.press("Enter")
                time.sleep(2)
                print("✅ 报告已发送")

        except Exception as e:
            print(f"错误：{e}")
            return 1
        finally:
            _save_state(context)
            context.close()

    return 0


def main():
    parser = argparse.ArgumentParser(description="发送交付报告到 DeepSeek 监管会话")
    parser.add_argument("report", nargs="?", help="报告文件路径")
    parser.add_argument("--url", default=DEFAULT_URL, help="DeepSeek 会话 URL")
    parser.add_argument("--confirm", action="store_false", dest="auto",
                        help="发送前手动确认")
    parser.add_argument("--headless", action="store_true", help="无头模式运行")
    args = parser.parse_args()

    if not args.report:
        print("用法: python scripts/send_report.py <报告文件> [--url URL] [--confirm] [--headless]")
        print("示例: python scripts/send_report.py docs/delivery_report_2026-06-01.md")
        print("      python scripts/send_report.py docs/delivery_report_2026-06-01.md --headless")
        return

    exit_code = send_report(
        args.report, url=args.url, auto=args.auto, headless=args.headless)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
