"""Indeed 邮件源(见 SPEC.md §27)。

不爬 Indeed。通过 IMAP 读取用户自己 QQ 邮箱里收到的 Indeed「职位提醒」邮件
(发件人 donotreply@jobalert.indeed.com),从邮件 HTML 中提取岗位。
IMAP/配置逻辑共享自 `_email_source`;本模块只管 Indeed 特有的解析。
"""
from __future__ import annotations

import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from ..models import Job, clip_description
from ..normalize import map_category, map_region
from . import _email_source

SOURCE = "indeed"
# 发件人精确过滤:Indeed 职位提醒(用完整地址——实测 QQ IMAP 的 FROM 搜索
# 匹配完整地址,但不匹配中间子串如 "jobalert.indeed.com")
SENDER = "donotreply@jobalert.indeed.com"


def fetch(config_path: Path = _email_source.MAILBOX_PATH) -> str:
    """IMAP 拉取近 since_days 天的 Indeed 提醒邮件,打包为 JSON。未配置则返回空载荷。"""
    return _email_source.fetch_messages(SENDER, source_label="Indeed", config_path=config_path)


# --- 纯解析:邮件 HTML → 岗位 -------------------------------------------------

def _clean(text: str) -> str:
    return " ".join(text.split()).strip()


def _jk_of(href: str) -> str:
    """从 Indeed 链接取 jk(岗位主键);无则空。兼容 ?jk= 与 &jk=。"""
    query = parse_qs(urlsplit(href).query)
    jk = query.get("jk", [""])[0]
    return jk.strip()


class _CardParser(HTMLParser):
    """把邮件 HTML 拆成有序 token 流。

    Indeed 提醒邮件每张岗位卡片结构稳定:
      标题(在 <h2> 里,可能是 /rc/clk 带 jk 的组织岗,也可能是 /pagead 赞助岗)
      → 公司(纯文本) → 地区(纯文本) → [薪资] → [轻松申请按钮] → JD 摘要 → 发布时间
    因此以「<h2> 内的锚点」为标题锚(比 jk 更稳,且能覆盖赞助岗),其余为纯文本。
    """

    def __init__(self) -> None:
        super().__init__()
        self.tokens: list[tuple[str, str]] = []  # ("title", href) 后紧跟标题文本;或 ("text", value)
        self._skip_depth = 0          # style/script 内文本忽略
        self._h2_depth = 0            # 是否在 <h2> 内
        self._h2_text: list[str] = []
        self._h2_href = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("style", "script"):
            self._skip_depth += 1
        elif tag == "h2":
            self._h2_depth += 1
            self._h2_text = []
            self._h2_href = ""
        elif tag == "a" and self._h2_depth and not self._h2_href:
            self._h2_href = dict(attrs).get("href") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script") and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "h2" and self._h2_depth:
            self._h2_depth -= 1
            title = _clean("".join(self._h2_text))
            if title:
                self.tokens.append(("title", self._h2_href))
                self.tokens.append(("titletext", title))

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._h2_depth:
            self._h2_text.append(data)
            return
        cleaned = _clean(data)
        if cleaned:
            self.tokens.append(("text", cleaned))


# 发布时间 / 申请按钮等非内容文本,组装卡片时跳过
_SKIP_TEXT = re.compile(
    r"^(刚刚发布|轻松申请|立即申请|已保存|保存|查看职位|Easily apply|Just posted|Save|View job"
    r"|\d+\s*(天前|小时前|分钟前|秒前|days?\s+ago|hours?\s+ago|minutes?\s+ago))$",
    re.IGNORECASE,
)
# 薪资样式文本(中文月/时/年薪或币种数字),仅用于识别并跳过,不做数字解析
_SALARY_LIKE = re.compile(r"薪|工资|月收入|[¥$]\s*\d|\d[\d,]*\s*元|/\s*(小时|月|年|hour|month|year)", re.IGNORECASE)
# 公司名后常跟星级评分(如 "3.9"),不是地区
_RATING = re.compile(r"^\d+(\.\d+)?$")
# 邮件页脚 / 促销 / 免责声明样板,出现即视为进入页脚,后续文本全部丢弃
_FOOTER = re.compile(
    r"此处显示的是|继续为求职者|取消.*订阅|管理职位提醒|隐私政策|服务条款|服务中心"
    r"|查看所有招聘职位|浏览招聘职位|借助应用|移动应用|请勿共享|设置此新职位提醒"
    r"|如果职位未提供薪资|©|Indeed Ireland|Operations,?\s*Ltd|unsubscribe|all rights reserved",
    re.IGNORECASE)
