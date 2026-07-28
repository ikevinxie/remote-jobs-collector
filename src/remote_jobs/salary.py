"""薪资原文解析为年薪数值区间(见 SPEC.md §13)。解析不了一律返回 None,保留原文展示。"""
from __future__ import annotations

import re

_CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP"}
_CURRENCY_CODES = {"USD", "EUR", "GBP", "CAD", "AUD", "SGD", "CHF", "JPY", "CNY", "INR"}

# 金额:1,234 / 55k / 55.5k / 100000
_AMOUNT = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(k)?", re.IGNORECASE)
# 非年薪周期(时薪/日薪/月薪)无法可靠折算,直接放弃
_NON_ANNUAL = re.compile(r"/\s*(hr|hour|day|mo|month|week|wk)|per\s+(hour|day|month|week)|hourly|monthly", re.IGNORECASE)

_MIN_PLAUSIBLE_ANNUAL = 5_000  # 展开后低于该值大概率不是年薪(如奖金、时薪)


def parse_salary(text: str) -> tuple[int, int, str] | None:
    """返回 (年薪下限, 年薪上限, 货币代码);单值时上下限相同。"""
    if not text or _NON_ANNUAL.search(text):
        return None
    # "401k"/"403b" 是美国养老金计划,不是薪资金额
    text = re.sub(r"\b40[13]\s*\(?[kb]\)?\b", "", text, flags=re.IGNORECASE)
    # HN 常见共享后缀写法 "$190–250k":k 同时作用于两端,先展开成 "190k - 250k"
    text = re.sub(
        r"(\d+(?:\.\d+)?)\s*[-–—]\s*[$€£]?(\d+(?:\.\d+)?)\s*k\b",
        r"\1k - \2k",
        text,
        flags=re.IGNORECASE,
    )

    currency = ""
    for symbol, code in _CURRENCY_SYMBOLS.items():
        if symbol in text:
            currency = code
            break
    if not currency:
        code_match = re.search(r"\b([A-Z]{3})\b", text)
        if code_match and code_match.group(1) in _CURRENCY_CODES:
            currency = code_match.group(1)
    if not currency:
        currency = "USD"  # 远程岗位默认美元报价

    amounts: list[int] = []
    for number, k_suffix in _AMOUNT.findall(text):
        value = float(number.replace(",", ""))
        if k_suffix:
            value *= 1000
        amounts.append(int(value))
    if not amounts:
        return None
    # 有任一金额低于年薪合理下限(如 "$3k - $10k"、"$500 bonus"),整条视为不可靠
    if min(amounts) < _MIN_PLAUSIBLE_ANNUAL:
        return None

    return (min(amounts), max(amounts), currency)
