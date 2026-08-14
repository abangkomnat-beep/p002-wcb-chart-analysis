"""ชั้นคิดของสไตล์ J — ย่อแล้วไปต่อ หรือกำลังเสียแนวโน้ม (M30 → M15)

คำถามที่คนอ่านอยากรู้ที่สุดเวลาราคาย่อ: **นี่คือย่อเพื่อไปต่อ หรือเริ่มเสียทรงแล้ว**

โครงสองชั้น — และลำดับสำคัญ ห้ามสลับ:

    ชั้น 1 (M30 · Ichimoku)   ตอบว่า *บริบทหลักเอนไปทางไหน* — ถ้าตอบไม่ได้ ชั้น 2 ไม่มีความหมาย
    ชั้น 2 (M15 · CHOP+ATR)   ตอบว่า *การย่อรอบนี้เดินถึงขั้นไหนแล้ว*

หน้าที่ของแต่ละตัว:

    Ichimoku (M30)   บริบท + **โซนอ้างอิงของการย่อ** (Tenkan–Kijun) + เส้นที่หลุดแล้วถือว่าเสีย
    CHOP (M15)       บอกว่าตลาดยังสับหรือเริ่มกลับมามีทิศ — **ไม่บอกทิศ**
    ATR (M15)        ความผันผวนของชั้นทริกเกอร์ ใช้ประเมินความกว้างของการแกว่ง

⚠️ **กับดักสองกรอบเวลา** ที่ด่าน `timeframe_alignment` กันไว้: ถ้าแท่ง M30 ที่หยิบมา
ปิดหลังแท่ง M15 ที่ใช้ตัดสิน บทจะอ้างบริบทที่ ณ เวลานั้นยังไม่เกิด — ตรวจที่
`intraday_story.check_alignment` ก่อนคิดสถานะเสมอ

⚠️ **กับดัก displacement ของ Ichimoku**: เมฆถูกพล็อตล่วงหน้า 26 แท่ง การเทียบราคา
ปัจจุบันกับ Span ที่คำนวณจากแท่งล่าสุดคือการอ่านค่าที่ยังอยู่ในอนาคต — จัดการแล้วที่
`intraday_indicators.ichimoku` (`cloud_now` vs `cloud_ahead`) ที่นี่ใช้ `cloud_now` เท่านั้น
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import intraday_indicators, intraday_story  # noqa: E402

SCHEMA = "intraday-pullback-story-v1"
STYLE_ID = intraday_story.STYLE_J

NO_M30_BIAS = "NO_M30_BIAS"
M30_BULL_CONTEXT = "M30_BULL_CONTEXT"
M30_BEAR_CONTEXT = "M30_BEAR_CONTEXT"
PULLBACK_FORMING = "PULLBACK_FORMING"
PULLBACK_CONFIRMED = "PULLBACK_CONFIRMED"
PULLBACK_FAILED = "PULLBACK_FAILED"
TREND_RESUMED = "TREND_RESUMED"

STATES = (NO_M30_BIAS, M30_BULL_CONTEXT, M30_BEAR_CONTEXT, PULLBACK_FORMING,
          PULLBACK_CONFIRMED, PULLBACK_FAILED, TREND_RESUMED)

IN_PULLBACK = {PULLBACK_FORMING, PULLBACK_CONFIRMED}


def context_bias(ichimoku: dict) -> str | None:
    """bias ของ M30 — ต้องให้องค์ประกอบทั้งสามชั้นพูดตรงกัน ไม่ใช่สองในสาม

    ราคาเหนือเมฆ + Tenkan เหนือ Kijun + Span A เหนือ Span B ⇒ ขึ้น (กลับกันคือลง)
    ขาดข้อใดข้อหนึ่ง = ช่วงเปลี่ยนผ่าน ซึ่งเป็นคำตอบที่ถูกต้อง ไม่ใช่คำตอบที่อ่อนแอ
    """
    cloud = ichimoku["cloud_now"]
    if ichimoku["position"] == "above" and ichimoku["tenkan_above_kijun"] and cloud["bullish"]:
        return "up"
    if (ichimoku["position"] == "below" and not ichimoku["tenkan_above_kijun"]
            and not cloud["bullish"]):
        return "down"
    return None


def classify(*, previous_state: str | None, bias: str | None, close: float,
             tenkan: float, kijun: float, chop: float, chop_previous: float | None,
             chop_choppy: float, extreme: float | None) -> str:
    """ตัวตัดสินสถานะของ J — ฟังก์ชันบริสุทธิ์

    `extreme` = จุดสูงสุด (ขาขึ้น) / ต่ำสุด (ขาลง) ของ M15 ในหน้าต่างที่ผ่านมา
    ไม่รวมแท่งปัจจุบัน — ใช้ตัดสิน `TREND_RESUMED` เท่านั้น
    """
    was_in_pullback = previous_state in IN_PULLBACK

    # 1) บริบทหายก่อนอย่างอื่น — ไม่มีทิศหลักแล้ว คำว่า "ย่อ" ก็ไม่มีความหมาย
    if bias is None:
        return PULLBACK_FAILED if was_in_pullback else NO_M30_BIAS

    up = bias == "up"
    beyond_kijun = close < kijun if up else close > kijun
    inside_zone = (close <= tenkan and close >= kijun) if up else (close >= tenkan and close <= kijun)
    back_with_trend = close > tenkan if up else close < tenkan

    # 2) หลุดเส้น Kijun สวนทิศ = การย่อกลายเป็นการเสียโครง
    if beyond_kijun:
        return PULLBACK_FAILED if was_in_pullback else NO_M30_BIAS

    # 3) กลับไปทำจุดสุดขั้วใหม่ต่อจากที่ยืนยันแล้ว = เทรนด์กลับมาเดินจริง
    if previous_state == PULLBACK_CONFIRMED and extreme is not None:
        if (close > extreme) if up else (close < extreme):
            return TREND_RESUMED

    # 4) ยืนยันการย่อ: เคยอยู่ในโซน + ปิดกลับไปตามทิศ + ตลาดออกจากช่วงสับ
    leaving_chop = chop < chop_choppy and (chop_previous is None or chop < chop_previous)
    if was_in_pullback and back_with_trend and leaving_chop:
        return PULLBACK_CONFIRMED

    # 5) กำลังย่อ: ราคาเข้ามาในโซนอ้างอิงระหว่าง Tenkan กับ Kijun
    if inside_zone:
        return PULLBACK_FORMING

    return M30_BULL_CONTEXT if up else M30_BEAR_CONTEXT


def build(context_rows: list[dict], trigger_rows: list[dict], *, asset: str,
          context_timeframe: str = "30min", trigger_timeframe: str = "15min",
          candle_basis: dict, context_basis: dict | None = None,
          previous_state: str | None = None, params: dict | None = None,
          styles: dict | None = None) -> dict:
    """artifact กลางของสไตล์ J

    `candle_basis` คือหลักฐานแท่งปิดของ **ชั้นทริกเกอร์ (M15)** ซึ่งเป็นแท่งที่บท
    ประกาศว่าเป็นฐาน · `context_basis` ของ M30 เก็บไว้เป็นหลักฐานประกอบ
    """
    intraday_story.ensure_asset_allowed(STYLE_ID, asset, styles=styles)
    config = intraday_story.params_for(STYLE_ID, params=params)
    # ตัดแท่งบริบทให้ปิดไม่ช้ากว่าแท่งทริกเกอร์ก่อนคำนวณอะไรทั้งนั้น — คำนวณก่อนตัด
    # แปลว่าค่าที่ได้มาจากแท่งที่กำลังจะถูกทิ้ง
    context_rows, context_close_at = intraday_story.align_context(
        context_rows, trigger_rows, context_timeframe=context_timeframe,
        trigger_timeframe=trigger_timeframe, asset=asset)

    cloud = intraday_story.require(
        intraday_indicators.ichimoku(context_rows, config["ichimoku_conversion"],
                                     config["ichimoku_base"], config["ichimoku_span_b"]),
        asset=asset, style_id=STYLE_ID)
    chop = intraday_story.require(
        intraday_indicators.choppiness(trigger_rows, config["chop_length"]),
        asset=asset, style_id=STYLE_ID)
    volatility = intraday_story.require(
        intraday_indicators.atr(trigger_rows, config["atr_length"]),
        asset=asset, style_id=STYLE_ID)

    bias = context_bias(cloud)
    close = float(trigger_rows[-1]["close"])
    lookback = trigger_rows[-(config["resume_lookback"] + 1):-1]
    extreme = None
    if bias and lookback:
        extreme = (max(float(row["high"]) for row in lookback) if bias == "up"
                   else min(float(row["low"]) for row in lookback))

    state = classify(previous_state=previous_state, bias=bias, close=close,
                     tenkan=cloud["tenkan"], kijun=cloud["kijun"],
                     chop=chop["value"], chop_previous=chop["previous"],
                     chop_choppy=config["chop_choppy"], extreme=extreme)

    story = intraday_story.envelope(
        schema=SCHEMA, style_id=STYLE_ID, asset=asset, timeframe=trigger_timeframe,
        rows=trigger_rows, candle_basis=candle_basis, state=state,
        previous_state=previous_state, display_bars=config["display_bars"])
    context_bars = min(config["display_bars"], len(context_rows))
    story |= {
        "direction": bias,
        "context_timeframe": context_timeframe,
        "trigger_timeframe": trigger_timeframe,
        "context_bar_at": context_rows[-1]["at"],
        "context_close_at": context_close_at,
        "context_basis": context_basis,
        "context_display": {"bars": context_bars,
                            "start_at": context_rows[-context_bars]["at"],
                            "start_date": context_rows[-context_bars]["date"],
                            "end_date": context_rows[-1]["date"]},
        "ichimoku": {"tenkan": cloud["tenkan"], "kijun": cloud["kijun"],
                     "tenkan_above_kijun": cloud["tenkan_above_kijun"],
                     "position": cloud["position"], "cloud_now": cloud["cloud_now"],
                     "cloud_ahead": cloud["cloud_ahead"],
                     "conversion": cloud["conversion"], "base": cloud["base"],
                     "span_b_length": cloud["span_b_length"]},
        "chop": {"value": chop["value"], "previous": chop["previous"],
                 "falling": chop["falling"], "length": chop["length"]},
        "atr": {"value": volatility["value"], "previous": volatility["previous"],
                "rising": volatility["rising"], "length": volatility["length"]},
        "thresholds": {"chop_trending": config["chop_trending"],
                       "chop_choppy": config["chop_choppy"]},
        "pullback_zone": {"near": cloud["tenkan"], "far": cloud["kijun"],
                          "low": min(cloud["tenkan"], cloud["kijun"]),
                          "high": max(cloud["tenkan"], cloud["kijun"])},
        # เส้นที่ทำให้ "ย่อเพื่อไปต่อ" ใช้ไม่ได้แล้ว = Kijun ของ M30
        # เลือก Kijun ไม่ใช่ขอบเมฆ เพราะ Kijun อยู่ใกล้กว่าและเป็นเส้นที่การย่อรอบนี้
        # กำลังทดสอบจริง ส่วนขอบเมฆเป็นเงื่อนไขของ *บริบท* ซึ่งถ้าเสียก็หมด bias อยู่แล้ว
        "invalidation": {"level": cloud["kijun"], "kind": "kijun_m30",
                         "rule": ("ราคาปิด M15 หลุดเส้น Kijun ของ M30 สวนทิศหลัก"
                                  if bias else "ยังไม่มีทิศหลักให้เสีย")},
        "triggers": ([f"สถานะเปลี่ยนจาก {previous_state} เป็น {state}"]
                     if previous_state and previous_state != state else []),
    }
    return story