_CJK = re.compile(r"[一-鿿]")


def _strip_html_soup(text: str) -> str:
    """清掉描述里偶尔混入的 HTML 碎片(完整标签、残缺尾标签、孤立属性残片)。"""
    text = re.sub(r"<[^>]*>", " ", text)        # 完整标签
    text = re.sub(r"<[^>]*$", " ", text)         # 尾部残缺标签,如 "<p"
    text = re.sub(r'^[^<>]*?"\s*>', " ", text)   # 首部孤立属性残片,如 'inherit">'
    text = re.sub(r'[\w-]+="[^"]*"', " ", text)  # 零散属性
    return _clean(text)


def _card_source_id(href: str, title: str, company: str) -> str:
    """有 jk 用 jk(稳定);赞助岗无 jk,用 title|company 的 sha1 前 16 位兜底。"""
    jk = _jk_of(href)
    if jk:
        return jk
    return "ad-" + hashlib.sha1(f"{title}|{company}".encode("utf-8")).hexdigest()[:16]


def _skippable(text: str) -> bool:
    return bool(_SKIP_TEXT.match(text) or _SALARY_LIKE.search(text) or _RATING.match(text))


def _build_job(href: str, title: str, texts: list[str], published_at: str) -> Job | None:
    if not title:
        return None
    company = texts[0] if texts else ""
    # 地区 = 公司之后第一段有意义文本(跳过评分/时间/按钮/薪资)
    location = ""
    rest_start = len(texts)
    for i in range(1, len(texts)):
        if _skippable(texts[i]):
            continue
        location, rest_start = texts[i], i + 1
        break
    # JD 摘要:地区之后、非样板、最长的一段;清掉偶发的 HTML 碎片
    body = [t for t in texts[rest_start:] if not _skippable(t)]
    description = _strip_html_soup(max(body, key=len, default=""))

    company = company or "Indeed"
    location = location or "远程(Indeed 提醒)"
    region = map_region(location)
    # cn.indeed 的中国岗位提醒:中文地名(如 大连市/兰州市)未命中关键词时默认亚太
    if region == "other" and _CJK.search(location):
        region = "asia_pacific"
    return Job(
        source=SOURCE,
        source_id=_card_source_id(href, title, company),
        title=title,
        company=company,
        category=map_category(title, record_unknown=False),
        location_constraint=location,
        region=region,
        salary_text="",  # 中国岗位薪资多为人民币,不做数字解析(同电鸭/V2EX)
        tags=["Indeed 邮件提醒"],
        url=href,
        published_at=published_at,
        description=clip_description(description or f"来自 Indeed 求职提醒邮件:{title}"),
    )


def parse_email_html(html: str, *, published_at: str = "") -> list[Job]:
    """解析单封邮件 HTML,返回岗位列表(按 source_id 去重)。"""
    parser = _CardParser()
    parser.feed(html or "")

    # 把 token 流按标题切成卡片:每个 title 到下一个 title 之间的 text 属于该卡片
    jobs: dict[str, Job] = {}
    cur_href: str | None = None
    cur_title = ""
    cur_texts: list[str] = []

    def flush() -> None:
        if cur_href is None:
            return
        job = _build_job(cur_href, cur_title, cur_texts, published_at)
        if job and job.title:
            jobs.setdefault(job.source_id, job)

    in_footer = False
    for kind, value in parser.tokens:
        if kind == "title":
            flush()
            cur_href = value
            cur_title = ""
            cur_texts = []
            in_footer = False
        elif kind == "titletext":
            cur_title = value
        elif cur_href is not None and not in_footer:  # text 属于当前卡片
            if _FOOTER.search(value):
                in_footer = True  # 页脚样板起始:本卡片后续文本全部丢弃
                continue
            cur_texts.append(value)
    flush()
    return list(jobs.values())


def parse(raw: str) -> list[Job]:
    """吃 fetch() 的 JSON,逐封解析并按 jk 跨邮件去重。"""
    payload = json.loads(raw)
    merged: dict[str, Job] = {}
    for message in payload.get("messages", []):
        published = _email_source.email_date_to_iso(message.get("date", ""))
        for job in parse_email_html(message.get("html", ""), published_at=published):
            merged.setdefault(job.source_id, job)
    return list(merged.values())
