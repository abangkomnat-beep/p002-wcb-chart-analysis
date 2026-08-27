"""Thai article renderer and fail-closed validator for dual-timeframe Style E+."""

from __future__ import annotations

import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from tools import style_e_plus_daily_conditional, style_e_plus_story, wcb_writers

MIN_CHARS = 1000
STATE_HEADINGS = {
    "NO_PLAN": (
        "สถานะวันนี้: NO_PLAN (เน้นเฝ้าระวัง – ยังไม่มีจุดเข้าเทรด)",
        "ภาพรวมตลาดและกรอบ H1 (H1 Framework)",
        "เหตุผลที่ไม่มีแผนเทรด M15",
        "เงื่อนไขสำหรับประเมินรอบถัดไป",
    ),
    "NO_CHASE": (
        "สถานะวันนี้: NO_CHASE (งดไล่ราคา – รอประเมินรอบถัดไป)",
        "ภาพรวมตลาดและกรอบ H1 (H1 Framework)",
        "เหตุผลที่งดไล่ราคาใน M15",
        "เงื่อนไขสำหรับประเมินรอบถัดไป",
    ),
    "WAIT_TRIGGER": (
        "แผน M15 วันนี้: รอยืนยันจุดเข้า (WAIT_TRIGGER)",
        "ภาพรวมตลาดและกรอบ H1 (H1 Framework)",
        "กลยุทธ์และเหตุผลของแผน M15",
        "เงื่อนไขยกเลิกแผนก่อนเข้า",
    ),
    "ENTRY_READY": (
        "แผน M15 วันนี้: Trigger พร้อม แต่ยังไม่มี Fill (ENTRY_READY)",
        "ภาพรวมตลาดและกรอบ H1 (H1 Framework)",
        "กลยุทธ์และเหตุผลของแผน M15",
        "เงื่อนไขยกเลิกแผนก่อนเข้า",
    ),
}
FORBIDDEN_TERMS = (
    "VWAP", "OBV", "RSI", "MACD", "Fibonacci", "ชวนคุย", "ข่าว",
    "แหล่งข้อมูล", "Disclaimer", "📌", "📈", "📉", "⚠", "✅", "❌",
    "Volume", "Pin Bar", "Mean Reversion", "มีโอกาสสำเร็จสูง", "คุ้มค่า",
    "ดีที่สุด", "win rate", "backtest",
)


def publication_slug(story: dict) -> str:
    return f"btcusd-eplus-h1-m15-{story['publish_date']}"


def _thai_date(value: str) -> str:
    months = ("มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
              "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม")
    parsed = date.fromisoformat(value)
    return f"{parsed.day} {months[parsed.month - 1]} {parsed.year}"


def _thai_datetime(value: str) -> str:
    """Format an already validated aware timestamp in Asia/Bangkok time."""
    months = ("ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
              "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.")
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise style_e_plus_story.StoryUnavailable(
            "Daily Watch timestamp แปลงเวลาไม่ได้") from exc
    if parsed.tzinfo is None:
        raise style_e_plus_story.StoryUnavailable(
            "Daily Watch timestamp ต้องระบุ timezone")
    local = parsed.astimezone(ZoneInfo("Asia/Bangkok"))
    return f"{local.day} {months[local.month - 1]} {local.year} ({local:%H:%M} น.)"


def _money(value: float) -> str:
    return f"{float(value):,.2f}"


def _pct(value: float) -> str:
    numeric = float(value)
    # Keep the side of the system's 50% gate visible; one decimal would turn
    # 49.99% into the misleading public value 50.0%.
    if abs(numeric - 50.0) <= 0.1:
        return f"{numeric:.2f}%"
    return f"{numeric:.1f}%"


def _index(value: float) -> str:
    return f"{float(value):.1f}"


def _side_label(side: str | None) -> str:
    return "BUY" if side == "buy" else ("SELL" if side == "sell" else "WAIT")


