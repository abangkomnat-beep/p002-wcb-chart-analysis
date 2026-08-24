"""Pure eligibility adapters for the four BTCUSD F+ candidates."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


class CandidateContractError(ValueError):
    """Raised when a non-candidate or malformed evidence is requested."""


ORDER = ("J", "I", "E_LOGIC", "F")


def _direction(value: Any) -> str:
    normalized = str(value or "").lower()
    if normalized in {"up", "bullish", "long", "ขาขึ้น"}:
        return "long"
    if normalized in {"down", "bearish", "short", "ขาลง"}:
        return "short"
    return "neutral"


def evaluate_candidate(
    name: str, *, evidence: Mapping[str, Any], risk_result: Mapping[str, Any],
) -> dict[str, Any]:
    if name not in ORDER:
        raise CandidateContractError(f"{name!r} is not an F+ candidate; H is evidence only")
    if not isinstance(evidence, Mapping) or not isinstance(risk_result, Mapping):
        raise CandidateContractError("candidate evidence and risk result must be mappings")
    ev = deepcopy(dict(evidence))
    reasons: list[str] = []
    eligible = True
    direction = "neutral"

    if name == "J":
        eligible &= ev.get("state") in {"PULLBACK_CONFIRMED", "TREND_RESUMED"}
        aligned = ev.get("h4_bias") == ev.get("h1_bias") == ev.get("m30_bias")
        eligible &= aligned and bool(ev.get("m15_confirmed")) and not bool(ev.get("invalidated"))
        direction = _direction(ev.get("h4_bias"))
        eligible &= direction != "neutral"
        if not eligible:
            reasons.append("J_CONTRACT_NOT_CONFIRMED")
    elif name == "I":
        state = ev.get("state")
        expected = "up" if state == "BREAKOUT_UP" else "down" if state == "BREAKOUT_DOWN" else None
        eligible &= expected is not None
        direction = _direction(expected)
        eligible &= str(ev.get("direction", "")).lower() == expected
        eligible &= str(ev.get("h4_bias", "")).lower() == expected
        classifier = str(ev.get("m30_classifier", "")).lower()
        eligible &= classifier in {expected, "no_trend", "transition"}
        eligible &= all(bool(ev.get(key)) for key in (
            "donchian_confirmed", "true_range_confirmed", "bbw_expanding"
        ))
        if not eligible:
            reasons.append("I_BREAKOUT_NOT_CONFIRMED")
    elif name == "E_LOGIC":
        aligned = ev.get("h4_bias") == ev.get("h1_bias")
        direction = _direction(ev.get("h4_bias"))
        eligible &= ev.get("scenario") == "follow_trend" and bool(ev.get("daily_entry"))
        eligible &= aligned and direction != "neutral"
        eligible &= bool(ev.get("fibonacci_swing_valid")) and bool(ev.get("in_golden_zone"))
        eligible &= bool(ev.get("m15_rejection"))
        eligible &= not (bool(ev.get("rsi_conflicts")) and bool(ev.get("macd_conflicts")))
        if not eligible:
            reasons.append("E_LOGIC_NOT_CONFIRMED")
    else:
        classifier = str(ev.get("h_classifier", "")).upper()
        location = str(ev.get("price_location", "")).lower()
        eligible &= classifier in {"NO_TREND", "TRANSITION"}
        eligible &= bool(ev.get("h1_range_valid")) and bool(ev.get("inside_range"))
        eligible &= bool(ev.get("m15_rejection")) and not bool(ev.get("ambiguous_edges"))
        eligible &= location in {"lower_edge", "upper_edge"}
        direction = "long" if location == "lower_edge" else "short" if location == "upper_edge" else "neutral"
        if not eligible:
            reasons.append("F_RANGE_EDGE_NOT_CONFIRMED")

    risk_eligible = bool(risk_result.get("eligible", False))
    if not risk_eligible:
        reasons.extend(str(code) for code in risk_result.get("reason_codes", ["RISK_GATE_FAILED"]))
    eligible = bool(eligible and risk_eligible)
    result = {
        "candidate": name,
        "eligible": eligible,
        "state": str(ev.get("state", ev.get("scenario", "evaluated"))),
        "direction": direction if eligible else "neutral",
        "setup_id": ev.get("setup_id") if eligible else None,
        "entry_zone": deepcopy(ev.get("entry_zone")) if eligible else None,
        "stop_loss": ev.get("stop_loss") if eligible else None,
        "take_profit_1": ev.get("take_profit_1") if eligible else None,
        "rr_worst_edge": risk_result.get("rr_worst_edge") if eligible else None,
        "stop_atr": risk_result.get("stop_atr") if eligible else None,
        "entry_distance_atr": risk_result.get("entry_distance_atr") if eligible else None,
        "gate_results": {"candidate": eligible, "risk": risk_eligible},
        "reason_codes": reasons,
        "evidence_refs": list(ev.get("evidence_refs", [])),
    }
    return result
