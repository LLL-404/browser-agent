"""自动搜索 BOSS 直聘职位，通过页面源代码直接提取数据"""
import asyncio
import json
import sys
from datetime import datetime
from core.browser_controller import BrowserController

sys.stdout.reconfigure(encoding='utf-8')


async def search_zhipin(cities: list[tuple[str, str]], keywords: list[str]):
    """在 BOSS 直聘上搜索职位，用 URL 参数直接跳转搜索页。"""
    ctrl = BrowserController()
    await ctrl.start(headless=False)

    # 先访问首页确认登录
    print("打开 BOSS 直聘…")
    await ctrl.navigate_to("https://www.zhipin.com")
    await asyncio.sleep(3)

    text = await ctrl.get_page_text(1500)
    if "安全验证" in text:
        print("⚠️ 遇到安全验证，请在浏览器中手动处理")
        input("处理完成后按 Enter 继续…")

    print("✅ 准备搜索\n")

    all_jobs = []
    for city_name, city_code in cities:
        for kw in keywords:
            print(f"\n🔍 [{city_name}] 搜索: {kw}")

            search_url = f"https://www.zhipin.com/web/geek/job?query={kw}&city={city_code}"
            await ctrl.navigate_to(search_url)
            await asyncio.sleep(3)

            # 用 JS 直接提取职位列表
            js_code = """
            (() => {
                const cards = document.querySelectorAll('.job-card-wrapper, .job-list li, [class*="job-card"]');
                const results = [];
                const seen = new Set();
                for (const card of cards) {
                    const titleEl = card.querySelector('[class*="job-name"], .job-title, h3, a[class*="name"]');
                    const salaryEl = card.querySelector('[class*="salary"], .job-salary');
                    const companyEl = card.querySelector('[class*="company"], .company-text .name, a[class*="company"]');
                    const areaEl = card.querySelector('[class*="area"], .job-area');
                    const tagsEls = card.querySelectorAll('.job-card-footer .tag-item, .job-tags span, .job-card-body li');
                    const linkEl = card.querySelector('a[href*="job_detail"]') || titleEl?.closest('a');

                    const title = titleEl?.innerText?.trim() || '';
                    const salary = salaryEl?.innerText?.trim() || '';
                    const company = companyEl?.innerText?.trim() || '';
                    const area = areaEl?.innerText?.trim() || '';
                    const tags = Array.from(tagsEls).map(t => t.innerText.trim()).filter(Boolean);
                    const link = linkEl?.href || '';

                    if (title && !seen.has(title + company)) {
                        seen.add(title + company);
                        results.push({ title, salary, company, area, tags, link });
                    }
                }
                return results;
            })()
            """
            result = await ctrl.execute_js(js_code)
            jobs = result.get("result", []) if isinstance(result, dict) else []

            if jobs:
                print(f"  找到 {len(jobs)} 个职位")
                for j in jobs[:10]:
                    print(f"  • {j['title']} | {j['salary']} | {j['company']} | {j['area']}")
                    if j['tags']:
                        print(f"    标签: {', '.join(j['tags'][:5])}")
                    if j['link']:
                        print(f"    链接: {j['link']}")
                all_jobs.extend(jobs)
            else:
                # 如果 JS 提取失败，看页面文本
                page_text = await ctrl.get_page_text(2000)
                print(f"  页面内容预览: {page_text[:300]}")

    # 汇总
    print(f"\n\n{'='*50}")
    print(f"📊 共搜索 {len(cities)} 个城市 × {len(keywords)} 个关键词")
    print(f"  找到 {len(all_jobs)} 个职位")

    # 输出结构化数据
    output = {"search_time": datetime.now().isoformat(),
              "keywords": keywords, "cities": [c[0] for c in cities],
              "total": len(all_jobs), "jobs": all_jobs}
    print(json.dumps(output, ensure_ascii=False, indent=2))

    input("\n按 Enter 关闭浏览器…")
    await ctrl.stop()
    return all_jobs


if __name__ == "__main__":
    # 枣庄 + 附近城市
    DEFAULT_CITIES = [
        ("枣庄", "101120300"),
        ("济宁", "101120800"),
        ("临沂", "101121000"),
        ("徐州", "101190800"),
        ("济南", "101120100"),
    ]
    DEFAULT_KEYWORDS = ["化工安全", "安全员", "EHS", "安全管理", "环保安全"]

    asyncio.run(search_zhipin(DEFAULT_CITIES, DEFAULT_KEYWORDS))
