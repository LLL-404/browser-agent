"""BOSS 直聘站点插件 — 封装 BOSS 直聘的搜索、分析、报告功能。

所有功能通过 core.scraper / core.selectors / core.storage 等模块实现，
本包仅作为站点的逻辑聚合与清晰入口。
"""

from core.scraper import (
    search_jobs,
    analyze_jobs,
    import_analysis,
    generate_report,
    generate_chat_prompt,
    health_check,
)
from core.storage import get_jobs, get_job_by_id, update_job_status, get_stats, JobQuery

__all__ = [
    "search_jobs", "analyze_jobs", "import_analysis",
    "generate_report", "generate_chat_prompt", "health_check",
    "get_jobs", "get_job_by_id", "update_job_status", "get_stats", "JobQuery",
]
