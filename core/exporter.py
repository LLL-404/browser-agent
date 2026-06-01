"""数据导出模块，将职位数据导出为 Markdown/JSON 格式。"""

import json
from datetime import datetime
from pathlib import Path

from .storage import batch_update_jobs


def export_for_analysis(jobs: list[dict],
                        output_dir: str = "data/export") -> tuple[Path, Path]:
    """导出待分析职位为 md + json 骨架（CLI 备用方案）。"""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    md_path = Path(output_dir) / f"todo_{date_str}.md"
    json_path = Path(output_dir) / f"todo_{date_str}.json"

    # JSON 骨架
    skeleton = []
    for j in jobs:
        skeleton.append({
            "job_id": j["id"],
            "title": j.get("title", ""),
            "company": j.get("company", ""),
            "city": j.get("city", ""),
            "salary": j.get("salary", ""),
            "five_insurance": None,
            "room_board": None,
            "regular_hours": None,
            "overtime_risk": None,
            "diploma_ok": None,
            "recruiter_active": None,
            "match_score": None,
            "reason": "",
        })
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(skeleton, f, ensure_ascii=False, indent=2)

    # Markdown
    lines = [
        "# 待分析职位列表",
        f"导出时间: {datetime.now().isoformat()}",
        f"共 {len(jobs)} 条",
        "",
        "你是求职匹配分析助手。用户画像：大专学历，期望朝九晚五、双休、五险一金、包食宿，不限行业和城市。",
        "请分析以下职位，判断每条对用户的匹配度，并将结果填入同目录下的 JSON 文件。",
        "每条需判断：",
        "- five_insurance: true/false     （是否提及五险一金）",
        "- room_board: true/false         （是否提及包食宿/包住/包吃）",
        "- regular_hours: true/false      （是否朝九晚五/双休/不加班）",
        "- overtime_risk: \"low\"/\"mid\"/\"high\"  （加班风险）",
        "- diploma_ok: true/false         （大专学历是否可投）",
        "- recruiter_active: bool         （招聘者是否7天内活跃，>7天视为 false）",
        "- match_score: 0-10              （综合匹配度，考虑购买力修正；招聘者超过7天未活跃则最高不超过5分）",
        "- reason: \"简要匹配理由\"",
        "",
        "---",
        "",
    ]

    for j in jobs:
        rent = j.get("rent_reference", {})
        rent_label = rent.get("label", "未知")
        lines.append(f"## [{j['id']}] {j.get('title', '')}")
        lines.append(f"- 公司: {j.get('company', '')}")
        lines.append(
            f"- 城市: {j.get('city', '')} | 薪资: {j.get('salary', '')}"
            f" | 单间月租参考: {rent_label}")
        lines.append(f"- 活跃: {j.get('recruiter_active', '未知')}")
        lines.append(f"- 标签: {', '.join(j.get('tags', [])[:5])}")
        desc = j.get("description", "")[:500]
        if desc:
            lines.append(f"- 描述: {desc}")
        lines.append("")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return md_path, json_path


def save_report(content: str, output_dir: str = "data/reports") -> Path:
    """保存推荐报告到文件"""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = Path(output_dir) / f"report_{date_str}.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def import_analysis_from_json(json_path: str) -> list[dict]:
    """从 JSON 文件读取 AI 分析结果"""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def import_from_analysis(file_path: str) -> int:
    """从文件导入 AI 分析结果到数据库。"""
    if file_path.endswith(".json"):
        results = import_analysis_from_json(file_path)
    else:
        # Markdown，暂不支持
        return 0
    updated, _ = batch_update_jobs(results)
    return updated
