"""智能求职流水线 — 优化版。

优化点:
  1. URL 直接加筛选参数（经验/学历），减少无效结果
  2. 搜索结果去重 + 本地 AI 初筛，只保留匹配度高的
  3. 公司验证改为「采样验证」——每家公司只验证一次，按优先级排队
  4. 支持断点续传——中断后可从中断处继续
  5. 生成结构化报告，按推荐度排序

用法:
  python -m modes.zhipin.smart_hunt
"""

import asyncio
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import contextlib

from browser_agent.core.agent import BrowserAgent
from modes.zhipin.city_codes import get_city_code
from shared.delay import delay
from shared.gov_site_limiter import GovernmentSiteLimiter
from shared.logging_config import get_logger, setup_logging

setup_logging(log_to_console=True, log_to_file=True)
logger = get_logger("smart_hunt")

DB_PATH = Path("data/jobs.db")
GSXT_URL = "https://www.gsxt.gov.cn"

# ============================================================
# 用户画像
# ============================================================
USER_PROFILE = {
    "education": "大专",
    "experience": ["应届生", "不限经验", "无经验", "经验不限"],
    "salary_min": 4000,
    "benefits": ["五险一金", "五险", "包住", "包吃", "双休", "社保"],
    "company_min_years": 5,
    "regions": ["山东", "江苏", "河南", "安徽"],  # 优先省份
}

# ============================================================
# 搜索参数（URL 筛选优化）
# ============================================================

CITIES = [
    "枣庄", "济宁", "临沂", "济南", "徐州",
    "青岛", "菏泽", "泰安", "潍坊", "烟台",
    "郑州", "合肥",
]

# 关键词精简——BOSS 搜索本身就覆盖广
KEYWORDS = [
    "普工", "操作工", "仓管", "质检",
    "文员", "客服", "销售", "后勤",
    "保安", "司机", "电工", "学徒",
]

# BOSS 直聘 URL 参数说明:
# degree=203 -> 大专
# experience=101 -> 应届生
# experience=102 -> 1年以内
# experience=103 -> 1-3年
URL_PARAMS = "&degree=202,203,204&experience=101,102,103"
# degree: 202=不限, 203=大专, 204=本科
# experience: 101=应届生, 102=1年以内, 103=1-3年


# ============================================================
# 数据库
# ============================================================

def _connect():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            company TEXT,
            salary TEXT,
            city TEXT,
            tags TEXT,
            keyword TEXT,
            source TEXT DEFAULT 'boss',
            status TEXT DEFAULT 'new',
            score INTEGER DEFAULT 0,
            reason TEXT,
            verified INTEGER DEFAULT 0,
            company_info TEXT,
            created_at TEXT,
            UNIQUE(title, company, city)
        );
        CREATE TABLE IF NOT EXISTS hunt_state (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    # 兼容旧表
    for col in ["score", "reason", "verified", "company_info"]:
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} TEXT DEFAULT ''")
    conn.commit()
    conn.close()


def get_state(key: str) -> str | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT value FROM hunt_state WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


def set_state(key: str, value: str):
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO hunt_state (key, value) VALUES (?, ?)",
            (key, value)
        )
        conn.commit()
    finally:
        conn.close()


