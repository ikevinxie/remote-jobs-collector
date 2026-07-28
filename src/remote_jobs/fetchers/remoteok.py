"""Remote OK — https://remoteok.com/api

其 API 条款要求引用数据时注明出处并附回链,周报页脚已包含。
"""
from __future__ import annotations

import json

from ..http import fetch_url
from ..models import Job, clip_description
from ..normalize import map_category, map_region

SOURCE = "remoteok"
URL = "https://remoteok.com/api"


def fetch() -> str:
    return fetch_url(URL)


def _salary_text(item: dict) -> str:
    low, high = item.get("salary_min") or 0, item.get("salary_max") or 0
    if low and high:
        return f"${low:,} - ${high:,}"
    if low or high:
        return f"${(low or high):,}"
    return ""


def _category_from_tags(tags: list[str]) -> str:
    for tag in tags:
        # 标签不是类目,试探不匹配不算"未识别类目"
        mapped = map_category(tag, record_unknown=False)
        if mapped != "other":
            return mapped
    return "other"


def parse(raw: str) -> list[Job]:
    jobs: list[Job] = []
    for item in json.loads(raw):
        if not item.get("id") or not item.get("position"):
            continue  # 首个元素是法律声明,不是岗位
        location = item.get("location") or ""
        tags = list(item.get("tags") or [])
        jobs.append(
            Job(
                source=SOURCE,
                source_id=str(item["id"]),
                title=item.get("position", "").strip(),
                company=item.get("company", "").strip(),
                category=_category_from_tags(tags),
                location_constraint=location,
                region=map_region(location),
                salary_text=_salary_text(item),
                tags=tags,
                url=item.get("url") or f"https://remoteok.com/remote-jobs/{item.get('slug', '')}",
                published_at=item.get("date") or "",
                description=clip_description(item.get("description")),
            )
        )
    return jobs