def _m15_close_relation(close: float, ema20: float, atr: float) -> str:
    """Describe the close/EMA relationship using the M15 data itself."""
    distance = abs(float(close) - float(ema20))
    near_threshold = 0.25 * abs(float(atr))
    if distance <= near_threshold:
        return "อยู่ใกล้เส้น EMA20"
    if close > ema20:
        return "อยู่เหนือเส้น EMA20"
    if close < ema20:
        return "อยู่ต่ำกว่าเส้น EMA20"
    return "อยู่ระดับเดียวกับเส้น EMA20"


def _state_reason(story: dict) -> str:
    if story["state"] == "NO_PLAN" and story.get("side") is None:
        return f"{story['bias_reason']} จึงยังไม่สร้าง execution map M15"
    return story["decision_reason"]


def excerpt(story: dict) -> str:
    """SEO excerpt using the same 120–160 character contract as other styles."""
    state = str(story["state"])
    excerpts = {
        "NO_PLAN": "วิเคราะห์ BTC/USD จากแนวโน้ม H1 และแท่งปิด M15 ล่าสุด สรุปว่ายังไม่มีระดับแผนในรอบนี้ พร้อมเหตุผลจากระบบและจังหวะประเมินรอบถัดไป",
        "NO_CHASE": "วิเคราะห์ BTC/USD จากแนวโน้ม H1 และแท่งปิด M15 ล่าสุด สรุปว่างดไล่ราคาเมื่อพ้นโซน พร้อมกรอบการรอประเมินรอบถัดไปและแท่งปิดชุดถัดไป",
        "WAIT_TRIGGER": "วิเคราะห์ BTC/USD จากแนวโน้ม H1 และแผน M15 ที่มีระดับคำนวณแล้ว สรุปรอแท่งปิดยืนยัน trigger ก่อนพิจารณาเข้า โดยไม่ไล่ราคา",
        "ENTRY_READY": "วิเคราะห์ BTC/USD จากแนวโน้ม H1 และแผน M15 ที่ trigger ผ่านแล้ว สรุประดับตามระบบพร้อมย้ำว่ายังไม่มี fill หรือ position ยืนยัน",
    }
    if state not in excerpts:
        raise style_e_plus_story.StoryUnavailable(f"state ไม่รองรับ excerpt: {state}")
    text = wcb_writers.fit_excerpt([
        excerpts[state],
    ])
    if not wcb_writers.EXCERPT_MIN <= len(text) <= wcb_writers.EXCERPT_MAX:
        raise style_e_plus_story.StoryUnavailable(
            f"excerpt ยาว {len(text)} ตัวอักษร ไม่อยู่ในช่วง "
            f"{wcb_writers.EXCERPT_MIN}–{wcb_writers.EXCERPT_MAX}")
    return text


def _m15_image_alt(story: dict) -> str:
    if not story.get("plan"):
        return "ภาพที่ 2 BTC/USD M15 แสดงราคาปิดและ EMA20 โดยไม่มีแผนเทรด"
    return "ภาพที่ 2 แผนเข้าเทรด BTC/USD M15 พร้อมระดับยกเลิก Protective Stop และ TP"


