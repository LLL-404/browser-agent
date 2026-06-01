"""打开 BOSS 直聘登录界面，等待你登录后自动保存"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    profile = "./browser_profile/persistent"
    
    async with async_playwright() as p:
        print("=" * 50)
        print("  BOSS 直聘 — 登录助手")
        print("=" * 50)
        print(f"[*] 启动浏览器...")
        
        context = await p.chromium.launch_persistent_context(
            user_data_dir=profile,
            headless=False,
            viewport={"width": 1400, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
            args=["--disable-blink-features=AutomationControlled"],
        )
        
        page = context.pages[0] if context.pages else await context.new_page()
        
        # 导航到登录页
        print("[*] 打开登录页面...")
        await page.goto("https://www.zhipin.com/web/user/?ka=header-login", wait_until="domcontentloaded")
        await asyncio.sleep(1)
        
        print()
        print("┌──────────────────────────────────────┐")
        print("│  请在浏览器中完成登录操作              │")
        print("│  支持方式: 扫码 / 手机验证码           │")
        print("│                                      │")
        print("│  登录成功后我会自动检测并保存          │")
        print("└──────────────────────────────────────┘")
        print()
        
        # 等待登录成功（URL 变化）
        initial_url = page.url
        logged_in = False
        
        for i in range(300):  # 最多等 10 分钟
            await asyncio.sleep(2)
            
            current_url = page.url
            
            # 检查是否离开登录页
            if "/user/" not in current_url.lower() and "passport" not in current_url.lower():
                if current_url != initial_url:
                    logged_in = True
                    break
            
            # 每 30 秒提示一次
            if i > 0 and i % 15 == 0:
                minutes = (i * 2) // 60
                seconds = (i * 2) % 60
                print(f"[*] 已等待 {minutes}分{seconds}秒，继续等待...")
        
        if logged_in:
            print()
            print("✅ 检测到登录成功！")
            print("[*] 正在保存登录态...")
            
            # 等待页面稳定
            await asyncio.sleep(3)
            
            # 验证 Cookie
            cookies = await context.cookies()
            zhipin_cookies = [c for c in cookies if "zhipin" in c.get("domain", "")]
            
            print(f"✅ 登录态已保存！")
            print(f"   - 总 Cookie 数量: {len(cookies)}")
            print(f"   - BOSS 直聘 Cookie: {len(zhipin_cookies)} 个")
            print(f"   - 保存位置: {profile}")
            print()
            print("✨ 下次使用时无需重新登录 ✨")
        else:
            print()
            print("❌ 登录超时，请重试")
        
        # 保持浏览器打开几秒让用户确认
        print()
        print("[*] 5 秒后自动关闭浏览器...")
        await asyncio.sleep(5)
        
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
