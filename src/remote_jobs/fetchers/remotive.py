"""Remotive — https://remotive.com/api/remote-jobs"""
from __future__ import annotations

import json

from ..http import fetch_url
from ..models import Job, clip_description
from ..normalize import map_category, map_region

SOURCE = "remotive"
URL = "https://remotive.com/api/remote-jobs"


def fetch() -> str:
    return fetch_url(URL)


def parse(raw: str) -> list[Job]:
    jobs: list[Job] = []
    for item in json.loads(raw).get("jobs", []):
        location = item.get("candidate_required_location") or ""
        jobs.append(
            Job(
                source=SOURCE,
                source_id=str(item["id"]),
                title=item.get("title", "").strip(),
                company=item.get("company_name", "").strip(),
                category=map_category(item.get("category", "")),
                location_constraint=location,
                region=map_region(location),
                salary_text=item.get("salary") or "",
                tags=list(item.get("tags") or []),
                url=item.get("url", ""),
                published_at=item.get("publication_date") or "",
                description=clip_description(item.get("description")),
            )
        )
    return jobs
