"""Fail-closed data contracts for one H4/H1/M30/M15 snapshot and cutoff."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from fixtures.fplus.contract_support import iso, make_rows, require_module, valid_snapshot


def config() -> dict:
    return {
        "required_timeframes": ["4h", "1h", "30min", "15min"],
        "warmup_bars": {"4h": 4, "1h": 4, "30min": 4, "15min": 4},
        "freshness_grace_seconds": {"4h": 300, "1h": 300, "30min": 300, "15min": 300},
        "cross_timeframe_tolerance": 0.000001,
    }


def reason_codes(report) -> set[str]:
    return set(report["reason_codes"])


def test_valid_snapshot_passes_price_data_gates():
    data = require_module("tools.fplus_data")
    report = data.evaluate_data_gates(valid_snapshot(), config=config())
    assert report["price_data_status"] == "pass"
    assert report["freshness"]["status"] == "pass"
    assert report["integrity"]["status"] == "pass"
    assert report["alignment"]["status"] == "pass"


@pytest.mark.parametrize("timeframe", ["4h", "1h", "30min", "15min"])
def test_each_missing_timeframe_blocks_retryably(timeframe):
    data = require_module("tools.fplus_data")
    snapshot = valid_snapshot()
    snapshot["series"].pop(timeframe)
    report = data.evaluate_data_gates(snapshot, config=config())
    assert report["price_data_status"] == "blocked_retryable"
    assert f"MISSING_TIMEFRAME_{timeframe.upper()}" in reason_codes(report)


def test_forming_rows_are_dropped_at_the_single_cutoff():
    data = require_module("tools.fplus_data")
    cutoff = datetime(2026, 8, 24, 2, 0, tzinfo=timezone.utc)
    rows = make_rows(timeframe_minutes=15, count=64, end_close=cutoff)
    rows += make_rows(timeframe_minutes=15, count=1, end_close=cutoff + timedelta(minutes=15))
    result = data.trim_closed_rows(rows, timeframe="15min", cutoff_at_utc=iso(cutoff))
    assert result["dropped_forming_bars"] == 1
    assert all(row["bar_close_at_utc"] <= iso(cutoff) for row in result["rows"])


@pytest.mark.parametrize("mutation,expected", [
    ("stale", "STALE_15MIN"),
    ("timezone", "TIMEZONE_UNVERIFIED_15MIN"),
    ("duplicate", "DUPLICATE_BAR_15MIN"),
    ("gap", "GAP_15MIN"),
    ("ohlc", "OHLC_INVALID_15MIN"),
    ("warmup", "INSUFFICIENT_WARMUP_15MIN"),
])
def test_integrity_faults_fail_closed(mutation, expected):
    data = require_module("tools.fplus_data")
    snapshot = valid_snapshot()
    frame = snapshot["series"]["15min"]
    if mutation == "stale":
        frame["latest_bar_close_at_utc"] = "2026-08-24T01:30:00Z"
    elif mutation == "timezone":
        frame["timezone_verified"] = False
    elif mutation == "duplicate":
        frame["rows"][-1] = deepcopy(frame["rows"][-2])
    elif mutation == "gap":
        frame["rows"].pop(-2)
        frame["row_count"] -= 1
    elif mutation == "ohlc":
        frame["rows"][-1]["low"] = frame["rows"][-1]["high"] + 1
    elif mutation == "warmup":
        frame["rows"] = frame["rows"][-10:]
        frame["row_count"] = 10
    report = data.evaluate_data_gates(snapshot, config=config())
    assert report["price_data_status"] == "blocked_retryable"
    assert expected in reason_codes(report)


def test_cross_timeframe_mismatch_is_blocked_not_silently_disabled():
    data = require_module("tools.fplus_data")
    snapshot = valid_snapshot()
    snapshot["series"]["1h"]["rows"][-1]["close"] += 5_000
    report = data.evaluate_data_gates(snapshot, config=config())
    assert report["price_data_status"] == "blocked_retryable"
    assert "CROSS_TIMEFRAME_MISMATCH" in reason_codes(report)


def test_cutoff_and_trade_date_are_shared_across_all_timeframes():
    data = require_module("tools.fplus_data")
    snapshot = valid_snapshot()
    report = data.evaluate_data_gates(snapshot, config=config())
    assert report["cutoff_at_utc"] == snapshot["cutoff_at_utc"]
    assert report["trade_date_bangkok"] == "2026-08-24"
    assert all(
        frame["latest_bar_close_at_utc"] <= snapshot["cutoff_at_utc"]
        for frame in snapshot["series"].values()
    )
