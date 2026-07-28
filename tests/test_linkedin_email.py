import json
from pathlib import Path

from remote_jobs.fetchers import linkedin_email

FIXTURE = Path(__file__).parent / "fixtures" / "linkedin_alert_sample.html"


def _jobs():
    return linkedin_email.parse_email_html(FIXTURE.read_text(encoding="utf-8"),
                                           published_at="2026-07-15T03:01:27+00:00")


def test_keeps_only_remote_and_hybrid():
    """卡片:Remote / Hybrid / 无工作方式 / On-site / Remote(Worldwide)。
    只保留 Remote 与 Hybrid,纯 On-site 与无工作方式标记的丢弃。"""
    jobs = _jobs()
    ids = {j.source_id for j in jobs}
    assert ids == {"1000000001", "1000000002", "1000000005"}
    assert "1000000003" not in ids, "无工作方式标记(Signify · Shanghai)被丢弃"
    assert "1000000004" not in ids, "On-site 被丢弃"


def test_field_mapping():
    by_id = {j.source_id: j for j in _jobs()}
    lead = by_id["1000000001"]
    assert lead.source == "linkedin"
    assert lead.title == "Supplier Engagement Leader"
    assert lead.company == "GE Vernova"
    assert lead.location_constraint == "Shanghai (Remote)"
    assert lead.region == "asia_pacific"
    assert lead.url == "https://www.linkedin.com/jobs/view/1000000001/"  # 规范链接,去 tracking
    assert lead.tags == ["LinkedIn 邮件提醒", "Remote"]
    assert lead.published_at == "2026-07-15T03:01:27+00:00"
    assert lead.salary_text == ""

    hybrid = by_id["1000000002"]
    assert hybrid.tags == ["LinkedIn 邮件提醒", "Hybrid"]
    assert hybrid.region == "asia_pacific"  # Shenzhen


def test_worldwide_remote_kept_and_region():
    """"Remote (Worldwide)" 也应保留,且地区归一化为全球。"""
    job = next(j for j in _jobs() if j.source_id == "1000000005")
    assert job.region == "worldwide"
    assert job.tags[1] == "Remote"


def test_parse_dedupes_across_messages():
    html = ('<a href="https://www.linkedin.com/comm/jobs/view/999/?t=x">同一岗位</a>'
            '<div>Acme · Shanghai (Remote)</div>')
    raw = json.dumps({"messages": [
        {"msg_id": "1", "date": "Tue, 15 Jul 2026 08:00:00 +0800", "html": html},
        {"msg_id": "2", "date": "Wed, 16 Jul 2026 08:00:00 +0800", "html": html},
    ]})
    jobs = linkedin_email.parse(raw)
    assert len(jobs) == 1
    assert jobs[0].published_at.startswith("2026-07-15")


def test_fetch_without_config_returns_empty(tmp_path):
    raw = linkedin_email.fetch(config_path=tmp_path / "nope.toml")
    assert json.loads(raw) == {"messages": []}
    assert linkedin_email.parse(raw) == []
