"""后台脚本：打开 BOSS 直聘首页并保持浏览器运行"""
import asyncio, sys
sys.path.insert(0, 'src')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

async def main():
    from camoufox import AsyncCamoufox
    from camoufox.addons import DefaultAddons
    from browser_agent.core.session import load_cookies_from_file

    cf = AsyncCamoufox(
        headless=False, humanize=True, geoip=False,
        block_images=False, exclude_addons=[DefaultAddons.UBO],
    )
    ctx = await cf.__aenter__()
    page = await ctx.new_page()
    await page.set_viewport_size({"width": 1920, "height": 1080})
    await page.goto('https://www.zhipin.com/', wait_until='domcontentloaded')

    cookies = await load_cookies_from_file(name="boss")
    if cookies:
        await page.context.add_cookies(cookies)
        await page.reload(wait_until='domcontentloaded')

    print(f'OK: {await page.title()}')
    # 保持运行
    while True:
        await asyncio.sleep(60)

asyncio.run(main())
