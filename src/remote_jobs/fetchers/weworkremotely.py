"""We Work Remotely — https://weworkremotely.com/remote-jobs.rss"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from ..http import fetch_url
from ..models import Job, clip_description
from ..normalize import map_category, map_region

SOURCE = "wwr"
URL = "https://weworkremotely.com/remote-jobs.rss"


def fetch() -> str:
    return fetch_url(URL)


def _text(item: ET.Element, tag: str) -> str:
    node = item.find(tag)
    return (node.text or "").strip() if node is not None else ""


def _published(item: ET.Element) -> str:
    raw = _text(item, "pubDate")
    if not raw:
        return ""
    try:
        return parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return ""


def parse(raw: str) -> list[Job]:
    jobs: list[Job] = []
    for item in ET.fromstring(raw).iter("item"):
        full_title = _text(item, "title")
        # RSS 标题格式为 "公司名: 岗位名"
        company, _, title = full_title.partition(": ")
        if not title:
            company, title = "", full_title
        url = _text(item, "link") or _text(item, "guid")
        location = _text(item, "region")
        skills = _text(item, "skills")
        jobs.append(
            Job(
                source=SOURCE,
                source_id=url,
                title=title.strip(),
                company=company.strip(),
                category=map_category(_text(item, "category")),
                location_constraint=location,
                region=map_region(location),
                salary_text="",
                tags=[s.strip() for s in skills.split(",") if s.strip()],
                url=url,
                published_at=_published(item),
                description=clip_description(_text(item, "description")),
            )
        )
    return jobs
