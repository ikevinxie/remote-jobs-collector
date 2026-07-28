import json

from remote_jobs import db
from remote_jobs.ai_import import import_ai_files
from remote_jobs.models import Job


def make_job(source_id="1", **kw):
    defaults = dict(source="remotive", title="Backend Engineer", company="Acme",
                    category="engineering", location_constraint="Worldwide", region="worldwide",
                    salary_text="", tags=[], url="https://example.com/1",
                    published_at="2026-07-10T00:00:00+00:00", description="JD")
    defaults.update(kw)
    return Job(source_id=source_id, **defaults)


NOW = "2026-07-12T00:00:00+00:00"


def _setup(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    db.upsert_jobs(conn, [make_job("1"), make_job("2")], NOW)
    return conn


def test_import_summaries_and_prep(tmp_path):
    conn = _setup(tmp_path)
    (tmp_path / "2026-W28-summaries.json").write_text(json.dumps([
        {"source": "remotive", "source_id": "1", "tldr": "负责后端开发,要求 5 年经验。"},
        {"source": "remotive", "source_id": "999", "tldr": "岗位不在库"},
        {"source": "remotive", "source_id": "2", "tldr": "  "},
    ], ensure_ascii=False), encoding="utf-8")
    (tmp_path / "2026-W28-prep.json").write_text(json.dumps([
        {"source": "remotive", "source_id": "1", "brief": "Acme 是一家…",
         "questions": ["请介绍分布式系统经验", "", "如何做容量规划?"]},
    ], ensure_ascii=False), encoding="utf-8")

    stats = import_ai_files(conn, tmp_path, "2026-W28", NOW)
    assert stats == {"tldr": 1, "prep": 1, "skipped": 2}
    ai = db.job_ai_map(conn)[("remotive", "1")]
    assert ai["tldr"] == "负责后端开发,要求 5 年经验。"
    assert ai["prep_brief"] == "Acme 是一家…"
    assert ai["prep_questions"] == ["请介绍分布式系统经验", "如何做容量规划?"], "空问题被过滤"


def test_import_missing_files_is_noop(tmp_path):
    conn = _setup(tmp_path)
    assert import_ai_files(conn, tmp_path, "2026-W28", NOW) == {"tldr": 0, "prep": 0, "skipped": 0}


def test_reimport_preserves_existing_fields(tmp_path):
    """速览和准备包分周导入时,后一次不能清掉前一次的字段。"""
    conn = _setup(tmp_path)
    db.upsert_job_ai(conn, [{"source": "remotive", "source_id": "1", "tldr": "旧速览"}], NOW)
    db.upsert_job_ai(conn, [{"source": "remotive", "source_id": "1",
                             "prep_brief": "新准备", "prep_questions": ["Q1"]}], NOW)
    ai = db.job_ai_map(conn)[("remotive", "1")]
    assert ai["tldr"] == "旧速览"
    assert ai["prep_brief"] == "新准备"


def test_corrupt_file_skipped(tmp_path):
    conn = _setup(tmp_path)
    (tmp_path / "2026-W28-summaries.json").write_text("{坏的", encoding="utf-8")
    assert import_ai_files(conn, tmp_path, "2026-W28", NOW)["tldr"] == 0
