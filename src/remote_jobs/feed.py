"""RSS 2.0 订阅输出:本周新增岗位(见 SPEC.md §20)。"""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape

from .models import Job
from .normalize import CATEGORIES
from .report import SOURCE_NAMES

MAX_ITEMS = 100


def _rfc822(iso_text: str) -> str:
    try:
        moment = datetime.fromisoformat(iso_text)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return format_datetime(moment)
    except ValueError:
        return ""


def render_feed(new_jobs: list[Job], *, base_url: str, week_label: str, generated_at_iso: str) -> str:
    channel_link = base_url or "https://example.invalid"
    items: list[str] = []
    ordered = sorted(new_jobs, key=lambda j: j.published_at, reverse=True)[:MAX_ITEMS]
    for job in ordered:
        description_bits = [f"🏢 {job.company}"]
        if job.location_constraint:
            description_bits.append(f"📍 {job.location_constraint}")
        if job.salary_text:
            description_bits.append(f"💰 {job.salary_text}")
        chinese, english = CATEGORIES.get(job.category, CATEGORIES["other"])
        description_bits.append(f"{chinese} | {english}")
        description_bits.append(f"来源 {SOURCE_NAMES.get(job.source, job.source)}")
        pub_date = _rfc822(job.published_at)
        items.append(
            "<item>"
            f"<title>{escape(f'{job.company} | {job.title}')}</title>"
            f"<link>{escape(job.url)}</link>"
            f'<guid isPermaLink="false">{escape(f"{job.source}:{job.source_id}")}</guid>'
            + (f"<pubDate>{pub_date}</pubDate>" if pub_date else "")
            + f"<description>{escape(' · '.join(description_bits))}</description>"
            "</item>"
        )
    build_date = _rfc822(generated_at_iso)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        "<title>全球远程岗位 | Global Remote Jobs</title>"
        f"<link>{escape(channel_link)}</link>"
        f"<description>{escape(f'每周自动收集的全球远程工作岗位,本期 {week_label}。Weekly digest of global remote jobs.')}</description>"
        "<language>zh-cn</language>"
        + (f"<lastBuildDate>{build_date}</lastBuildDate>" if build_date else "")
        + "\n".join(items)
        + "</channel></rss>\n"
    )
