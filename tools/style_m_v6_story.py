"""Deterministic Style M v6 price-action oracle.

The oracle always produces two conditional breakout/retest scenarios when
closed H1 data is valid.  Direction comes from price structure and trigger
levels; ADX is retained as a strength-only context value.
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
SCHEMA = "style-m-story/v2"
BANGKOK = ZoneInfo("Asia/Bangkok")
STATES = ("SCENARIOS_READY",)
SCENARIO_STATES = (
    "WAIT_TRIGGER", "TRIGGERED_WAIT_RETEST", "RETEST_OBSERVED",
    "INVALIDATED", "CANCELLED_OPPOSITE_TRIGGER", "EXPIRED",
)
DONCHIAN_LENGTH = 24
BREAKOUT_BUFFER_ATR = 0.10
ENTRY_ZONE_ATR = 0.25
STOP_BUFFER_ATR = 0.75
MIN_RR1 = 1.50
MIN_RR2 = 2.00
EXPIRY_HOURS = 24
PRICE_TICK = Decimal("0.01")


class StoryUnavailable(RuntimeError):
    """Closed H1 evidence cannot support a Style M v6 story."""


def _number(value: object, label: str) -> float:
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
    normalized: list[dict] = []
    previous: datetime | None = None
    for ordinal, raw in enumerate(rows or []):
        stamp = _at(raw.get("at"))
        if stamp + timedelta(hours=1) > limit:
            continue
        if previous is not None and stamp <= previous:
            raise StoryUnavailable("แท่ง H1 ต้องเรียงเวลาและไม่ซ้ำ")
        values = {key: _number(raw.get(key), f"rows[{ordinal}].{key}")
                  for key in ("open", "high", "low", "close")}
        if not values["low"] <= min(values["open"], values["close"]) <= max(
                values["open"], values["close"]) <= values["high"]:
            raise StoryUnavailable("OHLC envelope ไม่ถูกต้อง")
        normalized.append({"index": len(normalized),
                           "at": stamp.strftime("%Y-%m-%d %H:%M:%S"), **values})
        previous = stamp
    if len(normalized) < 60:
        raise StoryUnavailable("closed H1 rows ไม่พอ (ต้องมีอย่างน้อย 60)")
    recent = normalized[-120:]
    for left, right in zip(recent, recent[1:]):
        if _at(right["at"]) - _at(left["at"]) != timedelta(hours=1):
            raise StoryUnavailable("closed H1 rows ช่วงใช้งานต้องต่อเนื่องทุกชั่วโมง")
    latest_close = _at(normalized[-1]["at"]) + timedelta(hours=1)
    if latest_close > limit:
        raise StoryUnavailable("พบ forming H1 bar")
    if limit - latest_close > timedelta(hours=1):
        raise StoryUnavailable("H1 source ค้างเกินหนึ่งแท่ง")
    return normalized


def _true_ranges(rows: list[dict]) -> list[float]:
    result = []
    for index, row in enumerate(rows):
        if index == 0:
            result.append(float(row["high"] - row["low"]))
            continue
        previous_close = float(rows[index - 1]["close"])
        result.append(max(float(row["high"] - row["low"]),
                          abs(float(row["high"]) - previous_close),
                          abs(float(row["low"]) - previous_close)))
    return result


def atr14_wilder(rows: list[dict]) -> list[float | None]:
    ranges = _true_ranges(rows)
    output: list[float | None] = [None] * len(rows)
    if len(ranges) < 15:
        return output
    output[14] = sum(ranges[1:15]) / 14.0
    for index in range(15, len(ranges)):
        output[index] = (float(output[index - 1]) * 13.0 + ranges[index]) / 14.0
    return output


def adx14_wilder(rows: list[dict], length: int = 14) -> dict:
    """Return ADX strength context using Wilder smoothing.

    ADX is not directional.  The returned direction-movement intermediates
    are intentionally not exposed as Style M claims.
    """
    required = length * 2 + 1
    if len(rows) < required:
        return {"status": "unavailable", "required_bars": required,
                "available_bars": len(rows), "length": length}
    tr = _true_ranges(rows)[1:]
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    for index in range(1, len(rows)):
        up = float(rows[index]["high"] - rows[index - 1]["high"])
        down = float(rows[index - 1]["low"] - rows[index]["low"])
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    tr_s = sum(tr[:length])
    plus_s = sum(plus_dm[:length])
    minus_s = sum(minus_dm[:length])
    dx_values: list[float] = []
    for index in range(length, len(tr) + 1):
        if index > length:
            tr_s = tr_s - tr_s / length + tr[index - 1]
            plus_s = plus_s - plus_s / length + plus_dm[index - 1]
            minus_s = minus_s - minus_s / length + minus_dm[index - 1]
        if tr_s <= 0:
            dx_values.append(0.0)
            continue
        plus_di = 100.0 * plus_s / tr_s
        minus_di = 100.0 * minus_s / tr_s
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
            "adx": float(adx), "previous_adx": (float(previous)
                                                   if previous is not None else None),
            "regime": adx_regime(adx),
            "rising": bool(previous is not None and adx > previous)}


def adx_regime(value: float) -> str:
    value = _number(value, "adx14")
    if value < 20.0:
        return "QUIET_RANGE"
    if value < 25.0:
        return "TRANSITION"
    return "TRENDING"


def confirmed_pivots(rows: list[dict]) -> dict:
    highs: list[dict] = []
    lows: list[dict] = []
    for index in range(2, len(rows) - 2):
        neighbors = (index - 2, index - 1, index + 1, index + 2)
        if all(rows[index]["high"] > rows[item]["high"] for item in neighbors):
            highs.append({"index": index, "at": rows[index]["at"],
                          "price": rows[index]["high"]})
        if all(rows[index]["low"] < rows[item]["low"] for item in neighbors):
            lows.append({"index": index, "at": rows[index]["at"],
                         "price": rows[index]["low"]})
    return {"highs": highs, "lows": lows}


def _round_price(value: float, mode=ROUND_HALF_UP) -> float:
    return float(Decimal(str(value)).quantize(PRICE_TICK, rounding=mode))


def _scenario(side: str, *, upper: float, lower: float, atr: float,
              latest: dict, cutoff: datetime) -> dict:
    if side == "LONG":
        raw_trigger = upper + BREAKOUT_BUFFER_ATR * atr
        trigger = _round_price(raw_trigger, ROUND_CEILING)
        entry_low = trigger
        entry_high = _round_price(trigger + ENTRY_ZONE_ATR * atr, ROUND_CEILING)
        sl = _round_price(trigger - STOP_BUFFER_ATR * atr, ROUND_FLOOR)
        risk = entry_high - sl
        tp1 = _round_price(entry_high + MIN_RR1 * risk, ROUND_CEILING)
        tp2 = _round_price(entry_high + MIN_RR2 * risk, ROUND_CEILING)
        triggered = float(latest["close"]) > trigger
        invalidated = triggered and float(latest["close"]) <= sl
        distance = max(0.0, entry_low - float(latest["close"]),
                       float(latest["close"]) - entry_high)
        rr1 = (tp1 - entry_high) / risk
        rr2 = (tp2 - entry_high) / risk
    elif side == "SHORT":
        raw_trigger = lower - BREAKOUT_BUFFER_ATR * atr
        trigger = _round_price(raw_trigger, ROUND_FLOOR)
        entry_low = _round_price(trigger - ENTRY_ZONE_ATR * atr, ROUND_FLOOR)
        entry_high = trigger
        sl = _round_price(trigger + STOP_BUFFER_ATR * atr, ROUND_CEILING)
        risk = sl - entry_low
        tp1 = _round_price(entry_low - MIN_RR1 * risk, ROUND_FLOOR)
        tp2 = _round_price(entry_low - MIN_RR2 * risk, ROUND_FLOOR)
        while (entry_low - tp1) / risk < MIN_RR1:
            tp1 = _round_price(tp1 - 0.01, ROUND_FLOOR)
        while (entry_low - tp2) / risk < MIN_RR2:
            tp2 = _round_price(tp2 - 0.01, ROUND_FLOOR)
        triggered = float(latest["close"]) < trigger
        invalidated = triggered and float(latest["close"]) >= sl
        distance = max(0.0, entry_low - float(latest["close"]),
                       float(latest["close"]) - entry_high)
        rr1 = (entry_low - tp1) / risk
        rr2 = (entry_low - tp2) / risk
    else:
        raise StoryUnavailable(f"side ไม่รองรับ: {side}")
    if risk <= 0 or rr1 < MIN_RR1 or rr2 < MIN_RR2:
        raise StoryUnavailable(f"{side} geometry/RR ไม่ผ่าน")
    state = "INVALIDATED" if invalidated else (
        "TRIGGERED_WAIT_RETEST" if triggered else "WAIT_TRIGGER")
    return {
        "side": side, "state": state, "trigger": trigger,
        "raw_trigger": raw_trigger, "entry_low": entry_low,
        "entry_high": entry_high, "sl": sl, "tp1": tp1, "tp2": tp2,
        "risk": _round_price(risk), "rr1": round(rr1, 4), "rr2": round(rr2, 4),
        "entry_zone_atr": ENTRY_ZONE_ATR, "stop_buffer_atr": STOP_BUFFER_ATR,
        "worst_entry_risk_atr": round(risk / atr, 4),
        "extended": distance > atr, "no_chase": distance > atr,
        "valid_from": cutoff.astimezone(BANGKOK).isoformat(),
        "valid_until": (cutoff.astimezone(BANGKOK) +
                        timedelta(hours=EXPIRY_HOURS)).isoformat(),
        "trigger_rule": "closed_h1_strict_cross",
        "retest_rule": "next_closed_h1_touches_entry_zone",
    }


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


def build(rows: list[dict], *, cutoff: datetime, source_label: str,
          source_meta: dict | None = None) -> dict:
    normalized = canonical_rows(rows, cutoff=cutoff)
    atr_series = atr14_wilder(normalized)
    atr = atr_series[-1]
    if atr is None or atr <= 0:
        raise StoryUnavailable("ATR14 คำนวณไม่ได้")
    adx = adx14_wilder(normalized)
    if adx.get("status") != "available":
        raise StoryUnavailable("ADX14 คำนวณไม่ได้")
    reference = normalized[-(DONCHIAN_LENGTH + 1):-1]
    if len(reference) != DONCHIAN_LENGTH:
        raise StoryUnavailable("Donchian reference ไม่ครบ 24 แท่ง")
    upper = max(float(row["high"]) for row in reference)
    lower = min(float(row["low"]) for row in reference)
    latest = normalized[-1]
    pivots = confirmed_pivots(normalized)
    structure = _structure(pivots)
    scenarios = {
        "long": _scenario("LONG", upper=upper, lower=lower, atr=float(atr),
                           latest=latest, cutoff=cutoff),
        "short": _scenario("SHORT", upper=upper, lower=lower, atr=float(atr),
                            latest=latest, cutoff=cutoff),
    }
    order = ["long", "short"] if structure["priority"] == "LONG" else ["short", "long"]
    source_projection = {
        "cutoff": cutoff.astimezone(BANGKOK).isoformat(),
        "source_label": source_label, "source_meta": source_meta or {},
        "rows": [{key: row[key] for key in ("at", "open", "high", "low", "close")}
                 for row in normalized],
    }
    source_sha256 = hashlib.sha256(json.dumps(
        source_projection, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    story = {
        "schema": SCHEMA, "asset": ASSET, "timeframe": TIMEFRAME,
        "cutoff": cutoff.astimezone(BANGKOK).isoformat(),
        "latest": {key: latest[key] for key in ("at", "open", "high", "low", "close")},
        "indicators": {"atr14": round(float(atr), 4), "adx14": round(float(adx["adx"]), 4),
                       "previous_adx14": (round(float(adx["previous_adx"]), 4)
                                           if adx.get("previous_adx") is not None else None),
                       "adx_regime": adx["regime"], "adx_rising": adx["rising"]},
        "donchian": {"length": DONCHIAN_LENGTH, "upper": _round_price(upper),
                     "lower": _round_price(lower), "reference_start_index": reference[0]["index"],
                     "reference_end_index": reference[-1]["index"]},
        "pivots": pivots, "structure": structure, "state": "SCENARIOS_READY",
        "scenario_order": order, "scenarios": scenarios,
        "source_label": source_label, "source_meta": source_meta or {},
        "source_sha256": source_sha256,
        "volume_policy": "unavailable-and-forbidden",
    }
    validate(story)
    return {"story": story, "rows": normalized, "source_projection": source_projection}


def validate(story: dict) -> None:
    if story.get("schema") != SCHEMA or story.get("asset") != ASSET:
        raise StoryUnavailable("story schema/asset ไม่ตรง v6")
    if story.get("state") not in STATES:
        raise StoryUnavailable("state ไม่อยู่ใน Style M v6 contract")
    if set(story.get("scenarios", {})) != {"long", "short"}:
        raise StoryUnavailable("ต้องมี Long และ Short scenario ครบ")
    donchian = story.get("donchian", {})
    if donchian.get("length") != DONCHIAN_LENGTH or donchian.get("upper") <= donchian.get("lower"):
        raise StoryUnavailable("Donchian range ไม่ถูกต้อง")
    indicators = story.get("indicators", {})
    atr = _number(indicators.get("atr14"), "atr14")
    if atr <= 0 or indicators.get("adx_regime") not in {"QUIET_RANGE", "TRANSITION", "TRENDING"}:
        raise StoryUnavailable("indicator context ไม่ถูกต้อง")
    long_plan, short_plan = story["scenarios"]["long"], story["scenarios"]["short"]
    if long_plan["trigger"] <= short_plan["trigger"]:
        raise StoryUnavailable("Long trigger ต้องสูงกว่า Short trigger")
    for plan in (long_plan, short_plan):
        if plan["state"] not in SCENARIO_STATES:
            raise StoryUnavailable("scenario state ไม่ถูกต้อง")
        if not plan["sl"] < plan["entry_low"] < plan["entry_high"] < plan["tp1"] < plan["tp2"] and plan["side"] == "LONG":
            raise StoryUnavailable("Long geometry ไม่ถูกต้อง")
        if not plan["tp2"] < plan["tp1"] < plan["entry_low"] < plan["entry_high"] < plan["sl"] and plan["side"] == "SHORT":
            raise StoryUnavailable("Short geometry ไม่ถูกต้อง")
        if plan["rr1"] < MIN_RR1 or plan["rr2"] < MIN_RR2:
            raise StoryUnavailable("RR ต่ำกว่าเกณฑ์")


__all__ = [
    "ASSET", "TIMEFRAME", "SCHEMA", "BANGKOK", "STATES", "SCENARIO_STATES",
    "DONCHIAN_LENGTH", "BREAKOUT_BUFFER_ATR", "ENTRY_ZONE_ATR", "STOP_BUFFER_ATR",
    "MIN_RR1", "MIN_RR2", "StoryUnavailable", "canonical_rows", "atr14_wilder",
    "adx14_wilder", "adx_regime", "confirmed_pivots", "build", "validate",
]
