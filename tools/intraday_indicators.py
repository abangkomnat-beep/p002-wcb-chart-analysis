"""เครื่องคำนวณ indicator ของสไตล์ระหว่างวัน H/I/J — OHLC ล้วน ไม่มี volume

**ทำไมเป็นโมดูลแยกจาก `indicators.py`:** ตัวเดิมเป็นเครื่องของสายรายวัน (SMA/RSI/ATR
ค่าเดียวต่อรอบ) และค่าที่มันคืนถูกใช้โดยด่านความเสี่ยงที่ปรับเทียบมาจากข้อมูลจริง 484 วัน
ถ้าเติมสาขา intraday เข้าไปในนั้น ทุกสไตล์รับความเสี่ยงจากโค้ดที่มีสามสไตล์ใช้
⇒ แยกไฟล์ ใช้ *สัญญาเดียวกัน* (ทุกตัวคืน dict ที่บอกสถานะตัวเอง) แต่คนละเส้นทาง
**เส้นทางรายวันไม่ถูกแตะแม้แต่บรรทัดเดียว**

สัญญาของทุกฟังก์ชันในไฟล์นี้:

    คืน {"indicator", "status", "required_bars", "available_bars", "value"/ช่องค่า…}
    ข้อมูลไม่พอ = status ไม่ใช่ "available" และ **ค่าเป็น None** — ไม่ประมาณ ไม่เติมศูนย์

หลักที่ยึดตลอดทั้งไฟล์ (ข้อเสนอ H–J §39 No-Lookahead):

1. **ทุกตัวคำนวณจากแท่งที่ปิดแล้วเท่านั้น** — ผู้เรียกต้องผ่าน `intraday_bars.evaluate`
   มาก่อน ที่นี่ไม่ตัดแท่งเอง (กติกาแท่งปิดต้องมีชุดเดียวในระบบ)
2. **Donchian ไม่นับแท่งสัญญาณเข้าไปในกรอบที่ใช้ตัดสินแท่งนั้นเอง** — ไม่งั้นราคาจะ
   "ทะลุกรอบของตัวเอง" ไม่ได้เลยตลอดกาล
3. **Ichimoku คืนค่าเมฆ ณ แท่งปัจจุบันซึ่งคำนวณจากข้อมูลเมื่อ 26 แท่งก่อน** พร้อม
   ป้าย `calculated_at` / `plotted_at` — เมฆถูกเลื่อนไปข้างหน้า การหยิบ Span A/B
   ที่คำนวณจากแท่งล่าสุดมาเทียบกับราคาแท่งล่าสุดคือการมองอนาคต
4. **Percentile ของ BBW ใช้ข้อมูลถึงแท่งสัญญาณเท่านั้น**

ค่าเฉลี่ยที่ใช้เป็น **Wilder RMA** ไม่ใช่ค่าเฉลี่ยเลขคณิต — ต่างจาก `indicators._atr14`
โดยตั้งใจ เพราะ ADX/DMI/Supertrend ทั้งตระกูลนิยามบน RMA ถ้าผสมสองสูตร ค่า ATR ที่
Supertrend ใช้กับค่า ATR ที่บทพิมพ์จะไม่ใช่ตัวเดียวกัน แล้วภาพกับบทจะเล่าคนละเลข
"""

from __future__ import annotations

import math

AVAILABLE = "available"
INSUFFICIENT = "insufficient_data"

# เผื่อแท่งสำหรับตัวที่ใช้ค่าเฉลี่ยแบบ Wilder — RMA ต้องอุ่นเครื่องหลายรอบกว่าจะนิ่ง
# ตัวเลข 3 เท่าเป็นธรรมเนียมของ ADX (ค่าจะยังเพี้ยนถ้าให้แค่ length+1 แท่ง)
WILDER_WARMUP_FACTOR = 3


class IndicatorInputError(ValueError):
    """ชุดแท่งที่ส่งเข้ามาผิดรูป — คนละเรื่องกับ 'ข้อมูลไม่พอ' ซึ่งเป็นสถานะปกติ"""


def _series(rows: list[dict], key: str) -> list[float]:
    try:
        return [float(row[key]) for row in rows]
    except (KeyError, TypeError, ValueError) as exc:
        raise IndicatorInputError(f"แท่งขาดช่อง '{key}' หรือค่าไม่ใช่ตัวเลข") from exc


