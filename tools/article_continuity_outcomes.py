"""Bounded native E/L/M plan replay; unknown rules and candle paths withhold claims.

Rows carry Bangkok bar-open timestamps, matching intraday_bars. This module
describes observed conditions only, never fills, profit or reader transactions.
The v6 research simulator is intentionally not used for v7 production rules.
"""
from datetime import datetime, timedelta, timezone
import math

THAI = timezone(timedelta(hours=7))
UNRESOLVED = "ข้อมูลแท่งปิดยังไม่พอยืนยันลำดับเหตุการณ์ของแผนครั้งก่อน"


def _at(value):
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return stamp.replace(tzinfo=THAI) if stamp.tzinfo is None else stamp


def _num(value):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("invalid price")
    return value


def _bars(rows, start, end, minutes):
    span = timedelta(minutes=minutes)
    ordered = []
    for row in rows:
        opening = _at(row["at"])
        stamp = opening + span
        if not start < stamp <= end:
            continue
        if opening.minute % minutes or opening.second or opening.microsecond:
            raise ValueError("off-grid candle timestamp")
        if row.get("forming"):
            raise ValueError("forming evidence")
        values = {key: _num(row[key]) for key in ("open", "high", "low", "close")}
        if not values["low"] <= min(values["open"], values["close"]) <= max(values["open"], values["close"]) <= values["high"]:
            raise ValueError("invalid OHLC")
        ordered.append((stamp, values))
    ordered.sort(key=lambda item: item[0])
    if not ordered or ordered[0][0] - start > span or end - ordered[-1][0] >= span:
        raise ValueError("incomplete coverage")
    if any(b[0] - a[0] != span for a, b in zip(ordered, ordered[1:])):
        raise ValueError("gap or duplicate")
    return ordered


def _cross(previous, close, value, buy):
    return previous <= value < close if buy else previous >= value > close


def _touch(row, value, buy):
    return row["high"] >= value if buy else row["low"] <= value


def _m(story, evidence, cutoff):
    if story.get("contract_version") != "M-PROD/v7" or story.get("state") == "NO_PLAN":
        return None
    rules = story.get("false_breakout", {})
    if rules != {"bull_trap": "next_closed_h1_below_short_trigger",
                 "bear_trap": "next_closed_h1_above_long_trigger",
                 "no_retest_tp1": "cancel_if_tp1_reached_before_retest"}:
        return None
    plans = story["scenarios"]
    if set(plans) != {"long", "short"}:
        return None
    for key, plan in plans.items():
        if plan.get("trigger_rule") != "closed_h1_strict_cross" or plan.get("state") != "WAIT_TRIGGER":
            return None
        if plan["side"] != ("LONG" if key == "long" else "SHORT"):
            return None
        for field in ("trigger", "entry_low", "entry_high", "sl", "tp1", "tp2"):
            _num(plan[field])
    start, expiry = _at(story["cutoff"]), _at(story["valid_until"])
    end = min(_at(cutoff), expiry)
    bars = _bars(evidence["rows"], start, end, 60)
    previous = _num(story["latest"]["close"])
    active = None
    triggered_at = None
    retested = False
    for stamp, row in bars:
        if active is None:
            hits = [key for key, plan in plans.items()
                    if _cross(previous, row["close"], plan["trigger"], key == "long")]
            if len(hits) > 1:
                return UNRESOLVED
            previous = row["close"]
            if hits:
                active = hits[0]
                triggered_at = stamp
            continue  # trigger candle cannot also establish a later retest
        plan = plans[active]
        buy = active == "long"
        stop_hit = _touch(row, plan["sl"], not buy)
        target_hit = _touch(row, plan["tp1"], buy)
        if stop_hit and target_hit:
            return UNRESOLVED
        invalidated = row["close"] <= plan["sl"] if buy else row["close"] >= plan["sl"]
        if invalidated:
            return "แท่งปิดยืนยันเงื่อนไขยกเลิกแผนครั้งก่อนแล้ว และอีกฝั่งถูกยกเลิกตั้งแต่เงื่อนไขแรกยืนยัน"
        if not retested:
            opposite_trigger = plans["short" if buy else "long"]["trigger"]
            trap = row["close"] < opposite_trigger if buy else row["close"] > opposite_trigger
            if trap and stamp == triggered_at + timedelta(hours=1):
                return "แท่งปิดกลับผ่านเงื่อนไขกรอบอีกฝั่งก่อนการกลับทดสอบโซน แผนครั้งก่อนจึงเข้าเงื่อนไขยกเลิก"
            touch_zone = row["low"] <= plan["entry_high"] and row["high"] >= plan["entry_low"]
            if touch_zone and target_hit:
                return UNRESOLVED
            if target_hit:
                return "ราคาถึงเป้าหมายแรกก่อนพบการกลับทดสอบโซน แผนครั้งก่อนจึงเข้าเงื่อนไขยกเลิก"
            if touch_zone:
                if stop_hit:
                    return UNRESOLVED
                retested = True
        elif target_hit:
            return "หลังเงื่อนไขแท่งปิดยืนยันและพบการกลับทดสอบโซน ราคาถึงระดับเป้าหมายแรกของแผนครั้งก่อนแล้ว"
        elif stop_hit:
            return "หลังพบการกลับทดสอบโซน ราคาสัมผัสระดับหยุดขาดทุนของแผนครั้งก่อนแล้ว"
    if end >= expiry:
        return "แผนครั้งก่อนครบกำหนดอายุแล้ว จึงใช้เงื่อนไขของรอบปัจจุบันในการติดตามต่อ"
    if retested:
        return "เงื่อนไขแท่งปิดยืนยันและพบการกลับทดสอบโซนแล้ว โดยอีกฝั่งถูกยกเลิกตามกติกา"
    if active:
        return "เงื่อนไขแท่งปิดยืนยันแล้วและอีกฝั่งถูกยกเลิก แต่ยังไม่พบการกลับทดสอบโซนในแท่งที่ติดตาม"
    return "จากแท่งปิดที่ติดตามครบช่วง ยังไม่มีฝั่งใดยืนยันเงื่อนไขของแผนครั้งก่อน"


