"""Eligibility contracts for J, I, E-logic and F; H remains evidence only."""
from __future__ import annotations

import pytest

from fixtures.fplus.contract_support import require_module


RISK_PASS = {"eligible": True, "reason_codes": [], "rr_worst_edge": 1.5,
             "stop_atr": 1.1, "entry_distance_atr": 0.5}


def evaluate(name: str, **evidence):
    candidates = require_module("tools.fplus_candidates")
    return candidates.evaluate_candidate(name, evidence=evidence, risk_result=RISK_PASS)


@pytest.mark.parametrize("state", ["PULLBACK_CONFIRMED", "TREND_RESUMED"])
def test_j_only_accepts_executable_states_with_aligned_closed_trigger(state):
    result = evaluate("J", state=state, h4_bias="up", h1_bias="up",
                      m30_bias="up", m15_confirmed=True, invalidated=False)
    assert result["candidate"] == "J"
    assert result["eligible"] is True


@pytest.mark.parametrize("state", ["M30_BULL_CONTEXT", "PULLBACK_FORMING", "PULLBACK_FAILED", "NO_M30_BIAS"])
def test_j_non_executable_states_fail(state):
    assert evaluate("J", state=state, h4_bias="up", h1_bias="up",
                    m30_bias="up", m15_confirmed=True, invalidated=False)["eligible"] is False


@pytest.mark.parametrize("state", ["BREAKOUT_UP", "BREAKOUT_DOWN"])
def test_i_only_accepts_confirmed_breakouts(state):
    direction = "up" if state.endswith("UP") else "down"
    result = evaluate("I", state=state, direction=direction, h4_bias=direction,
                      m30_classifier=direction, donchian_confirmed=True,
                      true_range_confirmed=True, bbw_expanding=True)
    assert result["eligible"] is True


@pytest.mark.parametrize("state", ["ARMED", "COMPRESSION", "EXPANSION", "NORMAL", "FAILED_BREAKOUT_UP"])
def test_i_non_executable_states_fail(state):
    assert evaluate("I", state=state, direction="up", h4_bias="up",
                    m30_classifier="up", donchian_confirmed=True,
                    true_range_confirmed=True, bbw_expanding=True)["eligible"] is False


def test_e_logic_requires_follow_trend_golden_zone_and_m15_rejection():
    passed = evaluate("E_LOGIC", scenario="follow_trend", daily_entry=True,
                      h4_bias="up", h1_bias="up", fibonacci_swing_valid=True,
                      in_golden_zone=True, m15_rejection=True,
                      rsi_conflicts=False, macd_conflicts=False)
    assert passed["eligible"] is True
    for changed in (
        {"scenario": "counter_trend"}, {"fibonacci_swing_valid": False},
        {"in_golden_zone": False}, {"m15_rejection": False},
    ):
        base = dict(scenario="follow_trend", daily_entry=True, h4_bias="up",
                    h1_bias="up", fibonacci_swing_valid=True, in_golden_zone=True,
                    m15_rejection=True, rsi_conflicts=False, macd_conflicts=False)
        base.update(changed)
        assert evaluate("E_LOGIC", **base)["eligible"] is False


def test_f_requires_range_classifier_and_one_confirmed_edge():
    passed = evaluate("F", h_classifier="NO_TREND", h1_range_valid=True,
                      price_location="lower_edge", m15_rejection=True,
                      ambiguous_edges=False, inside_range=True)
    assert passed["eligible"] is True
    assert passed["direction"] == "long"
    for location in ("middle", "outside", "ambiguous"):
        result = evaluate("F", h_classifier="NO_TREND", h1_range_valid=True,
                          price_location=location, m15_rejection=True,
                          ambiguous_edges=location == "ambiguous", inside_range=location != "outside")
        assert result["eligible"] is False


def test_h_cannot_be_evaluated_as_candidate():
    candidates = require_module("tools.fplus_candidates")
    with pytest.raises(candidates.CandidateContractError, match="H|candidate"):
        candidates.evaluate_candidate("H", evidence={}, risk_result=RISK_PASS)

