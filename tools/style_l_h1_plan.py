"""Pure Style L H4/H1 planning contracts.

This module deliberately has no filesystem or publishing side effects.  Canonical
prices remain full precision; three-decimal values are a presentation adapter only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Iterable

from tools import wcb_source


class H1ContractError(ValueError):
    """Input cannot be interpreted without weakening the public contract."""


class H1PlanHold(RuntimeError):
    """Closed H4/H1 evidence does not support a valid public plan."""


@dataclass(frozen=True)
class Pivot:
    kind: str
    index: int
    price: float
    confirmed_at: str


def _number(value, field: str = "value") -> float:
    if isinstance(value, bool):
        raise H1ContractError(f"{field} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise H1ContractError(f"{field} must be numeric") from exc
    if not math.isfinite(result):
        raise H1ContractError(f"{field} must be finite")
    return result


def public_price(value, *, canonical_decimals: int = 5) -> str:
    """Normalize canonical FX precision, then format three public decimals.

    Engine arithmetic may produce a binary float just below an exact broker tick
    (for example ``0.9874999999999999``).  Normalizing to the asset's canonical
    tick before presentation preserves the intended canonical level.
    """
    if isinstance(value, bool):
        raise H1ContractError("price must be numeric")
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise H1ContractError("price must be numeric") from exc
    if not decimal.is_finite():
        raise H1ContractError("price must be finite")
    if isinstance(canonical_decimals, bool) or not isinstance(canonical_decimals, int):
        raise H1ContractError("canonical_decimals must be an integer")
    if not 0 <= canonical_decimals <= 12:
        raise H1ContractError("canonical_decimals outside supported range")
    canonical_tick = Decimal(1).scaleb(-canonical_decimals)
    decimal = decimal.quantize(canonical_tick, rounding=ROUND_HALF_UP)
    return format(decimal.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP), ".3f")


def canonical_decimals_for(asset: str) -> int:
    """Resolve canonical precision from the single registered asset profile."""
    try:
        decimals = wcb_source.profile_for(asset)["decimals"]
    except (KeyError, TypeError, ValueError) as exc:
        raise H1ContractError(f"asset profile has no canonical decimals: {asset}") from exc
    if isinstance(decimals, bool) or not isinstance(decimals, int) or not 0 <= decimals <= 12:
        raise H1ContractError(f"asset canonical decimals invalid: {asset}")
    return decimals


def _at(row: dict) -> datetime:
    raw = row.get("at")
    if not isinstance(raw, str):
        raise H1ContractError("bar at must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise H1ContractError("bar at must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise H1ContractError("bar at must include timezone")
    return parsed.astimezone(timezone.utc)


def _closed_prefix(rows: Iterable[dict], decision_at: datetime | None) -> list[dict]:
    result = []
    previous = None
    if decision_at is not None and decision_at.tzinfo is None:
        raise H1ContractError("decision_at must be timezone-aware")
    boundary = decision_at.astimezone(timezone.utc) if decision_at else None
    for row in rows:
        if not isinstance(row, dict) or row.get("closed") is not True:
            continue
        stamp = _at(row)
        if boundary is not None and stamp > boundary:
            continue
        if previous is not None and stamp <= previous:
            raise H1ContractError("closed bars must be strictly ordered")
        previous = stamp
        for field in ("open", "high", "low", "close"):
            _number(row.get(field), field)
        high, low = _number(row["high"], "high"), _number(row["low"], "low")
        opening, close = _number(row["open"], "open"), _number(row["close"], "close")
        if high < low or not low <= opening <= high or not low <= close <= high:
            raise H1ContractError("bar OHLC must satisfy low <= open/close <= high")
        result.append(row)
    return result


def confirmed_pivots(rows: Iterable[dict], *, left: int = 2, right: int = 2,
                     decision_at: datetime | None = None) -> list[Pivot]:
    """Return strict pivots only after all right-hand closed bars exist."""
    if left < 1 or right < 1:
        raise H1ContractError("pivot wings must be positive")
    data = _closed_prefix(rows, decision_at)
    pivots: list[Pivot] = []
    for index in range(left, len(data) - right):
        high = _number(data[index]["high"], "high")
        low = _number(data[index]["low"], "low")
        neighbours = data[index - left:index] + data[index + 1:index + right + 1]
        if all(high > _number(row["high"], "high") for row in neighbours):
            pivots.append(Pivot("high", index, high, data[index + right]["at"]))
        if all(low < _number(row["low"], "low") for row in neighbours):
            pivots.append(Pivot("low", index, low, data[index + right]["at"]))
    return pivots


def classify_h1_state(side: str, zone_low: float, zone_high: float,
                      latest_closed: dict) -> str:
    low, high = _number(zone_low), _number(zone_high)
    bar_low = _number(latest_closed.get("low"), "low")
    bar_high = _number(latest_closed.get("high"), "high")
    close = _number(latest_closed.get("close"), "close")
    if side not in {"BUY", "SELL"} or high <= low:
        raise H1ContractError("invalid side or entry zone")
    intersects = bar_high >= low and bar_low <= high
    if not intersects:
        return "WAIT_H1_ZONE"
    rejected = close > high if side == "BUY" else close < low
    return "H1_TRIGGER_CONFIRMED" if rejected else "H1_ENTRY_READY"


def build_leg(side: str, *, anchor: float, atr: float, stop_atr: float = 1.5,
              target_candidates: Iterable[float], buffer_atr: float = 0.25,
              max_stop_atr: float = 3.0) -> dict:
    if side not in {"BUY", "SELL"}:
        raise H1ContractError("side must be BUY or SELL")
    anchor = _number(anchor, "anchor")
    atr = _number(atr, "atr")
    stop_atr = _number(stop_atr, "stop_atr")
    buffer_atr = _number(buffer_atr, "buffer_atr")
    max_stop_atr = _number(max_stop_atr, "max_stop_atr")
    if anchor <= 0 or atr <= 0 or stop_atr <= 0 or buffer_atr < 0 or max_stop_atr <= 0:
        raise H1ContractError("anchor, ATR and stop multiplier must be positive")
    if stop_atr > max_stop_atr:
        raise H1PlanHold("NO_PLAN_STOP_CAP")
    sign = 1.0 if side == "BUY" else -1.0
    zone_low = anchor if side == "BUY" else anchor - buffer_atr * atr
    zone_high = anchor + buffer_atr * atr if side == "BUY" else anchor
    worst_entry = zone_high if side == "BUY" else zone_low
    structural_stop = anchor - sign * buffer_atr * atr
    raw_risk = abs(worst_entry - structural_stop)
    final_risk = max(raw_risk, stop_atr * atr)
    if final_risk > max_stop_atr * atr + 1e-12:
        raise H1PlanHold("NO_PLAN_STOP_CAP")
    stop = worst_entry - sign * final_risk

    candidates = sorted({_number(value, "target") for value in target_candidates})
    if side == "SELL":
        candidates.reverse()
    profitable = [value for value in candidates
                  if (value - worst_entry) * sign > 0]
    tp1 = next((value for value in profitable
                if abs(value - worst_entry) / final_risk >= 1.5), None)
    tp2 = next((value for value in profitable
                if value != tp1 and abs(value - worst_entry) / final_risk >= 2.0), None)
    if tp1 is None or tp2 is None:
        raise H1PlanHold("NO_PLAN_RR")
    rewards = [abs(tp1 - worst_entry) / final_risk,
               abs(tp2 - worst_entry) / final_risk]
    return {
        "side": side,
        "anchor": anchor,
        "entry_zone": {"low": zone_low, "high": zone_high},
        "worst_entry": worst_entry,
        "stop_loss": stop,
        "take_profit": [tp1, tp2],
        "risk_reward": [round(value, 4) for value in rewards],
        "stop_atr": stop_atr,
        "risk_atr": final_risk / atr,
        "invalidation": {
            "condition": "H1_CLOSE_BELOW_STRUCTURE" if side == "BUY"
            else "H1_CLOSE_ABOVE_STRUCTURE",
            "value": anchor,
        },
    }


def build_h1_plan(asset: str, h4_bias: str | None, h1_rows: Iterable[dict],
                  h4_rows: Iterable[dict], *, decision_at: datetime,
                  atr14: float | None = None, stop_atr: float = 1.5,
                  anchor_max_age: int = 48) -> dict:
    if h4_bias not in {"up", "down", None}:
        raise H1ContractError("H4 bias must be up, down or neutral")
    canonical_decimals = canonical_decimals_for(asset)
    if decision_at.tzinfo is None:
        raise H1ContractError("decision_at must be timezone-aware")
    data = _closed_prefix(h1_rows, decision_at)
    if len(data) < 5:
        raise H1PlanHold("NO_PLAN_DATA")
    if atr14 is None:
        if len(data) < 15:
            raise H1PlanHold("NO_PLAN_ATR14_HISTORY")
        true_ranges = []
        for index in range(len(data) - 14, len(data)):
            row, previous = data[index], data[index - 1]
            high, low = _number(row["high"]), _number(row["low"])
            previous_close = _number(previous["close"])
            true_ranges.append(max(high - low, abs(high - previous_close),
                                   abs(low - previous_close)))
        atr14 = sum(true_ranges) / 14
    h1_window = data[-120:]
    window_offset = len(data) - len(h1_window)
    h1_pivots = confirmed_pivots(h1_window, decision_at=decision_at)
    h4_data = list(h4_rows)
    h4_pivots = confirmed_pivots(h4_data, decision_at=decision_at) if h4_data else []
    target_values = [pivot.price for pivot in (*h1_pivots, *h4_pivots)]

    def one(direction: str) -> dict:
        side = "BUY" if direction == "up" else "SELL"
        kind = "low" if side == "BUY" else "high"
        anchors = [pivot for pivot in h1_pivots if pivot.kind == kind]
        if not anchors:
            raise H1PlanHold("NO_PLAN_PIVOT")
        anchor = anchors[-1]
        window_age = len(h1_window) - 1 - anchor.index
        if window_age > anchor_max_age:
            raise H1PlanHold("NO_PLAN_ANCHOR_STALE")
        leg = build_leg(side, anchor=anchor.price, atr=atr14,
                        stop_atr=stop_atr, target_candidates=target_values)
        leg["anchor_index"] = window_offset + anchor.index
        leg["anchor_confirmed_at"] = anchor.confirmed_at
        return leg

    if h4_bias is None:
        legs = [one("up"), one("down")]
        side = "OCO"
        direction = None
        budgets = {"single_leg_risk_pct": 0.0025, "oco_total_risk_pct": 0.005}
    else:
        legs = [one(h4_bias)]
        side = legs[0]["side"]
        direction = h4_bias
        budgets = {"single_leg_risk_pct": 0.005, "oco_total_risk_pct": 0.005}
    statuses = [classify_h1_state(
        leg["side"], leg["entry_zone"]["low"], leg["entry_zone"]["high"], data[-1])
        for leg in legs]
    status = statuses[0] if len(statuses) == 1 else "OCO_H1_READY"
    return {
        "schema": "style-l-h1-structural-plan/v1",
        "asset": asset,
        "public_timeframe": "H4-H1",
        "status": status,
        "side": side,
        "direction": direction,
        "decision_at": decision_at.astimezone(timezone.utc).isoformat(),
        "plans": legs,
        "risk_policy": budgets,
        "display_policy": "public-price-3dp-half-up/v1",
        "canonical_decimals": canonical_decimals,
    }


def risk_sizing(equity: float, risk_fraction: float, stop_distance: float,
                *, cost_per_unit: float = 0.0) -> dict:
    equity = _number(equity, "equity")
    risk_fraction = _number(risk_fraction, "risk_fraction")
    stop_distance = _number(stop_distance, "stop_distance")
    cost = _number(cost_per_unit, "cost_per_unit")
    if equity <= 0 or not 0 < risk_fraction <= 1 or stop_distance <= 0 or cost < 0:
        raise H1ContractError("invalid sizing inputs")
    budget = equity * risk_fraction
    return {"risk_budget": budget, "effective_risk_per_unit": stop_distance + cost,
            "quantity": budget / (stop_distance + cost)}


def oco_risk_budgets(equity: float, total_risk_fraction: float) -> dict:
    total = _number(equity, "equity") * _number(total_risk_fraction, "risk_fraction")
    return {"BUY": total / 2, "SELL": total / 2, "total": total}


def lifecycle_expiry(created_at: datetime, *, max_trading_days: int = 5) -> datetime:
    if created_at.tzinfo is None:
        raise H1ContractError("created_at must be timezone-aware")
    if isinstance(max_trading_days, bool) or not isinstance(max_trading_days, int) or max_trading_days <= 0:
        raise H1ContractError("max_trading_days must be a positive integer")
    current = created_at.astimezone(timezone.utc)
    # Friday 21:00 UTC is the conservative pre-weekend boundary for this contract.
    days_to_friday = (4 - current.weekday()) % 7
    friday = current + timedelta(days=days_to_friday)
    friday = friday.replace(hour=21, minute=0, second=0, microsecond=0)
    if current >= friday:
        friday += timedelta(days=7)
    cursor = current
    counted = 0
    while counted < max_trading_days:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            counted += 1
    return min(cursor, friday)


def lifecycle_status(side: str, *, anchor: float, current_close: float,
                     h4_bias: str | None, original_h4_bias: str,
                     newer_anchor: bool, tp2_hit: bool, now: datetime,
                     expires_at: datetime) -> str:
    if now.tzinfo is None or expires_at.tzinfo is None:
        raise H1ContractError("lifecycle timestamps must be timezone-aware")
    if tp2_hit:
        return "COMPLETE_TP2"
    if h4_bias != original_h4_bias:
        return "INVALIDATED_H4_FLIP"
    if newer_anchor:
        return "INVALIDATED_NEW_ANCHOR"
    if (side == "BUY" and current_close < anchor) or (side == "SELL" and current_close > anchor):
        return "INVALIDATED_STRUCTURE"
    if now >= expires_at:
        return "EXPIRED"
    return "LIVE"


def _display_zone(zone: dict, *, canonical_decimals: int) -> str:
    low = public_price(zone["low"], canonical_decimals=canonical_decimals)
    high = public_price(zone["high"], canonical_decimals=canonical_decimals)
    return low if low == high else f"{low}–{high}"


def render_public_table(plan: dict) -> str:
    canonical_decimals = plan.get("canonical_decimals")
    if isinstance(canonical_decimals, bool) or not isinstance(canonical_decimals, int):
        raise H1ContractError("plan canonical_decimals is required")
    lines = [
        '<div class="style-l-plan-table" role="region" aria-label="H1 trade plan" tabindex="0">',
        '<table><thead><tr><th>Side</th><th>H1 setup</th><th>Entry</th><th>SL</th>'
        '<th>TP &amp; RR</th><th>Invalidation</th></tr></thead><tbody>',
    ]
    for leg in plan.get("plans", []):
        tp1, tp2 = leg["take_profit"]
        rr1, rr2 = leg["risk_reward"]
        collision = (public_price(tp1, canonical_decimals=canonical_decimals)
                     == public_price(tp2, canonical_decimals=canonical_decimals))
        marker = "≈" if collision else ""
        targets = (f'<span class="nowrap">TP1 – {marker}{public_price(tp1, canonical_decimals=canonical_decimals)} ({rr1:g}R)</span><br>'
                   f'<span class="nowrap">TP2 – {marker}{public_price(tp2, canonical_decimals=canonical_decimals)} ({rr2:g}R)</span>')
        setup = plan.get("status", "WAIT_H1_ZONE")
        lines.append(
            f'<tr><td><span class="nowrap">{leg["side"]}</span></td><td>{setup}</td>'
            f'<td><span class="nowrap">{_display_zone(leg["entry_zone"], canonical_decimals=canonical_decimals)}</span></td>'
            f'<td><span class="nowrap">{public_price(leg["stop_loss"], canonical_decimals=canonical_decimals)}</span></td>'
            f'<td>{targets}</td><td>{leg["invalidation"]["condition"]} '
            f'<span class="nowrap">{public_price(leg["invalidation"]["value"], canonical_decimals=canonical_decimals)}</span></td></tr>')
    lines += ["</tbody></table>", "</div>", "",
              "ราคาแสดง 3 ตำแหน่งเพื่ออ่านง่าย; ระบบคำนวณจากค่าความละเอียดเต็ม"]
    return "\n".join(lines)


def resolve_h1_visual_contract(plan: dict) -> dict:
    canonical_decimals = plan.get("canonical_decimals")
    if isinstance(canonical_decimals, bool) or not isinstance(canonical_decimals, int):
        raise H1ContractError("plan canonical_decimals is required")
    specs = []
    for leg in plan.get("plans", []):
        levels = [
            (f"{leg['side']} Entry", leg["worst_entry"], "entry"),
            ("SL", leg["stop_loss"], "stop"),
            ("TP1", leg["take_profit"][0], "target"),
            ("TP2", leg["take_profit"][1], "target"),
            ("Invalidation", leg["invalidation"]["value"], "invalidation"),
        ]
        for label, raw, kind in levels:
            value = _number(raw, kind)
            specs.append({"role": label, "kind": kind, "side": leg["side"],
                          "value": value,
                          "text": f"{label} {public_price(value, canonical_decimals=canonical_decimals)}"})
    return {"panels": [
        {"role": "H1_CONTEXT", "bars": 120, "future_slots": 0,
         "h4_bias": plan.get("direction")},
        {"role": "H1_EXECUTION_ZOOM", "bars": 48, "future_slots": 24,
         "specs": specs, "status": plan.get("status")},
    ]}
