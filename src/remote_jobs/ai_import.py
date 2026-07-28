"""导入定时会话产出的 AI 文件(中文速览 / 面试准备)到 job_ai 表(见 SPEC.md §22)。"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from . import db as db_module

logger = logging.getLogger(__name__)


def _load_entries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(entries, list)
        return [e for e in entries if isinstance(e, dict)]
    except (json.JSONDecodeError, AssertionError, OSError) as error:
        logger.error("AI 文件无法解析,忽略: %s: %s", path, error)
        return []


def import_ai_files(conn: sqlite3.Connection, reports_dir: str | Path,
                    week_label: str, now_iso: str) -> dict[str, int]:
    """读 <week>-summaries.json 与 <week>-prep.json,校验后入库。返回统计。"""
    reports_dir = Path(reports_dir)
    merged: dict[tuple[str, str], dict] = {}
    skipped = 0

    for entry in _load_entries(reports_dir / f"{week_label}-summaries.json"):
        key = (str(entry.get("source", "")), str(entry.get("source_id", "")))
        tldr = str(entry.get("tldr", "")).strip()
        if not tldr or not db_module.job_exists(conn, *key):
            logger.warning("速览条目非法(空文本或岗位不在库),跳过: %s/%s", *key)
            skipped += 1
            continue
        merged.setdefault(key, {"source": key[0], "source_id": key[1]})["tldr"] = tldr

    prep_count = 0
    for entry in _load_entries(reports_dir / f"{week_label}-prep.json"):
        key = (str(entry.get("source", "")), str(entry.get("source_id", "")))
        brief = str(entry.get("brief", "")).strip()
        questions = [str(q).strip() for q in entry.get("questions", []) if str(q).strip()]
        if not (brief or questions) or not db_module.job_exists(conn, *key):
            logger.warning("面试准备条目非法,跳过: %s/%s", *key)
            skipped += 1
            continue
        item = merged.setdefault(key, {"source": key[0], "source_id": key[1]})
        item["prep_brief"] = brief
        item["prep_questions"] = questions
        prep_count += 1

    db_module.upsert_job_ai(conn, list(merged.values()), now_iso)
    tldr_count = sum(1 for v in merged.values() if v.get("tldr"))
    return {"tldr": tldr_count, "prep": prep_count, "skipped": skipped}
