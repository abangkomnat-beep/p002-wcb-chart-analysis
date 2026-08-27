"""Pure Adaptive Stop B100 geometry and canonical M15 decision context.

This production-owned module intentionally has no I/O, network, plotting,
replay, broker, or research-harness dependency.  Story construction and story
validation call the same functions so persisted derived fields cannot be
trusted without recomputation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math


PIVOT_LEFT = 2
PIVOT_RIGHT = 2
PIVOT_LOOKBACK_BARS = 20
STRUCTURE_BUFFER_ATR = 0.25
RISK_FLOOR_ATR = 2.0
RISK_CAP_ATR = 3.0
DONCHIAN_LENGTH = 20
TARGET_SPACE_MIN_R = 1.5
BASELINE_MAX_RISK_ATR = 1.5
TOLERANCE = 1e-12
CONTEXT_COUNT = 23
CONTEXT_SCHEMA = "style-e-plus-adaptive-context/v1"
M15_TIMEFRAME = "15min"
_BANGKOK = timezone(timedelta(hours=7))
_CONTEXT_KEYS = {
    "schema", "timeframe", "candle_state", "count", "window", "rows", "sha256"
}
_ROW_KEYS = {"at", "open", "high", "low", "close"}


class AdaptiveStopError(ValueError):
    """Input cannot satisfy the deterministic B100 contract."""


def _number(value, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise AdaptiveStopError(f"{label}: not numeric") from exc
    if not math.isfinite(result):
        raise AdaptiveStopError(f"{label}: must be finite")
    return result


def _decimal_text(value, label: str) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise AdaptiveStopError(f"{label}: not a canonical decimal") from exc
    if not number.is_finite():
        raise AdaptiveStopError(f"{label}: must be finite")
    if number == 0:
        return "0"
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _utc_text(value, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise AdaptiveStopError(f"{label}: timestamp is empty")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise AdaptiveStopError(f"{label}: invalid timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_BANGKOK)
    parsed = parsed.astimezone(timezone.utc)
    if parsed.microsecond:
        raise AdaptiveStopError(f"{label}: sub-second timestamps are forbidden")
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


def _context_payload(context: dict) -> dict:
    return {key: context[key] for key in
            ("schema", "timeframe", "candle_state", "count", "window", "rows")}


def _context_hash(payload: dict) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_context(rows: list[dict]) -> dict:
    """Return exactly decision-22..decision as canonical, hashed UTC OHLC."""
    if not isinstance(rows, list) or len(rows) < CONTEXT_COUNT:
        raise AdaptiveStopError("M15 decision context requires at least 23 rows")
    canonical = []
    for index, source in enumerate(rows[-CONTEXT_COUNT:]):
        if not isinstance(source, dict):
            raise AdaptiveStopError(f"rows[{index}]: must be an object")
        if source.get("forming") or source.get("candle_state") not in {None, "closed"}:
            raise AdaptiveStopError(f"rows[{index}]: forming candle is forbidden")
        item = {"at": _utc_text(source.get("at"), f"rows[{index}].at")}
        for field in ("open", "high", "low", "close"):
            item[field] = _decimal_text(source.get(field), f"rows[{index}].{field}")
        opened, high, low, closed = (
            _number(item[field], f"rows[{index}].{field}")
            for field in ("open", "high", "low", "close"))
        if high < max(opened, closed) or low > min(opened, closed) or high < low:
            raise AdaptiveStopError(f"rows[{index}]: invalid OHLC geometry")
        canonical.append(item)
    moments = [datetime.fromisoformat(row["at"].replace("Z", "+00:00"))
               for row in canonical]
    for index in range(1, len(moments)):
        if moments[index] - moments[index - 1] != timedelta(minutes=15):
            raise AdaptiveStopError("M15 context must be unique, ascending, and contiguous")
    context = {
        "schema": CONTEXT_SCHEMA,
        "timeframe": M15_TIMEFRAME,
        "candle_state": "closed",
        "count": CONTEXT_COUNT,
        "window": {
            "start_at": canonical[0]["at"],
            "decision_at": canonical[-1]["at"],
        },
        "rows": canonical,
    }
    context["sha256"] = _context_hash(_context_payload(context))
    return context


def canonical_timestamp(value) -> str:
    """Public timestamp normalizer shared by story and renderer boundaries."""
    return _utc_text(value, "timestamp")


def validate_context(context: dict) -> list[dict]:
    """Validate exact encoding/hash and return numeric rows for recomputation."""
    if not isinstance(context, dict) or set(context) != _CONTEXT_KEYS:
        raise AdaptiveStopError("adaptive_context schema is not exact")
    if (context.get("schema") != CONTEXT_SCHEMA
            or context.get("timeframe") != M15_TIMEFRAME
            or context.get("candle_state") != "closed"
            or context.get("count") != CONTEXT_COUNT):
        raise AdaptiveStopError("adaptive_context contract does not match B100")
    rows = context.get("rows")
    window = context.get("window")
    if (not isinstance(rows, list) or len(rows) != CONTEXT_COUNT
            or not isinstance(window, dict)
            or set(window) != {"start_at", "decision_at"}):
        raise AdaptiveStopError("adaptive_context count/window is invalid")
    normalized = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != _ROW_KEYS:
            raise AdaptiveStopError(f"adaptive_context.rows[{index}] schema is invalid")
        canonical_at = _utc_text(row["at"], f"rows[{index}].at")
        if canonical_at != row["at"]:
            raise AdaptiveStopError(f"rows[{index}].at is not canonical UTC")
        item = {"at": canonical_at}
        for field in ("open", "high", "low", "close"):
            if not isinstance(row[field], str):
                raise AdaptiveStopError(f"rows[{index}].{field} must be a decimal string")
            canonical_number = _decimal_text(row[field], f"rows[{index}].{field}")
            if canonical_number != row[field]:
                raise AdaptiveStopError(f"rows[{index}].{field} is not canonical")
            item[field] = _number(canonical_number, f"rows[{index}].{field}")
        if (item["high"] < max(item["open"], item["close"])
                or item["low"] > min(item["open"], item["close"])
                or item["high"] < item["low"]):
            raise AdaptiveStopError(f"rows[{index}]: invalid OHLC geometry")
        normalized.append(item)
    moments = [datetime.fromisoformat(row["at"].replace("Z", "+00:00")) for row in rows]
    if any(moments[index] - moments[index - 1] != timedelta(minutes=15)
           for index in range(1, len(moments))):
        raise AdaptiveStopError("adaptive_context rows are reordered, duplicated, or gapped")
    if window != {"start_at": rows[0]["at"], "decision_at": rows[-1]["at"]}:
        raise AdaptiveStopError("adaptive_context window does not match rows")
    expected_hash = _context_hash(_context_payload(context))
    if context.get("sha256") != expected_hash:
        raise AdaptiveStopError("adaptive_context SHA-256 mismatch")
    return normalized


def confirmed_pivot(rows: list[dict], *, decision_index: int, side: str) -> dict | None:
    """Find latest strict 2-left/2-right pivot in decision-2..decision-20."""
    if side not in {"buy", "sell"}:
        raise AdaptiveStopError("side must be buy or sell")
    if decision_index < 0 or decision_index >= len(rows):
        raise AdaptiveStopError("decision_index outside rows")
    earliest = max(PIVOT_LEFT, decision_index - PIVOT_LOOKBACK_BARS)
    latest = decision_index - PIVOT_RIGHT
    field = "low" if side == "buy" else "high"
    for index in range(latest, earliest - 1, -1):
        value = _number(rows[index].get(field), f"rows[{index}].{field}")
        neighbors = [
            _number(rows[position].get(field), f"rows[{position}].{field}")
            for position in range(index - PIVOT_LEFT, index + PIVOT_RIGHT + 1)
            if position != index
        ]
        is_pivot = (all(value < other for other in neighbors) if side == "buy"
                    else all(value > other for other in neighbors))
        if is_pivot:
            return {"index": index, "price": value,
                    "confirmed_index": index + PIVOT_RIGHT,
                    "left": PIVOT_LEFT, "right": PIVOT_RIGHT}
    return None


def bounded_adaptive_risk(raw_risk: float, *, atr: float) -> dict:
    raw_risk = _number(raw_risk, "raw_risk")
    atr = _number(atr, "atr")
    if raw_risk <= 0 or atr <= 0:
        raise AdaptiveStopError("risk and ATR must be positive")
    raw_atr = raw_risk / atr
    if raw_atr > RISK_CAP_ATR + TOLERANCE:
        return {"accepted": False, "reason": "STOP_GT_3ATR",
                "raw_risk_atr": raw_atr}
    if abs(raw_atr - RISK_FLOOR_ATR) <= TOLERANCE:
        risk_atr = RISK_FLOOR_ATR
    elif abs(raw_atr - RISK_CAP_ATR) <= TOLERANCE:
        risk_atr = RISK_CAP_ATR
    else:
        risk_atr = max(raw_atr, RISK_FLOOR_ATR)
    return {"accepted": True, "reason": None, "raw_risk": raw_risk,
            "raw_risk_atr": raw_atr, "risk": risk_atr * atr,
            "risk_atr": risk_atr, "floor_applied": raw_atr < RISK_FLOOR_ATR}


def target_space_check(*, side: str, entry: float, boundary: float, risk: float) -> dict:
    if side not in {"buy", "sell"}:
        raise AdaptiveStopError("side must be buy or sell")
    entry = _number(entry, "entry")
    boundary = _number(boundary, "boundary")
    risk = _number(risk, "risk")
    if risk <= 0:
        raise AdaptiveStopError("risk must be positive")
    space = boundary - entry if side == "buy" else entry - boundary
    space_r = space / risk
    accepted = space_r + TOLERANCE >= TARGET_SPACE_MIN_R
    return {"accepted": accepted,
            "reason": None if accepted else "TARGET_SPACE_LT_1_5R",
            "boundary": boundary, "space": space, "space_r": space_r}


def adaptive_plan(rows: list[dict], *, decision_index: int, side: str,
                  entry_low: float, entry_high: float, atr: float) -> dict:
    """Compute B100 from the closed prefix visible at ``decision_index`` only."""
    pivot = confirmed_pivot(rows, decision_index=decision_index, side=side)
    if pivot is None:
        return {"variant": "B", "accepted": False,
                "reason": "NO_CONFIRMED_SWING"}
    entry_low = _number(entry_low, "entry_low")
    entry_high = _number(entry_high, "entry_high")
    atr = _number(atr, "atr")
    if entry_low > entry_high or atr <= 0:
        raise AdaptiveStopError("entry zone/ATR is invalid")
    entry = entry_high if side == "buy" else entry_low
    buffer = STRUCTURE_BUFFER_ATR * atr
    raw_stop = pivot["price"] - buffer if side == "buy" else pivot["price"] + buffer
    raw_risk = entry - raw_stop if side == "buy" else raw_stop - entry
    if raw_risk <= 0:
        return {"variant": "B", "accepted": False,
                "reason": "NO_CONFIRMED_SWING", "pivot": pivot,
                "raw_stop": raw_stop}
    bounded = bounded_adaptive_risk(raw_risk, atr=atr)
    if not bounded["accepted"]:
        return {"variant": "B", **bounded, "pivot": pivot,
                "raw_stop": raw_stop}
    prefix = rows[max(0, decision_index - DONCHIAN_LENGTH):decision_index]
    if len(prefix) != DONCHIAN_LENGTH:
        raise AdaptiveStopError("decision prefix lacks Donchian20 history")
    boundary = (max(_number(row.get("high"), "high") for row in prefix)
                if side == "buy"
                else min(_number(row.get("low"), "low") for row in prefix))
    risk = bounded["risk"]
    target = target_space_check(side=side, entry=entry, boundary=boundary, risk=risk)
    if not target["accepted"]:
        return {"variant": "B", "accepted": False,
                "reason": target["reason"], "pivot": pivot,
                "raw_stop": raw_stop, "risk": risk,
                "risk_atr": bounded["risk_atr"],
                "target_space": target}
    direction = 1.0 if side == "buy" else -1.0
    stop = entry - direction * risk
    sizing_multiplier = BASELINE_MAX_RISK_ATR / bounded["risk_atr"]
    normalized_risk_ratio = (
        sizing_multiplier * bounded["risk_atr"] / BASELINE_MAX_RISK_ATR)
    return {
        "variant": "B", "accepted": True, "reason": None,
        "plan": {
            "variant": "B", "side": side, "entry": entry,
            "stop": stop, "raw_stop": raw_stop, "risk": risk,
            "risk_atr": bounded["risk_atr"],
            "raw_risk_atr": bounded["raw_risk_atr"],
            "floor_applied": bounded["floor_applied"],
            "tp1": entry + direction * 1.5 * risk,
            "tp2": entry + direction * 2.0 * risk,
            "pivot": pivot,
            "structure_buffer_atr": STRUCTURE_BUFFER_ATR,
            "donchian_boundary": boundary,
            "target_space_r": target["space_r"],
            "decision_index": decision_index,
            "prefix_end_index": decision_index,
            "sizing_multiplier": sizing_multiplier,
            "normalized_risk_ratio": normalized_risk_ratio,
            "sizing_basis": "baseline_reference_size",
            "manual_only": True,
        },
    }
