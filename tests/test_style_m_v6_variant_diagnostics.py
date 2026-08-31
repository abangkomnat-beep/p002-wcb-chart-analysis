from tools import style_m_v6_variant_diagnostics as variants
from tools import style_m_v6_walkforward as walk


def _plan(side: str, state="WAIT_TRIGGER"):
    if side == "LONG":
        return {"side": side, "state": state, "trigger": 100.0,
                "entry_low": 100.0, "entry_high": 102.0, "sl": 99.0,
                "tp1": 105.0, "tp2": 107.0, "rr1": 1.5, "rr2": 2.0,
                "risk": 3.0}
    return {"side": side, "state": state, "trigger": 90.0,
            "entry_low": 88.0, "entry_high": 90.0, "sl": 91.0,
            "tp1": 85.0, "tp2": 83.0, "rr1": 1.5, "rr2": 2.0,
            "risk": 3.0}


def _story(adx=30.0):
    return {"indicators": {"adx14": adx},
            "scenarios": {"long": _plan("LONG", "TRIGGERED_WAIT_RETEST"),
                          "short": _plan("SHORT")}}


def _bar(hour, low=100.5, high=101.5, close=101.0):
    return {"at": f"2026-01-02 {hour:02d}:00:00", "open": close,
            "low": low, "high": high, "close": close}


def test_adx_is_strength_filter_not_direction_gate():
    variant = variants.Variant("filter", 25.0, "zone_touch", "worst_boundary", 24, "test")
    result = variants.simulate_variant(_story(adx=24.9), [_bar(11)] * 24, variant,
                                       execution_costs=walk.DEFAULT_EXECUTION_COSTS)
    assert result["status"] == "FILTERED_ADX"


def test_reclaim_quality_requires_close_back_through_trigger():
    plan = _plan("LONG")
    assert not variants._quality_ok(plan, _bar(11, low=100.5, high=101.5, close=100.0),
                                    "reclaim_trigger_close")
    assert variants._quality_ok(plan, _bar(11, low=100.5, high=101.5, close=100.1),
                                "reclaim_trigger_close")


def test_trigger_limit_uses_trigger_boundary_and_recalculates_risk():
    plan, entry = variants._entry_plan(_plan("LONG"), "trigger_limit")
    assert entry["fill"] == 100.0
    assert entry["basis"] == "trigger_boundary_limit"
    assert plan["risk"] == 1.0
    assert plan["rr1"] == 5.0
