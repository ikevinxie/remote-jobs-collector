"""电鸭社区(eleduck.com)— 中文远程工作社区(见 SPEC.md §24)。

只收「企业直招(tag 8)+ 全职远程(tag 19)」的帖子;服务端 tag 过滤参数不可靠,
必须客户端精确过滤。帖子为自由格式,公司名靠启发式提取,提不出用兜底。
"""
from __future__ import annotations

import json
import re
import time

from ..http import fetch_url
from ..models import Job, clip_description

SOURCE = "eleduck"
LIST_URL = "https://svc.eleduck.com/api/v1/posts?category=5&sort=-published_at&page={page}"
DETAIL_URL = "https://svc.eleduck.com/api/v1/posts/{post_id}"
_LIST_PAGES = 4
_DETAIL_CAP = 40  # 详情请求上限,对源友好
_TAG_DIRECT_HIRE = 8   # 企业直招
_TAG_FULLTIME_REMOTE = 19  # 全职远程

# 职业 tag → 归一化类目
_SKILL_MAP = {"开发": "engineering", "产品": "product", "设计": "design",
              "运营": "ops_hr", "市场": "marketing", "销售": "sales"}

from .cn_title import company_from_title


def _qualified(post: dict) -> bool:
    tag_ids = {tag.get("id") for tag in post.get("tags", [])}
    if not ({_TAG_DIRECT_HIRE, _TAG_FULLTIME_REMOTE} <= tag_ids):
        return False
    if post.get("closed") or post.get("hide") or post.get("deleted") or post.get("pinned"):
        return False
    # 注意:paid_type 正常值是字符串 "free"(真值),不能当布尔用
    return post.get("paid_type") in (None, "", "free")


def fetch() -> str:
    posts: list[dict] = []
    for page in range(1, _LIST_PAGES + 1):
        posts.extend(json.loads(fetch_url(LIST_URL.format(page=page))).get("posts", []))
    qualified = [p for p in posts if _qualified(p)][:_DETAIL_CAP]
    for post in qualified:
        detail = json.loads(fetch_url(DETAIL_URL.format(post_id=post["id"]))).get("post", {})
        post["content"] = detail.get("content") or ""
        time.sleep(0.3)
    return json.dumps({"posts": qualified}, ensure_ascii=False)


def _company_from_title(title: str) -> str:
    # 【付费置顶】这类前缀标记先剥掉,再做提取
    title = re.sub(r"^【付费置顶】\s*", "", title.strip())
    return company_from_title(title, fallback="电鸭直招帖")


def _category(tags: list[dict]) -> str:
    for tag in tags:
        if tag.get("tag_group", {}).get("code") == "skill_type":
            mapped = _SKILL_MAP.get(tag.get("name", ""))
            if mapped:
                return mapped
    return "other"


def parse(raw: str) -> list[Job]:
    jobs: list[Job] = []
    for post in json.loads(raw).get("posts", []):
        if not _qualified(post):
            continue  # parse 兜底再滤一遍,fixture/回放数据同样安全
        tags = post.get("tags", [])
        jobs.append(
            Job(
                source=SOURCE,
                source_id=str(post["id"]),
                title=post.get("title", "").strip(),
                company=_company_from_title(post.get("title", "")),
                category=_category(tags),
                # 中文社区,面向中文/国内时区求职者
                location_constraint="全职远程(电鸭·中文社区)",
                region="asia_pacific",
                # 中文月薪写法("15-25k" 指人民币月薪)会被年薪解析器误判,不提数字
                salary_text="",
                tags=[t.get("name", "") for t in tags if t.get("name")],
                url=f"https://eleduck.com/posts/{post['id']}",
                published_at=post.get("published_at") or "",
                description=clip_description(post.get("content") or post.get("summary")),
            )
        )
    return jobs