def _action_plan(story: dict) -> str:
    state, plan, side = story["state"], story.get("plan"), story.get("side")
    h1_close = _money(story["current"]["close"])
    m15_close = _money(story["m15"]["current"]["close"])
    if not plan:
        label = (
            "NO_CHASE (งดไล่ราคา – รอประเมินรอบถัดไป)"
            if state == "NO_CHASE" else
            "NO_PLAN (เน้นเฝ้าระวัง – ยังไม่มีจุดเข้าเทรด)"
        )
        status_copy = (
            f"ราคาปิดเลย Entry Zone สำหรับฝั่ง {_side_label(side)} แล้ว "
            "จึงควรงดไล่ราคาและรอประเมินใหม่จากแท่งปิดถัดไป"
            if state == "NO_CHASE" else
            "โดยรวมยังไม่เข้าเงื่อนไขระบบเทรด M15 ในรอบนี้ "
            "แนะนำให้พักมือและรอสังเกตการณ์ราคาปิดของแท่งถัดไปเพื่อประเมินสถานการณ์อีกครั้ง"
        )
        close_text = (
            f"ราคาปิดในไทม์เฟรม H1 และ M15 ล่าสุดอยู่ที่ระดับ **{h1_close} ดอลลาร์**"
            if h1_close == m15_close else
            f"ราคาปิด H1 ล่าสุดอยู่ที่ระดับ **{h1_close} ดอลลาร์** "
            f"และ M15 ล่าสุดอยู่ที่ระดับ **{m15_close} ดอลลาร์**"
        )
        return (
            f"> **สถานะวันนี้:** **{label}**\n>\n"
            f"> {close_text} "
            f"{status_copy}"
        )
    direction = "เหนือ" if side == "buy" else "ต่ำกว่า"
    verb = "ซื้อ" if side == "buy" else "ขาย"
    state_text = (
        "WAIT_TRIGGER (รอ trigger)"
        if state == "WAIT_TRIGGER" else
        "ENTRY_READY (เงื่อนไข Trigger ครบถ้วน · ยังไม่มีข้อมูลยืนยัน Fill)"
    )
    note = (
        f"ภาพรวม H1 ให้น้ำหนักฝั่ง {side.upper()} แต่ M15 ยังไม่ยืนยัน ห้ามเปิดสถานะทันที "
        f"ให้รอแท่ง M15 ปิดกลับ{direction} EMA20 ภายใน Entry Zone"
        if state == "WAIT_TRIGGER" else
        f"แท่ง M15 ปิดยืนยันสัญญาณ {side.upper()} และราคายังอยู่ใน Entry Zone แล้ว "
        "ระบบนี้แสดงกรอบแผนเท่านั้นและยังไม่มีข้อมูลยืนยันการเปิดสถานะจริง (Fill)"
    )
    return (
        f"> **สถานะวันนี้:** **{state_text}**\n>\n> {note}\n\n"
        f"- **ทิศทางหลัก (H1 Bias):** **{_side_label(side)}**\n"
        f"- **เงื่อนไขเข้าเทรด (M15 Trigger):** แท่ง M15 ปิด{direction} "
        f"**{_money(plan['trigger'])} ดอลลาร์**\n"
        f"- **กรอบราคาเข้า{verb} (Entry Zone):** "
        f"**{_money(plan['entry_zone_low'])}–{_money(plan['entry_zone_high'])} ดอลลาร์**\n"
        f"- **ระดับยกเลิกก่อนเข้า (M15 close):** "
        f"**{_money(plan['pre_entry_invalidation_close'])} ดอลลาร์**\n"
        f"- **Protective Stop ตามแผน:** "
        f"**{_money(plan['protective_stop']['price'])} ดอลลาร์** "
        "*(inactive · มีผลได้เฉพาะหลัง external fill)*\n"
        f"- **เป้าหมายกำไร 1 (TP1):** **{_money(plan['tp1'])} ดอลลาร์** "
        f"*(อัตราผลตอบแทน {plan['rr1']:.1f}R)*\n"
        f"- **เป้าหมายกำไร 2 (TP2):** **{_money(plan['tp2'])} ดอลลาร์** "
        f"*(อัตราผลตอบแทน {plan['rr2']:.1f}R)*"
    )


