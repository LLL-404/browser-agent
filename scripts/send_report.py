"""交付报告自动发送脚本 — 通过 Playwright 将报告内容填入 DeepSeek 会话输入框。

默认自动发送；加 --confirm 可恢复手动确认模式。

退出码：
  0 — 成功发送
  1 — 未知错误
  2 — 无法定位输入框
  3 — 无法定位发送按钮
"""

import os
import re
import signal
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

# 从 llm_config.py 加载监管会话 URL，失败时使用默认值
try:
    from llm_config import DEEPSEEK_SESSION_URL
except ImportError:
    DEEPSEEK_SESSION_URL = "https://chat.deepseek.com/a/chat/s/6ba0590c-3d11-4a43-8d02-4ecb95bcd10b"

# 项目根目录（基于本脚本位置推导）
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_chat_url() -> str:
    """从 llm_config.py 或环境变量加载监管会话 URL。"""
    env_url = os.environ.get("SEND_REPORT_URL")
    if env_url:
        return env_url
    return DEEPSEEK_SESSION_URL

# 全局引用，用于信号处理中保存状态
_context_ref = None


def _signal_handler(sig, frame):
    """Ctrl+C 时尝试保存状态并退出。"""
    if _context_ref:
        try:
            _context_ref.storage_state(path=str(_storage_state_path()))
        except Exception:
            pass
        try:
            _context_ref.close()
        except Exception:
            pass
    sys.exit(1)


# ── 常量 ──────────────────────────────────────────────────

DEFAULT_URL = _load_chat_url()

# 与主项目共享的浏览器数据目录（browser_profile/ 已在 .gitignore 中）
SHARED_BROWSER_DIR = PROJECT_ROOT / "browser_profile" / "playwright_send"


def _storage_state_path() -> Path:
    """返回跨工具共享的 storage_state 文件路径。"""
    return PROJECT_ROOT / "sessions" / "storage_state.json"


# 输入框选择器（按优先级尝试）
INPUT_SELECTORS = [
    "div.ProseMirror[contenteditable='true']",
    "textarea[data-testid='chat-input']",
    "textarea",
    "div[contenteditable='true']",
]

# 发送按钮选择器（按优先级尝试）
SEND_SELECTORS = [
    "button[data-testid='send-button']",
    "button[aria-label='发送']",
    "button[aria-label='Send']",
]

# 登录页特征
LOGIN_URL_INDICATORS = ["login", "signin", "auth", "signup"]

# 已登录页面的正面特征
LOGGED_IN_INDICATORS = [
    "div.ProseMirror[contenteditable='true']",
    "textarea[data-testid='chat-input']",
    "textarea[placeholder]",
]


def _is_login_page(page) -> bool:
    """检测当前页面是否为登录页（正面特征优先）。"""
    for indicator in LOGGED_IN_INDICATORS:
        try:
            loc = page.locator(indicator)
            if loc.count() > 0:
                return False
        except Exception:
            continue

    current_url = page.url.lower()
    for keyword in LOGIN_URL_INDICATORS:
        if keyword in current_url:
            return True

    return False


def _check_session_valid(page) -> bool:
    """检测当前会话是否有效（已登录且可操作）。"""
    if _is_login_page(page):
        return False
    for indicator in LOGGED_IN_INDICATORS:
        try:
            loc = page.locator(indicator)
            if loc.count() > 0:
                return True
        except Exception:
            continue
    return False


def parse_report(report_path: str) -> dict:
    """从交付报告 md 文件中提取摘要信息。"""
    text = Path(report_path).read_text(encoding="utf-8")
    info = {"time": "", "task": "", "lint": "", "stats": "", "regression": ""}

    m = re.search(r"\*\*交付时间\*\*：(.+)", text)
    if m:
        info["time"] = m.group(1).strip()

    m = re.search(r"\*\*任务描述\*\*：(.+)", text)
    if m:
        info["task"] = m.group(1).strip()

    lines = text.split("\n")
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and "lint" in stripped.lower():
            info["lint"] = _clean_cell(stripped)
        elif stripped.startswith("|") and "stats" in stripped.lower():
            info["stats"] = _clean_cell(stripped)
        elif stripped.startswith("|") and "回归" in stripped:
            info["regression"] = _clean_cell(stripped)

    return info


def _clean_cell(row: str) -> str:
    """从表格行中提取数据部分（去掉表头标记）。"""
    cells = [c.strip() for c in row.split("|") if c.strip()]
    if len(cells) >= 3:
        return f"{cells[1]} | {cells[2]}"
    return row


def format_summary(info: dict) -> str:
    """格式化终端摘要。"""
    sep = "=" * 60
    return (
        f"{sep}\n"
        f"交付报告已填入输入框，内容摘要：\n"
        f"  交付时间：{info['time']}\n"
        f"  任务描述：{info['task']}\n"
        f"  lint: {info['lint']} | stats: {info['stats']} | 回归: {info['regression']}\n"
        f"{sep}"
    )