def _el(plan, evidence, cutoff, *, style):
    start, expiry = _at(plan["cutoff_at"]), _at(plan["valid_until"])
    end = min(_at(cutoff), expiry)
    minutes = 15 if style == "L" else 60
    source = evidence["rows"]
    bars = _bars(source["15min"] if style == "L" else source, start, end, minutes)
    needs_h1 = end.replace(minute=0, second=0, microsecond=0) > start
    h1 = dict(_bars(source["1h"], start, end, 60)) if style == "L" and needs_h1 else {}
    if any(stamp in h1 and h1[stamp]["close"] != row["close"] for stamp, row in bars):
        return None
    legs = plan["plans"]
    if not legs or len(legs) > 2 or (len(legs) == 2 and plan.get("side") != "OCO"):
        return None
    if any(leg.get("side") not in {"BUY", "SELL"} for leg in legs):
        return None
    if len(legs) == 2 and {leg["side"] for leg in legs} != {"BUY", "SELL"}:
        return None
    if plan.get("status", plan.get("plan_status", "WAIT_TRIGGER")) != "WAIT_TRIGGER":
        return None  # snapshot readiness alone does not prove trigger chronology
    for leg in legs:
        buy = leg["side"] == "BUY"
        expected = ("M15_CLOSE_ABOVE" if buy else "M15_CLOSE_BELOW") if style == "L" else "closed H1 strict cross from latest closed close"
        invalidation = ("H1_CLOSE_BELOW" if buy else "H1_CLOSE_ABOVE") if style == "L" else "closed H1 reaches canonical SL"
        if leg["trigger"]["condition"] != expected or leg["invalidation"]["condition"] != invalidation:
            return None
        for value in [leg["trigger"]["value"], leg["stop_loss"], leg["invalidation"]["value"], *leg["take_profit"]]:
            _num(value)
        if not leg["take_profit"]:
            return None
    previous = _num(plan["current_close"])
    active = None
    available = list(legs)
    for stamp, row in bars:
        if active is None:
            closed = h1.get(stamp) if style == "L" else row
            if closed is not None:
                kept = []
                for leg in available:
                    buy = leg["side"] == "BUY"
                    value = leg["invalidation"]["value"]
                    cancelled = (closed["close"] < value if buy else closed["close"] > value) if style == "L" else (closed["close"] <= value if buy else closed["close"] >= value)
                    if not cancelled:
                        kept.append(leg)
                available = kept
                if not available:
                    return "แท่งปิดยืนยันเงื่อนไขยกเลิกแผนครั้งก่อนก่อนเกิดสัญญาณยืนยัน"
            hits = [leg for leg in available if (
                (row["close"] > leg["trigger"]["value"] if leg["side"] == "BUY" else row["close"] < leg["trigger"]["value"])
                if style == "L" else _cross(previous, row["close"], leg["trigger"]["value"], leg["side"] == "BUY"))]
            if len(hits) > 1:
                return UNRESOLVED
            if hits:
                active = hits[0]
            previous = row["close"]
            continue  # high/low before a close trigger cannot prove subsequent targets
        buy = active["side"] == "BUY"
        stop = _touch(row, active["stop_loss"], not buy)
        target = _touch(row, active["take_profit"][0], buy)
        if stop and target:
            return UNRESOLVED
        closed = h1.get(stamp) if style == "L" else row
        if closed is not None:
            value = active["invalidation"]["value"]
            invalidated = (closed["close"] < value if buy else closed["close"] > value) if style == "L" else (closed["close"] <= value if buy else closed["close"] >= value)
            if invalidated:
                return "แท่งปิดยืนยันเงื่อนไขยกเลิกแผนครั้งก่อนแล้ว"
        if target:
            return "หลังเงื่อนไขแท่งปิดยืนยัน ราคาถึงระดับเป้าหมายแรกของแผนครั้งก่อนแล้ว"
        if stop:
            return "หลังเงื่อนไขแท่งปิดยืนยัน ราคาสัมผัสระดับหยุดขาดทุนของแผนครั้งก่อนแล้ว"
    if end >= expiry:
        return "แผนครั้งก่อนครบกำหนดอายุแล้ว จึงใช้เงื่อนไขของรอบปัจจุบันในการติดตามต่อ"
    return "เงื่อนไขแท่งปิดของแผนครั้งก่อนยืนยันแล้ว" if active else "จากแท่งปิดที่ติดตามครบช่วง ยังไม่ยืนยันเงื่อนไขของแผนครั้งก่อน"


def evaluate(previous_evidence, current_evidence, cutoff):
    """Return a grounded Thai observation, or None when the native rule is unknown."""
    try:
        story = previous_evidence.get("story", {})
        if story.get("contract_version") == "M-PROD/v7":
            return _m(story, current_evidence, cutoff)
        if "scenario" in previous_evidence:
            return _el(previous_evidence["scenario"], current_evidence, cutoff, style="L")
        if "plan" in previous_evidence:
            return _el(previous_evidence["plan"], current_evidence, cutoff, style="E")
    except (KeyError, TypeError, ValueError, IndexError, OverflowError):
        return None
    return None
