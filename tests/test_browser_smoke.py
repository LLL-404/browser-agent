"""浏览器冒烟测试 — 验证 Camoufox 可启动并访问 BOSS 直聘首页。"""

import pytest

BOSS_URL = "https://www.zhipin.com/?ka=header-home"
EXPECTED_TITLE = "BOSS直聘"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_boss_homepage_loads():
    from camoufox import AsyncCamoufox
    from camoufox.addons import DefaultAddons

    browser = await AsyncCamoufox(
        headless=True, humanize=False,
        geoip=False, block_images=True,
        enable_cache=False,
        exclude_addons=[DefaultAddons.UBO],
    ).__aenter__()
    try:
        page = browser.pages[0] if browser.pages else await browser.new_page()
        await page.goto(BOSS_URL, wait_until="domcontentloaded", timeout=30000)
        title = await page.title()
        assert EXPECTED_TITLE in title, f"页面标题不含'{EXPECTED_TITLE}'，实际：{title}"
    finally:
        await browser.__aexit__(None, None, None)
