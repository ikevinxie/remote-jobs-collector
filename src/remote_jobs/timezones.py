"""时区要求推断(见 SPEC.md §22)。保守策略:没把握就返回 None,绝不猜。"""
from __future__ import annotations

import re

# 无歧义的时区缩写 → UTC 锚点。CST(中国/美国中部)与 IST(印度/爱尔兰/以色列)歧义,刻意不识别。
_TZ_ABBREV: dict[str, int] = {
    "pst": -8, "pdt": -7, "pt": -8,
    "mst": -7, "mdt": -6,
    "est": -5, "edt": -4, "et": -5,
    "cet": 1, "cest": 2,
    "bst": 1,
    "jst": 9,
    "aest": 10,
    "sgt": 8,
}
_ABBREV_SPREAD = 3  # 缩写只给锚点,按 ±3 小时放宽为区间

# UTC+3 / GMT-5 / UTC +5.5
_EXPLICIT = re.compile(r"\b(?:UTC|GMT)\s*([+-]\s*\d{1,2}(?:\.5)?)", re.IGNORECASE)
# UTC-1 to UTC+3 / UTC +1 - UTC+5
_RANGE = re.compile(
    r"\b(?:UTC|GMT)\s*([+-]\s*\d{1,2}(?:\.5)?)\s*(?:to|-|–|—|~)\s*(?:UTC|GMT)?\s*([+-]\s*\d{1,2}(?:\.5)?)",
    re.IGNORECASE,
)
_ABBREV_WORD = re.compile(r"\b(" + "|".join(_TZ_ABBREV) + r")\b", re.IGNORECASE)


def _to_offset(text: str) -> int | None:
    try:
        value = float(text.replace(" ", ""))
    except ValueError:
        return None
    offset = int(round(value))
    return offset if -12 <= offset <= 14 else None


def infer_range(text: str) -> tuple[int, int] | None:
    """从自由文本推断 UTC 偏移区间 (tz_min, tz_max);推断不出返回 None。"""
    if not text:
        return None

    range_match = _RANGE.search(text)
    if range_match:
        low, high = _to_offset(range_match.group(1)), _to_offset(range_match.group(2))
        if low is not None and high is not None:
            return (min(low, high), max(low, high))

    explicit = [offset for m in _EXPLICIT.finditer(text) if (offset := _to_offset(m.group(1))) is not None]
    if explicit:
        return (min(explicit), max(explicit))

    abbrevs = [_TZ_ABBREV[m.group(1).lower()] for m in _ABBREV_WORD.finditer(text)]
    if abbrevs:
        return (min(abbrevs) - _ABBREV_SPREAD, max(abbrevs) + _ABBREV_SPREAD)

    return None
