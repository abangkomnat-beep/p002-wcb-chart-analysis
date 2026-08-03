"""ประกอบบทความสาธารณะจากหลักฐาน — ตัวเลขทุกตัวมาจาก evidence pack เท่านั้น

ลำดับที่บังคับ: สร้าง article.json (หลักฐาน) ก่อน แล้วค่อยเรนเดอร์ Markdown จากไฟล์นั้น
ทำแบบนี้ตัวเลขในบทความจะตรงกับหลักฐานโดยโครงสร้าง ไม่ต้องหวังว่าใครจะพิมพ์ตรง

โครงบทความใช้ WCB Voice Spec v1 (ฉบับที่ CC ล็อก 2026-08-03) — เล่าเรื่อง 4 ช่วง:
หัวเรื่อง → บรรทัดเวลา → ① ย่อหน้าเปิด → (② ปัจจัยจับตา — ระยะ 1 ไม่มีข่าว ตัดเงียบ)
→ ③ ข้อมูลเทคนิค (Technical Analysis) ร้อยแก้ว → ④ บล็อกแนวรับ/แนวต้าน + หมายเหตุ
+ disclaimer → กราฟ + caption 1 บรรทัด

กติกาเหล็ก:
- ห้ามคำนวณเลขใหม่ — ทุกตัวเลขปัดครั้งเดียวจากค่าดิบใน evidence (tools/voice_rules.py)
- สิ่งที่ evidence ไม่มี = ตัดประโยคทิ้งเงียบ ๆ ไม่เขียนคำแก้ตัวให้ผู้อ่านเห็น
- ข้อความเชิงระบบทั้งหมดอยู่ฝั่ง internal เท่านั้น
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import voice_rules  # noqa: E402


CONTRACT = "WCB Daily Output Contract v3.1 (Voice v1)"
SCHEMA_VERSION = "3.1.0"

INSTRUMENT_LABEL = {
    "forex_spot": "อัตราแลกเปลี่ยนตลาดสปอต",
    "crypto_spot": "คริปโทเคอร์เรนซีตลาดสปอต",
    "spot_metal": "โลหะมีค่าตลาดสปอต",
}

# ชื่อเต็มหัวบล็อกแนวรับ/แนวต้าน (spec ช่วง ④ — ผู้อ่านประจำต้องหาเจอที่เดิมทุกวัน)
BLOCK_LABEL = {
    "EUR/USD": "EUR/USD (Euro/US Dollar)",
    "BTC/USD": "BTC/USD (Bitcoin/US Dollar)",
    "XAU/USD": "XAU/USD (Gold Spot)",
}

# field นโยบาย/พารามิเตอร์ภายใน — ห้ามอยู่ในไฟล์ฝั่ง public ไม่ว่าชั้นไหนของ JSON
# ขยายรายการได้ที่นี่ที่เดียว: ตัวตัด (strip_internal_fields) และเทสกันหลุดซ้ำ
# (tests/test_public_output_hygiene.py) อ่านจากชุดเดียวกันนี้
PUBLIC_FIELD_DENYLIST = frozenset({
    "merge_tolerance",
    "quality_status",
    "approved_for_publication",
    "allowed_language",
    "forbidden_language",
})


def strip_internal_fields(node):
    """คืนสำเนาที่ตัด field ภายในออกทุกชั้น — ใช้กับข้อมูลที่กำลังจะเขียนฝั่ง public เท่านั้น

    ฝั่ง internal เก็บ field เหล่านี้ไว้ได้ตามเดิม เพราะมีประโยชน์ต่อการ audit
    """
    if isinstance(node, dict):
        return {key: strip_internal_fields(value)
                for key, value in node.items() if key not in PUBLIC_FIELD_DENYLIST}
    if isinstance(node, list):
        return [strip_internal_fields(item) for item in node]
    return node


def change_summary(report: dict) -> dict:
    """ค่าการเปลี่ยนแปลงที่บทความใช้ — บันทึกลง technical.evidence.json เป็นหลักฐาน

    บทความแสดง "ขนาด" ของการเปลี่ยนแปลง (ค่าสัมบูรณ์) คู่กับคำบอกทิศ เพิ่มขึ้น/ลดลง
    จึงต้องบันทึกทั้งค่าจริงที่มีเครื่องหมายและขนาดที่แสดงจริง ไม่อย่างนั้นวันที่ราคาลง
    validator จะหาตัวเลขในบทความไม่เจอในหลักฐาน (number_rounding)
    """
    candles = report.get("candles") or []
    if not candles:
        return {"latest_close": None, "previous_close": None, "change": None,
                "change_percent": None, "change_magnitude": None,
                "change_percent_magnitude": None}
    price = float(candles[-1]["close"])
    valid = [item for item in candles
             if item.get("is_expected_session") and item["candle_state"] == "closed"]
    previous_close = float(valid[-1]["close"]) if valid else None
    change = price - previous_close if previous_close is not None else None
    percent = (change / previous_close * 100) if change is not None and previous_close else None
    return {
        "latest_close": price,
        "previous_close": previous_close,
        "change": change,
        "change_percent": percent,
        "change_magnitude": abs(change) if change is not None else None,
        "change_percent_magnitude": abs(percent) if percent is not None else None,
    }


# ---------------------------------------------------------------- เลือกระดับช่วง ④
def select_block_levels(zones: list[dict], price: float, instrument_type: str | None,
                        *, per_side: int = 3) -> dict:
    """เลือกแนวรับ/แนวต้านฝั่งละไม่เกิน 3 ค่า เรียงใกล้ราคา → ไกล (spec ช่วง ④)

    - ระดับโซนใช้ขอบด้านที่ใกล้ราคาปัจจุบันเป็นตัวแทน 1 ค่า (spec กติกาเลือกค่า)
    - โซนที่คร่อมราคาอยู่ = ยังไม่รู้ว่าเป็นรับหรือต้าน — ข้ามเงียบ
    - ถ้าปัดเลขแล้วสองระดับกลายเป็นข้อความเดียวกัน ข้ามไประดับถัดไป (ห้ามขยับเลขหนี)
    """
    below: list[tuple[float, dict]] = []
    above: list[tuple[float, dict]] = []
    for level in zones:
        if not level.get("approved_for_publication"):
            continue
        value = level.get("value")
        if value is not None:
            anchor = float(value)
            if anchor < price:
                below.append((anchor, level))
            elif anchor > price:
                above.append((anchor, level))
            continue
        low, high = level.get("zone_low"), level.get("zone_high")
        if low is None or high is None:
            continue
        if float(high) < price:
            below.append((float(high), level))
        elif float(low) > price:
            above.append((float(low), level))

    def pick(candidates: list[tuple[float, dict]], *, descending: bool) -> list[dict]:
        chosen: list[dict] = []
        seen_text: set[str] = set()
        for anchor, level in sorted(candidates, key=lambda item: item[0], reverse=descending):
            text = voice_rules.format_price(anchor, instrument_type)
            if text in seen_text:
                continue  # ปัดแล้วชนกัน — ข้ามไปใช้ระดับถัดไปตาม spec
            seen_text.add(text)
            chosen.append({"level_id": level["id"], "raw": anchor, "text": text})
            if len(chosen) == per_side:
                break
        return chosen

    return {
        "supports": pick(below, descending=True),      # ใกล้ราคา → ไกล (ลงล่าง)
        "resistances": pick(above, descending=False),  # ใกล้ราคา → ไกล (ขึ้นบน)
    }


# ---------------------------------------------------------------- ประกอบ evidence pack
def build_article_data(
    *,
    report: dict,
    level_map: dict,
    chart_metadata: dict,
    license_result: dict,
    symbol: str,
    instrument_type: str,
    unit: str,
    decimals: int,
    cutoff_at: str,
    batch_id: str,
    verified_news: list[dict] | None = None,
) -> dict:
    candles = report["candles"]
    latest = candles[-1]
    summary = change_summary(report)
    price = summary["latest_close"]

    published = report["published_indicator_values"]
    sma20, sma50 = published.get("sma20"), published.get("sma50")
    rsi14, atr14 = published.get("rsi14"), published.get("atr14")

    zones = level_map["zones"]
    block = select_block_levels(zones, price, instrument_type)

    change = summary["change"]
    move_class = voice_rules.classify_move(summary["change_percent_magnitude"], instrument_type)
    if change is None:
        direction = "unknown"
    elif change > 0:
        direction = "up"
    elif change < 0:
        direction = "down"
    else:
        direction = "flat"

    headline = _headline(
        symbol=symbol, price=price, sma20=sma20, sma50=sma50,
        direction=direction, move_class=move_class,
        block=block, instrument_type=instrument_type,
    )

    payload = {
        "contract": CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "voice_spec": voice_rules.SPEC_REFERENCE,
        "batch_id": batch_id,
        "instrument": {
            "symbol": symbol,
            "instrument_type": instrument_type,
            "instrument_label": INSTRUMENT_LABEL.get(instrument_type, instrument_type),
            "block_label": BLOCK_LABEL.get(symbol, symbol),
            "unit": unit,
            "decimals": decimals,
            "cutoff_at": cutoff_at,
            "cutoff_public": (f"{voice_rules.thai_date_text(cutoff_at)} "
                              f"เวลา {voice_rules.thai_time_text(cutoff_at)} น. (เวลาไทย)"),
            "candle_state": latest["candle_state"],
            "session_timezone": report["session_timezone"],
            "public_timezone": report["public_timezone"],
        },
        "headline": headline,
        "snapshot": {
            "price": price,
            "previous_close": summary["previous_close"],
            "change": change,
            "percent": summary["change_percent"],
            "change_magnitude": summary["change_magnitude"],
            "percent_magnitude": summary["change_percent_magnitude"],
            "open": float(latest["open"]),
            "high": float(latest["high"]),
            "low": float(latest["low"]),
            "valid_completed_bars": report["valid_completed_bars"],
        },
        "move": {"direction": direction, "class": move_class},
        "drivers": {
            "verified_news": verified_news or [],
            "causal_claims_allowed": bool(verified_news),
        },
        "technical": {
            "sma20": sma20, "sma50": sma50, "rsi14": rsi14, "atr14": atr14,
            "unavailable_indicators": [
                name for name, item in report["indicators"].items()
                if not item["approved_for_publication"]
            ],
            "timeframes_available": ["1d"],
        },
        # ฝั่ง public เอาเฉพาะระดับที่ผ่านการตรวจแล้ว — ระดับที่ไม่ผ่านอยู่ฝั่ง internal
        "levels": [level for level in zones if level.get("approved_for_publication")],
        "sr_block": {
            **block,
            "note": (voice_rules.NOTE_FORMING if latest["candle_state"] == "forming"
                     else voice_rules.NOTE_CLOSED),
        },
        "visuals": chart_metadata,
        # ชุดนี้เป็น Public Article Pack — ผลด่านและรายละเอียดสัญญาสิทธิ์เป็นของภายใน
        # เก็บไว้เฉพาะสิ่งที่ผู้อ่านต้องเห็นจริง คือเครดิตแหล่งข้อมูลเมื่อสัญญาบังคับ
        "attribution_required": license_result.get("attribution_required", []),
    }
    # ตัด field นโยบายภายใน (merge_tolerance, quality_status, ฯลฯ) ออกทุกชั้น
    # ก่อนไฟล์นี้จะกลายเป็น public/article.json
    return strip_internal_fields(payload)


# ---------------------------------------------------------------- หัวเรื่อง (≤12 คำ)
def _headline(*, symbol, price, sma20, sma50, direction, move_class, block,
              instrument_type) -> str:
    """สูตร spec: ชื่อสินทรัพย์ + กริยาสถานะจากคลังสำนวน + ระดับที่เป็นประเด็นของวัน

    ห้ามศัพท์รหัส — เรียกระดับตามบทบาท (แนวรับ/แนวต้าน) เท่านั้น
    """
    resistance = block["resistances"][0]["text"] if block["resistances"] else None
    support = block["supports"][0]["text"] if block["supports"] else None

    if sma20 is not None and sma50 is not None:
        above20, above50 = price > sma20, price > sma50
        if above20 and above50:
            state, prefer_resistance = "ยืนเหนือเส้นค่าเฉลี่ย", True
        elif not above20 and not above50:
            state, prefer_resistance = "อยู่ใต้เส้นค่าเฉลี่ย", False
        else:
            state, prefer_resistance = "แกว่งระหว่างเส้นค่าเฉลี่ย", direction != "down"
    elif sma20 is not None:
        prefer_resistance = price > sma20
        state = "ยืนเหนือเส้นค่าเฉลี่ยระยะสั้น" if prefer_resistance else "หลุดเส้นค่าเฉลี่ยระยะสั้น"
    else:
        if move_class == voice_rules.MOVE_QUIET:
            state, prefer_resistance = "แกว่งตัวในกรอบ", True
        elif direction == "up":
            state, prefer_resistance = "ปรับตัวขึ้น", True
        elif direction == "down":
            state, prefer_resistance = "ปรับตัวลง", False
        else:
            state, prefer_resistance = "ทรงตัว", True

    if prefer_resistance and resistance:
        return f"{symbol} {state} จับตาแนวต้าน {resistance}"
    if support:
        return f"{symbol} {state} จับตาแนวรับ {support}"
    if resistance:
        return f"{symbol} {state} จับตาแนวต้าน {resistance}"
    return f"{symbol} {state} รอระดับใหม่ยืนยันทิศทาง"


# ---------------------------------------------------------------- ช่วง ① ย่อหน้าเปิด
def _opening_paragraph(data: dict) -> str:
    instrument = data["instrument"]
    snapshot = data["snapshot"]
    move = data["move"]
    kind = instrument["instrument_type"]
    unit = instrument["unit"]
    symbol = instrument["symbol"]

    date_text = voice_rules.thai_date_text(instrument["cutoff_at"])
    open_text = voice_rules.format_price(snapshot["open"], kind)
    last_text = voice_rules.format_price(snapshot["price"], kind)

    # ประโยคแรก: สูตรตายตัวของ spec + กริยาต่อเนื่องจากคลังหมวด ก. ตามตาราง 2.6
    first = f"วันนี้ ( {date_text} ) {symbol} เปิดตลาดที่ระดับ {open_text} {unit}"
    continuation = {
        ("up", voice_rules.MOVE_NORMAL): (
            f" ก่อนจะมีแรงซื้อเพิ่มเติมหนุนราคาขึ้นมาเคลื่อนไหวแถว {last_text} {unit}"),
        ("up", voice_rules.MOVE_STRONG): (
            f" ก่อนทะยานพุ่งต่อเนื่องขึ้นมาเคลื่อนไหวแถว {last_text} {unit}"),
        ("down", voice_rules.MOVE_NORMAL): (
            f" ก่อนเผชิญแรงเทขายกดราคาลงมาเคลื่อนไหวแถว {last_text} {unit}"),
        ("down", voice_rules.MOVE_STRONG): (
            f" ก่อนร่วงลงอย่างแรงมาเคลื่อนไหวแถว {last_text} {unit}"),
    }.get((move["direction"], move["class"]))
    if continuation is None:
        if move["class"] == voice_rules.MOVE_QUIET:
            # ก8 — เปลี่ยนแปลงเล็กน้อย ใช้ได้ไม่ต้องบอกทิศ
            continuation = (" และแกว่งตัวในกรอบแคบตลอดช่วงการซื้อขายที่ผ่านมา "
                            f"ล่าสุดเคลื่อนไหวแถว {last_text} {unit}")
        else:
            # ไม่มีฐานเทียบ (MOVE_UNKNOWN) — ตัดประโยคทิศทางเงียบตาม spec
            continuation = f" ล่าสุดเคลื่อนไหวแถว {last_text} {unit}"
    sentences = [first + continuation]

    # ประโยคเทียบราคาปิดวันก่อนหน้า — ใช้ percent_magnitude จาก evidence ตรง ๆ
    percent = snapshot.get("percent_magnitude")
    previous_close = snapshot.get("previous_close")
    if percent is not None and previous_close is not None:
        percent_text = voice_rules.format_percent(percent)
        previous_text = voice_rules.format_price(previous_close, kind)
        if move["direction"] == "up":
            word = "เพิ่มขึ้น"
        elif move["direction"] == "down":
            word = "ลดลง"
        else:
            word = "ทรงตัวเท่ากับ"
        if move["direction"] in ("up", "down"):
            sentences.append(
                f"โดยราคา{word}ราว {percent_text}% จากราคาปิดวันก่อนหน้าที่ {previous_text}"
            )
        else:
            sentences.append(f"โดยราคาทรงตัวใกล้ราคาปิดวันก่อนหน้าที่ {previous_text}")

    # กรอบระหว่างวันจากค่า high/low ของแท่งล่าสุด (มีใน evidence เสมอ)
    high_text = voice_rules.format_price(snapshot["high"], kind)
    low_text = voice_rules.format_price(snapshot["low"], kind)
    if high_text != low_text:
        sentences.append(
            f"ระหว่างวันราคาขึ้นไปทำจุดสูงสุดที่ {high_text} "
            f"และย่อลงต่ำสุดที่ {low_text} {unit}"
        )
    return " ".join(sentences)


# ---------------------------------------------------------------- ช่วง ③ ข้อมูลเทคนิค
def _buy_sell_phrase(price, sma20, sma50, rsi14) -> str | None:
    """วลีสรุปกำลังซื้อ-ขายจากคลังหมวด จ. — เลือกตามเงื่อนไข evidence เท่านั้น"""
    references = [value for value in (sma20, sma50) if value is not None]
    below_all = bool(references) and all(price < value for value in references)
    above_all = bool(references) and all(price > value for value in references)
    rsi_low = rsi14 is not None and rsi14 < 50
    rsi_high = rsi14 is not None and rsi14 >= 50

    if below_all and rsi_low:
        return "แปลว่าแรงซื้อยังอ่อนแรง"                # จ3
    if rsi_low or (references and not above_all and not rsi_high):
        return "สะท้อนว่าแรงขายยังได้เปรียบ"             # จ1
    if above_all and rsi_high:
        return "สะท้อนว่าแรงซื้อยังได้เปรียบ"            # กระจกของ จ1 (ตัวอย่างใน spec ช่วง ③)
    if above_all or rsi_high:
        return "สะท้อนว่าแรงซื้อยังพอได้เปรียบ"
    return None  # ไม่มีทั้งเส้นค่าเฉลี่ยและ RSI — ตัดจังหวะแปลความเงียบ


def _technical_paragraph(data: dict) -> str:
    snapshot = data["snapshot"]
    technical = data["technical"]
    block = data["sr_block"]
    kind = data["instrument"]["instrument_type"]
    price = snapshot["price"]
    sma20, sma50 = technical["sma20"], technical["sma50"]
    rsi14 = technical["rsi14"]

    # จังหวะ 1 — เหตุ: ข้อเท็จจริงจากกราฟ (ตัดเงียบเมื่อ evidence ไม่มี)
    # แนวโน้มรวมระบุได้เฉพาะเมื่อราคาอยู่ข้างเดียวกันของเส้นค่าเฉลี่ยทั้งสองเส้น
    # (ง3 — Bullish/Bearish + วงเล็บไทยกำกับครั้งแรกในช่วง ③)
    trend_label = None
    facts: list[str] = []
    if sma20 is not None and sma50 is not None:
        sma20_text = voice_rules.format_price(sma20, kind)
        sma50_text = voice_rules.format_price(sma50, kind)
        if price > sma20 and price > sma50:
            trend_label = "Bullish (ขาขึ้น)"
            facts.append(f"ราคายังยืนเหนือเส้นค่าเฉลี่ย 20 วัน ที่ {sma20_text} "
                         f"และเส้นค่าเฉลี่ย 50 วัน ที่ {sma50_text}")
        elif price < sma20 and price < sma50:
            trend_label = "Bearish (ขาลง)"
            facts.append(f"ราคายังเคลื่อนไหวต่ำกว่าเส้นค่าเฉลี่ย 20 วัน ที่ {sma20_text} "
                         f"และเส้นค่าเฉลี่ย 50 วัน ที่ {sma50_text}")
        else:
            facts.append(f"ราคาแกว่งอยู่ระหว่างเส้นค่าเฉลี่ย 20 วัน ที่ {sma20_text} "
                         f"กับเส้นค่าเฉลี่ย 50 วัน ที่ {sma50_text}")
    elif sma20 is not None:
        sma20_text = voice_rules.format_price(sma20, kind)
        side = "เหนือ" if price > sma20 else "ต่ำกว่า"
        facts.append(f"ราคาเคลื่อนไหว{side}เส้นค่าเฉลี่ย 20 วัน ที่ {sma20_text}")
    if rsi14 is not None:
        rsi_text = voice_rules.format_int(rsi14)
        zone = "เหนือระดับกลาง" if rsi14 > 50 else ("ใต้ระดับกลาง" if rsi14 < 50 else "บริเวณระดับกลาง")
        facts.append(f"ขณะที่ค่าโมเมนตัม RSI อยู่ที่ {rsi_text} ซึ่งอยู่{zone}ของเครื่องมือ")

    pieces: list[str] = []
    if facts:
        lead_in = "จากโครงสร้างกราฟรายวัน "
        if trend_label:
            lead_in += f"ภาพรวมยังเป็น {trend_label} โดย"
        pieces.append(lead_in + " ".join(facts))

    # จังหวะ 2 — ผล: วลีสรุปกำลังซื้อขายตามเงื่อนไขหมวด จ.
    phrase = _buy_sell_phrase(price, sma20, sma50, rsi14)
    bullish = phrase is not None and "แรงซื้อยัง" in phrase and "อ่อนแรง" not in phrase
    if phrase:
        pieces.append(phrase)

    # จังหวะ 3 — เงื่อนไขสองทาง (ขึ้นและลง) ด้วยเลขชุดเดียวกับบล็อกช่วง ④
    resistances = block["resistances"]
    supports = block["supports"]
    up_clause = down_clause = None
    next_targets = [item["text"] for item in resistances[1:3]]
    next_floors = [item["text"] for item in supports[1:3]]
    # "ตามลำดับ" มีความหมายเมื่อไล่หลายระดับเท่านั้น — ค่าเดียวไม่ต้องใส่
    target_text = " และ ".join(next_targets) + (" ตามลำดับ" if len(next_targets) > 1 else "")
    floor_text = " และ ".join(next_floors) + (" ตามลำดับ" if len(next_floors) > 1 else "")
    if resistances:
        if bullish:
            up_clause = (f"หากราคาทะลุขึ้นยืนเหนือ {resistances[0]['text']} ได้ชัดเจน "
                         + (f"จะเปิดโอกาสเข้าทดสอบแนวต้านถัดไปที่ {target_text}" if next_targets
                            else "ภาพการฟื้นตัวจะแข็งแรงขึ้น"))
        else:
            up_clause = (f"หากราคาสามารถกลับขึ้นไปยืนเหนือ {resistances[0]['text']} ได้อีกครั้ง "
                         "จะช่วยลดแรงกดดันฝั่งขาย"
                         + (f" และเปิดทางฟื้นตัวไปหาแนวต้านถัดไปที่ {target_text}"
                            if next_targets else ""))
    if supports:
        if bullish:
            down_clause = (f"หากราคายืนเหนือแนวรับ {supports[0]['text']} ไม่ได้ "
                           "ภาพบวกระยะสั้นจะเริ่มเสียโมเมนตัม"
                           + (f" และเปิดโอกาสย่อลงหาแนวรับถัดไปที่ {floor_text}"
                              if next_floors else ""))
        else:
            down_clause = (f"หากราคายืนเหนือแนวรับ {supports[0]['text']} ไม่ได้ "
                           "แรงขายจะกลับเข้ามาคุมเกม"
                           + (f" โดยมีแนวรับถัดไปที่ {floor_text}" if next_floors else ""))
    if up_clause and down_clause:
        ordered = (up_clause, down_clause) if bullish else (down_clause, up_clause)
        pieces.append(f"{ordered[0]} ในทางกลับกัน {ordered[1]}")
    elif up_clause or down_clause:
        pieces.append(up_clause or down_clause)

    return " ".join(pieces)


# ---------------------------------------------------------------- ช่วง ④ บล็อกท้าย
def _sr_block_lines(data: dict) -> list[str]:
    instrument = data["instrument"]
    block = data["sr_block"]
    unit = instrument["unit"]
    lines = [f"{instrument['block_label']}:"]
    if block["supports"]:
        values = " / ".join(item["text"] for item in block["supports"])
        lines.append(f"แนวรับ {values} {unit}")
    if block["resistances"]:
        values = " / ".join(item["text"] for item in block["resistances"])
        lines.append(f"แนวต้าน {values} {unit}")
    lines.append(f"หมายเหตุ {block['note']}")
    lines.append(voice_rules.DISCLAIMER)
    return lines


# ---------------------------------------------------------------- เรนเดอร์ Markdown
def render_markdown(data: dict) -> str:
    if data["drivers"]["verified_news"]:
        # ระยะ 3: ย่อหน้าปัจจัยจับตาแทรกระหว่างช่วง ① กับ ③ — ยังไม่เปิดใช้ในระยะ 1
        raise NotImplementedError("ช่วง ② (ข่าว) เป็นงานระยะ 3 — ต้องออกแบบผ่าน spec ก่อน")
    instrument = data["instrument"]
    symbol = instrument["symbol"]

    # กราฟเป็นจุดขายของ P002 — ต้องอยู่ทุกฉบับ (คำตัดสิน CC ข้อ 4)
    chart_name = Path(data["visuals"]["static_path"]).name
    plotted = data["visuals"].get("plotted_indicators") or []
    alt_text = f"กราฟแท่งเทียนรายวันของ {symbol} พร้อมแนวรับ แนวต้าน และเส้นค่าเฉลี่ยสำคัญ"
    if plotted:
        ma_days = " และ ".join(f"{name[3:]} วัน" for name in plotted if name.startswith("sma"))
        caption = f"กราฟรายวันของ {symbol} พร้อมแนวรับ แนวต้าน และเส้นค่าเฉลี่ย {ma_days}"
    else:
        caption = f"กราฟรายวันของ {symbol} พร้อมแนวรับและแนวต้านสำคัญ"

    lines = [
        "---",
        f"title: '{data['headline']}'",
        f"symbol: {symbol}",
        f"instrument_type: {instrument['instrument_type']}",
        f"cutoff_at: '{instrument['cutoff_at']}'",
        f"timezone: {instrument['public_timezone']}",
        "---",
        "",
        f"# {data['headline']}",
        "",
        f"*ข้อมูล ณ {instrument['cutoff_public']}*",
        "",
        _opening_paragraph(data),
        "",
        # ช่วง ② ปัจจัยจับตา: ระยะ 1 ไม่มีข่าวที่ยืนยันได้ = ตัดทั้งช่วงแบบเงียบ
        # (ห้ามหัวข้อว่าง ห้ามประโยคแก้ตัว) — เมื่อมีข่าวจริงในระยะ 3 ค่อยเติมย่อหน้า
        voice_rules.TECHNICAL_HEADING,
        "",
        _technical_paragraph(data),
        "",
        *_sr_block_lines(data),
        "",
        f"![{alt_text}]({chart_name})",
        "",
        f"*{caption}*",
        "",
    ]
    return "\n".join(lines)


def prose_only(text: str) -> str:
    """ตัด frontmatter หัวข้อ และ markup ภาพออก เหลือเฉพาะเนื้อความที่คนอ่านเป็นประโยค"""
    body = text.split("---", 2)[2] if text.startswith("---") else text
    keep = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("|", "#", "![", "*ข้อมูล ณ", "*กราฟ")):
            continue
        keep.append(stripped.lstrip("-* ").strip())
    return " ".join(keep)
