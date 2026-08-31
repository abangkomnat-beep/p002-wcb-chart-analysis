"""Public article number policy shared by every production style.

Technical prose must not expose decimal numbers.  News/calendar sections are
source reporting, so their values remain byte-for-byte as supplied.  The
policy deliberately runs after a style has composed its Markdown, which keeps
internal calculations and evidence at full precision.
"""
from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction


POLICY_VERSION = "public-number-policy/v1"

_DECIMAL = re.compile(r"(?<![\w.])(?P<number>\d[\d,]*\.\d+)(?![\w.])")
_RATIO_R = re.compile(r"(?<![\w.])(?P<number>\d+(?:\.\d+)?)\s*R\b", re.IGNORECASE)
_LINK = re.compile(r"!?\[[^\]]*\]\([^)]+\)")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_NEWS_CLOCK = re.compile(r"(?:\*\*)?\d{2}:\d{2}(?:\s*น\.)?")
_NEWS_WORDS = ("ข่าว", "ปฏิทิน", "เหตุการณ์", "ประกาศตัวเลข")


def whole_number(value: object, *, comma: bool = True) -> str:
    """Round half up to an integer for public technical copy."""
    rounded = Decimal(str(value).replace(",", "")).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP)
    integer = int(rounded)
    return f"{integer:,}" if comma else str(integer)


def percent(value: object) -> str:
    return f"{whole_number(value)}%"


def ratio(value: object) -> str:
    """Render a decimal R multiple without decimals, e.g. 1.5 -> 3 ต่อ 2."""
    fraction = Fraction(Decimal(str(value))).limit_denominator(100)
    return f"{fraction.numerator} ต่อ {fraction.denominator}"


def _is_news_heading(text: str) -> bool:
    folded = text.casefold()
    return any(word in folded for word in _NEWS_WORDS)


def _replace_unprotected(line: str, transform) -> str:
    pieces: list[str] = []
    cursor = 0
    for match in _LINK.finditer(line):
        pieces.append(transform(line[cursor:match.start()]))
        pieces.append(match.group(0))
        cursor = match.end()
    pieces.append(transform(line[cursor:]))
    return "".join(pieces)


def _technical_fragment(fragment: str) -> str:
    def replace_ratio(match: re.Match[str]) -> str:
        return ratio(match.group("number"))

    fragment = _RATIO_R.sub(replace_ratio, fragment)
    return _DECIMAL.sub(
        lambda match: whole_number(match.group("number")), fragment)


def _source_news_line(line: str, *, inside_news_section: bool) -> bool:
    if not inside_news_section:
        return False
    source_value = any(marker in line for marker in (
        "ที่มา:", "ผลจริง", "ผลประกาศ", "จริง", "ตลาดคาด", "ค่าคาด", "คาด ", "ครั้งก่อน"))
    timed_event = bool(_NEWS_CLOCK.search(line)) and line.lstrip().startswith(("-", "|"))
    linked_news = "ข่าว" in line and "](" in line
    return source_value or timed_event or linked_news


def publicize(markdown: str) -> str:
    """Remove decimals from technical body copy while preserving news values."""
    lines = markdown.splitlines(keepends=True)
    result: list[str] = []
    in_frontmatter = bool(lines and lines[0].rstrip("\r\n") == "---")
    frontmatter_closed = False
    news_heading_level: int | None = None
    news_table = False

    for line in lines:
        bare = line.rstrip("\r\n")
        if in_frontmatter:
            result.append(line)
            if bare == "---" and frontmatter_closed:
                in_frontmatter = False
            elif bare == "---":
                frontmatter_closed = True
            continue

        heading = _HEADING.match(bare)
        if heading:
            level = len(heading.group(1))
            if news_heading_level is not None and level <= news_heading_level:
                news_heading_level = None
            is_news_heading = _is_news_heading(heading.group(2))
            if is_news_heading:
                news_heading_level = level
            news_table = False
            result.append(line if is_news_heading
                          else _replace_unprotected(line, _technical_fragment))
            continue

        if "|" in bare and "ข่าว" in bare and "ตัวเลข" in bare:
            news_table = True
        elif news_table and not bare.strip():
            news_table = False

        explicit_news = bare.startswith("**ข่าวที่ต้องติดตาม:**")
        source_news = _source_news_line(
            bare, inside_news_section=news_heading_level is not None)
        if news_table or explicit_news or source_news:
            result.append(line)
        else:
            result.append(_replace_unprotected(line, _technical_fragment))
    return "".join(result)


def technical_decimal_tokens(markdown: str) -> list[str]:
    """Return technical decimal tokens that would be changed by the policy."""
    normalized = publicize(markdown)
    findings: list[str] = []
    original_lines = markdown.splitlines()
    normalized_lines = normalized.splitlines()
    for before, after in zip(original_lines, normalized_lines):
        if before != after:
            findings.extend(match.group("number") for match in _DECIMAL.finditer(before))
    return findings


def validate(markdown: str) -> list[str]:
    return [f"พบเลขทศนิยมในเนื้อหาเทคนิค: {token}"
            for token in technical_decimal_tokens(markdown)]


__all__ = [
    "POLICY_VERSION", "percent", "publicize", "ratio",
    "technical_decimal_tokens", "validate", "whole_number",
]