def _result(name: str, *, required: int, available: int, extra: dict | None = None) -> dict:
    ok = available >= required and extra is not None
    payload = {
        "indicator": name,
        "status": AVAILABLE if ok else INSUFFICIENT,
        "required_bars": required,
        "available_bars": available,
    }
    payload |= extra if ok else {}
    return payload


def available(indicator: dict | None) -> bool:
    return bool(indicator) and indicator.get("status") == AVAILABLE


def true_ranges(rows: list[dict]) -> list[float]:
    """TR ของทุกแท่งตั้งแต่แท่งที่สอง — แท่งแรกไม่มีราคาปิดก่อนหน้าจึงไม่มี TR"""
    highs, lows, closes = _series(rows, "high"), _series(rows, "low"), _series(rows, "close")
    return [max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            for i in range(1, len(rows))]


def rma(values: list[float], length: int) -> list[float | None]:
    """Wilder's smoothing — คืนลิสต์ยาวเท่าอินพุต ช่วงอุ่นเครื่องเป็น None

    ตัวแรกที่มีค่าคือค่าเฉลี่ยเลขคณิตของ `length` ตัวแรก จากนั้นเดินด้วยสูตร
    `prev + (x - prev) / length` ตามนิยามของ Wilder
    """
    if length <= 0:
        raise IndicatorInputError("ความยาวค่าเฉลี่ยต้องเป็นจำนวนบวก")
    out: list[float | None] = [None] * len(values)
    if len(values) < length:
        return out
    current = sum(values[:length]) / length
    out[length - 1] = current
    for index in range(length, len(values)):
        current += (values[index] - current) / length
        out[index] = current
    return out


def atr(rows: list[dict], length: int = 14) -> dict:
    """ATR แบบ Wilder — **วัดความผันผวนอย่างเดียว ไม่ใช่ตัวบอกทิศ**

    ช่อง `direction` จงใจไม่มีในผลลัพธ์ เพื่อให้เขียนโค้ดที่ถาม "ATR ให้ซื้อหรือขาย"
    ไม่ได้ตั้งแต่ระดับโครงสร้างข้อมูล (ข้อเสนอ §5 · ด่าน `atr_not_used_as_direction`)
    """
    required = length + 1
    if len(rows) < required:
        return _result("atr", required=required, available=len(rows))
    series = rma(true_ranges(rows), length)
    value = series[-1]
    previous = series[-2] if len(series) >= 2 else None
    if value is None:
        return _result("atr", required=required, available=len(rows))
    return _result("atr", required=required, available=len(rows), extra={
        "length": length,
        "value": float(value),
        "previous": float(previous) if previous is not None else None,
        "rising": bool(previous is not None and value > previous),
        "bar_true_range": float(true_ranges(rows)[-1]),
    })


def dmi_adx(rows: list[dict], length: int = 14) -> dict:
    """+DI / -DI / ADX แบบ Wilder

    หน้าที่แยกกันชัด และบทต้องพูดตามนี้เท่านั้น:
      +DI/-DI = **ทิศ** ฝั่งไหนมีแรงเคลื่อนตามทิศมากกว่า
      ADX     = **ความแข็งแรง** ของการเคลื่อนไหว ไม่บอกว่าขึ้นหรือลง
    """
    required = length * WILDER_WARMUP_FACTOR + 1
    if len(rows) < required:
        return _result("dmi_adx", required=required, available=len(rows))
    highs, lows = _series(rows, "high"), _series(rows, "low")
    plus_dm, minus_dm = [], []
    for index in range(1, len(rows)):
        up_move = highs[index] - highs[index - 1]
        down_move = lows[index - 1] - lows[index]
        plus_dm.append(up_move if (up_move > down_move and up_move > 0) else 0.0)
        minus_dm.append(down_move if (down_move > up_move and down_move > 0) else 0.0)

    tr_rma = rma(true_ranges(rows), length)
    plus_rma, minus_rma = rma(plus_dm, length), rma(minus_dm, length)

    dx: list[float] = []
    for index, tr_value in enumerate(tr_rma):
        if not tr_value or plus_rma[index] is None or minus_rma[index] is None:
            continue
        plus_di = 100.0 * plus_rma[index] / tr_value
        minus_di = 100.0 * minus_rma[index] / tr_value
        total = plus_di + minus_di
        dx.append(100.0 * abs(plus_di - minus_di) / total if total else 0.0)
    adx_series = rma(dx, length)
    if not adx_series or adx_series[-1] is None or not tr_rma[-1]:
        return _result("dmi_adx", required=required, available=len(rows))

    plus_di = 100.0 * plus_rma[-1] / tr_rma[-1]
    minus_di = 100.0 * minus_rma[-1] / tr_rma[-1]
    previous_adx = next((value for value in reversed(adx_series[:-1]) if value is not None), None)
    return _result("dmi_adx", required=required, available=len(rows), extra={
        "length": length,
        "plus_di": float(plus_di),
        "minus_di": float(minus_di),
        "adx": float(adx_series[-1]),
        "previous_adx": float(previous_adx) if previous_adx is not None else None,
        # ทิศมาจาก DI เท่านั้น — ADX ไม่มีสิทธิ์ออกความเห็นเรื่องทิศ
        "direction": "up" if plus_di > minus_di else ("down" if minus_di > plus_di else "flat"),
    })


