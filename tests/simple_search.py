"""最简测试：用持久化浏览器直接搜索，看能否找到卡片"""
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir="./browser_profile/persistent",
            headless=False,
            viewport={"width": 1400, "height": 900},
        )
        page = context.pages[0] if context.pages else await context.new_page()
        
        # 直接导航搜索页
        url = "https://www.zhipin.com/web/geek/job?city=101280600&query=普工"
        print(f"[→] goto {url}")
        await page.goto(url, wait_until="networkidle")
        print(f"    final_url: {page.url[:100]}")
        print(f"    title: {await page.title()}")
        
        # 尝试查找卡片
        try:
            await page.wait_for_selector("li.job-card-box", timeout=10000)
            cards = await page.query_selector_all("li.job-card-box")
            print(f"    cards found: {len(cards)}")
            if cards:
                title = await cards[0].query_selector(".job-name")
                company = await cards[0].query_selector(".boss-name")
                print(f"    card 0 title: {await title.inner_text()}")
                print(f"    card 0 company: {await company.inner_text()}")
        except Exception as e:
            print(f"    [✗] {e}")
            # 截图
            await page.screenshot(path="tests/output/debug.png")
            print(f"    截图已保存: tests/output/debug.png")
            body = await page.inner_text("body")
            print(f"    body text (first 200): {body[:200]}")
        
        await asyncio.sleep(3)
        await context.close()

if __name__ == "__main__":
    asyncio.run(test())