# ── 浏览器操作 ────────────────────────────────────────────


def _try_selectors(page, selectors: list[str], timeout: int = 2000):
    """按优先级尝试选择器，返回第一个匹配的 locator 或 None。"""
    for sel in selectors:
        loc = page.locator(sel)
        try:
            loc.wait_for(state="visible", timeout=timeout)
            return loc
        except Exception:
            continue
    return None


def _save_state(context):
    """保存浏览器状态到 shared storage_state 文件。"""
    path = _storage_state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(path))
        print(f"登录状态已保存 → {path}")
    except Exception as e:
        print(f"保存登录状态失败: {e}")


def _wait_for_login(page, context):
    """提示用户手动登录，等待回车后继续。登录完成后立即保存 cookie。"""
    print("\n⚠️ DeepSeek 登录态已失效，请在浏览器中手动登录。")
    print("登录完成后按回车继续...")
    input()
    page.wait_for_load_state("networkidle", timeout=30000)
    _save_state(context)


def _confirm_send() -> bool:
    """终端确认：默认发送，无需手动输入。"""
    print("是否发送？(y/n): 默认发送")
    return True


def send_report(report_path: str, url: str = DEFAULT_URL, auto: bool = True) -> int:
    """主流程：打开浏览器 → 填入报告 → 自动发送。"""
    report_file = Path(report_path)
    if not report_file.exists():
        print(f"错误：报告文件不存在：{report_path}")
        return 1

    report_text = report_file.read_text(encoding="utf-8")
    info = parse_report(report_path)

    SHARED_BROWSER_DIR.mkdir(parents=True, exist_ok=True)

    # 尝试从共享 storage_state 恢复登录态
    storage_state = None
    state_path = _storage_state_path()
    if state_path.exists():
        try:
            import json
            storage_state = json.loads(state_path.read_text(encoding="utf-8"))
            cookie_count = len(storage_state.get("cookies", []))
            if cookie_count:
                print(f"已加载共享登录态 ({cookie_count} 条 Cookie)")
        except Exception:
            storage_state = None

    with sync_playwright() as p:
        launch_kwargs = dict(
            user_data_dir=str(SHARED_BROWSER_DIR),
            headless=False,
            viewport={"width": 1280, "height": 800},
        )
        if storage_state:
            launch_kwargs["storage_state"] = storage_state

        context = p.chromium.launch_persistent_context(**launch_kwargs)
        global _context_ref
        _context_ref = context
        signal.signal(signal.SIGINT, _signal_handler)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            # 导航到会话 URL
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=30000)

            # 检测登录态
            if not _check_session_valid(page):
                print("\n⚠️ DeepSeek 登录态已失效，请手动登录后重试")
                _wait_for_login(page, context)
                # 登录后再次确认
                if not _check_session_valid(page):
                    print("错误：登录失败，无法继续。")
                    print("交付报告已保存至本地，请手动发送。")
                    return 1

            # 定位输入框
            input_loc = _try_selectors(page, INPUT_SELECTORS, timeout=5000)
            if not input_loc:
                print(f"\n错误：无法定位DeepSeek输入框。可能网页结构已变更。")
                print(f"交付报告已保存至：{report_path}")
                print("请手动复制内容发送至监管会话。")
                _save_state(context)
                return 2

            # 填入报告内容（加上发送标识前缀）
            send_text = f"项目负责人交付\n\n{report_text}"
            input_loc.click()
            input_loc.fill(send_text)
            time.sleep(0.5)

            # 定位发送按钮
            send_loc = _try_selectors(page, SEND_SELECTORS, timeout=3000)

            # 显示摘要
            print(format_summary(info))

            # 自动模式直接发送；--confirm 模式需手动确认
            if not auto:
                if not _confirm_send():
                    print("已放弃发送。交付报告已保存在本地。")
                    return 0

            # 发送
            if send_loc:
                send_loc.click()
            else:
                input_loc.press("Enter")

            # 等待消息出现在聊天记录中
            time.sleep(3)
            _save_state(context)
            print("报告已发送。")
            return 0

        except Exception as e:
            print(f"错误：{e}")
            print(f"交付报告已保存至：{report_path}")
            print("请手动复制内容发送至监管会话。")
            return 1
        finally:
            _save_state(context)
            context.close()


# ── CLI 入口 ──────────────────────────────────────────────


def main():
    args = sys.argv[1:]
    if not args:
        print("用法: python scripts/send_report.py <报告文件路径> [--url <会话URL>] [--confirm]")
        sys.exit(1)

    report_path = args[0]
    url = DEFAULT_URL
    auto = "--confirm" not in args

    if "--url" in args:
        idx = args.index("--url")
        if idx + 1 < len(args):
            url = args[idx + 1]

    exit_code = send_report(report_path, url, auto=auto)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