def _h1_overview(story: dict) -> str:
    dmi = story["indicators"]["dmi_adx"]
    bbw = story["indicators"]["bbw"]
    atr = story["indicators"]["atr"]
    dc = story["indicators"]["donchian"]
    kc = story["indicators"]["keltner"]
    plus_di, minus_di = dmi["plus_di"], dmi["minus_di"]
    if plus_di > minus_di:
        direction = (f"ฝั่งซื้อยังได้เปรียบเล็กน้อย (+DI {_index(plus_di)} "
                     f"สูงกว่า -DI {_index(minus_di)})")
    elif minus_di > plus_di:
        direction = (f"ฝั่งขายยังได้เปรียบเล็กน้อย (-DI {_index(minus_di)} "
                     f"สูงกว่า +DI {_index(plus_di)})")
    else:
        direction = (f"แรงซื้อและแรงขายยังสูสีกัน (+DI {_index(plus_di)} "
                     f"เท่ากับ -DI {_index(minus_di)})")
    adx_copy = (
        "ถือว่าผ่านเกณฑ์ขั้นต่ำของระบบในการยืนยัน Bias ทางฝั่ง H1"
        if dmi["adx"] >= 20 else
        "ยังไม่ผ่านเกณฑ์ขั้นต่ำของระบบในการยืนยัน Bias ทางฝั่ง H1"
    )
    bbw_low = bbw["percentile"] < 50
    atr_low = atr["percentile"] < 50
    if bbw_low and atr_low:
        volatility = (
            f"ตลาดช่วงนี้ความผันผวนค่อนข้างเบาบาง โดย BandWidth Percentile อยู่ที่ "
            f"{_pct(bbw['percentile'])} และ ATR14 เท่ากับ {_money(atr['value'])} ดอลลาร์ "
            f"(หรือ {_pct(atr['percentile'])}) ซึ่งทั้งสองค่าต่ำกว่าเกณฑ์ 50% "
            "ตามเกณฑ์ของระบบรอบนี้ ความผันผวนยังไม่สนับสนุนการยืนยันแรงเบรกเอาต์"
        )
    elif bbw_low:
        volatility = (
            f"BandWidth Percentile อยู่ที่ {_pct(bbw['percentile'])} ซึ่งต่ำกว่าเกณฑ์ 50% "
            f"ขณะที่ ATR14 เท่ากับ {_money(atr['value'])} ดอลลาร์ "
            f"(หรือ {_pct(atr['percentile'])}) ซึ่งผ่านเกณฑ์ 50% "
            "ตามเกณฑ์ของระบบรอบนี้ เงื่อนไข BandWidth ยังไม่สนับสนุนการยืนยันแรงเบรกเอาต์"
        )
    elif atr_low:
        volatility = (
            f"ATR14 อยู่ที่ {_money(atr['value'])} ดอลลาร์ หรือ {_pct(atr['percentile'])} "
            f"ซึ่งต่ำกว่าเกณฑ์ 50% ขณะที่ BandWidth Percentile อยู่ที่ "
            f"{_pct(bbw['percentile'])} ซึ่งผ่านเกณฑ์ 50% "
            "ตามเกณฑ์ของระบบรอบนี้ เงื่อนไข ATR14 ยังไม่สนับสนุนการยืนยันแรงเบรกเอาต์"
        )
    else:
        volatility = (
            f"ความผันผวนอยู่ในระดับที่ผ่านเกณฑ์ของระบบ โดย BandWidth Percentile อยู่ที่ "
            f"{_pct(bbw['percentile'])} และ ATR14 เท่ากับ {_money(atr['value'])} ดอลลาร์ "
            f"(หรือ {_pct(atr['percentile'])}) ซึ่งทั้งสองค่าผ่านเกณฑ์ 50%"
        )
    framework_reason = ""
    if plus_di > minus_di and dc["upper"] < kc["upper"]:
        framework_reason = " ตามเกณฑ์ของระบบรอบนี้ กรอบ Donchian ยังไม่ยืนยันแรงฝั่งซื้อ"
    elif minus_di > plus_di and dc["lower"] > kc["lower"]:
        framework_reason = " ตามเกณฑ์ของระบบรอบนี้ กรอบ Donchian ยังไม่ยืนยันแรงฝั่งขาย"
    return (
        f"- **ทิศทางแรงซื้อขาย:** {direction} ประกอบกับ ADX14 อยู่ที่ "
        f"{_index(dmi['adx'])} ซึ่ง{adx_copy}\n"
        f"- **สภาพความผันผวน:** {volatility}\n"
        f"- **กรอบแนวรับ-แนวต้าน H1:** กรอบ Donchian20 อยู่ที่ "
        f"{_money(dc['lower'])}–{_money(dc['upper'])} "
        f"ดอลลาร์ ส่วน Keltner อยู่ที่ {_money(kc['lower'])}–{_money(kc['upper'])} ดอลลาร์ "
        "ใช้เป็นบริบทแนวรับ-แนวต้านของตลาดเท่านั้น ยังไม่ใช่จุดเข้าออเดอร์"
        f"{framework_reason}"
    )