def insert_job(data: dict):
    now = datetime.now().isoformat()
    conn = _connect()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO jobs (title, company, salary, city, tags, keyword, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'new', ?)
        """, (
            data.get("title", ""),
            data.get("company", ""),
            data.get("salary", ""),
            data.get("city", ""),
            json.dumps(data.get("tags", []), ensure_ascii=False),
            data.get("keyword", ""),
            now,
        ))
        conn.commit()
    finally:
        conn.close()


def mark_scored(job_id: int, score: int, reason: str):
    conn = _connect()
    try:
        conn.execute(
            "UPDATE jobs SET score=?, reason=?, status='scored' WHERE id=?",
            (score, reason, job_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_unscored_jobs(limit=200):
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status='new' LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_jobs():
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY score DESC, id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ============================================================
# Step 1: BOSS 直聘搜索（URL 筛选优化）
# ============================================================

async def step1_search(agent: BrowserAgent):
    """带 URL 筛选参数的搜索。"""
    cities_done = get_state("cities_done") or ""
    cities_done = set(cities_done.split(",")) if cities_done else set()
    cities_todo = [c for c in CITIES if c not in cities_done]

    if not cities_todo:
        logger.info("所有城市已搜索完毕")
        return

    logger.info("Step 1: 搜索 %d 个城市 (%d 个关键词)", len(cities_todo), len(KEYWORDS))

    total = 0
    for city in cities_todo:
        code = get_city_code(city)
        if not code:
            continue

        for kw in KEYWORDS:
            # URL 直接加学历+经验筛选
            url = f"https://www.zhipin.com/web/geek/job?city={code}&query={kw}{URL_PARAMS}"
            logger.info("  %s / %s", city, kw)

            try:
                await agent.navigate(url)
                await delay("page_stable")

                # 提取岗位
                result = await agent.extract_table(
                    rows_selector="li.job-card-box",
                    columns={
                        "title": ".job-name",
                        "salary": ".job-salary",
                        "company": ".boss-name",
                        "tags": ".tag-list li",
                    },
                    limit=30,
                )

                for row in result.get("results", []):
                    insert_job({
                        "title": row.get("title", ""),
                        "salary": row.get("salary", ""),
                        "company": row.get("company", ""),
                        "tags": row.get("tags", ""),
                        "city": city,
                        "keyword": kw,
                    })
                total += len(result.get("results", []))

            except Exception as e:
                logger.error("    异常: %s", str(e))
                await asyncio.sleep(2)

            await delay("pagination")

        cities_done.add(city)
        set_state("cities_done", ",".join(cities_done))
        logger.info("  %s 完成 (累计 %d 条)", city, total)

    logger.info("Step 1 完成: %d 条", total)


# ============================================================
# Step 2: 本地 AI 初筛（不依赖网络，快速）
# ============================================================

def score_job(job: dict) -> tuple[int, str]:
    """根据用户画像对岗位打分。满分 10 分。"""
    score = 0
    reasons = []
    title = job.get("title", "")
    tags = job.get("tags", "")
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except json.JSONDecodeError:
            tags = []
    tags_str = " ".join(tags) if isinstance(tags, list) else str(tags)
    salary_str = job.get("salary", "")

    # 1. 学历匹配 (0-2分)
    title_lower = title.lower()
    if any(w in title_lower for w in ["大专", "不限", "学历不限"]):
        score += 2
        reasons.append("学历匹配")
    elif "本科" in title_lower and "及以上" not in title_lower:
        score += 1
        reasons.append("本科可试")

    # 2. 经验匹配 (0-2分)
    if any(w in title_lower for w in ["应届", "不限经验", "无经验", "经验不限"]):
        score += 2
        reasons.append("经验匹配")

    # 3. 福利标签 (0-3分，每个匹配 +1)
    benefit_count = 0
    for b in USER_PROFILE["benefits"]:
        if b in title_lower or b in tags_str:
            benefit_count += 1
    if benefit_count >= 3:
        score += 3
        reasons.append(f"福利{benefit_count}项")
    elif benefit_count >= 1:
        score += benefit_count
        reasons.append(f"福利{benefit_count}项")

    # 4. 薪资 (0-2分)
    try:
        nums = re.findall(r'(\d+)', salary_str.replace("K", "000").replace("k", "000"))
        if nums:
            lo = int(nums[0])
            if len(nums) > 1:
                hi = int(nums[-1])
                if lo < 1000:
                    lo *= 1000
                if hi < 1000:
                    hi *= 1000
                avg = (lo + hi) / 2
            else:
                avg = lo if lo > 100 else lo * 1000
            if avg >= 6000:
                score += 2
                reasons.append(f"薪资≈{avg/1000:.0f}K")
            elif avg >= 4000:
                score += 1
                reasons.append(f"薪资≈{avg/1000:.0f}K")
    except (ValueError, IndexError):
        pass

    # 5. 标题黑名单扣分
    black = ["经理", "总监", "主管", "高级", "资深", "硕士", "博士", "架构师", "专家"]
    for w in black:
        if w in title:
            score -= 2
            reasons.append(f"含'{w}'")
            break

    return max(0, min(10, score)), "; ".join(reasons)


def step2_score():
    """本地打分——不需要网络。"""
    jobs = get_unscored_jobs()
    if not jobs:
        logger.info("没有待打分的岗位")
        return

    logger.info("Step 2: 本地打分 %d 条岗位...", len(jobs))

    good = 0
    for job in jobs:
        score, reason = score_job(job)
        mark_scored(job["id"], score, reason)
        if score >= 5:
            good += 1

    logger.info("打分完成: %d/%d 条达标 (>=5分)", good, len(jobs))


# ============================================================
# Step 3: 国家企业信用信息公示系统验证（采样）
# ============================================================

async def step3_verify(agent: BrowserAgent):
    """验证高分岗位的公司（≥6分优先）。"""
    conn = _connect()
    try:
        rows = conn.execute("""
            SELECT DISTINCT company FROM jobs
            WHERE score >= 6 AND (verified = 0 OR verified IS NULL)
            LIMIT 20
        """).fetchall()
        companies = [r["company"] for r in rows]
    finally:
        conn.close()

    if not companies:
        logger.info("没有待验证的高分公司")
        return

    GovernmentSiteLimiter()
    logger.info("Step 3: 官方验证 %d 家高分公司 (gsxt.gov.cn)", len(companies))

    verified = 0
    for i, company in enumerate(companies):
        if verified >= 20:
            break

        logger.info("  [%d/%d] %s", i + 1, len(companies), company)
        try:
            await asyncio.sleep(6)
            await agent.navigate(GSXT_URL)
            await asyncio.sleep(4)

            await agent.type("#keyword", company, clear=True)
            await asyncio.sleep(1)
            await agent.click("#btn_query")
            await asyncio.sleep(6)

            page = await agent.text(5000)
            text = page.get("text", "")

            info = {
                "company": company,
                "found_date": "",
                "status": "",
                "verified_at": datetime.now().isoformat(),
                "source": "gsxt.gov.cn",
            }
            for line in text.split("\n"):
                line = line.strip()
                if "成立日期" in line:
                    info["found_date"] = line.split("：")[-1].strip() if "：" in line else line.split(":")[-1].strip()
                if "登记状态" in line or "经营状态" in line:
                    info["status"] = line.split("：")[-1].strip() if "：" in line else line.split(":")[-1].strip()

            digits = re.findall(r'\d+', info.get("found_date", ""))
            years = 0
            if digits:
                yr = int(digits[0])
                if 1900 < yr < 2100:
                    years = datetime.now().year - yr
            info["years"] = years

            # 写入数据库
            conn2 = _connect()
            try:
                conn2.execute(
                    "UPDATE jobs SET verified=1, company_info=? WHERE company=?",
                    (json.dumps(info, ensure_ascii=False), company)
                )
                conn2.commit()
            finally:
                conn2.close()

            logger.info("    -> 成立:%s(%d年) 状态:%s", info["found_date"], years, info.get("status", "?"))
            verified += 1

        except Exception as e:
            logger.error("    失败: %s", str(e))

    logger.info("Step 3 完成: 验证 %d 家", verified)


# ============================================================
# Step 4: 生成报告
# ============================================================

def step4_report():
    """生成带排序的推荐报告。"""
    jobs = get_all_jobs()

    # 统计
    total = len(jobs)
    scored = sum(1 for j in jobs if j["score"] > 0)
    good = sum(1 for j in jobs if j["score"] >= 6)
    verified = sum(1 for j in jobs if j["verified"] == 1)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    report = f"""# 求职搜索报告
