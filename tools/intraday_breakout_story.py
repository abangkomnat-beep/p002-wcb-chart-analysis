"""ชั้นคิดของสไตล์ I — เบรกเอาต์ความผันผวนบน M15

คำถามของสไตล์นี้ต่างจาก H คนละเรื่อง: **ตลาดกำลังบีบตัวหรือกำลังขยายจริง และการทะลุ
กรอบครั้งนี้เป็นแค่ไส้แท่งหรือเริ่มมีแรงตามมา**

หน้าที่ของแต่ละตัว:

    Donchian   ขอบกรอบที่ใช้ตัดสินการทะลุ — คิดจาก **แท่งก่อนหน้า** เท่านั้น
    BBW        บอกว่าความผันผวนกำลังหด (บีบตัว) หรือกำลังกาง — วัดด้วย *เปอร์เซ็นไทล์
               ของตัวเอง* ไม่ใช่ค่าดิบ เพราะ 'แคบ' ของทองกับของบิทคอยน์คนละเลข
    ATR        ยืนยันว่าแท่งที่ทะลุมีช่วงกว้างจริง ไม่ใช่แท่งเล็กที่บังเอิญไปแตะขอบ

สิ่งที่ทำให้สไตล์นี้มีเรื่องเล่าไม่ซ้ำเดิมทุก 15 นาที คือมันมีสถานะ **ล้มเหลว**
(`FAILED_BREAKOUT_*`) ซึ่งเป็นบทที่คนอ่านได้ประโยชน์จริง — "ทะลุแล้วไม่ไปต่อ"
เป็นข้อมูล ไม่ใช่ความว่างเปล่า · แต่มันนิยามด้วยอดีต ⇒ **ต้องมีความจำสถานะรอบก่อน**
ถ้าเรียก `build` โดยไม่ส่ง `previous_state` สถานะกลุ่มนี้จะเกิดไม่ได้เลย
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import intraday_indicators, intraday_story  # noqa: E402

SCHEMA = "intraday-breakout-story-v1"
STYLE_ID = intraday_story.STYLE_I

NORMAL = "NORMAL"
COMPRESSION = "COMPRESSION"
ARMED = "ARMED"
BREAKOUT_UP = "BREAKOUT_UP"
BREAKOUT_DOWN = "BREAKOUT_DOWN"
FAILED_BREAKOUT_UP = "FAILED_BREAKOUT_UP"
FAILED_BREAKOUT_DOWN = "FAILED_BREAKOUT_DOWN"
EXPANSION = "EXPANSION"

STATES = (NORMAL, COMPRESSION, ARMED, BREAKOUT_UP, BREAKOUT_DOWN,
          FAILED_BREAKOUT_UP, FAILED_BREAKOUT_DOWN, EXPANSION)

DIRECTIONAL = {BREAKOUT_UP: "up", BREAKOUT_DOWN: "down",
               FAILED_BREAKOUT_UP: "down", FAILED_BREAKOUT_DOWN: "up"}


def classify(*, previous_state: str | None, close: float, upper: float, lower: float,
             bbw_percentile: float, bbw_rising: bool, bar_true_range: float,
             atr_value: float, compression_percentile: float,
             expansion_percentile: float, armed_distance_atr: float,
             breakout_tr_atr: float) -> str:
    """ตัวตัดสินสถานะของ I — ฟังก์ชันบริสุทธิ์ เทสได้ครบทุกสาขาโดยไม่ต้องมีตลาดจริง

    **ลำดับสำคัญมาก** และเรียงตาม 'ข่าวที่ใหญ่ที่สุดก่อน':

        1. เบรกล้มเหลว  (ต้องเช็คก่อนทุกอย่าง เพราะมันคือการกลับเข้ากรอบหลังทะลุ
                         ซึ่งหน้าตาเหมือน NORMAL ทุกประการถ้าไม่ดูอดีต)
        2. เบรกจริง
        3. ง้างรอ / บีบตัว
        4. กาง / ปกติ
    """
    broke_up = close > upper
    broke_down = close < lower
    if previous_state == BREAKOUT_UP and not broke_up:
        return FAILED_BREAKOUT_UP
    if previous_state == BREAKOUT_DOWN and not broke_down:
        return FAILED_BREAKOUT_DOWN

    # แท่งที่ทะลุต้องมีช่วงกว้างจริง — ไม่ใช่แท่งจิ๋วที่ปิดเลยขอบไปหนึ่งจุด
    # และ BandWidth ต้องกางออก ไม่ใช่หดขณะราคาทะลุ (นั่นคืออาการของการทะลุที่ไม่มีแรง)
    expansion_ok = bar_true_range >= atr_value * breakout_tr_atr and bbw_rising
    if broke_up and expansion_ok:
        return BREAKOUT_UP
    if broke_down and expansion_ok:
        return BREAKOUT_DOWN

    squeezed = bbw_percentile <= compression_percentile
    if squeezed:
        near = min(upper - close, close - lower) <= atr_value * armed_distance_atr
        return ARMED if near else COMPRESSION
    if bbw_percentile >= expansion_percentile:
        return EXPANSION
    return NORMAL


def build(rows: list[dict], *, asset: str, timeframe: str, candle_basis: dict,
          previous_state: str | None = None, params: dict | None = None,
          styles: dict | None = None) -> dict:
    intraday_story.ensure_asset_allowed(STYLE_ID, asset, styles=styles)
    config = intraday_story.params_for(STYLE_ID, params=params)

    channel = intraday_story.require(
        intraday_indicators.donchian(rows, config["donchian_length"]),
        asset=asset, style_id=STYLE_ID)
    bandwidth = intraday_story.require(
        intraday_indicators.bollinger_bandwidth(
            rows, config["bbw_length"], config["bbw_stdev"],
            config["percentile_lookback"]),
        asset=asset, style_id=STYLE_ID)
    volatility = intraday_story.require(
        intraday_indicators.atr(rows, config["atr_length"]),
        asset=asset, style_id=STYLE_ID)

    # ⛔ เปอร์เซ็นไทล์ที่คำนวณจากตัวอย่างไม่กี่ตัวไม่ใช่เปอร์เซ็นไทล์ — มันคือการจัด
    # อันดับในกลุ่มเล็กที่บังเอิญมี · ปล่อยผ่านแปลว่าบทจะประกาศ 'บีบตัวที่สุดใน 200
    # แท่ง' ทั้งที่มีข้อมูลอยู่ 25 แท่ง
    minimum_samples = max(config["bbw_length"] * 2, config["percentile_lookback"] // 4)
    if bandwidth["percentile_samples"] < minimum_samples:
        raise intraday_story.StoryUnavailable(
            f"{asset}: ประวัติ BandWidth มี {bandwidth['percentile_samples']} ค่า "
            f"ต่ำกว่าขั้นต่ำ {minimum_samples} — เปอร์เซ็นไทล์ยังไม่มีความหมาย")

    close = float(rows[-1]["close"])
    state = classify(
        previous_state=previous_state, close=close,
        upper=channel["upper"], lower=channel["lower"],
        bbw_percentile=bandwidth["percentile"], bbw_rising=bandwidth["rising"],
        bar_true_range=volatility["bar_true_range"], atr_value=volatility["value"],
        compression_percentile=config["compression_percentile"],
        expansion_percentile=config["expansion_percentile"],
        armed_distance_atr=config["armed_distance_atr"],
        breakout_tr_atr=config["breakout_tr_atr"])

    story = intraday_story.envelope(
        schema=SCHEMA, style_id=STYLE_ID, asset=asset, timeframe=timeframe,
        rows=rows, candle_basis=candle_basis, state=state,
        previous_state=previous_state, display_bars=config["display_bars"])
    story |= {
        "direction": DIRECTIONAL.get(state),
        "donchian": {"upper": channel["upper"], "lower": channel["lower"],
                     "middle": channel["middle"], "width": channel["width"],
                     "length": channel["length"],
                     "excludes_signal_bar": channel["excludes_signal_bar"]},
        "bbw": {"value": bandwidth["value"], "previous": bandwidth["previous"],
                "percentile": bandwidth["percentile"], "rising": bandwidth["rising"],
                "samples": bandwidth["percentile_samples"],
                "length": bandwidth["length"], "series": bandwidth["series"]},
        "atr": {"value": volatility["value"], "previous": volatility["previous"],
                "rising": volatility["rising"], "length": volatility["length"],
                "bar_true_range": volatility["bar_true_range"],
                "expansion_ratio": (volatility["bar_true_range"] / volatility["value"]
                                    if volatility["value"] else 0.0)},
        "thresholds": {"compression_percentile": config["compression_percentile"],
                       "expansion_percentile": config["expansion_percentile"],
                       "breakout_tr_atr": config["breakout_tr_atr"]},
        # ระดับที่ทำให้มุมมองเสีย = ขอบกรอบฝั่งตรงข้ามของการเบรก · สถานะที่ยังไม่เบรก
        # ใช้ขอบที่ราคาใกล้กว่า เพราะนั่นคือขอบที่จะถูกทดสอบก่อน
        "invalidation": _invalidation(state, channel, close),
        "triggers": ([f"สถานะเปลี่ยนจาก {previous_state} เป็น {state}"]
                     if previous_state and previous_state != state else []),
    }
    return story


def _invalidation(state: str, channel: dict, close: float) -> dict:
    if state in (BREAKOUT_UP, FAILED_BREAKOUT_DOWN):
        return {"level": channel["upper"], "kind": "donchian_upper",
                "rule": "ราคาปิดกลับเข้ามาใต้ขอบบนของกรอบ"}
    if state in (BREAKOUT_DOWN, FAILED_BREAKOUT_UP):
        return {"level": channel["lower"], "kind": "donchian_lower",
                "rule": "ราคาปิดกลับเข้ามาเหนือขอบล่างของกรอบ"}
    nearer_upper = (channel["upper"] - close) <= (close - channel["lower"])
    return {"level": channel["upper"] if nearer_upper else channel["lower"],
            "kind": "donchian_upper" if nearer_upper else "donchian_lower",
            "rule": "ราคาปิดออกนอกขอบกรอบด้านที่ใกล้ที่สุด"}
