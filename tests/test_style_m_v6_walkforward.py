from datetime import datetime, timedelta

from tools import style_m_v6_story, style_m_v6_walkforward as walk


def _plan(side: str, *, state: str = "WAIT_TRIGGER") -> dict:
    if side == "LONG":
        return {"side": side, "state": state, "trigger": 100.0,
                "entry_low": 100.0, "entry_high": 102.0, "sl": 99.0,
                "tp1": 105.0, "tp2": 107.0, "rr1": 1.5, "rr2": 2.0,
                "risk": 3.0}
    return {"side": side, "state": state, "trigger": 90.0,
            "entry_low": 88.0, "entry_high": 90.0, "sl": 91.0,
            "tp1": 85.0, "tp2": 83.0, "rr1": 1.5, "rr2": 2.0,
            "risk": 3.0}


def _story(*, long_state="WAIT_TRIGGER", short_state="WAIT_TRIGGER") -> dict:
    return {"scenarios": {"long": _plan("LONG", state=long_state),
                          "short": _plan("SHORT", state=short_state)}}


def _bar(hour: int, *, low=100.5, high=101.5, close=101.0) -> dict:
    return {"at": f"2026-01-02 {hour:02d}:00:00", "open": close,
            "low": low, "high": high, "close": close}


def test_signal_bar_trigger_is_accepted_and_retest_waits_for_next_bar():
    result = walk.simulate(_story(long_state="TRIGGERED_WAIT_RETEST"),
                           [_bar(11), *[_bar(hour) for hour in range(12, 35)]])
    assert result["triggered_side"] == "long"
    assert result["lifecycle"]["triggered"] == 1
    assert result["entry"]["at"] == "2026-01-02 11:00:00"
    assert result["scenario_states"]["short"] == "CANCELLED_OPPOSITE_TRIGGER"


def test_retest_bar_stop_and_target_is_conservative_stop():
    result = walk.simulate(_story(long_state="TRIGGERED_WAIT_RETEST"),
                           [_bar(11, low=98.0, high=106.0, close=101.0),
                            *[_bar(hour) for hour in range(12, 35)]])
    exit_result = result["exit_models"]["tp1_all_in"]
    assert exit_result["outcome"] == "STOP_AMBIGUOUS_BAR"
    assert exit_result["r"] == -1.0
    assert exit_result["after_cost_r"] < -1.0


def test_default_cost_config_is_explicit_and_reduces_realized_r():
    costs = walk.load_execution_costs()
    assert costs == walk.DEFAULT_EXECUTION_COSTS
    cost_r, detail = walk._cost_r(_plan("LONG"), {"fill": 102.0}, costs)
    assert detail["round_trip_bps"] == 24.0
    assert cost_r > 0


def test_evaluate_uses_11_bangkok_cutoff():
    start = datetime(2026, 1, 1, tzinfo=style_m_v6_story.BANGKOK)
    rows = []
    for index in range(120):
        price = 100.0 + (index % 7) * 0.2
        rows.append({"at": (start + timedelta(hours=index)).strftime("%Y-%m-%d %H:%M:%S"),
                     "open": price, "high": price + 1.0, "low": price - 1.0,
                     "close": price + 0.1})
    report = walk.evaluate(rows, source_label="fixture", source_meta={}, days=1,
                           in_sample_days=0)
    assert report["records"][0]["cutoff"].endswith("T11:00:00+07:00")
    assert report["methodology"]["decision_clock"].startswith("one plan at Bangkok 11:00")