**生成时间**: {now}
**用户画像**: 大专 | 应届/不限经验 | 山东及周边

## 概览
| 指标 | 数值 |
|------|------|
| 搜索总数 | {total} |
| 已打分 | {scored} |
| 推荐(≥6分) | {good} |
| 已验证公司 | {verified} |

## 推荐岗位 (≥6分)
"""
    # 排序: 分数 > 已验证 > 薪资
    top = sorted(
        [j for j in jobs if j["score"] >= 6],
        key=lambda j: (j["score"], j["verified"] or 0),
        reverse=True,
    )[:30]

    for job in top:
        tags = job.get("tags", "")
        if isinstance(tags, str):
            with contextlib.suppress(json.JSONDecodeError):
                tags = json.loads(tags)
        tags_str = " ".join(tags) if isinstance(tags, list) else str(tags)

        company_info = job.get("company_info", "")
        years_str = ""
        if company_info:
            try:
                ci = json.loads(company_info)
                yrs = ci.get("years", "")
                if yrs:
                    years_str = f" | 成立{yrs}年"
            except (json.JSONDecodeError, TypeError):
                pass

        verify_mark = "✅" if job.get("verified") == 1 else ""
        report += f"- **{job['title']}** | {job['company']}{years_str} | {job['city']} | {job['salary']} | {tags_str} | {verify_mark} 评分:{job['score']}\n"

    report += "\n## 可尝试岗位 (4-5分)\n"
    mid = sorted(
        [j for j in jobs if 4 <= j["score"] <= 5],
        key=lambda j: j["score"],
        reverse=True,
    )[:20]

    for job in mid:
        report += f"- {job['title']} | {job['company']} | {job['city']} | {job['salary']} | 评分:{job['score']}\n"

    path = Path("docs/运行结果/搜索报告.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    logger.info("报告: %s", path)

    return report


# ============================================================
# 主入口
# ============================================================

async def main():
    init_db()
    agent = BrowserAgent()

    try:
        logger.info("启动浏览器...")
        await agent.open(headless=False)

        # BOSS 登录
        await agent.navigate("https://www.zhipin.com")
        await delay("page_stable")

        page_data = await agent.text(500)
        if "登录" in page_data.get("text", ""):
            logger.warning("请手动扫码登录 BOSS 直聘...")
            for _ in range(120):
                await delay("login_poll")
                curr = await agent.text(500)
                if "登录" not in curr.get("text", ""):
                    logger.info("登录成功！")
                    break
            else:
                logger.error("登录超时")

        # 执行流水线
        await step1_search(agent)

        # Step 2 本地打分（不需要浏览器）
        step2_score()

        # Step 3 官方验证（仅高分公司）
        await step3_verify(agent)

        # Step 4 报告
        report = step4_report()
        print("\n" + report)

        logger.info("全部完成！")

    except KeyboardInterrupt:
        logger.info("用户中断，保存进度...")
        step2_score()
        step4_report()
    except Exception as e:
        logger.error("异常: %s", str(e))
        raise


if __name__ == "__main__":
    asyncio.run(main())
