"""ReportBuilder 报告生成器测试。"""
from __future__ import annotations

import pytest

from shared.engine.profile import (
    MetaConfig,
    ReportConfig,
    ReportDimension,
    SiteProfile,
)
from shared.engine.report_builder import ReportBuilder


# ── 辅助函数：从维度列表构建 SiteProfile + ReportBuilder ────────────────

def _make_report_profile(dimensions: list[dict] | None = None,
                         score_threshold: int = 6) -> tuple[SiteProfile, ReportBuilder]:
    """从字典列表构造 SiteProfile 并返回对应的 ReportBuilder。"""
    dims = [
        ReportDimension(key=d["key"], label=d["label"])
        for d in (dimensions or [])
    ]
    profile = SiteProfile(
        meta=MetaConfig(display_name="测试招聘平台"),
        report=ReportConfig(score_threshold=score_threshold, dimensions=dims),
    )
    return profile, ReportBuilder(profile)


# 默认测试用维度
_DEFAULT_DIMS = [
    {"key": "has_remote", "label": "支持远程"},
    {"key": "has_bonus", "label": "年终奖"},
    {"key": "stock_option", "label": "股票期权"},
]

# 默认测试职位数据
_SAMPLE_JOB = {
    "title": "Python 后端开发",
    "job_url": "https://example.com/job/1",
    "company": "示例科技",
    "salary": "20-35K",
    "city": "北京",
    "recruiter_active": "是",
    "match_score": 8,
    "has_remote": 1,
    "has_bonus": 0,
    "stock_option": -1,
    "ai_reason": "技术栈匹配度高，团队规模合适",
}


class TestGenerate:
    """报告生成核心测试。"""

    def test_basic_report_with_dimensions(self):
        """基本报告应包含标题、职位条目、福利维度和缺失提示。"""
        _, builder = _make_report_profile(_DEFAULT_DIMS)
        result = builder.generate([_SAMPLE_JOB])

        assert "# 测试招聘平台 求职推荐报告" in result
        assert "共 1 条推荐职位" in result
        assert "Python 后端开发" in result
        assert "★8/10" in result
        assert "✓ 支持远程" in result
        assert "⚠ 年终奖未提及" in result
        assert "✗ 股票期权" in result
        assert "缺失: 年终奖、股票期权" in result
        assert "投递时可主动询问" in result
        assert "分析: 技术栈匹配度高，团队规模合适" in result

    def test_below_threshold_filtered(self):
        """低于 score_threshold 的职位应被过滤掉。"""
        _, builder = _make_report_profile(_DEFAULT_DIMS, score_threshold=9)
        low_job = {**_SAMPLE_JOB, "match_score": 5}
        result = builder.generate([low_job])
        assert result == "暂无符合条件的推荐职位。"

    def test_empty_jobs_list(self):
        """空职位列表应返回提示信息。"""
        _, builder = _make_report_profile(_DEFAULT_DIMS)
        result = builder.generate([])
        assert result == "暂无符合条件的推荐职位。"

    def test_custom_dimensions_replace_default(self):
        """自定义维度应替换默认维度，报告中只显示自定义维度。"""
        custom_dims = [{"key": "flex_time", "label": "弹性工作时间"}]
        _, builder = _make_report_profile(custom_dims)
        job = {
            **_SAMPLE_JOB,
            "flex_time": 1,
            # 移除默认维度的 key 以验证不会出现旧维度
            "has_remote": None,
            "has_bonus": None,
            "stock_option": None,
        }
        result = builder.generate([job])

        assert "✓ 弹性工作时间" in result
        assert "支持远程" not in result
        assert "年终奖" not in result

    def test_top_limits_results(self):
        """top 参数应限制返回的职位数量。"""
        _, builder = _make_report_profile(_DEFAULT_DIMS)
        jobs = [{**_SAMPLE_JOB, "title": f"职位{i}", "match_score": 8 + i}
                for i in range(5)]
        result = builder.generate(jobs, top=2)

        assert "共 2 条推荐职位" in result
        assert "职位0" in result
        assert "职位1" in result
        assert "职位2" not in result
        assert "职位4" not in result

    def test_city_filter(self):
        """city 参数应按城市筛选职位。"""
        _, builder = _make_report_profile(_DEFAULT_DIMS)
        bj_job = {**_SAMPLE_JOB, "city": "北京", "match_score": 8}
        sh_job = {**_SAMPLE_JOB, "city": "上海", "title": "上海岗位", "match_score": 9}
        result = builder.generate([bj_job, sh_job], city="上海")

        assert "上海岗位" in result
        assert "Python 后端开发" not in result
        assert "共 1 条推荐职位" in result

    def test_no_ai_reason_when_missing(self):
        """职位没有 ai_reason 时不应输出分析行。"""
        _, builder = _make_report_profile(_DEFAULT_DIMS)
        job = {**_SAMPLE_JOB}
        del job["ai_reason"]
        result = builder.generate([job])

        assert "分析:" not in result

    def test_all_dimensions_positive(self):
        """所有维度值为 1 时不应出现缺失提示。"""
        _, builder = _make_report_profile(_DEFAULT_DIMS)
        job = {
            **_SAMPLE_JOB,
            "has_remote": 1,
            "has_bonus": 1,
            "stock_option": 1,
        }
        result = builder.generate([job])

        assert "缺失:" not in result
        assert "✓ 支持远程" in result
        assert "✓ 年终奖" in result
        assert "✓ 股票期权" in result

    def test_multiple_jobs_with_separator(self):
        """多个职位之间应有分隔线。"""
        _, builder = _make_report_profile(_DEFAULT_DIMS)
        jobs = [
            {**_SAMPLE_JOB, "title": "职位A", "match_score": 8},
            {**_SAMPLE_JOB, "title": "职位B", "match_score": 7},
        ]
        result = builder.generate(jobs)

        assert "---" in result
        assert "共 2 条推荐职位" in result
        assert "### 1." in result
        assert "### 2." in result

    def test_empty_dimensions_no_benefit_section(self):
        """空维度列表时福利区域仍应正常输出（仅不含维度行）。"""
        _, builder = _make_report_profile([])
        result = builder.generate([_SAMPLE_JOB])

        assert "# 测试招聘平台 求职推荐报告" in result
        assert "Python 后端开发" in result
        # 空维度时 benefit_lines 为空，但 "> " 前缀仍会出现（空内容）
