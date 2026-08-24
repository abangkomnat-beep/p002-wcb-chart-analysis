"""Fail-closed WCB news blackout gate for BTCUSD F+."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping


class NewsContractError(ValueError):
    """Raised when calendar evidence violates the single-source contract."""


def _utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise NewsContractError("event/cutoff time must be valid ISO-8601") from exc
    if parsed.tzinfo is None:
        raise NewsContractError("event/cutoff time must include timezone")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def evaluate_news_gate(
    events: Iterable[Mapping[str, Any]], *, cutoff_at_utc: str,
    calendar_available: bool, source: str, before_minutes: int, after_minutes: int,
) -> dict[str, Any]:
    if str(source).lower() != "wcb":
        raise NewsContractError("calendar source must be WCB")
    if before_minutes != 30 or after_minutes != 30:
        raise NewsContractError("WCB blackout window is locked at ±30 minutes")
    if not calendar_available:
        return {
            "status": "unproven", "reason_codes": ["NEWS_GATE_UNPROVEN"],
            "blackout_window": None,
        }
    cutoff = _utc(cutoff_at_utc)
    normalized_events = list(events)
    invalid_sources = [item.get("source") for item in normalized_events
                       if str(item.get("source", "")).lower() != "wcb"]
    if invalid_sources:
        raise NewsContractError("multiple/non-WCB calendar sources are forbidden")
    for item in normalized_events:
        if str(item.get("currency", "")).upper() != "USD":
            continue
        if str(item.get("impact", "")).lower() != "high":
            continue
        event_at = _utc(str(item.get("event_at_utc", "")))
        start = event_at - timedelta(minutes=before_minutes)
        end = event_at + timedelta(minutes=after_minutes)
        if start <= cutoff <= end:
            return {
                "status": "blackout",
                "reason_codes": ["HIGH_USD_BLACKOUT"],
                "blackout_window": {
                    "start_utc": _iso(start), "event_at_utc": _iso(event_at),
                    "end_utc": _iso(end), "title": str(item.get("title", "")),
                },
            }
    return {"status": "pass", "reason_codes": [], "blackout_window": None}
