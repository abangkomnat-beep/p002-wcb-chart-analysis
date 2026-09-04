from __future__ import annotations

import copy
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from tools import style_l_h1_plan as h1plan


def bars(values, *, start_hour=0):
    result = []
    for index, (low, high, close) in enumerate(values):
        result.append({
            "at": f"2026-09-{1 + (start_hour + index) // 24:02d}T{(start_hour + index) % 24:02d}:00:00+00:00",
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "closed": True,
        })
    return result


def test_public_price_is_half_up_and_never_changes_canonical():
    payload = {"entry": Decimal("1.16450"), "tp": Decimal("1.16449")}
    before = copy.deepcopy(payload)
    assert h1plan.public_price(payload["entry"]) == "1.165"
    assert h1plan.public_price(payload["tp"]) == "1.164"
    assert h1plan.public_price(0.9874999999999999) == "0.988"
    assert payload == before


@pytest.mark.parametrize("value", [float("nan"), float("inf"), "bad", True])
def test_public_price_rejects_non_finite_or_non_numeric(value):
    with pytest.raises(h1plan.H1ContractError):
        h1plan.public_price(value)


def test_confirmed_pivots_need_two_closed_bars_on_the_right():
    rows = bars([
        (1.00, 1.20, 1.10), (0.99, 1.25, 1.12), (1.00, 1.30, 1.20),
        (0.98, 1.24, 1.10), (1.01, 1.22, 1.15),
    ])
    pivots = h1plan.confirmed_pivots(rows, left=2, right=2)
    assert [(p.kind, p.index, p.price) for p in pivots] == [("high", 2, 1.30)]
    assert h1plan.confirmed_pivots(rows[:-1], left=2, right=2) == []


def test_future_mutation_does_not_change_prefix_plan():
    prefix = _buy_fixture()
    decision = datetime(2026, 9, 1, 23, tzinfo=timezone.utc)
    first = h1plan.build_h1_plan("eurusd", "up", prefix, [], decision_at=decision)
    future = prefix + bars([(0.7, 1.8, 1.5), (0.6, 1.9, 1.6)], start_hour=len(prefix))
    second = h1plan.build_h1_plan("eurusd", "up", future, [], decision_at=decision)
    assert first == second


def test_decision_time_must_be_timezone_aware():
    with pytest.raises(h1plan.H1ContractError, match="timezone-aware"):
        h1plan.build_h1_plan(
            "eurusd", "up", _buy_fixture(), [],
            decision_at=datetime(2026, 9, 1, 23), atr14=0.01)


def test_anchor_age_uses_the_120_bar_window_index():
    tail = _buy_fixture()
    combined = ([(0.90, 1.10, 1.0)] * 20
                + [(row["low"], row["high"], row["close"]) for row in tail])
    plan = h1plan.build_h1_plan(
        "eurusd", "up", bars(combined), [],
        decision_at=datetime(2026, 9, 2, 19, tzinfo=timezone.utc),
        atr14=0.01, anchor_max_age=48)
    assert plan["plans"][0]["anchor_index"] == 28


def test_buy_plan_uses_confirmed_swing_low_stop_floor_and_structural_targets():
    plan = h1plan.build_h1_plan(
        "eurusd", "up", _buy_fixture(), [],
        decision_at=datetime(2026, 9, 5, 0, tzinfo=timezone.utc),
        atr14=0.010, stop_atr=1.5,
    )
    leg = plan["plans"][0]
    assert plan["status"] == "WAIT_H1_ZONE"
    assert leg["side"] == "BUY"
    assert leg["entry_zone"] == {"low": 1.0, "high": 1.0025}
    assert leg["stop_loss"] == pytest.approx(0.9875)
    assert leg["risk_reward"][0] >= 1.5
    assert leg["risk_reward"][1] >= 2.0
    assert plan["public_timeframe"] == "H4-H1"
    assert "m15" not in str(plan).lower()


def test_sell_leg_is_symmetric_to_buy_leg():
    buy = h1plan.build_leg("BUY", anchor=1.0, atr=0.01, stop_atr=1.5,
                           target_candidates=[1.03, 1.04])
    sell = h1plan.build_leg("SELL", anchor=1.0, atr=0.01, stop_atr=1.5,
                            target_candidates=[0.97, 0.96])
    assert buy["entry_zone"] == {"low": 1.0, "high": 1.0025}
    assert sell["entry_zone"] == {"low": 0.9975, "high": 1.0}
    assert buy["risk_atr"] == pytest.approx(sell["risk_atr"])
    assert buy["risk_reward"] == sell["risk_reward"]
    assert h1plan.public_price(buy["stop_loss"]) == "0.988"
    assert h1plan.public_price(sell["stop_loss"]) == "1.013"


