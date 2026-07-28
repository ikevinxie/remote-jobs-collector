"""AI 精选(picks)协议:消费定时会话 Agent 产出的 reports/<周>-picks.json(见 SPEC.md §18)。

文件格式:[{"source": "hn", "source_id": "48843116", "score": 8.5, "comment": "一句中文点评"}]
脚本只读不写;写入方是每周一定时会话里的 Agent。
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from .db import _row_to_job
from .models import Job

logger = logging.getLogger(__name__)

Pick = tuple[Job, float, str]  # (岗位, 分数 1-10, 点评)


def picks_path(reports_dir: str | Path, week_label: str) -> Path:
    return Path(reports_dir) / f"{week_label}-picks.json"


def load_picks(path: str | Path, conn: sqlite3.Connection) -> list[Pick]:
    """读取并校验 picks;文件缺失/损坏返回空表,非法条目跳过并告警。结果按分数降序。"""
    path = Path(path)
    if not path.exists():
        return []
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(entries, list)
    except (json.JSONDecodeError, AssertionError, OSError) as error:
        logger.error("picks 文件无法解析,忽略: %s: %s", path, error)
        return []

    picks: list[Pick] = []
    for entry in entries:
        if not isinstance(entry, dict):
            logger.warning("picks 条目不是对象,跳过: %r", entry)
            continue
        source, source_id = entry.get("source"), str(entry.get("source_id", ""))
        score, comment = entry.get("score"), str(entry.get("comment", "")).strip()
        if not isinstance(score, (int, float)) or not (1 <= score <= 10):
            logger.warning("picks 分数非法(须 1–10),跳过: %r", entry)
            continue
        row = conn.execute(
            "SELECT * FROM jobs WHERE source = ? AND source_id = ?", (source, source_id)
        ).fetchone()
        if row is None:
            logger.warning("picks 指向不存在的岗位,跳过: %s/%s", source, source_id)
            continue
        picks.append((_row_to_job(row), float(score), comment))
    picks.sort(key=lambda p: p[1], reverse=True)
    return picks
