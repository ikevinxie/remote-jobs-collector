"""各源 parse() 纯函数测试,输入为 tests/fixtures/ 中的真实 API 响应快照。"""
from pathlib import Path

import pytest

from remote_jobs.fetchers import (ALL_FETCHERS, eleduck, himalayas, hn_whoishiring, jobicy,
                                  remoteok, remotive, v2ex, weworkremotely, workingnomads)
from remote_jobs.normalize import CATEGORIES, REGIONS

FIXTURES = Path(__file__).parent / "fixtures"

_FIXTURE_FILES = {
    "remotive": "remotive.json",
    "wwr": "wwr.xml",
    "remoteok": "remoteok.json",
    "jobicy": "jobicy.json",
    "himalayas": "himalayas.json",
    "workingnomads": "workingnomads.json",
    "hn": "hn.json",
    "eleduck": "eleduck.json",
    "v2ex": "v2ex.json",
    "indeed": "indeed.json",
    "linkedin": "linkedin.json",
}


def _load(source: str) -> str:
    return (FIXTURES / _FIXTURE_FILES[source]).read_text(encoding="utf-8")


@pytest.mark.parametrize("fetcher", ALL_FETCHERS, ids=lambda f: f.SOURCE)
def test_parse_produces_valid_jobs(fetcher):
    """通用约束:每个源都解析出岗位,且必填字段合法。"""
    jobs = fetcher.parse(_load(fetcher.SOURCE))
    assert len(jobs) == 4, f"{fetcher.SOURCE} 的 fixture 含 4 条岗位"
    for job in jobs:
        assert job.source == fetcher.SOURCE
        assert job.source_id, "source_id 不能为空"
        assert job.title, "标题不能为空"
        assert job.url.startswith("http"), "必须保留岗位原始链接"
        assert job.category in CATEGORIES, f"类目必须归一化: {job.category!r}"
        assert job.region in REGIONS, f"地区必须归一化: {job.region!r}"
        assert isinstance(job.tags, list)
        assert job.description, "JD 描述必须入库(AI 点评与详情页依赖)"
        from remote_jobs.models import DESCRIPTION_LIMIT
        assert len(job.description) <= DESCRIPTION_LIMIT


def test_remotive_field_mapping():
    job = remotive.parse(_load("remotive"))[0]
    assert job.source_id == "2091048"
    assert job.title == "Product Sales Specialist - Pet Health"
    assert job.company == "Tribe Wellness"
    assert job.category == "sales"
    assert job.location_constraint == "USA, CST (UTC-6)"
    assert job.region == "americas"
    assert job.salary_text == "$55k - $100k"
    assert job.url.startswith("https://remotive.com/remote-jobs/")
    assert job.published_at == "2026-07-09T08:01:56"


def test_remotive_worldwide_region():
    job = remotive.parse(_load("remotive"))[1]
    assert job.location_constraint == "Worldwide"
    assert job.region == "worldwide"


def test_wwr_splits_company_from_title():
    jobs = weworkremotely.parse(_load("wwr"))
    assert jobs[0].company == "Mathmo"
    assert jobs[0].title == "Maths Coach"
    assert jobs[0].region == "worldwide"  # "Anywhere in the World"
    assert jobs[0].category == "other"  # "All Other Remote"
    assert jobs[0].url == "https://weworkremotely.com/remote-jobs/mathmo-maths-coach"
    assert jobs[1].company == "Qase"
    assert jobs[1].title == "Developer Advocate"
    assert jobs[1].category == "marketing"  # "Sales and Marketing"


def test_remoteok_skips_legal_notice_and_maps_fields():
    jobs = remoteok.parse(_load("remoteok"))
    job = jobs[0]
    assert job.source_id == "1134698"
    assert job.title == "Australian English Voice Actor Adelaide"
    assert job.company == "OpsArmy Careers"
    assert job.region == "asia_pacific"  # Adelaide, Australia
    assert "remoteok.com/remote-jobs/" in job.url.lower()


def test_jobicy_field_mapping():
    job = jobicy.parse(_load("jobicy"))[0]
    assert job.source_id == "145880"
    assert job.title == "Senior Software Engineer (Contract)"
    assert job.company == "Mozilla"
    assert job.category == "engineering"  # Software Engineering
    assert job.region == "europe"  # Germany
    assert "Senior" in job.tags
    assert job.published_at == "2026-07-10T20:00:05+00:00"


