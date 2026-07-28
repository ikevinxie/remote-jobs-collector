"""职能类目与地区的归一化映射(见 SPEC.md §5–6)。"""
from __future__ import annotations

import html
import logging

logger = logging.getLogger(__name__)

# 本次进程内遇到的未识别类目原文,run 结束后汇总提醒(按 SPEC §10 沉淀映射与用例)
UNKNOWN_CATEGORIES: set[str] = set()

# key -> (中文名, English name)
CATEGORIES: dict[str, tuple[str, str]] = {
    "engineering": ("软件开发", "Software Development"),
    "design": ("设计", "Design"),
    "product": ("产品", "Product"),
    "data": ("数据", "Data"),
    "marketing": ("市场营销", "Marketing"),
    "sales": ("销售", "Sales"),
    "support": ("客户支持", "Customer Support"),
    "ops_hr": ("运营与人力", "Operations & HR"),
    "finance_legal": ("财务与法务", "Finance & Legal"),
    "writing": ("写作", "Writing"),
    "other": ("其他", "Other"),
}

# key -> (中文名, English name)
REGIONS: dict[str, tuple[str, str]] = {
    "worldwide": ("全球", "Worldwide"),
    "americas": ("美洲", "Americas"),
    "europe": ("欧洲", "Europe / EMEA"),
    "asia_pacific": ("亚太", "Asia-Pacific"),
    "africa_middle_east": ("非洲与中东", "Africa & Middle East"),
    "other": ("其他/未标明", "Other / Unspecified"),
}

# 各源类目原文(小写)→ 归一化 key。精确匹配优先于关键词启发。
_CATEGORY_EXACT: dict[str, str] = {
    # Remotive
    "software development": "engineering",
    "devops / sysadmin": "engineering",
    "qa": "engineering",
    "design": "design",
    "product": "product",
    "data": "data",
    "data analysis": "data",
    "marketing": "marketing",
    "sales": "sales",
    "sales / business": "sales",
    "customer service": "support",
    "customer support": "support",
    "human resources": "ops_hr",
    "project management": "ops_hr",
    "finance / legal": "finance_legal",
    "writing": "writing",
    "all others": "other",
    # We Work Remotely
    "full-stack programming": "engineering",
    "front-end programming": "engineering",
    "back-end programming": "engineering",
    "programming": "engineering",
    "devops and sysadmin": "engineering",
    "sales and marketing": "marketing",
    "management and finance": "finance_legal",
    "all other remote": "other",
    # Jobicy
    "software engineering": "engineering",
    "engineering": "engineering",
    "technical support": "support",
    "customer success": "support",
    "business development": "sales",
    "hr & recruiting": "ops_hr",
    "web & app design": "design",
    "creative & design": "design",
    "data science & analytics": "data",
    "marketing & sales": "marketing",
    "copywriting": "writing",
    "content & editorial": "writing",
    # Working Nomads
    "development": "engineering",
    "system administration": "engineering",
    "administration": "ops_hr",
    "management": "ops_hr",
    "human resource": "ops_hr",
    "finance": "finance_legal",
    "legal": "finance_legal",
    "consulting": "other",
    "education": "other",
    "healthcare": "other",
    # Himalayas (parentCategories)
    "content-marketing": "marketing",
    "mortgage-lending": "finance_legal",
    "co-founder": "other",
    # Jobicy(2026-07-11 线上样本)
    "healthcare & medical": "other",
    # 2026-07-11 首次全量运行沉淀的线上类目样本
    "artificial intelligence": "engineering",
    "information technology": "engineering",
    "qa & testing": "engineering",
    "quality assurance": "engineering",
    "testing": "engineering",
    "blockchain": "engineering",
    "crypto": "engineering",
    "web3": "engineering",
    "admin & virtual assistant": "ops_hr",
    "virtual assistant": "ops_hr",
    "project manager": "ops_hr",
    "coordinator": "ops_hr",
    "supervisor": "ops_hr",
    "exec": "ops_hr",
    "ops": "ops_hr",
    "communications": "marketing",
    "strategy": "other",
    "education & e-learning": "other",
    "teaching": "other",
    "medical": "other",
    "non tech": "other",
    "technical": "other",
    "digital nomad": "other",
    "work from home": "other",
    # Himalayas 长尾类目(2026-07-12 电鸭接入当轮沉淀)
    "commissioning-project-management": "ops_hr",
    "information-technology-management": "engineering",
    "research-director": "other",
    # Himalayas 长尾类目(2026-07-11 第二轮运行沉淀)
    "ppc-specialist": "marketing",
    "e-commerce-merchandising": "marketing",
    "scada-systems-integration": "engineering",
    "sap-consulting": "engineering",
    "process-architecture": "ops_hr",
    "oracle-incentive-compensation": "other",
    "clinical-triage-specialist": "other",
    # Himalayas 长尾类目(2026-W29 运行沉淀)
    "ai-and-automation-specialist": "engineering",
    "oracle-configurator": "engineering",
    "commercial-card-implementation": "finance_legal",
    "paid-media": "marketing",
    "translation & localization": "writing",
    "clinical-research": "other",
    "medical-coding": "other",
    "religious-studies": "other",
    # Himalayas 长尾类目(2026-W29 第二轮运行沉淀,教练/咨询类长尾)
    "growth": "marketing",
    "practice-manager": "ops_hr",
    "mental-health-coach": "other",
    "startup-coaching": "other",
    "college-admissions-coaching": "other",
    "venture-capital-training": "other",
    "executive-coach": "other",
    "corporate-coaching": "other",
    "career-counseling-for-veterans": "other",
}

