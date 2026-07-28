from pathlib import Path

from remote_jobs.models import Job
from remote_jobs.publish import generate_site, git_publish
from remote_jobs.report_html import render_report_html


def make_job(source_id="1", **kw):
    defaults = dict(source="remotive", title="Backend Engineer", company="Acme",
                    category="engineering", location_constraint="Worldwide", region="worldwide",
                    salary_text="$100k", tags=[], url="https://example.com/job/1",
                    published_at="2026-07-10T00:00:00+00:00")
    defaults.update(kw)
    return Job(source_id=source_id, **defaults)


REPORT_KW = dict(week_label="2026-W28", generated_at="2026-07-11 04:00 UTC", total_in_db=570)


# ---- report_html ----

def test_report_html_bilingual_and_links():
    html = render_report_html([make_job()], **REPORT_KW)
    assert "远程岗位周报 · 2026-W28" in html
    assert '<a href="https://example.com/job/1"' in html, "保留原链接"
    assert "软件开发 | Software Development(1)" in html
    assert 'href="../index.html"' in html, "周报页可跳回浏览页"
    assert "prefers-color-scheme: dark" in html


def test_report_html_titles_link_to_detail_pages():
    from remote_jobs.jobpage import job_page_filename
    html = render_report_html([make_job()], **REPORT_KW)
    expected = f"../jobs/{job_page_filename('remotive', '1')}"
    assert f'href="{expected}"' in html, "岗位标题链到站内详情页"
    assert "↗ 原链接 | Source" in html


def test_report_html_chips_and_pagination():
    jobs = [make_job(str(i), title=f"Engineer {i}") for i in range(3)]
    jobs.append(make_job("d1", title="Designer", category="design"))
    html = render_report_html(jobs, **REPORT_KW,
                              watchlist_matches={"AI 岗": jobs[:2], "设计岗": [jobs[3]]})
    # 重点关注:顶部 chips,默认第一个激活,其余版块条目隐藏
    assert '<button class="chip active" data-filter="w0">AI 岗(2)</button>' in html
    assert 'data-filter="w1">设计岗(1)</button>' in html
    assert 'class="job hidden" data-pane="w1"' in html
    # 岗位列表:职能 chips 含「全部」+ 数量
    assert '>全部 | All(4)</button>' in html
    assert 'data-filter="engineering">软件开发 | Software Development(3)</button>' in html
    assert 'data-pane="design"' in html
    # 分页脚手架
    assert "const PAGE_SIZE = 50" in html
    assert 'id="listing-pager"' in html and 'id="watchlist-pager"' in html
    assert "initFilteredList" in html


def test_report_html_escapes_survive_interactive_rewrite():
    evil = make_job(title='</script><script>alert(1)</script>', company='A"B')
    html = render_report_html([evil], **REPORT_KW)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;/script&gt;" in html


def test_report_html_escapes_job_text():
    evil = make_job(title='<script>alert(1)</script>', company='A&B "quotes"')
    html = render_report_html([evil], **REPORT_KW)
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html
    assert "A&amp;B" in html


def test_report_html_sections():
    jobs = [make_job("1"), make_job("2", title="Designer", category="design")]
    html = render_report_html(
        jobs, **REPORT_KW,
        source_status={"remotive": ("ok", 30), "wwr": ("HTTP 500", 0)},
        watchlist_matches={"AI 岗": [jobs[0]]},
        prev_week_new=379,
    )
    assert "🎯 重点关注 | Watchlist Highlights" in html
    assert "AI 岗(1)" in html
    assert "✅ 正常 OK" in html and "❌ 失败 Failed: HTTP 500" in html
    assert "上周 | last week: 379" in html


def test_report_html_empty_week():
    html = render_report_html([], **REPORT_KW)
    assert "本周没有新增岗位" in html


def test_report_html_og_meta():
    html = render_report_html([], **REPORT_KW,
                              og={"title": "周报 2026-W28", "description": "本周新增 570 条"})
    assert '<meta property="og:title" content="周报 2026-W28">' in html
    assert '<meta property="og:type" content="article">' in html
    assert "og:title" not in render_report_html([], **REPORT_KW)


# ---- generate_site ----

def test_generate_site_writes_expected_files(tmp_path):
    files = generate_site(tmp_path, browse_html="<html>browse</html>",
                          report_html="<html>report</html>", week_label="2026-W28",
                          feed_xml="<rss/>", base_url="https://x.github.io/board")
    assert (tmp_path / "index.html").read_text() == "<html>browse</html>"
    assert (tmp_path / "reports" / "2026-W28.html").read_text() == "<html>report</html>"
    index = (tmp_path / "reports" / "index.html").read_text()
    assert '<a href="2026-W28.html">2026-W28</a>' in index
    assert (tmp_path / "feed.xml").read_text() == "<rss/>"
    assert len(files) == 8, "index + 周报 + 历史索引 + feed + README + manifest + icon + sitemap"


