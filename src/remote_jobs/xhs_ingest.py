"""导入小红书截图提取的岗位(见 SPEC.md §28)。

小红书无公开 API、风控强,不自动采集。流程:用户把岗位截图丢进 `inbox/xhs/`,
会话用视觉能力提取后写 `reports/<周>-xhs.json`,本模块校验、归一化并入库
(source=xhs)。source_id = sha1(title|company) 前 16 位,稳定,重复 ingest 不重复。
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from . import db as db_module
from .models import Job, clip_description
from .normalize import CATEGORIES, REGIONS, map_category, map_region

logger = logging.getLogger(__name__)

SOURCE = "xhs"
_DEFAULT_LOCATION = "远程(小红书)"


def xhs_source_id(title: str, company: str) -> str:
    """稳定 source_id:标题+公司 的 sha1 前 16 位。同一岗位两次 ingest 不产生重复。"""
    digest = hashlib.sha1(f"{title.strip()}|{company.strip()}".encode("utf-8")).hexdigest()
    return digest[:16]


def _load_entries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(entries, list)
        return [e for e in entries if isinstance(e, dict)]
    except (json.JSONDecodeError, AssertionError, OSError) as error:
        logger.error("小红书 JSON 无法解析,忽略: %s: %s", path, error)
        return []


def _to_job(entry: dict) -> Job | None:
    title = str(entry.get("title", "")).strip()
    company = str(entry.get("company", "")).strip() or "小红书分享"
    if not title:
        return None

    category = str(entry.get("category", "")).strip()
    if category not in CATEGORIES:
        category = map_category(title, record_unknown=False)

    location = str(entry.get("location_constraint", "")).strip() or _DEFAULT_LOCATION
    region = str(entry.get("region", "")).strip()
    if region not in REGIONS:
        # 有原文地区就推断,否则小红书岗位默认全球(多为面向华人的远程)
        region = map_region(location) if entry.get("location_constraint") else "worldwide"

    blogger = str(entry.get("blogger", "")).strip()
    tags = ["小红书"] + ([blogger] if blogger else [])

    return Job(
        source=SOURCE,
        source_id=xhs_source_id(title, company),
        title=title,
        company=company,
        category=category,
        location_constraint=location,
        region=region,
        salary_text=str(entry.get("salary_text", "")).strip(),
        tags=tags,
        url=str(entry.get("url", "")).strip(),
        published_at=str(entry.get("published_at", "")).strip(),
        description=clip_description(str(entry.get("description", "")).strip()),
    )


def ingest_xhs(conn, reports_dir: str | Path, week_label: str, now_iso: str) -> dict[str, int]:
    """读 reports/<周>-xhs.json,校验入库。返回 {inserted, updated, skipped}。"""
    path = Path(reports_dir) / f"{week_label}-xhs.json"
    jobs: list[Job] = []
    skipped = 0
    seen: set[str] = set()
    for entry in _load_entries(path):
        job = _to_job(entry)
        if job is None:
            logger.warning("小红书条目缺 title,跳过: %s", entry)
            skipped += 1
            continue
        if job.source_id in seen:  # 同文件内重复(同 title+company)
            continue
        seen.add(job.source_id)
        jobs.append(job)

    inserted, cross_week_dup = db_module.upsert_jobs(conn, jobs, now_iso)
    updated = len(jobs) - inserted - cross_week_dup  # 已在库、仅刷新的条数
    logger.info("小红书导入:%d 条,新增 %d,更新 %d,跨源重复拦截 %d,非法跳过 %d",
                len(jobs), inserted, updated, cross_week_dup, skipped)
    return {"inserted": inserted, "updated": updated,
            "duplicates": cross_week_dup, "skipped": skipped}
