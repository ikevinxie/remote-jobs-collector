"""本地浏览网页:纯静态单文件 HTML,岗位 JSON 内嵌 + 原生 JS 筛选/分页(见 SPEC.md §14、§20、§23)。

同一份代码渲染本地 web/jobs.html 与线上 site/index.html;
求职工作台状态存 localStorage(键 job-status:<source>:<source_id>),按浏览器隔离。
"""
from __future__ import annotations

import html as html_escape
import json

from .normalize import CATEGORIES, REGIONS
from .report import DISCLAIMER, SOURCE_NAMES
from .theme import TAGLINE, THEME_CSS

_SALARY_STEPS = [0, 30_000, 60_000, 100_000, 150_000, 200_000]
PAGE_SIZE = 50


def render_page(
    jobs: list[dict],
    *,
    generated_at_iso: str,
    report_links: list[tuple[str, str]] | None = None,
    og: dict | None = None,
    rss_href: str = "",
    extra_head: str = "",
    share_qr_svg: str = "",
    share_url: str = "",
) -> str:
    """渲染完整 HTML 页面。jobs 为 db.all_jobs_with_meta 的输出。

    report_links:页头可见入口(标题, href);og:链接预览 meta;rss_href:<link rel=alternate>。
    """
    payload = {
        "generatedAt": generated_at_iso,
        # description 不内嵌:600+ 条 × 15KB 会把单文件撑到数 MB
        "jobs": [{k: v for k, v in job.items() if k != "description"} for job in jobs],
        "categories": {k: f"{zh} | {en}" for k, (zh, en) in CATEGORIES.items()},
        "regions": {k: f"{zh} | {en}" for k, (zh, en) in REGIONS.items()},
        "sources": SOURCE_NAMES,
    }
    # </script> 必须转义,防止岗位文本(标题等)提前闭合 script 标签破坏页面
    data_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    salary_options = "\n".join(
        f'<option value="{v}">{"不限 | Any" if v == 0 else f"≥ {v // 1000}k"}</option>'
        for v in _SALARY_STEPS
    )

    esc = html_escape.escape
    head_parts: list[str] = []
    if og:
        description = str(og.get("description", ""))
        head_parts += [
            f'<meta property="og:title" content="{esc(str(og.get("title", "")))}">',
            f'<meta property="og:description" content="{esc(description)}">',
            '<meta property="og:site_name" content="Global Remote Jobs">',
            '<meta property="og:type" content="website">',
            f'<meta name="description" content="{esc(description)}">',
        ]
    if rss_href:
        head_parts.append(
            f'<link rel="alternate" type="application/rss+xml" title="Global Remote Jobs" href="{esc(rss_href)}">'
        )
    if extra_head:
        head_parts.append(extra_head)
    nav_html = ""
    if report_links:
        anchors = " · ".join(f'<a href="{esc(href)}">{esc(label)}</a>' for label, href in report_links)
        nav_html = f'<div class="nav">{anchors}</div>'

    share_html = ""
    share_button = ""
    if share_qr_svg:
        share_button = '<button class="share-fab" id="share-btn">Share</button>'
        share_html = (
            '<div id="share-panel" class="share-panel hidden">'
            f'<div class="share-box">{share_qr_svg}'
            '<div class="sub">📱 扫码打开本站 | Scan to open</div>'
            + (f'<div class="sub">{esc(share_url)}</div>' if share_url else "")
            # 未来:社交媒体分享按钮加在这个面板里
            + "</div></div>"
        )

    return (
        _TEMPLATE
        .replace("__THEME_CSS__", THEME_CSS)
        .replace("__TAGLINE__", esc(TAGLINE))
        .replace("__DISCLAIMER__", esc(DISCLAIMER))
        .replace("__HEAD_EXTRA__", "\n".join(head_parts))
        .replace("__NAV_LINKS__", nav_html)
        .replace("__SHARE_BUTTON__", share_button)
        .replace("__SHARE_PANEL__", share_html)
        .replace("__DATA_JSON__", data_json)
        .replace("__SALARY_OPTIONS__", salary_options)
    )


_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>全球远程岗位 | Global Remote Jobs</title>
__HEAD_EXTRA__
<style>__THEME_CSS__</style>
</head>
<body>
<div class="hero">
<h1>全球远程岗位 | Global Remote Jobs</h1>
<div class="tagline">__TAGLINE__</div>
<div class="sub" id="generated"></div>
__NAV_LINKS__
</div>

