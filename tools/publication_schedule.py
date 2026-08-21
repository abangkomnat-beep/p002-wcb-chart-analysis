"""Pure, fail-closed publication schedule contract for P002.

This module only decides the eligible style slots. It never writes output,
publishes, or mutates the existing policy. Callers must still run per-article
QA and route gates before promotion.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable

WEEKEND = frozenset((5, 6))
MAX_PUBLIC_PER_DAY = 2


class ScheduleError(ValueError):
    """Raised when a schedule request violates a safety invariant."""


def eligible_styles(day: date) -> tuple[str, ...]:
    """Return the approved public style slots for a Bangkok calendar date."""
    if day.weekday() in WEEKEND:
        return ()
    if day.weekday() == 0:
        return ("D", "E")
    return ("E",)


def validate_bundle(day: date, styles: Iterable[str]) -> tuple[str, ...]:
    """Validate a proposed bundle; reject duplicates, weekend and over-cap."""
    proposed = tuple(styles)
    if len(proposed) > MAX_PUBLIC_PER_DAY:
        raise ScheduleError("daily_public_cap_exceeded")
    if len(set(proposed)) != len(proposed):
        raise ScheduleError("duplicate_style_slot")
    allowed = eligible_styles(day)
    if any(style not in allowed for style in proposed):
        raise ScheduleError("style_not_allowed_for_day")
    return proposed


def is_no_run(day: date) -> bool:
    return day.weekday() in WEEKEND