def test_stop_cap_and_missing_targets_fail_closed():
    with pytest.raises(h1plan.H1PlanHold, match="NO_PLAN_STOP_CAP"):
        h1plan.build_leg(
            "BUY", anchor=1.0, atr=0.01, stop_atr=3.001,
            target_candidates=[1.1, 1.2])
    with pytest.raises(h1plan.H1PlanHold, match="NO_PLAN_RR"):
        h1plan.build_leg(
            "BUY", anchor=1.0, atr=0.01, stop_atr=1.5,
            target_candidates=[1.01, 1.02])


@pytest.mark.parametrize("kwargs", [
    {"buffer_atr": -0.001}, {"buffer_atr": float("nan")},
    {"max_stop_atr": 0}, {"max_stop_atr": -1},
])
def test_leg_rejects_invalid_buffer_and_cap(kwargs):
    with pytest.raises(h1plan.H1ContractError):
        h1plan.build_leg("BUY", anchor=1.0, atr=0.01,
                         target_candidates=[1.1, 1.2], **kwargs)


def test_atr14_fallback_uses_true_range_and_requires_prior_close():
    short = _buy_fixture()[:14]
    with pytest.raises(h1plan.H1PlanHold, match="NO_PLAN_ATR14_HISTORY"):
        h1plan.build_h1_plan(
            "eurusd", "up", short, [],
            decision_at=datetime(2026, 9, 5, tzinfo=timezone.utc))
    source = _buy_fixture()
    source[-1]["open"] = source[-1]["close"] = 1.20
    source[-1]["high"] = 1.201
    source[-1]["low"] = 1.199
    plan = h1plan.build_h1_plan(
        "eurusd", "up", source, [],
        decision_at=datetime(2026, 9, 5, tzinfo=timezone.utc))
    assert plan["plans"][0]["risk_atr"] == pytest.approx(1.5)


@pytest.mark.parametrize("field,value", [
    ("open", float("nan")), ("open", 1.5), ("close", 0.5),
])
def test_ohlc_domain_fails_closed(field, value):
    source = _buy_fixture()
    source[0][field] = value
    with pytest.raises(h1plan.H1ContractError, match="OHLC|finite"):
        h1plan.build_h1_plan(
            "eurusd", "up", source, [],
            decision_at=datetime(2026, 9, 5, tzinfo=timezone.utc), atr14=0.01)


def test_status_comes_from_closed_h1_zone_intersection_and_rejection():
    wait = h1plan.classify_h1_state("BUY", 1.0, 1.0025, {"low": 1.01, "high": 1.02, "close": 1.015})
    ready = h1plan.classify_h1_state("BUY", 1.0, 1.0025, {"low": 1.001, "high": 1.01, "close": 1.002})
    confirmed = h1plan.classify_h1_state("BUY", 1.0, 1.0025, {"low": 0.999, "high": 1.01, "close": 1.006})
    assert (wait, ready, confirmed) == ("WAIT_H1_ZONE", "H1_ENTRY_READY", "H1_TRIGGER_CONFIRMED")


def test_position_size_is_inverse_to_effective_stop_and_oco_is_capped():
    one = h1plan.risk_sizing(10_000, 0.005, 0.010, cost_per_unit=0.001)
    wider = h1plan.risk_sizing(10_000, 0.005, 0.020, cost_per_unit=0.001)
    assert one["risk_budget"] == wider["risk_budget"] == 50
    assert wider["quantity"] < one["quantity"]
    assert h1plan.oco_risk_budgets(10_000, 0.005) == {"BUY": 25.0, "SELL": 25.0, "total": 50.0}


def test_lifecycle_is_structural_and_friday_expires_before_weekend():
    friday = datetime(2026, 9, 4, 13, tzinfo=timezone.utc)
    expiry = h1plan.lifecycle_expiry(friday, max_trading_days=5)
    assert expiry.weekday() == 4
    assert expiry.hour == 21
    assert h1plan.lifecycle_status(
        "BUY", anchor=1.0, current_close=0.999, h4_bias="up",
        original_h4_bias="up", newer_anchor=False, tp2_hit=False,
        now=friday, expires_at=expiry) == "INVALIDATED_STRUCTURE"


