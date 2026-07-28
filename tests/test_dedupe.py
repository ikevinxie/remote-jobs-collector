from remote_jobs.dedupe import dedupe
from remote_jobs.models import Job


def make_job(source="remotive", source_id="1", title="Backend Engineer", company="Acme", **kw):
    defaults = dict(category="engineering", location_constraint="Worldwide",
                    region="worldwide", salary_text="", url="https://example.com/1")
    defaults.update(kw)
    return Job(source=source, source_id=source_id, title=title, company=company, **defaults)


def test_same_source_same_id_deduped():
    jobs = dedupe([make_job(), make_job(title="Backend Engineer II")])
    assert len(jobs) == 1


def test_cross_source_same_title_company_deduped_keeps_first():
    first = make_job(source="remotive", source_id="1")
    second = make_job(source="remoteok", source_id="999", url="https://other.com")
    jobs = dedupe([first, second])
    assert jobs == [first], "优先保留排前面的源"


def test_fingerprint_ignores_case_and_punctuation():
    a = make_job(title="Backend Engineer", company="Acme Inc.")
    b = make_job(source="jobicy", source_id="2", title="backend   engineer!", company="ACME, Inc")
    assert a.fingerprint == b.fingerprint
    assert len(dedupe([a, b])) == 1


def test_different_jobs_not_deduped():
    a = make_job(source_id="1", title="Backend Engineer")
    b = make_job(source_id="2", title="Frontend Engineer")
    c = make_job(source_id="3", title="Backend Engineer", company="Globex")
    assert len(dedupe([a, b, c])) == 3
