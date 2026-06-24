"""两步搜索流水线：BOSS 直聘搜岗位 + 企查查验公司。

Step 1: BOSS 直聘搜索 → 存入 jobs.db
Step 2: 对 Step 1 结果中的公司，用企查查验证注册年限/社保人数 → 标注可信度
"""

import asyncio
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from browser_agent.core.agent import BrowserAgent
from modes.zhipin.city_codes import get_city_code
from modes.zhipin.selectors import CAPTCHA_KEYWORDS
from modes.zhipin.storage import get_all_companies, get_stats, init_db, insert_job, update_company_info
from shared.delay import delay
from shared.logging_config import get_logger, setup_logging

setup_logging(log_to_console=True, log_to_file=True)
logger = get_logger("pipeline")


async def step1_search(agent: BrowserAgent):
    """BOSS 直聘搜索岗位"""
    # 山东及周边城市
    cities = [
        "枣庄", "济宁", "临沂", "济南", "徐州",
        "青岛", "菏泽", "泰安", "潍坊", "烟台",
        "郑州", "合肥",
    ]
    # 关键词：覆盖面广，大专可投
    keywords = [
        "普工", "操作工", "包装工", "学徒",
        "仓管", "质检", "叉车工", "电工", "焊工",
        "文员", "客服", "后勤", "保安", "保洁",
        "销售", "营业员", "收银员", "理货员",
        "厨师", "服务员", "司机", "搬运工", "快递员",
    ]

    total = 0
    for city in cities:
        for kw in keywords:
            code = get_city_code(city)
            if not code:
                continue
            search_url = f"https://www.zhipin.com/web/geek/job?city={code}&query={kw}"
            logger.info("搜索: %s %s", city, kw)
            await agent.navigate(search_url)
            await delay("page_stable")

            snap = await agent.text(1500)
            text = snap.get("text", "")
            if any(kw_cap in text for kw_cap in CAPTCHA_KEYWORDS):
                logger.warning("触发验证码！请在浏览器中手动完成验证后按 Enter...")
                input("完成验证后按 Enter 继续...")

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
            for row in rows:
                insert_job({
                    "title": row.get("title", ""),
                    "salary": row.get("salary", ""),
                    "company": row.get("company", ""),
                    "tags": row.get("tags", ""),
                    "city": city,
                    "keyword": kw,
                    "source": "boss",
                    "verified": 0,
                })
            total += len(rows)
            logger.info("  -> %d 条 (累计 %d)", len(rows), total)

    logger.info("Step1 完成！共搜索到 %d 条岗位", total)


async def step2_verify(agent: BrowserAgent):
    """企查查验公司"""
    companies = get_all_companies()  # 去重后的公司列表
    logger.info("Step2: 验证 %d 家公司...", len(companies))

    # 先导航到企查查
    await agent.navigate("https://www.qcc.com")
    await delay("page_stable")

    verified = 0
    for company in companies:
        logger.info("验证: %s (%d/%d)", company, verified + 1, len(companies))
        # 搜索公司
        try:
            search_input = await agent.find("#searchKey")
            if search_input:
                await agent.type("#searchKey", company, clear=True)
                await delay("hover")
                await agent.click("button:has-text('查一下')")
                await delay("page_stable")

                # 提取关键信息
                page_data = await agent.text(3000)
                text = page_data.get("text", "")

                # 解析注册时间、社保人数、注册资本
                info = {
                    "company": company,
                    "found_date": "",
                    "register_capital": "",
                    "social_insurance": "",
                    "status": "",
                }

                for line in text.split("\n"):
                    line = line.strip()
                    if "成立日期" in line or "成立时间" in line:
                        info["found_date"] = line.split("：")[-1].strip() if "：" in line else line.split(":")[-1].strip()
                    if "注册资本" in line:
                        info["register_capital"] = line.split("：")[-1].strip() if "：" in line else line.split(":")[-1].strip()
                    if "参保人数" in line:
                        info["social_insurance"] = line.split("：")[-1].strip() if "：" in line else line.split(":")[-1].strip()
                    if "经营状态" in line:
                        info["status"] = line.split("：")[-1].strip() if "：" in line else line.split(":")[-1].strip()

                # 更新数据库
                update_company_info(info)
                logger.info("  -> %s | 成立:%s | 社保:%s | 状态:%s",
                            company, info["found_date"], info["social_insurance"], info["status"])
                verified += 1

                await delay("pagination")

            else:
                logger.warning("  搜索框未找到，跳过 %s", company)

        except Exception as e:
            logger.error("  验证 %s 失败: %s", company, str(e))
            await delay("default")

    logger.info("Step2 完成！验证了 %d/%d 家公司", verified, len(companies))


async def main():
    init_db()
    agent = BrowserAgent()

    try:
        logger.info("正在打开浏览器（非无头，带持久 Cookie）...")
        result = await agent.open(headless=False)
        logger.info("浏览器已打开: %s", result.get("url"))

        # --- BOSS 直聘登录检查 ---
        await agent.navigate("https://www.zhipin.com/?ka=header-home")
        await delay("page_stable")
        page_data = await agent.text(500)
        page_text = page_data.get("text", "")

        need_login = any(kw in page_text for kw in ["登录", "请登录", "扫码登录"])
        if need_login:
            logger.warning("BOSS 直聘需要登录！请在浏览器中手动扫码...")
            for i in range(120):
                await delay("login_poll")
                curr = await agent.text(500)
                ct = curr.get("text", "")
                if "登录" not in ct and "请登录" not in ct:
                    logger.info("BOSS 直聘登录成功！")
                    break
                if i % 20 == 0:
                    logger.info("等待登录中...")
            else:
                logger.error("BOSS 登录超时")

        # --- 选择步骤 ---
        print("\n" + "=" * 50)
        print(" 1 = 仅搜索岗位 (Step1)")
        print(" 2 = 仅验证公司 (Step2)")
        print(" 3 = 全部执行 (Step1 + Step2)")
        choice = input("请选择 (1/2/3): ").strip()

        if choice in ("1", "3"):
            await step1_search(agent)
        if choice in ("2", "3"):
            await step2_verify(agent)

        stats = get_stats()
        logger.info("流水线完成！统计: %s", json.dumps(stats, ensure_ascii=False))
        logger.info("浏览器保持打开，可手动关闭。")

    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.error("流水线异常: %s", str(e))
        raise


if __name__ == "__main__":
    asyncio.run(main())