<div class="controls">
  <input type="search" id="search" placeholder="搜索标题/公司/标签 | Search title, company, tags">
  <select id="category"><option value="">职能:全部 | Category: All</option></select>
  <select id="region" title="岗位对求职者所在地区的要求 | Where the job allows you to be based">
    <option value="">👤 所在地要求:不限 | Candidate location: Any</option></select>
  <select id="salary" title="年薪下限 | Min annual salary">__SALARY_OPTIONS__</select>
  <select id="status" title="求职状态 | My status">
    <option value="">状态:全部 | Status: All</option>
    <option value="interested">⭐ 感兴趣 | Interested</option>
    <option value="applied">📮 已投递 | Applied</option>
    <option value="ignored">🙈 忽略 | Ignored</option>
    <option value="none">未标记 | Unmarked</option>
  </select>
  <label class="toggle"><input type="checkbox" id="active" checked> 仅活跃 | Active only</label>
  <label class="toggle"><input type="checkbox" id="fresh"> 仅本周新增 | New this week</label>
  <label class="toggle" title="时区要求与 UTC+5~UTC+11(东八区前后 3 个时区)有交集,或全球可申请且未标时区">
    <input type="checkbox" id="tz8"> 🕐 时区可协作(UTC+8±3)| Workable from UTC+8</label>
</div>

<div class="count" id="count"></div>
<div id="list"></div>
<div class="pager" id="pager"></div>
__SHARE_BUTTON__
__SHARE_PANEL__

<footer>
<p>__DISCLAIMER__</p>
数据来源 | Data sources: Remotive, We Work Remotely,
<a href="https://remoteok.com">Remote OK</a>, Jobicy, Himalayas, Working Nomads,
Hacker News Who's Hiring
</footer>

<script>
const DATA = __DATA_JSON__;

const $ = (id) => document.getElementById(id);
const DAY = 86400e3;
const PAGE_SIZE = 50;
const STATUS_PREFIX = "job-status:";
const generated = new Date(DATA.generatedAt).getTime();
const activeCutoff = new Date(generated - 14 * DAY).toISOString();
const freshCutoff = new Date(generated - 7 * DAY).toISOString();
let page = 1;

$("generated").textContent =
  `数据更新于 | Data as of: ${DATA.generatedAt.slice(0, 16).replace("T", " ")} UTC · 共 ${DATA.jobs.length} 条 | ${DATA.jobs.length} jobs total`;

function fillSelect(id, names) {
  for (const [key, label] of Object.entries(names)) {
    const opt = document.createElement("option");
    opt.value = key; opt.textContent = label;
    $(id).appendChild(opt);
  }
}
fillSelect("category", DATA.categories);
fillSelect("region", DATA.regions);

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
}

const jobKey = (job) => `${job.source}:${job.source_id}`;
function statusOf(job) {
  try { return localStorage.getItem(STATUS_PREFIX + jobKey(job)) || ""; } catch { return ""; }
}

function matches(job) {
  const status = statusOf(job);
  const wantStatus = $("status").value;
  if (wantStatus) {
    if (wantStatus === "none" ? status : status !== wantStatus) return false;
  } else if (status === "ignored") {
    return false; // 默认视图隐藏已忽略的岗位
  }
  const q = $("search").value.trim().toLowerCase();
  if (q) {
    const hay = (job.title + " " + job.company + " " + job.tags.join(" ")).toLowerCase();
    if (!hay.includes(q)) return false;
  }
  if ($("category").value && job.category !== $("category").value) return false;
  if ($("region").value && job.region !== $("region").value) return false;
  const minSalary = Number($("salary").value);
  if (minSalary && !(job.salary_max !== null && job.salary_max >= minSalary)) return false;
  if ($("active").checked && job.last_seen_at < activeCutoff) return false;
  if ($("fresh").checked && job.first_seen_at < freshCutoff) return false;
  if ($("tz8").checked) {
    // 通过 = 时区区间与 UTC+8±3(即 [5, 11])有交集;无时区信息时,全球可申请的宽松放行
    const known = job.tz_min !== null && job.tz_min !== undefined;
    const ok = known ? (job.tz_max >= 5 && job.tz_min <= 11) : job.region === "worldwide";
    if (!ok) return false;
  }
  return true;
}

function markCounts() {
  let interested = 0, applied = 0;
  for (const job of DATA.jobs) {
    const s = statusOf(job);
    if (s === "interested") interested++;
    if (s === "applied") applied++;
  }
  return (interested || applied) ? ` · 我的标记 | My marks: ⭐${interested} 📮${applied}` : "";
}

function jobRow(job) {
  const isFresh = job.first_seen_at >= freshCutoff;
  const status = statusOf(job);
  const salary = job.salary_text ? `💰 ${esc(job.salary_text)}` : "";
  const titleHref = job.detail || job.url;
  const sourceLink = job.detail
    ? `<a href="${esc(job.url)}" target="_blank" rel="noopener">↗ 原链接 | Source</a>` : "";
  return `<div class="job${status ? " marked-" + status : ""}">
    <a class="title" href="${esc(titleHref)}"${job.detail ? "" : ' target="_blank" rel="noopener"'}>${esc(job.title)}</a>
    ${job.ai_score ? `<span class="badge">⭐ ${esc(job.ai_score)}</span>` : ""}
    ${isFresh ? '<span class="badge">本周新增 | New</span>' : ""}
    <div class="meta">
      <span>🏢 ${esc(job.company)}</span>
      ${sourceLink ? `<span>${sourceLink}</span>` : ""}
      <span>📍 ${esc(job.location_constraint) || "-"}</span>
      ${salary ? `<span>${salary}</span>` : ""}
      <span>${esc(DATA.categories[job.category] || job.category)}</span>
      <span>来源 ${esc(DATA.sources[job.source] || job.source)}</span>
      <span>${esc((job.published_at || "").slice(0, 10))}</span>
      <select class="mark" data-job-key="${esc(jobKey(job))}">
        <option value=""${status === "" ? " selected" : ""}>未标记 | Unmarked</option>
        <option value="interested"${status === "interested" ? " selected" : ""}>⭐ 感兴趣 | Interested</option>
        <option value="applied"${status === "applied" ? " selected" : ""}>📮 已投递 | Applied</option>
        <option value="ignored"${status === "ignored" ? " selected" : ""}>🙈 忽略 | Ignored</option>
      </select>
    </div>
  </div>`;
}

