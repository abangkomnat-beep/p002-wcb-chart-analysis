"""Deterministic BTCUSD H1-context / M15-execution contract for Style E+.

H1 decides whether a directional bias is strong enough to act on. M15 owns
every execution number (trigger, entry zone, stop and targets). Both inputs
must contain closed WCB candles only; this module never fetches or writes data.
"""

from __future__ import annotations

import math
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from tools import intraday_bars, intraday_indicators, wcb_source
from tools import style_e_plus_adaptive_stop as adaptive_stop

STYLE_ID = "e_plus_h1_m15"
STYLE_NAME = "E+ — H1 Context / M15 Execution"
ASSET = "btcusd"
SYMBOL = "BTC/USD"
H1_TIMEFRAME = "1h"
M15_TIMEFRAME = "15min"
TIMEFRAME = "1h/15min"
MIN_CLOSED_BARS = 240
PERCENTILE_LOOKBACK = 200
ENTRY_HALF_WIDTH_ATR = 0.25
STORY_SCHEMA = "style-e-plus-story/v4"


def _lifecycle_contract() -> dict:
    """Runtime B100 is analysis-only and cannot assert broker execution state."""
    return {
        "mode": "manual_analysis_only",
        "external_fill_evidence_accepted": False,
        "position_confirmed": False,
        "protective_stop_active": False,
    }


class StoryUnavailable(RuntimeError):
    """The source data cannot prove a complete, deterministic E+ story."""


