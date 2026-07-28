"""周报的交互式 HTML 渲染(发布到 GitHub Pages 用,见 SPEC.md §17/§23)。

与 report.generate_report 同入参;岗位标题链到站内详情页;
「重点关注」与「岗位列表」均为 chips 过滤 + 每页 50 条 DOM 分页。
Markdown 周报(report.py)保持纯文本形态不变。
"""
from __future__ import annotations

import html

from .jobpage import job_page_filename
from .models import Job
from .normalize import CATEGORIES, REGIONS
from .report import DISCLAIMER, SOURCE_NAMES, _wow_suffix
from .theme import THEME_CSS, hero_html

PAGE_SIZE = 50


def render_report_html(
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
    og: dict | None = None,
) -> str:
    esc = html.escape
    og_parts: list[str] = []
    if og:
        description = str(og.get("description", ""))
        og_parts = [
            f'<meta property="og:title" content="{esc(str(og.get("title", "")))}">',
            f'<meta property="og:description" content="{esc(description)}">',
            '<meta property="og:site_name" content="Global Remote Jobs">',
            '<meta property="og:type" content="article">',
            f'<meta name="description" content="{esc(description)}">',
        ]

    hero_sub = (f'<div class="sub">生成时间 | Generated at: {esc(generated_at)}</div>'
                '<div class="nav"><a href="../index.html">🔍 浏览全部岗位 | Browse all jobs</a> · '
                '<a href="index.html">🗂 历史周报 | Archive</a></div>')

    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>远程岗位周报 {esc(week_label)} | Remote Jobs Weekly</title>",
        *og_parts,
        f"<style>{THEME_CSS}</style></head><body>",
        hero_html(f"远程岗位周报 · {week_label}", sub_html=hero_sub),
        '<div class="stats">',
        f'<div class="stat">本周新增 | New this week<b>{len(new_jobs)}</b>'
        f'<span>{esc(_wow_suffix(len(new_jobs), prev_week_new))}</span></div>',
        f'<div class="stat">数据库累计 | Total<b>{total_in_db}</b></div>',
        "</div>",
    ]

    if source_status:
        ok_count = sum(1 for status, _ in source_status.values() if status == "ok")
        parts += [f"<h3>数据源状态 | Source Status({ok_count}/{len(source_status)} ✅)</h3>",
                  "<table><tr><th>来源 Source</th><th>状态 Status</th><th>抓取数 Fetched</th></tr>"]
        for source, (status, count) in source_status.items():
            display = esc(SOURCE_NAMES.get(source, source))
            if status == "ok":
                parts.append(f"<tr><td>{display}</td><td>✅ 正常 OK</td><td>{count}</td></tr>")
            else:
                parts.append(f"<tr><td>{display}</td><td>❌ 失败 Failed: {esc(status)}</td><td>-</td></tr>")
        parts.append("</table>")

    if ai_picks:
        parts.append("<h2>🤖 本周最值得投 | AI Top Picks</h2>"
                     '<p class="sub">点击岗位进详情页,含中文速览与面试准备 | '
                     "Job pages include Chinese TL;DR & interview prep</p>"
                     '<ul class="joblist">')
        for job, score, comment in ai_picks:
            extra = f'<div class="meta">⭐{score:g}' + (f" · {esc(comment)}" if comment else "") + "</div>"
            parts.append(_job_html(job).replace("</li>", extra + "</li>"))
        parts.append("</ul>")

    if watchlist_matches:
        parts.append("<h2>🎯 重点关注 | Watchlist Highlights</h2>")
        chips, items = [], []
        for index, (rule_name, jobs) in enumerate(watchlist_matches.items()):
            chips.append(f'<button class="chip{" active" if index == 0 else ""}" '
                         f'data-filter="w{index}">{esc(rule_name)}({len(jobs)})</button>')
            for job in sorted(jobs, key=lambda j: j.published_at, reverse=True):
                items.append(_job_html(job, pane=f"w{index}", hidden=index != 0))
        parts += [f'<div class="chips" data-list="watchlist">{"".join(chips)}</div>',
                  f'<ul class="joblist" id="watchlist">{"".join(items)}</ul>',
                  '<div class="pager" id="watchlist-pager"></div>']

    group_title = "按职能分组 | Grouped by Category" if group_by == "category" else "按地区分组 | Grouped by Region"
    parts.append(f"<h2>岗位列表 | Job Listings({group_title})</h2>")
    names = CATEGORIES if group_by == "category" else REGIONS
    groups: dict[str, list[Job]] = {}
    for job in new_jobs:
        key = job.category if group_by == "category" else job.region
        groups.setdefault(key if key in names else "other", []).append(job)
    if not groups:
        parts.append('<p class="meta">本周没有新增岗位。 | No new jobs this week.</p>')
    else:
        ordered_keys = sorted(groups, key=lambda k: len(groups[k]), reverse=True)
        chips = [f'<button class="chip active" data-filter="*">全部 | All({len(new_jobs)})</button>']
        items = []
        for key in ordered_keys:
            chinese, english = names[key]
            chips.append(f'<button class="chip" data-filter="{esc(key)}">'
                         f"{esc(chinese)} | {esc(english)}({len(groups[key])})</button>")
        for key in ordered_keys:
            for job in sorted(groups[key], key=lambda j: j.published_at, reverse=True):
                items.append(_job_html(job, pane=key))
        parts += [f'<div class="chips" data-list="listing">{"".join(chips)}</div>',
                  f'<ul class="joblist" id="listing">{"".join(items)}</ul>',
                  '<div class="pager" id="listing-pager"></div>']

    parts += [
        f"<footer><p>{esc(DISCLAIMER)}</p>"
        "数据来源 | Data sources: Remotive, We Work Remotely, "
        '<a href="https://remoteok.com">Remote OK</a>, Jobicy, Himalayas, Working Nomads, '
        "Hacker News Who's Hiring</footer>",
        f"<script>{_SCRIPT}</script>",
        "</body></html>",
    ]
    return "\n".join(parts)


