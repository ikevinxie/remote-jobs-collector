from remote_jobs.timezones import infer_range


def test_explicit_utc_from_live_samples():
    """2026-07 现网真实样式。"""
    assert infer_range("Remote (UTC+3)") == (3, 3)
    assert infer_range("Remote (UTC-1 to UTC+3 only)") == (-1, 3)
    assert infer_range("USA, CST (UTC-6)") == (-6, -6), "括号里的显式值可用,CST 本身不认"
    assert infer_range("GMT+2 preferred") == (2, 2)


def test_multiple_explicit_values_form_range():
    assert infer_range("UTC-5 or UTC+1 teams") == (-5, 1)


def test_abbreviations_widened():
    assert infer_range("4h overlap with PST required") == (-11, -5)
    assert infer_range("CET working hours") == (-2, 4)


def test_ambiguous_abbreviations_not_recognized():
    assert infer_range("CST business hours") is None, "CST 中美歧义,拒绝识别"
    assert infer_range("IST timezone") is None, "IST 印度/爱尔兰歧义"


def test_no_info_returns_none():
    assert infer_range("Worldwide") is None
    assert infer_range("") is None
    assert infer_range("competitive salary, flexible hours") is None


def test_out_of_range_offsets_rejected():
    assert infer_range("UTC+99") is None


def test_range_is_ordered():
    result = infer_range("UTC+3 to UTC-1")
    assert result == (-1, 3), "无论书写顺序,输出 min<=max"
