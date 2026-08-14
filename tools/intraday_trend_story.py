"""ชั้นคิดของสไตล์ H — แรงเทรนด์ระหว่างวันบน M30

คำถามที่สไตล์นี้ตอบมีข้อเดียว: **ตอนนี้ตลาดมีเทรนด์จริงหรือแค่แกว่ง และถ้ามี ฝั่งไหนคุม**

หลักที่ทำให้ H ไม่ใช่ "เอาอินดิเคเตอร์มาโหวต" — indicator แต่ละตัวมีหน้าที่คนละอย่าง
และ **ห้ามข้ามหน้าที่กัน**:

    DMI (+DI/-DI)  บอก *ทิศ*            ฝั่งไหนมีแรงเคลื่อนตามทิศมากกว่า
    ADX            บอก *ความแข็งแรง*     ไม่มีสิทธิ์บอกทิศ
    Supertrend     บอก *สถานะตามทิศ*     ราคายังยืนฝั่งเดิมของเส้นไหม
    ATR            บอก *ความผันผวน*      ไม่มีสิทธิ์บอกทิศเช่นกัน

⛔ สิ่งที่ห้ามเกิดขึ้นในไฟล์นี้เด็ดขาด: การนับคะแนน `ADX Buy + Supertrend Buy = 2 คะแนน`
ATR กับ ADX ไม่ใช่ directional indicator การให้มันโหวตทิศคือการนับเสียงคนที่ไม่รู้เรื่อง

**Python เป็นคนตัดสินสถานะ ไม่ใช่ตัวเขียน** — ตัวเขียนได้รับ `state` มาเป็นคำสำเร็จรูป
แล้วมีหน้าที่อธิบายมันเท่านั้น ถ้าปล่อยให้ตัวเขียนตีความเลขเอง สองรอบที่เลขเท่ากัน
จะได้ข้อสรุปคนละแบบ และไม่มีใครตรวจย้อนได้ว่าทำไม
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import intraday_indicators, intraday_story  # noqa: E402

SCHEMA = "intraday-trend-story-v1"
STYLE_ID = intraday_story.STYLE_H

BULL_TREND = "BULL_TREND"
BEAR_TREND = "BEAR_TREND"
EARLY_BULL = "EARLY_BULL"
EARLY_BEAR = "EARLY_BEAR"
TRANSITION = "TRANSITION"
NO_TREND = "NO_TREND"

STATES = (BULL_TREND, BEAR_TREND, EARLY_BULL, EARLY_BEAR, TRANSITION, NO_TREND)

# สถานะที่ถือว่า "ชี้ทิศ" — ใช้ทั้งเลือกคำในบทและตัดสินว่าพาดหัวมีทิศได้ไหม
DIRECTIONAL = {BULL_TREND: "up", BEAR_TREND: "down",
               EARLY_BULL: "up", EARLY_BEAR: "down"}


def classify(*, plus_di: float, minus_di: float, adx: float, close: float,
             supertrend_value: float, adx_trend: float, adx_no_trend: float) -> str:
    """ตัวตัดสินสถานะของ H — ฟังก์ชันบริสุทธิ์ ไม่แตะไฟล์ ไม่แตะเครือข่าย

    แยกออกมาเป็นฟังก์ชันเดี่ยวโดยตั้งใจ เพราะนี่คือชิ้นที่ต้องเทสด้วยค่าที่แต่งเอง
    ครบทุกสาขา — ถ้าฝังอยู่ใน `build` ก็ต้องมีข้อมูลตลาดจริงถึงจะทดสอบได้

    ลำดับการตัดสินสำคัญ: **เช็ค "ไม่มีเทรนด์" ก่อนเสมอ** เพราะ ADX ต่ำแปลว่าคำถาม
    เรื่องทิศยังไม่ควรถูกถามด้วยซ้ำ
    """
    if adx < adx_no_trend:
        return NO_TREND
    above = close > supertrend_value
    if plus_di > minus_di and above:
        return BULL_TREND if adx >= adx_trend else EARLY_BULL
    if minus_di > plus_di and not above:
        return BEAR_TREND if adx >= adx_trend else EARLY_BEAR
    # DI ชี้ทางหนึ่งแต่ราคายืนอีกฝั่งของ Supertrend = หลักฐานขัดกันเอง
    # สถานะนี้เป็นเรื่องที่ **มีค่าเขียนถึง** ไม่ใช่ของเสีย — ตลาดกำลังเปลี่ยนมือ
    return TRANSITION


def _threshold_crossed(adx: float, previous_adx: float | None,
                       levels: tuple[float, ...]) -> list[float]:
    """เกณฑ์ ADX ที่ถูกข้ามในแท่งนี้ — ตัวจุดชนวนบทตามข้อเสนอ §37

    "ADX ข้าม 20/25" เป็นเหตุการณ์ที่ควรได้บทแม้สถานะยังชื่อเดิม เพราะความหมาย
    ของสถานะเปลี่ยน (เทรนด์อ่อนกำลังแข็งขึ้น) — เก็บเป็นรายการ ไม่ใช่ธงเดียว
    """
    if previous_adx is None:
        return []
    return [level for level in levels
            if (previous_adx < level <= adx) or (adx < level <= previous_adx)]


def build(rows: list[dict], *, asset: str, timeframe: str, candle_basis: dict,
          previous_state: str | None = None, params: dict | None = None,
          styles: dict | None = None) -> dict:
    """artifact กลางของสไตล์ H — ตัวเขียนกับตัววาดอ่านก้อนนี้ก้อนเดียว

    `rows` ต้องผ่าน `intraday_bars.evaluate` มาแล้ว (แท่งปิดล้วน) — ที่นี่ไม่ตัดเอง
    """
    intraday_story.ensure_asset_allowed(STYLE_ID, asset, styles=styles)
    config = intraday_story.params_for(STYLE_ID, params=params)

    dmi = intraday_story.require(
        intraday_indicators.dmi_adx(rows, config["adx_length"]),
        asset=asset, style_id=STYLE_ID)
    trend_line = intraday_story.require(
        intraday_indicators.supertrend(rows, config["supertrend_atr_length"],
                                       config["supertrend_multiplier"]),
        asset=asset, style_id=STYLE_ID)
    volatility = intraday_story.require(
        intraday_indicators.atr(rows, config["atr_length"]),
        asset=asset, style_id=STYLE_ID)

    close = float(rows[-1]["close"])
    state = classify(plus_di=dmi["plus_di"], minus_di=dmi["minus_di"], adx=dmi["adx"],
                     close=close, supertrend_value=trend_line["value"],
                     adx_trend=config["adx_trend"], adx_no_trend=config["adx_no_trend"])

    crossed = _threshold_crossed(dmi["adx"], dmi["previous_adx"],
                                 (config["adx_no_trend"], config["adx_trend"]))
    story = intraday_story.envelope(
        schema=SCHEMA, style_id=STYLE_ID, asset=asset, timeframe=timeframe,
        rows=rows, candle_basis=candle_basis, state=state,
        previous_state=previous_state, display_bars=config["display_bars"])
    story |= {
        "direction": DIRECTIONAL.get(state),
        "dmi": {"plus_di": dmi["plus_di"], "minus_di": dmi["minus_di"],
                "adx": dmi["adx"], "previous_adx": dmi["previous_adx"],
                "direction": dmi["direction"], "length": dmi["length"]},
        "supertrend": {"direction": trend_line["direction"], "value": trend_line["value"],
                       "flipped": trend_line["flipped"],
                       "length": trend_line["length"],
                       "multiplier": trend_line["multiplier"],
                       # สองชุดนี้มีไว้ให้ตัววาดลากเส้นทั้งหน้าต่าง — บทไม่ได้ใช้
                       # แต่ถ้าไม่เก็บ ตัววาดจะต้องคำนวณเองแล้วอาจได้คนละเส้นกับที่บทอ้าง
                       "line_series": trend_line["line_series"],
                       "direction_series": trend_line["direction_series"]},
        "atr": {"value": volatility["value"], "previous": volatility["previous"],
                "rising": volatility["rising"], "length": volatility["length"]},
        "thresholds": {"trend": config["adx_trend"], "no_trend": config["adx_no_trend"]},
        "adx_crossed": crossed,
        # 🔑 ระดับที่ทำให้มุมมองรอบนี้เสีย = เส้น Supertrend ณ แท่งล่าสุด
        # **ไม่ใช่ระดับที่คิดขึ้นใหม่** — สไตล์นี้ไม่มีสิทธิ์ประกาศระดับราคาที่ไม่ได้
        # มาจาก indicator ของตัวเอง (ข้อเสนอ §26: ห้ามคิดแผน/ระดับซ้ำกับสายอื่น)
        "invalidation": {"level": trend_line["value"],
                         "kind": "supertrend",
                         "rule": ("ราคาปิดกลับไปอีกฝั่งของเส้น Supertrend"
                                  if state in DIRECTIONAL else
                                  "ยังไม่มีทิศให้เสีย — รอสถานะชี้ทิศก่อน")},
        # ตัวจุดชนวนบท (ข้อเสนอ §37) — เก็บเป็นเหตุผลเป็นคำ ไม่ใช่ True/False ลอย ๆ
        "triggers": ([f"สถานะเปลี่ยนจาก {previous_state} เป็น {state}"]
                     if previous_state and previous_state != state else [])
                    + ([f"ADX ข้ามเกณฑ์ {level:g}" for level in crossed])
                    + (["Supertrend พลิกทิศ"] if trend_line["flipped"] else []),
    }
    return story
