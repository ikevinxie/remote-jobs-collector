"""「清晨海岸」共享主题:全站唯一 CSS 来源(见 SPEC.md §23)。

浏览页 / 周报 HTML / 岗位详情页共用,避免多份样式漂移。
基调:暖沙背景 + 白卡片 + teal→sky 渐变,自由与工作生活平衡的年轻气质。
"""
from __future__ import annotations

import html

TAGLINE = "Work from anywhere 🌴 自由工作,生活在别处 | Own your time, work-life in balance"

THEME_CSS = """
:root {
  --bg: #faf7f2; --card: #ffffff; --fg: #1c2b33; --muted: #687a84;
  --border: #e7e0d4; --accent: #0d9488; --accent2: #0284c7;
  --chip: #e6f4f1; --warn-bg: rgba(217, 119, 6, .10); --warn-border: rgba(217, 119, 6, .45);
  --shadow: 0 1px 2px rgba(28, 43, 51, .05), 0 6px 20px -8px rgba(28, 43, 51, .12);
  --grad: linear-gradient(100deg, var(--accent), var(--accent2));
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0c1418; --card: #122029; --fg: #e7edf0; --muted: #8fa3ad;
    --border: #22333d; --accent: #2dd4bf; --accent2: #38bdf8;
    --chip: #173039; --warn-bg: rgba(251, 191, 36, .10); --warn-border: rgba(251, 191, 36, .4);
    --shadow: 0 1px 2px rgba(0, 0, 0, .3), 0 8px 24px -10px rgba(0, 0, 0, .5);
  }
}
* { box-sizing: border-box; }
body { margin: 0 auto; max-width: 1000px; padding: 28px 18px 72px;
       font: 15px/1.65 -apple-system, "PingFang SC", "Segoe UI", sans-serif;
       background: var(--bg); color: var(--fg); }
h1 { font-size: 26px; margin: 0 0 2px; letter-spacing: .2px;
     background: var(--grad); -webkit-background-clip: text; background-clip: text; color: transparent; }
h2 { font-size: 19px; margin: 34px 0 12px; }
h3 { font-size: 15px; margin: 22px 0 10px; }
a { color: var(--accent2); }
.hero { margin-bottom: 20px; }
.share-fab { position: fixed; right: 16px; bottom: 24px; z-index: 40;
             padding: 10px 20px; border-radius: 999px; border: none; cursor: pointer;
             background: var(--grad); color: #fff; font-size: 14px; font-weight: 650;
             box-shadow: 0 4px 16px rgba(13, 148, 136, .35); }
.share-fab:hover { filter: brightness(1.06); }
.tagline { color: var(--muted); font-size: 14px; margin: 2px 0 8px; }
.sub { color: var(--muted); font-size: 13px; }
.nav { font-size: 13px; margin-top: 6px; }
.nav a { color: var(--accent2); text-decoration: none; margin-right: 4px; }
.nav a:hover { text-decoration: underline; }

.stats { display: flex; flex-wrap: wrap; gap: 10px; margin: 14px 0; }
.stat { background: var(--card); border: 1px solid var(--border); border-radius: 14px;
        padding: 10px 16px; box-shadow: var(--shadow); font-size: 13px; color: var(--muted); }
.stat b { display: block; font-size: 20px; color: var(--fg); }

.chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }
.chip { border: 1px solid var(--border); background: var(--card); color: var(--fg);
        border-radius: 999px; padding: 6px 14px; font-size: 13px; cursor: pointer;
        transition: all .15s; }
.chip:hover { border-color: var(--accent); }
.chip.active { background: var(--grad); color: #fff; border-color: transparent; }

.controls { display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
            padding: 14px; background: var(--card); border: 1px solid var(--border);
            border-radius: 16px; position: sticky; top: 8px; z-index: 5; box-shadow: var(--shadow); }
.controls input[type=search], .controls select {
  padding: 8px 12px; border: 1px solid var(--border); border-radius: 10px;
  background: var(--bg); color: var(--fg); font-size: 14px; }
.controls input[type=search] { flex: 1 1 200px; min-width: 160px; }
.controls label.toggle { display: inline-flex; gap: 5px; align-items: center;
                         font-size: 13px; color: var(--muted); cursor: pointer; }
.count { margin: 14px 2px; color: var(--muted); font-size: 13px; }

.job, li.job { padding: 14px 16px; border: 1px solid var(--border); border-radius: 14px;
       margin-bottom: 10px; background: var(--card); box-shadow: var(--shadow);
       transition: transform .15s, box-shadow .15s; list-style: none; }
.job:hover { transform: translateY(-2px); }
ul.joblist { padding: 0; margin: 0; }
.job a.title { font-weight: 650; color: var(--fg); text-decoration: none; font-size: 15.5px; }
.job a.title:hover { color: var(--accent); }
.meta { margin-top: 6px; color: var(--muted); font-size: 13px;
        display: flex; flex-wrap: wrap; gap: 4px 14px; align-items: center; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 999px;
         background: var(--chip); color: var(--accent); font-size: 12px; margin-left: 8px;
         vertical-align: 1px; font-weight: 600; }
select.mark { padding: 2px 6px; border: 1px solid var(--border); border-radius: 8px;
              background: var(--bg); color: var(--muted); font-size: 12px; }
.job.marked-interested { border-color: var(--accent); }
.job.marked-applied { opacity: .72; }

.pager { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: center;
         margin: 18px 0; font-size: 13px; color: var(--muted); }
.pager button { border: 1px solid var(--border); background: var(--card); color: var(--fg);
                border-radius: 10px; padding: 6px 14px; cursor: pointer; }
.pager button:disabled { opacity: .4; cursor: default; }
.pager button:not(:disabled):hover { border-color: var(--accent); }
.pager select { padding: 5px 8px; border: 1px solid var(--border); border-radius: 8px;
                background: var(--card); color: var(--fg); }

.banner { padding: 12px 16px; border-radius: 12px; margin: 14px 0; font-size: 14px; }
.banner.warn { background: var(--warn-bg); border: 1px solid var(--warn-border); }
.banner.pick { background: var(--card); border: 1.5px solid var(--accent); box-shadow: var(--shadow); }
.banner.tldr { background: var(--card); border: 1px solid var(--border); line-height: 1.75; box-shadow: var(--shadow); }
.apply { display: inline-block; margin: 20px 0; padding: 13px 30px; border-radius: 12px;
         background: var(--grad); color: #fff !important; font-weight: 650; text-decoration: none;
         box-shadow: var(--shadow); }
.apply:hover { filter: brightness(1.06); }
.jd { border-top: 1px solid var(--border); padding-top: 16px; }
.jd p, .jd li { line-height: 1.75; }

table { border-collapse: collapse; font-size: 13px; background: var(--card);
        border-radius: 12px; overflow: hidden; box-shadow: var(--shadow); }
td, th { border: 1px solid var(--border); padding: 6px 12px; text-align: left; }

.share-panel { position: fixed; inset: 0; background: rgba(10, 20, 24, .55);
               display: flex; align-items: center; justify-content: center; z-index: 50; }
.share-box { background: var(--card); border: 1px solid var(--border); border-radius: 18px;
             padding: 26px 30px; text-align: center; box-shadow: var(--shadow); max-width: 320px; }
.share-box svg { width: 220px; height: 220px; border-radius: 10px; }
.share-box .sub { margin-top: 10px; word-break: break-all; }

footer { margin-top: 36px; color: var(--muted); font-size: 12px; line-height: 1.7; }
footer a { color: var(--accent2); }
.empty { text-align: center; color: var(--muted); padding: 48px 0; }
.hidden { display: none !important; }
"""


def hero_html(title: str, *, sub_html: str = "", tagline: str = TAGLINE) -> str:
    """页头 hero:渐变标题 + 标语 + 可选副内容(已转义的 HTML)。"""
    return (f'<div class="hero"><h1>{html.escape(title)}</h1>'
            f'<div class="tagline">{html.escape(tagline)}</div>{sub_html}</div>')
