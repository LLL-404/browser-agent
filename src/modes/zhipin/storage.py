"""数据持久化模块，提供 SQLite 数据库的初始化与 CRUD 操作。"""

import contextlib
import json
import sqlite3
from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DB_PATH = Path("data/jobs.db")


@dataclass
class JobQuery:
    """职位查询条件，避免 get_jobs 参数过多。"""
    status: str | None = None
    city: str | None = None
    min_score: int | None = None
    limit: int = 50
    offset: int = 0
    exclude_ignored: bool = True


def _connect() -> sqlite3.Connection:
    """创建数据库连接，启用 WAL 模式提升并发性能。"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """初始化数据库表结构（jobs、search_log、chat_templates），不存在则创建。"""
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            boss_job_id TEXT UNIQUE,
            title TEXT,
            company TEXT,
            salary TEXT,
            city TEXT,
            tags TEXT,
            recruiter_active TEXT,
            description TEXT,
            company_info TEXT,
            job_url TEXT,
            status TEXT DEFAULT 'new',
            five_insurance INTEGER DEFAULT 0,
            room_board INTEGER DEFAULT 0,
            regular_hours INTEGER DEFAULT 0,
            overtime_risk TEXT,
            diploma_ok INTEGER DEFAULT 0,
            recruiter_active_bool INTEGER DEFAULT 0,
            match_score INTEGER DEFAULT 0,
            ai_reason TEXT,
            verified INTEGER DEFAULT 0,
            keyword TEXT,
            source TEXT DEFAULT 'boss',
            created_at TEXT,
            analyzed_at TEXT,
            applied_at TEXT
        );

        CREATE TABLE IF NOT EXISTS search_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT UNIQUE,
            status TEXT DEFAULT 'pending',
            job_count INTEGER DEFAULT 0,
            started_at TEXT,
            finished_at TEXT
        );

        CREATE TABLE IF NOT EXISTS chat_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            template TEXT,
            used INTEGER DEFAULT 0,
            created_at TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        );
    """)
    conn.commit()

    # 兼容旧表：如果缺少新列则添加
    with contextlib.suppress(sqlite3.OperationalError):
        conn.execute("ALTER TABLE jobs ADD COLUMN verified INTEGER DEFAULT 0")
    with contextlib.suppress(sqlite3.OperationalError):
        conn.execute("ALTER TABLE jobs ADD COLUMN keyword TEXT")
    with contextlib.suppress(sqlite3.OperationalError):
        conn.execute("ALTER TABLE jobs ADD COLUMN source TEXT DEFAULT 'boss'")

    conn.commit()
    conn.close()


def insert_job(data: dict) -> bool:
    """插入单条职位，已存在则跳过。返回是否成功插入"""
    now = datetime.now().isoformat()
    conn = _connect()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO jobs
                (boss_job_id, title, company, salary, city, tags,
                 recruiter_active, description, company_info, job_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("boss_job_id"),
            data.get("title"),
            data.get("company"),
            data.get("salary"),
            data.get("city"),
            json.dumps(data.get("tags", []), ensure_ascii=False),
            data.get("recruiter_active"),
            data.get("description"),
            data.get("company_info"),
            data.get("job_url"),
            now,
        ))
        conn.commit()
        inserted = conn.total_changes > 0
        return inserted
    finally:
        conn.close()


def update_search_log(city: str, status: str, job_count: int = 0):
    """记录城市的搜索进度（开始→进行中→完成）。"""
    now = datetime.now().isoformat()
    conn = _connect()
    try:
        existing = conn.execute(
            "SELECT id FROM search_log WHERE city = ?", (city,)
        ).fetchone()
        if existing:
            conn.execute("""
                UPDATE search_log
                SET status = ?, job_count = ?, finished_at = ?
                WHERE city = ?
            """, (status, job_count, now, city))
        else:
            conn.execute("""
                INSERT INTO search_log (city, status, job_count, started_at)
                VALUES (?, ?, ?, ?)
            """, (city, status, job_count, now))
        conn.commit()
    finally:
        conn.close()


def get_searched_cities() -> set[str]:
    """返回已完成搜索的城市列表，用于增量搜索跳过已搜城市。"""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT city FROM search_log WHERE status = 'done'"
        ).fetchall()
        return {r["city"] for r in rows}
    finally:
        conn.close()


