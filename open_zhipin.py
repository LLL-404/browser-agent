import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        print("正在打开 BOSS 直聘首页...")
        try:
            response = await page.goto("https://www.zhipin.com/?ka=header-home", wait_until="networkidle", timeout=60000)
            print(f"页面加载完成！状态码: {response.status}")
            print(f"当前 URL: {page.url}")
            print(f"页面标题: {await page.title()}")
            
            # 截图
            screenshot_path = "/workspace/zhipin_screenshot.png"
            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"截图已保存到: {screenshot_path}")
            
        except Exception as e:
            print(f"打开页面时出错: {e}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
