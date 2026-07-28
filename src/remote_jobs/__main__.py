"""CLI 入口:
    python3 run.py run                 # 采集 + 入库 + 生成本周周报
    python3 run.py report              # 仅从数据库重新生成周报(不抓取)
    python3 run.py prune --days 180    # 清理超过 N 天未再见到的岗位
    run/report 可选:--group-by {category,region} --days N --watchlist PATH
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db as db_module
from .ai_import import import_ai_files
from .dedupe import dedupe
from .feed import render_feed
from .fetchers import ALL_FETCHERS
from .models import Job
from .normalize import UNKNOWN_CATEGORIES
from .notify import load_channels, load_pages_config, notify_all, pick_highlights
from .jobpage import job_page_filename, render_job_page
from .picks import load_picks, picks_path
from .profiles import load_profiles
from .publish import PWA_HEAD_LINKS, generate_site, git_publish
from .qr import qr_svg
from .report import generate_report
from .report_html import render_report_html
from .timezones import infer_range
from .watchlist import load_watchlist, select_matches
from .webpage import render_page
from .xhs_ingest import ingest_xhs

ROOT = Path(__file__).resolve().parents[2]

logger = logging.getLogger("remote_jobs")


def collect(status: dict[str, tuple[str, int]]) -> list[Job]:
    """逐源抓取解析;单源失败不阻塞整体,状态记入 status。"""
    jobs: list[Job] = []
    for fetcher in ALL_FETCHERS:
        try:
            parsed = fetcher.parse(fetcher.fetch())
            for job in parsed:
                # 源没提供时区信息时,从地区限制 + JD 开头做保守推断
                if job.tz_min is None:
                    inferred = infer_range(f"{job.location_constraint} {job.description[:500]}")
                    if inferred:
                        job.tz_min, job.tz_max = inferred
                        job.tz_source = "inferred"
            status[fetcher.SOURCE] = ("ok", len(parsed))
            jobs.extend(parsed)
            logger.info("%s: 抓取到 %d 条", fetcher.SOURCE, len(parsed))
        except Exception as error:  # noqa: BLE001 - 单源容错是设计要求
            status[fetcher.SOURCE] = (str(error)[:80], 0)
            logger.error("%s: 采集失败: %s", fetcher.SOURCE, error)
    return jobs


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="remote_jobs", description="每周收集全球远程工作岗位")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_report_options(p: argparse.ArgumentParser) -> None:
        p.add_argument("--group-by", choices=["category", "region"], default="category")
        p.add_argument("--days", type=int, default=7, help="周报覆盖最近 N 天新增(默认 7)")
        p.add_argument("--db", default=str(ROOT / "data" / "jobs.db"))
        p.add_argument("--reports-dir", default=str(ROOT / "reports"))
        p.add_argument("--watchlist", default=str(ROOT / "watchlist.toml"))
        p.add_argument("--notify-config", default=str(ROOT / "notify.toml"))
        p.add_argument("--site-dir", default=str(ROOT / "site"))
        p.add_argument("--profiles-dir", default=str(ROOT / "profiles"))

    run_parser = sub.add_parser("run", help="采集 + 入库 + 生成周报 + 发布 + 推送通知")
    add_report_options(run_parser)
    run_parser.add_argument("--skip-notify", action="store_true",
                            help="跳过 IM 通知(定时会话先打分写 picks 再单独 notify 时用)")
    add_report_options(sub.add_parser("report", help="仅从数据库重新生成周报"))
    notify_parser = sub.add_parser("notify", help="基于当前数据库重发一次 IM 通知(验证配置用)")
    add_report_options(notify_parser)
    notify_parser.add_argument("--profile", default="", help="只给指定 profile 重发")
    add_report_options(sub.add_parser("publish", help="生成 site/ 静态页面并 git push 上线"))

    prune_parser = sub.add_parser("prune", help="清理长期未再见到的岗位")
    prune_parser.add_argument("--days", type=int, default=180, help="删除超过 N 天未见的岗位(默认 180)")
    prune_parser.add_argument("--db", default=str(ROOT / "data" / "jobs.db"))

    web_parser = sub.add_parser("web", help="从数据库生成本地浏览网页")
    web_parser.add_argument("--db", default=str(ROOT / "data" / "jobs.db"))
    web_parser.add_argument("--out", default=str(ROOT / "web" / "jobs.html"))

    ai_parser = sub.add_parser("import-ai", help="导入定时会话产出的中文速览/面试准备 JSON")
    ai_parser.add_argument("--week", required=True, help="ISO 周号,如 2026-W28")
    ai_parser.add_argument("--db", default=str(ROOT / "data" / "jobs.db"))
    ai_parser.add_argument("--reports-dir", default=str(ROOT / "reports"))

    xhs_parser = sub.add_parser("ingest-xhs", help="导入小红书截图提取的岗位 JSON(见 SPEC §28)")
    xhs_parser.add_argument("--week", required=True, help="ISO 周号,如 2026-W29")
    xhs_parser.add_argument("--db", default=str(ROOT / "data" / "jobs.db"))
    xhs_parser.add_argument("--reports-dir", default=str(ROOT / "reports"))

    ai_all_parser = sub.add_parser(
        "ai-all",
        help="调用百炼 API 一次性产出 picks/summaries/prep 三个 JSON(替代本地 Claude Code 会话)")
    ai_all_parser.add_argument("--week", required=True, help="ISO 周号,如 2026-W29")
    ai_all_parser.add_argument("--days", type=int, default=7,
                               help="候选窗口:最近 N 天 first_seen 的岗位(默认 7)")
    ai_all_parser.add_argument("--db", default=str(ROOT / "data" / "jobs.db"))
    ai_all_parser.add_argument("--reports-dir", default=str(ROOT / "reports"))
    ai_all_parser.add_argument("--profiles-dir", default=str(ROOT / "profiles"))
    ai_all_parser.add_argument("--watchlist", default=str(ROOT / "watchlist.toml"))
    ai_all_parser.add_argument("--notify-config", default=str(ROOT / "notify.toml"))
    ai_all_parser.add_argument("--profile-md", default=str(ROOT / "profile.md"),
                               help="个性化打分视角文件,存在则启用,缺省自动检测")

    xhs_extract_parser = sub.add_parser(
        "xhs-extract",
        help="用视觉模型提取 inbox/xhs/ 下未归档截图里的岗位,写 reports/<W>-xhs.json")
    xhs_extract_parser.add_argument("--week", required=True, help="ISO 周号,如 2026-W29")
    xhs_extract_parser.add_argument("--inbox", default=str(ROOT / "inbox" / "xhs"))
    xhs_extract_parser.add_argument("--reports-dir", default=str(ROOT / "reports"))
    return parser


def _write_webpage(conn, out_path: Path, now_iso: str) -> Path:
    jobs = db_module.all_jobs_with_meta(conn)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_page(jobs, generated_at_iso=now_iso), encoding="utf-8")
    return out_path


def _cmd_ai_all_with_conn(conn, args) -> int:
    import json as _json
    from . import llm as llm_mod

    since_iso = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()
    new_jobs = db_module.jobs_first_seen_since(conn, since_iso)
    profiles = load_profiles(Path(args.profiles_dir), args.watchlist, args.notify_config)
    seen: set[tuple[str, str]] = set()
    candidates: list[dict] = []
    for profile in profiles:
        matches = select_matches(new_jobs, load_watchlist(profile.watchlist_path))
        for jobs in matches.values():
            for job in jobs:
                key = (job.source, job.source_id)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append({
                    "source": job.source,
                    "source_id": job.source_id,
                    "title": job.title,
                    "company": job.company,
                    "salary_text": job.salary_text,
                    "location_constraint": job.location_constraint,
                    "region": job.region,
                    "description": job.description,
                })
    by_key = {(c["source"], c["source_id"]): c for c in candidates}
    print(f"候选岗位 {len(candidates)} 条(本周 watchlist 命中,去重后)", flush=True)
    if not candidates:
        print("⚠ 无候选,跳过 AI 产出(写空数组占位,避免下游 import-ai 报错)",
              file=sys.stderr, flush=True)

    profile_md = ""
    pm_path = Path(args.profile_md)
    if pm_path.exists():
        profile_md = pm_path.read_text(encoding="utf-8")
        print(f"启用个性化打分视角: {pm_path}", flush=True)

    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    picks = llm_mod.score_picks(candidates, profile_md=profile_md) if candidates else []
    (reports_dir / f"{args.week}-picks.json").write_text(
        _json.dumps(picks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {args.week}-picks.json ({len(picks)} 条)", flush=True)

    summaries = llm_mod.write_summaries(candidates) if candidates else []
    (reports_dir / f"{args.week}-summaries.json").write_text(
        _json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {args.week}-summaries.json ({len(summaries)} 条)", flush=True)

    prep = llm_mod.write_prep(picks, by_key) if picks else []
    (reports_dir / f"{args.week}-prep.json").write_text(
        _json.dumps(prep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {args.week}-prep.json ({len(prep)} 条)", flush=True)
    return 0


def _cmd_xhs_extract(args) -> int:
    import json as _json
    from . import llm as llm_mod

    inbox = Path(args.inbox)
    if not inbox.exists():
        print(f"inbox 不存在: {inbox},跳过", flush=True)
        return 0
    images = sorted([p for p in inbox.iterdir()
                     if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")])
    if not images:
        print(f"inbox/xhs/ 无未归档截图,跳过", flush=True)
        return 0
    notes_path = inbox / "notes.md"
    notes = notes_path.read_text(encoding="utf-8") if notes_path.exists() else ""
    all_jobs: list[dict] = []
    for img in images:
        print(f"  视觉提取: {img.name}", flush=True)
        try:
            jobs = llm_mod.extract_xhs_jobs(img, notes=notes)
        except Exception as e:  # noqa: BLE001 - 单图失败不阻塞其他图
            print(f"  ⚠ {img.name} 提取失败: {e}", file=sys.stderr, flush=True)
            continue
        print(f"    → {len(jobs)} 条岗位", flush=True)
        all_jobs.extend(jobs)
    out = Path(args.reports_dir) / f"{args.week}-xhs.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_json.dumps(all_jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {out.name} (合计 {len(all_jobs)} 条,来自 {len(images)} 张截图)", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    conn = db_module.connect(args.db)

    if args.command == "import-ai":
        stats = import_ai_files(conn, args.reports_dir, args.week, now_iso)
        print(f"AI 产物导入完成:中文速览 {stats['tldr']} 条,面试准备 {stats['prep']} 条,跳过 {stats['skipped']} 条")
        return 0

    if args.command == "ingest-xhs":
        stats = ingest_xhs(conn, args.reports_dir, args.week, now_iso)
        print(f"小红书导入完成:新增 {stats['inserted']} 条,更新 {stats['updated']} 条,"
              f"跨源重复拦截 {stats['duplicates']} 条,非法跳过 {stats['skipped']} 条")
        return 0

    if args.command == "ai-all":
        return _cmd_ai_all_with_conn(conn, args)

    if args.command == "xhs-extract":
        return _cmd_xhs_extract(args)

    if args.command == "web":
        path = _write_webpage(conn, Path(args.out), now_iso)
        print(f"浏览页面已生成: {path}({db_module.total_count(conn)} 条岗位)")
        return 0

    if args.command == "prune":
        cutoff = (now - timedelta(days=args.days)).isoformat()
        deleted = db_module.prune(conn, cutoff)
        print(f"已清理 {deleted} 条超过 {args.days} 天未见的岗位,剩余 {db_module.total_count(conn)} 条")
        return 0

    source_status: dict[str, tuple[str, int]] = {}
    if args.command == "run":
        jobs = dedupe(collect(source_status))
        if not jobs and source_status and all(s != "ok" for s, _ in source_status.values()):
            logger.error("全部数据源采集失败,本次不生成周报")
            return 1
        inserted, duplicates_skipped = db_module.upsert_jobs(conn, jobs, now_iso)
        logger.info("入库完成:%d 条中新增 %d 条,拦截跨周重复 %d 条",
                    len(jobs), inserted, duplicates_skipped)
        if UNKNOWN_CATEGORIES:
            logger.warning(
                "本次出现 %d 个未识别类目,请按 SPEC §10 沉淀映射与测试用例: %s",
                len(UNKNOWN_CATEGORIES), sorted(UNKNOWN_CATEGORIES),
            )

    since_iso = (now - timedelta(days=args.days)).isoformat()
    prev_since_iso = (now - timedelta(days=args.days * 2)).isoformat()
    new_jobs = db_module.jobs_first_seen_since(conn, since_iso)
    prev_week_new = db_module.count_first_seen_between(conn, prev_since_iso, since_iso)
    iso_year, iso_week, _ = now.isocalendar()
    week_label = f"{iso_year}-W{iso_week:02d}"

    profiles = load_profiles(Path(args.profiles_dir), args.watchlist, args.notify_config)
    if args.command == "notify" and args.profile:
        profiles = [p for p in profiles if p.name == args.profile]
        if not profiles:
            print(f"找不到 profile: {args.profile}(应为 profiles/ 下的目录名)")
            return 1
    profile_matches = [(p, select_matches(new_jobs, load_watchlist(p.watchlist_path))) for p in profiles]

    # 周报用的合并视图:多人时版块标题带人名前缀
    multi_profile = len(profiles) > 1
    watchlist_matches: dict[str, list[Job]] = {}
    for profile, matches in profile_matches:
        for rule_name, jobs in matches.items():
            key = f"{profile.name} · {rule_name}" if multi_profile and profile.name else rule_name
            watchlist_matches[key] = jobs
    if watchlist_matches:
        logger.info("关注清单命中 %d 个版块(%d 个 profile)", len(watchlist_matches), len(profiles))

    report_path = Path(args.reports_dir) / f"{week_label}.md"
    ai_picks = load_picks(picks_path(args.reports_dir, week_label), conn)
    if ai_picks:
        logger.info("加载 AI 精选 %d 条", len(ai_picks))
    report_kwargs = dict(
        ai_picks=ai_picks or None,
        week_label=week_label,
        generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
        total_in_db=db_module.total_count(conn),
        source_status=source_status or None,
        group_by=args.group_by,
        watchlist_matches=watchlist_matches or None,
        prev_week_new=prev_week_new,
    )
    if args.command in ("run", "report"):
        markdown = generate_report(new_jobs, **report_kwargs)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(markdown, encoding="utf-8")
        print(f"周报已生成: {report_path}(本周新增 {len(new_jobs)} 条,库存 {db_module.total_count(conn)} 条)")

    if args.command == "run":
        web_path = _write_webpage(conn, ROOT / "web" / "jobs.html", now_iso)
        print(f"浏览页面已更新: {web_path}")

    site_dir = Path(args.site_dir)
    if args.command == "publish" or (args.command == "run" and (site_dir / ".git").exists()):
        base_url = next(
            (url for p in profiles if (url := load_pages_config(p.notify_path))), ""
        )
        jobs_meta = db_module.all_jobs_with_meta(conn)
        total = db_module.total_count(conn)

        # 活跃岗位(60 天内在源可见)生成详情页;浏览页标题链接指向详情
        active_cutoff = (now - timedelta(days=60)).isoformat()
        ai_index = {(job.source, job.source_id): (score, comment) for job, score, comment in ai_picks}
        ai_extras = db_module.job_ai_map(conn)
        job_pages: dict[str, str] = {}
        for job_meta in jobs_meta:
            key = (job_meta["source"], job_meta["source_id"])
            if job_meta["last_seen_at"] >= active_cutoff:
                filename = job_page_filename(*key)
                job_pages[filename] = render_job_page(job_meta, generated_at_iso=now_iso,
                                                      ai=ai_index.get(key),
                                                      extra=ai_extras.get(key))
                job_meta["detail"] = f"jobs/{filename}"
            if key in ai_index:
                job_meta["ai_score"] = f"{ai_index[key][0]:g}"

        generate_site(
            site_dir,
            browse_html=render_page(
                jobs_meta,
                generated_at_iso=now_iso,
                report_links=[
                    ("📰 本周周报 | This week", f"reports/{week_label}.html"),
                    ("🗂 历史周报 | Archive", "reports/"),
                    ("📡 RSS", "feed.xml"),
                ],
                og={
                    "title": "全球远程岗位 | Global Remote Jobs",
                    "description": f"{total} 个全球远程岗位,每周一自动更新 · 7 个免费数据源",
                },
                rss_href="feed.xml",
                extra_head=PWA_HEAD_LINKS,
                share_qr_svg=qr_svg(f"{base_url}/") if base_url else "",
                share_url=f"{base_url}/" if base_url else "",
            ),
            report_html=render_report_html(
                new_jobs, **report_kwargs,
                og={
                    "title": f"远程岗位周报 {week_label} | Remote Jobs Weekly",
                    "description": f"本周新增 {len(new_jobs)} 个远程岗位 · New remote jobs this week",
                },
            ),
            week_label=week_label,
            feed_xml=render_feed(new_jobs, base_url=base_url,
                                 week_label=week_label, generated_at_iso=now_iso),
            base_url=base_url,
            job_pages=job_pages,
            generated_date=now_iso[:10],
        )
        published = git_publish(site_dir, week_label)
        print(f"站点发布: {'✅ 已上线' if published else '⚠️ 页面已生成,推送未完成(详见日志)'}")

    if args.command == "notify" or (args.command == "run" and not args.skip_notify):
        stats = {
            "new_count": len(new_jobs),
            "prev_week_new": prev_week_new,
            "total": db_module.total_count(conn),
        }
        any_channel = False
        for profile, matches in profile_matches:
            channels = load_channels(profile.notify_path)
            if not channels:
                continue
            any_channel = True
            base_url = load_pages_config(profile.notify_path)
            report_url = f"{base_url}/reports/{week_label}.html" if base_url else ""
            results = notify_all(channels, pick_highlights(matches),
                                 stats, week_label, str(report_path),
                                 report_url=report_url, ai_picks=ai_picks or None,
                                 base_url=base_url)
            label = f"[{profile.name}] " if profile.name else ""
            for provider, ok in results.items():
                print(f"通知 {label}{provider}: {'✅ 已发送' if ok else '❌ 失败(详见日志)'}")
        if not any_channel and args.command == "notify":
            print("未配置任何通知通道,请编辑 notify.toml(见文件内说明)")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
