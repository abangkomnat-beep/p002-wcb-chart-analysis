"""Level engine — Pivot ไม่ใช่แหล่งระดับราคาเพียงแหล่งเดียวอีกต่อไป

รองรับ: previous day/week high-low · swing high-low · moving average ที่ผ่านขั้นต่ำ ·
ATR projection · Classic Pivot — พร้อมรวมระดับที่ชิดกันเป็นโซนและตรวจว่า target มีที่มาจริง
"""

from __future__ import annotations

from datetime import date


SUPPORT = "support"
RESISTANCE = "resistance"
BIAS_DIVIDER = "bias_divider"

WATCHLIST = "watchlist"
DAILY_SCENARIO = "daily_scenario"
TRADE_SETUP = "trade_setup"


def _level(
    *,
    identifier: str,
    label: str,
    kind: str,
    value: float | None = None,
    zone_low: float | None = None,
    zone_high: float | None = None,
    timeframe: str = "1d",
    role: str,
    source_field: str,
    basis_timestamp: str | None,
    calculation_method: str,
    quality_status: str = "valid",
) -> dict:
    return {
        "id": identifier,
        "label": label,
        "type": kind,
        "value": value,
        "zone_low": zone_low,
        "zone_high": zone_high,
        "timeframe": timeframe,
        "role": role,
        "source_field": source_field,
        "basis_timestamp": basis_timestamp,
        "calculation_method": calculation_method,
        "quality_status": quality_status,
        "approved_for_publication": quality_status == "valid",
    }


def _role_for(value: float, reference: float) -> str:
    return RESISTANCE if value > reference else SUPPORT


def previous_week_candles(valid_candles: list[dict], *, anchor_date: str | None = None) -> list[dict]:
    """แท่งของสัปดาห์ ISO ก่อนหน้าสัปดาห์ของ session ปัจจุบัน

    anchor_date = วันที่ของ session ปัจจุบัน (แท่งที่กำลังก่อตัว) — **ต้องส่งมาเสมอ**
    ในการใช้งานจริง ถ้าไม่ส่ง จะถอยไปใช้แท่งปิดล่าสุดซึ่งให้ผลผิดในวันแรกของสัปดาห์

    เหตุผล: วันจันทร์ แท่งที่ปิดแล้วตัวล่าสุดคือวันศุกร์ซึ่งยังอยู่ "สัปดาห์ที่แล้ว"
    ถ้าใช้แท่งนั้นเป็นจุดอ้าง ระบบจะเข้าใจว่าสัปดาห์ที่แล้วคือสัปดาห์ปัจจุบัน แล้วถอย
    ไปหยิบสัปดาห์ก่อนหน้านั้นอีกที = ได้ระดับของเมื่อสองสัปดาห์ก่อน และ High/Low
    ของสัปดาห์ที่แล้วจริง ๆ หายไปจากตารางแนวรับแนวต้านเงียบ ๆ (พบ 2026-08-04)
    """
    if not valid_candles:
        return []
    anchor = anchor_date or valid_candles[-1]["session_date"]
    current_week = date.fromisoformat(str(anchor)[:10]).isocalendar()[:2]
    weeks: dict[tuple, list[dict]] = {}
    for candle in valid_candles:
        key = date.fromisoformat(candle["session_date"]).isocalendar()[:2]
        weeks.setdefault(key, []).append(candle)
    earlier = sorted(key for key in weeks if key < current_week)
    return weeks[earlier[-1]] if earlier else []


def find_swings(valid_candles: list[dict], *, window: int = 3) -> tuple[dict | None, dict | None]:
    """หา swing high/low ล่าสุดแบบ fractal — แท่งที่สูง/ต่ำสุดในกรอบซ้ายขวาเท่ากัน"""
    swing_high = swing_low = None
    for index in range(window, len(valid_candles) - window):
        window_slice = valid_candles[index - window:index + window + 1]
        candle = valid_candles[index]
        if float(candle["high"]) == max(float(item["high"]) for item in window_slice):
            swing_high = candle
        if float(candle["low"]) == min(float(item["low"]) for item in window_slice):
            swing_low = candle
    return swing_high, swing_low


