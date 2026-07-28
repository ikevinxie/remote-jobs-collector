from remote_jobs.models import Job
from remote_jobs.watchlist import Rule, load_watchlist, match, select_matches


def make_job(**kw):
    defaults = dict(source="remotive", source_id="1", title="Senior Backend Engineer",
                    company="Acme", category="engineering", location_constraint="Worldwide",
                    region="worldwide", salary_text="", tags=["python", "aws"],
                    url="https://example.com/1")
    defaults.update(kw)
    return Job(**defaults)


def test_keyword_matches_title_case_insensitive():
    rule = Rule(name="后端", keywords=["backend"])
    assert match(make_job(title="Senior BACKEND Engineer"), rule)
    assert not match(make_job(title="Frontend Engineer", tags=[]), rule)


def test_keyword_matches_tags():
    rule = Rule(name="Python", keywords=["python"])
    assert match(make_job(title="Software Engineer", tags=["Python", "django"]), rule)


def test_short_keyword_requires_word_boundary():
    """回归:2026-07-11 真实运行中 'llm' 误命中 'Unsecured Installments'(insta-llm-ents)。"""
    rule = Rule(name="AI", keywords=["llm", "ai"])
    assert not match(make_job(title="Software Engineer, Unsecured Installments", tags=["Senior"]), rule)
    assert not match(make_job(title="Email Marketing Manager", tags=[]), rule)
    assert match(make_job(title="LLM Infrastructure Engineer", tags=[]), rule)
    assert match(make_job(title="AI/ML Engineer", tags=[]), rule), "标点相邻的整词也要命中"
    assert match(make_job(title="Backend Engineer", tags=["AI"]), rule)


def test_exclude_keywords_win():
    rule = Rule(name="后端", keywords=["backend"], exclude_keywords=["intern"])
    assert not match(make_job(title="Backend Engineer Intern"), rule)


def test_dimensions_are_anded():
    rule = Rule(name="全球后端", keywords=["backend"], categories=["engineering"], regions=["worldwide"])
    assert match(make_job(), rule)
    assert not match(make_job(region="europe"), rule)
    assert not match(make_job(category="data"), rule)


def test_company_substring_match():
    rule = Rule(name="关注公司", companies=["mozilla"])
    assert match(make_job(company="Mozilla Foundation"), rule)
    assert not match(make_job(company="Acme"), rule)


def test_empty_rule_matches_everything():
    assert match(make_job(), Rule(name="全部"))


def test_select_matches_groups_by_rule_and_drops_empty():
    jobs = [make_job(source_id="1"), make_job(source_id="2", title="UI Designer", category="design", tags=[])]
    rules = [Rule(name="工程", categories=["engineering"]),
             Rule(name="设计", categories=["design"]),
             Rule(name="销售", categories=["sales"])]
    result = select_matches(jobs, rules)
    assert [j.source_id for j in result["工程"]] == ["1"]
    assert [j.source_id for j in result["设计"]] == ["2"]
    assert "销售" not in result, "无命中的规则不出现"


def test_load_watchlist_missing_file_returns_empty(tmp_path):
    assert load_watchlist(tmp_path / "nope.toml") == []


def test_load_watchlist_comment_only_file_is_empty(tmp_path):
    """全注释的配置(初始模板形态)必须解析为空规则集。"""
    path = tmp_path / "w.toml"
    path.write_text("# 只有注释\n", encoding="utf-8")
    assert load_watchlist(path) == []


def test_kevin_profile_watchlist_is_valid():
    """kevin 的真实规则(2026-07-11 确认,M4.3 起位于 profiles/kevin/)必须可解析且字段合法。"""
    from remote_jobs.__main__ import ROOT
    from remote_jobs.normalize import CATEGORIES, REGIONS
    rules = load_watchlist(ROOT / "profiles" / "kevin" / "watchlist.toml")
    assert len(rules) == 7, "kevin 配置了 7 条规则"
    for rule in rules:
        assert rule.name
        assert all(c in CATEGORIES for c in rule.categories)
        assert all(r in REGIONS for r in rule.regions)


def test_load_watchlist_parses_rules_and_skips_nameless(tmp_path):
    path = tmp_path / "w.toml"
    path.write_text(
        """
[[rules]]
name = "AI 工程岗"
keywords = ["LLM", "Agent"]
exclude_keywords = ["Intern"]
categories = ["engineering"]
regions = ["worldwide"]
companies = ["Anthropic"]

[[rules]]
keywords = ["无名规则"]
""",
        encoding="utf-8",
    )
    rules = load_watchlist(path)
    assert len(rules) == 1, "缺 name 的规则被跳过"
    rule = rules[0]
    assert rule.name == "AI 工程岗"
    assert rule.keywords == ["llm", "agent"], "关键词统一转小写"
    assert rule.exclude_keywords == ["intern"]
    assert rule.companies == ["anthropic"]
