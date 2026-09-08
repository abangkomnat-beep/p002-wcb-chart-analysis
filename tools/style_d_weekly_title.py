"""Canonical weekly period and title semantics for Style D.

The production source chooses one ISO Monday--Friday period.  Localized
delivery may format that period differently, but it must not recalculate it.
This module deliberately has no market-data or timezone logic.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REPO_ROOT = Path(__file__).resolve().parents[1]
_CLDR_ROOT = _REPO_ROOT / "language" / "vendor" / "unicode-cldr-48.2.0" / "locales"


class StyleDWeeklyTitleError(ValueError):
    """The Style D weekly period or localized title is not trustworthy."""


def _parse_iso(value: object, field: str) -> date:
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        raise StyleDWeeklyTitleError(f"{field} must be canonical YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise StyleDWeeklyTitleError(f"{field} is not a real date") from exc
    if parsed.isoformat() != value:
        raise StyleDWeeklyTitleError(f"{field} must be canonical YYYY-MM-DD")
    return parsed


def week_bounds(publish_date: str) -> tuple[str, str]:
    """Return the Monday--Friday period containing ``publish_date``."""
    anchor = _parse_iso(publish_date, "publish_date")
    monday = anchor - timedelta(days=anchor.weekday())
    return monday.isoformat(), (monday + timedelta(days=4)).isoformat()


def canonical_period(start: object, end: object, *, publish_date: str | None = None,
                     require_publication_in_period: bool = False) -> tuple[str, str]:
    """Validate and return one canonical ISO weekly period.

    A Style D period is always Monday through Friday.  ``publish_date`` is
    checked when supplied by the production route; old offline story fixtures
    can omit the stricter containment check.
    """
    first = _parse_iso(start, "week_start")
    last = _parse_iso(end, "week_end")
    if first.weekday() != 0 or last != first + timedelta(days=4):
        raise StyleDWeeklyTitleError("Style D week must be Monday through Friday")
    if require_publication_in_period and publish_date is not None:
        published = _parse_iso(publish_date, "publish_date")
        if not first <= published <= last:
            raise StyleDWeeklyTitleError("publish_date is outside the Style D week")
    return first.isoformat(), last.isoformat()


def period_for_story(story: dict, *, strict_publication: bool = False) -> tuple[str, str]:
    """Resolve the source period once from calendar metadata or publication date."""
    published = str(story.get("publish_date") or story.get("current", {}).get("date") or "")
    calendar = story.get("calendar") or {}
    start, end = calendar.get("week_start"), calendar.get("week_end")
    if start is None and end is None:
        return (*week_bounds(published),)
    if start is None or end is None:
        raise StyleDWeeklyTitleError("calendar week_start/week_end must be supplied together")
    return canonical_period(start, end, publish_date=published,
                            require_publication_in_period=strict_publication)


THAI_MONTHS = ("มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
               "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม")


def _cldr_months(locale: str) -> tuple[str, ...]:
    """Read month names from the pinned CLDR vendor data, with safe fallback."""
    language = (locale or "").split("-")[0].lower()
    candidates = [locale, f"{language}-001", language]
    path = next((_CLDR_ROOT / candidate / "ca-gregorian.json"
                 for candidate in candidates if (_CLDR_ROOT / candidate / "ca-gregorian.json").exists()), None)
    if path is None:
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        calendars = payload["main"][next(iter(payload["main"]))]["dates"]["calendars"]["gregorian"]
        wide = calendars["months"]["format"]["wide"]
        return tuple(str(wide[str(index)]) for index in range(1, 13))
    except (KeyError, OSError, TypeError, ValueError):
        return ()


def _cldr_month_variants(locale: str) -> tuple[tuple[str, ...], ...]:
    """Return wide and abbreviated month names for semantic title checks."""
    language = (locale or "").split("-")[0].lower()
    candidates = [locale, f"{language}-001", language]
    path = next((_CLDR_ROOT / candidate / "ca-gregorian.json"
                 for candidate in candidates if (_CLDR_ROOT / candidate / "ca-gregorian.json").exists()), None)
    if path is None:
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        calendars = payload["main"][next(iter(payload["main"]))]["dates"]["calendars"]["gregorian"]
        formats = calendars["months"]["format"]
        return tuple(tuple(str(form[str(index)]) for index in range(1, 13))
                     for form in (formats["wide"], formats["abbreviated"]))
    except (KeyError, OSError, TypeError, ValueError):
        return ()


def _date_parts(value: str) -> tuple[int, int, int]:
    parsed = _parse_iso(value, "date")
    return parsed.day, parsed.month, parsed.year


def thai_range(start: str, end: str) -> str:
    """Thai full-month range, retaining both months and years across boundaries."""
    first_day, first_month, first_year = _date_parts(start)
    last_day, last_month, last_year = _date_parts(end)
    if (first_month, first_year) == (last_month, last_year):
        return f"{first_day}-{last_day} {THAI_MONTHS[first_month - 1]} {first_year}"
    return (f"{first_day} {THAI_MONTHS[first_month - 1]} {first_year}-"
            f"{last_day} {THAI_MONTHS[last_month - 1]} {last_year}")


def localized_range(start: str, end: str, locale: str) -> str:
    """Render a readable range using pinned CLDR month names.

    Thai follows the approved editorial form.  Other locales use a stable
    day-month-year form; the validator accepts translators' punctuation and
    ordering while requiring every semantic component.
    """
    start, end = canonical_period(start, end)
    if (locale or "").lower().startswith("th"):
        return thai_range(start, end)
    months = _cldr_months(locale)
    if len(months) != 12:
        raise StyleDWeeklyTitleError(f"no pinned CLDR month names for locale {locale!r}")
    sd, sm, sy = _date_parts(start)
    ed, em, ey = _date_parts(end)
    if (sm, sy) == (em, ey):
        return f"{sd}-{ed} {months[sm - 1]} {sy}"
    return f"{sd} {months[sm - 1]} {sy}-{ed} {months[em - 1]} {ey}"


WEEKLY_MARKERS = {
    "th": ("รายสัปดาห์",), "en": ("weekly",), "ms": ("mingguan",),
    "pt": ("semanal",), "es": ("semanal",), "ar": ("أسبوع", "أسبوعي"),
    "ru": ("недель",), "zh": ("每周", "每週"), "hi": ("साप्ताहिक",),
    "id": ("mingguan",), "ja": ("週間",), "ur": ("ہفتہ وار",),
    "bn": ("সাপ্তাহিক",), "tr": ("haftalık",), "fil": ("lingguhan",),
    "ko": ("주간",), "am": ("ሳምንታዊ",), "sw": ("kila wiki",),
    "si": ("සතිපතා",),
}


def _numeric_values(text: str) -> list[int]:
    values: list[int] = []
    for match in re.finditer(r"[\d\u0660-\u0669\u06f0-\u06f9\u0966-\u096f\u09e6-\u09ef]+", text):
        token = "".join(str(unicodedata.digit(char)) for char in match.group())
        try:
            values.append(int(token))
        except ValueError:
            continue
    return values


def validate_localized_title(title: str, start: str, end: str, *, locale: str) -> list[str]:
    """Return fail-closed findings for a localized Style D title.

    Date components are checked semantically, while language-specific month
    names come from the pinned CLDR data.  This permits natural punctuation
    and date order without allowing a translated title to silently move weeks.
    """
    findings: list[str] = []
    try:
        start, end = canonical_period(start, end)
        sd, sm, sy = _date_parts(start)
        ed, em, ey = _date_parts(end)
    except StyleDWeeklyTitleError as exc:
        return [str(exc)]
    title_casefold = title.casefold()
    language = (locale or "").split("-")[0].lower()
    markers = WEEKLY_MARKERS.get(language, ())
    if not any(marker.casefold() in title_casefold for marker in markers):
        findings.append("title does not express a weekly period")
    month_variants = _cldr_month_variants(locale) if language != "th" else (
        THAI_MONTHS, ("ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
                      "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."))
    for month in {sm, em}:
        month_names = [names[month - 1].casefold() for names in month_variants]
        if month_names and not any(month_name in title_casefold for month_name in month_names):
            findings.append(f"title is missing month {month}")
    numbers = _numeric_values(title)
    if sd not in numbers or ed not in numbers:
        findings.append("title is missing one or both week boundary days")
    for year in {sy, ey}:
        if year not in numbers:
            findings.append(f"title is missing year {year}")
    if len(set(findings)) != len(findings):
        findings = list(dict.fromkeys(findings))
    return findings


__all__ = ["StyleDWeeklyTitleError", "canonical_period", "localized_range",
           "period_for_story", "thai_range", "validate_localized_title", "week_bounds"]
