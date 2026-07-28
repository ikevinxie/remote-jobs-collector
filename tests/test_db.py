from remote_jobs import db
from remote_jobs.models import Job


def make_job(source_id="1", **kw):
    defaults = dict(source="remotive", title="Backend Engineer", company="Acme",
                    category="engineering", location_constraint="Worldwide", region="worldwide",
                    salary_text="$100k", tags=["python"], url="https://example.com/1",
                    published_at="2026-07-10T00:00:00+00:00", description="JD 描述")
    defaults.update(kw)
    return Job(source_id=source_id, **defaults)


def test_description_roundtrip_and_webpage_excludes_it(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    db.upsert_jobs(conn, [make_job("1", description="很长的 JD" * 100)], "2026-07-11T00:00:00+00:00")
    meta = db.all_jobs_with_meta(conn)[0]
    assert meta["description"].startswith("很长的 JD")
    from remote_jobs.webpage import render_page
    html = render_page(db.all_jobs_with_meta(conn), generated_at_iso="2026-07-11T00:00:00+00:00")
    assert "很长的 JD" not in html, "浏览网页不内嵌描述(体积)"


def test_upsert_inserts_new_jobs(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    inserted, duplicates = db.upsert_jobs(conn, [make_job("1", title="A"), make_job("2", title="B")],
                                          "2026-07-11T00:00:00+00:00")
    assert (inserted, duplicates) == (2, 0)
    assert db.total_count(conn) == 2


def test_upsert_existing_updates_last_seen_keeps_first_seen(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    day1, day2 = "2026-07-04T00:00:00+00:00", "2026-07-11T00:00:00+00:00"
    db.upsert_jobs(conn, [make_job("1")], day1)
    inserted, _ = db.upsert_jobs(conn, [make_job("1", salary_text="$120k")], day2)
    assert inserted == 0, "已存在的岗位不算新增"
    row = conn.execute("SELECT * FROM jobs").fetchone()
    assert row["first_seen_at"] == day1
    assert row["last_seen_at"] == day2
    assert row["salary_text"] == "$120k", "可变字段应刷新"


def test_jobs_first_seen_since_only_returns_new(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    db.upsert_jobs(conn, [make_job("old")], "2026-06-01T00:00:00+00:00")
    db.upsert_jobs(conn, [make_job("old"), make_job("new", title="Designer")],
                   "2026-07-11T00:00:00+00:00")
    recent = db.jobs_first_seen_since(conn, "2026-07-04T00:00:00+00:00")
    assert [j.source_id for j in recent] == ["new"]


def test_salary_columns_populated_on_upsert(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    db.upsert_jobs(conn, [make_job("1", salary_text="$55k - $100k"),
                          make_job("2", title="Designer", salary_text="Competitive")],
                   "2026-07-11T00:00:00+00:00")
    rows = {r["source_id"]: r for r in conn.execute("SELECT * FROM jobs")}
    assert (rows["1"]["salary_min"], rows["1"]["salary_max"], rows["1"]["salary_currency"]) == (55000, 100000, "USD")
    assert rows["2"]["salary_min"] is None, "解析不了的保持 NULL,保留原文"


def test_migration_from_m1_schema(tmp_path):
    """回归:M1 老库(无 salary 三列)必须无损自动升级。"""
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("""CREATE TABLE jobs (
        source TEXT NOT NULL, source_id TEXT NOT NULL, title TEXT NOT NULL,
        company TEXT NOT NULL, category TEXT NOT NULL,
        location_constraint TEXT NOT NULL DEFAULT '', region TEXT NOT NULL DEFAULT 'other',
        salary_text TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '[]',
        url TEXT NOT NULL, published_at TEXT NOT NULL DEFAULT '',
        fingerprint TEXT NOT NULL, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
        PRIMARY KEY (source, source_id))""")
    old.execute("INSERT INTO jobs VALUES ('remotive','1','T','C','engineering','','other','$90k','[]','http://x','','fp','2026-07-01','2026-07-01')")
    old.commit()
    old.close()

    conn = db.connect(path)
    assert db.total_count(conn) == 1, "迁移不丢数据"
    row = conn.execute("SELECT * FROM jobs").fetchone()
    assert row["salary_min"] is None, "老数据新列为 NULL"
    assert row["first_seen_at"] == "2026-07-01"
    db.upsert_jobs(conn, [make_job("1", salary_text="$90k")], "2026-07-11T00:00:00+00:00")
    assert conn.execute("SELECT salary_min FROM jobs").fetchone()["salary_min"] == 90000, "再次采集后回填"


def test_count_first_seen_between(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    db.upsert_jobs(conn, [make_job("a")], "2026-06-28T00:00:00+00:00")
    db.upsert_jobs(conn, [make_job("b", title="Designer"), make_job("c", title="PM")],
                   "2026-07-05T00:00:00+00:00")
    assert db.count_first_seen_between(conn, "2026-07-01T00:00:00+00:00", "2026-07-08T00:00:00+00:00") == 2
    assert db.count_first_seen_between(conn, "2026-06-24T00:00:00+00:00", "2026-07-01T00:00:00+00:00") == 1


def test_cross_week_repost_blocked_within_30_days(tmp_path):
    """跨周去重(SPEC §24):同岗位换新帖 ID 重发,30 天内拦截。"""
    conn = db.connect(tmp_path / "jobs.db")
    db.upsert_jobs(conn, [make_job("old-id", source="eleduck")], "2026-07-01T00:00:00+00:00")
    inserted, duplicates = db.upsert_jobs(
        conn, [make_job("new-id", source="eleduck")], "2026-07-12T00:00:00+00:00")
    assert (inserted, duplicates) == (0, 1), "同指纹 30 天内重发被拦截"
    assert db.total_count(conn) == 1


def test_cross_week_repost_allowed_after_window(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    db.upsert_jobs(conn, [make_job("old-id")], "2026-05-01T00:00:00+00:00")
    inserted, duplicates = db.upsert_jobs(conn, [make_job("new-id")], "2026-07-12T00:00:00+00:00")
    assert (inserted, duplicates) == (1, 0), "超过 30 天视为新一轮招聘"


def test_cross_source_repost_also_blocked(tmp_path):
    """『包括各种来源的』:A 源已收录的岗位,B 源 30 天内出现同指纹也拦截。"""
    conn = db.connect(tmp_path / "jobs.db")
    db.upsert_jobs(conn, [make_job("1", source="remotive")], "2026-07-10T00:00:00+00:00")
    inserted, duplicates = db.upsert_jobs(conn, [make_job("x9", source="eleduck")],
                                          "2026-07-12T00:00:00+00:00")
    assert (inserted, duplicates) == (0, 1)


def test_same_source_id_update_not_affected_by_dup_check(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    db.upsert_jobs(conn, [make_job("1")], "2026-07-10T00:00:00+00:00")
    inserted, duplicates = db.upsert_jobs(conn, [make_job("1")], "2026-07-12T00:00:00+00:00")
    assert (inserted, duplicates) == (0, 0), "同 ID 刷新是更新,不是重复"


def test_prune_removes_stale_jobs(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    db.upsert_jobs(conn, [make_job("stale")], "2026-01-01T00:00:00+00:00")
    db.upsert_jobs(conn, [make_job("fresh")], "2026-07-11T00:00:00+00:00")
    deleted = db.prune(conn, "2026-06-01T00:00:00+00:00")
    assert deleted == 1
    assert [r["source_id"] for r in conn.execute("SELECT source_id FROM jobs")] == ["fresh"]


def test_roundtrip_preserves_fields(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    original = make_job("1", tags=["python", "远程"])
    db.upsert_jobs(conn, [original], "2026-07-11T00:00:00+00:00")
    loaded = db.jobs_first_seen_since(conn, "2026-07-11T00:00:00+00:00")[0]
    assert loaded == original