# 关键词启发式(按优先级排列),命中子串即归类
_CATEGORY_KEYWORDS: list[tuple[str, str]] = [
    ("engineer", "engineering"),
    ("developer", "engineering"),
    ("develop", "engineering"),
    ("program", "engineering"),
    ("devops", "engineering"),
    ("sysadmin", "engineering"),
    ("sre", "engineering"),
    ("swe", "engineering"),
    # 中文关键词(2026-07-12 接入电鸭/V2EX 后补充)
    ("工程师", "engineering"),
    ("开发", "engineering"),
    ("前端", "engineering"),
    ("后端", "engineering"),
    ("全栈", "engineering"),
    ("测试", "engineering"),
    ("运维", "engineering"),
    ("security", "engineering"),
    ("data", "data"),
    ("analy", "data"),  # analyst / analytics / analysis
    ("数据", "data"),
    ("design", "design"),
    ("设计", "design"),
    ("product", "product"),
    ("产品", "product"),
    ("market", "marketing"),
    ("seo", "marketing"),
    ("市场", "marketing"),
    ("增长", "marketing"),
    ("sales", "sales"),
    ("account executive", "sales"),
    ("销售", "sales"),
    ("support", "support"),
    ("customer", "support"),
    ("客服", "support"),
    ("运营", "ops_hr"),
    ("recruit", "ops_hr"),
    ("hr", "ops_hr"),
    ("people", "ops_hr"),
    ("operation", "ops_hr"),
    ("financ", "finance_legal"),
    ("legal", "finance_legal"),
    ("account", "finance_legal"),
    ("writ", "writing"),
    ("content", "writing"),
    ("editor", "writing"),
]


def map_category(raw: str, *, record_unknown: bool = True) -> str:
    """把源类目原文映射为归一化 key;未识别记日志并归入 other。

    record_unknown=False 用于"拿标签试探类目"的场景(如 RemoteOK):
    标签本来就不是类目,不匹配不算未识别。
    """
    # 部分源(如 Jobicy)返回 HTML 转义文本,先解码再匹配
    text = html.unescape(raw or "").strip().lower()
    if not text:
        return "other"
    if text in _CATEGORY_EXACT:
        return _CATEGORY_EXACT[text]
    for keyword, key in _CATEGORY_KEYWORDS:
        if keyword in text:
            return key
    if record_unknown:
        UNKNOWN_CATEGORIES.add(text)
        logger.info("未识别的类目原文,归入 other: %r", raw)
    return "other"


