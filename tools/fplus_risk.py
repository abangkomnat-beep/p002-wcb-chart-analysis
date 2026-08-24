"""Locked, candidate-neutral risk gate for BTCUSD F+."""
from __future__ import annotations

import math
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


RISK_PATH = Path(__file__).resolve().parents[1] / "config" / "risk_thresholds.json"


def load_risk_thresholds(path: str | Path | None = None) -> dict[str, Any]:
    """Load the sole risk source and return its byte fingerprint."""
    source = Path(path) if path is not None else RISK_PATH
    try:
        raw = source.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        thresholds = payload["thresholds"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("risk threshold source is unavailable or invalid") from exc
    if set(thresholds) != {"minimum_rr", "minimum_stop_atr", "maximum_entry_atr"}:
        raise ValueError("risk threshold source contains an invalid key set")
    if any(not isinstance(value, (int, float)) or value <= 0 for value in thresholds.values()):
        raise ValueError("risk threshold source contains a non-positive value")
    return {
        "thresholds": dict(thresholds),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "source": str(source.resolve()),
    }


def evaluate_risk(
    *, direction: str, entry_zone: Mapping[str, float], stop_loss: float,
    take_profit_1: float, current_price: float, atr: float,
    thresholds: Mapping[str, float],
) -> dict[str, Any]:
    locked = load_risk_thresholds()
    if dict(thresholds) != locked["thresholds"]:
        raise ValueError("thresholds must come unchanged from config/risk_thresholds.json")
    reasons: list[str] = []
    try:
        low = float(entry_zone["low"])
        high = float(entry_zone["high"])
        stop = float(stop_loss)
        target = float(take_profit_1)
        current = float(current_price)
        atr_value = float(atr)
    except (KeyError, TypeError, ValueError):
        return {"eligible": False, "reason_codes": ["RISK_INPUT_INVALID"]}
    if not all(math.isfinite(value) for value in (low, high, stop, target, current, atr_value)):
        return {"eligible": False, "reason_codes": ["RISK_INPUT_INVALID"]}
    if low > high or atr_value <= 0 or direction not in {"long", "short"}:
        return {"eligible": False, "reason_codes": ["RISK_INPUT_INVALID"]}

    entry_edge = high if direction == "long" else low
    risk = entry_edge - stop if direction == "long" else stop - entry_edge
    reward = target - entry_edge if direction == "long" else entry_edge - target
    if risk <= 0 or reward <= 0:
        reasons.append("NON_POSITIVE_RISK")
        rr = 0.0
        stop_atr = max(risk, 0.0) / atr_value
    else:
        rr = reward / risk
        stop_atr = risk / atr_value
    if current < low:
        entry_distance = low - current
    elif current > high:
        entry_distance = current - high
    else:
        entry_distance = 0.0
    entry_distance_atr = entry_distance / atr_value

    minimum_rr = float(thresholds["minimum_rr"])
    minimum_stop_atr = float(thresholds["minimum_stop_atr"])
    maximum_entry_atr = float(thresholds["maximum_entry_atr"])
    epsilon = 1e-12
    if risk > 0 and reward > 0 and rr + epsilon < minimum_rr:
        reasons.append("RR_BELOW_MINIMUM")
    if stop_atr + epsilon < minimum_stop_atr:
        reasons.append("STOP_BELOW_MINIMUM_ATR")
    if entry_distance_atr - epsilon > maximum_entry_atr:
        reasons.append("ENTRY_TOO_FAR_ATR")
    return {
        "eligible": not reasons,
        "reason_codes": reasons,
        "entry_edge_used": entry_edge,
        "rr_worst_edge": rr,
        "stop_atr": stop_atr,
        "entry_distance_atr": entry_distance_atr,
        "risk": risk,
        "reward": reward,
        "thresholds_fingerprint": locked["sha256"],
    }
