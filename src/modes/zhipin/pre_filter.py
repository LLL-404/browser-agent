"""前置过滤模块，在列表页阶段筛除低质量职位，避免无谓进入详情页。"""

import re

from shared.config import get_config

# 预编译正则，避免高频调用时重复编译（提速 30%~50%）
_RE_SALARY_K = re.compile(r'(\d+)\s*[Kk]')
_RE_SALARY_NUM = re.compile(r'(\d+)')
_RE_DAY = re.compile(r'(\d+)\s*天')
_RE_WEEK = re.compile(r'(\d+)\s*周')
_RE_MONTH = re.compile(r'(\d+)\s*个月')


def parse_salary_min(salary_text: str) -> int | None:
    """从薪资文本中提取最低月薪。如 '4K-6K' → 4000, '3000-5000元/月' → 3000"""
    if not salary_text:
        return None
    nums = _RE_SALARY_K.findall(salary_text)
    if nums:
        return int(nums[0]) * 1000
    nums = _RE_SALARY_NUM.findall(salary_text)
    if len(nums) >= 1:
        return int(nums[0])
    return None


def should_skip_job(title: str, company: str, salary: str,
                    _tags: list[str], recruiter_active: str) -> tuple[bool, str]:
    """
    前置过滤：在列表页判断是否跳过，不进详情页。
    返回 (是否跳过, 跳过原因)
    """
    cfg = get_config()
    pf = cfg.get("pre_filters", {})

    # 1. 薪资过低
    min_salary = pf.get("min_salary", 0)
    parsed = parse_salary_min(salary)
    if parsed is not None and parsed < min_salary:
        return True, f"薪资 {salary} 低于 {min_salary}"

    # 2. 标题黑名单
    title_lower = title.lower() if title else ""
    for word in pf.get("title_blacklist", []):
        if word.lower() in title_lower:
            return True, f"标题含 '{word}'（门槛高于大专）"

    # 3. 公司黑名单
    company_lower = company.lower() if company else ""
    for word in pf.get("company_blacklist", []):
        if word.lower() in company_lower:
            return True, f"公司类型含 '{word}'（大概率无固定作息）"

    # 4. 标签白名单检查已移除
    # 原因：福利信息通常在详情页描述中，不在列表页标签
    # 真正的福利判断在 AI 分析阶段完成

    # 5. 招聘者活跃度
    inactive_days = _parse_inactive_days(recruiter_active)
    max_days = cfg.get("runtime", {}).get("max_inactive_days", 7)
    if inactive_days is not None and inactive_days > max_days:
        return True, f"招聘者已 {inactive_days} 天未活跃"

    return False, ""


def _parse_inactive_days(active_text: str) -> int | None:
    """解析活跃时间文本 → 天数"""
    if not active_text:
        return None
    text = active_text.strip()
    if "今日" in text or "刚刚" in text or "分钟" in text or "小时" in text:
        return 0

    _patterns = [
        (_RE_DAY, 1),
        (_RE_WEEK, 7),
        (_RE_MONTH, 30),
    ]
    for pat, mul in _patterns:
        m = re.search(pat, text)
        if m:
            return int(m.group(1)) * mul

    _fallback = {"昨天": 1, "周前": 7, "月前": 30}
    for kw, days in _fallback.items():
        if kw in text:
            return days
    return None