_REGION_KEYWORDS: list[tuple[str, str]] = [
    ("worldwide", "worldwide"),
    ("anywhere", "worldwide"),
    ("global", "worldwide"),
    ("全球", "worldwide"),
    ("不限地区", "worldwide"),
    # 美洲
    ("usa", "americas"),
    ("u.s.", "americas"),
    ("united states", "americas"),
    ("america", "americas"),
    ("canada", "americas"),
    ("latam", "americas"),
    ("brazil", "americas"),
    ("mexico", "americas"),
    ("argentina", "americas"),
    ("colombia", "americas"),
    ("美国", "americas"),
    ("美洲", "americas"),
    ("加拿大", "americas"),
    # 欧洲
    ("europe", "europe"),
    ("emea", "europe"),
    ("united kingdom", "europe"),
    ("uk", "europe"),
    ("germany", "europe"),
    ("france", "europe"),
    ("spain", "europe"),
    ("portugal", "europe"),
    ("netherlands", "europe"),
    ("poland", "europe"),
    ("ireland", "europe"),
    ("italy", "europe"),
    ("cet", "europe"),
    ("欧洲", "europe"),
    ("英国", "europe"),
    ("德国", "europe"),
    ("法国", "europe"),
    # 亚太
    ("apac", "asia_pacific"),
    ("asia", "asia_pacific"),
    ("australia", "asia_pacific"),
    ("new zealand", "asia_pacific"),
    ("india", "asia_pacific"),
    ("japan", "asia_pacific"),
    ("singapore", "asia_pacific"),
    ("philippines", "asia_pacific"),
    ("china", "asia_pacific"),
    ("korea", "asia_pacific"),
    ("hong kong", "asia_pacific"),
    ("taiwan", "asia_pacific"),
    ("taipei", "asia_pacific"),
    ("shanghai", "asia_pacific"),
    ("beijing", "asia_pacific"),
    ("shenzhen", "asia_pacific"),
    ("guangzhou", "asia_pacific"),
    ("hangzhou", "asia_pacific"),
    ("chengdu", "asia_pacific"),
    ("wuhan", "asia_pacific"),
    ("nanjing", "asia_pacific"),
    ("suzhou", "asia_pacific"),
    ("dalian", "asia_pacific"),
    ("亚太", "asia_pacific"),
    ("中国", "asia_pacific"),
    ("中國", "asia_pacific"),
    ("北京", "asia_pacific"),
    ("上海", "asia_pacific"),
    ("深圳", "asia_pacific"),
    ("广州", "asia_pacific"),
    ("杭州", "asia_pacific"),
    ("日本", "asia_pacific"),
    ("新加坡", "asia_pacific"),
    ("印度", "asia_pacific"),
    ("韩国", "asia_pacific"),
    ("澳大利亚", "asia_pacific"),
    # 非洲与中东
    ("africa", "africa_middle_east"),
    ("middle east", "africa_middle_east"),
    ("israel", "africa_middle_east"),
    ("uae", "africa_middle_east"),
    ("egypt", "africa_middle_east"),
    ("nigeria", "africa_middle_east"),
    # 兜底:只写了 "Remote"/"远程" 之类且未指明国家的,视为全球
    ("remote", "worldwide"),
    ("远程", "worldwide"),
]


def map_region(location_text: str) -> str:
    """从地区限制原文推断归一化地区;推断不出归入 other。"""
    text = (location_text or "").strip().lower()
    if not text:
        return "other"
    for keyword, key in _REGION_KEYWORDS:
        if keyword in text:
            return key
    return "other"