def supertrend(rows: list[dict], length: int = 10, multiplier: float = 3.0) -> dict:
    """Supertrend — เส้นตามทิศที่ใช้ ATR เป็นระยะ และกติกาแถบที่ 'ไม่ถอยหลัง'

    ค่าที่คืนคือเส้น ณ แท่งล่าสุด (`value`) กับทิศ (`direction`) และธง `flipped`
    ที่บอกว่าแท่งนี้เพิ่งพลิกทิศหรือไม่ — ธงนี้เป็นหนึ่งในตัวจุดชนวนบทของสไตล์ H
    """
    required = length * 2 + 1
    if len(rows) < required:
        return _result("supertrend", required=required, available=len(rows))
    atr_series = rma(true_ranges(rows), length)
    highs, lows, closes = _series(rows, "high"), _series(rows, "low"), _series(rows, "close")

    final_upper: list[float | None] = [None] * len(rows)
    final_lower: list[float | None] = [None] * len(rows)
    direction: list[int | None] = [None] * len(rows)
    for index in range(1, len(rows)):
        atr_value = atr_series[index - 1]      # atr_series เดินตาม true_ranges ซึ่งเริ่มที่แท่งที่สอง
        if atr_value is None:
            continue
        mid = (highs[index] + lows[index]) / 2
        basic_upper = mid + multiplier * atr_value
        basic_lower = mid - multiplier * atr_value
        previous_upper = final_upper[index - 1]
        previous_lower = final_lower[index - 1]
        # กติกาแถบของ Supertrend: แถบบนขยับลงได้เฉพาะเมื่อแท่งก่อนปิดทะลุแถบบนไปแล้ว
        # (และกลับกันสำหรับแถบล่าง) — นี่คือสิ่งที่ทำให้เส้นเป็น trailing ไม่ใช่เส้นแกว่ง
        if previous_upper is None or basic_upper < previous_upper or closes[index - 1] > previous_upper:
            final_upper[index] = basic_upper
        else:
            final_upper[index] = previous_upper
        if previous_lower is None or basic_lower > previous_lower or closes[index - 1] < previous_lower:
            final_lower[index] = basic_lower
        else:
            final_lower[index] = previous_lower

        previous_direction = direction[index - 1]
        if previous_direction is None:
            direction[index] = 1 if closes[index] > final_upper[index] else -1
        elif previous_direction == 1:
            direction[index] = -1 if closes[index] < final_lower[index] else 1
        else:
            direction[index] = 1 if closes[index] > final_upper[index] else -1

    if direction[-1] is None:
        return _result("supertrend", required=required, available=len(rows))
    line = final_lower[-1] if direction[-1] == 1 else final_upper[-1]
    previous_direction = direction[-2] if len(direction) >= 2 else None
    return _result("supertrend", required=required, available=len(rows), extra={
        "length": length,
        "multiplier": multiplier,
        "direction": "up" if direction[-1] == 1 else "down",
        "value": float(line),
        "flipped": bool(previous_direction is not None and previous_direction != direction[-1]),
        # เส้นทั้งชุดสำหรับตัววาด — บทไม่ได้ใช้ แต่ภาพต้องลากได้ทั้งหน้าต่าง
        "line_series": [
            None if d is None else float(final_lower[i] if d == 1 else final_upper[i])
            for i, d in enumerate(direction)
        ],
        "direction_series": [None if d is None else ("up" if d == 1 else "down")
                             for d in direction],
    })


