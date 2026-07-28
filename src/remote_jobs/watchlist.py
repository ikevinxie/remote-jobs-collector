"""关注清单:从 watchlist.toml 读规则,对岗位做命中匹配(见 SPEC.md §12)。"""
from __future__ import annotations

import logging
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .models import Job

logger = logging.getLogger(__name__)


@dataclass
class Rule:
    name: str
    keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)
    companies: list[str] = field(default_factory=list)


def load_watchlist(path: str | Path) -> list[Rule]:
    """读取规则;文件不存在、为空或无 rules 表时返回空列表。"""
    path = Path(path)
    if not path.exists():
        return []
    with path.open("rb") as f:
        data = tomllib.load(f)
    rules: list[Rule] = []
    for raw in data.get("rules", []):
        name = str(raw.get("name", "")).strip()
        if not name:
            logger.warning("watchlist 规则缺少 name,已跳过: %r", raw)
            continue
        rules.append(
            Rule(
                name=name,
                keywords=[str(k).lower() for k in raw.get("keywords", [])],
                exclude_keywords=[str(k).lower() for k in raw.get("exclude_keywords", [])],
                categories=list(raw.get("categories", [])),
                regions=list(raw.get("regions", [])),
                companies=[str(c).lower() for c in raw.get("companies", [])],
            )
        )
    return rules


def _contains_word(haystack: str, keyword: str) -> bool:
    """整词匹配:避免 'llm' 命中 'installments'、'ai' 命中 'email' 这类子串误报。"""
    return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", haystack) is not None


def match(job: Job, rule: Rule) -> bool:
    """规则内各维度 AND,维度内列表 OR;未填写的维度不限制。"""
    haystack = " ".join([job.title] + job.tags).lower()
    if rule.exclude_keywords and any(_contains_word(haystack, k) for k in rule.exclude_keywords):
        return False
    if rule.keywords and not any(_contains_word(haystack, k) for k in rule.keywords):
        return False
    if rule.categories and job.category not in rule.categories:
        return False
    if rule.regions and job.region not in rule.regions:
        return False
    if rule.companies and not any(c in job.company.lower() for c in rule.companies):
        return False
    return True


def select_matches(jobs: list[Job], rules: list[Rule]) -> dict[str, list[Job]]:
    """按规则名返回命中岗位;无命中的规则不出现在结果里。"""
    result: dict[str, list[Job]] = {}
    for rule in rules:
        hits = [job for job in jobs if match(job, rule)]
        if hits:
            result[rule.name] = hits
    return result