def _m15_execution(story: dict) -> str:
    m15 = story["m15"]
    indicators = m15["indicators"]
    plan = story.get("plan")
    if not plan:
        close = m15["current"]["close"]
        market = (
            f"M15 ปิดล่าสุดที่ {_money(close)} ดอลลาร์ "
            f"{_m15_close_relation(close, indicators['ema20'], indicators['atr']['value'])} "
            f"({_money(indicators['ema20'])} ดอลลาร์)"
        )
        if story["state"] == "NO_CHASE":
            return (
                f"{market} {story['decision_reason']} ระบบจึงไม่สร้าง Execution Map "
                "ในรอบนี้และจะคำนวณใหม่จากแท่งปิด M15 ถัดไป"
            )
        return (
            f"{market} ระบบไม่สร้าง Execution Map ในรอบนี้ เนื่องจาก "
            f"{story['decision_reason']} และจะคำนวณใหม่จากแท่งปิด M15 ถัดไป"
        )
    side = plan["side"]
    close = m15["current"]["close"]
    market = (
        f"M15 ปิดล่าสุดที่ {_money(close)} ดอลลาร์ "
        f"{_m15_close_relation(close, indicators['ema20'], indicators['atr']['value'])} "
        f"({_money(indicators['ema20'])} ดอลลาร์)"
    )
    direction = "เหนือ" if side == "buy" else "ต่ำกว่า"
    confirmation = (
        "แท่ง M15 ปิดยืนยัน Trigger แล้ว แต่ระบบยังไม่มีข้อมูลยืนยันการเปิดสถานะจริง (Fill)"
        if story["state"] == "ENTRY_READY" else
        f"ต้องรอให้แท่ง M15 ปิดสมบูรณ์ (Candle Close) {direction} EMA20 "
        "ภายใน Entry Zone เท่านั้น การแตะระดับระหว่างแท่งยังไม่ถือว่าเกิด Trigger"
    )
    stop_direction = "ต่ำกว่า" if side == "buy" else "สูงกว่า"
    stop_edge = "ขอบล่าง" if side == "buy" else "ขอบบน"
    risk_edge = "ขอบบน" if side == "buy" else "ขอบล่าง"
    return (
        f"{market} {story['decision_reason']} จุดเข้าเทรดถูกย้ายจาก H1 ลงมาอยู่ที่ M15 โดยใช้ EMA20 ที่ "
        f"{_money(indicators['ema20'])} ดอลลาร์เป็นแกนกลาง และใช้ ATR14 M15 ที่ "
        f"{_money(indicators['atr']['value'])} ดอลลาร์กำหนดความกว้างของโซน\n\n"
        f"- **จังหวะยืนยัน:** {confirmation}\n"
        f"- **การจำกัดความเสี่ยง B100:** ใช้ confirmed swing ที่ {_money(plan['pivot']['price'])} "
        f"ร่วมกับ buffer {plan['structure_buffer_atr']:.2f} ATR; ระดับ Protective Stop "
        f"อยู่{stop_direction}{stop_edge}ของ Entry Zone โดยวัดระยะจาก{risk_edge}ของโซน "
        f"และระยะเสี่ยงเท่ากับ "
        f"{plan['risk_atr']:.2f} ATR ({_money(plan['risk'])} ดอลลาร์) "
        f"โดยใช้ตัวคูณขนาดอ้างอิง {plan['sizing_multiplier']:.2f} เท่านั้น "
        "ระดับนี้ยังไม่มีผลจนกว่าจะมีข้อมูลยืนยันการเปิดสถานะจริง (Fill)\n"
        "- **การจบแผน:** TP1 และ TP2 คำนวณจากระยะเสี่ยงจริง 1.5R และ 2.0R "
        "จึงเปรียบเทียบ Risk/Reward ได้จากภาพ M15 โดยตรง"
    )


