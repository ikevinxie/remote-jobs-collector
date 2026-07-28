"""Himalayas — https://himalayas.app/jobs/api"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..http import fetch_url
from ..models import Job, clip_description
from ..normalize import map_category, map_region

SOURCE = "himalayas"
URL = "https://himalayas.app/jobs/api?limit=100"


def fetch() -> str:
    return fetch_url(URL)


def _salary_text(item: dict) -> str:
    low, high = item.get("minSalary"), item.get("maxSalary")
    currency = item.get("currency") or "USD"
    if low and high:
        return f"{currency} {low:,} - {high:,}"
    if low or high:
        return f"{currency} {(low or high):,}"
    return ""


def parse(raw: str) -> list[Job]:
    jobs: list[Job] = []
    for item in json.loads(raw).get("jobs", []):
        restrictions = [r for r in (item.get("locationRestrictions") or []) if r]
        location = ", ".join(restrictions) if restrictions else "Worldwide"
        categories = [c for c in (item.get("parentCategories") or item.get("categories") or []) if c]
        pub_epoch = item.get("pubDate")
        published = (
            datetime.fromtimestamp(pub_epoch, tz=timezone.utc).isoformat()
            if isinstance(pub_epoch, (int, float))
            else ""
        )
        url = item.get("guid") or item.get("applicationLink") or ""
        tz_offsets = [t for t in (item.get("timezoneRestrictions") or []) if isinstance(t, (int, float))]
        jobs.append(
            Job(
                tz_min=int(min(tz_offsets)) if tz_offsets else None,
                tz_max=int(max(tz_offsets)) if tz_offsets else None,
                tz_source="source" if tz_offsets else "",
                source=SOURCE,
                source_id=url,
                title=item.get("title", "").strip(),
                company=item.get("companyName", "").strip(),
                category=map_category(categories[0] if categories else ""),
                location_constraint=location,
                region=map_region(location),
                salary_text=_salary_text(item),
                tags=list(item.get("seniority") or []) + categories,
                url=url,
                published_at=published,
                description=clip_description(item.get("description") or item.get("excerpt")),
            )
        )
    return jobs
