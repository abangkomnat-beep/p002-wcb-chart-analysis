"""Deterministic BTCUSD H1 decision oracle for Style M."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


ASSET = "btcusd"
TIMEFRAME = "1h"
SCHEMA = "style-m-story/v1"
BANGKOK = ZoneInfo("Asia/Bangkok")
STATES = ("NO_PLAN", "WAIT_H1_CONFIRM", "PLAN_VALID", "INVALIDATED")


class StoryUnavailable(RuntimeError):
    """Closed H1 evidence cannot support a Style M story."""


def _number(value, label: str) -> float:
    try:
        output = float(value)
    except (TypeError, ValueError) as exc:
        raise StoryUnavailable(f"{label} ไม่ใช่ตัวเลข") from exc
    if not math.isfinite(output):
        raise StoryUnavailable(f"{label} ไม่เป็น finite")
    return output


def _at(value: str) -> datetime:
    try:
        return datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=BANGKOK)
    except ValueError as exc:
        raise StoryUnavailable(f"เวลาแท่ง H1 ไม่ถูกต้อง: {value}") from exc


def canonical_rows(rows: list[dict], *, cutoff: datetime) -> list[dict]:
    if cutoff.tzinfo is None:
        raise StoryUnavailable("cutoff ต้องมี timezone")
    limit = cutoff.astimezone(BANGKOK)
    normalized: list[dict] = []
    previous: datetime | None = None
    for index, raw in enumerate(rows or []):
        stamp = _at(raw.get("at"))
        if stamp + timedelta(hours=1) > limit:
            continue
        if previous is not None and stamp <= previous:
            raise StoryUnavailable("แท่ง H1 ต้องเรียงเวลาและไม่ซ้ำ")
        values = {key: _number(raw.get(key), f"rows[{index}].{key}")
                  for key in ("open", "high", "low", "close")}
        if not values["low"] <= min(values["open"], values["close"]) \
                <= max(values["open"], values["close"]) <= values["high"]:
            raise StoryUnavailable("OHLC envelope ไม่ถูกต้อง")
        normalized.append({"index": len(normalized), "at": stamp.strftime("%Y-%m-%d %H:%M:%S"),
                           **values})
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


def ema(values: list[float], period: int) -> list[float]:
    alpha = 2.0 / (period + 1.0)
    output = [float(values[0])]
    for value in values[1:]:
        output.append(alpha * float(value) + (1.0 - alpha) * output[-1])
    return output


def atr14_wilder(rows: list[dict]) -> list[float | None]:
    true_ranges: list[float] = []
    for index, row in enumerate(rows):
        high, low = row["high"], row["low"]
        if index == 0:
            true_ranges.append(high - low)
        else:
            previous = rows[index - 1]["close"]
            true_ranges.append(max(high - low, abs(high - previous), abs(low - previous)))
    output: list[float | None] = [None] * len(rows)
    if len(rows) > 14:
        output[14] = sum(true_ranges[1:15]) / 14.0
        for index in range(15, len(rows)):
            output[index] = (float(output[index - 1]) * 13.0 + true_ranges[index]) / 14.0
    return output


def confirmed_pivots(rows: list[dict]) -> dict:
    highs: list[dict] = []
    lows: list[dict] = []
    for index in range(2, len(rows) - 2):
        neighbors = (index - 2, index - 1, index + 1, index + 2)
        if all(rows[index]["high"] > rows[item]["high"] for item in neighbors):
            highs.append({"index": index, "at": rows[index]["at"], "price": rows[index]["high"]})
        if all(rows[index]["low"] < rows[item]["low"] for item in neighbors):
            lows.append({"index": index, "at": rows[index]["at"], "price": rows[index]["low"]})
    return {"highs": highs, "lows": lows}


def _no_plan(reason: str, *, detail: str = "") -> dict:
    return {"state": "NO_PLAN", "side": None, "reason_code": reason,
            "reason": detail or reason, "show_plan_geometry": False, "plan": None}


ENTRY_ZONE_ATR = 0.25
STOP_BUFFER_ATR = 0.75
MIN_RR1 = 1.5
MIN_RR2 = 2.0


def decide(rows: list[dict], *, ema20: float, ema50: float, atr14: float,
           pivots: dict) -> dict:
    latest = rows[-1]
    highs, lows = pivots["highs"], pivots["lows"]
    if atr14 <= 0 or len(highs) < 2 or len(lows) < 2:
        return _no_plan("INSUFFICIENT_STRUCTURE", detail="โครงสร้างหรือ ATR ยังไม่พอสร้างแผน")
    hprev, hlast = highs[-2], highs[-1]
    lprev, llast = lows[-2], lows[-1]
    latest_time = _at(latest["at"])
    anchors = (hprev, hlast, lprev, llast)
    ages = [(latest_time - _at(item["at"])).total_seconds() / 3600.0 for item in anchors]
    if any(age < 0 or age > 72 for age in ages):
        return _no_plan("STALE_STRUCTURE", detail="จุดโครงสร้างล่าสุดเก่าเกินเกณฑ์ 72 ชั่วโมง")
    buy = (hprev["index"] < llast["index"] < hlast["index"] and
           hlast["price"] > hprev["price"] and llast["price"] > lprev["price"] and
           ema20 > ema50 and latest["close"] > ema50 and ages[3] <= 24)
    sell = (lprev["index"] < hlast["index"] < llast["index"] and
            hlast["price"] < hprev["price"] and llast["price"] < lprev["price"] and
            ema20 < ema50 and latest["close"] < ema50 and ages[1] <= 24)
    if buy == sell:
        return _no_plan("STRUCTURE_CONFLICT", detail="โครงสร้างและเส้นเฉลี่ยยังไม่ให้ทิศเดียวกัน")
    width = ENTRY_ZONE_ATR * atr14
    stop_buffer = STOP_BUFFER_ATR * atr14
    if buy:
        side = "BUY"
        entry_low, entry_high = llast["price"], llast["price"] + width
        stop, tp1, tp2 = llast["price"] - stop_buffer, hprev["price"], hlast["price"]
        if not stop < entry_low < entry_high < tp1 < tp2:
            return _no_plan("INVALID_GEOMETRY", detail="ระดับฝั่งซื้อเรียงตัวไม่ถูกต้อง")
        risk = entry_high - stop
        rr1, rr2 = (tp1 - entry_high) / risk, (tp2 - entry_high) / risk
        dynamic_entry_limit = min(
            (tp1 + MIN_RR1 * stop) / (1.0 + MIN_RR1),
            (tp2 + MIN_RR2 * stop) / (1.0 + MIN_RR2),
        )
        invalidated = latest["close"] <= stop
        target_passed = latest["close"] >= tp1
    else:
        side = "SELL"
        entry_low, entry_high = hlast["price"] - width, hlast["price"]
        stop, tp1, tp2 = hlast["price"] + stop_buffer, lprev["price"], llast["price"]
        if not tp2 < tp1 < entry_low < entry_high < stop:
            return _no_plan("INVALID_GEOMETRY", detail="ระดับฝั่งขายเรียงตัวไม่ถูกต้อง")
        risk = stop - entry_low
        rr1, rr2 = (entry_low - tp1) / risk, (entry_low - tp2) / risk
        dynamic_entry_limit = max(
            (tp1 + MIN_RR1 * stop) / (1.0 + MIN_RR1),
            (tp2 + MIN_RR2 * stop) / (1.0 + MIN_RR2),
        )
        invalidated = latest["close"] >= stop
        target_passed = latest["close"] <= tp1
    if rr1 < MIN_RR1 or rr2 < MIN_RR2:
        return _no_plan("RR_TOO_LOW", detail="RR ต่ำกว่าเกณฑ์ขั้นต่ำ")
    plan = {"entry_low": round(entry_low, 2), "entry_high": round(entry_high, 2),
            "sl": round(stop, 2), "tp1": round(tp1, 2), "tp2": round(tp2, 2),
            "rr1": round(rr1, 4), "rr2": round(rr2, 4), "atr14": round(atr14, 4),
            "min_rr1": MIN_RR1, "min_rr2": MIN_RR2,
            "dynamic_entry_limit": round(dynamic_entry_limit, 2),
            "entry_zone_atr": ENTRY_ZONE_ATR, "stop_buffer_atr": STOP_BUFFER_ATR,
            "worst_entry_risk_atr": round(risk / atr14, 4),
            "anchors": {"hprev": hprev, "hlast": hlast, "lprev": lprev, "llast": llast}}
    if invalidated:
        return {"state": "INVALIDATED", "side": side, "reason_code": "STOP_INVALIDATED",
                "reason": "แท่ง H1 ปิดพ้นระดับยกเลิกแผน", "show_plan_geometry": False,
                "plan": None, "invalidated_plan": plan}
    if target_passed:
        return _no_plan("TARGET_PASSED", detail="ราคาผ่าน TP1 ก่อนเกิดจังหวะใหม่ ห้ามไล่ราคา")
    nearest = (0.0 if entry_low <= latest["close"] <= entry_high else
               min(abs(latest["close"] - entry_low), abs(latest["close"] - entry_high)))
    if nearest > atr14:
        return _no_plan("PRICE_EXTENDED", detail="ราคาห่าง Entry เกิน 1 ATR ห้ามไล่ราคา")
    # Confirmation depends on the closed H1 price crossing the boundary, not
    # candle colour. Execution is a separate retest step handled by the writer.
    confirmed = ((side == "BUY" and latest["close"] > entry_high) or
                 (side == "SELL" and latest["close"] < entry_low))
    state = "PLAN_VALID" if confirmed else "WAIT_H1_CONFIRM"
    return {"state": state, "side": side, "reason_code": "PLAN_VALID",
            "reason": ("แท่ง H1 ปิดยืนยันตามเงื่อนไข" if confirmed
                       else "รอแท่ง H1 ปิดยืนยันใน/หลังโซน Entry"),
            "show_plan_geometry": True, "plan": plan}


def build(rows: list[dict], *, cutoff: datetime, source_label: str,
          source_meta: dict | None = None) -> dict:
    normalized = canonical_rows(rows, cutoff=cutoff)
    closes = [row["close"] for row in normalized]
    ema20_value = ema(closes, 20)[-1]
    ema50_value = ema(closes, 50)[-1]
    atr_value = atr14_wilder(normalized)[-1]
    if atr_value is None:
        raise StoryUnavailable("ATR14 คำนวณไม่ได้")
    pivot_map = confirmed_pivots(normalized)
    decision = decide(normalized, ema20=ema20_value, ema50=ema50_value,
                      atr14=float(atr_value), pivots=pivot_map)
    source_projection = {"cutoff": cutoff.astimezone(BANGKOK).isoformat(),
                         "source_label": source_label, "source_meta": source_meta or {},
                         "rows": [{k: row[k] for k in ("at", "open", "high", "low", "close")}
                                  for row in normalized]}
    source_hash = hashlib.sha256(json.dumps(source_projection, sort_keys=True,
                                            ensure_ascii=False).encode("utf-8")).hexdigest()
    story = {"schema": SCHEMA, "asset": ASSET, "timeframe": TIMEFRAME,
             "cutoff": cutoff.astimezone(BANGKOK).isoformat(),
             "latest": {k: normalized[-1][k] for k in ("at", "open", "high", "low", "close")},
             "indicators": {"ema20": round(ema20_value, 4), "ema50": round(ema50_value, 4),
                            "atr14": round(float(atr_value), 4)},
             "pivots": pivot_map, "source_label": source_label,
             "source_meta": source_meta or {}, "source_sha256": source_hash,
             "volume_policy": "unavailable-and-forbidden", **decision}
    validate(story)
    return {"story": story, "rows": normalized, "source_projection": source_projection}


def validate(story: dict) -> None:
    if story.get("schema") != SCHEMA or story.get("asset") != ASSET:
        raise StoryUnavailable("story contract ไม่ตรง Style M")
    if story.get("state") not in STATES:
        raise StoryUnavailable("state ไม่อยู่ใน Style M contract")
    plan = story.get("plan")
    if story["state"] in ("NO_PLAN", "INVALIDATED") and plan is not None:
        raise StoryUnavailable("NO PLAN/INVALIDATED ต้องไม่มี active Entry/SL/TP")
    if story["state"] in ("WAIT_H1_CONFIRM", "PLAN_VALID"):
        if not story.get("side") or not story.get("show_plan_geometry") or not plan:
            raise StoryUnavailable("active setup ขาด side หรือ plan geometry")
        for key in ("entry_low", "entry_high", "sl", "tp1", "tp2", "rr1", "rr2",
                    "min_rr1", "min_rr2", "dynamic_entry_limit",
                    "entry_zone_atr", "stop_buffer_atr", "worst_entry_risk_atr"):
            _number(plan.get(key), f"plan.{key}")
        if plan["entry_zone_atr"] != ENTRY_ZONE_ATR:
            raise StoryUnavailable("active setup ใช้ Entry ATR ไม่ตรง contract")
        if plan["stop_buffer_atr"] != STOP_BUFFER_ATR:
            raise StoryUnavailable("active setup ใช้ SL ATR ไม่ตรง contract")
        if abs(plan["worst_entry_risk_atr"] - 1.0) > 0.0001:
            raise StoryUnavailable("active setup ต้องเสี่ยง 1 ATR จากขอบ Entry ที่เสียเปรียบที่สุด")
        if plan["min_rr1"] != MIN_RR1 or plan["min_rr2"] != MIN_RR2:
            raise StoryUnavailable("เกณฑ์ RR ขั้นต่ำไม่ตรง contract")
        if story["side"] == "BUY":
            expected_limit = min(
                (plan["tp1"] + MIN_RR1 * plan["sl"]) / (1.0 + MIN_RR1),
                (plan["tp2"] + MIN_RR2 * plan["sl"]) / (1.0 + MIN_RR2),
            )
        else:
            expected_limit = max(
                (plan["tp1"] + MIN_RR1 * plan["sl"]) / (1.0 + MIN_RR1),
                (plan["tp2"] + MIN_RR2 * plan["sl"]) / (1.0 + MIN_RR2),
            )
        if abs(plan["dynamic_entry_limit"] - expected_limit) > 0.011:
            raise StoryUnavailable("ขีดจำกัดราคาเข้าจริงไม่ตรงสูตร RR")


__all__ = ["ASSET", "BANGKOK", "ENTRY_ZONE_ATR", "MIN_RR1", "MIN_RR2",
           "SCHEMA", "STATES",
           "STOP_BUFFER_ATR", "StoryUnavailable",
           "build", "canonical_rows", "confirmed_pivots", "decide", "validate"]
