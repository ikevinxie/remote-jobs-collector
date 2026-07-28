"""GitHub Pages 发布:生成 site/ 静态文件并 git push(见 SPEC.md §17)。"""
from __future__ import annotations

import html
import logging
import re
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


_MANIFEST = """{
  "name": "全球远程岗位 | Global Remote Jobs",
  "short_name": "远程岗位",
  "start_url": "./",
  "display": "standalone",
  "background_color": "#101418",
  "theme_color": "#2563eb",
  "icons": [{ "src": "icon.svg", "sizes": "any", "type": "image/svg+xml" }]
}
"""

_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
<rect width="100" height="100" rx="20" fill="#2563eb"/>
<text x="50" y="66" font-size="52" text-anchor="middle">🌍</text>
</svg>
"""

PWA_HEAD_LINKS = ('<link rel="manifest" href="manifest.webmanifest">'
                  '<link rel="icon" href="icon.svg" type="image/svg+xml">'
                  '<meta name="theme-color" content="#2563eb">')


def generate_site(site_dir: Path, *, browse_html: str, report_html: str, week_label: str,
                  feed_xml: str = "", base_url: str = "",
                  job_pages: dict[str, str] | None = None,
                  generated_date: str = "") -> list[Path]:
    """写入 index.html、reports/<week>.html、feed.xml、README.md,并重建历史列表。"""
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "reports").mkdir(exist_ok=True)

    index_path = site_dir / "index.html"
    index_path.write_text(browse_html, encoding="utf-8")
    report_path = site_dir / "reports" / f"{week_label}.html"
    report_path.write_text(report_html, encoding="utf-8")

    weeks = sorted(
        (p.stem for p in (site_dir / "reports").glob("*.html")
         if re.fullmatch(r"\d{4}-W\d{2}", p.stem)),
        reverse=True,
    )
    reports_index = site_dir / "reports" / "index.html"
    reports_index.write_text(_reports_index_html(weeks), encoding="utf-8")
    written = [index_path, report_path, reports_index]

    if feed_xml:
        feed_path = site_dir / "feed.xml"
        feed_path.write_text(feed_xml, encoding="utf-8")
        written.append(feed_path)
    readme_path = site_dir / "README.md"
    readme_path.write_text(_readme_md(base_url, week_label), encoding="utf-8")
    written.append(readme_path)

    if job_pages is not None:
        # 全量重建:过期岗位的详情页随之消失,防止仓库无限膨胀
        jobs_dir = site_dir / "jobs"
        if jobs_dir.exists():
            shutil.rmtree(jobs_dir)
        jobs_dir.mkdir()
        for filename, page_html in job_pages.items():
            page_path = jobs_dir / filename
            page_path.write_text(page_html, encoding="utf-8")
            written.append(page_path)
        logger.info("详情页已生成 %d 个", len(job_pages))

    # PWA:manifest + 图标(静态内容,每次覆写)
    manifest_path = site_dir / "manifest.webmanifest"
    manifest_path.write_text(_MANIFEST, encoding="utf-8")
    icon_path = site_dir / "icon.svg"
    icon_path.write_text(_ICON_SVG, encoding="utf-8")
    written += [manifest_path, icon_path]

    if base_url:
        sitemap_path = site_dir / "sitemap.xml"
        sitemap_path.write_text(
            _sitemap_xml(base_url, weeks, list(job_pages or {}), generated_date), encoding="utf-8")
        written.append(sitemap_path)
    return written


def _sitemap_xml(base_url: str, weeks: list[str], job_files: list[str], generated_date: str) -> str:
    locations = [f"{base_url}/", f"{base_url}/reports/"]
    locations += [f"{base_url}/reports/{week}.html" for week in weeks]
    locations += [f"{base_url}/jobs/{filename}" for filename in job_files]
    lastmod = f"<lastmod>{html.escape(generated_date)}</lastmod>" if generated_date else ""
    entries = "\n".join(f"<url><loc>{html.escape(loc)}</loc>{lastmod}</url>" for loc in locations)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{entries}\n</urlset>\n")


def _readme_md(base_url: str, week_label: str) -> str:
    from .report import DISCLAIMER

    root = base_url or "."
    disclaimer = DISCLAIMER
    return f"""# 全球远程岗位 | Global Remote Jobs

每周一自动收集的全球远程工作岗位,来自 7 个免费公开数据源
(Remotive、We Work Remotely、Remote OK、Jobicy、Himalayas、Working Nomads、HN Who's Hiring)。

- 🔍 [浏览全部岗位 | Browse all jobs]({root}/index.html)
- 📰 [本周周报 | This week's report]({root}/reports/{week_label}.html)
- 🗂 [历史周报 | Archive]({root}/reports/)
- 📡 [RSS 订阅 | RSS feed]({root}/feed.xml)

手机浏览器打开浏览页后可「添加到主屏幕」,像 App 一样使用。

> {disclaimer}
>
> 本仓库内容由脚本自动生成并每周更新;岗位信息版权归原发布方所有,链接均指向原始出处。
> Auto-generated weekly. All listings link back to their original sources.
"""


def _reports_index_html(weeks: list[str]) -> str:
    items = "\n".join(
        f'<li><a href="{html.escape(w)}.html">{html.escape(w)}</a></li>' for w in weeks
    )
    return (
        '<!DOCTYPE html>\n<html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>历史周报 | Weekly Reports</title></head><body>"
        '<h1>历史周报 | Weekly Reports</h1>'
        f"<ul>{items}</ul>"
        '<p><a href="../index.html">🔍 浏览全部岗位 | Browse all jobs</a></p>'
        "</body></html>\n"
    )


def _run_git(site_dir: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(site_dir), *args],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败: {result.stderr.strip()[:200]}")
    return result.stdout


def git_publish(site_dir: Path, week_label: str, runner=_run_git) -> bool:
    """add/commit/push;无变更视为成功;任何失败只记日志返回 False。"""
    if not (site_dir / ".git").exists():
        logger.warning("site/ 不是 git 仓库,跳过发布(初始化见 README「发布上线」一节)")
        return False
    try:
        runner(site_dir, "add", "-A")
        if not runner(site_dir, "status", "--porcelain").strip():
            logger.info("site/ 无变更,跳过 commit")
            return True
        runner(site_dir, "commit", "-m", f"publish {week_label}")
        runner(site_dir, "push")
        logger.info("site/ 已发布(%s)", week_label)
        return True
    except Exception as error:  # noqa: BLE001 - 发布失败不影响采集主流程
        logger.error("发布失败: %s", error)
        return False
