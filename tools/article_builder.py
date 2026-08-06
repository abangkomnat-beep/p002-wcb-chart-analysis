"""ประกอบบทความสาธารณะจากหลักฐาน — ตัวเลขทุกตัวมาจาก evidence pack เท่านั้น

ลำดับที่บังคับ: สร้าง article.json (หลักฐาน) ก่อน แล้วค่อยเรนเดอร์ Markdown จากไฟล์นั้น
ทำแบบนี้ตัวเลขในบทความจะตรงกับหลักฐานโดยโครงสร้าง ไม่ต้องหวังว่าใครจะพิมพ์ตรง

โครงบทความใช้ WCB Voice Spec v1 + ส่วนขยาย v1.1 (คำสั่งผู้ใช้ 2026-08-04) — เล่าเรื่อง 4 ช่วง:
หัวเรื่อง → บรรทัดเวลา → ① ย่อหน้าเปิด (2 ย่อหน้า) → (② ปัจจัยจับตา — ระยะ 1 ไม่มีข่าว
ตัดเงียบ) → ③ ข้อมูลเทคนิค (Technical Analysis) ร้อยแก้ว 2 ย่อหน้า → ④ บล็อกแนวรับ/แนวต้าน
→ กราฟ + caption 1 บรรทัด

ส่วนต่างของ v1.1 (ผู้ใช้อ่านฉบับ v1 แล้วสั่งแก้ 2 เรื่อง):
- **ตัดหมายเหตุและ disclaimer ออกจากบทความ public** — บล็อกช่วง ④ จบที่บรรทัดแนวต้าน
  ข้อความทั้งสองยังถูกบันทึกฝั่ง internal (qa-report.json) เพื่อ audit
- **ขยายเนื้อหาเป็น 350-560 คำ** ด้วยวิธีเดียวที่อนุญาต: เพิ่มข้อมูลลง evidence ก่อน
  (ชั้น `narrative_context` ด้านล่าง) แล้วจึงเล่าจาก evidence นั้น — ห้ามแต่งเรื่อง

กติกาเหล็ก:
- ห้ามคำนวณเลขใหม่ในชั้นเรียบเรียง — ฟังก์ชัน `_..._paragraph` อ่านค่าจาก evidence
  อย่างเดียว ทุกการคำนวณอยู่ในชั้นหลักฐาน (change_summary / narrative_context) ซึ่งผลลัพธ์
  ถูกเขียนลง article.json และ technical.evidence.json ก่อนบทความจะถูกตรวจ
- ทุกตัวเลขปัดครั้งเดียวจากค่าดิบใน evidence (tools/voice_rules.py)
- สิ่งที่ evidence ไม่มี = ตัดประโยคทิ้งเงียบ ๆ ไม่เขียนคำแก้ตัวให้ผู้อ่านเห็น
- ข้อความเชิงระบบทั้งหมดอยู่ฝั่ง internal เท่านั้น
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import chart_renderer, voice_rules  # noqa: E402


CONTRACT = "WCB Daily Output Contract v3.1 (Voice v1)"
SCHEMA_VERSION = "3.2.0"

INSTRUMENT_LABEL = {
    "forex_spot": "อัตราแลกเปลี่ยนตลาดสปอต",
    "crypto_spot": "คริปโทเคอร์เรนซีตลาดสปอต",
    "spot_metal": "โลหะมีค่าตลาดสปอต",
    # ต้องบอกให้ชัดว่าเป็นสัญญาอ้างอิงราคาหุ้น ไม่ใช่ตัวหุ้นที่ซื้อขายบนกระดาน
    # (input gate ของ contract ข้อ instrument_type ห้ามเรียกของอย่างหนึ่งเป็นอีกอย่าง)
    "stock_cfd": "สัญญาอ้างอิงราคาหุ้นรายตัว",
}

# ชื่อเต็มหัวบล็อกแนวรับ/แนวต้าน (spec ช่วง ④ — ผู้อ่านประจำต้องหาเจอที่เดิมทุกวัน)
BLOCK_LABEL = {
    "EUR/USD": "EUR/USD (Euro/US Dollar)",
    "BTC/USD": "BTC/USD (Bitcoin/US Dollar)",
    "XAU/USD": "XAU/USD (Gold Spot)",
    "NVDA": "NVDA (NVIDIA Corporation)",
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


# field ของระดับที่ผู้อ่าน (และหน้าเว็บ) ใช้จริง — ที่เหลือ (source_field,
# calculation_method, members, basis_timestamp) เป็นข้อมูลเทคนิคภายใน อยู่ internal/level-map.json
PUBLIC_LEVEL_FIELDS = ("id", "label", "value", "zone_low", "zone_high", "timeframe", "role")


def public_level_views(zones: list[dict], reference_price: float) -> tuple[list[dict], dict]:
    """สำเนาระดับที่ผ่านตรวจแล้วในภาษาคน — ใช้กับของฝั่ง public ทุกชิ้น (กราฟ + article.json)

    id ภายใน (เช่น zone_pivot_s3_sma20_pivot_s2) มีศัพท์ระบบฝังอยู่ จึงออกรหัสกลาง
    level-XX ให้ฝั่ง public · คืน (views, id_map) โดย id_map คือ id ภายใน → id public
    (ตารางแปลงกลับถูกเก็บใน internal/level-map.json โดย build_daily_package)
    ฟังก์ชันนี้ deterministic — เรียกซ้ำด้วย input เดิมได้ผลเดิมเสมอ
    """
    views: list[dict] = []
    id_map: dict[str, str] = {}
    for level in zones:
        if not level.get("approved_for_publication"):
            continue
        public_id = f"level-{len(views) + 1:02d}"
        id_map[level["id"]] = public_id
        views.append({
            **level,
            "id": public_id,
            "label": voice_rules.public_level_label(level, reference_price),
            "role": voice_rules.public_level_side(level, reference_price),
        })
    return views, id_map


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


# ---------------------------------------------------------------- ชั้นหลักฐานเชิงบริบท (v1.1)
# ค่าทุกตัวในหมวดนี้ถูกคำนวณที่นี่ครั้งเดียว แล้วบันทึกลง article.json (`context`) และ
# technical.evidence.json — ชั้นเรียบเรียงห้ามคำนวณซ้ำ อ่านค่าไปเล่าอย่างเดียว
# ชื่อ field ห้ามมีคำ denylist (session/sma/atr/pivot/swing) เพราะ article.json เป็นไฟล์ public
LOOKBACK_SHORT = 20        # กรอบราคาช่วงสั้นที่บทความเล่า (วันทำการ)
LOOKBACK_LONG = 60         # กรอบราคาช่วงยาว
VOLATILITY_WINDOW = 14     # หน้าต่างค่าเฉลี่ยช่วงแกว่งรายวัน
SLOPE_LOOKBACK = 5         # ใช้เทียบว่าเส้นค่าเฉลี่ยชันขึ้นหรือลง
WIDE_RANGE_RATIO = 1.15    # ช่วงแกว่งวันนี้ / ค่าเฉลี่ย — เกินนี้ถือว่ากว้างกว่าปกติ
NARROW_RANGE_RATIO = 0.85  # ต่ำกว่านี้ถือว่าแคบกว่าปกติ
BAND_EDGE_RATIO = 0.33     # ตำแหน่งในกรอบ: < 0.33 ขอบล่าง · > 0.67 ขอบบน

# เกณฑ์สองตัวนี้ปรับเมื่อ 2026-08-04 จากการวัดข้อมูลจริง 198 วัน × 3 สินทรัพย์
# (บันทึกผลวัดใน 01-CC/Output/2026-08-04_ผลวัดเกณฑ์ตัวเลข-P002.md)
STREAK_MIN_DAYS = 3        # เดิม 2 — 2 วันติดเกิดที่อัตราเดียวกับการโยนเหรียญ จึงไม่มีนัย
SLOPE_FLAT_PERCENT = 0.2   # เดิมไม่มี — เส้นค่าเฉลี่ยขยับน้อยกว่านี้ถือว่าแทบไม่เปลี่ยนทิศ


def _closed_candles(report: dict) -> list[dict]:
    """แท่งที่ใช้เป็นหลักฐานได้ — อยู่ในปฏิทินและปิดรอบแล้ว (ฐานเดียวกับ indicator)"""
    return [candle for candle in report.get("candles") or []
            if candle.get("is_expected_session") and candle.get("candle_state") == "closed"]


def _range_candles(report: dict) -> list[dict]:
    """ฐานแท่งของ "กรอบราคาช่วง N วัน" — แท่งที่ปิดแล้ว **บวกแท่งวันนี้ที่ยังเดินอยู่**

    ต่างจาก `_closed_candles` โดยตั้งใจ และเป็นที่เดียวในไฟล์นี้ที่ต่าง:

    - ค่า indicator (เส้นค่าเฉลี่ย · ช่วงแกว่งเฉลี่ย · Pivot) ต้องนิ่ง จึงนับเฉพาะแท่งที่
      ปิดแล้วเสมอ — เกณฑ์ความเสี่ยงทั้งชุดถูกวัดมาบนฐานนั้น ห้ามขยับ
    - แต่ "จุดสูงสุด/ต่ำสุดของช่วง" เป็นการ**บรรยายราคา** ไม่ใช่ค่าที่มีเกณฑ์ผูกอยู่
      และย่อหน้าเล่าราคาในบทความใช้แท่งวันนี้อยู่แล้ว (จุดสูงสุด-ต่ำสุดระหว่างวัน)

    ถ้าสองที่ใช้ฐานต่างกัน บทความจะขัดกันเองแบบที่ผู้อ่านจับได้ทันที — เจอจริงกับทองคำ
    รอบ 2026-08-05: ย่อหน้าแรกเล่าว่า "ระหว่างวันราคาขึ้นไปทำจุดสูงสุดที่ 4,179" แล้ว
    ย่อหน้าถัดมาบอกว่า "จุดสูงสุดของช่วง 20 วันคือ 4,166 เมื่อ 22 ก.ค." พร้อมสรุปว่า
    ราคายังต่ำกว่าจุดสูงสุดของช่วง ทั้งที่วันนี้ทะลุไปแล้ว 13 ดอลลาร์ — เพราะกรอบ 20 วัน
    ไม่นับแท่งวันนี้ ส่วนย่อหน้าเล่าราคานับ
    """
    candles = _closed_candles(report)
    latest = (report.get("candles") or [None])[-1]
    if latest and latest.get("is_expected_session") and latest.get("candle_state") != "closed":
        candles = candles + [latest]
    return candles


def _side(value: float, reference: float) -> str:
    if value > reference:
        return "above"
    if value < reference:
        return "below"
    return "at"


def close_streak(candles: list[dict]) -> dict:
    """จำนวนวันทำการที่ราคาปิดไปทางเดียวกันติดต่อกัน (นับเฉพาะแท่งที่ปิดรอบแล้ว)

    คืน days=None เมื่อไม่มีสถิติที่เล่าได้ — บทความจะตัดประโยคนั้นเงียบ
    """
    closes = [float(candle["close"]) for candle in candles]
    if len(closes) < 2:
        return {"direction": None, "days": None, "last_date": None}
    direction: str | None = None
    days = 0
    for index in range(len(closes) - 1, 0, -1):
        step = closes[index] - closes[index - 1]
        if step == 0:
            break
        side = "up" if step > 0 else "down"
        if direction is None:
            direction = side
        elif side != direction:
            break
        days += 1
    if not days:
        return {"direction": None, "days": None, "last_date": None}
    return {"direction": direction, "days": days,
            "last_date": candles[-1]["session_date"]}


def range_window(candles: list[dict], window: int, price: float | None) -> dict | None:
    """จุดสูงสุด/ต่ำสุดของช่วง N วันทำการ พร้อมวันที่ และระยะห่างของราคาปัจจุบันเป็น %"""
    if price is None or len(candles) < window:
        return None
    recent = candles[-window:]
    high_candle = max(recent, key=lambda candle: float(candle["high"]))
    low_candle = min(recent, key=lambda candle: float(candle["low"]))
    high, low = float(high_candle["high"]), float(low_candle["low"])
    return {
        "window": window,
        # บอกไว้ในหลักฐานว่ากรอบนี้นับแท่งวันนี้ที่ยังเดินอยู่ด้วยหรือไม่ — ไม่มีตัวนี้
        # คนตรวจย้อนหลังจะแยกไม่ออกว่ากรอบกับย่อหน้าเล่าราคายืนอยู่บนฐานเดียวกันไหม
        "includes_today": recent[-1].get("candle_state") != "closed",
        "high": high,
        "high_date": high_candle["session_date"],
        "low": low,
        "low_date": low_candle["session_date"],
        "price_side_high": _side(price, high),
        "price_side_low": _side(price, low),
        "percent_from_high": abs(price - high) / high * 100 if high else None,
        "percent_from_low": abs(price - low) / low * 100 if low else None,
    }


def _average_line_slope(candles: list[dict], period: int) -> tuple[str | None, str | None]:
    """ทิศของเส้นค่าเฉลี่ยเทียบกับค่าของมันเองเมื่อ SLOPE_LOOKBACK วันทำการก่อน

    คืน (slope, วันที่ที่ใช้เทียบ) — เก็บเป็นทิศ ไม่เก็บค่าเฉลี่ยย้อนหลังเป็นตัวเลข
    เพื่อไม่ให้ evidence มีเลขราคาส่วนเกินที่ด่านตรวจตัวเลขจะยอมรับโดยไม่จำเป็น

    "flat" ต้องมีแถบผ่อนผัน ไม่ใช่เทียบเท่ากันเป๊ะ — ก่อน 2026-08-04 ใช้ `>` กับ `<`
    ตรง ๆ ทำให้เงื่อนไข flat ต้องการค่าทศนิยมตรงกันพอดี ซึ่งแทบไม่เกิดขึ้นเลย
    วัดจริง 546 จุดไม่เจอสักครั้ง = บทความไม่เคยพูดว่า "แทบไม่เปลี่ยนทิศ" แม้เส้นจะนิ่ง
    """
    closes = [float(candle["close"]) for candle in candles]
    if len(closes) < period + SLOPE_LOOKBACK:
        return None, None
    latest = sum(closes[-period:]) / period
    earlier = sum(closes[-period - SLOPE_LOOKBACK:-SLOPE_LOOKBACK]) / period
    if not earlier:
        return None, None
    change_percent = (latest - earlier) / earlier * 100
    if abs(change_percent) < SLOPE_FLAT_PERCENT:
        slope = "flat"
    elif change_percent > 0:
        slope = "up"
    else:
        slope = "down"
    return slope, candles[-1 - SLOPE_LOOKBACK]["session_date"]


def moving_average_context(candles: list[dict], price: float | None,
                           ma20: float | None, ma50: float | None) -> dict:
    """ตำแหน่งราคาเทียบเส้นค่าเฉลี่ย · โครงสร้างสั้น-ยาว · ความชันของแต่ละเส้น"""
    entries: dict[str, dict] = {}
    for name, period, value in (("ma20", 20, ma20), ("ma50", 50, ma50)):
        if value is None or price is None or not value:
            continue
        slope, reference_date = _average_line_slope(candles, period)
        entries[name] = {
            "period": period,
            "price_side": _side(price, value),
            "distance_percent": abs(price - value) / value * 100,
            "slope": slope,
            "slope_lookback": SLOPE_LOOKBACK,
            "slope_reference_date": reference_date,
        }
    structure = None
    if ma20 is not None and ma50 is not None:
        if ma20 > ma50:
            structure = "short_above_long"
        elif ma20 < ma50:
            structure = "short_below_long"
        else:
            structure = "aligned"
    return {"entries": entries, "structure": structure}


def volatility_context(candles: list[dict], latest: dict, price: float | None) -> dict | None:
    """ช่วงแกว่งวันนี้เทียบค่าเฉลี่ยช่วงแกว่ง 14 วันทำการ — กว้างกว่าหรือแคบกว่าปกติ"""
    if price is None or not price or len(candles) < VOLATILITY_WINDOW:
        return None
    spans = [float(candle["high"]) - float(candle["low"])
             for candle in candles[-VOLATILITY_WINDOW:]]
    average = sum(spans) / VOLATILITY_WINDOW
    if average <= 0:
        return None
    today = float(latest["high"]) - float(latest["low"])
    ratio = today / average
    if ratio > WIDE_RANGE_RATIO:
        comparison = "wider"
    elif ratio < NARROW_RANGE_RATIO:
        comparison = "narrower"
    else:
        comparison = "similar"
    return {
        "window": VOLATILITY_WINDOW,
        "today_range": today,
        "average_range": average,
        "today_range_percent": today / price * 100,
        "average_range_percent": average / price * 100,
        "comparison": comparison,
    }


def level_structure(block: dict, price: float | None) -> dict:
    """ระยะจากราคาถึงแนวรับ/แนวต้านแรกเป็น % และตำแหน่งของราคาในกรอบสองระดับนั้น"""
    result = {"support_distance_percent": None, "resistance_distance_percent": None,
              "band_position": None, "band_position_percent": None}
    if price is None or not price:
        return result
    support = block["supports"][0]["raw"] if block.get("supports") else None
    resistance = block["resistances"][0]["raw"] if block.get("resistances") else None
    if support is not None:
        result["support_distance_percent"] = abs(price - support) / price * 100
    if resistance is not None:
        result["resistance_distance_percent"] = abs(resistance - price) / price * 100
    if support is not None and resistance is not None and resistance > support:
        ratio = (price - support) / (resistance - support)
        result["band_position_percent"] = ratio * 100
        if ratio < BAND_EDGE_RATIO:
            result["band_position"] = "lower"
        elif ratio > 1 - BAND_EDGE_RATIO:
            result["band_position"] = "upper"
        else:
            result["band_position"] = "middle"
    return result


def narrative_context(report: dict, *, price: float | None, ma20: float | None,
                      ma50: float | None, block: dict) -> dict:
    """หลักฐานเชิงบริบททั้งชุดที่บทความ v1.1 ใช้ขยายเนื้อหา — deterministic ทั้งก้อน"""
    candles = _closed_candles(report)
    latest = (report.get("candles") or [None])[-1]
    # กรอบราคาใช้ฐานที่รวมแท่งวันนี้ ส่วนที่เหลือใช้แท่งปิดล้วน — เหตุผลอยู่ที่ `_range_candles`
    range_candles = _range_candles(report)
    return {
        "closed_bars_used": len(candles),
        "streak": close_streak(candles),
        "ranges": {
            "short": range_window(range_candles, LOOKBACK_SHORT, price),
            "long": range_window(range_candles, LOOKBACK_LONG, price),
        },
        "moving_average": moving_average_context(candles, price, ma20, ma50),
        "volatility": volatility_context(candles, latest, price) if latest else None,
        "levels": level_structure(block, price),
    }


def internal_note_lines(candle_state: str) -> dict:
    """ข้อความที่ v1.1 ถอดออกจากบทความ public — เก็บฝั่ง internal ไว้ audit เท่านั้น"""
    return {
        "note": (voice_rules.NOTE_FORMING if candle_state == "forming"
                 else voice_rules.NOTE_CLOSED),
        "disclaimer": voice_rules.DISCLAIMER,
        "reason": "คำสั่งผู้ใช้ 2026-08-04 — ไม่ต้องเขียนสองบรรทัดนี้ในบทความสาธารณะ",
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
    rsi14 = published.get("rsi14")

    zones = level_map["zones"]
    block = select_block_levels(zones, price, instrument_type)
    level_views, level_id_map = public_level_views(zones, price)
    # sr_block ฝั่ง public อ้างระดับด้วยรหัสกลาง level-XX (id ภายในมีศัพท์ระบบฝังอยู่)
    block = {
        side: [{**item, "level_id": level_id_map[item["level_id"]]} for item in items]
        for side, items in block.items()
    }

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
            # session_timezone เป็นข้อมูลระบบ (และคำว่า session อยู่ใน denylist)
            # — อยู่ฝั่ง internal (normalized.market.json) ผู้อ่านใช้ public_timezone พอ
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
            # วันของแท่งที่บทความกำลังเล่า — ไม่ใช่วันที่รันสายท่อ สองค่านี้ไม่เท่ากันเสมอไป
            # (หุ้นสหรัฐ: เช้าไทยวันนี้ แท่งล่าสุดยังเป็นรอบซื้อขายของเมื่อวาน)
            # ชื่อ field ฝั่ง public ห้ามใช้คำว่า session (denylist ข้อ 5) จึงเรียก trading_date
            "trading_date": str(latest["session_date"])[:10],
        },
        "move": {"direction": direction, "class": move_class},
        "drivers": {
            "verified_news": verified_news or [],
            "causal_claims_allowed": bool(verified_news),
        },
        # ฝั่ง public ใช้ชื่อกลาง ma20/ma50 (sma/atr เป็นคำ denylist ข้อ 3)
        # ค่า atr14 และรายชื่อเครื่องมือที่ไม่พร้อม เป็นเรื่องระบบ — อยู่ technical.evidence.json
        "technical": {
            "ma20": sma20, "ma50": sma50, "rsi14": rsi14,
            "timeframes_available": ["1d"],
        },
        # ฝั่ง public เอาเฉพาะระดับที่ผ่านการตรวจแล้ว ในภาษาคนและ field ที่ผู้อ่านใช้จริง
        # รายละเอียดเทคนิค (ชื่อเต็ม ที่มา วิธีคำนวณ) อยู่ internal/level-map.json
        "levels": [{key: view.get(key) for key in PUBLIC_LEVEL_FIELDS}
                   for view in level_views],
        # v1.1: บล็อกช่วง ④ จบที่แนวต้าน — ไม่มี note ในของฝั่ง public อีกแล้ว
        # (ข้อความหมายเหตุ/disclaimer ย้ายไป internal/qa-report.json เพื่อ audit)
        "sr_block": dict(block),
        # หลักฐานเชิงบริบทที่ย่อหน้าขยายของ v1.1 ใช้ — คำนวณที่ชั้นนี้ชั้นเดียว
        "context": narrative_context(report, price=price, ma20=sma20, ma50=sma50,
                                     block=block),
        # metadata กราฟเฉพาะส่วนสาธารณะ — พาธในเครื่อง/โค้ดเครื่องมือถูกกรองออก
        "visuals": {key: value for key, value in chart_metadata.items()
                    if key not in chart_renderer.PRIVATE_METADATA_KEYS},
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

    # วันที่ในประโยคแรกต้องเป็นวันของ "แท่งที่กำลังเล่า" ไม่ใช่วันที่รันสายท่อ
    # ตลาดที่เปิดตลอด 24 ชั่วโมง สองค่านี้ตรงกัน แต่หุ้นสหรัฐไม่ตรง — เช้าไทยวันนี้
    # แท่งล่าสุดยังเป็นรอบซื้อขายของเมื่อวาน การเขียน "วันนี้" จึงกลายเป็นคำเท็จทันที
    session_date = snapshot.get("trading_date") or instrument["cutoff_at"]
    date_text = voice_rules.thai_date_text(session_date)
    # เทียบกับวันที่ผู้อ่านเห็นบนบรรทัดเวลา (เวลาไทย) ไม่ใช่วันที่แบบ UTC
    same_day = date_text == voice_rules.thai_date_text(instrument["cutoff_at"])
    open_text = voice_rules.format_price(snapshot["open"], kind)
    last_text = voice_rules.format_price(snapshot["price"], kind)

    # ประโยคแรก: สูตรตายตัวของ spec + กริยาต่อเนื่องจากคลังหมวด ก. ตามตาราง 2.6
    lead = "วันนี้" if same_day else "ในรอบการซื้อขายล่าสุด"
    first = f"{lead} ( {date_text} ) {symbol} เปิดตลาดที่ระดับ {open_text} {unit}"
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
            # ก8 — เปลี่ยนแปลงเล็กน้อย ใช้ได้ไม่ต้องบอกทิศ (คลังคือ "แกว่งตัวในกรอบ"
            # เฉย ๆ — "แคบ" เป็นการตีความเพิ่มที่เลข high/low อาจไม่รองรับ)
            continuation = (" และแกว่งตัวในกรอบตลอดช่วงการซื้อขายที่ผ่านมา "
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


# -------------------------------------------------- ช่วง ① ย่อหน้าสอง: บริบทราคาย้อนหลัง
def _context_paragraph(data: dict) -> str:
    """ย่อหน้าที่สองของช่วง ① (v1.1) — เล่าพฤติกรรมราคาย้อนหลังจาก `context` ล้วน ๆ

    ทุกประโยคมีเงื่อนไขของตัวเอง: evidence ไม่พอ = หายไปเงียบ ๆ ไม่มีคำแก้ตัว
    """
    context = data.get("context") or {}
    instrument = data["instrument"]
    kind = instrument["instrument_type"]
    unit = instrument["unit"]
    sentences: list[str] = []

    streak = context.get("streak") or {}
    days, direction = streak.get("days"), streak.get("direction")
    if days and days >= STREAK_MIN_DAYS and direction in ("up", "down"):
        # ก่อนหน้านี้ราคาปิดไปทางเดียวกันหลายวัน — corpus เล่าแบบเดียวกัน [ชิ้น 3]
        # เกณฑ์ 3 วันไม่ใช่ 2: วัดจริงแล้ว 2 วันติดเกิดราว 30% ของวัน ซึ่งเท่ากับ
        # อัตราที่การโยนเหรียญให้ได้เอง — เล่าไปก็ไม่ได้บอกอะไรผู้อ่าน
        word = "ปิดบวก" if direction == "up" else "ปิดลบ"
        sentences.append(f"ก่อนหน้านี้ราคา{word}ติดต่อกัน {days} วันทำการ")

    ranges = context.get("ranges") or {}
    short = ranges.get("short")
    if short:
        sentences.append(
            f"โดยกรอบการเคลื่อนไหวของช่วง {short['window']} วันทำการล่าสุด "
            f"อยู่ระหว่าง {voice_rules.format_price(short['low'], kind)} ถึง "
            f"{voice_rules.format_price(short['high'], kind)} {unit} "
            f"ซึ่งจุดต่ำสุดเกิดขึ้นเมื่อ {voice_rules.thai_date_text(short['low_date'])} "
            f"และจุดสูงสุดเมื่อ {voice_rules.thai_date_text(short['high_date'])}"
        )
        gaps = []
        if short.get("percent_from_high") is not None and short["price_side_high"] != "at":
            word = "ต่ำกว่า" if short["price_side_high"] == "below" else "สูงกว่า"
            gaps.append(f"{word}จุดสูงสุดของช่วงราว "
                        f"{voice_rules.format_percent(short['percent_from_high'])}%")
        if short.get("percent_from_low") is not None and short["price_side_low"] != "at":
            word = "สูงกว่า" if short["price_side_low"] == "above" else "ต่ำกว่า"
            gaps.append(f"{word}จุดต่ำสุดราว "
                        f"{voice_rules.format_percent(short['percent_from_low'])}%")
        if gaps:
            sentences.append("ทำให้ราคาล่าสุดอยู่" + " และ".join(gaps))

    long_range = ranges.get("long")
    if long_range:
        sentences.append(
            f"หากขยายภาพไปถึง {long_range['window']} วันทำการ "
            f"ราคาเคยขึ้นไปสูงสุดที่ {voice_rules.format_price(long_range['high'], kind)} "
            f"และลงไปต่ำสุดที่ {voice_rules.format_price(long_range['low'], kind)} {unit}"
        )
    return " ".join(sentences)


# ---------------------------------------------------------------- ช่วง ③ ข้อมูลเทคนิค
def _buy_sell_phrase(price, sma20, sma50, rsi14) -> str | None:
    """วลีสรุปกำลังซื้อ-ขายจากคลังหมวด จ. — เลือกตามเงื่อนไข evidence เท่านั้น

    **ตำแหน่งราคาเทียบเส้นค่าเฉลี่ยมาก่อน RSI เสมอ** (แก้ 2026-08-04 ตามคำสั่งผู้ใช้)
    เดิมสาขาท้ายสุดตัดสินจาก RSI ได้ลำพัง ⇒ วันที่ราคาอยู่ใต้ทั้งสองเส้นแต่ RSI แตะ 50
    ย่อหน้าเดียวกันจะเขียนว่า "ภาพรวมยังเป็น Bearish (ขาลง) … จึงสะท้อนว่าแรงซื้อยัง
    พอได้เปรียบ" ซึ่งขัดกันเอง (เจอจริงกับทองคำ: ราคา 4,048.95 ใต้เส้น 20 วันที่
    4,061.28 และเส้น 50 วันที่ 4,174.45 · RSI 50.4)

    **รอบ 2026-08-06 ปิดด้านกระจกที่รอบก่อนแก้ไม่ครบ** — คราวนั้นกันเฉพาะขาที่ราคา
    อยู่ใต้ทุกเส้น ส่วนขาตรงข้ามยังปล่อยให้ `rsi_low` ตัดสินได้ลำพังอยู่ ⇒ วันที่ราคายืน
    เหนือทั้งสองเส้นแต่ RSI ต่ำกว่า 50 ย่อหน้าเดียวกันจะเขียนว่า "ภาพรวมยังเป็น Bullish
    (ขาขึ้น) โดยราคายังยืนเหนือเส้นค่าเฉลี่ย 20 วัน … จึงสะท้อนว่าแรงขายยังได้เปรียบ"
    (เจอจริงกับ GBP/USD 2026-08-06: ราคา 1.3471 เหนือเส้น 20 วันที่ 1.3405 และเส้น
    50 วันที่ 1.3364 · RSI 49) · **กติกาคือฝั่งไหนก็ตาม ตำแหน่งราคาชนะ RSI เสมอ**
    """
    position = voice_rules.price_vs_averages(price, sma20, sma50)
    below_all = position == "below"
    above_all = position == "above"
    rsi_low = rsi14 is not None and rsi14 < 50
    rsi_high = rsi14 is not None and rsi14 >= 50

    if below_all and rsi_low:
        return "แปลว่าแรงซื้อยังอ่อนแรง"                # จ3
    # `not above_all` คือตัวกันด้านกระจก — ราคาเหนือทุกเส้นแล้วห้ามลงเอยที่ฝั่งขาย
    # ไม่ว่า RSI จะอยู่ตรงไหน (เงื่อนไขที่เหลือคงเดิมทุกตัว)
    if not above_all and (rsi_low or (position is not None and not rsi_high)):
        return "สะท้อนว่าแรงขายยังได้เปรียบ"             # จ1
    if above_all and rsi_high:
        return "สะท้อนว่าแรงซื้อยังได้เปรียบ"            # กระจกของ จ1 (ตัวอย่างใน spec ช่วง ③)
    if below_all:
        # ราคาอยู่ใต้ทั้งสองเส้น ⇒ ห้ามสรุปเป็นฝั่งซื้อไม่ว่า RSI จะอยู่ตรงไหน
        return "สะท้อนว่าแรงขายยังพอได้เปรียบ"           # กระจกอ่อนของ จ1
    if above_all or rsi_high:
        return "สะท้อนว่าแรงซื้อยังพอได้เปรียบ"
    return None  # ไม่มีทั้งเส้นค่าเฉลี่ยและ RSI — ตัดจังหวะแปลความเงียบ


def _average_line_detail(context: dict) -> list[str]:
    """จังหวะ 1 ส่วนขยาย v1.1 — ตำแหน่งเทียบเส้นค่าเฉลี่ย โครงสร้างสั้น-ยาว และความชัน"""
    moving = context.get("moving_average") or {}
    entries = moving.get("entries") or {}
    pieces: list[str] = []

    gaps = []
    for name in ("ma20", "ma50"):
        entry = entries.get(name)
        if not entry or entry.get("distance_percent") is None:
            continue
        if entry["price_side"] not in ("above", "below"):
            continue
        word = "สูงกว่า" if entry["price_side"] == "above" else "ต่ำกว่า"
        gaps.append(f"{word}เส้นค่าเฉลี่ย {entry['period']} วัน ราว "
                    f"{voice_rules.format_percent(entry['distance_percent'])}%")
    if gaps:
        pieces.append("ในแง่ระยะห่าง ราคาล่าสุดอยู่" + " และ".join(gaps))

    structure = moving.get("structure")
    if structure in ("short_above_long", "short_below_long"):
        # อ่านการเรียงตัวแบบพรรณนาเท่านั้น — ห้ามสรุปทิศแทนป้าย Bullish/Bearish ข้างต้น
        # (ถ้าสรุปซ้ำ จะขัดกันเองในวันที่ราคายืนเหนือเส้นทั้งสองแต่เส้นสั้นยังตามหลังเส้นยาว)
        side = "เหนือ" if structure == "short_above_long" else "ใต้"
        read = ("สะท้อนการเรียงตัวที่เส้นระยะสั้นนำเส้นระยะยาว" if structure == "short_above_long"
                else "สะท้อนว่าเส้นระยะสั้นยังตามหลังเส้นระยะยาวอยู่")
        pieces.append(f"ขณะที่เส้นค่าเฉลี่ย 20 วัน ยังอยู่{side}เส้นค่าเฉลี่ย 50 วัน {read}")

    short_line = entries.get("ma20") or {}
    slope = short_line.get("slope")
    if slope in ("up", "down", "flat"):
        motion = {"up": "ยังไต่ขึ้น", "down": "ยังชี้ลง",
                  "flat": "แทบไม่เปลี่ยนทิศ"}[slope]
        pieces.append(f"โดยเส้นค่าเฉลี่ย 20 วัน {motion}เมื่อเทียบกับ "
                      f"{short_line['slope_lookback']} วันทำการก่อนหน้า")
    return pieces


def _volatility_sentence(context: dict) -> str | None:
    """จังหวะ 1 ส่วนขยาย v1.1 — ช่วงแกว่งวันนี้เทียบค่าเฉลี่ย 14 วันทำการ"""
    volatility = context.get("volatility")
    if not volatility:
        return None
    verdict = {"wider": "จึงถือว่ากว้างกว่าการเคลื่อนไหวตามปกติ",
               "narrower": "จึงถือว่าแคบกว่าการเคลื่อนไหวตามปกติ",
               "similar": "จึงถือว่าใกล้เคียงกับการเคลื่อนไหวตามปกติ"}[volatility["comparison"]]
    # "รอบล่าสุด" ไม่ใช่ "วันนี้" — แท่งที่วัดอาจเป็นรอบซื้อขายของเมื่อวานได้
    # (หุ้นสหรัฐเวลาเช้าไทย) ประโยคนี้ใช้ร่วมกันทุกสินทรัพย์จึงต้องพูดให้จริงกับทุกกรณี
    return (f"ด้านความผันผวน ช่วงแกว่งระหว่างวันของรอบล่าสุดอยู่ที่ราว "
            f"{voice_rules.format_percent(volatility['today_range_percent'])}% ของราคา "
            f"เทียบกับค่าเฉลี่ย {volatility['window']} วันทำการที่ราว "
            f"{voice_rules.format_percent(volatility['average_range_percent'])}% {verdict}")


def _level_structure_sentence(context: dict) -> str | None:
    """จังหวะ 3 ส่วนขยาย v1.1 — ระยะถึงแนวรับ/แนวต้านแรก และตำแหน่งในกรอบ"""
    levels = context.get("levels") or {}
    gaps = []
    if levels.get("resistance_distance_percent") is not None:
        gaps.append("ห่างจากแนวต้านแรกราว "
                    f"{voice_rules.format_percent(levels['resistance_distance_percent'])}%")
    if levels.get("support_distance_percent") is not None:
        gaps.append("ห่างจากแนวรับแรกราว "
                    f"{voice_rules.format_percent(levels['support_distance_percent'])}%")
    if not gaps:
        return None
    sentence = "ในเชิงโครงสร้างระดับ ราคาปัจจุบัน" + " และ".join(gaps)
    position = {"lower": "ค่อนไปทางขอบล่างของกรอบ", "middle": "บริเวณกลางกรอบ",
                "upper": "ค่อนไปทางขอบบนของกรอบ"}.get(levels.get("band_position"))
    if position:
        sentence += f" ซึ่งนับว่าอยู่{position}"
    return sentence


def _strategy_sentence(data: dict, context: dict, *, bullish: bool) -> str | None:
    """มุมมองเชิงกลยุทธ์แบบมีเงื่อนไข — ผูกกับเงื่อนไข evidence เดียวกับวลีหมวด จ."""
    block = data["sr_block"]
    supports, resistances = block.get("supports"), block.get("resistances")
    # เลี่ยงพูดเลขระดับซ้ำกับประโยคเงื่อนไขที่อยู่ก่อนหน้า — ถ้ามีเส้นค่าเฉลี่ย 20 วัน
    # ให้ยึดเส้นนั้นเป็นหลักแทน (เป็นเงื่อนไขที่อยู่ใน evidence เหมือนกัน)
    short_line = ((context.get("moving_average") or {}).get("entries") or {}).get("ma20")
    expected_side = "above" if bullish else "below"
    if short_line and short_line["price_side"] == expected_side:
        anchor = "เส้นค่าเฉลี่ย 20 วัน "
    elif bullish and supports:
        anchor = f" {supports[0]['text']} "
    elif not bullish and resistances:
        anchor = f" {resistances[0]['text']} "
    else:
        return None
    if bullish:
        sentence = f"ในเชิงกลยุทธ์ ฝั่งซื้อยังเป็นต่อตราบที่ราคายังยืนเหนือ{anchor}ได้"
    else:
        sentence = ("ในเชิงกลยุทธ์ ฝั่งขายยังเป็นต่อตราบที่ราคายังกลับขึ้นไปยืนเหนือ"
                    f"{anchor}ไม่ได้")
    band = (context.get("levels") or {}).get("band_position")
    if band == "middle" or data["move"]["class"] == voice_rules.MOVE_QUIET:
        sentence += " และภาพรวมยังเหมาะกับการซื้อขายในกรอบระยะสั้นมากกว่าการไล่ราคาตามทิศทางเดียว"
    return sentence


def _technical_paragraphs(data: dict) -> list[str]:
    """ช่วง ③ — v1.1 แยกเป็น 2 ย่อหน้า: (1) เหตุ → ผล (2) เงื่อนไขสองทาง → กลยุทธ์"""
    snapshot = data["snapshot"]
    technical = data["technical"]
    block = data["sr_block"]
    context = data.get("context") or {}
    kind = data["instrument"]["instrument_type"]
    price = snapshot["price"]
    sma20, sma50 = technical["ma20"], technical["ma50"]
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
    zone = voice_rules.rsi_zone(rsi14)
    if zone:
        # corpus พูดสั้น "RSI ยังอยู่ต่ำกว่าโซนกลาง" — "ของเครื่องมือ" เป็นภาษาอธิบายระบบ
        # ฝั่งของโซนตัดสินจาก **เลขที่พิมพ์ออกไป** ไม่ใช่ค่าดิบ (แก้ 2026-08-04)
        # ค่าดิบ 50.4 เคยพิมพ์ว่า "RSI อยู่ที่ 50 ซึ่งยังอยู่เหนือโซนกลาง" ซึ่งอ่านแล้วขัดกันเอง
        rsi_text, side = zone
        zone_phrase = {"above": "ยังอยู่เหนือโซนกลาง",
                       "below": "ยังอยู่ต่ำกว่าโซนกลาง",
                       "at": "อยู่บริเวณโซนกลาง"}[side]
        facts.append(f"ขณะที่ค่าโมเมนตัม RSI อยู่ที่ {rsi_text} ซึ่ง{zone_phrase}")

    pieces: list[str] = []
    if facts:
        lead_in = "จากโครงสร้างกราฟรายวัน "
        if trend_label:
            lead_in += f"ภาพรวมยังเป็น {trend_label} โดย"
        pieces.append(lead_in + " ".join(facts))

    # ส่วนขยาย v1.1 ของจังหวะ 1 — ระยะห่างจากเส้นค่าเฉลี่ย โครงสร้าง ความชัน ความผันผวน
    pieces.extend(_average_line_detail(context))
    volatility_sentence = _volatility_sentence(context)
    if volatility_sentence:
        pieces.append(volatility_sentence)

    # จังหวะ 2 — ผล: วลีสรุปกำลังซื้อขายตามเงื่อนไขหมวด จ.
    phrase = _buy_sell_phrase(price, sma20, sma50, rsi14)
    bullish = phrase is not None and "แรงซื้อยัง" in phrase and "อ่อนแรง" not in phrase
    if phrase:
        # v1.1 มีข้อเท็จจริงคั่นก่อนถึงวลีสรุป — ต้องมีคำนำที่บอกว่านี่คือบทสรุปของทั้งย่อหน้า
        # ไม่อย่างนั้นผู้อ่านจะเข้าใจว่าสรุปมาจากประโยคความผันผวนที่อยู่ติดกันเท่านั้น
        pieces.append(f"เมื่อประกอบภาพทั้งหมดเข้าด้วยกัน จึง{phrase}"
                      if len(pieces) > 1 else phrase)

    # ย่อหน้าที่สอง: โครงสร้างระดับ → เงื่อนไขสองทาง → มุมมองเชิงกลยุทธ์
    second: list[str] = []
    level_sentence = _level_structure_sentence(context)
    if level_sentence:
        second.append(level_sentence)

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
            # ค2 ของคลัง: "ทะลุขึ้นเหนือ...ได้อย่างชัดเจน" — ของเดิมอ่านสะดุดจังหวะ
            up_clause = (f"หากราคาทะลุขึ้นเหนือ {resistances[0]['text']} ได้อย่างชัดเจน "
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
        second.append(f"{ordered[0]} ในทางกลับกัน {ordered[1]}")
    elif up_clause or down_clause:
        second.append(up_clause or down_clause)

    strategy = _strategy_sentence(data, context, bullish=bullish)
    if strategy:
        second.append(strategy)

    return [" ".join(part) for part in (pieces, second) if part]


# ---------------------------------------------------------------- ช่วง ④ บล็อกท้าย
def _sr_block_lines(data: dict) -> list[str]:
    """บล็อกท้าย v1.1 — จบที่บรรทัดแนวต้าน ไม่มีหมายเหตุและไม่มี disclaimer

    ผู้ใช้สั่งตัดสองบรรทัดนั้นออก (2026-08-04) เพราะไม่จำเป็นต้องเขียนให้ผู้อ่านเห็น
    ข้อความยังถูกเก็บฝั่ง internal ผ่าน internal_note_lines() เพื่อ audit
    """
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
    return lines


# -------------------------------------------------------------- ช่วง ② ปัจจัยจับตา
def _safe_source_name(name: str) -> str | None:
    """ชื่อสำนักข่าวที่บังเอิญมีคำต้องห้ามอยู่ในตัว ให้ไม่เอ่ยชื่อดีกว่าทำบทความตกด่าน

    เช่นสำนักที่ชื่อมีคำว่า swing หรือ pivot อยู่ — เป็นชื่อเฉพาะก็จริง แต่ validator
    ตรวจแบบ substring และไม่มีทางแยกออก จึงตัดการเอ่ยชื่อทิ้งแทนที่จะไปผ่อนกฎ
    """
    lowered = (name or "").lower()
    if not lowered:
        return None
    if any(term in lowered for term in voice_rules.VOICE_DENYLIST):
        return None
    if any(character.isdigit() for character in lowered):
        # ช่วง ② ห้ามมีตัวเลขเด็ดขาด เพราะตัวเลขทุกตัวในบทความต้องชี้กลับค่าใน evidence
        # ได้ แต่ข่าวไม่ได้อยู่ในชุดตัวเลขนั้น
        return None
    return name.strip()


def _watch_paragraph(data: dict) -> str:
    """ช่วง ② — ย่อหน้าเดียวจากข่าวที่ผ่านชั้นคัดกรองแล้วเท่านั้น

    สูตรประโยคแรกล็อกตาม Voice Spec ข้อ 2 ช่วง ②:
    "สำหรับช่วงนี้ นักลงทุนจับตา{เหตุการณ์} เพื่อหาสัญญาณ{ผลต่อสินทรัพย์}"

    ระยะ 3a เล่าเฉพาะ "ประเด็น" ที่จับคู่กับพจนานุกรมได้ — ไม่แปลพาดหัวข่าวตรงตัว
    และ**ไม่มีตัวเลขคาดการณ์** เพราะยังไม่มีปฏิทินเศรษฐกิจที่ให้ค่าคาดการณ์มาเทียบ
    วงเล็บชี้ทิศ "(บวกต่อ…)" ของ spec จึงยังไม่เปิดใช้ในระยะนี้ ไม่ใช่ลืม
    """
    items = data.get("drivers", {}).get("verified_news") or []
    if not items:
        return ""

    first = items[0]
    sentences = [f"สำหรับช่วงนี้ นักลงทุนจับตา{first['event']} เพื่อหาสัญญาณ{first['signal']}"]
    if len(items) > 1:
        second = items[1]
        sentences.append(
            f"อีกประเด็นที่ตลาดให้น้ำหนักคือ{second['event']} "
            f"ซึ่งโยงกับ{second['signal']}"
        )

    names, seen = [], set()
    for item in items:
        name = _safe_source_name(item.get("source", ""))
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    if names:
        # เอ่ยชื่อสำนักข่าวเพื่อให้ผู้อ่านรู้ว่าประเด็นนี้มาจากไหน ไม่ใช่เราคิดเอง
        joined = names[0] if len(names) == 1 else f"{' '.join(names[:-1])} และ {names[-1]}"
        sentences.append(f"โดยทั้งสองเรื่องปรากฏในรายงานของ {joined} ในรอบวันทำการล่าสุด"
                         if len(items) > 1 else
                         f"โดยประเด็นนี้ปรากฏในรายงานของ {joined} ในรอบวันทำการล่าสุด")
    return " ".join(sentences)


# ---------------------------------------------------------------- เรนเดอร์ Markdown
def _paragraph_lines(paragraph: str) -> list[str]:
    """ย่อหน้า + บรรทัดว่าง — ย่อหน้าที่ evidence ไม่พอจะกลายเป็นค่าว่างแล้วหายไปทั้งบล็อก"""
    return [paragraph, ""] if paragraph else []


def render_markdown(data: dict, *, chart_name: str | None = None) -> str:
    instrument = data["instrument"]
    symbol = instrument["symbol"]

    # กราฟเป็นจุดขายของ P002 — ต้องอยู่ทุกฉบับ (คำตัดสิน CC ข้อ 4)
    # chart_name ส่งเข้ามาได้เมื่อชั้นจัดวางไฟล์เปลี่ยนชื่อไฟล์ภาพให้ตรงกับชื่อไฟล์บทความ
    chart_name = chart_name or Path(data["visuals"]["static_path"]).name
    ma_days = data["visuals"].get("average_line_days") or []
    alt_text = f"กราฟแท่งเทียนรายวันของ {symbol} พร้อมแนวรับ แนวต้าน และเส้นค่าเฉลี่ยสำคัญ"
    if ma_days:
        # เลี่ยง "และ...และ..." ซ้อนสองครั้งในประโยคเดียว — สองเส้นใช้ "20 กับ 50 วัน"
        if len(ma_days) == 1:
            days_text = f"{ma_days[0]} วัน"
        else:
            head = ", ".join(str(days) for days in ma_days[:-1])
            days_text = f"{head} กับ {ma_days[-1]} วัน"
        caption = f"กราฟรายวันของ {symbol} พร้อมแนวรับ แนวต้าน และเส้นค่าเฉลี่ย {days_text}"
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
        # v1.1: ย่อหน้าที่สองของช่วง ① — บริบทราคาย้อนหลังจาก context (ว่าง = ไม่แทรกบรรทัด)
        *_paragraph_lines(_context_paragraph(data)),
        # ช่วง ② ปัจจัยจับตา: มีข่าวที่ผ่านชั้นคัดกรอง = ย่อหน้าเดียว
        # ไม่มีข่าว = ย่อหน้าว่างแล้วหายไปทั้งบล็อก ตัดเงียบตาม spec
        # (ห้ามหัวข้อว่าง ห้ามประโยคแก้ตัว)
        *_paragraph_lines(_watch_paragraph(data)),
        voice_rules.TECHNICAL_HEADING,
        "",
        *[line for paragraph in _technical_paragraphs(data)
          for line in (paragraph, "")],
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
