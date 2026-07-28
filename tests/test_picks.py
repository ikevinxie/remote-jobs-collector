import json

from remote_jobs import db
from remote_jobs.models import Job
from remote_jobs.picks import load_picks, picks_path


def make_job(source_id="1", **kw):
    defaults = dict(source="remotive", title="Backend Engineer", company="Acme",
                    category="engineering", location_constraint="Worldwide", region="worldwide",
                    salary_text="", tags=[], url="https://example.com/1",
                    published_at="2026-07-10T00:00:00+00:00", description="JD 全文")
    defaults.update(kw)
    return Job(source_id=source_id, **defaults)


def _setup(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    db.upsert_jobs(conn, [make_job("1"), make_job("2", title="Designer")], "2026-07-11T00:00:00+00:00")
    return conn


def test_picks_path():
    assert str(picks_path("/r", "2026-W28")).endswith("/r/2026-W28-picks.json")


def test_load_picks_missing_file(tmp_path):
    conn = _setup(tmp_path)
    assert load_picks(tmp_path / "nope.json", conn) == []


def test_load_picks_valid_sorted_by_score(tmp_path):
    conn = _setup(tmp_path)
    path = tmp_path / "picks.json"
    path.write_text(json.dumps([
        {"source": "remotive", "source_id": "1", "score": 7, "comment": "稳"},
        {"source": "remotive", "source_id": "2", "score": 9.5, "comment": "强烈推荐"},
    ]), encoding="utf-8")
    picks = load_picks(path, conn)
    assert [(j.source_id, s, c) for j, s, c in picks] == [("2", 9.5, "强烈推荐"), ("1", 7.0, "稳")]
    assert picks[0][0].title == "Designer", "岗位字段从库中还原"


def test_load_picks_skips_invalid_entries(tmp_path):
    conn = _setup(tmp_path)
    path = tmp_path / "picks.json"
    path.write_text(json.dumps([
        {"source": "remotive", "source_id": "1", "score": 8, "comment": "ok"},
        {"source": "remotive", "source_id": "999", "score": 8, "comment": "岗位不存在"},
        {"source": "remotive", "source_id": "2", "score": 11, "comment": "分数越界"},
        {"source": "remotive", "source_id": "2", "score": "high", "comment": "分数非数字"},
        "not-a-dict",
    ]), encoding="utf-8")
    picks = load_picks(path, conn)
    assert [j.source_id for j, _, _ in picks] == ["1"]


def test_load_picks_corrupt_file(tmp_path):
    conn = _setup(tmp_path)
    path = tmp_path / "picks.json"
    path.write_text("{ 不是合法 JSON", encoding="utf-8")
    assert load_picks(path, conn) == []
