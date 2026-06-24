"""通过国家企业信用信息公示系统验证公司。

数据来源：https://www.gsxt.gov.cn （国家市场监督管理总局）
这是官方免费的企业信息查询平台，完全合规。

合规措施：
- 每次请求间隔 ≥ 5 秒
- 每分钟不超过 5 次查询
- 每小时不超过 30 次查询
- 查询前自动检查速率限制
"""

import asyncio
import re
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from browser_agent.core.agent import BrowserAgent
from modes.zhipin.storage import get_all_companies, update_company_info
from shared.gov_site_limiter import GovernmentSiteLimiter, gov_safe_delay
from shared.logging_config import get_logger, setup_logging

setup_logging(log_to_console=True, log_to_file=True)
logger = get_logger("gov_verify")

# 国家企业信用信息公示系统
GSXT_URL = "https://www.gsxt.gov.cn"

# 合规参数
MIN_INTERVAL_SEC = 5       # 每次查询至少间隔 5 秒
MAX_PER_HOUR = 25          # 每小时最多 25 次（留余量）
PAUSE_EVERY_N = 10         # 每查 10 家暂停一下


async def verify_company(agent: BrowserAgent, company: str, limiter: GovernmentSiteLimiter) -> dict:
    """验证单家公司，返回信息字典。"""
    info = {
        "company": company,
        "found_date": "",
        "register_capital": "",
        "social_insurance": "",
        "status": "",
        "legal_person": "",
        "source": "gsxt.gov.cn",
    }

    try:
        # 合规等待
        await gov_safe_delay(GSXT_URL, "page_ready")

        # 导航到搜索页
        await agent.navigate(GSXT_URL)
        await asyncio.sleep(3)  # 政府网站额外等待

        # 查找搜索框并输入公司名
        search_input = await agent.find("#keyword")
        if not search_input:
            # 尝试备选选择器
            search_input = await agent.find("input[placeholder*='搜索']")
        if not search_input:
            search_input = await agent.find("input[type='text']")

        if search_input:
            await agent.type("#keyword" if await agent.find("#keyword") else "input[type='text']",
                             company, clear=True)
            await asyncio.sleep(1)

            # 点击搜索按钮
            search_btn = await agent.find("#btn_query")
            if search_btn:
                await agent.click("#btn_query")
            else:
                await agent.click("button:has-text('查询')")

            await asyncio.sleep(5)  # 等待搜索结果加载

            # 获取页面文本
            page_data = await agent.text(5000)
            text = page_data.get("text", "")

            # 解析关键信息
            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                if "法定代表人" in line:
                    info["legal_person"] = _extract_value(line)
                if "成立日期" in line or "成立时间" in line:
                    info["found_date"] = _extract_value(line)
                if "注册资本" in line:
                    info["register_capital"] = _extract_value(line)
                if "经营状态" in line or "登记状态" in line:
                    info["status"] = _extract_value(line)
                if "参保人数" in line:
                    info["social_insurance"] = _extract_value(line)

            # 判断可信度
            years = _calc_years(info["found_date"])
            info["years_since_found"] = years
            info["trust_score"] = _calc_trust(info)

            logger.info("  %s | 成立:%s(%d年) | 状态:%s | 可信度:%d",
                        company, info["found_date"], years,
                        info["status"], info["trust_score"])

        else:
            logger.warning("  %s: 搜索框未找到", company)

    except Exception as e:
        logger.error("  %s: 验证异常 - %s", company, str(e))
        info["error"] = str(e)

    return info


async def main():
    limiter = GovernmentSiteLimiter()
    companies = get_all_companies()

    if not companies:
        logger.warning("没有待验证的公司，请先运行 Step1 搜索")
        return

    logger.info("=" * 60)
    logger.info("  国家企业信用信息公示系统 — 公司验证")
    logger.info("  数据来源: %s (官方)", GSXT_URL)
    logger.info("  待验证: %d 家公司", len(companies))
    logger.info("  合规: 每次 ≥ %d秒, 每小时 ≤ %d次", MIN_INTERVAL_SEC, MAX_PER_HOUR)
    logger.info("=" * 60)

    agent = BrowserAgent()
    verified_count = 0
    skipped_count = 0

    try:
        await agent.open(headless=False)
        logger.info("浏览器已打开")

        for i, company in enumerate(companies):
            # 每小时上限检查
            if verified_count >= MAX_PER_HOUR:
                logger.warning("已达到每小时上限 %d 次，暂停 1 小时后继续...", MAX_PER_HOUR)
                await asyncio.sleep(3600)
                verified_count = 0

            # 每查 10 家额外暂停
            if i > 0 and i % PAUSE_EVERY_N == 0:
                pause = 30
                logger.info("已查 %d 家，暂停 %d 秒...", i, pause)
                await asyncio.sleep(pause)

            logger.info("[%d/%d] 验证: %s", i + 1, len(companies), company)

            info = await verify_company(agent, company, limiter)

            if info.get("error"):
                skipped_count += 1
            else:
                update_company_info(info)
                verified_count += 1

            # 间隔等待
            await asyncio.sleep(MIN_INTERVAL_SEC)

        logger.info("=" * 60)
        logger.info("  验证完成！成功: %d, 跳过: %d, 总计: %d",
                    verified_count, skipped_count, len(companies))
        logger.info("  数据来源: 国家企业信用信息公示系统 (gsxt.gov.cn)")
        logger.info("=" * 60)

    except KeyboardInterrupt:
        logger.info("用户中断，已保存 %d 条结果", verified_count)
    finally:
        logger.info("浏览器保持打开，可手动关闭。")


def _extract_value(line: str) -> str:
    """从文本行提取冒号后的值。"""
    for sep in ["：", ":", " "]:
        if sep in line:
            parts = line.split(sep, 1)
            return parts[-1].strip()
    return ""


def _calc_years(date_str: str) -> int:
    """从日期字符串计算距今多少年。"""
    if not date_str:
        return 0
    try:
        # 支持 "2018-05-12" 或 "2018年05月12日" 格式
        digits = re.findall(r'\d+', date_str)
        if len(digits) >= 1:
            year = int(digits[0])
            if year > 1900 and year < 2100:
                return datetime.now().year - year
    except (ValueError, IndexError):
        pass
    return 0


def _calc_trust(info: dict) -> int:
    """计算可信度分数 (0-10)。"""
    score = 0
    # 注册年限: >=5年 +3, >=10年 +5
    years = info.get("years_since_found", 0)
    if years >= 10:
        score += 5
    elif years >= 5:
        score += 3
    elif years >= 2:
        score += 1

    # 经营状态正常
    status = info.get("status", "")
    if any(s in status for s in ["存续", "开业", "正常", "在营"]):
        score += 3

    # 有法人信息
    if info.get("legal_person"):
        score += 1

    # 有社保信息
    if info.get("social_insurance"):
        score += 1

    return score


if __name__ == "__main__":
    asyncio.run(main())
