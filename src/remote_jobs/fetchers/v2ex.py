"""V2EX — 远程工作节点 + 酷工作节点(见 SPEC.md §25)。

老 API 免登录、每节点仅返回最新 10 帖;帖子为自由格式,
宽进严出:剔除已删除/求助讨论帖,酷工作节点必须标题标明远程。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from ..http import fetch_url
from ..models import Job, clip_description
from ..normalize import map_category
from .cn_title import company_from_title

SOURCE = "v2ex"
NODE_URL = "https://www.v2ex.com/api/topics/show.json?node_name={node}"
_NODES = {"remote": "V2EX·远程工作", "jobs": "V2EX·酷工作"}
_CST = timezone(timedelta(hours=8))

_REMOTE_WORD = re.compile(r"(?<![a-zA-Z])remote(?![a-zA-Z])|远程", re.IGNORECASE)
# 求助/讨论帖信号:命中即剔除
_SEEKER = re.compile(r"求职|求\s*offer|请教|应该|怎么|如何|吗|求带|接单")
# 招聘信号:必须命中其一
_HIRING = re.compile(
    r"招|岗位|职位|工程师|经理|设计师|hiring|engineer|developer|manager|designer|薪|\d+\s*k",
    re.IGNORECASE)
# V2EX 方括号惯例是城市/标记(如 [上海]、[内推]),在电鸭否决表基础上增补
_V2EX_VETO = (r"内推|relocate|北京|上海|深圳|广州|杭州|成都|武汉|西安|南京|苏州"
              r"|悉尼|新加坡|外企|可谈")


def fetch() -> str:
    merged: dict[int, dict] = {}
    for node in _NODES:
        for topic in json.loads(fetch_url(NODE_URL.format(node=node))):
            topic["_node"] = node
            merged.setdefault(topic["id"], topic)
    return json.dumps({"topics": list(merged.values())}, ensure_ascii=False)


def _qualified(topic: dict) -> bool:
    if topic.get("deleted"):
        return False
    title = topic.get("title", "")
    if topic.get("_node") == "jobs" and not _REMOTE_WORD.search(title):
        return False  # 酷工作节点必须标题标明远程
    if _SEEKER.search(title):
        return False
    return bool(_HIRING.search(title))


def parse(raw: str) -> list[Job]:
    jobs: list[Job] = []
    for topic in json.loads(raw).get("topics", []):
        if not _qualified(topic):
            continue
        title = topic.get("title", "").strip()
        published = datetime.fromtimestamp(topic.get("created", 0), tz=_CST).isoformat()
        jobs.append(
            Job(
                source=SOURCE,
                source_id=str(topic["id"]),
                title=title,
                company=company_from_title(title, fallback="V2EX 招聘帖", extra_veto=_V2EX_VETO),
                # 帖子标题即最好的类目线索(同 HN 模式,不匹配不算未识别)
                category=map_category(title, record_unknown=False),
                location_constraint="远程(V2EX·中文社区)",
                region="asia_pacific",
                # 中文月薪写法(如 1.2w-2w、15k)不做数字解析,防误判为美元年薪
                salary_text="",
                tags=[_NODES.get(topic.get("_node"), "V2EX")],
                url=topic.get("url") or f"https://www.v2ex.com/t/{topic['id']}",
                published_at=published,
                description=clip_description(topic.get("content_rendered") or topic.get("content")),
            )
        )
    return jobs
