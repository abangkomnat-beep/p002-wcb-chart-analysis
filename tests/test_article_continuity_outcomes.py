from copy import deepcopy
from datetime import datetime, timedelta

from tools.article_continuity_outcomes import evaluate, UNRESOLVED


def candle(hour, close=105, low=101, high=108, minutes=60):
    return {"at": (datetime(2026, 9, 1) + timedelta(minutes=hour * minutes)).isoformat(),
            "open": close, "close": close, "low": low, "high": high}


def m():
    return {"story": {"contract_version": "M-PROD/v7", "state": "SCENARIOS_READY",
        "cutoff": "2026-09-01T00:00:00+07:00", "valid_until": "2026-09-02T00:00:00+07:00",
        "latest": {"close": 100}, "false_breakout": {
            "bull_trap": "next_closed_h1_below_short_trigger",
            "bear_trap": "next_closed_h1_above_long_trigger",
            "no_retest_tp1": "cancel_if_tp1_reached_before_retest"},
        "scenarios": {
            "long": {"side": "LONG", "state": "WAIT_TRIGGER", "trigger_rule": "closed_h1_strict_cross",
                     "trigger": 110, "entry_low": 108, "entry_high": 110, "sl": 100, "tp1": 120, "tp2": 130},
            "short": {"side": "SHORT", "state": "WAIT_TRIGGER", "trigger_rule": "closed_h1_strict_cross",
                      "trigger": 90, "entry_low": 90, "entry_high": 92, "sl": 100, "tp1": 80, "tp2": 70}}}}


def test_m_trigger_bar_is_not_retest_and_oco_never_switches():
    rows = [candle(0, 111, 108, 112)]
    result = evaluate(m(), {"rows": rows}, "2026-09-01T01:00:00+07:00")
    assert "ยังไม่พบการกลับทดสอบ" in result
    rows.append(candle(1, 89, 88, 99))
    assert "ยกเลิก" in evaluate(m(), {"rows": rows}, "2026-09-01T02:00:00+07:00")


def test_m_retest_then_target_is_observation_not_fill():
    rows = [candle(0, 111, 108, 112), candle(1, 111, 109, 112), candle(2, 120, 111, 121)]
    assert "ถึงระดับเป้าหมายแรก" in evaluate(m(), {"rows": rows}, "2026-09-01T03:00:00+07:00")
    rows[1] = candle(1, 115, 109, 121)
    assert evaluate(m(), {"rows": rows}, "2026-09-01T03:00:00+07:00") == UNRESOLVED


def test_m_target_before_retest_cancels():
    rows = [candle(0, 111, 108, 112), candle(1, 120, 112, 121)]
    assert "ก่อนพบการกลับทดสอบ" in evaluate(m(), {"rows": rows}, "2026-09-01T02:00:00+07:00")


def test_m_next_bar_trap_does_not_apply_to_later_bars():
    previous = m()
    previous["story"]["scenarios"]["long"]["sl"] = 80
    trigger = candle(0, 111, 111, 112)
    immediate = [trigger, candle(1, 89, 88, 89)]
    assert "กรอบอีกฝั่ง" in evaluate(previous, {"rows": immediate}, "2026-09-01T02:00:00+07:00")
    later = [trigger, candle(1, 112, 111, 113), candle(2, 89, 88, 89)]
    assert "ยังไม่พบการกลับทดสอบ" in evaluate(previous, {"rows": later}, "2026-09-01T03:00:00+07:00")


def test_gaps_nan_forming_and_future_bar_cannot_support_claim():
    rows = [candle(0), candle(2)]
    assert evaluate(m(), {"rows": rows}, "2026-09-01T03:00:00+07:00") is None
    rows = [candle(0)]
    rows[0]["high"] = float("nan")
    assert evaluate(m(), {"rows": rows}, "2026-09-01T01:00:00+07:00") is None
    rows = [candle(0), {**candle(1), "forming": True}]
    assert evaluate(m(), {"rows": rows}, "2026-09-01T02:00:00+07:00") is None
    assert "ยังไม่มีฝั่งใด" in evaluate(m(), {"rows": rows}, "2026-09-01T01:00:00+07:00")


