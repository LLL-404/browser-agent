#!/usr/bin/env python3
"""终极方案：打开 Playwright 浏览器（最大化、置顶），等待 Boss 登录后保存。"""
import asyncio, json, time
from pathlib import Path

SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

LOGIN_DETECT_COOKIES = [
    "auth_token", "TYC_USER_INFO", "tyc-user-info",
    "tyc_token", "TYC_SESSION", "CUID", "TYCID",
    "qcc_token", "QCCSESSID",
]


async def main():
    from playwright.async_api import async_playwright

    url = "https://www.tianyancha.com/login"

    print("=" * 55)
    print("  天眼查登录 — Playwright 浏览器")
    print("=" * 55)
    print()
    print(f"  新浏览器窗口已打开（非您当前的 Chrome）")
    print(f"  URL: {url}")
    print()
    print("  📌 请在此浏览器窗口中完成天眼查登录（扫码/手机号）")
    print("  ⏳ 登录后程序自动检测并保存（最长 10 分钟）")
    print()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch_persistent_context(
            user_data_dir="./browser_profile_tyc",
            headless=False,
            viewport={"width": 1280, "height": 900},
            args=[
                "--start-maximized",
                "--window-position=100,50",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        page = browser.pages[0] if browser.pages else await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # Initial state
        await asyncio.sleep(3)
        initial_cookies = await browser.cookies()
        initial_cnames = {c["name"] for c in initial_cookies}
        initial_url = page.url

        start = time.time()
        timeout = 600
        detected = False

        while time.time() - start < timeout:
            elapsed = int(time.time() - start)
            try:
                current_url = page.url
                current_cookies = await browser.cookies()
                current_cnames = {c["name"] for c in current_cookies}
                new_cookies = current_cnames - initial_cnames

                # Priority 1: Auth cookies appeared
                important = [n for n in new_cookies if any(kw in n.lower() for kw in ["token", "auth", "session", "user", "sid"])]
                if important:
                    print(f"\n  ✅ 检测到登录: 重要 Cookie 出现 {important}")
                    detected = True
                    break

                # Priority 2: URL changed from /login
                if "/login" in current_url.lower() and "/login" not in initial_url.lower():
                    print(f"\n  ✅ 检测到登录: URL 跳转至 {current_url[:80]}")
                    detected = True
                    break
                if "login" not in current_url.lower() and "login" in initial_url.lower():
                    print(f"\n  ✅ 检测到登录: URL 跳转至 {current_url[:80]}")
                    detected = True
                    break

                # Priority 3: User indicator elements
                for sel in ["a:has-text('退出')", "span:has-text('退出')",
                            ".user-name", ".header-user-name",
                            ".user-wrapper", ".user-info"]:
                    try:
                        loc = page.locator(sel).first
                        if await loc.count() > 0 and await loc.is_visible():
                            print(f"\n  ✅ 检测到登录: 用户元素 {sel}")
                            detected = True
                            break
                    except Exception:
                        continue
                if detected:
                    break

            except Exception:
                pass

            if elapsed > 0 and elapsed % 30 == 0:
                print(f"  ⏳ 已等待 {elapsed} 秒，URL={page.url[:60]}")

            await asyncio.sleep(3)

        await asyncio.sleep(3)

        is_tyc = "tianyancha" in url
        if is_tyc:
            save_path = SESSIONS_DIR / "tyc_storage_state.json"
        else:
            save_path = SESSIONS_DIR / "qcc_storage_state.json"

        state = await browser.storage_state()
        save_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n✅ 登录态已保存至 {save_path}")
        print(f"   Cookie: {len(state.get('cookies', []))} 个")
        print(f"   大小: {save_path.stat().st_size} bytes")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
