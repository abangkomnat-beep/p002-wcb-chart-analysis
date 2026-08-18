"""Pure value helpers for evidence-bound economic-event analysis.

This module deliberately has no rendering or CLI entry point.  It is the small,
reviewable subset of the stopped ``event_report`` prototype that Style C needs.
"""

from __future__ import annotations

import re

_NUMBER = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")


def parse_value(field: dict | str | int | float | None, *, unit_kind: str | None = None) -> dict:
    """Return a lossless normalized value; unreadable/missing values fail closed."""
    source = field if isinstance(field, dict) else {"raw": field, "value": field}
    raw = source.get("raw")
    if raw in (None, ""):
        raw = source.get("value")
    value = source.get("value")
    if value in (None, ""):
        match = _NUMBER.search(str(raw or ""))
        value = match.group(0).replace(",", "") if match else None
    try:
        number = float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        number = None
    kind = source.get("kind") or source.get("unit_kind") or unit_kind
    unit = source.get("unit")
    unit_source = source.get("unit_source")
    return {
        "raw": None if raw in (None, "") else str(raw),
        "value": number,
        "unit": unit,
        "unit_kind": kind,
        "unit_source": unit_source,
        "scale_unknown": bool(source.get("scale_unknown")),
    }


def units_compatible(left: dict, right: dict) -> bool:
    """True only when two parsed values are safe to compare without conversion."""
    if left.get("value") is None or right.get("value") is None:
        return False
    if left.get("scale_unknown") or right.get("scale_unknown"):
        return False
    lk, rk = left.get("unit_kind"), right.get("unit_kind")
    if not lk or not rk or lk != rk:
        return False
    lu, ru = left.get("unit"), right.get("unit")
    return lu == ru or (lk == "index" and not lu and not ru)


def compare(left: dict, right: dict) -> str:
    """Return above/equal/below/unknown without inventing a unit conversion."""
    if not units_compatible(left, right):
        return "unknown"
    if left["value"] > right["value"]:
        return "above"
    if left["value"] < right["value"]:
        return "below"
    return "equal"