def build_levels(
    valid_candles: list[dict],
    *,
    pivots: dict | None = None,
    indicators: dict | None = None,
    reference_price: float | None = None,
    session_date: str | None = None,
) -> list[dict]:
    if not valid_candles:
        return []

    reference = reference_price if reference_price is not None else float(valid_candles[-1]["close"])
    levels: list[dict] = []

    # ป้าย source_field ต้องเป็นชื่อเชิงความหมาย ไม่ใช่ดัชนีอาร์เรย์
    # เดิมเขียนว่า "candles[-1].high" ซึ่ง**ชี้ผิดแถวเมื่อมีแท่งที่กำลังก่อตัว**:
    # valid_candles คือแท่งที่ปิดแล้วเท่านั้น แต่คนที่เปิด raw.snapshot.json ตรวจตาม
    # จะเจอแท่งวันนี้ที่ยังไม่ปิดเป็นแถวสุดท้าย แล้วสรุปว่าเลขในบทความผิด
    # (วัด 2026-08-04: pdh = 4,079.68 ของวันที่ 3 แต่ candles[-1] ตามตัวอักษรคือวันที่ 4)
    # ใช้ "previous_day.*" ให้เข้าชุดกับ previous_week.* / swing.* ที่เป็นชื่อความหมายอยู่แล้ว
    previous_day = valid_candles[-1]
    stamp = previous_day["session_date"]
    levels.append(_level(
        identifier="pdh", label="High วันก่อน", kind="previous_day",
        value=float(previous_day["high"]), role=_role_for(float(previous_day["high"]), reference),
        source_field="previous_day.high", basis_timestamp=stamp,
        calculation_method="ค่าสูงสุดของ session ที่ปิดแล้วล่าสุด",
    ))
    levels.append(_level(
        identifier="pdl", label="Low วันก่อน", kind="previous_day",
        value=float(previous_day["low"]), role=_role_for(float(previous_day["low"]), reference),
        source_field="previous_day.low", basis_timestamp=stamp,
        calculation_method="ค่าต่ำสุดของ session ที่ปิดแล้วล่าสุด",
    ))

    week = previous_week_candles(valid_candles, anchor_date=session_date)
    if week:
        high = max(float(item["high"]) for item in week)
        low = min(float(item["low"]) for item in week)
        span = f"{week[0]['session_date']}..{week[-1]['session_date']}"
        levels.append(_level(
            identifier="pwh", label="High สัปดาห์ก่อน", kind="previous_week", value=high,
            role=_role_for(high, reference), source_field="previous_week.high",
            basis_timestamp=span, calculation_method="ค่าสูงสุดของสัปดาห์ ISO ก่อนหน้า",
        ))
        levels.append(_level(
            identifier="pwl", label="Low สัปดาห์ก่อน", kind="previous_week", value=low,
            role=_role_for(low, reference), source_field="previous_week.low",
            basis_timestamp=span, calculation_method="ค่าต่ำสุดของสัปดาห์ ISO ก่อนหน้า",
        ))

    swing_high, swing_low = find_swings(valid_candles)
    if swing_high:
        value = float(swing_high["high"])
        levels.append(_level(
            identifier="swing_high", label="Swing high", kind="swing", value=value,
            role=_role_for(value, reference), source_field="swing.high",
            basis_timestamp=swing_high["session_date"],
            calculation_method="fractal window 3 แท่งซ้ายขวา",
        ))
    if swing_low:
        value = float(swing_low["low"])
        levels.append(_level(
            identifier="swing_low", label="Swing low", kind="swing", value=value,
            role=_role_for(value, reference), source_field="swing.low",
            basis_timestamp=swing_low["session_date"],
            calculation_method="fractal window 3 แท่งซ้ายขวา",
        ))

    for name, item in (indicators or {}).items():
        if not item.get("approved_for_publication") or item.get("value") is None:
            continue
        if not name.startswith(("sma", "ema")):
            continue
        value = float(item["value"])
        levels.append(_level(
            identifier=name, label=name.upper(), kind="moving_average", value=value,
            role=_role_for(value, reference), source_field=f"indicators.{name}",
            basis_timestamp=stamp,
            calculation_method=f"คำนวณจาก {item['available_completed_bars']} แท่งที่ปิดแล้ว",
        ))

    atr = (indicators or {}).get("atr14")
    if atr and atr.get("approved_for_publication") and atr.get("value"):
        distance = float(atr["value"])
        levels.append(_level(
            identifier="atr_up", label="ATR projection ขึ้น", kind="atr_projection",
            value=reference + distance, role=RESISTANCE, source_field="indicators.atr14",
            basis_timestamp=stamp, calculation_method="ราคาอ้างอิง + ATR14 หนึ่งเท่า",
        ))
        levels.append(_level(
            identifier="atr_down", label="ATR projection ลง", kind="atr_projection",
            value=reference - distance, role=SUPPORT, source_field="indicators.atr14",
            basis_timestamp=stamp, calculation_method="ราคาอ้างอิง - ATR14 หนึ่งเท่า",
        ))

    if pivots and pivots.get("quality_status") != "invalid":
        for key in ("r3", "r2", "r1", "p", "s1", "s2", "s3"):
            value = pivots.get(key)
            if value is None:
                continue
            role = BIAS_DIVIDER if key == "p" else _role_for(float(value), reference)
            levels.append(_level(
                identifier=f"pivot_{key}", label=f"Pivot {key.upper()}", kind="pivot",
                value=float(value), role=role, source_field=f"pivots.{key}",
                basis_timestamp=pivots.get("basis_session_date"),
                calculation_method=f"Classic pivot จาก session {pivots.get('basis_session_date')}",
                quality_status="warning" if pivots.get("quality_status") == "warning" else "valid",
            ))

    return levels


