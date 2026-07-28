import pytest

from remote_jobs.models import Job
from remote_jobs.report import generate_report


def make_job(source_id="1", **kw):
    defaults = dict(source="remotive", title="Backend Engineer", company="Acme",
                    category="engineering", location_constraint="Worldwide", region="worldwide",
                    salary_text="$100k", tags=[], url="https://example.com/job/1",
                    published_at="2026-07-10T00:00:00+00:00")
    defaults.update(kw)
    return Job(source_id=source_id, **defaults)


JOBS = [
    make_job("1"),
    make_job("2", title="UI Designer", category="design", region="europe",
             location_constraint="Europe", url="https://example.com/job/2", salary_text=""),
    make_job("3", title="Data Analyst", category="engineering", region="americas",
             location_constraint="USA", url="https://example.com/job/3"),
]


def render(**kw):
    defaults = dict(week_label="2026-W28", generated_at="2026-07-11 04:00 UTC", total_in_db=100)
    defaults.update(kw)
    return generate_report(JOBS, **defaults)


def test_report_is_bilingual():
    text = render()
    assert "全球远程岗位周报 | Global Remote Jobs Weekly — 2026-W28" in text
    assert "本周新增岗位 | New jobs this week: **3**" in text
    assert "数据库累计岗位 | Total jobs in database: **100**" in text


def test_report_preserves_original_links():
    text = render()
    for job in JOBS:
        assert f"[{job.title}]({job.url})" in text, "必须保留岗位原始链接"


def test_default_grouping_is_category_sorted_by_count():
    text = render()
    assert "### 软件开发 | Software Development(2)" in text
    assert "### 设计 | Design(1)" in text
    assert text.index("软件开发") < text.index("### 设计"), "岗位多的类目排前面"


def test_group_by_region():
    text = render(group_by="region")
    assert "### 全球 | Worldwide(1)" in text
    assert "### 欧洲 | Europe / EMEA(1)" in text
    assert "### 美洲 | Americas(1)" in text
    with pytest.raises(ValueError):
        render(group_by="salary")


def test_source_status_table():
    text = render(source_status={"remotive": ("ok", 30), "wwr": ("HTTP 500", 0)})
    assert "| Remotive | ✅ 正常 OK | 30 |" in text
    assert "| We Work Remotely | ❌ 失败 Failed: HTTP 500 | - |" in text


def test_ai_picks_section_before_watchlist():
    picks = [(JOBS[0], 9.5, "薪资透明,全球可投"), (JOBS[1], 8.0, "")]
    text = render(ai_picks=picks, watchlist_matches={"AI 岗": [JOBS[0]]})
    assert "## 🤖 本周最值得投 | AI Top Picks" in text
    assert "⭐9.5" in text
    assert "> 薪资透明,全球可投" in text
    assert text.index("AI Top Picks") < text.index("重点关注"), "AI 版块在重点关注之前"
    assert "AI Top Picks" not in render(), "无 picks 不渲染该版块"


def test_week_over_week_comparison():
    assert "(上周 | last week: 2,环比 | WoW: +50%)" in render(prev_week_new=2)
    assert "(上周 | last week: 6,环比 | WoW: -50%)" in render(prev_week_new=6)
    assert "(上周 | last week: 0)" in render(prev_week_new=0)
    assert "上周" not in render(prev_week_new=None), "无上周数据不显示环比"


def test_watchlist_highlights_section():
    text = render(watchlist_matches={"AI 工程岗": [JOBS[0]], "设计岗": [JOBS[1]]})
    assert "## 🎯 重点关注 | Watchlist Highlights" in text
    assert "### AI 工程岗(1)" in text
    assert "### 设计岗(1)" in text
    assert text.index("重点关注") < text.index("岗位列表"), "重点关注版块在正文之前"
    assert text.count(f"[{JOBS[0].title}]({JOBS[0].url})") == 2, "命中岗位同时保留在正文分组"


def test_no_watchlist_section_when_no_matches():
    assert "重点关注" not in render()
    assert "重点关注" not in render(watchlist_matches=None)


def test_empty_week():
    text = generate_report([], week_label="2026-W28", generated_at="x", total_in_db=100)
    assert "本周没有新增岗位。 | No new jobs this week." in text


def test_remoteok_attribution_in_footer():
    assert "[Remote OK](https://remoteok.com)" in render()


def test_disclaimer_in_markdown_report():
    text = render()
    assert "请仔细甄别招聘信息真假" in text
    assert text.index("请仔细甄别") < text.index("数据来源 | Data sources")
