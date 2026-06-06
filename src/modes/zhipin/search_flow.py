"""直接用 BrowserAgent（Camoufox）搜索 BOSS 直聘校招职位。"""
import asyncio
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from browser_agent.core.agent import BrowserAgent
from modes.zhipin.city_codes import get_city_code
from modes.zhipin.selectors import CAPTCHA_KEYWORDS
from modes.zhipin.storage import get_stats, init_db, insert_job
from shared.delay import delay
from shared.logging_config import get_logger, setup_logging

setup_logging(log_to_console=True, log_to_file=True)
logger = get_logger("search")


async def main():
    init_db()
    agent = BrowserAgent()
    try:
        logger.info("正在打开 Camoufox 浏览器（非无头，带持久 Cookie）...")
        result = await agent.open(headless=False)
        logger.info("浏览器已打开: %s", result.get("url"))

        await agent.navigate("https://www.zhipin.com/?ka=header-home")
        await delay("page_stable")

        page_data = await agent.text(2000)
        page_text = page_data.get("text", "")
        logger.info("页面文本片段: %s", page_text[:300])

        need_login = any(kw in page_text for kw in [
            "登录", "注册", "请登录", "扫码登录",
        ])
        if need_login:
            logger.warning("需要登录！请在浏览器中手动扫码登录...")
            for i in range(120):
                await delay("login_poll")
                curr = await agent.text(500)
                ct = curr.get("text", "")
                if "登录" not in ct and "请登录" not in ct:
                    logger.info("检测到登录成功！")
                    break
                if i % 20 == 0:
                    curr_url = await agent.url()
                    logger.info("等待登录中... 当前: %s", curr_url.get("url"))
            else:
                logger.error("登录超时")
                return

        cities = ["枣庄", "济宁", "临沂", "徐州", "济南"]
        keywords = ["校招", "应届", "实习生", "化工", "安全"]

        for city in cities:
            for kw in keywords:
                code = get_city_code(city)
                search_url = f"https://www.zhipin.com/web/geek/job?city={code}&query={kw}"
                logger.info("搜索: %s %s", city, kw)
                await agent.navigate(search_url)
                await delay("page_stable")

                snap = await agent.text(1500)
                text = snap.get("text", "")
                if any(kw_cap in text for kw_cap in CAPTCHA_KEYWORDS):
                    logger.warning("触发验证码！请在浏览器中手动完成")
                    input("完成验证后按 Enter 继续...")
                    continue

                result = await agent.extract_table(
                    rows_selector="li.job-card-box",
                    columns={
                        "title": ".job-name",
                        "salary": ".job-salary",
                        "company": ".boss-name",
                        "tags": ".tag-list li",
                    },
                    limit=50,
                )
                rows = result.get("results", [])
                logger.info("  → 提取到 %d 条职位", len(rows))
                for row in rows:
                    insert_job({
                        "title": row.get("title", ""),
                        "salary": row.get("salary", ""),
                        "company": row.get("company", ""),
                        "tags": row.get("tags", ""),
                        "city": city,
                    })

        stats = get_stats()
        logger.info("搜索完成！统计: %s", json.dumps(stats, ensure_ascii=False))
        logger.info("浏览器保持打开，您可查看结果。关闭浏览器窗口即可退出。")

    except KeyboardInterrupt:
        logger.info("用户中断")
    finally:
        pass


if __name__ == "__main__":
    asyncio.run(main())