def _number(value, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise StoryUnavailable(f"{label}: ค่าไม่ใช่ตัวเลข") from exc
    if not math.isfinite(result):
        raise StoryUnavailable(f"{label}: ค่าต้องเป็น finite number")
    return result


def _validate_rows(rows: list[dict], *, timeframe: str) -> None:
    if len(rows) < MIN_CLOSED_BARS:
        raise StoryUnavailable(
            f"BTCUSD {timeframe} ต้องมีแท่งปิดอย่างน้อย {MIN_CLOSED_BARS} แท่ง "
            f"(ได้ {len(rows)})")
    previous_at = ""
    for index, row in enumerate(rows):
        at = str(row.get("at") or "")
        if len(at) < 19 or (previous_at and at <= previous_at):
            raise StoryUnavailable(
                f"{timeframe} แท่งลำดับ {index}: เวลาไม่ครบหรือไม่เรียงจากเก่าไปใหม่")
        previous_at = at
        if row.get("forming") or row.get("candle_state") not in {None, "closed"}:
            raise StoryUnavailable(f"{timeframe} แท่ง {at} ยัง forming — ห้ามใช้ใน Style E+")
        opened = _number(row.get("open"), f"{timeframe}.{at}.open")
        high = _number(row.get("high"), f"{timeframe}.{at}.high")
        low = _number(row.get("low"), f"{timeframe}.{at}.low")
        closed = _number(row.get("close"), f"{timeframe}.{at}.close")
        if high < max(opened, closed) or low > min(opened, closed) or high < low:
            raise StoryUnavailable(f"{timeframe} แท่ง {at}: OHLC geometry ไม่ถูกต้อง")


def _ema(values: list[float], length: int) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    if len(values) < length:
        return output
    current = sum(values[:length]) / length
    output[length - 1] = current
    alpha = 2.0 / (length + 1.0)
    for index in range(length, len(values)):
        current = current + alpha * (values[index] - current)
        output[index] = current
    return output


def _percentile(value: float, history: list[float], *, label: str) -> float:
    if len(history) < PERCENTILE_LOOKBACK:
        raise StoryUnavailable(
            f"{label}: percentile ต้องมี {PERCENTILE_LOOKBACK} samples (ได้ {len(history)})")
    window = history[-PERCENTILE_LOOKBACK:]
    return sum(1 for item in window if item <= value) / len(window) * 100.0


def _atr_contract(rows: list[dict]) -> dict:
    result = intraday_indicators.atr(rows, length=14)
    if not intraday_indicators.available(result):
        raise StoryUnavailable("ATR14 unavailable")
    series = [item for item in intraday_indicators.rma(
        intraday_indicators.true_ranges(rows), 14) if item is not None]
    value = _number(result.get("value"), "ATR14")
    return {
        "length": 14,
        "value": value,
        "previous": result.get("previous"),
        "rising": bool(result.get("rising")),
        "percentile": _percentile(value, [float(item) for item in series], label="ATR14"),
        "percentile_samples": PERCENTILE_LOOKBACK,
    }


def _keltner(rows: list[dict], atr_value: float) -> dict:
    closes = [_number(row["close"], "close") for row in rows]
    middle = _ema(closes, 20)[-1]
    if middle is None:
        raise StoryUnavailable("Keltner EMA20 unavailable")
    distance = 1.5 * atr_value
    return {"ema_length": 20, "atr_length": 14, "multiplier": 1.5,
            "middle": float(middle), "upper": float(middle + distance),
            "lower": float(middle - distance)}


def _indicator_contract(rows: list[dict]) -> dict:
    """H1 context indicators approved for the first image."""
    donchian = intraday_indicators.donchian(rows, length=20)
    bbw = intraday_indicators.bollinger_bandwidth(
        rows, length=20, stdev=2.0, percentile_lookback=PERCENTILE_LOOKBACK)
    dmi = intraday_indicators.dmi_adx(rows, length=14)
    for label, result in (("Donchian20", donchian), ("BBW20", bbw), ("DMI/ADX14", dmi)):
        if not intraday_indicators.available(result):
            raise StoryUnavailable(f"{label} unavailable")
    if int(bbw.get("percentile_samples", 0)) != PERCENTILE_LOOKBACK:
        raise StoryUnavailable(
            f"BBW percentile ต้องมี {PERCENTILE_LOOKBACK} samples "
            f"(ได้ {bbw.get('percentile_samples', 0)})")
    atr = _atr_contract(rows)
    return {
        "donchian": {key: deepcopy(donchian[key]) for key in
                     ("length", "upper", "lower", "middle", "width",
                      "excludes_signal_bar")},
        "atr": atr,
        "keltner": _keltner(rows, atr["value"]),
        "bbw": {key: deepcopy(bbw[key]) for key in
                ("length", "stdev", "value", "previous", "rising", "percentile",
                 "percentile_samples")},
        "dmi_adx": {key: deepcopy(dmi[key]) for key in
                    ("length", "plus_di", "minus_di", "adx", "previous_adx", "direction")},
    }


def _m15_indicator_contract(rows: list[dict]) -> dict:
    """Only indicators that directly define or explain the M15 execution map."""
    atr = _atr_contract(rows)
    ema20 = _ema([_number(row["close"], "M15.close") for row in rows], 20)[-1]
    donchian = intraday_indicators.donchian(rows, length=20)
    if ema20 is None or not intraday_indicators.available(donchian):
        raise StoryUnavailable("M15 EMA20/Donchian20 unavailable")
    return {
        "ema20": float(ema20),
        "atr": atr,
        "donchian": {key: deepcopy(donchian[key]) for key in
                     ("length", "upper", "lower", "middle", "width",
                      "excludes_signal_bar")},
    }


def _h1_bias(indicators: dict) -> tuple[str | None, str]:
    dmi = indicators["dmi_adx"]
    if dmi["adx"] < 20 or math.isclose(dmi["plus_di"], dmi["minus_di"], abs_tol=1e-12):
        return None, "H1 ยังไม่มีแรงแนวโน้มที่ยืนยันได้จาก ADX และ DI"
    side = "buy" if dmi["plus_di"] > dmi["minus_di"] else "sell"
    volatility_gaps = []
    if indicators["bbw"]["percentile"] < 50:
        volatility_gaps.append(
            f"BandWidth percentile {indicators['bbw']['percentile']:.1f}% ต่ำกว่า 50%")
    if indicators["atr"]["percentile"] < 50:
        volatility_gaps.append(
            f"ATR14 percentile {indicators['atr']['percentile']:.1f}% ต่ำกว่า 50%")
    if volatility_gaps:
        return None, "ความผันผวน H1 ยังไม่ผ่านเกณฑ์: " + " และ ".join(volatility_gaps)
    dc, kc = indicators["donchian"], indicators["keltner"]
    if side == "buy" and dc["upper"] < kc["upper"]:
        return None, "โครง Donchian H1 ฝั่งซื้อยังไม่พ้น Keltner"
    if side == "sell" and dc["lower"] > kc["lower"]:
        return None, "โครง Donchian H1 ฝั่งขายยังไม่พ้น Keltner"
    return side, f"H1 ให้น้ำหนัก{('ฝั่งซื้อ' if side == 'buy' else 'ฝั่งขาย')}"


def _m15_effective_from(bar_at: str) -> str:
    """The plan only exists after its closed M15 creation bar has ended."""
    try:
        opened_at = intraday_bars.parse_at(bar_at)
    except (TypeError, ValueError) as exc:
        raise StoryUnavailable("M15.bar_at แปลงเวลาไม่ได้") from exc
    return (opened_at + timedelta(minutes=15)).isoformat()


def _canonical_utc_at(value: str) -> str:
    """Canonicalize a feed row timestamp for the hashed decision context."""
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise StoryUnavailable("M15 timestamp แปลงเป็น UTC ไม่ได้") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=wcb_source.BANGKOK)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _m15_decision(indicators: dict, close: float, side: str | None, *,
                  plan_created_at: str, context: dict) -> tuple[str, dict | None, str, dict]:
    """Apply the unchanged EMA20 gate, then the B100 stop geometry."""
    adaptive_meta = {
        "evaluated": False, "accepted": False, "pivot_index": None,
        "pivot_at": None, "pivot_price": None, "raw_stop": None,
        "raw_risk_atr": None, "risk_atr": None, "final_stop": None,
        "floor_applied": False, "donchian_boundary": None,
        "target_space_r": None, "constants_version": "B100/v1",
    }
    if side is None:
        return "NO_PLAN", None, "H1 ยังไม่ให้ bias จึงไม่สร้างจุดเข้า M15", adaptive_meta
    atr = _number(indicators["atr"]["value"], "M15.ATR14")
    ema20 = _number(indicators["ema20"], "M15.EMA20")
    half_width = ENTRY_HALF_WIDTH_ATR * atr
    zone_low, zone_high = ema20 - half_width, ema20 + half_width
    if side == "buy":
        disadvantaged = zone_high
        sign = 1.0
        beyond = close > zone_high
        confirmed = close > ema20
    else:
        disadvantaged = zone_low
        sign = -1.0
        beyond = close < zone_low
        confirmed = close < ema20
    if beyond:
        return "NO_CHASE", None, "ราคา M15 เลย Entry Zone แล้ว จึงไม่ไล่ราคา", adaptive_meta
    adaptive_meta["evaluated"] = True
    result = adaptive_stop.adaptive_plan(
        context["rows"], decision_index=context["count"] - 1, side=side,
        entry_low=zone_low, entry_high=zone_high, atr=atr)
    pivot = result.get("pivot")
    if pivot:
        adaptive_meta.update({
            "pivot_index": pivot["index"],
            "pivot_at": context["rows"][pivot["index"]]["at"],
            "pivot_price": pivot["price"],
        })
    for source, target in (("raw_stop", "raw_stop"), ("raw_risk_atr", "raw_risk_atr"),
                           ("risk_atr", "risk_atr"), ("floor_applied", "floor_applied")):
        if source in result:
            adaptive_meta[target] = result[source]
    if result.get("target_space"):
        adaptive_meta["donchian_boundary"] = result["target_space"].get("boundary")
        adaptive_meta["target_space_r"] = result["target_space"].get("space_r")
    adaptive_meta["raw_stop"] = result.get("raw_stop", adaptive_meta["raw_stop"])
    adaptive_meta["final_stop"] = (result.get("plan") or {}).get("stop")
    if not result.get("accepted"):
        reason = result.get("reason") or "NO_CONFIRMED_SWING"
        adaptive_meta["accepted"] = False
        return "NO_PLAN", None, f"B100 ยังไม่สร้างแผน: {reason}", adaptive_meta
    adaptive_meta["accepted"] = True
    bplan = result["plan"]
    adaptive_meta.update({
        "pivot_index": bplan["pivot"]["index"],
        "pivot_at": context["rows"][bplan["pivot"]["index"]]["at"],
        "pivot_price": bplan["pivot"]["price"],
        "raw_stop": bplan["raw_stop"],
        "raw_risk_atr": bplan["raw_risk_atr"],
        "risk_atr": bplan["risk_atr"],
        "floor_applied": bplan["floor_applied"],
        "donchian_boundary": bplan["donchian_boundary"],
        "target_space_r": bplan["target_space_r"],
    })
    stop = bplan["stop"]
    risk = bplan["risk"]
    adaptive_meta["final_stop"] = stop
    invalidated = close <= stop if side == "buy" else close >= stop
    if invalidated:
        return "NO_PLAN", None, "ราคา M15 ปิดพ้นจุดยกเลิกก่อนเกิดสัญญาณเข้า", adaptive_meta
    state = "ENTRY_READY" if confirmed else "WAIT_TRIGGER"
    plan = {
        "variant": "B",
        "side": side,
        "timeframe": M15_TIMEFRAME,
        "plan_created_at": plan_created_at,
        "effective_from": plan_created_at,
        "trigger": ema20,
        "trigger_rule": "close_above_ema20" if side == "buy" else "close_below_ema20",
        "entry_zone_low": zone_low,
        "entry_zone_high": zone_high,
        "pre_entry_invalidation_close": stop,
        "pre_entry_invalidation_rule": (
            "m15_close_at_or_below_level_after_effective_from"
            if side == "buy" else
            "m15_close_at_or_above_level_after_effective_from"
        ),
        "protective_stop": {
            "price": stop,
            "active": False,
            "status": "inactive_until_external_fill",
            "activation_event": "external_entry_fill",
            "effective_from": None,
        },
        "disadvantaged_entry": disadvantaged,
        "risk": risk,
        "tp1": disadvantaged + sign * 1.5 * risk,
        "tp2": disadvantaged + sign * 2.0 * risk,
        "rr1": 1.5,
        "rr2": 2.0,
        "trigger_confirmed": state == "ENTRY_READY",
        "raw_stop": bplan["raw_stop"],
        "risk_atr": bplan["risk_atr"],
        "raw_risk_atr": bplan["raw_risk_atr"],
        "floor_applied": bplan["floor_applied"],
        "sizing_multiplier": bplan["sizing_multiplier"],
        "normalized_risk_ratio": bplan["normalized_risk_ratio"],
        "sizing_basis": bplan["sizing_basis"],
        "manual_only": bplan["manual_only"],
        "pivot": bplan["pivot"],
        "structure_buffer_atr": bplan["structure_buffer_atr"],
        "donchian_boundary": bplan["donchian_boundary"],
        "target_space_r": bplan["target_space_r"],
        "decision_index": bplan["decision_index"],
        "prefix_end_index": bplan["prefix_end_index"],
    }
    reason = ("แท่ง M15 ปิดยืนยัน EMA20 และราคายังอยู่ใน Entry Zone แต่ยังไม่มีหลักฐาน fill"
              if state == "ENTRY_READY"
              else "รอแท่ง M15 ปิดกลับผ่าน EMA20 ภายใน Entry Zone")
    return state, plan, reason, adaptive_meta


