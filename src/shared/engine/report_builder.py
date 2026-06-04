"""声明式报告生成器 — 维度来自 SiteProfile.report.dimensions。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from shared.engine.profile import SiteProfile


class ReportBuilder:
    """动态报告生成器 — 内容和格式完全由配置决定。"""

    def __init__(self, profile: SiteProfile):
        self.profile = profile
        self.score_threshold = profile.report.score_threshold
        self.dimensions = profile.report.dimensions

    def generate(self, jobs: list[dict[str, Any]],
                 city: str | None = None,
                 top: int | None = None) -> str:
        """生成推荐报告（Markdown 格式）。"""
        filtered = [j for j in jobs
                    if j.get("match_score", 0) >= self.score_threshold]
        if city:
            filtered = [j for j in filtered if j.get("city") == city]
        if top:
            filtered = filtered[:top]
        if not filtered:
            return "暂无符合条件的推荐职位。"

        lines = [
            f"# {self.profile.meta.display_name} 求职推荐报告",
            f"生成时间: {datetime.now().isoformat()}",
            f"匹配分数 ≥ {self.score_threshold}",
            f"共 {len(filtered)} 条推荐职位", "",
        ]
        for i, j in enumerate(filtered, 1):
            lines.extend(self._format_job_entry(i, j))
            lines.append("---")
            lines.append("")
        return "\n".join(lines)

    def _format_job_entry(self, index: int, job: dict) -> list[str]:
        score = job.get("match_score", 0)
        lines = [
            f"### {index}. [{job.get('title', '')}]({job.get('job_url', '')}) ★{score}/10",
            f"**{job.get('company', '')}** | {job.get('salary', '')} "
            f"| {job.get('city', '')} | 活跃: {job.get('recruiter_active', '未知')}", "",
        ]
        benefit_lines = []
        missing_labels = []
        for dim in self.dimensions:
            val = job.get(dim.key, 0)
            label = dim.label
            if val == 1:
                benefit_lines.append(f"✓ {label}")
            elif val == -1:
                benefit_lines.append(f"✗ {label}")
                missing_labels.append(label)
            else:
                benefit_lines.append(f"⚠ {label}未提及")
                missing_labels.append(label)
        lines.append("> " + "\n> ".join(benefit_lines))
        lines.append("")
        if missing_labels:
            lines.append(f"⚠ 缺失: {'、'.join(missing_labels)}，投递时可主动询问")
            lines.append("")
        if job.get("ai_reason"):
            lines.append(f"分析: {job['ai_reason']}")
            lines.append("")
        return lines
