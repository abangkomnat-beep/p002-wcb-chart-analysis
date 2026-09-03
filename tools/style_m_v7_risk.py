"""Frozen ADR14 production policy for Style M M-PROD/v7."""
from __future__ import annotations

import copy
import math
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from statistics import mean

from tools import style_m_v7_story as story_mod

POLICY_ID = "ADR14_F0.50_C1.00_E0.10_R1.50_R2.00"
METRIC = "ADR14"
LENGTH = 14
ENTRY_WIDTH_COEFFICIENT = 0.10
RISK_FLOOR_COEFFICIENT = 0.50
RISK_CAP_COEFFICIENT = 1.00
TP1_R = 1.50
TP2_R = 2.00


class RiskUnavailable(ValueError):
    def __init__(self, message: str, reason_code: str = "ADR14_UNAVAILABLE"):
        super().__init__(message)
        self.reason_code = reason_code


def _at(value: object) -> datetime:
    try:
        return story_mod._at(value)
    except Exception as exc:  # normalize producer errors to a stable code
        raise RiskUnavailable("daily timestamp invalid", "ADR14_INVALID_DAILY_INPUT") from exc


def _num(value: object, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise RiskUnavailable(f"{label} invalid", "ADR14_INVALID_DAILY_INPUT") from exc
    if not math.isfinite(result):
        raise RiskUnavailable(f"{label} non-finite", "ADR14_INVALID_DAILY_INPUT")
    return result


def completed_daily_bars(rows, *, cutoff: datetime) -> list[dict]:
    if cutoff.tzinfo is None:
        raise RiskUnavailable("cutoff timezone missing", "ADR14_UNAVAILABLE")
    limit = cutoff.astimezone(story_mod.BANGKOK)
    groups: dict[str, list[dict]] = defaultdict(list)
    previous = None
    for index, raw in enumerate(rows or []):
        stamp = _at(raw.get("at"))
        if previous is not None and stamp <= previous:
            raise RiskUnavailable("daily source unsorted or duplicate", "ADR14_INVALID_DAILY_INPUT")
        previous = stamp
        # The current Bangkok calendar day is forming and is intentionally
        # excluded; even malformed values on that day must not influence ADR14.
        if stamp.date() >= limit.date():
            continue
        values = {key: _num(raw.get(key), f"rows[{index}].{key}")
                  for key in ("open", "high", "low", "close")}
        if not values["low"] <= min(values["open"], values["close"]) <= max(
                values["open"], values["close"]) <= values["high"]:
            raise RiskUnavailable("daily OHLC envelope invalid", "ADR14_INVALID_DAILY_INPUT")
        groups[stamp.date().isoformat()].append({"at": stamp, **values})
    bars = []
    for day in sorted(groups):
        items = groups[day]
        hours = [item["at"].hour for item in items]
        if len(items) != 24 or hours != list(range(24)):
            raise RiskUnavailable(f"daily bar incomplete: {day}", "ADR14_INVALID_DAILY_INPUT")
        bars.append({"date": day, "at": f"{day}T00:00:00+07:00",
                     "open": items[0]["open"], "high": max(x["high"] for x in items),
                     "low": min(x["low"] for x in items), "close": items[-1]["close"],
                     "h1_count": 24})
    return bars


def adr14(rows, *, cutoff: datetime) -> dict:
    bars = completed_daily_bars(rows, cutoff=cutoff)
    if len(bars) < LENGTH:
        raise RiskUnavailable("completed daily bars insufficient", "ADR14_INSUFFICIENT_COMPLETED_DAYS")
    value = mean(item["high"] - item["low"] for item in bars[-LENGTH:])
    if not math.isfinite(value) or value <= 0:
        raise RiskUnavailable("ADR14 non-positive", "ADR14_UNAVAILABLE")
    return {"metric": METRIC, "value": round(float(value), 8), "length": LENGTH,
            "closed_daily_bars": len(bars), "last_closed_date": bars[-1]["date"],
            "basis": "completed_bangkok_calendar_days_before_cutoff"}


def _round(value: float, mode) -> float:
    return float(Decimal(str(value)).quantize(story_mod.PRICE_TICK, rounding=mode))


def _anchor(story: dict, plan: dict) -> tuple[float, str]:
    pivots = story.get("pivots") or {}
    if plan["side"] == "LONG":
        vals = [float(item["price"]) for item in pivots.get("lows", [])
                if float(item["price"]) < float(plan["trigger"])]
        return (max(vals), "confirmed_h1_swing_low") if vals else (
            float(story["donchian"]["lower"]), "opposite_donchian_boundary")
    vals = [float(item["price"]) for item in pivots.get("highs", [])
            if float(item["price"]) > float(plan["trigger"])]
    return (min(vals), "confirmed_h1_swing_high") if vals else (
        float(story["donchian"]["upper"]), "opposite_donchian_boundary")


def _no_plan(plan: dict, detail: dict, reason: str) -> None:
    plan.update({"state": "NO_PLAN", "entry_low": None, "entry_high": None,
                 "sl": None, "tp1": None, "tp2": None, "risk": None,
                 "rr1": None, "rr2": None, "no_plan_reason": reason,
                 "risk_geometry": detail})
    detail["no_plan_reason"] = reason


def apply_policy(story: dict, *, volatility: dict) -> dict:
    story_mod.validate(story)
    if volatility.get("metric") != METRIC or int(volatility.get("length", 0)) != LENGTH:
        raise RiskUnavailable("production requires ADR14", "ADR14_UNAVAILABLE")
    value = _num(volatility.get("value"), "ADR14")
    if value <= 0:
        raise RiskUnavailable("ADR14 non-positive", "ADR14_UNAVAILABLE")
    if volatility.get("basis") != "completed_bangkok_calendar_days_before_cutoff":
        raise RiskUnavailable("ADR14 basis invalid", "ADR14_INVALID_DAILY_INPUT")
    result = copy.deepcopy(story)
    result["contract_version"] = "M-PROD/v7"
    result["risk_geometry"] = {"policy_id": POLICY_ID, "volatility": copy.deepcopy(volatility),
                                "entry_width_coefficient": ENTRY_WIDTH_COEFFICIENT,
                                "risk_floor_coefficient": RISK_FLOOR_COEFFICIENT,
                                "risk_cap_coefficient": RISK_CAP_COEFFICIENT,
                                "tp1_r": TP1_R, "tp2_r": TP2_R}
    for key, plan in result["scenarios"].items():
        edge = float(plan["trigger"])
        if plan["side"] == "LONG":
            entry_low = edge
            entry_high = _round(edge + ENTRY_WIDTH_COEFFICIENT * value, ROUND_CEILING)
            adverse_edge = entry_high
        else:
            entry_high = edge
            entry_low = _round(edge - ENTRY_WIDTH_COEFFICIENT * value, ROUND_FLOOR)
            adverse_edge = entry_low
        anchor, anchor_rule = _anchor(result, plan)
        structural = adverse_edge - anchor if plan["side"] == "LONG" else anchor - adverse_edge
        detail = {"policy_id": POLICY_ID, "volatility_metric": METRIC,
                  "volatility_value": round(value, 8), "entry_width_coefficient": ENTRY_WIDTH_COEFFICIENT,
                  "entry_width": round(abs(entry_high - entry_low), 8),
                  "adverse_entry_edge": adverse_edge, "structural_anchor": round(anchor, 8),
                  "structural_anchor_rule": anchor_rule, "structural_risk": round(structural, 8),
                  "risk_floor_coefficient": RISK_FLOOR_COEFFICIENT,
                  "volatility_floor": round(value * RISK_FLOOR_COEFFICIENT, 8),
                  "risk_cap_coefficient": RISK_CAP_COEFFICIENT,
                  "max_risk_cap": round(value * RISK_CAP_COEFFICIENT, 8),
                  "final_risk": None, "sl": None, "tp1": None, "tp2": None,
                  "tp1_r": TP1_R, "tp2_r": TP2_R, "no_plan_reason": None}
        if not math.isfinite(structural) or structural <= 0:
            _no_plan(plan, detail, "STRUCTURAL_RISK_NON_POSITIVE")
            continue
        final_risk = max(structural, value * RISK_FLOOR_COEFFICIENT)
        detail["final_risk"] = round(final_risk, 8)
        if final_risk > value * RISK_CAP_COEFFICIENT:
            _no_plan(plan, detail, "FINAL_RISK_EXCEEDS_ADR14_CAP")
            continue
        if plan["side"] == "LONG":
            sl = _round(adverse_edge - final_risk, ROUND_FLOOR)
            risk_value = _round(adverse_edge - sl, ROUND_HALF_UP)
            tp1 = _round(adverse_edge + TP1_R * risk_value, ROUND_CEILING)
            tp2 = _round(adverse_edge + TP2_R * risk_value, ROUND_CEILING)
            rr1, rr2 = (tp1 - adverse_edge) / risk_value, (tp2 - adverse_edge) / risk_value
        else:
            sl = _round(adverse_edge + final_risk, ROUND_CEILING)
            risk_value = _round(sl - adverse_edge, ROUND_HALF_UP)
            tp1 = _round(adverse_edge - TP1_R * risk_value, ROUND_FLOOR)
            tp2 = _round(adverse_edge - TP2_R * risk_value, ROUND_FLOOR)
            rr1, rr2 = (adverse_edge - tp1) / risk_value, (adverse_edge - tp2) / risk_value
        plan.update({"entry_low": entry_low, "entry_high": entry_high, "sl": sl,
                     "tp1": tp1, "tp2": tp2, "risk": risk_value,
                     "rr1": round(rr1, 8), "rr2": round(rr2, 8),
                     "risk_geometry": detail, "no_plan_reason": None})
        detail.update({"final_risk": risk_value, "sl": sl, "tp1": tp1, "tp2": tp2})
    return result


__all__ = ["POLICY_ID", "METRIC", "LENGTH", "ENTRY_WIDTH_COEFFICIENT",
           "RISK_FLOOR_COEFFICIENT", "RISK_CAP_COEFFICIENT", "TP1_R", "TP2_R",
           "RiskUnavailable", "completed_daily_bars", "adr14", "apply_policy"]
