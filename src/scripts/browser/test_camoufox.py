"""Camoufox BOSS直聘测试脚本"""
import asyncio
from camoufox import AsyncCamoufox
from camoufox.addons import DefaultAddons

async def main():
    print("🦊 Camoufox 启动测试...")
    print("=" * 50)

    try:
        async with AsyncCamoufox(
            headless=False,
            humanize=True,
            geoip=False,
            persistent_context=False,
            block_images=False,
            enable_cache=True,
            window=(1400, 900),
            exclude_addons=[DefaultAddons.UBO],
        ) as browser:
            print("✅ Camoufox 启动成功!")

            page = await browser.new_page()
            print(f"📍 初始URL: {page.url}")

            await page.goto(
                "https://www.zhipin.com/?ka=header-home", wait_until="domcontentloaded"
            )
            print(f"📍 当前URL: {page.url}")
            print(f"📄 标题: {await page.title()}")

            body_text = await page.evaluate(
                '() => document.body?.innerText?.substring(0, 500) || ""'
            )
            print(f"📝 内容预览: {body_text}")

            checks = await page.evaluate("""() => {
                return {
                    webdriver: navigator.webdriver,
                    chrome: typeof window.chrome,
                    plugins: navigator.plugins.length,
                    languages: navigator.languages,
                    platform: navigator.platform,
                    userAgent: navigator.userAgent.substring(0, 100),
                }
            }""")
            print(f"\n🔍 反检测状态:")
            for k, v in checks.items():
                print(f"   {k}: {v}")

            print("\n⏳ 等待5秒后关闭...")
            await asyncio.sleep(5)
            print("✅ 测试完成!")

    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
