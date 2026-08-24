"""Deterministic strict-priority router for BTCUSD F+."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping


ORDER = ("J", "I", "E_LOGIC", "F")


def _no_trade(reason_codes: list[str], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "no_trade",
        "selection": "NO_TRADE",
        "direction": "neutral",
        "entry_zone": None,
        "stop_loss": None,
        "take_profit_1": None,
        "rr": None,
        "reason_codes": reason_codes or ["NO_ELIGIBLE_CANDIDATE"],
        "source_candidate_id": None,
        "candidate_decisions": candidates,
    }


def route(
    candidate_decisions: Iterable[Mapping[str, Any]], *, gate_report: Mapping[str, Any],
) -> dict[str, Any]:
    candidates = [deepcopy(dict(item)) for item in candidate_decisions]
    by_name = {item.get("candidate"): item for item in candidates}
    if set(by_name) != set(ORDER) or len(candidates) != len(ORDER):
        raise ValueError("router requires exactly J, I, E_LOGIC and F decisions")
    candidates = [by_name[name] for name in ORDER]
    gate_reasons = [str(code) for code in gate_report.get("reason_codes", [])]
    if gate_report.get("price_data_status") != "pass":
        return {
            "status": "blocked_retryable", "selection": None,
            "reason_codes": gate_reasons or ["PRICE_DATA_BLOCKED"],
            "candidate_decisions": candidates,
        }
    news = gate_report.get("news", "pass")
    if isinstance(news, Mapping):
        news_status = news.get("status")
        gate_reasons.extend(str(code) for code in news.get("reason_codes", []))
    else:
        news_status = news
    if news_status in {"blackout", "unproven"}:
        return _no_trade(list(dict.fromkeys(gate_reasons)), candidates)
    for name in ORDER:
        candidate = by_name[name]
        if candidate.get("eligible") is True:
            return {
                "status": "selected",
                "selection": name,
                "direction": candidate.get("direction", "neutral"),
                "entry_zone": deepcopy(candidate.get("entry_zone")),
                "stop_loss": candidate.get("stop_loss"),
                "take_profit_1": candidate.get("take_profit_1"),
                "rr": candidate.get("rr_worst_edge"),
                "reason_codes": list(candidate.get("reason_codes", [])),
                "source_candidate_id": candidate.get("setup_id"),
                "candidate_decisions": candidates,
            }
    reasons = gate_reasons[:]
    for candidate in candidates:
        reasons.extend(str(code) for code in candidate.get("reason_codes", []))
    return _no_trade(list(dict.fromkeys(reasons)), candidates)
