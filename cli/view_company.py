"""自动查看各职位详情（无需手动按 Enter）。"""
import asyncio, sys, json
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.agent import BrowserAgent

_VIEW_ERRORS = (Exception,)

# (公司, 城市, 职位关键词)
TARGETS = [
    ("英科医疗科技", "枣庄", "安全专员"),
    ("渤洋化工", "济宁", "化工中控调度员"),
    ("广通新材料", "枣庄", "化验员"),
    ("山东达沃", "济南", "化工外贸员"),
]

async def get_detail(agent: BrowserAgent, company: str, city: str, job_title: str):
    code = {"济南": "101120100", "济宁": "101120800", "临沂": "101121000", "枣庄": "101120300"}.get(city, "101120100")
    import urllib.parse
    url = f"https://www.zhipin.com/web/geek/job?query={urllib.parse.quote(company)}&city={code}"
    await agent.navigate(url)
    await asyncio.sleep(3)

    # 点击目标职位
    await agent.click(job_title, mode="text")
    await asyncio.sleep(2)

    # 用 JS 提取详情
    js = """
    (() => {
        const text = document.body.innerText || '';
        // 提取关键信息
        const lines = text.split('\\n').map(l => l.trim()).filter(Boolean);

        const result = {};
        let descStarted = false;
        let desc = [];

        for (const line of lines) {
            if (/职位描述|工作内容|岗位职责|任职资格/.test(line)) descStarted = true;
            if (descStarted) desc.push(line);
        }
        result.description = desc.slice(0, 80).join('\\n');

        // 提取薪资、学历、工作经验、福利关键词
        const salary_match = text.match(/[][-.~～][]K/g);
        result.salary = salary_match ? salary_match[0] : '';

        const benefits = [];
        const benefit_kw = ['五险一金','公积金','五险','包吃','包住','住宿','食堂','餐补','班车','双休',
            '大小周','单休','朝九晚五','朝九晚六','补贴','宿舍','免费'];
        for (const kw of benefit_kw) {
            if (text.includes(kw)) benefits.push(kw);
        }
        result.benefits = [...new Set(benefits)];

        const edu = [];
        const edu_kw = ['大专','本科','硕士','学历不限','中专','博士'];
        for (const kw of edu_kw) {
            if (text.includes(kw)) edu.push(kw);
        }
        result.education = [...new Set(edu)];

        return JSON.stringify(result);
    })()
    """
    result = await agent.execute_js(js)
    data = result.get("result", "{}")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except _VIEW_ERRORS:
            data = {}
    return data


async def main():
    agent = BrowserAgent()
    await agent.open(headless=False)
    await asyncio.sleep(1)

    for company, city, job_title in TARGETS:
        print(f"\n{'='*55}")
        print(f"  {company} — {job_title}（{city}）")
        print(f"{'='*55}")

        detail = await get_detail(agent, company, city, job_title)
        print(f"  💰 薪资: {detail.get('salary', '未知')}")
        print(f"  🎓 学历要求: {', '.join(detail.get('education', ['未知']))}")
        print(f"  🎁 福利关键词: {', '.join(detail.get('benefits', ['无']))}")
        desc = detail.get('description', '')
        if desc:
            # 提取福利待遇部分
            lines = desc.split('\n')
            for i, line in enumerate(lines):
                if any(kw in line for kw in ['福利', '待遇', '薪资', '五险', '公积金', '住宿', '食堂', '餐', '班车', '双休', '补贴']):
                    # 输出福利相关行及上下文
                    for j in range(max(0,i-1), min(len(lines), i+4)):
                        if lines[j].strip():
                            print(f"    {lines[j].strip()}")
        print()

    print(f"\n{'='*55}")
    print("✅ 所有信息已提取完毕，浏览器保持打开供您查看。")
    try:
        while True:
            await asyncio.sleep(30)
    except KeyboardInterrupt:
        pass

asyncio.run(main())