def test_expiry_caps_observation_and_contract_change_withholds():
    previous = m()
    previous["story"]["valid_until"] = "2026-09-01T01:00:00+07:00"
    rows = [candle(0), candle(1, 111, 108, 112)]
    assert "ครบกำหนด" in evaluate(previous, {"rows": rows}, "2026-09-01T02:00:00+07:00")
    previous["story"]["scenarios"]["long"]["trigger_rule"] = "unknown"
    assert evaluate(previous, {"rows": rows}, "2026-09-01T02:00:00+07:00") is None


def l():
    return {"scenario": {"cutoff_at": "2026-09-01T00:00:00+07:00",
        "valid_until": "2026-09-02T00:00:00+07:00", "status": "WAIT_TRIGGER", "side": "BUY", "current_close": 100,
        "plans": [{"side": "BUY", "trigger": {"condition": "M15_CLOSE_ABOVE", "value": 110},
                   "stop_loss": 100, "take_profit": [120, 130],
                   "invalidation": {"condition": "H1_CLOSE_BELOW", "value": 95}}]}}


def test_l_strict_cross_and_invalidation_timeframe():
    previous = l()
    rows = [candle(0, 110, 105, 111, 15)]
    assert "ยังไม่ยืนยัน" in evaluate(previous, {"rows": {"15min": rows, "1h": []}}, "2026-09-01T00:15:00+07:00")
    rows.append(candle(1, 111, 109, 112, 15))
    assert "ยืนยันแล้ว" in evaluate(previous, {"rows": {"15min": rows, "1h": []}}, "2026-09-01T00:30:00+07:00")
    rows.append(candle(2, 94, 93, 99, 15))
    result = evaluate(previous, {"rows": {"15min": rows, "1h": []}}, "2026-09-01T00:45:00+07:00")
    assert "สัมผัสระดับหยุด" in result and "ยืนยันเงื่อนไขยกเลิก" not in result


def test_l_h1_invalidation_before_trigger():
    rows = [candle(i, 94, 93, 99, 15) for i in range(4)]
    assert "ก่อนเกิดสัญญาณ" in evaluate(l(), {"rows": {"15min": rows, "1h": [candle(0, 94, 93, 99)]}}, "2026-09-01T01:00:00+07:00")


def test_e_only_known_canonical_rule_and_ambiguous_stop_target():
    previous = {"plan": deepcopy(l()["scenario"])}
    leg = previous["plan"]["plans"][0]
    leg["trigger"]["condition"] = "closed H1 strict cross from latest closed close"
    leg["invalidation"] = {"condition": "closed H1 reaches canonical SL", "value": 100}
    rows = [candle(0, 111, 105, 112), candle(1, 115, 99, 121)]
    assert evaluate(previous, {"rows": rows}, "2026-09-01T02:00:00+07:00") == UNRESOLVED
    leg["trigger"]["condition"] = "unknown confirmation"
    assert evaluate(previous, {"rows": rows}, "2026-09-01T02:00:00+07:00") is None


def test_l_oco_keeps_first_leg_and_never_triggers_opposite_afterwards():
    previous = l()
    previous["scenario"]["side"] = "OCO"
    previous["scenario"]["plans"].append({
        "side": "SELL", "trigger": {"condition": "M15_CLOSE_BELOW", "value": 90},
        "stop_loss": 100, "take_profit": [80, 70],
        "invalidation": {"condition": "H1_CLOSE_ABOVE", "value": 105}})
    rows = [candle(0, 111, 109, 112, 15), candle(1, 79, 78, 99, 15)]
    result = evaluate(previous, {"rows": {"15min": rows, "1h": []}}, "2026-09-01T00:30:00+07:00")
    assert "สัมผัสระดับหยุด" in result and "เป้าหมาย" not in result


def test_l_partial_hour_still_requires_h1_close_for_invalidation():
    previous = l()
    previous["scenario"]["cutoff_at"] = "2026-09-01T00:35:00+07:00"
    rows = [candle(2, 94, 93, 99, 15), candle(3, 94, 93, 99, 15)]
    current = {"rows": {"15min": rows, "1h": [candle(0, 94, 93, 99)]}}
    assert "ก่อนเกิดสัญญาณ" in evaluate(previous, current, "2026-09-01T01:00:00+07:00")
    current["rows"]["1h"] = []
    assert evaluate(previous, current, "2026-09-01T01:00:00+07:00") is None