def _zone_label(members: list[dict], *, maximum_names: int = 3) -> str:
    names = [item["label"] for item in members]
    if len(names) <= maximum_names:
        return " + ".join(names)
    return f"{' + '.join(names[:maximum_names])} และอีก {len(names) - maximum_names} ระดับ"


def merge_zones(levels: list[dict], *, reference_price: float, tolerance_pct: float = 0.15,
                atr: float | None = None, width_factor: float = 1.5) -> list[dict]:
    """รวมระดับที่ชิดกันเป็นโซนเดียว เพื่อไม่ให้กราฟและบทความรกด้วยเส้นที่แทบทับกัน

    คุมความกว้างสูงสุดของโซนด้วย เพราะถ้าดูแค่ระยะห่างระหว่างคู่ที่ติดกัน
    ระดับจะต่อกันเป็นลูกโซ่จนกลายเป็นโซนกว้างเกินจริงและอ่านไม่ได้
    """
    tolerance = reference_price * tolerance_pct / 100.0
    if atr:
        tolerance = max(tolerance, atr * 0.25)
    maximum_width = tolerance * width_factor

    priced = sorted((item for item in levels if item.get("value") is not None),
                    key=lambda item: item["value"])
    merged: list[dict] = []
    bucket: list[dict] = []

    def flush():
        if not bucket:
            return
        if len(bucket) == 1:
            merged.append(bucket[0])
            return
        low = min(item["value"] for item in bucket)
        high = max(item["value"] for item in bucket)
        members = [item["id"] for item in bucket]
        roles = {item["role"] for item in bucket}
        merged.append({
            **bucket[0],
            "id": "zone_" + "_".join(members),
            "label": _zone_label(bucket),
            "type": "zone",
            "value": None,
            "zone_low": low,
            "zone_high": high,
            "role": roles.pop() if len(roles) == 1 else BIAS_DIVIDER,
            "source_field": ", ".join(item["source_field"] for item in bucket),
            # ข้อความนี้ไปโผล่ในบทความสาธารณะ จึงห้ามมีตัวเลขปรับจูนภายใน
            # ค่า tolerance จริงเก็บไว้ใน merge_tolerance สำหรับหลักฐานหลังบ้าน
            "calculation_method": f"รวม {len(bucket)} ระดับที่อยู่ใกล้กันเป็นโซนเดียว",
            "merge_tolerance": tolerance,
            "members": members,
            "approved_for_publication": all(item["approved_for_publication"] for item in bucket),
        })

    for level in priced:
        if bucket:
            close_enough = level["value"] - bucket[-1]["value"] <= tolerance
            still_narrow = level["value"] - bucket[0]["value"] <= maximum_width
            if close_enough and still_narrow:
                bucket.append(level)
                continue
        flush()
        bucket = [level]
    flush()
    return merged


