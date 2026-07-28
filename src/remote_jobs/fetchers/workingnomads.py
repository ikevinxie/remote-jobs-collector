"""Working Nomads — https://www.workingnomads.com/api/exposed_jobs/"""
from __future__ import annotations

import json

from ..http import fetch_url
from ..models import Job, clip_description
from ..normalize import map_category, map_region

SOURCE = "workingnomads"
URL = "https://www.workingnomads.com/api/exposed_jobs/"


def fetch() -> str:
    return fetch_url(URL)


def parse(raw: str) -> list[Job]:
    jobs: list[Job] = []
    for item in json.loads(raw):
        url = item.get("url", "")
        if not url:
            continue
        location = item.get("location") or ""
        tags_text = item.get("tags") or ""
        jobs.append(
            Job(
                source=SOURCE,
                source_id=url,  # 该源无独立 ID,以 URL 为源内唯一键
                title=item.get("title", "").strip(),
                company=item.get("company_name", "").strip(),
                category=map_category(item.get("category_name", "")),
                location_constraint=location,
                region=map_region(location),
                salary_text="",
                tags=[t.strip() for t in tags_text.split(",") if t.strip()],
                url=url,
                published_at=item.get("pub_date") or "",
                description=clip_description(item.get("description")),
            )
        )
    return jobs
