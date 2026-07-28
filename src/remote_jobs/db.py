"""SQLite 存取:upsert 维护 first_seen_at / last_seen_at。"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from .models import Job
from .salary import parse_salary

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    source              TEXT NOT NULL,
    source_id           TEXT NOT NULL,
    title               TEXT NOT NULL,
    company             TEXT NOT NULL,
    category            TEXT NOT NULL,
    location_constraint TEXT NOT NULL DEFAULT '',
    region              TEXT NOT NULL DEFAULT 'other',
    salary_text         TEXT NOT NULL DEFAULT '',
    tags                TEXT NOT NULL DEFAULT '[]',
    url                 TEXT NOT NULL,
    published_at        TEXT NOT NULL DEFAULT '',
    fingerprint         TEXT NOT NULL,
    first_seen_at       TEXT NOT NULL,
    last_seen_at        TEXT NOT NULL,
    salary_min          INTEGER,
    salary_max          INTEGER,
    salary_currency     TEXT,
    description         TEXT NOT NULL DEFAULT '',
    tz_min              INTEGER,
    tz_max              INTEGER,
    tz_source           TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (source, source_id)
);
CREATE TABLE IF NOT EXISTS job_ai (
    source          TEXT NOT NULL,
    source_id       TEXT NOT NULL,
    tldr            TEXT NOT NULL DEFAULT '',
    prep_brief      TEXT NOT NULL DEFAULT '',
    prep_questions  TEXT NOT NULL DEFAULT '[]',
    updated_at      TEXT NOT NULL,
    PRIMARY KEY (source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_jobs_fingerprint ON jobs (fingerprint);
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs (first_seen_at);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """老库(M1 schema)无损升级:补齐后来新增的列。"""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
    for column, column_type in (
        ("salary_min", "INTEGER"),
        ("salary_max", "INTEGER"),
        ("salary_currency", "TEXT"),
        ("description", "TEXT NOT NULL DEFAULT ''"),
        ("tz_min", "INTEGER"),
        ("tz_max", "INTEGER"),
        ("tz_source", "TEXT NOT NULL DEFAULT ''"),
    ):
        if column not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {column} {column_type}")
    conn.commit()


DUPLICATE_WINDOW_DAYS = 30  # 跨周重发判定窗口:同指纹、30 天内在库 → 视为重复


def upsert_jobs(conn: sqlite3.Connection, jobs: list[Job], now_iso: str) -> tuple[int, int]:
    """写入岗位:新岗位记 first_seen;已有岗位仅刷新 last_seen 与可变字段。

    跨周去重(SPEC §24):新 (source, source_id) 但库中存在同 fingerprint 且
    last_seen 在 30 天内的其他岗位 → 视为同岗位重发,跳过。
    返回 (新增数, 拦截的跨周重复数)。
    """
    duplicate_cutoff = (datetime.fromisoformat(now_iso) - timedelta(days=DUPLICATE_WINDOW_DAYS)).isoformat()
    inserted = 0
    duplicates_skipped = 0
    for job in jobs:
        existed = conn.execute(
            "SELECT 1 FROM jobs WHERE source = ? AND source_id = ?",
            (job.source, job.source_id),
        ).fetchone() is not None
        if not existed and conn.execute(
            "SELECT 1 FROM jobs WHERE fingerprint = ? AND last_seen_at >= ?"
            " AND NOT (source = ? AND source_id = ?) LIMIT 1",
            (job.fingerprint, duplicate_cutoff, job.source, job.source_id),
        ).fetchone():
            duplicates_skipped += 1
            continue
        conn.execute(
            """
            INSERT INTO jobs (source, source_id, title, company, category,
                              location_constraint, region, salary_text, tags, url,
                              published_at, fingerprint, first_seen_at, last_seen_at,
                              salary_min, salary_max, salary_currency, description,
                              tz_min, tz_max, tz_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (source, source_id) DO UPDATE SET
                title = excluded.title,
                company = excluded.company,
                category = excluded.category,
                location_constraint = excluded.location_constraint,
                region = excluded.region,
                salary_text = excluded.salary_text,
                tags = excluded.tags,
                url = excluded.url,
                published_at = excluded.published_at,
                fingerprint = excluded.fingerprint,
                last_seen_at = excluded.last_seen_at,
                salary_min = excluded.salary_min,
                salary_max = excluded.salary_max,
                salary_currency = excluded.salary_currency,
                description = excluded.description,
                tz_min = excluded.tz_min,
                tz_max = excluded.tz_max,
                tz_source = excluded.tz_source
            """,
            (
                job.source, job.source_id, job.title, job.company, job.category,
                job.location_constraint, job.region, job.salary_text,
                json.dumps(job.tags, ensure_ascii=False), job.url,
                job.published_at, job.fingerprint, now_iso, now_iso,
                *(parse_salary(job.salary_text) or (None, None, None)),
                job.description,
                job.tz_min, job.tz_max, job.tz_source,
            ),
        )
        if not existed:
            inserted += 1
    conn.commit()
    return inserted, duplicates_skipped


def jobs_first_seen_since(conn: sqlite3.Connection, since_iso: str) -> list[Job]:
    rows = conn.execute(
        "SELECT * FROM jobs WHERE first_seen_at >= ? ORDER BY published_at DESC",
        (since_iso,),
    ).fetchall()
    return [_row_to_job(row) for row in rows]


def total_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"]


def count_first_seen_between(conn: sqlite3.Connection, start_iso: str, end_iso: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) AS n FROM jobs WHERE first_seen_at >= ? AND first_seen_at < ?",
        (start_iso, end_iso),
    ).fetchone()["n"]


def all_jobs_with_meta(conn: sqlite3.Connection) -> list[dict]:
    """全量岗位(含 seen 时间与解析后薪资),供本地浏览网页使用。"""
    rows = conn.execute("SELECT * FROM jobs ORDER BY published_at DESC").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["tags"] = json.loads(item["tags"])
        result.append(item)
    return result


def prune(conn: sqlite3.Connection, cutoff_iso: str) -> int:
    """删除 last_seen_at 早于 cutoff 的岗位,返回删除数;随后 VACUUM 回收空间。"""
    deleted = conn.execute("DELETE FROM jobs WHERE last_seen_at < ?", (cutoff_iso,)).rowcount
    conn.commit()
    conn.execute("VACUUM")
    return deleted


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        source=row["source"],
        source_id=row["source_id"],
        title=row["title"],
        company=row["company"],
        category=row["category"],
        location_constraint=row["location_constraint"],
        region=row["region"],
        salary_text=row["salary_text"],
        tags=json.loads(row["tags"]),
        url=row["url"],
        published_at=row["published_at"],
        description=row["description"],
        tz_min=row["tz_min"],
        tz_max=row["tz_max"],
        tz_source=row["tz_source"],
    )


def upsert_job_ai(conn: sqlite3.Connection, entries: list[dict], now_iso: str) -> int:
    """写入 AI 产物(中文速览/面试准备);entries 已经过 import-ai 校验。返回写入数。"""
    for entry in entries:
        conn.execute(
            """
            INSERT INTO job_ai (source, source_id, tldr, prep_brief, prep_questions, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (source, source_id) DO UPDATE SET
                tldr = CASE WHEN excluded.tldr != '' THEN excluded.tldr ELSE job_ai.tldr END,
                prep_brief = CASE WHEN excluded.prep_brief != '' THEN excluded.prep_brief ELSE job_ai.prep_brief END,
                prep_questions = CASE WHEN excluded.prep_questions != '[]' THEN excluded.prep_questions ELSE job_ai.prep_questions END,
                updated_at = excluded.updated_at
            """,
            (entry["source"], entry["source_id"], entry.get("tldr", ""),
             entry.get("prep_brief", ""),
             json.dumps(entry.get("prep_questions", []), ensure_ascii=False), now_iso),
        )
    conn.commit()
    return len(entries)


def job_ai_map(conn: sqlite3.Connection) -> dict[tuple[str, str], dict]:
    """全部 AI 产物,键 (source, source_id),值含 tldr / prep_brief / prep_questions。"""
    result: dict[tuple[str, str], dict] = {}
    for row in conn.execute("SELECT * FROM job_ai"):
        result[(row["source"], row["source_id"])] = {
            "tldr": row["tldr"],
            "prep_brief": row["prep_brief"],
            "prep_questions": json.loads(row["prep_questions"]),
        }
    return result


def job_exists(conn: sqlite3.Connection, source: str, source_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM jobs WHERE source = ? AND source_id = ?", (source, source_id)
    ).fetchone() is not None
