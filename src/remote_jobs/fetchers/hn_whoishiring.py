"""Hacker News "Ask HN: Who is hiring?" 月度帖(Algolia HN Search API,见 SPEC.md §15)。

自由文本评论源,宽进严出:只收「顶层评论 + 首行含整词 REMOTE + 竖线分隔格式」,
解析不出的评论直接跳过,不算失败。
"""
from __future__ import annotations

import html
import json
import re

from ..http import fetch_url
from ..models import Job, clip_description
from ..normalize import map_category, map_region

SOURCE = "hn"
STORY_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring&hitsPerPage=10"
COMMENTS_URL = "https://hn.algolia.com/api/v1/search_by_date?tags=comment,story_{story_id}&hitsPerPage=1000&page={page}"
_MAX_PAGES = 5

_REMOTE_WORD = re.compile(r"(?<![a-z])remote(?![a-z])", re.IGNORECASE)
_SALARY_HINT = re.compile(r"[$€£]|\d+\s*k\b", re.IGNORECASE)


def fetch() -> str:
    stories = json.loads(fetch_url(STORY_SEARCH_URL))["hits"]
    story = next(s for s in stories if s.get("title", "").startswith("Ask HN: Who is hiring?"))
    story_id = int(story["objectID"])

    hits: list[dict] = []
    for page in range(_MAX_PAGES):
        data = json.loads(fetch_url(COMMENTS_URL.format(story_id=story_id, page=page)))
        hits.extend(data["hits"])
        if page + 1 >= data.get("nbPages", 1):
            break
    return json.dumps({"story_id": story_id, "story_title": story["title"], "hits": hits})


def _first_line(comment_html: str) -> str:
    """首行 = 第一个 <p> 之前的文本,去标签并解码 HTML 实体。"""
    head = (comment_html or "").split("<p>", 1)[0]
    return html.unescape(re.sub(r"<[^>]+>", " ", head)).strip()


def parse(raw: str) -> list[Job]:
    data = json.loads(raw)
    story_id = data["story_id"]
    month_tag = _month_tag(data.get("story_title", ""))

    jobs: list[Job] = []
    for item in data["hits"]:
        if item.get("parent_id") != story_id:
            continue  # 只要顶层评论,回复丢弃
        line = _first_line(item.get("comment_text", ""))
        if not _REMOTE_WORD.search(line):
            continue  # Onsite 或未标明远程
        segments = [s.strip() for s in line.split("|") if s.strip()]
        if len(segments) < 2:
            continue  # 不符合 "公司 | 职位 | ..." 惯例,无法可靠解析
        company, title = segments[0], segments[1]
        location = next((s for s in segments[2:] if _REMOTE_WORD.search(s)), "")
        salary = next((s for s in segments[2:] if _SALARY_HINT.search(s)), "")
        jobs.append(
            Job(
                source=SOURCE,
                source_id=str(item["objectID"]),
                title=title,
                company=company,
                # 职位名不是类目,keyword 启发式够用,不匹配不算未识别
                category=map_category(title, record_unknown=False),
                location_constraint=location,
                region=map_region(line),
                salary_text=salary,
                tags=[month_tag] if month_tag else [],
                url=f"https://news.ycombinator.com/item?id={item['objectID']}",
                published_at=item.get("created_at") or "",
                # 评论全文(去标签解码),AI 点评直接可读
                description=clip_description(
                    html.unescape(re.sub(r"<[^>]+>", " ", item.get("comment_text") or ""))
                ),
            )
        )
    return jobs


def _month_tag(story_title: str) -> str:
    """"Ask HN: Who is hiring? (July 2026)" -> "HN 2026-07"。"""
    match = re.search(r"\((\w+) (\d{4})\)", story_title)
    if not match:
        return "HN"
    months = ["January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]
    try:
        month_number = months.index(match.group(1)) + 1
    except ValueError:
        return "HN"
    return f"HN {match.group(2)}-{month_number:02d}"