def _job_html(job: Job, *, pane: str = "", hidden: bool = False) -> str:
    esc = html.escape
    detail = f"../jobs/{job_page_filename(job.source, job.source_id)}"
    meta = [f"🏢 {esc(job.company)}",
            f'<a href="{esc(job.url)}" target="_blank" rel="noopener">↗ 原链接 | Source</a>']
    if job.location_constraint:
        meta.append(f"📍 {esc(job.location_constraint)}")
    if job.salary_text:
        meta.append(f"💰 {esc(job.salary_text)}")
    meta.append(f"来源 {esc(SOURCE_NAMES.get(job.source, job.source))}")
    if job.published_at:
        meta.append(esc(job.published_at[:10]))
    pane_attr = f' data-pane="{esc(pane)}"' if pane else ""
    return (f'<li class="job{" hidden" if hidden else ""}"{pane_attr}>'
            f'<a class="title" href="{esc(detail)}">{esc(job.title)}</a>'
            f'<div class="meta">{" · ".join(meta)}</div></li>')


# chips 过滤 + 每页 50 条 DOM 分页(单一 ul + data-pane 属性,不复制 DOM)
_SCRIPT = """
const PAGE_SIZE = %d;
function initFilteredList(chipsSel, listId) {
  const chips = document.querySelector(chipsSel);
  const list = document.getElementById(listId);
  const pager = document.getElementById(listId + "-pager");
  if (!chips || !list) return;
  let page = 1;
  const current = () => chips.querySelector(".chip.active").dataset.filter;
  const matched = () => Array.from(list.children).filter((li) =>
    current() === "*" || li.dataset.pane === current());
  function render() {
    const rows = matched();
    const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    page = Math.min(page, pages);
    Array.from(list.children).forEach((li) => li.classList.add("hidden"));
    rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).forEach((li) => li.classList.remove("hidden"));
    if (!pager) return;
    if (pages <= 1) { pager.innerHTML = rows.length ? "" : "本分类暂无岗位 | No jobs"; return; }
    const options = Array.from({length: pages}, (_, i) =>
      `<option value="${i + 1}"${i + 1 === page ? " selected" : ""}>第 ${i + 1} 页</option>`).join("");
    pager.innerHTML =
      `<button data-nav="-1"${page === 1 ? " disabled" : ""}>‹ 上一页 | Prev</button>` +
      `<select data-jump>${options}</select> <span>/ 共 ${pages} 页 · ${rows.length} 条</span>` +
      `<button data-nav="1"${page === pages ? " disabled" : ""}>下一页 | Next ›</button>`;
  }
  chips.addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    chips.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
    chip.classList.add("active");
    page = 1;
    render();
  });
  if (pager) pager.addEventListener("click", (e) => {
    const nav = e.target.closest("[data-nav]");
    if (nav && !nav.disabled) { page += Number(nav.dataset.nav); render(); }
  });
  if (pager) pager.addEventListener("change", (e) => {
    if (e.target.matches("[data-jump]")) { page = Number(e.target.value); render(); }
  });
  render();
}
initFilteredList('[data-list="watchlist"]', "watchlist");
initFilteredList('[data-list="listing"]', "listing");
""" % PAGE_SIZE
