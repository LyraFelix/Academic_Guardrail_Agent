"""Compare explicitly compatible quantities; never guess units or statistical meaning."""

from dataclasses import dataclass
from decimal import Decimal
import re

from academic_guardrail.core.claim_checks.text import finding, normalize

# Dimension, multiplier to the base unit. Percent and percentage points differ.
UNITS = {
    "%": ("percent", "1"), "percent": ("percent", "1"), "per cent": ("percent", "1"),
    "percentage points": ("percentage_point", "1"), "percentage point": ("percentage_point", "1"), "个百分点": ("percentage_point", "1"),
    "mg": ("mass", "0.001"), "g": ("mass", "1"), "kg": ("mass", "1000"),
    "μg": ("mass", "0.000001"), "ug": ("mass", "0.000001"), "毫克": ("mass", "0.001"), "克": ("mass", "1"),
    "ml": ("volume", "0.001"), "l": ("volume", "1"),
    "ms": ("time", "0.001"), "s": ("time", "1"), "seconds": ("time", "1"), "second": ("time", "1"),
    "minutes": ("time", "60"), "minute": ("time", "60"), "hours": ("time", "3600"),
    "days": ("time", "86400"), "weeks": ("time", "604800"), "week": ("time", "604800"), "周": ("time", "604800"),
    "patients": ("patient_count", "1"), "patient": ("patient_count", "1"), "例": ("patient_count", "1"),
}
UNIT_PATTERN = "|".join(re.escape(unit) + (r"(?![a-z])" if unit[-1:].isascii() and unit[-1:].isalpha() else "") for unit in sorted(UNITS, key=len, reverse=True))
QUANTITY = re.compile(rf"(?<![a-z0-9_.])(?P<value>[+-]?(?:(?:\d{{1,3}}(?:,\d{{3}})+|\d+)(?:\.\d+)?|\.\d+))(?:\s*(?P<unit>{UNIT_PATTERN}))?", re.I)
QUALIFIERS = ((r"(?:up to|at most|no more than|最多|至多|不超过|<=|≤)\s*$", "upper_inclusive"),
              (r"(?:less than|小于|(?<![<>=])<)\s*$", "upper_exclusive"),
              (r"(?:at least|至少|>=|≥)\s*$", "lower_inclusive"),
              (r"(?:more than|greater than|超过|大于|(?<![<>=])>)\s*$", "lower_exclusive"),
              (r"(?:approximately|about|around|roughly|约|大约|~|≈)\s*$", "approximate"))


@dataclass(frozen=True)
class Quantity:
    value: Decimal
    dimension: str
    qualifier: str
    raw: str
    unknown_unit: bool = False


def quantities(text: str) -> list[Quantity]:
    value = normalize(text)
    extracted = []
    for match in QUANTITY.finditer(value):
        unit = match.group("unit") or ""
        dimension, scale = UNITS.get(unit, ("unspecified", "1"))
        qualifier = next((name for pattern, name in QUALIFIERS if re.search(pattern, value[:match.start()])), "exact")
        number = Decimal(match.group("value").replace(",", "")) * Decimal(scale)
        tail = value[match.end():]
        # Unrecognized adjacent unit words are never treated as dimensionless.
        unknown = not unit and bool(re.match(r"\s*[a-zμ\u4e00-\u9fff]+", tail))
        extracted.append(Quantity(number, dimension, qualifier, match.group(), unknown))
    return extracted


def check_numbers(claim: str, evidence: str, conditions_differ: bool = False):
    first, second = quantities(claim), quantities(evidence)
    if not first and not second:
        return []
    c, e = normalize(claim), normalize(evidence)
    complex_form = r"\d\s*(?:[-–—]|to|至|到)\s*\d|\d(?:\.\d+)?[eE][+-]?\d|±|\b(?:confidence interval|ci)\b|\d\s*[a-zμ]+\s*[/·]"
    if c != e and (re.search(complex_form, c) or re.search(complex_form, e)):
        return [finding("COMPLEX_QUANTITY", "NUMBER", "检测到区间、科学计数或统计区间；当前规则不把它简化成单个数值。", claim, evidence)]
    if len(first) != len(second):
        return [finding("NUMBER_COVERAGE", "NUMBER", "两段文字中的数量信息未一一对应，不能据相似度补全缺失数值。", claim, evidence)]
    if len(first) > 1 and c != e:
        return [finding("COMPLEX_QUANTITY", "NUMBER", "存在多个数量，当前规则无法可靠绑定每个数值与指标，请逐项核对。", claim, evidence)]
    results = []
    for a, b in zip(first, second):
        if a.unknown_unit or b.unknown_unit:
            results.append(finding("UNKNOWN_UNIT", "NUMBER", "发现未支持的数量单位，未按无量纲数字比较。", claim, evidence))
        elif a.dimension != b.dimension:
            results.append(finding("UNIT_NOT_COMPARABLE", "NUMBER", f"单位或量纲未对应：{a.raw} / {b.raw}；未猜测换算关系。", claim, evidence))
        elif a.qualifier != b.qualifier:
            results.append(finding("NUMERIC_QUALIFIER_CHANGED", "NUMBER", f"数量限定不同：{a.raw} ({a.qualifier}) / {b.raw} ({b.qualifier})。", claim, evidence))
        elif a.value != b.value:
            if conditions_differ or a.qualifier != "exact":
                results.append(finding("NUMBER_NOT_COMPARABLE", "NUMBER", "数量不同，但适用条件或上下界未对齐，不能直接宣称数值矛盾。", claim, evidence))
            else:
                results.append(finding("NUMBER_MISMATCH", "NUMBER", f"相同指标的可比数值不同：{a.raw} / {b.raw}（已按显式单位换算）。", claim, evidence, conflict=True))
    return results
