from remote_jobs.normalize import CATEGORIES, REGIONS, map_category, map_region


def test_exact_category_mapping():
    assert map_category("Software Development") == "engineering"
    assert map_category("DevOps / Sysadmin") == "engineering"
    assert map_category("Full-Stack Programming") == "engineering"
    assert map_category("Sales and Marketing") == "marketing"
    assert map_category("Customer Service") == "support"
    assert map_category("Finance / Legal") == "finance_legal"
    assert map_category("All Other Remote") == "other"
    assert map_category("Administration") == "ops_hr"


def test_chinese_keyword_categories():
    """接入电鸭/V2EX 后(2026-07-12):中文标题也能启发式归类。"""
    assert map_category("招产品经理(PM)") == "product"
    assert map_category("远程岗位-Go / 后端开发岗位") == "engineering"
    assert map_category("招募全栈工程师") == "engineering"
    assert map_category("UI 设计师") == "design"
    assert map_category("13k-16k招远程平台运营") == "ops_hr"
    assert map_category("谷歌SEO优化专员") == "marketing"


def test_keyword_category_fallback():
    assert map_category("Senior Backend Engineer Stuff") == "engineering"
    assert map_category("Growth Marketing") == "marketing"
    assert map_category("Technical Writing") == "writing"


def test_html_escaped_category_from_live_run():
    """回归:2026-07-11 线上 Jobicy 返回 HTML 转义类目,曾被误判为未识别。"""
    assert map_category("Healthcare &amp; Medical") == "other"  # 显式映射,不再记日志
    assert map_category("Marketing &amp; Sales") == "marketing"


def test_himalayas_categories_from_live_run():
    """回归:2026-07-11 线上 Himalayas 出现的未识别类目。"""
    assert map_category("Mortgage-Lending") == "finance_legal"
    assert map_category("Co-Founder") == "other"


def test_categories_from_first_full_run():
    """回归:2026-07-11 首次全量运行出现的线上类目样本。"""
    assert map_category("Artificial Intelligence") == "engineering"
    assert map_category("QA & Testing") == "engineering"
    assert map_category("Admin & Virtual Assistant") == "ops_hr"
    assert map_category("Project Manager") == "ops_hr"
    assert map_category("Communications") == "marketing"
    assert map_category("Analyst") == "data"
    assert map_category("Education & E-Learning") == "other"


def test_himalayas_longtail_categories_from_eleduck_round():
    """回归:2026-07-12 电鸭接入当轮出现的 Himalayas 长尾类目。"""
    assert map_category("Commissioning-Project-Management") == "ops_hr"
    assert map_category("Information-Technology-Management") == "engineering"
    assert map_category("Research-Director") == "other"


def test_himalayas_longtail_categories_from_second_run():
    """回归:2026-07-11 第二轮运行出现的 Himalayas 长尾类目。"""
    assert map_category("PPC-Specialist") == "marketing"
    assert map_category("SCADA-Systems-Integration") == "engineering"
    assert map_category("Clinical-Triage-Specialist") == "other"
    assert map_category("On-Premises SRE") == "engineering"  # HN 标题启发式,靠 sre 关键词


def test_himalayas_longtail_categories_from_2026_w29_run():
    """回归:2026-W29 运行出现的 Himalayas/Jobicy 未识别类目。"""
    assert map_category("AI-And-Automation-Specialist") == "engineering"
    assert map_category("Oracle-Configurator") == "engineering"
    assert map_category("Commercial-Card-Implementation") == "finance_legal"
    assert map_category("Paid-Media") == "marketing"
    assert map_category("Translation &amp; Localization") == "writing"
    assert map_category("Clinical-Research") == "other"
    assert map_category("Medical-Coding") == "other"
    assert map_category("Religious-Studies") == "other"


def test_himalayas_longtail_categories_from_2026_w29_second_round():
    """回归:2026-W29 第二轮运行出现的 Himalayas 教练/咨询类长尾类目。"""
    assert map_category("Growth") == "marketing"
    assert map_category("Practice-Manager") == "ops_hr"
    assert map_category("Mental-Health-Coach") == "other"
    assert map_category("Startup-Coaching") == "other"
    assert map_category("College-Admissions-Coaching") == "other"
    assert map_category("Venture-Capital-Training") == "other"
    assert map_category("Executive-Coach") == "other"
    assert map_category("Corporate-Coaching") == "other"
    assert map_category("Career-Counseling-For-Veterans") == "other"


def test_unknown_recording_can_be_suppressed():
    """回归:RemoteOK 拿标签试探类目时,不匹配的标签不得进入未识别集合。"""
    from remote_jobs.normalize import UNKNOWN_CATEGORIES
    UNKNOWN_CATEGORIES.clear()
    assert map_category("jira-like-tool-xyz", record_unknown=False) == "other"
    assert UNKNOWN_CATEGORIES == set()
    assert map_category("some-brand-new-category") == "other"
    assert UNKNOWN_CATEGORIES == {"some-brand-new-category"}
    UNKNOWN_CATEGORIES.clear()


def test_unknown_category_goes_to_other():
    assert map_category("Astrology Consulting") == "other"
    assert map_category("") == "other"
    assert map_category(None) == "other"


def test_all_mapped_values_are_canonical():
    from remote_jobs.normalize import _CATEGORY_EXACT, _CATEGORY_KEYWORDS
    for value in _CATEGORY_EXACT.values():
        assert value in CATEGORIES
    for _, value in _CATEGORY_KEYWORDS:
        assert value in CATEGORIES


def test_region_mapping():
    assert map_region("Anywhere in the World") == "worldwide"
    assert map_region("Worldwide") == "worldwide"
    assert map_region("USA Only") == "americas"
    assert map_region("United States") == "americas"
    assert map_region("Germany") == "europe"
    assert map_region("EMEA") == "europe"
    assert map_region("Australia") == "asia_pacific"
    assert map_region("South Africa") == "africa_middle_east"


def test_region_remote_us_is_not_worldwide():
    """回归:'remote' 兜底不能盖过国家关键词。"""
    assert map_region("Remote - USA") == "americas"
    assert map_region("Remote") == "worldwide"


def test_region_unknown_goes_to_other():
    assert map_region("Orlando, ") == "other"
    assert map_region("") == "other"
    for key in ("worldwide", "americas", "europe", "asia_pacific", "africa_middle_east", "other"):
        assert key in REGIONS