def donchian(rows: list[dict], length: int = 20) -> dict:
    """กรอบ Donchian ของ **แท่งก่อนหน้า** — แท่งล่าสุดถูกกันออกจากกรอบของตัวเอง

    🐞 กับดักคลาสสิกที่ข้อเสนอ §14 เตือนไว้: ถ้าเอา 20 แท่งที่รวมแท่งปัจจุบันมาหา
    high สูงสุด แล้วถามว่า "ราคาปิดสูงกว่าขอบบนไหม" คำตอบจะเป็น 'ไม่' เกือบตลอด
    เพราะแท่งนั้นเป็นคนตั้งขอบบนเอง ⇒ ระบบจะไม่เห็นเบรกเอาต์เลยแบบเงียบ ๆ
    """
    required = length + 1
    if len(rows) < required:
        return _result("donchian", required=required, available=len(rows))
    window = rows[-(length + 1):-1]
    upper = max(float(row["high"]) for row in window)
    lower = min(float(row["low"]) for row in window)
    close = float(rows[-1]["close"])
    return _result("donchian", required=required, available=len(rows), extra={
        "length": length,
        "upper": upper,
        "lower": lower,
        "middle": (upper + lower) / 2,
        "width": upper - lower,
        "excludes_signal_bar": True,
        "close_above_upper": close > upper,
        "close_below_lower": close < lower,
        "inside": lower <= close <= upper,
        # ระยะจากราคาปิดถึงขอบที่ใกล้ที่สุด (บวกเสมอเมื่ออยู่ในกรอบ)
        "distance_to_upper": upper - close,
        "distance_to_lower": close - lower,
    })


def _stdev(values: list[float]) -> float:
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def bollinger_bandwidth(rows: list[dict], length: int = 20, stdev: float = 2.0,
                        percentile_lookback: int = 200) -> dict:
    """BandWidth + **อันดับเปอร์เซ็นไทล์ของตัวเอง** ไม่ใช่ค่าดิบ

    ข้อเสนอ §14 อ้างคำเตือนของ TradingView ไว้ตรงประเด็น: ความ "แคบ" ของ BBW
    เทียบข้ามสินทรัพย์และข้ามกรอบเวลาไม่ได้ ⇒ ห้ามฮาร์ดโค้ด `BBW < 2 = squeeze`
    ที่นี่จึงคืน `percentile` ที่วัดเทียบประวัติของ **สินทรัพย์นั้น กรอบเวลานั้น**
    และนับเฉพาะข้อมูลถึงแท่งสัญญาณ (ไม่มีแท่งอนาคตใน lookback)
    """
    required = length
    closes = _series(rows, "close")
    if len(closes) < required:
        return _result("bollinger_bandwidth", required=required, available=len(rows))

    series: list[float] = []
    for end in range(length, len(closes) + 1):
        window = closes[end - length:end]
        middle = sum(window) / length
        spread = stdev * _stdev(window)
        series.append(((middle + spread) - (middle - spread)) / middle * 100 if middle else 0.0)

    value = series[-1]
    history = series[-percentile_lookback:]
    rank = sum(1 for item in history if item <= value)
    percentile = rank / len(history) * 100
    previous = series[-2] if len(series) >= 2 else None
    return _result("bollinger_bandwidth", required=required, available=len(rows), extra={
        "length": length,
        "stdev": stdev,
        "value": float(value),
        "previous": float(previous) if previous is not None else None,
        "rising": bool(previous is not None and value > previous),
        "percentile": float(percentile),
        "percentile_samples": len(history),
        "series": [float(item) for item in series],
    })


