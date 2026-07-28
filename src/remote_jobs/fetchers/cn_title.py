"""中文社区帖标题的公司名启发式(电鸭 / V2EX 共用,见 SPEC.md §24–25)。

社区帖没有结构化公司字段,只能从标题猜:括号内容或分隔符首段,
命中否决词(场景/营销/城市标记等)则放弃,兜底为来源标识。
"""
from __future__ import annotations

import re

_BRACKET = re.compile(r"^[【\[「〔]([^】\]」〕]{1,20})[】\]」〕]")
# 基础否决词:场景/形式/营销话术,而非公司(2026-07-12 电鸭线上样本沉淀)
BASE_VETO = (r"远程|线上|居家|海外|全职|兼职|急招|招聘|直招|坐班|置顶|高薪|寻|大牛|求职"
             r"|^团队$|^我们|^继续|^\d|^remote$")


def company_from_title(title: str, *, fallback: str, extra_veto: str = "") -> str:
    veto = re.compile(BASE_VETO + (f"|{extra_veto}" if extra_veto else ""), re.IGNORECASE)
    title = title.strip()
    bracket = _BRACKET.match(title)
    if bracket:
        name = re.sub(r"(招聘|直招|远程)+$", "", bracket.group(1)).strip()
        if name and not veto.search(name):
            return name
    first = re.split(r"[｜|—\-]", title, maxsplit=1)[0].strip()
    if first and first != title and len(first) <= 16 and not veto.search(first):
        return first
    return fallback
