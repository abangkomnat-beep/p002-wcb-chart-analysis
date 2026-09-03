"""Style M v7 market/trigger story.

This module owns only closed-H1 market structure and Donchian triggers.  Risk
geometry is deliberately delegated to :mod:`style_m_v7_risk` so legacy H1
entry/stop constants cannot leak into the production contract.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from zoneinfo import ZoneInfo

ASSET = "btcusd"
TIMEFRAME = "1h"
SCHEMA = "style-m-story/v3"
CONTRACT_VERSION = "M-PROD/v7"
BANGKOK = ZoneInfo("Asia/Bangkok")
DONCHIAN_LENGTH = 24
TRIGGER_ATR_BUFFER = 0.10
SQUEEZE_MAX_WIDTH_ATR = 4.0
PRICE_TICK = Decimal("0.01")


class StoryUnavailable(RuntimeError):
    pass


def _num(value: object, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise StoryUnavailable(f"{label} ไม่ใช่ตัวเลข") from exc
    if not math.isfinite(result):
        raise StoryUnavailable(f"{label} ไม่เป็น finite")
    return result


def _at(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise StoryUnavailable(f"เวลาแท่ง H1 ไม่ถูกต้อง: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BANGKOK)
    return parsed.astimezone(BANGKOK)


def canonical_rows(rows: list[dict], *, cutoff: datetime) -> list[dict]:
    if cutoff.tzinfo is None:
        raise StoryUnavailable("cutoff ต้องมี timezone")
    limit = cutoff.astimezone(BANGKOK)
    out, previous = [], None
    for ordinal, raw in enumerate(rows or []):
        stamp = _at(raw.get("at"))
        if previous is not None and stamp <= previous:
            raise StoryUnavailable("แท่ง H1 ต้องเรียงเวลาและไม่ซ้ำ")
        if stamp + timedelta(hours=1) > limit:
            continue
        values = {key: _num(raw.get(key), f"rows[{ordinal}].{key}")
                  for key in ("open", "high", "low", "close")}
        if not values["low"] <= min(values["open"], values["close"]) <= max(
                values["open"], values["close"]) <= values["high"]:
            raise StoryUnavailable("OHLC envelope ไม่ถูกต้อง")
        out.append({"index": len(out), "at": stamp.strftime("%Y-%m-%d %H:%M:%S"), **values})
        previous = stamp
    if len(out) < 60:
        raise StoryUnavailable("closed H1 rows ไม่พอ (ต้องมีอย่างน้อย 60)")
    for left, right in zip(out[-120:], out[-119:]):
        if _at(right["at"]) - _at(left["at"]) != timedelta(hours=1):
            raise StoryUnavailable("closed H1 rows ช่วงใช้งานต้องต่อเนื่องทุกชั่วโมง")
    return out


def _tr(rows: list[dict]) -> list[float]:
    out = []
    for i, row in enumerate(rows):
        if i == 0:
            out.append(row["high"] - row["low"])
        else:
            prev = rows[i - 1]["close"]
            out.append(max(row["high"] - row["low"], abs(row["high"] - prev),
                           abs(row["low"] - prev)))
    return out


def atr14(rows: list[dict]) -> float:
    ranges = _tr(rows)
    if len(ranges) < 15:
        raise StoryUnavailable("ATR14 คำนวณไม่ได้")
    value = sum(ranges[1:15]) / 14
    for item in ranges[15:]:
        value = (value * 13 + item) / 14
    return value


def _round(value: float, mode=ROUND_HALF_UP) -> float:
    return float(Decimal(str(value)).quantize(PRICE_TICK, rounding=mode))


def _pivots(rows: list[dict]) -> dict:
    highs, lows = [], []
    for i in range(2, len(rows) - 2):
        if all(rows[i]["high"] > rows[j]["high"] for j in (i-2, i-1, i+1, i+2)):
            highs.append({"index": i, "at": rows[i]["at"], "price": rows[i]["high"]})
        if all(rows[i]["low"] < rows[j]["low"] for j in (i-2, i-1, i+1, i+2)):
            lows.append({"index": i, "at": rows[i]["at"], "price": rows[i]["low"]})
    return {"highs": highs, "lows": lows}


def _adx14(rows: list[dict], length: int = 14) -> dict:
    """Return non-directional ADX context for the editorial copy only."""
    required = length * 2 + 1
    if len(rows) < required:
        return {"status": "unavailable", "required_bars": required,
                "available_bars": len(rows), "length": length}
    tr = _tr(rows)[1:]
    plus_dm, minus_dm = [], []
    for index in range(1, len(rows)):
        up = rows[index]["high"] - rows[index - 1]["high"]
        down = rows[index - 1]["low"] - rows[index]["low"]
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    tr_s, plus_s, minus_s = sum(tr[:length]), sum(plus_dm[:length]), sum(minus_dm[:length])
    dx_values = []
    for index in range(length, len(tr) + 1):
        if index > length:
            tr_s = tr_s - tr_s / length + tr[index - 1]
            plus_s = plus_s - plus_s / length + plus_dm[index - 1]
            minus_s = minus_s - minus_s / length + minus_dm[index - 1]
        if tr_s <= 0:
            dx_values.append(0.0)
            continue
        plus_di, minus_di = 100.0 * plus_s / tr_s, 100.0 * minus_s / tr_s
        total = plus_di + minus_di
        dx_values.append(100.0 * abs(plus_di - minus_di) / total if total else 0.0)
    if len(dx_values) < length:
        return {"status": "unavailable", "required_bars": required,
                "available_bars": len(rows), "length": length}
    adx = sum(dx_values[:length]) / length
    series = [adx]
    for value in dx_values[length:]:
        adx = (adx * (length - 1) + value) / length
        series.append(adx)
    previous = series[-2] if len(series) > 1 else None
    return {"status": "available", "required_bars": required,
            "available_bars": len(rows), "length": length,
            "adx": float(adx), "previous_adx": (float(previous) if previous is not None else None),
            "regime": _adx_regime(adx),
            "rising": bool(previous is not None and adx > previous)}


def _adx_regime(value: float) -> str:
    if value < 20.0:
        return "QUIET_RANGE"
    if value < 25.0:
        return "TRANSITION"
    return "TRENDING"


def _structure(pivots: dict) -> dict:
    highs, lows = pivots["highs"], pivots["lows"]
    if len(highs) < 2 or len(lows) < 2:
        return {"pattern": "INSUFFICIENT", "priority": "LONG"}
    high_delta = highs[-1]["price"] - highs[-2]["price"]
    low_delta = lows[-1]["price"] - lows[-2]["price"]
    if high_delta > 0 and low_delta > 0:
        pattern, priority = "BULLISH_HH_HL", "LONG"
    elif high_delta < 0 and low_delta < 0:
        pattern, priority = "BEARISH_LH_LL", "SHORT"
    else:
        pattern, priority = "MIXED", "LONG"
    return {"pattern": pattern, "priority": priority,
            "high_relation": "HIGHER_HIGH" if high_delta > 0 else "LOWER_HIGH" if high_delta < 0 else "EQUAL_HIGH",
            "low_relation": "HIGHER_LOW" if low_delta > 0 else "LOWER_LOW" if low_delta < 0 else "EQUAL_LOW"}


def _market_position(close: float, upper: float, lower: float) -> str:
    width = upper - lower
    if width <= 0:
        raise StoryUnavailable("Donchian width ต้องมากกว่า 0")
    position = (close - lower) / width
    if position <= 1 / 3:
        return "NEAR_LOWER"
    if position >= 2 / 3:
        return "NEAR_UPPER"
    return "CENTER"


def _scenario(side: str, upper: float, lower: float, atr: float, latest: dict) -> dict:
    if side == "LONG":
        trigger = _round(upper + TRIGGER_ATR_BUFFER * atr, ROUND_CEILING)
        return {"side": side, "trigger": trigger, "raw_trigger": upper + TRIGGER_ATR_BUFFER * atr,
                "entry_low": trigger, "entry_high": None, "sl": None, "tp1": None,
                "tp2": None, "risk": None, "rr1": None, "rr2": None,
                "state": "WAIT_TRIGGER", "no_plan_reason": None,
                "trigger_rule": "closed_h1_strict_cross"}
    trigger = _round(lower - TRIGGER_ATR_BUFFER * atr, ROUND_FLOOR)
    return {"side": side, "trigger": trigger, "raw_trigger": lower - TRIGGER_ATR_BUFFER * atr,
            "entry_low": None, "entry_high": trigger, "sl": None, "tp1": None,
            "tp2": None, "risk": None, "rr1": None, "rr2": None,
            "state": "WAIT_TRIGGER", "no_plan_reason": None,
            "trigger_rule": "closed_h1_strict_cross"}


def build(rows: list[dict], *, cutoff: datetime, source_label: str,
          source_meta: dict | None = None) -> dict:
    normalized = canonical_rows(rows, cutoff=cutoff)
    atr = atr14(normalized)
    reference = normalized[-(DONCHIAN_LENGTH + 1):-1]
    if len(reference) != DONCHIAN_LENGTH:
        raise StoryUnavailable("Donchian reference ไม่ครบ 24 แท่ง")
    upper = max(row["high"] for row in reference)
    lower = min(row["low"] for row in reference)
    latest = normalized[-1]
    if upper <= lower:
        raise StoryUnavailable("Donchian width ต้องมากกว่า 0")
    pivots = _pivots(normalized)
    adx = _adx14(normalized)
    if adx.get("status") != "available":
        raise StoryUnavailable("ADX14 คำนวณไม่ได้")
    structure = _structure(pivots)
    width = upper - lower
    width_atr_ratio = width / atr
    squeeze_confirmed = (adx["regime"] == "QUIET_RANGE"
                         and width_atr_ratio <= SQUEEZE_MAX_WIDTH_ATR)
    zones = {"buy_side_liquidity_reference": _round(upper),
             "sell_side_liquidity_reference": _round(lower),
             "trap_zone_low": _round(lower - TRIGGER_ATR_BUFFER * atr, ROUND_FLOOR),
             "trap_zone_high": _round(upper + TRIGGER_ATR_BUFFER * atr, ROUND_CEILING)}
    false_breakout = {"bull_trap": "next_closed_h1_below_short_trigger",
                      "bear_trap": "next_closed_h1_above_long_trigger",
                      "no_retest_tp1": "cancel_if_tp1_reached_before_retest"}
    source_projection = {"cutoff": cutoff.astimezone(BANGKOK).isoformat(),
                         "source_label": source_label, "source_meta": source_meta or {},
                         "rows": [{key: row[key] for key in ("at", "open", "high", "low", "close")}
                                  for row in normalized]}
    sha = hashlib.sha256(json.dumps(source_projection, sort_keys=True,
                                     ensure_ascii=False).encode()).hexdigest()
    story = {"schema": SCHEMA, "contract_version": CONTRACT_VERSION, "asset": ASSET,
             "timeframe": TIMEFRAME, "cutoff": cutoff.astimezone(BANGKOK).isoformat(),
             "valid_until": (cutoff.astimezone(BANGKOK) + timedelta(hours=24)).isoformat(),
             "latest": {key: latest[key] for key in ("at", "open", "high", "low", "close")},
             "indicators": {"atr14": round(atr, 8), "adx14": round(adx["adx"], 8),
                            "previous_adx14": (round(adx["previous_adx"], 8)
                                               if adx.get("previous_adx") is not None else None),
                            "adx_regime": adx["regime"], "adx_rising": adx["rising"]},
            "donchian": {"length": DONCHIAN_LENGTH, "upper": _round(upper),
                          "lower": _round(lower), "width": _round(width),
                          "width_atr_ratio": round(width_atr_ratio, 8)},
             "pivots": pivots, "structure": structure, "state": "SCENARIOS_READY",
             "scenario_order": (["long", "short"] if structure["priority"] == "LONG"
                                 else ["short", "long"]),
             "scenarios": {"long": _scenario("LONG", upper, lower, atr, latest),
                           "short": _scenario("SHORT", upper, lower, atr, latest)},
             "market_position": _market_position(float(latest["close"]), upper, lower),
             "squeeze": {"status": "CONFIRMED" if squeeze_confirmed else "NOT_CONFIRMED",
                         "width_atr_ratio": round(width_atr_ratio, 8),
                         "max_width_atr": SQUEEZE_MAX_WIDTH_ATR,
                         "basis": "quiet_range_and_donchian_width_to_atr"},
             "zones": zones, "false_breakout": false_breakout,
             "source_label": source_label, "source_meta": source_meta or {},
             "source_sha256": sha, "volume_policy": "unavailable-and-forbidden"}
    validate(story)
    return {"story": story, "rows": normalized, "source_projection": source_projection}


def validate(story: dict) -> None:
    if story.get("schema") != SCHEMA or story.get("contract_version") != CONTRACT_VERSION:
        raise StoryUnavailable("story schema/version ไม่ตรง v7")
    if story.get("asset") != ASSET or story.get("state") not in {"SCENARIOS_READY", "NO_PLAN"}:
        raise StoryUnavailable("story state/asset ไม่ตรง v7")
    d = story.get("donchian") or {}
    if d.get("length") != DONCHIAN_LENGTH or not (d.get("upper") > d.get("lower")):
        raise StoryUnavailable("Donchian range ไม่ถูกต้อง")
    if set(story.get("scenarios") or {}) != {"long", "short"}:
        raise StoryUnavailable("ต้องมี Long และ Short scenario ครบ")
    for plan in story["scenarios"].values():
        if plan.get("side") not in {"LONG", "SHORT"} or not math.isfinite(float(plan.get("trigger"))):
            raise StoryUnavailable("trigger ไม่ถูกต้อง")
        if any(key in plan for key in ("entry_zone_atr", "stop_buffer_atr", "worst_entry_risk_atr")):
            raise StoryUnavailable("legacy H1 geometry field ปรากฏใน v7 story")


__all__ = ["ASSET", "TIMEFRAME", "SCHEMA", "CONTRACT_VERSION", "BANGKOK",
           "DONCHIAN_LENGTH", "TRIGGER_ATR_BUFFER", "PRICE_TICK", "StoryUnavailable",
           "canonical_rows", "atr14", "build", "validate"]
