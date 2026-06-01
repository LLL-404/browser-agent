import asyncio
from playwright.async_api import async_playwright


async def smoke_test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        await page.goto("https://www.zhipin.com/web/geek/job")
        await page.wait_for_timeout(3000)
        title = await page.title()
        print(f"页面标题: {title}")
        print("冒烟测试通过！关闭浏览器...")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(smoke_test())
