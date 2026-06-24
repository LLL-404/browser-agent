"""打开 BOSS 直聘登录界面，等待你登录后自动保存"""
import asyncio
import sys
import io
from pathlib import Path

# 修复 Windows GBK 编码问题
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 确保 session 模块路径可用
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

async def main():
    profile = "./browser_profile/persistent"
    
    print("=" * 50)
    print("  BOSS 直聘 — 登录助手")
    print("=" * 50)
    print(f"[*] 启动浏览器 (Camoufox)...")
    
    # 优先使用 Camoufox，不可用时回退 Playwright
    pw = None
    try:
        from camoufox import AsyncCamoufox
        from camoufox.addons import DefaultAddons
        
        camoufox = AsyncCamoufox(
            headless=False,
            humanize=True,
            geoip=False,
            block_images=False,
            user_data_dir=profile,
            persistent_context=True,
            exclude_addons=[DefaultAddons.UBO],
        )
        context = await camoufox.__aenter__()
        engine = "Camoufox"
    except (ImportError, Exception) as e:
        print(f"[!] Camoufox 不可用 ({e})，回退到 Playwright...")
        from playwright.async_api import async_playwright
        
        pw = await async_playwright().__aenter__()
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=profile,
            headless=False,
            viewport={"width": 1400, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
            args=["--disable-blink-features=AutomationControlled"],
        )
        engine = "Playwright"
    
    print(f"[*] 浏览器引擎: {engine}")
    
    # Camoufox 返回 Browser 对象(无 pages 属性), Playwright 返回 BrowserContext(有 pages)
    pages = getattr(context, 'pages', None)
    page = pages[0] if pages else await context.new_page()
    
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
        print("[OK] 检测到登录成功！")
        print("[*] 正在保存登录态...")
        
        # 等待页面稳定
        await asyncio.sleep(3)
        
        # 获取并保存 Cookie 到文件
        cookies = await context.cookies()
        zhipin_cookies = [c for c in cookies if "zhipin" in c.get("domain", "")]
        
        # 保存到 JSON 文件（搜索流程用这个读取）
        from browser_agent.core.session import save_cookies_to_file
        result = await save_cookies_to_file(cookies, name="boss")
        
        print(f"[OK] 登录态已保存！")
        print(f"   - 总 Cookie 数量: {len(cookies)}")
        print(f"   - BOSS 直聘 Cookie: {len(zhipin_cookies)} 个")
        print(f"   - JSON 文件: {result.get('path', '?')}")
        print(f"   - 浏览器 Profile: {profile}")
        print()
        print("[*] 下次使用时无需重新登录")
    else:
        print()
        print("[FAIL] 登录超时，请重试")
    
    # 保持浏览器打开几秒让用户确认
    print()
    print("[*] 5 秒后自动关闭浏览器...")
    await asyncio.sleep(5)
    
    if engine == "Camoufox":
        await camoufox.__aexit__(None, None, None)
    else:
        await context.close()
        if pw:
            await pw.stop()

if __name__ == "__main__":
    asyncio.run(main())