def count_jobs_by_status(status: str | None = None) -> dict[str, int] | int:
    """统计职位数量。
    不传 status 时返回所有状态的计数字典，传 status 时返回该状态的数量。
    """
    conn = _connect()
    try:
        if status:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM jobs WHERE status = ?", (status,)
            ).fetchone()
            return row["cnt"]
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM jobs GROUP BY status"
        ).fetchall()
        return {r["status"]: r["cnt"] for r in rows}
    finally:
        conn.close()


def get_recent_logs(limit: int = 10) -> list[tuple]:
    """返回最近搜索日志：(城市, 入库数, 最后更新时间)"""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT city, job_count, MAX(started_at) as last_time "
            "FROM search_log WHERE status='done' "
            "GROUP BY city ORDER BY last_time DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [(r["city"], r["job_count"], r["last_time"]) for r in rows]
    finally:
        conn.close()


def get_jobs_stream(query: JobQuery | None = None) -> Generator[dict, None, None]:
    """游标式逐行返回职位列表（不含全文），避免大数据量时 O(n) 内存。

    参数:
        query: JobQuery 查询条件，不传则使用默认值。

    产生:
        每行一个 dict，适合内存受限场景或流式处理。
    """
    if query is None:
        query = JobQuery()
    conn = _connect()
    try:
        conditions = []
        params = []
        if query.status:
            conditions.append("status = ?")
            params.append(query.status)
        if query.city:
            conditions.append("city = ?")
            params.append(query.city)
        if query.min_score is not None:
            conditions.append("match_score >= ?")
            params.append(query.min_score)
        if query.exclude_ignored:
            conditions.append("status != 'ignored'")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"""
            SELECT id, boss_job_id, title, company, salary, city, tags,
                   recruiter_active, job_url, status, match_score, ai_reason,
                   five_insurance, room_board, regular_hours, overtime_risk,
                   diploma_ok, recruiter_active_bool
            FROM jobs
            {where}
            ORDER BY match_score DESC, id DESC
            LIMIT ? OFFSET ?
        """
        params.extend([query.limit, query.offset])
        rows = conn.execute(sql, params)
        for row in rows:
            yield _row_to_dict(row)
    finally:
        conn.close()


def get_jobs(query: JobQuery | None = None) -> list[dict]:
    """查询职位列表（不含全文，轻量），按匹配分降序排列。

    参数:
        query: JobQuery 查询条件，不传则使用默认值。
    """
    return list(get_jobs_stream(query))


def get_job_by_id(job_id: int) -> dict | None:
    """读取单条职位完整信息，含全文"""
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row:
            return _row_to_dict(row)
        return None
    finally:
        conn.close()


def batch_update_jobs(results: list[dict]) -> tuple[int, int]:
    """批量更新 AI 分析结果，使用 executemany 一次提交。返回 (成功数, 失败数)。"""
    if not results:
        return 0, 0
    now = datetime.now().isoformat()
    _sql = """
        UPDATE jobs SET
            five_insurance = ?, room_board = ?, regular_hours = ?,
            overtime_risk = ?, diploma_ok = ?,
            recruiter_active_bool = ?,
            match_score = ?, ai_reason = ?,
            status = 'analyzed', analyzed_at = ?
        WHERE id = ?
    """
    _params = [
        (_bool_to_int(item.get("five_insurance")),
         _bool_to_int(item.get("room_board")),
         _bool_to_int(item.get("regular_hours")),
         item.get("overtime_risk"),
         _bool_to_int(item.get("diploma_ok")),
         _bool_to_int(item.get("recruiter_active")),
         item.get("match_score", 0),
         item.get("reason", ""),
         now,
         item.get("job_id"))
        for item in results
    ]
    conn = _connect()
    try:
        conn.execute("BEGIN")
        conn.executemany(_sql, _params)
        conn.commit()
        return len(results), 0
    except sqlite3.Error:
        conn.rollback()
        # 回退到逐条更新，记录各条成败
        success = 0
        fail = 0
        for item in results:
            try:
                conn.execute(_sql, (
                    _bool_to_int(item.get("five_insurance")),
                    _bool_to_int(item.get("room_board")),
                    _bool_to_int(item.get("regular_hours")),
                    item.get("overtime_risk"),
                    _bool_to_int(item.get("diploma_ok")),
                    _bool_to_int(item.get("recruiter_active")),
                    item.get("match_score", 0),
                    item.get("reason", ""),
                    now,
                    item.get("job_id"),
                ))
                success += 1
            except sqlite3.Error:
                fail += 1
        conn.commit()
        return success, fail
    finally:
        conn.close()