function renderPager(pages, total) {
  if (pages <= 1) { $("pager").innerHTML = ""; return; }
  const options = Array.from({length: pages}, (_, i) =>
    `<option value="${i + 1}"${i + 1 === page ? " selected" : ""}>第 ${i + 1} 页</option>`).join("");
  $("pager").innerHTML =
    `<button data-nav="-1"${page === 1 ? " disabled" : ""}>‹ 上一页 | Prev</button>` +
    `<select data-jump>${options}</select> <span>/ 共 ${pages} 页 · ${total} 条</span>` +
    `<button data-nav="1"${page === pages ? " disabled" : ""}>下一页 | Next ›</button>`;
}

function render() {
  const hits = DATA.jobs.filter(matches);
  const pages = Math.max(1, Math.ceil(hits.length / PAGE_SIZE));
  page = Math.min(Math.max(1, page), pages);
  const tzNote = $("tz8").checked
    ? " · ⏱ 部分岗位时区来自 JD 文本推断,可能不准,请以原文为准 | Some timezones are inferred from the JD — verify in the original posting"
    : "";
  $("count").textContent =
    `显示 ${hits.length} / ${DATA.jobs.length} 条 | Showing ${hits.length} of ${DATA.jobs.length}` + markCounts() + tzNote;
  if (!hits.length) {
    $("list").innerHTML = '<div class="empty">没有符合条件的岗位 | No matching jobs</div>';
    $("pager").innerHTML = "";
    return;
  }
  $("list").innerHTML = hits.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map(jobRow).join("");
  renderPager(pages, hits.length);
}

$("pager").addEventListener("click", (event) => {
  const nav = event.target.closest("[data-nav]");
  if (nav && !nav.disabled) { page += Number(nav.dataset.nav); updateHash(); render(); window.scrollTo({top: 0}); }
});
$("pager").addEventListener("change", (event) => {
  if (event.target.matches("[data-jump]")) { page = Number(event.target.value); updateHash(); render(); window.scrollTo({top: 0}); }
});

$("list").addEventListener("change", (event) => {
  const key = event.target.dataset && event.target.dataset.jobKey;
  if (!key) return;
  try {
    if (event.target.value) localStorage.setItem(STATUS_PREFIX + key, event.target.value);
    else localStorage.removeItem(STATUS_PREFIX + key);
  } catch {}
  render();
});

// 可分享筛选:筛选状态 + 页码 ↔ location.hash(URLSearchParams),复制地址栏即分享当前视图
const FILTER_IDS = ["search", "category", "region", "salary", "status", "active", "fresh", "tz8"];
const FILTER_DEFAULTS = { search: "", category: "", region: "", salary: "0",
                          status: "", active: "1", fresh: "0", tz8: "0" };
const filterValue = (el) => el.type === "checkbox" ? (el.checked ? "1" : "0") : el.value;

function applyHashFilters() {
  const params = new URLSearchParams(location.hash.slice(1));
  for (const id of FILTER_IDS) {
    if (!params.has(id)) continue;
    const el = $(id);
    if (el.type === "checkbox") el.checked = params.get(id) === "1";
    else el.value = params.get(id);
  }
  if (params.has("p")) page = Math.max(1, Number(params.get("p")) || 1);
}

function updateHash() {
  const params = new URLSearchParams();
  for (const id of FILTER_IDS) {
    const value = filterValue($(id));
    if (value !== FILTER_DEFAULTS[id]) params.set(id, value);
  }
  if (page !== 1) params.set("p", String(page));
  const serialized = params.toString();
  history.replaceState(null, "", serialized ? "#" + serialized : location.pathname + location.search);
}

const shareButton = $("share-btn");
if (shareButton) {
  shareButton.addEventListener("click", () => $("share-panel").classList.toggle("hidden"));
  $("share-panel").addEventListener("click", (event) => {
    if (event.target.id === "share-panel") $("share-panel").classList.add("hidden");
  });
}

for (const id of FILTER_IDS) {
  $(id).addEventListener("input", () => { page = 1; updateHash(); render(); });
}
applyHashFilters();
render();
</script>
</body>
</html>
"""