def _same_plan(actual: dict | None, expected: dict | None) -> None:
    if expected is None:
        if actual is not None:
            raise StoryUnavailable("NO_PLAN/NO_CHASE ต้องไม่มี Entry/SL/TP")
        return
    if not isinstance(actual, dict) or set(actual) != set(expected):
        raise StoryUnavailable("plan schema M15 ไม่ครบ")
    for key, expected_value in expected.items():
        value = actual[key]
        if isinstance(expected_value, float):
            if not math.isclose(_number(value, key), expected_value, rel_tol=0, abs_tol=1e-12):
                raise StoryUnavailable(f"plan.{key} ไม่ตรงสูตร M15")
        elif value != expected_value:
            raise StoryUnavailable(f"plan.{key} ไม่ตรงสูตร M15")


def validate_story(story: dict, *, now: datetime | None = None) -> None:
    """Recalculate the dual-timeframe decision and reject altered artifacts."""
    if story.get("schema") != STORY_SCHEMA:
        raise StoryUnavailable("รุ่น story schema ไม่ตรง Style E+ lifecycle v4")
    if story.get("asset") != ASSET or story.get("timeframe") != TIMEFRAME:
        raise StoryUnavailable("Style E+ รับเฉพาะ BTCUSD H1/M15")
    if story.get("wcb_tag") != "btc" or wcb_source.tag_for(ASSET) != "btc":
        raise StoryUnavailable("WCB tag ของ BTCUSD ต้องเป็น btc")
    bases = story.get("candle_basis")
    if not isinstance(bases, dict):
        raise StoryUnavailable("story ขาดหลักฐานแท่งปิด H1/M15")
    for key, timeframe, bar_key in (("h1", H1_TIMEFRAME, "bar_at"),
                                    ("m15", M15_TIMEFRAME, "m15_bar_at")):
        basis = bases.get(key)
        if not isinstance(basis, dict) or basis.get("candle_state") != "closed":
            raise StoryUnavailable(f"candle basis {key} ต้องระบุ closed")
        basis_bar_at = str(basis.get("basis_bar_at") or "")
        if key == "m15":
            if _canonical_utc_at(basis_bar_at) != story.get(bar_key):
                raise StoryUnavailable("ฐานแท่ง M15 ไม่ตรงกับ canonical adaptive context")
            verify_bar_at = basis_bar_at
        else:
            verify_bar_at = str(story.get(bar_key) or "")
        detail = intraday_bars.verify(
            basis, asset=ASSET, bar_at=verify_bar_at, now=now)
        if detail or basis.get("timeframe") != timeframe:
            raise StoryUnavailable(detail or f"candle basis {key} ใช้ timeframe ผิด")
    context = story.get("adaptive_context")
    try:
        context_rows = adaptive_stop.validate_context(context)
    except adaptive_stop.AdaptiveStopError as exc:
        raise StoryUnavailable(str(exc)) from exc
    if context["window"]["decision_at"] != story.get("m15_bar_at"):
        raise StoryUnavailable("adaptive context decision_at ไม่ตรง m15_bar_at")
    if _canonical_utc_at(bases["m15"].get("basis_bar_at")) != context["window"]["decision_at"]:
        raise StoryUnavailable("adaptive context ไม่ตรงกับ basis M15")
    plan_created_at = str(bases["m15"].get("basis_close_at") or "")
    if not plan_created_at:
        raise StoryUnavailable("candle basis M15 ขาด basis_close_at")
    if bases["m15"].get("basis_close_at") != plan_created_at:
        raise StoryUnavailable("candle basis M15 ระบุเวลาปิดไม่ตรง creation bar")
    if story.get("lifecycle") != _lifecycle_contract():
        raise StoryUnavailable("lifecycle ต้องเป็น manual analysis ที่ยังไม่ยืนยัน position")
    indicators = story.get("indicators") or {}
    for key in ("donchian", "atr", "keltner", "bbw", "dmi_adx"):
        if not isinstance(indicators.get(key), dict):
            raise StoryUnavailable(f"story ขาด H1 indicator {key}")
    m15 = story.get("m15") or {}
    m15_indicators = m15.get("indicators") or {}
    for key in ("ema20", "atr", "donchian"):
        if key not in m15_indicators:
            raise StoryUnavailable(f"story ขาด M15 indicator {key}")
    side, bias_reason = _h1_bias(indicators)
    close = _number((m15.get("current") or {}).get("close"), "M15.close")
    if abs(close - context_rows[-1]["close"]) > 1e-12:
        raise StoryUnavailable("M15 current.close ไม่ตรงกับ adaptive context decision row")
    state, plan, execution_reason, adaptive_meta = _m15_decision(
        m15_indicators, close, side, plan_created_at=plan_created_at,
        context=context)
    if story.get("state") != state or story.get("side") != side:
        raise StoryUnavailable("state/side ไม่ตรงกฎ H1 bias + M15 execution")
    if story.get("bias_reason") != bias_reason or story.get("decision_reason") != execution_reason:
        raise StoryUnavailable("เหตุผลการตัดสินไม่ตรงกฎ deterministic")
    _same_plan(story.get("plan"), plan)
    expected_reason = None
    if adaptive_meta["evaluated"] and not adaptive_meta["accepted"]:
        expected_reason = execution_reason.rsplit(": ", 1)[-1]
    if story.get("adaptive_reason_code") != expected_reason:
        raise StoryUnavailable("adaptive_reason_code ไม่ตรง lifecycle/B rejection")
    expected_adaptive = adaptive_meta
    actual_adaptive = story.get("adaptive_stop")
    if actual_adaptive != expected_adaptive:
        raise StoryUnavailable("adaptive_stop ไม่ตรงผล recompute B100")
    images = story.get("images") or {}
    if set(images) != {"h1", "m15"} or len(set(images.values())) != 2:
        raise StoryUnavailable("Style E+ H1/M15 ต้องมีชื่อภาพไม่ซ้ำกัน 2 ภาพ")


