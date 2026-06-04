"""验证浏览器登录态是否正确保存和恢复"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    profile = "./browser_profile/persistent"
    
    async with async_playwright() as p:
        print(f"[*] 启动浏览器，使用持久化配置: {profile}")
        context = await p.chromium.launch_persistent_context(
            user_data_dir=profile,
            headless=False,
            viewport={"width": 1400, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
            args=["--disable-blink-features=AutomationControlled"],
        )
        
        # 检查 Cookie 数量
        cookies = await context.cookies()
        print(f"[*] 当前 Cookie 总数: {len(cookies)}")
        
        page = context.pages[0] if context.pages else await context.new_page()
        
        # 访问 BOSS 首页
        print("[*] 访问 BOSS 直聘首页...")
        await page.goto("https://www.zhipin.com/?ka=header-home", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        
        url = page.url
        title = await page.title()
        print(f"    URL: {url}")
        print(f"    标题: {title}")
        
        # 检查是否登录
        url_lower = url.lower()
        body_text = ""
        try:
            body_text = await page.inner_text("body")
        except Exception:
            pass
        
        is_login_page = any(p in url_lower for p in ["/user/", "passport", "login"])
        has_login_text = "扫码" in body_text or "验证码登录" in body_text or "登录" in body_text
        
        if is_login_page:
            print("[!] ❌ 页面是登录页，登录态已过期")
        elif has_login_text:
            print("[!] ❌ 页面显示登录提示，需要重新登录")
        else:
            print("[✓] ✅ 看起来已登录！")
        
        # 检查 zhipin 相关 Cookie
        zhipin_cookies = [c for c in cookies if "zhipin" in c.get("domain", "")]
        print(f"\n[*] BOSS 直聘相关 Cookie 数量: {len(zhipin_cookies)}")
        if zhipin_cookies:
            print("[✓] 找到以下 Cookie:")
            for c in zhipin_cookies[:5]:  # 只显示前5个
                print(f"    - {c.get('name', '')}: {c.get('value', '')[:30]}...")
        
        # 等待 10 秒供观察
        print("\n[*] 等待 10 秒供你观察浏览器状态...")
        await asyncio.sleep(10)
        
        await context.close()
        print("[*] 浏览器已关闭")

if __name__ == "__main__":
    asyncio.run(main())