def ichimoku(rows: list[dict], conversion: int = 9, base: int = 26,
             span_b: int = 52) -> dict:
    """Ichimoku ที่ **จัดการ displacement ให้ถูกต้อง**

    Senkou Span A/B ถูกพล็อตล่วงหน้า `base` แท่ง ⇒ เมฆที่อยู่ตรงแท่งล่าสุดบนกราฟ
    คือค่าที่คำนวณจากข้อมูลเมื่อ `base` แท่งก่อน · การหยิบ Span ที่คำนวณจากแท่ง
    ล่าสุดมาเทียบกับราคาแท่งล่าสุด = อ่านค่าที่บนกราฟยังอยู่ในอนาคต (lookahead)

    ผลลัพธ์จึงแยกสองชุดให้ชัด:
        `cloud_now`     เมฆ ณ ตำแหน่งราคาปัจจุบัน (ใช้ตัดสิน bias) พร้อม
                        `calculated_at` / `plotted_at`
        `cloud_ahead`   เมฆที่คำนวณจากแท่งล่าสุด ซึ่งจะไปโผล่ข้างหน้า (ใช้วาดเท่านั้น)
    """
    required = span_b + base
    if len(rows) < required:
        return _result("ichimoku", required=required, available=len(rows))
    highs, lows = _series(rows, "high"), _series(rows, "low")

    def midpoint(end: int, window: int) -> float:
        return (max(highs[end - window + 1:end + 1]) + min(lows[end - window + 1:end + 1])) / 2

    last = len(rows) - 1
    tenkan = midpoint(last, conversion)
    kijun = midpoint(last, base)
    origin = last - base                       # แท่งที่ค่าของเมฆ ณ ตอนนี้ถูกคำนวณไว้
    span_a_now = (midpoint(origin, conversion) + midpoint(origin, base)) / 2
    span_b_now = midpoint(origin, span_b)
    close = float(rows[last]["close"])
    top, bottom = max(span_a_now, span_b_now), min(span_a_now, span_b_now)
    if close > top:
        position = "above"
    elif close < bottom:
        position = "below"
    else:
        position = "inside"
    return _result("ichimoku", required=required, available=len(rows), extra={
        "conversion": conversion,
        "base": base,
        "span_b_length": span_b,
        "tenkan": float(tenkan),
        "kijun": float(kijun),
        "tenkan_above_kijun": bool(tenkan > kijun),
        "cloud_now": {
            "span_a": float(span_a_now),
            "span_b": float(span_b_now),
            "top": float(top),
            "bottom": float(bottom),
            "bullish": bool(span_a_now > span_b_now),
            "calculated_at": str(rows[origin].get("at") or rows[origin].get("date")),
            "plotted_at": str(rows[last].get("at") or rows[last].get("date")),
        },
        "cloud_ahead": {
            "span_a": float((tenkan + kijun) / 2),
            "span_b": float(midpoint(last, span_b)),
            "calculated_at": str(rows[last].get("at") or rows[last].get("date")),
            "plotted_at": f"+{base} แท่งจากแท่งล่าสุด",
        },
        "position": position,
    })


def choppiness(rows: list[dict], length: int = 14) -> dict:
    """Choppiness Index — **ไม่บอกทิศ** บอกแค่ว่าตลาดสับหรือมีทิศ

    ค่าสูง = แกว่งสับ · ค่าต่ำ = เดินเป็นทิศมากขึ้น (เกณฑ์ 61.8/38.2 อยู่ในไฟล์ config
    ไม่ฝังที่นี่ เพราะเป็นค่าที่ต้อง calibrate ไม่ใช่นิยามของสูตร)
    """
    required = length + 1
    if len(rows) < required:
        return _result("choppiness", required=required, available=len(rows))

    def value_at(end: int) -> float | None:
        # ⚠️ **สองหน้าต่างนี้ต้องยาวเท่ากัน คือ `length` แท่ง**
        # 🐞 พบตอนเขียนเทส 2026-08-13: เดิมวัดช่วงสูง-ต่ำจาก `length + 1` แท่ง
        # (ชุดเดียวกับที่ใช้หา TR ซึ่งต้องมีแท่งพิเศษข้างหน้าไว้อ้างราคาปิดก่อนหน้า)
        # ⇒ ตัวหารกว้างกว่าตัวตั้งอย่างเป็นระบบ ค่าจึงติดลบได้ในตลาดที่เดินทางเดียว
        # ซึ่งอยู่นอกช่วง 0–100 ที่ทั้งเกณฑ์ 38.2/61.8 และคำอธิบายในบทตั้งอยู่บน
        tr_window = rows[end - length:end + 1]        # length + 1 แท่ง ⇒ length ค่า TR
        span_window = rows[end - length + 1:end + 1]  # length แท่ง ตามนิยาม
        tr_sum = sum(true_ranges(tr_window))
        span = (max(float(row["high"]) for row in span_window)
                - min(float(row["low"]) for row in span_window))
        if span <= 0 or tr_sum <= 0:
            return None
        return 100.0 * math.log10(tr_sum / span) / math.log10(length)

    value = value_at(len(rows) - 1)
    if value is None:
        return _result("choppiness", required=required, available=len(rows))
    previous = value_at(len(rows) - 2) if len(rows) >= required + 1 else None
    return _result("choppiness", required=required, available=len(rows), extra={
        "length": length,
        "value": float(value),
        "previous": float(previous) if previous is not None else None,
        "falling": bool(previous is not None and value < previous),
    })
