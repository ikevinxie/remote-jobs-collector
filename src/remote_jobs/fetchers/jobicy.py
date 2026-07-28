"""Jobicy — https://jobicy.com/api/v2/remote-jobs"""
from __future__ import annotations

import html
import json

from ..http import fetch_url
from ..models import Job, clip_description
from ..normalize import map_category, map_region

SOURCE = "jobicy"
URL = "https://jobicy.com/api/v2/remote-jobs?count=100"


def fetch() -> str:
    return fetch_url(URL)


def _salary_text(item: dict) -> str:
    low, high = item.get("annualSalaryMin"), item.get("annualSalaryMax")
    currency = item.get("salaryCurrency") or "USD"
    if low and high:
        return f"{currency} {low:,} - {high:,}"
    if low or high:
        return f"{currency} {(low or high):,}"
    return ""


def parse(raw: str) -> list[Job]:
    jobs: list[Job] = []
    for item in json.loads(raw).get("jobs", []):
        industries = [i for i in (item.get("jobIndustry") or []) if i]
        location = item.get("jobGeo") or ""
        jobs.append(
            Job(
                source=SOURCE,
                source_id=str(item["id"]),
                title=html.unescape(item.get("jobTitle", "")).strip(),
                company=html.unescape(item.get("companyName", "")).strip(),
                category=map_category(industries[0] if industries else ""),
                location_constraint=location,
                region=map_region(location),
                salary_text=_salary_text(item),
                tags=[level for level in [item.get("jobLevel") or ""] if level] + industries,
                url=item.get("url", ""),
                published_at=item.get("pubDate") or "",
                description=clip_description(item.get("jobDescription") or item.get("jobExcerpt")),
            )
        )
    return jobs