def test_himalayas_field_mapping():
    job = himalayas.parse(_load("himalayas"))[0]
    assert job.title == "Content & Marcom Specialist"
    assert job.company == "Ceragon Networks"
    assert job.location_constraint == "United States"
    assert job.region == "americas"
    assert job.url.startswith("https://himalayas.app/")
    assert job.published_at.startswith("2026-07-")  # pubDate epoch 转 ISO


def test_hn_field_mapping():
    """fixture 含 4 条可解析远程岗 + 3 条噪音(回复/Onsite/无竖线),噪音必须全部跳过。"""
    jobs = hn_whoishiring.parse(_load("hn"))
    ids = {j.source_id for j in jobs}
    assert ids == {"48860201", "48843116", "48842567", "48837669"}
    assert "48859053" not in ids, "回复(parent 非主帖)被跳过"
    assert "48868436" not in ids, "Onsite 帖被跳过"
    assert "48804695" not in ids, "无竖线格式被跳过"

    by_id = {j.source_id: j for j in jobs}
    qase = by_id["48860201"]
    assert qase.company == "Qase"
    assert qase.title == "Developer Advocate"
    assert qase.url == "https://news.ycombinator.com/item?id=48860201"
    assert "HN 2026-07" in qase.tags

    wave = by_id["48843116"]
    assert wave.company == "Wave"
    assert "$185,500" in wave.salary_text
    assert wave.location_constraint == "Remote (EMEA)"
    assert wave.region == "europe"
    assert wave.category == "engineering"  # "On-Premises SRE" 靠 sre 关键词启发式归类

    trinsic = by_id["48837669"]
    assert trinsic.region == "europe"  # REMOTE (Europe)


def test_hn_html_entities_unescaped():
    import json
    raw = json.dumps({
        "story_id": 1, "story_title": "Ask HN: Who is hiring? (July 2026)",
        "hits": [{"objectID": "9", "parent_id": 1, "created_at": "2026-07-01T00:00:00Z",
                  "comment_text": "O&#x27;Reilly &amp; Co | Staff Engineer | REMOTE<p>body"}],
    })
    job = hn_whoishiring.parse(raw)[0]
    assert job.company == "O'Reilly & Co"
    assert job.title == "Staff Engineer"


def test_hn_month_tag_fallback():
    assert hn_whoishiring._month_tag("Ask HN: Who is hiring? (July 2026)") == "HN 2026-07"
    assert hn_whoishiring._month_tag("Ask HN: Who is hiring?") == "HN"


def test_eleduck_filters_and_field_mapping():
    """fixture:4 条合格(企业直招+全职远程)+ 3 条噪音(缺企业直招 tag/付费置顶/closed)。"""
    jobs = eleduck.parse(_load("eleduck"))
    ids = {j.source_id for j in jobs}
    assert len(jobs) == 4
    assert "N0fVmN" not in ids, "缺企业直招 tag 的帖被过滤"
    assert "QZfpd2" not in ids, "付费置顶帖被过滤"
    assert "CLOSED1" not in ids, "已关闭帖被过滤"
    for job in jobs:
        assert job.region == "asia_pacific"
        assert job.location_constraint == "全职远程(电鸭·中文社区)"
        assert job.salary_text == "", "中文月薪不做数字解析"
        assert job.url.startswith("https://eleduck.com/posts/")
    by_id = {j.source_id: j for j in jobs}
    assert by_id["QZfpq2"].category == "engineering"  # 职业 tag「开发」
    assert by_id["3EfDaN"].category == "ops_hr"  # 职业 tag「运营」


def test_eleduck_paid_type_free_string_is_not_paid():
    """回归:paid_type 正常值是字符串 "free"(真值),曾被当布尔用导致全部误过滤。"""
    import json
    raw = json.dumps({"posts": [{
        "id": "X1", "title": "【好公司】招后端", "paid_type": "free",
        "closed": False, "hide": False, "deleted": False, "pinned": False,
        "published_at": "2026-07-11T00:00:00+08:00", "content": "JD 全文",
        "tags": [{"id": 8, "name": "企业直招", "tag_group": {"code": "hire_type"}},
                 {"id": 19, "name": "全职远程", "tag_group": {"code": "job_type"}},
                 {"id": 10, "name": "开发", "tag_group": {"code": "skill_type"}}],
    }]})
    jobs = eleduck.parse(raw)
    assert len(jobs) == 1
    assert jobs[0].company == "好公司", "【】内公司名提取"


