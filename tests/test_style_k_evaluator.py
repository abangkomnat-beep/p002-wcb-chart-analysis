"""เทสชั้นวัดผล — จุดที่ผิดแล้วรายงานเปรียบเทียบจะโกหกโดยไม่มีใครจับได้

สามเรื่องที่ชุดนี้กันตรง ๆ: ลำดับเหตุการณ์ที่เดาไม่ได้ต้องไม่ถูกเดา · ไม่ trigger
ต้องไม่กลายเป็นศูนย์ · และ MFE/MAE ต้องไม่ติดลบตามนิยาม
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import style_k_evaluator as ev  # noqa: E402


def scenario(bias="bullish", *, confirm=110.0, invalidate=90.0, reference=100.0,
             target=None) -> dict:
    return {
        "scenario_id": "A", "bias": bias,
        "confirmation_rule": {"measure": "close", "comparison": "gt" if bias == "bullish" else "lt",
                              "level": confirm, "level_label": "ระดับยืนยัน",
                              "level_evidence_id": "E1"},
        "invalidation_rule": {"measure": "close", "comparison": "lt" if bias == "bullish" else "gt",
                              "level": invalidate, "level_label": "ระดับหักล้าง",
                              "level_evidence_id": "E2"},
        "evaluation_reference_price": reference,
        "target_zone": target,
    }


def bar(date, *, open_, high, low, close) -> dict:
    return {"date": date, "open": open_, "high": high, "low": low, "close": close}


def test_confirmation_before_invalidation_is_confirmed_then_held():
    rows = [bar("2026-08-11", open_=100, high=112, low=99, close=111)]
    result = ev.evaluate_scenario(scenario(), rows, horizon="H+1", atr14=10.0)
    assert result["first_event"] == "confirmation"
    assert result["scenario_status"] == ev.STATUS_CONFIRMED_HELD
    assert result["confirmation_triggered"] is True


def test_invalidation_before_confirmation_is_invalidated_first():
    rows = [bar("2026-08-11", open_=100, high=101, low=85, close=88)]
    result = ev.evaluate_scenario(scenario(), rows, horizon="H+1", atr14=10.0)
    assert result["first_event"] == "invalidation"
    assert result["scenario_status"] == ev.STATUS_INVALIDATED_FIRST


def test_same_bar_touching_both_sides_is_ambiguous_not_a_guess():
    """แท่งเดียวปิดยืนยัน แต่ระหว่างวันเคยแตะระดับหักล้าง = ไม่ตัดสิน"""
    rows = [bar("2026-08-11", open_=100, high=112, low=88, close=111)]
    result = ev.evaluate_scenario(scenario(), rows, horizon="H+1", atr14=10.0)
    assert result["first_event"] == "ambiguous_same_bar"
    assert result["scenario_status"] == ev.STATUS_AMBIGUOUS
    assert result["confirmation_triggered"] and result["invalidation_triggered"]
    assert result["limitations"], "กรณีกำกวมต้องบันทึกเหตุผลไว้เสมอ"


def test_no_trigger_gives_not_applicable_not_zero():
    rows = [bar("2026-08-11", open_=100, high=105, low=96, close=101)]
    result = ev.evaluate_scenario(scenario(), rows, horizon="H+1", atr14=10.0)
    assert result["first_event"] == "neither"
    assert result["mfe"] == ev.NOT_APPLICABLE and result["mae"] == ev.NOT_APPLICABLE
    assert result["scenario_status"] == ev.STATUS_UNRESOLVED


def test_excursions_are_never_negative():
    """ราคาที่ไม่เคยวิ่งเข้าทางเลย = ระยะเข้าทางศูนย์ ไม่ใช่ค่าติดลบ"""
    rows = [bar("2026-08-11", open_=100, high=130, low=125, close=128)]
    result = ev.evaluate_scenario(scenario("bearish", confirm=90.0, invalidate=110.0),
                                  rows, horizon="H+1", atr14=10.0)
    assert result["first_event"] == "invalidation"
    assert result["mfe"] >= 0 and result["mae"] >= 0


def test_confirmed_then_invalidated_is_tracked_across_bars():
    rows = [bar("2026-08-11", open_=100, high=112, low=99, close=111),
            bar("2026-08-12", open_=111, high=112, low=85, close=87)]
    result = ev.evaluate_scenario(scenario(), rows, horizon="H+3", atr14=10.0)
    assert result["scenario_status"] == ev.STATUS_CONFIRMED_INVALIDATED
    assert result["confirmation_triggered"] and result["invalidation_triggered"]


def test_empty_horizon_reports_not_available():
    result = ev.evaluate_scenario(scenario(), [], horizon="H+3", atr14=10.0)
    assert result["scenario_status"] == ev.STATUS_UNRESOLVED
    assert any("not_available" in item for item in result["limitations"])


def test_atr_normalization_makes_assets_comparable():
    rows = [bar("2026-08-11", open_=100, high=112, low=99, close=111)]
    result = ev.evaluate_scenario(scenario(), rows, horizon="H+1", atr14=10.0)
    assert result["mfe_atr"] == result["mfe"] / 10.0
    without = ev.evaluate_scenario(scenario(), rows, horizon="H+1", atr14=None)
    assert without["mfe_atr"] is None and without["limitations"]


def test_target_not_defined_stays_not_defined():
    rows = [bar("2026-08-11", open_=100, high=112, low=99, close=111)]
    result = ev.evaluate_scenario(scenario(), rows, horizon="H+1", atr14=10.0)
    assert result["target_reached"] == "not_defined"
