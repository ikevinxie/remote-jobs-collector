"""LinkedIn 邮件源(见 SPEC.md §29)。

不爬 LinkedIn。通过 IMAP 读取用户自己 QQ 邮箱里收到的「LinkedIn Job Alerts」邮件
(发件人 jobalerts-noreply@linkedin.com),从邮件 HTML 中提取岗位。
IMAP/配置逻辑共享自 `_email_source`;本模块只管 LinkedIn 特有的解析。

结构(2026-07 真实样例):每张卡片 = 岗位链接(`/jobs/view/<id>`,锚文本即标题)
→ 一行「公司 · 地区 (工作方式)」→ 一行状态(Actively recruiting / N school alum,忽略)。
本项目聚焦远程,只保留工作方式为 Remote / Hybrid 的岗位,纯 On-site 丢弃。
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

from ..models import Job, clip_description
from ..normalize import map_category, map_region
from . import _email_source

SOURCE = "linkedin"
SENDER = "jobalerts-noreply@linkedin.com"

_JOB_ID = re.compile(r"/jobs/view/(\d+)")
# 「公司 · 地区 (工作方式)」中的工作方式;paren 可有可无(如 "City (Remote)" / "Remote (Worldwide)")
_WORKTYPE = re.compile(r"\b(remote|hybrid|on-?\s*site)\b", re.IGNORECASE)
_KEEP_WORKTYPE = {"remote", "hybrid"}


def _worktype_of(text: str) -> str:
    m = _WORKTYPE.search(text)
    return re.sub(r"[^a-z]", "", m.group(1).lower()) if m else ""  # remote/hybrid/onsite/""


def fetch(config_path: Path = _email_source.MAILBOX_PATH) -> str:
    """IMAP 拉取近 since_days 天的 LinkedIn Job Alerts 邮件。未配置则返回空载荷。"""
    return _email_source.fetch_messages(SENDER, source_label="LinkedIn", config_path=config_path)


def _clean(text: str) -> str:
    return " ".join(text.split()).strip()


class _CardParser(HTMLParser):
    """有序 token 流:岗位链接锚点 ("job", id, title) 与纯文本 ("text", "", value)。"""

    def __init__(self) -> None:
        super().__init__()
        self.tokens: list[tuple[str, str, str]] = []
        self._href: str | None = None
        self._buf: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("style", "script"):
            self._skip += 1
        elif tag == "a":
            self._href = dict(attrs).get("href") or ""
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script") and self._skip:
            self._skip -= 1
        elif tag == "a" and self._href is not None:
            text = _clean("".join(self._buf))
            m = _JOB_ID.search(self._href)
            if m and text:
                self.tokens.append(("job", m.group(1), text))
            # 非岗位链接的锚文本无用,丢弃(避免污染卡片文本序)
            self._href = None
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._href is not None:
            self._buf.append(data)
        else:
            cleaned = _clean(data)
            if cleaned:
                self.tokens.append(("text", "", cleaned))


def _split_company_location(line: str) -> tuple[str, str, str]:
    """「GE Vernova · Shanghai (Remote)」→ (公司, 地区含工作方式, 工作方式)。"""
    company, _, location = line.partition("·")
    return _clean(company), _clean(location) or _clean(line), _worktype_of(line)


def parse_email_html(html: str, *, published_at: str = "") -> list[Job]:
    parser = _CardParser()
    parser.feed(html or "")

    jobs: dict[str, Job] = {}
    cur_id: str | None = None
    cur_title = ""
    cur_meta = ""  # 「公司 · 地区」行(标题后第一段文本)

    def flush() -> None:
        if cur_id is None or not cur_title:
            return
        company, location, worktype = _split_company_location(cur_meta)
        # 只保留远程/混合;纯 On-site 或无工作方式标记的丢弃
        if worktype not in _KEEP_WORKTYPE:
            return
        if cur_id in jobs:
            return
        jobs[cur_id] = Job(
            source=SOURCE,
            source_id=cur_id,
            title=cur_title,
            company=company or "LinkedIn",
            category=map_category(cur_title, record_unknown=False),
            location_constraint=location or "远程(LinkedIn)",
            region=_region_of(location),
            salary_text="",  # 提醒邮件通常无薪资;中国岗位人民币也不做数字解析
            tags=["LinkedIn 邮件提醒", "Remote" if worktype == "remote" else "Hybrid"],
            # 用规范链接(去掉一次性 tracking 参数),稳定可点
            url=f"https://www.linkedin.com/jobs/view/{cur_id}/",
            published_at=published_at,
            description=clip_description(f"来自 LinkedIn Job Alerts:{cur_title} · {cur_meta}"),
        )

    for kind, ident, value in parser.tokens:
        if kind == "job":
            flush()
            cur_id = ident
            cur_title = value
            cur_meta = ""
        elif kind == "text" and cur_id is not None and not cur_meta:
            cur_meta = value
    flush()
    return list(jobs.values())


def _region_of(location: str) -> str:
    """地区归一化;中文/中国城市未命中关键词时默认亚太(城市名在关键词表里先于
    remote 兜底,故 "Shanghai (Remote)" 会正确判为亚太而非全球)。"""
    region = map_region(location)
    if region == "other" and re.search(r"[一-鿿]", location):
        return "asia_pacific"
    return region


def parse(raw: str) -> list[Job]:
    """吃 fetch() 的 JSON,逐封解析并按 job id 跨邮件去重。"""
    payload = json.loads(raw)
    merged: dict[str, Job] = {}
    for message in payload.get("messages", []):
        published = _email_source.email_date_to_iso(message.get("date", ""))
        for job in parse_email_html(message.get("html", ""), published_at=published):
            merged.setdefault(job.source_id, job)
    return list(merged.values())