def test_eleduck_company_heuristics():
    from remote_jobs.fetchers.eleduck import _company_from_title
    assert _company_from_title("【云雀科技招聘】远程前端") == "云雀科技"
    assert _company_from_title("Acme中国｜资深后端工程师") == "Acme中国"
    assert _company_from_title("2. 居家线上｜C++/Godot图形渲染工程师") == "电鸭直招帖", "场景词首段被否决"
    assert _company_from_title("海外远程 荷兰公司 ODM Software Manager") == "电鸭直招帖"
    assert _company_from_title("美业跨境贸易") == "电鸭直招帖", "无分隔符无括号走兜底"
    # 回归:2026-07-12 首跑线上样本,营销性括号不是公司名
    assert _company_from_title("【付费置顶】硅谷远程 🔍 Cracked的AI agent后端工程师") == "电鸭直招帖"
    assert _company_from_title("【高薪寻独立全栈大牛】海外流量 SaaS 平台招募全栈") == "电鸭直招帖"
    assert _company_from_title("【团队直招】13k-16k招远程平台运营") == "电鸭直招帖"
    assert _company_from_title("继续｜招资深前端") == "电鸭直招帖"
    assert _company_from_title("Remote | Senior Engineer") == "电鸭直招帖"


def test_v2ex_filters_and_field_mapping():
    """fixture:4 条合格(remote 节点岗位帖)+ 3 条噪音(求助讨论帖/酷工作无远程关键词/已删除)。"""
    jobs = v2ex.parse(_load("v2ex"))
    assert len(jobs) == 4
    titles = " ".join(j.title for j in jobs)
    assert "应该往哪边走" not in titles, "求助讨论帖被剔除"
    assert "SHEIN" not in titles, "酷工作节点无远程关键词的帖被剔除"
    assert all(j.source_id != "99999999" for j in jobs), "已删除帖被剔除"
    for job in jobs:
        assert job.region == "asia_pacific"
        assert job.location_constraint == "远程(V2EX·中文社区)"
        assert job.salary_text == ""
        assert job.url.startswith("https://www.v2ex.com/t/")
        assert job.published_at.endswith("+08:00"), "epoch 转东八区 ISO"
        assert job.tags and job.tags[0].startswith("V2EX·")


def test_v2ex_seeker_and_hiring_signals():
    import json
    def topic(tid, title, node="remote", deleted=0):
        return {"id": tid, "title": title, "_node": node, "deleted": deleted,
                "created": 1783751332, "url": f"https://www.v2ex.com/t/{tid}",
                "content": "详情", "content_rendered": "<p>详情</p>"}
    raw = json.dumps({"topics": [
        topic(1, "招聘远程后端工程师"),
        topic(2, "请教:远程工程师岗位怎么找"),          # 求助词 → 剔除
        topic(3, "远程办公体验分享"),                    # 无招聘信号 → 剔除
        topic(4, "[Remote] Senior Engineer wanted", "jobs"),   # 酷工作 + remote 整词 → 保留
        topic(5, "Senior Engineer wanted", "jobs"),      # 酷工作无远程 → 剔除
    ]})
    ids = [j.source_id for j in v2ex.parse(raw)]
    assert ids == ["1", "4"]


def test_v2ex_brackets_are_not_company():
    """V2EX 方括号惯例是城市/标记:[上海]/[内推] 不能当公司名。"""
    from remote_jobs.fetchers.cn_title import company_from_title
    from remote_jobs.fetchers.v2ex import _V2EX_VETO
    kw = dict(fallback="V2EX 招聘帖", extra_veto=_V2EX_VETO)
    assert company_from_title("[上海] SHEIN 内推:算法/前端", **kw) == "V2EX 招聘帖"
    assert company_from_title("[内推] [可 relocate 悉尼] [远程] Senior AI Researcher", **kw) == "V2EX 招聘帖"
    assert company_from_title("【云雀科技】招远程前端", **kw) == "云雀科技"


def test_workingnomads_field_mapping():
    jobs = workingnomads.parse(_load("workingnomads"))
    job = jobs[0]
    assert job.title == "AI Content Analyst (No Experience Required)"
    assert job.company == "Peroptyx"
    assert job.category == "ops_hr"  # Administration
    assert job.region == "asia_pacific"  # Australia
    assert job.source_id == job.url  # 该源以 URL 为源内唯一键
    assert jobs[1].category == "engineering"  # Development
