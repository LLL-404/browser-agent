#!/usr/bin/env python3
"""
保存企查查/天眼查登录态。

流程：打开首页 → 点登录按钮 → 弹窗登录 → 轮询检测登录态 → 保存
处理浏览器意外关闭/页面导航等情况。
"""

from __future__ import annotations
import time, sys, traceback
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

BROWSER_DIR = Path("browser_profile/save_login")
SESSIONS_DIR = Path("sessions")

PLATFORMS = [
    {
        "name": "企查查",
        "url": "https://www.qcc.com",
        "state_file": "qcc_storage_state.json",
    },
    {
        "name": "天眼查",
        "url": "https://www.tianyancha.com",
        "state_file": "tyc_storage_state.json",
    },
]

LOGIN_BTN_SELECTORS = [
    "button:has-text('登录')",
    "a:has-text('登录')",
    "span:has-text('登录')",
    "div:has-text('登录')",
    ".login-btn",
    "a[href*='login']",
    ".header-login",
    "a.nav-login",
]

USER_INDICATORS = [
    "img[alt*='avatar']",
    ".user-avatar",
    ".user-info",
    ".top-user-name",
    ".user-name",
    "a[href*='user/center']",
    "a[href*='user_center']",
    "button:has-text('退出')",
    "a:has-text('退出')",
]


def get_or_create_page(context):
    if context.pages:
        try:
            p = context.pages[0]
            p.title()  # probe alive
            return p
        except Exception:
            pass
    return context.new_page()


def is_logged_in(page) -> bool:
    for sel in USER_INDICATORS:
        try:
            if page.locator(sel).first.count() > 0 and page.locator(sel).first.is_visible():
                return True
        except Exception:
            continue
    return False


def click_login(page) -> bool:
    for sel in LOGIN_BTN_SELECTORS:
        try:
            el = page.locator(sel).first
            if el.count() > 0 and el.is_visible():
                print(f"  → 点击登录按钮: {sel}")
                el.click()
                time.sleep(2)
                return True
        except Exception:
            continue
    return False


def wait_for_login(page, name: str, timeout=600) -> bool:
    print(f"\n  📌 请在浏览器中完成 {name} 登录（扫码/手机号验证码）")
    print(f"  ⏳ 轮询检测中（最长 {timeout} 秒）...")
    start = time.time()
    while time.time() - start < timeout:
        elapsed = int(time.time() - start)
        try:
            if is_logged_in(page):
                print(f"\n  ✅ 登录成功！耗时 {elapsed} 秒")
                return True
            # also detect newly created pages (login sometimes opens new tab)
            for p in page.context.pages:
                if p != page:
                    try:
                        if is_logged_in(p):
                            print(f"\n  ✅ 在新标签页中检测到登录成功")
                            return True
                    except Exception:
                        pass
        except Exception:
            # page might have been closed, try to get a new one
            try:
                page = get_or_create_page(page.context)
                page.goto(PLATFORMS[0]["url"] if "企查查" in name else PLATFORMS[1]["url"],
                          wait_until="domcontentloaded", timeout=15000)
                time.sleep(2)
            except Exception:
                pass

        if elapsed > 0 and elapsed % 15 == 0:
            print(f"  ⏳ 已等待 {elapsed} 秒...")
        time.sleep(3)

    print(f"\n  ⚠️ 登录等待超时")
    return False


def process(context, plat):
    name = plat["name"]
    state_path = SESSIONS_DIR / plat["state_file"]

    print(f"\n{'='*60}")
    print(f"🔵 {name} — {plat['url']}")
    print(f"{'='*60}")

    page = get_or_create_page(context)
    print(f"  打开首页...")
    page.goto(plat["url"], wait_until="domcontentloaded", timeout=20000)
    time.sleep(3)

    if is_logged_in(page):
        print(f"  检测到已登录")
    else:
        ok = click_login(page)
        if not ok:
            print(f"  ⚠️ 未找到登录按钮，尝试直接导航到登录页")
            try:
                page.goto(plat["url"].rstrip("/") + "/login", timeout=15000)
                time.sleep(2)
            except Exception:
                pass

        ok = wait_for_login(page, name)
        if not ok:
            print(f"  跳过 {name}")
            return False

    # Save
    state_path.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(state_path))
    sz = state_path.stat().st_size
    print(f"  ✅ 状态已保存: {state_path} ({sz} bytes)")

    # Verify on protected page
    verify_urls = {
        "企查查": "https://www.qcc.com/firm/enterprise-detail.html",
        "天眼查": "https://www.tianyancha.com/company/",
    }
    vurl = verify_urls.get(name)
    if vurl:
        try:
            page.goto(vurl, wait_until="domcontentloaded", timeout=15000)
            time.sleep(2)
            if is_logged_in(page):
                print(f"  🟢 验证通过 — 企业详情页登录态有效")
            else:
                print(f"  🟡 验证：企业详情页未检测到用户元素（状态仍已保存）")
        except Exception as e:
            print(f"  🟡 验证跳过: {e}")

    return True


def main():
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    BROWSER_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_DIR),
            headless=False,
            viewport={"width": 1280, "height": 800},
        )
        try:
            for plat in PLATFORMS:
                try:
                    process(context, plat)
                except Exception as e:
                    print(f"  ❌ 处理 {plat['name']} 时出错: {e}")
                    traceback.print_exc()
        finally:
            try:
                context.close()
            except Exception:
                pass

    print(f"\n{'='*50}")
    print("✅ 完成")
    for p in PLATFORMS:
        f = SESSIONS_DIR / p["state_file"]
        status = f"✅ {f.stat().st_size} bytes" if f.exists() else "❌ 不存在"
        print(f"   {p['name']}: {status}")


if __name__ == "__main__":
    main()