def approved_level_values(levels: list[dict]) -> list[float]:
    values: list[float] = []
    for level in levels:
        if not level.get("approved_for_publication"):
            continue
        if level.get("value") is not None:
            values.append(float(level["value"]))
        else:
            values.extend([float(level["zone_low"]), float(level["zone_high"])])
    return values


def validate_target(target, levels: list[dict], *, tolerance: float = 1e-6) -> dict:
    """target ต้องอ้างระดับที่มีอยู่จริง — ข้อความลอยอย่าง follow-through above R3 ไม่ผ่าน"""
    if target is None or isinstance(target, str):
        return {"valid": False, "reason": "no_numeric_target",
                "detail": "target ต้องเป็นระดับที่ตรวจสอบได้ ไม่ใช่ข้อความบรรยาย"}
    value = float(target)
    for level in levels:
        if not level.get("approved_for_publication"):
            continue
        if level.get("value") is not None and abs(float(level["value"]) - value) <= tolerance:
            return {"valid": True, "reason": None, "matched_level": level["id"]}
        low, high = level.get("zone_low"), level.get("zone_high")
        if low is not None and float(low) - tolerance <= value <= float(high) + tolerance:
            return {"valid": True, "reason": None, "matched_level": level["id"]}
    return {"valid": False, "reason": "target_not_in_approved_levels",
            "detail": "ไม่พบระดับที่อนุมัติแล้วตรงกับ target นี้"}


def classify_scenario(
    *,
    target,
    invalidation,
    levels: list[dict],
    has_h4: bool = False,
    has_intraday: bool = False,
) -> dict:
    """ตัดสินว่าฉากทัศน์นี้เป็นแผนเทรดจริง แผนระดับวัน หรือแค่เฝ้าดู"""
    target_check = validate_target(target, levels)

    if not target_check["valid"]:
        return {
            "classification": WATCHLIST,
            "executable": False,
            "reason": "no_approved_target",
            "target_check": target_check,
            "allowed_language": ["Watchlist", "เฝ้าดู", "ยังไม่ตั้งเป้าหมาย"],
        }

    if invalidation is None:
        return {
            "classification": WATCHLIST,
            "executable": False,
            "reason": "no_invalidation",
            "target_check": target_check,
            "allowed_language": ["Watchlist", "เฝ้าดู"],
        }

    if not has_intraday:
        return {
            "classification": DAILY_SCENARIO,
            "executable": False,
            "reason": "no_intraday_data" if not has_h4 else "no_trigger_timeframe",
            "target_check": target_check,
            "allowed_language": ["Daily Outlook", "ฉากทัศน์ระดับวัน", "หากราคาปิดเหนือ/ใต้"],
            "forbidden_language": ["เข้า Buy ตรงนี้", "เข้า Sell ตรงนี้",
                                   "Entry confirmed", "Intraday trigger confirmed"],
        }

    return {
        "classification": TRADE_SETUP,
        "executable": True,
        "reason": None,
        "target_check": target_check,
        "allowed_language": ["Trade setup", "Trigger", "Target", "Invalidation"],
    }


def build_level_map(report: dict, *, reference_price: float | None = None) -> dict:
    """เรียกจากผลของ integrity.assess() ได้โดยตรง"""
    from tools import candles as candles_module

    valid = candles_module.valid_completed_candles(report["candles"])
    reference = reference_price
    if reference is None and report["candles"]:
        reference = float(report["candles"][-1]["close"])

    # จุดอ้างของ "สัปดาห์ก่อน" ต้องเป็น session ปัจจุบัน (แท่งท้ายสุดรวมแท่งที่ก่อตัวอยู่)
    # ไม่ใช่แท่งที่ปิดแล้วตัวล่าสุด — ดู docstring ของ previous_week_candles
    session_date = report["candles"][-1]["session_date"] if report.get("candles") else None
    levels = build_levels(
        valid,
        pivots=report.get("pivots"),
        indicators=report.get("indicators"),
        reference_price=reference,
        session_date=session_date,
    )
    atr = (report.get("indicators") or {}).get("atr14") or {}
    zones = merge_zones(levels, reference_price=reference or 0.0,
                        atr=atr.get("value") if atr.get("approved_for_publication") else None)
    return {
        "reference_price": reference,
        "levels": levels,
        "zones": zones,
        "approved_values": approved_level_values(zones),
    }
