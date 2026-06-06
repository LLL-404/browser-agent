#!/usr/bin/env python3
"""登录企查查并保存登录态 + 用户信息。"""
import asyncio, json, sys
from pathlib import Path
from playwright.async_api import async_playwright

SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

LOGIN_COOKIES = ["qcc_token", "QCC_SESSION", "QCCSESSID", "auth_token"]
USER_INFO_FILE = SESSIONS_DIR / "qcc_user_info.json"

def eprint(*a, **kw):
    """Print with forced utf-8 encoding."""
    s = " ".join(str(x) for x in a) + kw.get("end", "\n")
    sys.stdout.buffer.write(s.encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch_persistent_context(
            user_data_dir="./browser_profile_qcc",
            headless=False,
            viewport={"width": 1280, "height": 900},
            args=["--start-maximized"],
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()
        await page.goto("https://www.qcc.com", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        eprint("=" * 55)
        eprint("企查查登录助手")
        eprint("=" * 55)
        eprint("浏览器已打开，请在页面中完成登录（扫码/手机号）")
        eprint("脚本将自动检测登录状态并保存")
        eprint()

        initial_cookies = await browser.cookies()
        initial_cnames = {c["name"] for c in initial_cookies}
        start = asyncio.get_event_loop().time()
        timeout = 600
        detected = False

        while asyncio.get_event_loop().time() - start < timeout:
            elapsed = int(asyncio.get_event_loop().time() - start)
            try:
                cookies = await browser.cookies()
                cnames = {c["name"] for c in cookies}
                important = [n for n in cnames if any(kw in n.lower() for kw in ["token", "auth", "session", "sid"])]
                new_important = [n for n in important if n not in initial_cnames]
                if new_important:
                    eprint(f"检测到登录: Cookie 出现 {new_important}")
                    detected = True
                    break
                # also check URL change
                cur = page.url
                if "/login" not in cur.lower():
                    has_user = False
                    for sel in ["a:has-text('退出')", "span:has-text('退出')", ".user-name", ".user-info"]:
                        try:
                            el = page.locator(sel).first
                            if await el.count() > 0 and await el.is_visible():
                                has_user = True
                                break
                        except: pass
                    if has_user:
                        eprint("检测到登录: 页面出现用户元素")
                        detected = True
                        break
            except: pass

            if elapsed > 0 and elapsed % 30 == 0:
                eprint(f"已等待 {elapsed} 秒... 请完成登录")
            await asyncio.sleep(3)

        if detected:
            await asyncio.sleep(3)
            eprint("登录检测成功，正在保存...")

        # Always try to save
        state = await browser.storage_state()
        save_path = SESSIONS_DIR / "qcc_storage_state.json"
        save_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        eprint(f"登录态已保存: {save_path}")
        eprint(f"Cookie 数量: {len(state.get('cookies', []))}")
        eprint(f"文件大小: {save_path.stat().st_size} bytes")

        # Extract user info
        try:
            user_info = {}
            for c in state.get("cookies", []):
                if any(kw in c["name"].lower() for kw in ["user", "name", "phone", "mobile", "login"]):
                    user_info[c["name"]] = c["value"][:50]
            # Try to scrape user name from page
            try:
                title = await page.title()
                user_info["page_title"] = title
            except: pass
            for sel in [".user-name", ".user-info", ".top-user-name", ".header-user-name"]:
                try:
                    el = page.locator(sel).first
                    if await el.count() > 0:
                        txt = await el.text_content()
                        if txt:
                            user_info["display_name"] = txt.strip()
                            break
                except: pass

            if user_info:
                USER_INFO_FILE.write_text(json.dumps(user_info, ensure_ascii=False, indent=2), encoding="utf-8")
                eprint(f"用户信息已保存: {USER_INFO_FILE}")
                for k, v in user_info.items():
                    eprint(f"  {k}: {v}")
            else:
                eprint("未提取到用户信息（Cookie中无用户字段）")
        except Exception as ex:
            eprint(f"提取用户信息失败: {ex}")

        await browser.close()
        eprint("完成")

asyncio.run(main())