@pytest.mark.parametrize("created,expected", [
    (datetime(2026, 9, 4, 22, tzinfo=timezone.utc), datetime(2026, 9, 11, 21, tzinfo=timezone.utc)),
    (datetime(2026, 9, 5, 12, tzinfo=timezone.utc), datetime(2026, 9, 11, 12, tzinfo=timezone.utc)),
    (datetime(2026, 9, 6, 12, tzinfo=timezone.utc), datetime(2026, 9, 11, 12, tzinfo=timezone.utc)),
])
def test_lifecycle_created_after_friday_close_uses_next_friday(created, expected):
    expiry = h1plan.lifecycle_expiry(created, max_trading_days=5)
    assert expiry == expected


@pytest.mark.parametrize("days", [0, -1, True, 1.5])
def test_lifecycle_rejects_invalid_trading_day_cap(days):
    with pytest.raises(h1plan.H1ContractError):
        h1plan.lifecycle_expiry(
            datetime(2026, 9, 4, 13, tzinfo=timezone.utc), max_trading_days=days)


def test_lifecycle_terminal_precedence_is_deterministic():
    now = datetime(2026, 9, 4, 13, tzinfo=timezone.utc)
    assert h1plan.lifecycle_status(
        "BUY", anchor=1.0, current_close=0.9, h4_bias="down",
        original_h4_bias="up", newer_anchor=True, tp2_hit=True,
        now=now, expires_at=now) == "COMPLETE_TP2"


def test_six_column_table_has_no_m15_or_slash_separator_and_keeps_payload():
    plan = h1plan.build_h1_plan(
        "eurusd", "up", _buy_fixture(), [],
        decision_at=datetime(2026, 9, 5, 0, tzinfo=timezone.utc), atr14=0.010)
    before = copy.deepcopy(plan)
    table = h1plan.render_public_table(plan)
    assert "<table>" in table and table.count("<th>") == 6
    assert "<th>Side</th>" in table and "TP &amp; RR" in table
    assert "TP1 –" in table and "TP2 –" in table
    assert " / " not in table and "M15" not in table
    assert "ราคาแสดง 3 ตำแหน่ง" in table
    assert plan == before


def test_display_collision_marks_both_targets_without_merging():
    plan = {"status": "WAIT_H1_ZONE", "plans": [{
        "side": "BUY", "entry_zone": {"low": 1.1, "high": 1.1002},
        "stop_loss": 1.08, "take_profit": [1.1641, 1.1644],
        "risk_reward": [1.5, 2.0],
        "invalidation": {"condition": "H1_CLOSE_BELOW_STRUCTURE", "value": 1.07},
    }]}
    table = h1plan.render_public_table(plan)
    assert table.count("≈1.164") == 2


def test_neutral_plan_fails_closed_when_either_leg_has_no_structure():
    source = _buy_fixture()
    for index, row in enumerate(source):
        row["high"] = 2.0 + index * 0.01
    with pytest.raises(h1plan.H1PlanHold):
        h1plan.build_h1_plan(
            "eurusd", None, source, [],
            decision_at=datetime(2026, 9, 5, tzinfo=timezone.utc), atr14=0.01)


def test_visual_contract_has_context_and_zoom_with_canonical_y():
    plan = h1plan.build_h1_plan(
        "eurusd", "up", _buy_fixture(), [],
        decision_at=datetime(2026, 9, 5, 0, tzinfo=timezone.utc), atr14=0.010)
    visual = h1plan.resolve_h1_visual_contract(plan)
    assert [panel["role"] for panel in visual["panels"]] == ["H1_CONTEXT", "H1_EXECUTION_ZOOM"]
    assert visual["panels"][0]["bars"] == 120
    assert visual["panels"][1]["bars"] == 48
    for spec in visual["panels"][1]["specs"]:
        assert isinstance(spec["value"], float)
        assert spec["text"].split()[-1].count(".") == 1
        assert len(spec["text"].split()[-1].split(".")[-1]) == 3


def _buy_fixture():
    # Latest confirmed swing low at index 8, opposing highs provide >=1.5R/2R.
    closes = [1.03, 1.04, 1.05, 1.04, 1.03, 1.02, 1.015, 1.01,
              1.001, 1.012, 1.018, 1.025, 1.03, 1.035, 1.04, 1.045,
              1.05, 1.055, 1.06, 1.065, 1.07, 1.075, 1.08, 1.085]
    values = []
    for index, close in enumerate(closes):
        low = close - 0.003
        high = close + 0.003
        if index == 8:
            low = 1.0
        if index == 2:
            high = 1.08
        if index == 16:
            high = 1.10
        if index == 19:
            high = 1.13
        values.append((low, high, close))
    return bars(values)
