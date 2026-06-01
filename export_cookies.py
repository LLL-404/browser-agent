"""一次性 Cookie 导出工具。

用旧持久化 profile 启动浏览器，让用户确认已登录后导出 Cookie。
后续新 session 将使用这些 Cookie 自动登录，不再需要手动操作。
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.browser_controller import BrowserController
from core.cookie_manager import save_cookies_to_file
from core.logging_config import get_logger

logger = get_logger("export")


async def main():
    print("=" * 60)
    print("  BOSS直聘 Cookie 导出工具")
    print("=" * 60)
    print()
    print("此脚本会启动浏览器，请你手动登录 BOSS直聘")
    print("登录成功后按 Enter 键继续，脚本将导出 Cookie")
    print()

    import subprocess
    result = subprocess.run(
        ["where", "camoufox"], capture_output=True, text=True, shell=True
    )
    ctrl = BrowserController()
    try:
        ok = await ctrl.start(headless=False, use_camoufox=True)
        if not ok:
            print("Camoufox 启动失败，尝试 Playwright...")
            ok = await ctrl.start(headless=False, use_camoufox=False)
        if not ok:
            print("浏览器启动失败！")
            return

        await ctrl.navigate_to("https://www.zhipin.com/")
        await asyncio.sleep(3)

        title = await ctrl.get_page_title()
        print(f"页面标题: {title}")

        url = await ctrl.get_current_url()
        print(f"当前 URL: {url}")

        await ctrl.navigate_to("https://www.zhipin.com/web/chat")
        await asyncio.sleep(2)

        url = await ctrl.get_current_url()
        print(f"当前 URL: {url}")
        print()
        print("请在浏览器中确认已登录，然后按 Enter 导出 Cookie...")
        input()

        cookies = await ctrl.save_cookies()
        if not cookies:
            print("未获取到 Cookie，可能未登录")
            return

        result = save_cookies_to_file(cookies, name="boss")
        print()
        print(f"✅ 已导出 {result['count']} 条 Cookie → {result['path']}")
        print("后续新会话将自动注入这些 Cookie，无需手动登录")

    finally:
        await ctrl.stop()


if __name__ == "__main__":
    asyncio.run(main())