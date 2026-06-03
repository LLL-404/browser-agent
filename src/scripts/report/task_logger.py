#!/usr/bin/env python3
"""任务执行日志自动记录。

用法:
    python scripts/task_logger.py record <JSON参数文件>
    python scripts/task_logger.py list [--last N]

示例:
    # 记录一次任务
    python scripts/task_logger.py record '{
        "task_id": "wow-cg-search-20260601",
        "task_type": "websearch_collection",
        "capabilities": ["web_search", "web_fetch"],
        "operations": {"web_search": 2},
        "anti_scrape_triggered": false,
        "captcha_triggered": false,
        "duration_seconds": 1800,
        "success": true,
        "notes": "搜索无水印原版魔兽世界官方 CG 动画"
    }'

    # 查看最近 N 条日志
    python scripts/task_logger.py list --last 5
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TASK_LOGS_DIR = Path("data/task_logs")


def _ensure_dir() -> Path:
    TASK_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return TASK_LOGS_DIR


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


class TaskLogger:
    """任务执行日志记录器。

    提供上下文管理器支持，自动记录开始/结束时间。
    """

    def __init__(self, task_id: str | None = None, task_type: str = "generic",
                 capabilities: list[str] | None = None):
        self.task_id = task_id or f"task-{uuid.uuid4().hex[:12]}"
        self.task_type = task_type
        self.capabilities = capabilities or []
        self.operations: dict[str, int] = {}
        self.anti_scrape_triggered = False
        self.captcha_triggered = False
        self.start_time = time.time()
        self.end_time: float | None = None
        self.success = True
        self.notes: str = ""

        self._record: dict[str, Any] = {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "timestamp_start": _now_iso(),
            "capabilities": self.capabilities,
            "operations": {},
            "anti_scrape_triggered": False,
            "captcha_triggered": False,
            "duration_seconds": None,
            "success": True,
            "notes": "",
        }

    def log_operation(self, name: str, count: int = 1) -> None:
        self.operations[name] = self.operations.get(name, 0) + count

    def mark_anti_scrape(self) -> None:
        self.anti_scrape_triggered = True

    def mark_captcha(self) -> None:
        self.captcha_triggered = True

    def set_notes(self, notes: str) -> None:
        self.notes = notes

    def finish(self, success: bool = True) -> dict[str, Any]:
        self.end_time = time.time()
        self.success = success
        duration = round(self.end_time - self.start_time, 1)

        self._record.update({
            "timestamp_end": _now_iso(),
            "operations": dict(self.operations),
            "anti_scrape_triggered": self.anti_scrape_triggered,
            "captcha_triggered": self.captcha_triggered,
            "duration_seconds": duration,
            "success": self.success,
            "notes": self.notes,
        })
        return self._record

    def save(self) -> Path:
        record = self.finish(success=self.success)
        log_dir = _ensure_dir()
        safe_id = self.task_id.replace(" ", "_").replace("/", "_")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = log_dir / f"{safe_id}_{ts}.json"
        path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def __enter__(self) -> TaskLogger:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        success = exc_type is None
        self.finish(success=success)
        if success:
            self.save()


def cmd_record(args: argparse.Namespace) -> int:
    """记录一次任务日志。"""
    try:
        data = json.loads(args.json_data) if args.json_data else _load_json(args.file)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"错误: 无法解析输入数据 — {e}")
        return 1

    logger = TaskLogger(
        task_id=data.get("task_id"),
        task_type=data.get("task_type", "generic"),
        capabilities=data.get("capabilities", []),
    )

    for op_name, count in data.get("operations", {}).items():
        logger.log_operation(op_name, count)

    if data.get("anti_scrape_triggered"):
        logger.mark_anti_scrape()
    if data.get("captcha_triggered"):
        logger.mark_captcha()

    logger.set_notes(data.get("notes", ""))
    logger.success = data.get("success", True)

    path = logger.save()
    print(f"任务日志已记录: {path}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """列出最近 N 条任务日志。"""
    log_dir = _ensure_dir()
    files = sorted(log_dir.glob("*.json"), reverse=True)
    count = args.last or 10

    if not files:
        print("暂无任务日志。")
        return 0

    print(f"最近 {min(count, len(files))} 条任务日志:\n")
    for f in files[:count]:
        try:
            record = _load_json(f)
            dur_str = f"{record['duration_seconds']}s" if record.get("duration_seconds") else "N/A"
            status = "✅" if record.get("success") else "❌"
            print(f"  {status} {record['task_id']}")
            print(f"     类型: {record['task_type']}")
            print(f"     时间: {record.get('timestamp_start', '?')} → {record.get('timestamp_end', '?')}")
            print(f"     耗时: {dur_str}")
            print(f"     能力: {', '.join(record.get('capabilities', []))}")
            print(f"     操作: {record.get('operations', {})}")
            if record.get("notes"):
                print(f"     备注: {record['notes']}")
            print()
        except Exception as e:
            print(f"  ⚠️  {f.name}: 解析失败 — {e}\n")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="任务执行日志管理")
    sub = parser.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("record", help="记录一条任务日志")
    rec.add_argument("json_data", nargs="?",
                     help='JSON 数据字符串 (如 \'{"task_id":"x","task_type":"y"}\')')
    rec.add_argument("-f", "--file", type=str,
                     help="从 JSON 文件读取任务数据")

    lst = sub.add_parser("list", help="列出最近任务日志")
    lst.add_argument("--last", type=int, default=10,
                     help="显示最近 N 条记录 (默认 10)")

    args = parser.parse_args()

    if args.command == "record":
        if not args.json_data and not args.file:
            print("错误: 请提供 JSON 数据字符串或 -f 文件路径")
            return 1
        return cmd_record(args)
    elif args.command == "list":
        return cmd_list(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
