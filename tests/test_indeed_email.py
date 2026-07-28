import json
from pathlib import Path

from remote_jobs.fetchers import _email_source, indeed_email

FIXTURE = Path(__file__).parent / "fixtures" / "indeed_alert_sample.html"


def _jobs():
    return indeed_email.parse_email_html(FIXTURE.read_text(encoding="utf-8"),
                                         published_at="2026-07-15T08:00:00+00:00")


def test_parse_card_structure():
    """标题在 <h2>,其后依次是公司/地区/JD;jk 作 source_id。"""
    by_id = {j.source_id: j for j in _jobs()}
    backend = by_id["abc123def456"]
    assert backend.source == "indeed"
    assert backend.title == "高级后端工程师"
    assert backend.company == "Corning"
    assert backend.location_constraint == "上海市 浦东新区"
    assert backend.region == "asia_pacific"
    assert backend.category == "engineering"
    assert backend.tags == ["Indeed 邮件提醒"]
    assert "jk=abc123def456" in backend.url
    assert backend.published_at == "2026-07-15T08:00:00+00:00"
    assert "remote" in backend.description.lower()


def test_rating_between_company_and_location_is_skipped():
    """公司后的星级评分(如 3.9)不能被当成地区。"""
    job = next(j for j in _jobs() if j.source_id == "rate99rate88")
    assert job.company == "ABB Electrical Machines Ltd."
    assert job.location_constraint == "大连市"      # 跳过了 "3.9"
    assert job.region == "asia_pacific"             # 中文地名默认亚太


def test_sponsored_card_without_jk_uses_hash_id():
    """赞助岗(/pagead 无 jk)用 title|company 哈希作稳定 source_id。"""
    jobs = _jobs()
    ad = next(j for j in jobs if j.title == "远程数据分析师")
    assert ad.source_id.startswith("ad-")
    assert ad.company == "IPMC"
    assert ad.location_constraint == "中国"
    # 同 title+company 再解析一次,source_id 不变
    again = next(j for j in _jobs() if j.title == "远程数据分析师")
    assert again.source_id == ad.source_id


def test_salary_not_numeric_parsed():
    """中国岗位人民币薪资不做数字解析(同电鸭/V2EX),salary_text 留空。"""
    ad = next(j for j in _jobs() if j.title == "远程数据分析师")
    assert ad.salary_text == ""


def test_footer_boilerplate_not_leaked_into_description():
    """页脚样板(免责声明/公司地址/退订)不得混进最后一张卡片的描述。"""
    last = next(j for j in _jobs() if j.source_id == "last000last")
    assert last.company == "bp"
    assert last.location_constraint == "太仓市"
    assert indeed_email._FOOTER.search(last.description) is None
    assert "<" not in last.description
    assert "relocation" in last.description.lower()


def test_all_cards_parsed():
    assert len(_jobs()) == 4


def test_parse_wraps_fetch_json_and_dedupes_across_messages():
    html = '<h2><a href="https://indeed.com/viewjob?jk=dup">同一岗位</a></h2><div>公司X</div>'
    raw = json.dumps({"messages": [
        {"msg_id": "1", "date": "Tue, 15 Jul 2026 08:00:00 +0800", "html": html},
        {"msg_id": "2", "date": "Wed, 16 Jul 2026 08:00:00 +0800", "html": html},
    ]})
    jobs = indeed_email.parse(raw)
    assert len(jobs) == 1                              # 跨邮件同 jk 去重
    assert jobs[0].published_at.startswith("2026-07-15")


def test_fetch_without_config_returns_empty(tmp_path):
    missing = tmp_path / "nope.toml"
    raw = indeed_email.fetch(config_path=missing)
    assert json.loads(raw) == {"messages": []}
    assert indeed_email.parse(raw) == []


def test_fetch_skips_when_authcode_blank(tmp_path):
    cfg = tmp_path / "mailbox.toml"
    cfg.write_text('user = "x@qq.com"\nauthcode = ""\n', encoding="utf-8")
    assert json.loads(indeed_email.fetch(config_path=cfg)) == {"messages": []}


def test_mailbox_config_reads_values(tmp_path):
    cfg = tmp_path / "mailbox.toml"
    cfg.write_text('user = "me@qq.com"\nauthcode = "secret"\nsince_days = 14\n',
                   encoding="utf-8")
    loaded = _email_source.load_mailbox_config(cfg)
    assert loaded["user"] == "me@qq.com"
    assert loaded["authcode"] == "secret"
    assert loaded["since_days"] == 14
    assert loaded["host"] == "imap.qq.com"            # 默认值填充
