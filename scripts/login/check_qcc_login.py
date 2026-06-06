"""验证企查查登录状态 — 使用 browser_profile_qcc 持久化 Profile。"""
import asyncio
import sys
from playwright.async_api import async_playwright

PROFILE_DIR = "./browser_profile_qcc"


def eprint(*a, **kw):
    s = " ".join(str(x) for x in a) + kw.get("end", "\n")
    sys.stdout.buffer.write(s.encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()


async def main():
    async with async_playwright() as p:
        eprint("[*] 使用 browser_profile_qcc 启动浏览器...")
        context = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            viewport={"width": 1280, "height": 900},
        )

        cookies = await context.cookies()
        eprint(f"[*] Cookie 总数: {len(cookies)}")

        # 筛选企查查相关 Cookie
        qcc_cookies = [c for c in cookies if "qcc.com" in c.get("domain", "")]
        eprint(f"[*] 企查查域名 Cookie: {len(qcc_cookies)}")

        page = context.pages[0] if context.pages else await context.new_page()

        eprint("[*] 访问企查查首页...")
        await page.goto("https://www.qcc.com", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        url = page.url
        title = await page.title()
        eprint(f"    URL: {url}")
        eprint(f"    标题: {title}")

        # 检测是否已登录
        body_text = ""
        try:
            body_text = await page.inner_text("body")
        except Exception:
            pass

        is_login = False
        for sel in [
            'a:has-text("退出")',
            'span:has-text("退出")',
            ".user-name",
            ".user-info",
            ".top-user-name",
        ]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0 and await el.is_visible():
                    txt = (await el.text_content() or "").strip()
                    eprint(f"[OK] 检测到用户元素 [{sel}]: {txt}")
                    is_login = True
                    break
            except Exception:
                pass

        if not is_login:
            has_login_btn = any(
                kw in body_text for kw in ["扫码登录", "密码登录", "账号登录"]
            )
            if has_login_btn:
                eprint("[!] 未登录 - 页面显示登录入口")
            else:
                eprint("[?] 无法确定登录状态")

        # 检查关键认证 Cookie
        auth_names = ["qcc_token", "QCC_SESSION", "QCCSESSID", "auth_token"]
        found_auth = {
            c["name"]: c["value"][:20] + "..."
            for c in cookies
            if c["name"] in auth_names
        }
        if found_auth:
            eprint("[*] 认证 Cookie:")
            for k, v in found_auth.items():
                eprint(f"    {k}: {v}")
        else:
            eprint("[!] 未找到认证 Cookie")

        # 尝试访问需要登录的页面验证
        eprint("\n[*] 验证企业详情页（需登录）...")
        try:
            await page.goto(
                "https://www.qcc.com/firm/enterprise-detail.html",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            await asyncio.sleep(2)
            verify_url = page.url
            if "login" in verify_url.lower():
                eprint("[!] 企业详情页被重定向到登录页 — 登录态无效")
            else:
                eprint(f"[OK] 企业详情页可正常访问: {verify_url}")
        except Exception as ex:
            eprint(f"[!] 验证页面异常: {ex}")

        eprint("\n[*] 等待 5 秒供观察...")
        await asyncio.sleep(5)

        await context.close()
        eprint("[*] 完成")


if __name__ == "__main__":
    asyncio.run(main())
