"""岗位详情静态页(见 SPEC.md §21)。"""
from __future__ import annotations

import hashlib
import html
from datetime import datetime, timezone

from .normalize import CATEGORIES, REGIONS
from .report import DISCLAIMER, SOURCE_NAMES
from .sanitize import sanitize_html
from .theme import THEME_CSS

STALE_DAYS = 7  # last_seen 距生成时间超过该天数,标注「可能已关闭」


def job_page_filename(source: str, source_id: str) -> str:
    digest = hashlib.sha1(f"{source}:{source_id}".encode()).hexdigest()[:16]
    return f"{source}-{digest}.html"


def _days_between(earlier_iso: str, later_iso: str) -> int:
    try:
        earlier = datetime.fromisoformat(earlier_iso)
        later = datetime.fromisoformat(later_iso)
        if earlier.tzinfo is None:
            earlier = earlier.replace(tzinfo=timezone.utc)
        if later.tzinfo is None:
            later = later.replace(tzinfo=timezone.utc)
        return max(0, (later - earlier).days)
    except ValueError:
        return 0


def _format_tz(job: dict) -> str:
    """时区要求展示;推断值加标注。无信息返回空串。"""
    tz_min, tz_max = job.get("tz_min"), job.get("tz_max")
    if tz_min is None:
        return ""
    span = f"UTC{tz_min:+d}" if tz_min == tz_max else f"UTC{tz_min:+d} ~ UTC{tz_max:+d}"
    suffix = "(推断)" if job.get("tz_source") == "inferred" else ""
    return f"🕐 时区 {span}{suffix}"


def render_job_page(job: dict, *, generated_at_iso: str,
                    ai: tuple[float, str] | None = None,
                    extra: dict | None = None) -> str:
    """job 为 db.all_jobs_with_meta 的一行;ai 为 (分数, 点评);
    extra 为 job_ai 表数据(tldr / prep_brief / prep_questions)。"""
    esc = html.escape
    title = job["title"]
    company = job["company"]
    source_name = SOURCE_NAMES.get(job["source"], job["source"])
    chinese_cat, english_cat = CATEGORIES.get(job["category"], CATEGORIES["other"])
    chinese_region, english_region = REGIONS.get(job["region"], REGIONS["other"])

    og_description_bits = [company]
    if job.get("location_constraint"):
        og_description_bits.append(f"📍{job['location_constraint']}")
    if job.get("salary_text"):
        og_description_bits.append(f"💰{job['salary_text']}")
    og_description = " · ".join(og_description_bits)

    meta_bits = [f"🏢 {esc(company)}"]
    if job.get("location_constraint"):
        meta_bits.append(f"📍 {esc(job['location_constraint'])}")
    if job.get("salary_text"):
        meta_bits.append(f"💰 {esc(job['salary_text'])}")
    meta_bits += [
        f"{esc(chinese_cat)} | {esc(english_cat)}",
        f"{esc(chinese_region)} | {esc(english_region)}",
        f"来源 {esc(source_name)}",
    ]
    tz_line = _format_tz(job)
    if tz_line:
        meta_bits.append(esc(tz_line))
    if job.get("published_at"):
        meta_bits.append(f"发布 {esc(job['published_at'][:10])}")

    stale_days = _days_between(job.get("last_seen_at", ""), generated_at_iso)
    stale_banner = (
        f'<div class="banner warn">⚠️ 该岗位已 {stale_days} 天未在来源出现,可能已关闭 | '
        f"Not seen at the source for {stale_days} days — possibly closed</div>"
        if stale_days > STALE_DAYS else ""
    )
    ai_banner = ""
    if ai:
        score, comment = ai
        ai_banner = (f'<div class="banner pick">🤖 AI 精选 ⭐{score:g}'
                     + (f" · {esc(comment)}" if comment else "") + "</div>")

    body = sanitize_html(job.get("description", "")) or '<p class="meta">该来源未提供岗位描述。 | No description provided.</p>'

    extra = extra or {}
    tldr_box = ""
    if extra.get("tldr"):
        tldr_box = f'<div class="banner tldr">🇨🇳 <b>中文速览</b>(AI 生成):{esc(extra["tldr"])}</div>'
    prep_section = ""
    if extra.get("prep_brief") or extra.get("prep_questions"):
        question_items = "".join(f"<li>{esc(q)}</li>" for q in extra.get("prep_questions", []))
        prep_section = (
            '<div class="jd"><h3>🎯 面试准备(AI 生成)| Interview Prep</h3>'
            + (f"<p>{esc(extra['prep_brief'])}</p>" if extra.get("prep_brief") else "")
            + (f"<ol>{question_items}</ol>" if question_items else "")
            + "</div>"
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(company)} | {esc(title)}</title>
<meta property="og:title" content="{esc(f'{company} | {title}')}">
<meta property="og:description" content="{esc(og_description)}">
<meta property="og:site_name" content="Global Remote Jobs">
<meta property="og:type" content="article">
<meta name="description" content="{esc(og_description)}">
<style>{THEME_CSS}</style></head><body>
<div class="sub"><a href="../index.html">← 返回全部岗位 | All jobs</a></div>
<h1>{esc(title)}</h1>
<div class="meta">{" · ".join(meta_bits)}</div>
{ai_banner}
{stale_banner}
{tldr_box}
<p class="meta">{esc(DISCLAIMER)}</p>
<a class="apply" href="{esc(job["url"])}" target="_blank" rel="noopener">去原站申请 | Apply on {esc(source_name)} ↗</a>
<div class="jd">{body}</div>
{prep_section}
<a class="apply" href="{esc(job["url"])}" target="_blank" rel="noopener">去原站申请 | Apply on {esc(source_name)} ↗</a>
<footer>信息采集自 {esc(source_name)},版权归原发布方;内容可能滞后,以原站为准。 |
Collected from {esc(source_name)}; refer to the original posting.</footer>
</body></html>
"""