def _invalidation(story: dict) -> str:
    plan = story.get("plan")
    if not plan:
        return (
            f"สถานะ {story['state']} ไม่มีระดับยกเลิกเชิงตัวเลขหรือแผนที่ต้องติดตาม "
            "ให้รอข้อมูลแท่งปิด H1 และ M15 ชุดถัดไปก่อนประเมินใหม่"
        )
    side = plan["side"]
    direction = "ต่ำกว่า" if side == "buy" else "สูงกว่า"
    return (
        f"- หลังเวลาเริ่มมีผล {plan['effective_from']} หากแท่ง M15 "
        f"ปิด{direction} **{_money(plan['pre_entry_invalidation_close'])} ดอลลาร์** "
        f"ให้ยกเลิกแผน {side.upper()} ก่อนเข้า เหตุการณ์นี้ไม่ใช่ Stop Loss\n"
        "- Protective Stop ในภาพเป็นระดับวางแผนเท่านั้น ยังไม่ active และรุ่นนี้ไม่อ้างผลการออกจากสถานะ\n"
        "- หากแท่ง M15 ปิดเลย Entry Zone ไปตามทิศทางของแผน "
        "ระบบจะเปลี่ยนเป็น NO_CHASE ให้งดไล่ราคาและรอคำนวณรอบใหม่"
    )


def _render_daily_conditional(story: dict) -> str:
    """Render the additive DC-T watch without inventing execution levels."""
    conditional = story.get("daily_conditional") or {}
    state = story.get("state") or "NO_PLAN"
    status = conditional.get("status", "ARMED")
    cutoff = conditional.get("session_cutoff", "")
    expiry = conditional.get("expires_at", "")
    geometry = conditional.get("watch_geometry") or {}
    buy = geometry.get("buy_watch", "—")
    sell = geometry.get("sell_watch", "—")
    cutoff_copy = _thai_datetime(cutoff)
    expiry_copy = _thai_datetime(expiry)
    buy_copy = "—" if buy in (None, "", "—") else _money(buy)
    sell_copy = "—" if sell in (None, "", "—") else _money(sell)
    return (
        f"## ระดับราคาเฝ้าระวังประจำวัน (Daily Watch Levels · {status})\n\n"
        f"โหมด Watch เท่านั้น ยังไม่ใช่จุดเข้าซื้อขาย (NOT ENTRY) และ Strict B100 "
        f"ยังคงสถานะ **{state}**\n\n"
        f"- **รอบการประเมิน:** {cutoff_copy} – {expiry_copy}\n\n"
        f"- **Buy Watch (โซนเฝ้าระวังฝั่งซื้อ):** {buy_copy} ดอลลาร์\n\n"
        f"- **Sell Watch (โซนเฝ้าระวังฝั่งขาย):** {sell_copy} ดอลลาร์\n"
        "คำแนะนำ: ต้องรอให้แท่งราคาปิดสมบูรณ์และได้รับการยืนยันตามระบบ Strict B100 "
        "ก่อนพิจารณาออกออเดอร์ทุกครั้ง"
    )


def _strict_view(story: dict) -> dict:
    """Return the strict B100 view from either a v4 story or v5 envelope."""
    if not isinstance(story, dict) or story.get("schema") != "style-e-plus-story/v5":
        return story
    view = {key: value for key, value in story.items()
            if key not in {"daily_conditional", "session_id",
                           "strict_projection_oracle", "watch_geometry_oracle",
                           "source_snapshot", "manifest"}}
    view["schema"] = "style-e-plus-story/v4"
    return view


def _render_strict_article(story: dict) -> str:
    style_e_plus_story.validate_story(story)
    headings = STATE_HEADINGS.get(story["state"])
    if headings is None:
        raise style_e_plus_story.StoryUnavailable(f"state ไม่รองรับ heading: {story['state']}")
    h1_image, m15_image = story["images"]["h1"], story["images"]["m15"]
    summary = excerpt(story)
    lines = [
        "---",
        f'title: "วิเคราะห์ BTC/USD (H1/M15) ประจำวันที่ {_thai_date(story["publish_date"])}"',
        f'date: "{story["publish_date"]}"',
        f'slug: "{publication_slug(story)}"',
        f'excerpt: "{summary}"',
        f'author_slug: "{wcb_writers.author_slug_for(story["asset"])}"',
        f'image: "{h1_image}"',
        f'image_m15: "{m15_image}"',
        'asset: "BTC/USD"',
        'timeframe: "H1/M15"',
        "---", "",
        f"## {headings[0]}", "", _action_plan(story), "",
        f"![ภาพที่ 1 โครงสร้าง BTC/USD H1 และความพร้อมของแนวโน้ม]({h1_image})", "",
        f"## {headings[1]}", "", _h1_overview(story), "",
        f"![{_m15_image_alt(story)}]({m15_image})", "",
        f"## {headings[2]}", "", _m15_execution(story), "",
        f"## {headings[3]}", "", _invalidation(story), "",
    ]
    return "\n".join(lines)


