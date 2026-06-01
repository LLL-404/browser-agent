"""分析全国搜索结果，按用户标准筛选。"""
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
with open(BASE / "data/nationwide_results.json", encoding="utf-8") as f:
    data = json.load(f)

# 硬排除关键词
EXCLUDE_TITLE = ["销售", "营销", "业务", "推广", "客服", "外卖", "快递", "司机", "保安", "保洁", "普工", "操作工", "管培生", "管理培训生"]
EXCLUDE_EDU = ["本科", "硕士", "博士"]
EXCLUDE_EXP = ["3-5年", "5-10年", "10年以上"]
EXCLUDE_SCHEDULE = ["倒班", "夜班", "两班倒", "三班倒", "早晚班"]
EXCLUDE_STUDENT = ["初中"]

GOOD_TITLE = ["化工", "安全", "质检", "化验", "检测", "环保", "技术", "研发", "实验", "工艺", "生产", "质量", "储备"]
GOOD_BENEFIT = ["五险一金", "五险", "公积金", "双休", "大小周", "朝九晚五", "朝九晚六",
                 "包吃", "包住", "住宿", "食堂", "餐补", "班车", "补贴", "宿舍", "住房"]
GOOD_SCHEDULE = ["双休", "大小周", "朝九晚五", "朝九晚六", "不加班", "长白班"]

results = []
for r in data:
    title = r.get("title", "")
    tags = r.get("tags", [])
    company = r.get("company", "")
    salary = r.get("salary", "")
    city = r.get("city", "")
    self_text = r.get("self_text", "")
    all_text = title + " " + " ".join(tags) + " " + self_text
    keyword = r.get("keyword", "")

    # 硬排除
    skip = False
    for kw in EXCLUDE_TITLE:
        if kw in title:
            skip = True
            break
    if skip:
        continue

    for kw in EXCLUDE_EDU:
        if kw in tags or kw in all_text:
            skip = True
            break
    if skip:
        continue

    for kw in EXCLUDE_EXP:
        if kw in tags:
            skip = True
            break
    if skip:
        continue

    for kw in EXCLUDE_SCHEDULE:
        if kw in all_text:
            skip = True
            break
    if skip:
        continue

    for kw in EXCLUDE_STUDENT:
        if kw in tags:
            skip = True
            break
    if skip:
        continue

    # 评分
    score = 0
    # 专业匹配
    for kw in GOOD_TITLE:
        if kw in title:
            score += 2
    # 应届友好
    if any(k in " ".join(tags) for k in ["应届", "校招", "经验不限", "实习生"]):
        score += 3
    if "在校/应届" in " ".join(tags):
        score += 5
    # 福利
    for kw in GOOD_BENEFIT:
        if kw in all_text:
            score += 1
    # 双休
    for kw in GOOD_SCHEDULE:
        if kw in all_text:
            score += 2
    # 薪资(粗略)
    salary_nums = re.findall(r"(\d+)-(\d+)", salary)
    if salary_nums:
        lo, hi = int(salary_nums[0][0]), int(salary_nums[0][1])
        if lo >= 5:
            score += 2
        if lo >= 7:
            score += 2
    if "薪" in salary:
        score += 1
    # 大专友好
    if "大专" in " ".join(tags):
        score += 3
    if "学历不限" in " ".join(tags):
        score += 1

    results.append({
        "score": score,
        "title": title,
        "company": company,
        "city": city,
        "salary": salary,
        "tags": tags,
        "keyword": keyword,
    })

# 去重 + 排序
seen = set()
unique = []
for r in sorted(results, key=lambda x: x["score"], reverse=True):
    key = (r["title"], r["company"], r["city"])
    if key not in seen:
        seen.add(key)
        unique.append(r)

# 专业对口 vs 其他
PRO_MATCH = ["化工", "安全", "质检", "化验", "检测", "环保", "技术", "研发", "实验", "工艺", "工程师"]
pro = [r for r in unique if any(kw in r["title"] for kw in PRO_MATCH)]
other = [r for r in unique if r not in pro]

print(f"筛选后: {len(unique)} 条（专业对口 {len(pro)} + 其他 {len(other)}）（原始 {len(data)} 条）")
print(f"\n{'='*90}")
print("  专业对口 Top 40")
print(f"{'='*90}")
print(f"{'#':>3} {'得分':>3} {'城市':<6} {'薪资':<18} {'职位':<34} {'公司':<22}")
print(f"{'-'*90}")
for i, r in enumerate(pro[:40]):
    print(f"{i+1:>3} {r['score']:>3} {r['city']:<6} {r['salary']:<18} {r['title'][:32]:<34} {r['company'][:20]:<22}")
    if i % 15 == 14 and i < 39:
        print(f"{'='*90}")
print(f"{'='*90}")