"""Exhaustive strict-priority router contract: J → I → E_LOGIC → F → No-trade."""
from __future__ import annotations

from itertools import product

import pytest

from fixtures.fplus.contract_support import load_json, require_module


ORDER = ("J", "I", "E_LOGIC", "F")


def decisions(eligible: set[str]) -> list[dict]:
    return [{
        "candidate": name,
        "eligible": name in eligible,
        "state": "fixture",
        "direction": "long" if name in eligible else "neutral",
        "setup_id": f"{name}-fixture" if name in eligible else None,
        "entry_zone": {"low": 100.0, "high": 101.0} if name in eligible else None,
        "stop_loss": 96.0 if name in eligible else None,
        "take_profit_1": 107.0 if name in eligible else None,
        "rr_worst_edge": 1.2 if name in eligible else None,
        "stop_atr": 1.0 if name in eligible else None,
        "entry_distance_atr": 0.25 if name in eligible else None,
        "gate_results": {},
        "reason_codes": [] if name in eligible else [f"{name}_NOT_ELIGIBLE"],
        "evidence_refs": [f"evidence:{name}"],
    } for name in ORDER]


PASS_GATES = {"price_data_status": "pass", "news": "pass", "reason_codes": []}


@pytest.mark.parametrize("case", load_json("router_cases.json"))
def test_declared_router_cases_follow_strict_order(case):
    router = require_module("tools.fplus_router")
    selected = router.route(decisions(set(case["eligible"])), gate_report=PASS_GATES)
    assert selected["selection"] == case["expected"]


@pytest.mark.parametrize("bits", list(product([False, True], repeat=4)))
def test_exhaustive_truth_table_selects_first_eligible(bits):
    router = require_module("tools.fplus_router")
    eligible = {name for name, passed in zip(ORDER, bits) if passed}
    expected = next((name for name in ORDER if name in eligible), "NO_TRADE")
    selected = router.route(decisions(eligible), gate_report=PASS_GATES)
    assert selected["selection"] == expected
    assert selected["selection"] != "H"


def test_router_evaluates_and_preserves_all_four_candidate_decisions():
    router = require_module("tools.fplus_router")
    result = router.route(decisions({"J", "I", "F"}), gate_report=PASS_GATES)
    assert [item["candidate"] for item in result["candidate_decisions"]] == list(ORDER)
    assert result["selection"] == "J"


@pytest.mark.parametrize("news_status,reason", [
    ("blackout", "HIGH_USD_BLACKOUT"),
    ("unproven", "NEWS_GATE_UNPROVEN"),
])
def test_news_gate_forces_no_trade_even_when_candidates_pass(news_status, reason):
    router = require_module("tools.fplus_router")
    result = router.route(decisions(set(ORDER)), gate_report={
        "price_data_status": "pass", "news": news_status, "reason_codes": [reason],
    })
    assert result["selection"] == "NO_TRADE"
    assert reason in result["reason_codes"]
    assert result["entry_zone"] is None


def test_price_data_failure_is_blocked_retryable_not_no_trade():
    router = require_module("tools.fplus_router")
    result = router.route(decisions(set()), gate_report={
        "price_data_status": "blocked_retryable", "news": "unproven",
        "reason_codes": ["STALE_15MIN"],
    })
    assert result["status"] == "blocked_retryable"
    assert result.get("selection") is None

