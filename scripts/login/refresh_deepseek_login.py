"""打开 DeepSeek，自动检测登录完成并保存 Cookie。"""
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

DEEPSEEK_URL = "https://chat.deepseek.com/a/chat/s/6ba0590c-3d11-4a43-8d02-4ecb95bcd10b"
PROFILE_DIR = str(Path("browser_profile/playwright_send").resolve())

LOGIN_INDICATORS = ["/login", "/signin", "passport", "accounts"]
LOGGED_IN_INDICATORS = [".ds-input", "textarea", '[placeholder*="输入"]', '[contenteditable="true"]']

def is_logged_in(page) -> bool:
    url = page.url.lower()
    if any(k in url for k in LOGIN_INDICATORS):
        return False
    for sel in LOGGED_IN_INDICATORS:
        try:
            if page.locator(sel).count() > 0:
                return True
        except Exception:
            continue
    return False

def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            no_viewport=True,
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(DEEPSEEK_URL, wait_until="domcontentloaded")
        print("浏览器已打开 DeepSeek，请在浏览器中登录...")
        print("正在检测登录状态（每 3 秒检查一次）...")
        while True:
            if is_logged_in(page):
                print("检测到登录成功！正在保存 Cookie...")
                break
            time.sleep(3)
        state = ctx.storage_state()
        state_path = Path("sessions/storage_state.json")
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        cookies = state.get("cookies", [])
        print(f"已保存 {len(cookies)} 条 Cookie → sessions/storage_state.json")
        ctx.close()

if __name__ == "__main__":
    main()