def test_generate_site_readme_links(tmp_path):
    generate_site(tmp_path, browse_html="b", report_html="r", week_label="2026-W28",
                  feed_xml="<rss/>", base_url="https://x.github.io/board")
    readme = (tmp_path / "README.md").read_text()
    assert "[浏览全部岗位 | Browse all jobs](https://x.github.io/board/index.html)" in readme
    assert "https://x.github.io/board/reports/2026-W28.html" in readme
    assert "https://x.github.io/board/feed.xml" in readme
    assert "Auto-generated" in readme
    assert "请仔细甄别招聘信息真假" in readme, "公开仓 README 带防诈声明"


def test_generate_site_job_pages_written_and_stale_cleared(tmp_path):
    generate_site(tmp_path, browse_html="b", report_html="r", week_label="2026-W28",
                  job_pages={"remotive-abc.html": "<html>1</html>", "hn-def.html": "<html>2</html>"})
    assert (tmp_path / "jobs" / "remotive-abc.html").read_text() == "<html>1</html>"
    # 第二次生成:旧页面必须被清除
    generate_site(tmp_path, browse_html="b", report_html="r", week_label="2026-W28",
                  job_pages={"hn-def.html": "<html>2v2</html>"})
    assert not (tmp_path / "jobs" / "remotive-abc.html").exists(), "过期详情页随全量重建消失"
    assert (tmp_path / "jobs" / "hn-def.html").read_text() == "<html>2v2</html>"
    # job_pages=None 时不触碰 jobs/ 目录
    generate_site(tmp_path, browse_html="b", report_html="r", week_label="2026-W28")
    assert (tmp_path / "jobs" / "hn-def.html").exists()


def test_generate_site_without_feed_or_base_url(tmp_path):
    files = generate_site(tmp_path, browse_html="b", report_html="r", week_label="2026-W28")
    assert not (tmp_path / "feed.xml").exists()
    assert not (tmp_path / "sitemap.xml").exists(), "无 base_url 不生成 sitemap"
    assert "(./index.html)" in (tmp_path / "README.md").read_text(), "无 base_url 用相对链接"
    assert (tmp_path / "manifest.webmanifest").exists() and (tmp_path / "icon.svg").exists()
    assert len(files) == 6, "index + 周报 + 历史索引 + README + manifest + icon"


def test_generate_site_sitemap(tmp_path):
    import xml.etree.ElementTree as ET
    generate_site(tmp_path, browse_html="b", report_html="r", week_label="2026-W28",
                  base_url="https://x.github.io/board", generated_date="2026-07-12",
                  job_pages={"remotive-abc.html": "<html>1</html>"})
    root = ET.fromstring((tmp_path / "sitemap.xml").read_text())
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    locations = [u.findtext(f"{ns}loc") for u in root.findall(f"{ns}url")]
    assert "https://x.github.io/board/" in locations
    assert "https://x.github.io/board/reports/2026-W28.html" in locations
    assert "https://x.github.io/board/jobs/remotive-abc.html" in locations
    assert root.find(f"{ns}url").findtext(f"{ns}lastmod") == "2026-07-12"


def test_generate_site_reports_index_accumulates_history(tmp_path):
    generate_site(tmp_path, browse_html="b", report_html="r1", week_label="2026-W27")
    generate_site(tmp_path, browse_html="b", report_html="r2", week_label="2026-W28")
    index = (tmp_path / "reports" / "index.html").read_text()
    assert index.index("2026-W28") < index.index("2026-W27"), "新周报排前面"


# ---- git_publish ----

def test_git_publish_requires_git_repo(tmp_path):
    assert git_publish(tmp_path, "2026-W28") is False, "非 git 仓库直接失败,不抛异常"


def test_git_publish_sequence(tmp_path):
    (tmp_path / ".git").mkdir()
    calls = []

    def fake_runner(site_dir, *args):
        calls.append(args)
        return " M index.html" if args[0] == "status" else ""

    assert git_publish(tmp_path, "2026-W28", runner=fake_runner) is True
    assert [c[0] for c in calls] == ["add", "status", "commit", "push"]
    assert calls[2] == ("commit", "-m", "publish 2026-W28")


def test_git_publish_no_changes_skips_commit(tmp_path):
    (tmp_path / ".git").mkdir()
    calls = []

    def fake_runner(site_dir, *args):
        calls.append(args)
        return ""  # status 干净

    assert git_publish(tmp_path, "2026-W28", runner=fake_runner) is True
    assert [c[0] for c in calls] == ["add", "status"], "无变更不 commit/push"


def test_git_publish_push_failure_returns_false(tmp_path):
    (tmp_path / ".git").mkdir()

    def fake_runner(site_dir, *args):
        if args[0] == "push":
            raise RuntimeError("remote rejected")
        return "dirty" if args[0] == "status" else ""

    assert git_publish(tmp_path, "2026-W28", runner=fake_runner) is False
