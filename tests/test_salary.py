from remote_jobs.salary import parse_salary


def test_remotive_real_samples():
    """现网真实样本(2026-07-11 采集)。"""
    assert parse_salary("$55k - $100k") == (55000, 100000, "USD")
    assert parse_salary("OTE $25k - $35k") == (25000, 35000, "USD")


def test_full_numbers_with_commas():
    assert parse_salary("USD 100,000 - 150,000") == (100000, 150000, "USD")
    assert parse_salary("$85,000 per year") == (85000, 85000, "USD")


def test_single_value():
    assert parse_salary("€60k") == (60000, 60000, "EUR")
    assert parse_salary("£45,000") == (45000, 45000, "GBP")


def test_currency_code_detection():
    assert parse_salary("CAD 90,000 - 110,000") == (90000, 110000, "CAD")
    assert parse_salary("60k - 80k")[2] == "USD", "无标识默认 USD"


def test_decimal_k():
    assert parse_salary("$52.5k - $70k") == (52500, 70000, "USD")


def test_non_annual_rates_rejected():
    assert parse_salary("$30/hr") is None
    assert parse_salary("$50 per hour") is None
    assert parse_salary("$4,000 per month") is None
    assert parse_salary("hourly rate negotiable") is None


def test_401k_is_not_salary():
    assert parse_salary("Competitive salary + 401k") is None
    assert parse_salary("$100k plus 401(k) match") == (100000, 100000, "USD")


def test_unparseable_returns_none():
    assert parse_salary("") is None
    assert parse_salary("Competitive") is None
    assert parse_salary("DOE") is None
    assert parse_salary("$500 signing bonus") is None, "低于年薪合理下限的数字被过滤"


def test_shared_k_suffix_range_from_hn():
    """回归:2026-07-11 HN 真实样本 '$190–250k',k 同时作用于两端,曾被整条误拒。"""
    assert parse_salary("$190–250k + early equity") == (190000, 250000, "USD")
    assert parse_salary("$140K - $170K") == (140000, 170000, "USD")
    assert parse_salary("100-150k") == (100000, 150000, "USD")


def test_implausibly_low_range_rejected_entirely():
    """回归:2026-07-11 线上样本 '$3k - $10k' 曾被截成 (10000, 10000),区间失真;应整条放弃。"""
    assert parse_salary("$3k - $10k") is None
    assert parse_salary("$20k -$35k") == (20000, 35000, "USD")