def render_article(story: dict) -> str:
    """Render strict B100 first, then append an additive DC-T watch section."""
    if isinstance(story, dict) and "daily_conditional" in story:
        try:
            style_e_plus_daily_conditional.validate(
                story,
                strict_story=style_e_plus_daily_conditional._strict_from_artifact(story),
                check_nested_parity=False,
            )
        except style_e_plus_daily_conditional.ContractError as exc:
            raise style_e_plus_story.StoryUnavailable(
                f"DC-T validation failed closed: {exc}") from exc
        strict_story = _strict_view(story)
        try:
            strict_markdown = _render_strict_article(strict_story)
        except style_e_plus_story.StoryUnavailable:
            # The isolated contract fixture is intentionally not a complete
            # publication story; retain a deterministic watch-only preview.
            # Production-shaped stories have no marker and must fail closed.
            if (story.get("_incomplete_fixture") is True and
                    "source_snapshot" not in story and "manifest" not in story):
                return _render_daily_conditional(story)
            raise
        watch = _render_daily_conditional(story)
        return f"{strict_markdown}\n\n{watch}"
    return _render_strict_article(story)


render = render_article


def _finding(rule: str, message: str) -> dict:
    return {"rule": rule, "severity": "fatal", "line": 1, "message": message}


def _h1_copy_is_semantic(story: dict, markdown: str) -> bool:
    """Check H1 meaning from indicators instead of requiring raw reason prose."""
    headings = STATE_HEADINGS.get(story.get("state"), ())
    if len(headings) < 2:
        return False
    marker = f"## {headings[1]}"
    if marker not in markdown:
        return False
    h1_copy = markdown.split(marker, 1)[1].split("\n![", 1)[0]
    dmi = story["indicators"]["dmi_adx"]
    bbw = story["indicators"]["bbw"]
    atr = story["indicators"]["atr"]
    dc = story["indicators"]["donchian"]
    kc = story["indicators"]["keltner"]
    if bbw["percentile"] < 50 or atr["percentile"] < 50:
        return (
            "สภาพความผันผวน" in h1_copy and
            "ต่ำกว่าเกณฑ์ 50%" in h1_copy and
            "ยังไม่สนับสนุนการยืนยันแรงเบรกเอาต์" in h1_copy
        )
    if dmi["adx"] < 20 or abs(dmi["plus_di"] - dmi["minus_di"]) <= 1e-12:
        return (
            "ยังไม่ผ่านเกณฑ์ขั้นต่ำของระบบในการยืนยัน Bias ทางฝั่ง H1" in h1_copy
            and ("แรงซื้อและแรงขายยังสูสีกัน" in h1_copy or
                 "ฝั่งซื้อยังได้เปรียบเล็กน้อย" in h1_copy or
                 "ฝั่งขายยังได้เปรียบเล็กน้อย" in h1_copy)
        )
    if dmi["plus_di"] > dmi["minus_di"] and dc["upper"] < kc["upper"]:
        return "กรอบ Donchian ยังไม่ยืนยันแรงฝั่งซื้อ" in h1_copy
    if dmi["minus_di"] > dmi["plus_di"] and dc["lower"] > kc["lower"]:
        return "กรอบ Donchian ยังไม่ยืนยันแรงฝั่งขาย" in h1_copy
    side_phrase = (
        "ฝั่งซื้อยังได้เปรียบเล็กน้อย" if dmi["plus_di"] > dmi["minus_di"]
        else "ฝั่งขายยังได้เปรียบเล็กน้อย"
    )
    return side_phrase in h1_copy and "ผ่านเกณฑ์ขั้นต่ำของระบบในการยืนยัน Bias ทางฝั่ง H1" in h1_copy


