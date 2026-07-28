from remote_jobs.jobpage import job_page_filename, render_job_page


def make_meta(**kw):
    defaults = dict(source="remotive", source_id="1", title="Backend Engineer", company="Acme",
                    category="engineering", location_constraint="Worldwide", region="worldwide",
                    salary_text="$100k", tags=[], url="https://example.com/job/1",
                    published_at="2026-07-10T00:00:00+00:00",
                    first_seen_at="2026-07-11T00:00:00+00:00", last_seen_at="2026-07-11T00:00:00+00:00",
                    description="<p>We build <strong>things</strong>.</p>",
                    tz_min=None, tz_max=None, tz_source="")
    defaults.update(kw)
    return defaults


NOW = "2026-07-11T04:00:00+00:00"


def test_filename_is_stable_and_safe_for_url_ids():
    a = job_page_filename("wwr", "https://weworkremotely.com/remote-jobs/foo")
    assert a == job_page_filename("wwr", "https://weworkremotely.com/remote-jobs/foo")
    assert a.startswith("wwr-") and a.endswith(".html")
    assert "/" not in a and ":" not in a
    assert a != job_page_filename("wwr", "https://weworkremotely.com/remote-jobs/bar")


def test_page_structure():
    html = render_job_page(make_meta(), generated_at_iso=NOW)
    assert "<title>Acme | Backend Engineer</title>" in html
    assert '<meta property="og:title" content="Acme | Backend Engineer">' in html
    assert "💰$100k" in html or "💰 $100k" in html
    assert 'href="https://example.com/job/1"' in html
    assert "去原站申请 | Apply on Remotive ↗" in html
    assert 'href="../index.html"' in html
    assert "<p>We build <strong>things</strong>.</p>" in html


def test_description_is_sanitized():
    html = render_job_page(
        make_meta(description='<p>ok</p><script>alert(1)</script><a href="javascript:x">bad</a>'),
        generated_at_iso=NOW)
    assert "alert(1)" not in html
    assert "javascript:" not in html
    assert "<p>ok</p>" in html


def test_stale_banner():
    stale = render_job_page(make_meta(last_seen_at="2026-07-01T00:00:00+00:00"), generated_at_iso=NOW)
    assert "可能已关闭" in stale and "10 天" in stale
    fresh = render_job_page(make_meta(), generated_at_iso=NOW)
    assert "可能已关闭" not in fresh


def test_ai_banner():
    html = render_job_page(make_meta(), generated_at_iso=NOW, ai=(9.5, "薪资透明,全球可投"))
    assert "🤖 AI 精选 ⭐9.5" in html and "薪资透明,全球可投" in html
    assert "AI 精选" not in render_job_page(make_meta(), generated_at_iso=NOW)


def test_missing_description_placeholder():
    html = render_job_page(make_meta(description=""), generated_at_iso=NOW)
    assert "该来源未提供岗位描述" in html


def test_timezone_line_with_inference_label():
    html = render_job_page(make_meta(tz_min=-1, tz_max=3, tz_source="inferred"), generated_at_iso=NOW)
    assert "🕐 时区 UTC-1 ~ UTC+3(推断)" in html
    html = render_job_page(make_meta(tz_min=8, tz_max=8, tz_source="source"), generated_at_iso=NOW)
    assert "🕐 时区 UTC+8" in html and "推断" not in html
    assert "🕐" not in render_job_page(make_meta(), generated_at_iso=NOW), "无时区信息不显示"


def test_tldr_and_prep_sections():
    extra = {"tldr": "负责 <后端> 开发。", "prep_brief": "Acme 做 & 什么",
             "prep_questions": ["问题一?", "问题二?"]}
    html = render_job_page(make_meta(), generated_at_iso=NOW, extra=extra)
    assert "中文速览" in html and "负责 &lt;后端&gt; 开发。" in html, "速览内容必须转义"
    assert "面试准备" in html and "Acme 做 &amp; 什么" in html
    assert "<ol><li>问题一?</li><li>问题二?</li></ol>" in html
    plain = render_job_page(make_meta(), generated_at_iso=NOW)
    assert "中文速览" not in plain and "面试准备" not in plain


def test_disclaimer_before_apply_button():
    html = render_job_page(make_meta(), generated_at_iso=NOW)
    assert "请仔细甄别招聘信息真假" in html
    assert html.index("请仔细甄别招聘信息真假") < html.index("去原站申请"), "免责提示在申请按钮之前"


def test_title_company_escaped():
    html = render_job_page(make_meta(title='<img src=x onerror=1>', company="A&B"), generated_at_iso=NOW)
    assert "onerror" not in html.replace("&lt;img src=x onerror=1&gt;", "")
    assert "A&amp;B" in html
