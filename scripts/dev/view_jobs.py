"""查看搜索结果"""
from modes.zhipin.storage import init_db, get_jobs, get_job_by_id, JobQuery

init_db()
jobs = get_jobs(JobQuery(limit=10))
print(f"共 {len(jobs)} 条\n")
for j in jobs:
    full = get_job_by_id(j['id'])
    print(f"[{full['id']}] {full['title']}")
    print(f"    公司: {full['company']}")
    print(f"    薪资: {full['salary']}")
    print(f"    城市: {full['city']}")
    print(f"    标签: {full.get('tags', '')}")
    print(f"    活跃: {full.get('recruiter_active', '')}")
    desc = full.get('description', '') or ''
    print(f"    描述: {desc[:100]}")
    print()