def validate(markdown: str, story: dict, *, now: datetime | None = None) -> dict:
    findings: list[dict] = []
    try:
        style_e_plus_story.validate_story(story, now=now)
    except style_e_plus_story.StoryUnavailable as exc:
        findings.append(_finding("story_contract", str(exc)))
    expected = ""
    if not findings:
        try:
            expected = render_article(story)
        except style_e_plus_story.StoryUnavailable as exc:
            findings.append(_finding("story_contract", str(exc)))
    if expected and markdown != expected:
        findings.append(_finding(
            "deterministic_copy", "บทไม่ตรงผล render จาก story ทุกตัวอักษร — อาจมีเลขหรือสถานะถูกแก้มือ"))
    headings = re.findall(r"^##\s+(.+)$", markdown, flags=re.MULTILINE)
    expected_headings = list(STATE_HEADINGS.get(story.get("state"), ()))
    if isinstance(story, dict) and "daily_conditional" in story:
        expected_headings.append("ระดับราคาเฝ้าระวังประจำวัน (Daily Watch Levels · " +
                                 str(story["daily_conditional"].get("status", "ARMED")) + ")")
    if not expected_headings or tuple(headings) != tuple(expected_headings):
        findings.append(_finding("h2_structure", "หัวข้อ H2 ไม่ตรงโครง Style E+ ตามสถานะ หรือมีเลขลำดับ"))
    if re.search(r"^##\s+\d+[\.\)]", markdown, flags=re.MULTILINE):
        findings.append(_finding("numbered_h2", "หัวข้อ H2 ห้ามมีเลขลำดับ"))
    for term in FORBIDDEN_TERMS:
        if term.lower() in markdown.lower():
            findings.append(_finding("forbidden_term", f"พบถ้อยคำต้องห้าม: {term}"))
    images = story.get("images") or {}
    for role in ("h1", "m15"):
        name = images.get(role, "")
        if not name or markdown.count(f"]({name})") != 1:
            findings.append(_finding("image_reference", f"บทต้องอ้างภาพ {role.upper()} หนึ่งครั้ง"))
    if story.get("state") in {"NO_PLAN", "NO_CHASE"}:
        for term in ("Entry Zone):", "Protective Stop ตามแผน):", "TP1):", "TP2):"):
            if term in markdown:
                findings.append(_finding("plan_forbidden", f"{story['state']} ห้ามมี {term}"))
        if "ภาพที่ 2 แผนเข้าเทรด BTC/USD M15 พร้อมระดับยกเลิก" in markdown:
            findings.append(_finding(
                "planless_image_copy", f"{story['state']} ห้ามบรรยายภาพ M15 ว่ามีแผนเข้า/SL/TP"))
    bias_reason = story.get("bias_reason")
    if not bias_reason or not _h1_copy_is_semantic(story, markdown):
        findings.append(_finding(
            "bias_reason_copy", "บทต้องแสดงเหตุผล H1 ตาม branch และ indicator โดยไม่บิดความหมาย"))
    decision_reason = story.get("decision_reason")
    if not decision_reason or markdown.count(decision_reason) != 1:
        findings.append(_finding(
            "decision_reason_copy", "บทต้องแสดงเหตุผล state จาก story แบบตรงข้อความเพียงหนึ่งครั้ง"))
    char_count = len(re.sub(r"\s+", "", markdown))
    if char_count < MIN_CHARS:
        findings.append(_finding(
            "minimum_length", f"บทมี {char_count} อักขระ ต่ำกว่าเกณฑ์ {MIN_CHARS}"))
    ok = not findings
    return {"status": "pass" if ok else "fail", "ok": ok,
            "char_count": char_count, "findings": findings,
            "slug": publication_slug(story) if isinstance(story, dict) and story.get("publish_date") else None,
            "validated_at": (now or datetime.now()).isoformat(timespec="seconds")}
