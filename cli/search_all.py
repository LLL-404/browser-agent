"""全国校招/应届搜索 — 使用 Camoufox，自动提取并保存结果。"""
import asyncio
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.agent import BrowserAgent
from core.logging_config import setup_logging, get_logger

setup_logging(log_to_console=True, log_to_file=True)
logger = get_logger("nationwide")

_JSON_ERRORS = (Exception,)


def _safe_json(data):
    if isinstance(data, str):
        try:
            return json.loads(data)
        except _JSON_ERRORS:
            return {}
    return data


async def search_and_extract(agent, city_name, city_code, keyword):
    """搜一个城市+关键词，提取30条职位。"""
    import urllib.parse
    result = []
    try:
        query = urllib.parse.quote(keyword)
        url = f"https://www.zhipin.com/web/geek/job?query={query}&city={city_code}"
        await agent.navigate(url)
        await asyncio.sleep(3)

        js = """(() => {
            const cards = document.querySelectorAll('.job-card-box');
            const results = [];
            for (let i = 0; i < Math.min(cards.length, 15); i++) {
                const c = cards[i];
                const title = (c.querySelector('.job-name') || {}).innerText || '';
                const salary = (c.querySelector('.job-salary') || {}).innerText || '';
                const tags = Array.from(c.querySelectorAll('.tag-list li, .job-info-require li, .job-tags span'))
                    .map(el => el.innerText.trim()).filter(Boolean);
                const company = (c.querySelector('.company-name') || {}).innerText || '';
                const self_text = c.innerText || '';
                results.push({title, salary, tags, company, self_text: self_text.substring(0, 200)});
            }
            return JSON.stringify({total: cards.length, results});
        })()"""
        raw = await agent.execute_js(js)
        data = _safe_json(raw.get("result", "{}"))
        rows = data.get("results", [])
        for r in rows:
            r["city"] = city_name
            r["keyword"] = keyword
            result.append(r)
        logger.info("  %s / %s → %d 条", city_name, keyword, len(result))
    except _JSON_ERRORS as exc:
        logger.warning("  %s / %s 搜索失败: %s", city_name, keyword, exc)
    return result


async def main():
    cities = [
        ("北京", "101010100"), ("上海", "101020100"),
        ("广州", "101280100"), ("深圳", "101280600"),
        ("杭州", "101210100"), ("南京", "101190100"),
        ("苏州", "101190400"), ("武汉", "101200100"),
        ("成都", "101270100"), ("重庆", "101040100"),
        ("合肥", "101220100"), ("郑州", "101180100"),
        ("西安", "101110100"), ("长沙", "101250100"),
        ("天津", "101030100"), ("青岛", "101120200"),
    ]
    keywords = ["化工 应届", "安全 大专", "质检 应届", "环保 校招"]

    agent = BrowserAgent()
    logger.info("正在启动 Camoufox...")
    await agent.open(headless=False)
    await asyncio.sleep(2)

    all_results = []
    total = len(cities) * len(keywords)
    done = 0
    for city_name, city_code in cities:
        for kw in keywords:
            done += 1
            logger.info("[%d/%d] %s: %s", done, total, city_name, kw)
            items = await search_and_extract(agent, city_name, city_code, kw)
            all_results.extend(items)
            await asyncio.sleep(1.5)

    out = Path("data/nationwide_results.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(all_results, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    logger.info("✅ 搜索完成！共 %d 条，已保存到 %s", len(all_results), out)

    # 快速汇总
    for r in all_results:
        tags_str = " | ".join(r.get("tags", []))
        edu = [t for t in r.get("tags", []) if any(x in t for x in ["大专", "本科", "不限", "中专"])]
        if not any("本科" in t for t in edu):
            print(f"  [{r['salary']}] {r['title']} @{r['company']}({r['city']}) | {tags_str}")

    print("\n浏览器保持打开，按 Ctrl+C 关闭。")
    try:
        while True:
            await asyncio.sleep(30)
    except KeyboardInterrupt:
        pass


asyncio.run(main())