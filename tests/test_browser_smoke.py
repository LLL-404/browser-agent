"""浏览器冒烟测试 — 验证 Playwright 可启动并访问 BOSS 直聘首页。"""

from playwright.sync_api import sync_playwright

BOSS_URL = "https://www.zhipin.com/?ka=header-home"
EXPECTED_TITLE = "BOSS直聘"


def test_boss_homepage_loads():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        page = context.new_page()
        page.goto(BOSS_URL, wait_until="domcontentloaded", timeout=30000)
        assert EXPECTED_TITLE in page.title(), f"页面标题不含'{EXPECTED_TITLE}'，实际：{page.title()}"
        browser.close()