def update_job_status(job_id: int, status: str):
    """更新职位状态（applied/interview/offered/rejected/ignored）。"""
    now = datetime.now().isoformat()
    conn = _connect()
    try:
        if status == "applied":
            conn.execute(
                "UPDATE jobs SET status = ?, applied_at = ? WHERE id = ?",
                (status, now, job_id)
            )
        else:
            conn.execute(
                "UPDATE jobs SET status = ? WHERE id = ?",
                (status, job_id)
            )
        conn.commit()
    finally:
        conn.close()


def insert_chat_template(job_id: int, template: str):
    """保存 AI 生成的招呼语模板到数据库。"""
    now = datetime.now().isoformat()
    conn = _connect()
    try:
        conn.execute("""
            INSERT INTO chat_templates (job_id, template, created_at)
            VALUES (?, ?, ?)
        """, (job_id, template, now))
        conn.commit()
    finally:
        conn.close()


def get_stats() -> dict:
    """获取求职数据的全局统计概览。"""
    conn = _connect()
    try:
        total = conn.execute("SELECT COUNT(*) as cnt FROM jobs").fetchone()["cnt"]
        new_c = conn.execute(
            "SELECT COUNT(*) as cnt FROM jobs WHERE status='new'"
        ).fetchone()["cnt"]
        analyzed = conn.execute(
            "SELECT COUNT(*) as cnt FROM jobs WHERE status='analyzed'"
        ).fetchone()["cnt"]
        applied = conn.execute(
            "SELECT COUNT(*) as cnt FROM jobs WHERE status='applied'"
        ).fetchone()["cnt"]
        recommended = conn.execute(
            "SELECT COUNT(*) as cnt FROM jobs WHERE match_score >= 6"
        ).fetchone()["cnt"]
        searched = conn.execute(
            "SELECT COUNT(*) as cnt FROM search_log WHERE status='done'"
        ).fetchone()["cnt"]
        total_cities = conn.execute(
            "SELECT COUNT(*) as cnt FROM search_log"
        ).fetchone()["cnt"]

        city_rows = conn.execute(
            "SELECT city, COUNT(*) as cnt FROM jobs GROUP BY city ORDER BY cnt DESC LIMIT 10"
        ).fetchall()

        return {
            "total_jobs": total,
            "new": new_c,
            "analyzed": analyzed,
            "applied": applied,
            "recommended": recommended,
            "searched_cities": searched,
            "total_cities_in_queue": total_cities,
            "top_cities": {r["city"]: r["cnt"] for r in city_rows},
        }
    finally:
        conn.close()


def get_unanalyzed_jobs(limit: int = 50) -> list[dict]:
    """获取待分析职位，含完整描述"""
    conn = _connect()
    try:
        rows = conn.execute("""
            SELECT * FROM jobs
            WHERE status = 'new'
            ORDER BY id ASC
            LIMIT ?
        """, (limit,)).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    if "tags" in d and isinstance(d["tags"], str):
        try:
            d["tags"] = json.loads(d["tags"])
        except json.JSONDecodeError:
            d["tags"] = []
    return d


def _bool_to_int(val) -> int:
    if val is True:
        return 1
    if val is False:
        return -1
    return 0


def get_all_companies() -> list[str]:
    """获取所有待验证公司名称（去重）。"""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT DISTINCT company FROM jobs WHERE company IS NOT NULL AND company != ''"
        ).fetchall()
        return [r["company"] for r in rows]
    finally:
        conn.close()


def update_company_info(info: dict):
    """更新公司验证信息到 company_info 字段。

    info 包含: company, found_date, register_capital, social_insurance, status
    """
    conn = _connect()
    try:
        company_info = json.dumps(info, ensure_ascii=False)
        conn.execute(
            "UPDATE jobs SET company_info = ?, verified = 1 WHERE company = ?",
            (company_info, info["company"])
        )
        conn.commit()
    finally:
        conn.close()
