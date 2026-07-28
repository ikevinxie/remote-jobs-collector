"""中英双语 Markdown 周报生成(见 SPEC.md §7)。"""
from __future__ import annotations

from .models import Job
from .normalize import CATEGORIES, REGIONS

SOURCE_NAMES = {
    "remotive": "Remotive",
    "wwr": "We Work Remotely",
    "remoteok": "Remote OK",
    "jobicy": "Jobicy",
    "himalayas": "Himalayas",
    "workingnomads": "Working Nomads",
    "hn": "HN Who's Hiring",
    "eleduck": "电鸭社区",
    "v2ex": "V2EX",
}

# 全站统一防诈免责声明(浏览页/详情页/周报/公开仓 README 共用,避免文案漂移)
DISCLAIMER = (
    "⚠️ 请仔细甄别招聘信息真假:本站仅自动聚合公开信息,不对其真实性负责;"
    "凡要求缴费、垫资、提供银行卡密码的均为骗局。 | "
    "Listings are auto-aggregated from public sources; we don't verify them. "
    "Beware of job scams — never pay to apply."
)

_FOOTER = (
    "数据来源 | Data sources: Remotive, We Work Remotely, "
    "[Remote OK](https://remoteok.com), Jobicy, Himalayas, Working Nomads, "
    "Hacker News Who's Hiring, 电鸭社区, V2EX"
)


def generate_report(
    new_jobs: list[Job],
    *,
    week_label: str,
    generated_at: str,
    total_in_db: int,
    source_status: dict[str, tuple[str, int]] | None = None,
    group_by: str = "category",
    watchlist_matches: dict[str, list[Job]] | None = None,
    prev_week_new: int | None = None,
    ai_picks: list[tuple[Job, float, str]] | None = None,
) -> str:
    if group_by not in ("category", "region"):
        raise ValueError(f"group_by 只支持 category / region,收到 {group_by!r}")

    lines: list[str] = [
        f"# 全球远程岗位周报 | Global Remote Jobs Weekly — {week_label}",
        "",
        f"> 生成时间 | Generated at: {generated_at}",
        "",
        "## 概览 | Overview",
        "",
        f"- 本周新增岗位 | New jobs this week: **{len(new_jobs)}**{_wow_suffix(len(new_jobs), prev_week_new)}",
        f"- 数据库累计岗位 | Total jobs in database: **{total_in_db}**",
        "",
    ]

    if source_status:
        lines += [
            "### 数据源状态 | Source Status",
            "",
            "| 来源 Source | 状态 Status | 抓取数 Fetched |",
            "|---|---|---|",
        ]
        for source, (status, count) in source_status.items():
            display = SOURCE_NAMES.get(source, source)
            if status == "ok":
                lines.append(f"| {display} | ✅ 正常 OK | {count} |")
            else:
                lines.append(f"| {display} | ❌ 失败 Failed: {status} | - |")
        lines.append("")

    if ai_picks:
        lines += ["## 🤖 本周最值得投 | AI Top Picks", "",
                  "> 站点详情页含中文速览与面试准备 | Chinese TL;DR & interview prep on the site's job pages", ""]
        for job, score, comment in ai_picks:
            lines.append(f"{_format_job(job)} · ⭐{score:g}")
            if comment:
                lines.append(f"  > {comment}")
        lines.append("")

    if watchlist_matches:
        lines += ["## 🎯 重点关注 | Watchlist Highlights", ""]
        for rule_name, jobs in watchlist_matches.items():
            lines += [f"### {rule_name}({len(jobs)})", ""]
            lines += [_format_job(job) for job in sorted(jobs, key=lambda j: j.published_at, reverse=True)]
            lines.append("")

    group_title = "按职能分组 | Grouped by Category" if group_by == "category" else "按地区分组 | Grouped by Region"
    lines += [f"## 岗位列表 | Job Listings({group_title})", ""]

    names = CATEGORIES if group_by == "category" else REGIONS
    groups: dict[str, list[Job]] = {}
    for job in new_jobs:
        key = job.category if group_by == "category" else job.region
        groups.setdefault(key if key in names else "other", []).append(job)

    if not groups:
        lines += ["本周没有新增岗位。 | No new jobs this week.", ""]

    for key in sorted(groups, key=lambda k: len(groups[k]), reverse=True):
        chinese, english = names[key]
        jobs = sorted(groups[key], key=lambda j: j.published_at, reverse=True)
        lines += [f"### {chinese} | {english}({len(jobs)})", ""]
        lines += [_format_job(job) for job in jobs]
        lines.append("")

    lines += ["---", "", f"> {DISCLAIMER}", "", _FOOTER, ""]
    return "\n".join(lines)


def _wow_suffix(this_week: int, prev_week: int | None) -> str:
    """环比文案;上周无数据(None)或为 0 时不算百分比。"""
    if prev_week is None:
        return ""
    if prev_week == 0:
        return f"(上周 | last week: 0)"
    change = (this_week - prev_week) / prev_week * 100
    return f"(上周 | last week: {prev_week},环比 | WoW: {change:+.0f}%)"


def _format_job(job: Job) -> str:
    parts = [f"- [{job.title}]({job.url}) — **{job.company}**"]
    if job.location_constraint:
        parts.append(f"📍 {job.location_constraint}")
    if job.salary_text:
        parts.append(f"💰 {job.salary_text}")
    parts.append(f"来源 Source: {SOURCE_NAMES.get(job.source, job.source)}")
    if job.published_at:
        parts.append(f"发布 Published: {job.published_at[:10]}")
    return " · ".join(parts)
