import json

from remote_jobs import db
from remote_jobs.xhs_ingest import ingest_xhs, xhs_source_id

NOW = "2026-07-15T00:00:00+00:00"


def _write(tmp_path, week, entries):
    (tmp_path / f"{week}-xhs.json").write_text(
        json.dumps(entries, ensure_ascii=False), encoding="utf-8")


def test_ingest_normalizes_and_inserts(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    _write(tmp_path, "2026-W29", [
        {"title": "远程 Python 工程师", "company": "海外某公司",
         "url": "https://xhslink.com/m/abc", "blogger": "Tina远程慢游记",
         "salary_text": "15-25k", "published_at": "2026-07-14"},
    ])
    stats = ingest_xhs(conn, tmp_path, "2026-W29", NOW)
    assert stats["inserted"] == 1 and stats["skipped"] == 0

    rows = db.all_jobs_with_meta(conn)
    assert len(rows) == 1
    job = rows[0]
    assert job["source"] == "xhs"
    assert job["source_id"] == xhs_source_id("远程 Python 工程师", "海外某公司")
    assert job["category"] == "engineering"      # 标题自动映射
    assert job["region"] == "worldwide"          # 未给地区 → 默认全球
    assert job["location_constraint"] == "远程(小红书)"
    assert "小红书" in job["tags"] and "Tina远程慢游记" in job["tags"]


def test_missing_title_skipped_company_fallback(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    _write(tmp_path, "2026-W29", [
        {"title": "", "company": "X"},                 # 无标题 → 跳过
        {"title": "远程设计师"},                        # 无公司 → 兜底
    ])
    stats = ingest_xhs(conn, tmp_path, "2026-W29", NOW)
    assert stats["inserted"] == 1 and stats["skipped"] == 1
    assert db.all_jobs_with_meta(conn)[0]["company"] == "小红书分享"


def test_reingest_same_job_is_stable(tmp_path):
    """同一岗位两次 ingest 不产生重复(source_id 稳定)。"""
    conn = db.connect(tmp_path / "jobs.db")
    entry = [{"title": "远程运营", "company": "Acme"}]
    _write(tmp_path, "2026-W29", entry)
    first = ingest_xhs(conn, tmp_path, "2026-W29", NOW)
    second = ingest_xhs(conn, tmp_path, "2026-W29", NOW)
    assert first["inserted"] == 1
    assert second["inserted"] == 0 and second["updated"] == 1
    assert len(db.all_jobs_with_meta(conn)) == 1


def test_dedupe_within_file(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    _write(tmp_path, "2026-W29", [
        {"title": "远程后端", "company": "Acme"},
        {"title": "远程后端", "company": "Acme"},   # 同 title+company → 同一条
    ])
    stats = ingest_xhs(conn, tmp_path, "2026-W29", NOW)
    assert stats["inserted"] == 1
    assert len(db.all_jobs_with_meta(conn)) == 1


def test_explicit_category_and_region_respected(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    _write(tmp_path, "2026-W29", [
        {"title": "神秘岗位", "company": "C", "category": "design",
         "location_constraint": "美国远程", "region": "americas"},
    ])
    ingest_xhs(conn, tmp_path, "2026-W29", NOW)
    job = db.all_jobs_with_meta(conn)[0]
    assert job["category"] == "design"
    assert job["region"] == "americas"


def test_missing_file_is_noop(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    assert ingest_xhs(conn, tmp_path, "2026-W30", NOW)["inserted"] == 0
