"""统一 Job 数据模型(见 SPEC.md §5)。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Job:
    source: str
    source_id: str
    title: str
    company: str
    category: str  # 归一化职能类目 key,见 normalize.CATEGORIES
    location_constraint: str
    region: str  # 归一化地区 key,见 normalize.REGIONS
    salary_text: str
    tags: list[str] = field(default_factory=list)
    url: str = ""
    published_at: str = ""  # ISO 8601,未知则为空
    description: str = ""  # JD 原文(截断),供 AI 点评读取;浏览网页不内嵌
    tz_min: int | None = None  # 时区要求下限(UTC 偏移),None = 未知
    tz_max: int | None = None
    tz_source: str = ""  # "source" 源提供 / "inferred" 文本推断 / "" 无

    @property
    def fingerprint(self) -> str:
        """跨源去重指纹:标题+公司,忽略大小写、标点与多余空白。"""
        return f"{_norm(self.title)}|{_norm(self.company)}"


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9一-鿿]+", " ", text.lower()).strip()


DESCRIPTION_LIMIT = 15000


def clip_description(text: str | None) -> str:
    return (text or "")[:DESCRIPTION_LIMIT]
