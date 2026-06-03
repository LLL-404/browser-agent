"""岗位卡片解析测试 — 使用 Mock HTML 测试 _parse_list_card 解析逻辑。"""
import pytest

from playwright.async_api import async_playwright
from modes.zhipin.selectors import JOB_CARD

MOCK_HTML = """
<html><body>
<ul class="job-list-box">
  <li class="job-card-box" data-jid="abc123">
    <a class="job-name" href="/job_detail/abc123.html">测试岗位A</a>
    <span class="boss-name">测试公司A</span>
    <span class="job-salary">8K-12K</span>
    <ul class="tag-list">
      <li>五险一金</li>
      <li>包吃</li>
    </ul>
  </li>
  <li class="job-card-box" data-jid="def456">
    <a class="job-name" href="/job_detail/def456.html">测试岗位B</a>
    <span class="boss-name">测试公司B</span>
    <span class="job-salary">6K-10K</span>
    <ul class="tag-list">
      <li>五险一金</li>
      <li>双休</li>
      <li>不加班</li>
    </ul>
  </li>
  <li class="job-card-box" data-jid="ghi789">
    <a class="job-name" href="/job_detail/ghi789.html">测试岗位C</a>
    <span class="boss-name">测试公司C</span>
    <span class="job-salary">15K-25K</span>
    <ul class="tag-list">
      <li>六险一金</li>
      <li>年终奖</li>
      <li>股票期权</li>
      <li>弹性工作</li>
    </ul>
  </li>
</ul>
</body></html>
"""


@pytest.mark.asyncio
async def test_parse_mock_cards():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(MOCK_HTML, wait_until="domcontentloaded")

        cards = await page.query_selector_all(JOB_CARD)
        assert len(cards) == 3

        from modes.zhipin.scraper import _parse_list_card
        results = []
        for card in cards:
            result = await _parse_list_card(card, "深圳", page)
            results.append(result)

        assert results[0] is not None
        assert results[0]["title"] == "测试岗位A"
        assert results[0]["company"] == "测试公司A"
        assert results[0]["salary"] == "8K-12K"
        assert results[0]["city"] == "深圳"
        assert "五险一金" in results[0]["tags"]
        assert results[0]["boss_job_id"] == "abc123"

        assert results[1]["title"] == "测试岗位B"
        assert results[1]["company"] == "测试公司B"
        assert results[1]["salary"] == "6K-10K"
        assert len(results[1]["tags"]) == 3

        assert results[2]["title"] == "测试岗位C"
        assert results[2]["company"] == "测试公司C"
        assert results[2]["salary"] == "15K-25K"
        assert len(results[2]["tags"]) == 4

        await browser.close()
