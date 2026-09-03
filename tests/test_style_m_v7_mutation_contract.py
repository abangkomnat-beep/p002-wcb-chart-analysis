"""Required ADR14 mutation probes; every frozen-semantic mutant is killed."""
from copy import deepcopy
from unittest import mock

import pytest

from tools import style_m_v7_risk as risk
from tests.test_style_m_v7_adr14 import cutoff, rows_fixture
from tools import style_m_v7_story as story


def _story():
    built = story.build(rows_fixture(), cutoff=cutoff(), source_label="mutation")
    built["story"]["pivots"] = {"lows": [{"price": 1100}], "highs": [{"price": 930}]}
    return built["story"]


def test_frozen_coefficients_and_directional_rounding_are_contract_constants():
    assert risk.METRIC == "ADR14"
    assert risk.ENTRY_WIDTH_COEFFICIENT == 0.10
    assert risk.RISK_FLOOR_COEFFICIENT == 0.50
    assert risk.RISK_CAP_COEFFICIENT == 1.00
    assert risk.TP1_R == 1.50 and risk.TP2_R == 2.00
    result = risk.apply_policy(_story(), volatility=risk.adr14(rows_fixture(), cutoff=cutoff()))
    long, short = result["scenarios"].values()
    assert long["entry_high"] - long["entry_low"] >= 0.10 * 230.0
    assert short["entry_high"] - short["entry_low"] >= 0.10 * 230.0


def test_structural_risk_wins_over_floor_and_cap_is_strict():
    vol = {"metric": "ADR14", "value": 200.0, "length": 14,
           "last_closed_date": "2026-08-29",
           "basis": "completed_bangkok_calendar_days_before_cutoff"}
    s = _story()
    s["pivots"] = {"lows": [{"price": 1000}], "highs": [{"price": 1040}]}
    result = risk.apply_policy(s, volatility=vol)
    assert result["scenarios"]["long"]["risk_geometry"]["final_risk"] > 0.5 * 200
    over = deepcopy(s)
    over["pivots"] = {"lows": [{"price": 800}], "highs": [{"price": 1250}]}
    capped = risk.apply_policy(over, volatility=vol)
    assert all(p["state"] == "NO_PLAN" and p["no_plan_reason"] == "FINAL_RISK_EXCEEDS_ADR14_CAP"
               for p in capped["scenarios"].values())


def test_adverse_edge_is_the_rr_reference_for_both_directions():
    result = risk.apply_policy(_story(), volatility={"metric": "ADR14", "value": 400.0,
        "length": 14, "last_closed_date": "2026-08-29",
        "basis": "completed_bangkok_calendar_days_before_cutoff"})
    for plan in result["scenarios"].values():
        edge = plan["entry_high"] if plan["side"] == "LONG" else plan["entry_low"]
        reward = (plan["tp1"] - edge) if plan["side"] == "LONG" else (edge - plan["tp1"])
        assert reward / plan["risk"] >= 1.5


def test_runtime_legacy_h1_risk_spy_is_never_called():
    # Production v7 is isolated from the historical research module; this
    # spy makes an accidental fallback fail immediately.
    from tools import style_m_v6_risk
    with mock.patch.object(style_m_v6_risk, "apply_policy", side_effect=AssertionError("legacy called")):
        result = risk.apply_policy(_story(), volatility={"metric": "ADR14", "value": 400.0,
            "length": 14, "last_closed_date": "2026-08-29",
            "basis": "completed_bangkok_calendar_days_before_cutoff"})
    assert result["risk_geometry"]["policy_id"] == risk.POLICY_ID
