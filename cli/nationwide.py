"""全国范围搜化工安全相关职位，大专可+包吃住。"""
import asyncio
import sys
import json
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.agent import BrowserAgent

_JSON_ERRORS = (Exception,)

# 全国主要化工城市
CITIES = [
    ("南京", "101190100"), ("苏州", "101190400"), ("常州", "101191100"),
    ("宁波", "101210400"), ("杭州", "101210100"),
    ("广州", "101280100"), ("深圳", "101280600"), ("佛山", "101280300"),
    ("武汉", "101200100"),
    ("合肥", "101220100"),
    ("郑州", "101180100"),
    ("沧州", "101090700"), ("唐山", "101090500"),
    ("成都", "101270100"), ("重庆", "101040100"),
]


def _parse_json(data):
    if isinstance(data, str):
        try:
            return json.loads(data)
        except _JSON_ERRORS:
            return {}
    return data


async def main():
    agent = BrowserAgent()
    await agent.open(headless=False)
    await asyncio.sleep(1)

    import urllib.parse
    for city_name, city_code in CITIES:
        print(f"\n{'='*50}")
        print(f"  {city_name}")
        print(f"{'='*50}")

        for kw in ["化工", "安全", "环保"]:
            query = urllib.parse.quote(kw)
            url = f"https://www.zhipin.com/web/geek/job?query={query}&city={city_code}"
            await agent.navigate(url)
            await asyncio.sleep(2)

            js = """(() => {
                const cards = document.querySelectorAll('li.job-card-box');
                const results = [];
                const limit = Math.min(cards.length, 10);
                for (let i = 0; i < limit; i++) {
                    const c = cards[i];
                    const title = (c.querySelector('.job-name') || {}).innerText || '';
                    const salary = (c.querySelector('.job-salary') || {}).innerText || '';
                    const tag_els = c.querySelectorAll('.tag-list li, .job-tags span');
                    const tags = Array.from(tag_els)
                        .map(el => el.innerText.trim()).filter(Boolean);
                    const edu = tags.filter(t =>
                        t.includes('大专') || t.includes('本科')
                        || t.includes('学历不限') || t.includes('中专')
                    );
                    results.push({title, salary, education: edu});
                }
                return JSON.stringify({total: cards.length, results});
            })()"""
            result = await agent.execute_js(js)
            data = _parse_json(result.get("result", "{}"))
            rows = data.get("results", [])
            if isinstance(rows, list):
                for r in rows:
                    title = r.get("title", "")
                    salary = r.get("salary", "")
                    edu = r.get("education", [])
                    edu_str = " | ".join(edu) if edu else "（无学历标签）"
                    has_ben = any("本科" in e for e in edu)
                    has_junior = any("大专" in e for e in edu)
                    has_any = any("不限" in e for e in edu)
                    if not has_ben or has_junior or has_any:
                        print(f"  [{salary}] {title} | {edu_str}")

        print()

    print("\n✅ 全国搜索完成，浏览器保持打开。")
    try:
        while True:
            await asyncio.sleep(30)
    except KeyboardInterrupt:
        pass


asyncio.run(main())