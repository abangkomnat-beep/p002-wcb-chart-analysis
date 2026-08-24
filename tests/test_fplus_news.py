"""WCB-only High-impact USD blackout contract with inclusive ±30-minute edges."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fixtures.fplus.contract_support import iso, require_module


EVENT_AT = datetime(2026, 8, 24, 12, 30, tzinfo=timezone.utc)


def event(*, currency="USD", impact="high", source="wcb") -> dict:
    return {
        "source": source,
        "currency": currency,
        "impact": impact,
        "event_at_utc": iso(EVENT_AT),
        "title": "Synthetic event",
    }


@pytest.mark.parametrize("offset_minutes", [-30, 0, 30])
def test_high_usd_blackout_includes_both_boundaries(offset_minutes):
    news = require_module("tools.fplus_news")
    result = news.evaluate_news_gate(
        [event()], cutoff_at_utc=iso(EVENT_AT + timedelta(minutes=offset_minutes)),
        calendar_available=True, source="wcb", before_minutes=30, after_minutes=30,
    )
    assert result["status"] == "blackout"
    assert "HIGH_USD_BLACKOUT" in result["reason_codes"]


@pytest.mark.parametrize("offset_minutes", [-31, 31])
def test_outside_blackout_window_passes(offset_minutes):
    news = require_module("tools.fplus_news")
    result = news.evaluate_news_gate(
        [event()], cutoff_at_utc=iso(EVENT_AT + timedelta(minutes=offset_minutes)),
        calendar_available=True, source="wcb", before_minutes=30, after_minutes=30,
    )
    assert result["status"] == "pass"


@pytest.mark.parametrize("changed", [event(currency="EUR"), event(impact="medium")])
def test_non_usd_or_non_high_events_do_not_blackout(changed):
    news = require_module("tools.fplus_news")
    result = news.evaluate_news_gate(
        [changed], cutoff_at_utc=iso(EVENT_AT), calendar_available=True,
        source="wcb", before_minutes=30, after_minutes=30,
    )
    assert result["status"] == "pass"


def test_calendar_unavailable_is_unproven_no_trade_not_data_block():
    news = require_module("tools.fplus_news")
    result = news.evaluate_news_gate(
        [], cutoff_at_utc=iso(EVENT_AT), calendar_available=False,
        source="wcb", before_minutes=30, after_minutes=30,
    )
    assert result["status"] == "unproven"
    assert "NEWS_GATE_UNPROVEN" in result["reason_codes"]


def test_multiple_calendar_sources_are_rejected():
    news = require_module("tools.fplus_news")
    with pytest.raises(news.NewsContractError, match="source|WCB|wcb"):
        news.evaluate_news_gate(
            [event(), event(source="other")], cutoff_at_utc=iso(EVENT_AT),
            calendar_available=True, source="wcb", before_minutes=30, after_minutes=30,
        )