def build(h1_rows: list[dict], m15_rows: list[dict], *, asset: str = ASSET,
          candle_basis: dict, m15_candle_basis: dict,
          publish_date: str | None = None, now: datetime | None = None) -> dict:
    if asset != ASSET:
        raise StoryUnavailable("Style E+ รับเฉพาะ asset=btcusd")
    if wcb_source.tag_for(asset) != "btc":
        raise StoryUnavailable("WCB request tag ของ BTCUSD ต้องเป็น btc")
    _validate_rows(h1_rows, timeframe="H1")
    _validate_rows(m15_rows, timeframe="M15")
    for basis, rows, timeframe in ((candle_basis, h1_rows, H1_TIMEFRAME),
                                   (m15_candle_basis, m15_rows, M15_TIMEFRAME)):
        if not isinstance(basis, dict) or basis.get("candle_state") != "closed":
            raise StoryUnavailable(f"ข้อมูลไม่มีหลักฐานแท่ง {timeframe} ปิด")
        detail = intraday_bars.verify(basis, asset=asset, bar_at=str(rows[-1]["at"]), now=now)
        if detail or basis.get("timeframe") != timeframe:
            raise StoryUnavailable(detail or f"หลักฐานใช้ timeframe ผิด: {timeframe}")

    indicators = _indicator_contract(h1_rows)
    m15_indicators = _m15_indicator_contract(m15_rows)
    side, bias_reason = _h1_bias(indicators)
    m15_close = _number(m15_rows[-1]["close"], "M15.current.close")
    context = adaptive_stop.build_context(m15_rows)
    plan_created_at = str(m15_candle_basis.get("basis_close_at") or
                          _m15_effective_from(str(m15_rows[-1]["at"])))
    state, plan, decision_reason, adaptive_meta = _m15_decision(
        m15_indicators, m15_close, side, plan_created_at=plan_created_at,
        context=context)
    date_text = publish_date or datetime.now(tz=wcb_source.BANGKOK).strftime("%Y-%m-%d")
    images = {
        "h1": f"btcusd-eplus-h1-context-{date_text}.webp",
        "m15": f"btcusd-eplus-m15-execution-{date_text}.webp",
    }
    story = {
        "schema": STORY_SCHEMA,
        "style": STYLE_ID,
        "style_name": STYLE_NAME,
        "asset": asset,
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "timeframes": {"context": H1_TIMEFRAME, "execution": M15_TIMEFRAME},
        "wcb_tag": "btc",
        "publish_date": date_text,
        "bar_at": str(h1_rows[-1]["at"]),
        "m15_bar_at": context["window"]["decision_at"],
        "candle_basis": {"h1": deepcopy(candle_basis), "m15": deepcopy(m15_candle_basis)},
        "state": state,
        "side": side,
        "lifecycle": _lifecycle_contract(),
        "current": {"date": h1_rows[-1].get("date", str(h1_rows[-1]["at"])[:10]),
                    "at": str(h1_rows[-1]["at"]),
                    "open": _number(h1_rows[-1]["open"], "H1.open"),
                    "high": _number(h1_rows[-1]["high"], "H1.high"),
                    "low": _number(h1_rows[-1]["low"], "H1.low"),
                    "close": _number(h1_rows[-1]["close"], "H1.close")},
        "indicators": indicators,
        "m15": {
            "bar_at": context["window"]["decision_at"],
            "current": {"date": m15_rows[-1].get("date", str(m15_rows[-1]["at"])[:10]),
                        "at": context["window"]["decision_at"],
                        "open": _number(m15_rows[-1]["open"], "M15.open"),
                        "high": _number(m15_rows[-1]["high"], "M15.high"),
                        "low": _number(m15_rows[-1]["low"], "M15.low"),
                        "close": m15_close},
            "indicators": m15_indicators,
        },
        "plan": plan,
        "adaptive_context": context,
        "adaptive_reason_code": (None if adaptive_meta["accepted"] or
                                  not adaptive_meta["evaluated"] else
                                  decision_reason.rsplit(": ", 1)[-1]),
        "adaptive_stop": adaptive_meta,
        "bias_reason": bias_reason,
        "decision_reason": decision_reason,
        "images": images,
        "image_name": images["h1"],
    }
    validate_story(story, now=now)
    return story


build_story = build
