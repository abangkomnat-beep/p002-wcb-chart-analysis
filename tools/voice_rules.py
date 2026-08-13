"""กติกากลางตาม WCB Voice Spec v1 — แหล่งเดียวที่ตัวประกอบบทความและด่านตรวจใช้ร่วมกัน

อ้างอิง: 03-RR/Output/2026-08-03_WCB-Voice-Spec-v1.md (ฉบับที่ CC ล็อกเมื่อ 2026-08-03)
ครอบคลุม 5 เรื่อง:
1. กติกาปัดตัวเลขต่อชนิดสินทรัพย์ (spec ข้อ 4 — round half up ครั้งเดียวจากค่าดิบ)
2. denylist คำ robot 20 รายการ (spec ข้อ 3)
3. เกณฑ์เลือกกริยาตามขนาดการเปลี่ยนแปลง (spec ตาราง 2.6)
4. ตัวนับคำแบบ deterministic + เพดานความยาว (spec ข้อ 5 · v1.1 ปรับเป็น 350-560 คำ)
5. ตัวตรวจข้อความซ้ำ corpus (spec หลักการข้อ 2 — ห้ามตรงเกิน 10 คำติด)
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools.chart_renderer import BANGKOK, THAI_MONTHS, indicator_public_name  # noqa: E402


SPEC_REFERENCE = "WCB Voice Spec v1.1 (2026-08-04)"

# ---------------------------------------------------------------- ข้อความตายตัว
TECHNICAL_HEADING = "ข้อมูลเทคนิค (Technical Analysis)"

# v1.1 (คำสั่งผู้ใช้ 2026-08-04): หมายเหตุและ disclaimer **ไม่อยู่ในบทความ public แล้ว**
# บทความจบที่บรรทัดแนวต้าน แล้วต่อด้วยกราฟ + caption ทันที
# ข้อความสามชุดนี้ยังเก็บไว้ฝั่ง internal (qa-report.json) เพื่อ audit ว่าเงื่อนไขของวันคืออะไร
DISCLAIMER = (
    "บทวิเคราะห์นี้จัดทำเพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน "
    "ผู้ลงทุนควรกำหนดจุดตัดขาดทุนให้เหมาะกับตนเอง"
)
NOTE_FORMING = "ราคาอ้างอิงระหว่างวัน อาจเปลี่ยนแปลงได้จนกว่าตลาดจะปิดรอบวัน"
NOTE_CLOSED = "ราคาอ้างอิงจากแท่งรายวันล่าสุดที่ปิดรอบแล้ว"

# ---------------------------------------------------------------- 1. กติกาปัดตัวเลข
# spec ข้อ 4: ปัดครั้งเดียวจากค่าดิบด้วย round half up — ค่าเดียวกันทุกตำแหน่งในบทความ
# quantum >= 1 หมายถึงปัดเป็นจำนวนเต็มขั้นละ quantum (เช่น BTC ปัดเป็นหลักร้อย)
PRICE_RULES = {
    "forex_spot": {"quantum": Decimal("0.0001"), "comma": False},
    "crypto_spot": {"quantum": Decimal("100"), "comma": True},
    "spot_metal": {"quantum": Decimal("1"), "comma": True},
    # หุ้นรายตัวเสนอราคาเป็นเซนต์ และตัวเลขอยู่หลักสิบ-หลักร้อย จึงไม่ต้องมี comma
    "stock_cfd": {"quantum": Decimal("0.01"), "comma": False},
}
DEFAULT_PRICE_RULE = {"quantum": Decimal("0.01"), "comma": False}
PERCENT_QUANTUM = Decimal("0.01")


def _price_rule(instrument_type: str | None) -> dict:
    return PRICE_RULES.get(instrument_type or "", DEFAULT_PRICE_RULE)


def round_price(value: float, instrument_type: str | None) -> Decimal:
    """ปัดราคาครั้งเดียวจากค่าดิบตามกติกาของสินทรัพย์ (round half up)"""
    rule = _price_rule(instrument_type)
    raw = Decimal(str(value))
    quantum = rule["quantum"]
    if quantum >= 1:
        steps = (raw / quantum).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return steps * quantum
    return raw.quantize(quantum, rounding=ROUND_HALF_UP)


def format_price(value: float, instrument_type: str | None) -> str:
    """ข้อความราคาที่บทความแสดง — ใช้ตัวเดียวกันนี้ทุกตำแหน่ง (หัวเรื่อง/เนื้อ/บล็อก)"""
    rule = _price_rule(instrument_type)
    rounded = round_price(value, instrument_type)
    if rule["quantum"] >= 1:
        return f"{int(rounded):,}" if rule["comma"] else str(int(rounded))
    decimals = -rule["quantum"].as_tuple().exponent
    return f"{rounded:.{decimals}f}"


def format_percent(value: float) -> str:
    """เปอร์เซ็นต์ทศนิยม 2 ตำแหน่งเสมอ (ไม่รวมเครื่องหมาย %)"""
    return f"{Decimal(str(value)).quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP):.2f}"


def format_int(value: float) -> str:
    """จำนวนเต็มแบบ round half up — ใช้กับ RSI"""
    return str(int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)))


def rsi_zone(rsi14: float | None) -> tuple[str, str] | None:
    """คืน (เลขที่แสดง, ฝั่งของโซนกลาง) โดยตัดสินจาก **เลขที่ผู้อ่านเห็น** ไม่ใช่ค่าดิบ

    ฝั่งที่คืนได้: `above` · `below` · `at`

    ค่าดิบ 50.4 แสดงเป็น "50" — ถ้าตัดสินจากค่าดิบจะได้ประโยค "RSI อยู่ที่ 50
    ซึ่งยังอยู่เหนือโซนกลาง" ซึ่งขัดกันเองในสายตาผู้อ่าน เพราะเขาเห็นเลข 50 เป๊ะ
    (เจอจริงในบทความทองคำ 2026-08-04 · ผู้ใช้สั่งแก้)

    **หลักที่ใช้:** ประโยคที่พูดถึงเลขที่พิมพ์ออกไป ต้องตรงกับเลขที่พิมพ์
    ส่วนบทสรุปเชิงตัดสิน (เช่น `_buy_sell_phrase`) ใช้ค่าดิบเต็มความละเอียดได้
    เพราะไม่ได้อ้างถึงตัวเลขนั้นให้ผู้อ่านเห็น
    """
    if rsi14 is None:
        return None
    text = format_int(rsi14)
    shown = int(text)
    if shown > 50:
        return text, "above"
    if shown < 50:
        return text, "below"
    return text, "at"


def price_vs_averages(price: float, ma20: float | None, ma50: float | None) -> str | None:
    """ตำแหน่งราคาเทียบเส้นค่าเฉลี่ยที่มีอยู่ — `above` · `below` · `mixed` · None

    None = ไม่มีเส้นไหนผ่านจำนวนแท่งขั้นต่ำเลย จึงไม่มีอะไรให้เทียบ (ไม่ใช่ "กลาง ๆ")

    เป็นแหล่งเดียวที่ทั้งสามสไตล์ใช้ตัดสินฝั่ง — ก่อนหน้านี้ต่างคนต่างเขียน แล้ว
    ฉบับของณธารสรุปสวนกับย่อหน้าของตัวเองได้ (2026-08-04)
    """
    references = [value for value in (ma20, ma50) if value is not None]
    if not references:
        return None
    if all(price > value for value in references):
        return "above"
    if all(price < value for value in references):
        return "below"
    return "mixed"


def format_ratio(value: float) -> str:
    """อัตราส่วนทศนิยม 2 ตำแหน่ง — ใช้กับผลตอบแทนต่อความเสี่ยงเท่านั้น

    แยกจาก `format_price` เพราะอัตราส่วน **ไม่ใช่ราคา** จึงไม่ควรถูกปัดด้วยกติกา
    ของสินทรัพย์ — อัตราส่วน 1.90 ของคู่เงินจะกลายเป็น "1.90000" ถ้าใช้กติการาคา
    ซึ่งอ่านแล้วเหมือนเลขราคาที่หลุดมา ไม่ใช่จำนวนเท่า
    """
    return f"{Decimal(str(value)).quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP):.2f}"


# ---------------------------------------------------------------- 2. denylist คำ robot
# spec ข้อ 3 — 20 รายการ (ข้อ 19 มีสองรูป จึงมี 21 pattern) ตรวจแบบ substring
# คำละตินตรวจแบบไม่สนตัวพิมพ์ (เก็บเป็นตัวเล็กแล้วเทียบกับบรรทัดที่ lower แล้ว)
VOICE_DENYLIST = (
    "ฉากทัศน์",                 # 1
    "ระดับตัดสินใจ",            # 2
    "เป้าหมายที่ตรวจสอบได้",     # 3
    "จุดที่ถือว่ามุมมองนี้ผิด",   # 4
    "session",                  # 5
    "atr",                      # 6
    "projection",               # 7
    "ปฏิทินการซื้อขาย",          # 8
    "เป็นโซนเดียว",             # 9
    "เวลาตัดข้อมูล",            # 10
    "กำลังก่อตัว",              # 11
    "ผู้ให้ข้อมูล",             # 12
    "pivot",                    # 13
    "swing",                    # 14
    "sma",                      # 15
    "มุมมองรายวัน",             # 16
    "ไม่ใช่คำสั่งซื้อขาย",       # 17
    "หลักฐาน",                  # 18
    "แหล่งที่มา",               # 19 (รูปที่หนึ่ง)
    "ยืนยันแหล่ง",              # 19 (รูปที่สอง)
    "ตรวจสอบได้",               # 20
)


# ---------------------------------------------------------------- คำตระกูล volume
# ใบแจ้งหัวหน้า 2026-08-13 ข้อ 3 + วัด payload จริง: ช่อง `v` มีค่าจริงเฉพาะหุ้น
# (จำนวนหุ้นที่ซื้อขายจากตลาดหลักทรัพย์) · ทอง/ฟอเร็กซ์/น้ำมัน/คริปโตคู่ USD เป็น OTC
# ไม่มีตลาดกลางให้นับ ปลายทางส่ง null ทุกแท่ง ⇒ บทของกลุ่มนั้นเขียนถึง volume ได้
# ก็ต่อเมื่อแต่งขึ้นเอง ซึ่งด่านตัวเลขจับไม่ได้เพราะคำว่า volume ไม่ใช่ตัวเลข
# จึงต้องห้ามที่ระดับคำ — ทุก validator (A–E · เว็บ · F/G · H/I/J) เรียกตัวช่วยตัวเดียวกัน
VOLUME_ALLOWED_INSTRUMENT_TYPES = frozenset({"stock_cfd"})
# คำละตินต้องมีขอบเขตคำ — บทเรียน 'sma' จับกลางคำ 'Smart Money' (`282ffb0`)
_VOLUME_LATIN = re.compile(r"\b(volume|vwap|obv)\b", re.IGNORECASE)
_VOLUME_THAI = ("วอลุ่ม", "วอลลุ่ม", "ปริมาณการซื้อขาย", "ปริมาณซื้อขาย",
                "ปริมาณเทรด", "ปริมาณธุรกรรม")


def volume_term_in(text: str) -> str | None:
    """คำตระกูล volume คำแรกที่พบในข้อความ — ไม่พบคืน None"""
    match = _VOLUME_LATIN.search(text)
    if match:
        return match.group(0).lower()
    for term in _VOLUME_THAI:
        if term in text:
            return term
    return None


# ---------------------------------------------------------------- ป้ายระดับภาษาคน
# spec ข้อ 3 (คำแทนที่ #13 #14 #15): ผู้อ่านเห็นระดับตาม "บทบาท" ไม่ใช่ชื่อเทคนิค
# ชื่อเทคนิคเต็ม (Pivot S3, SMA20, ATR projection) ยังอยู่ครบฝั่ง internal ตามเดิม
_LEVEL_MEMBER_KINDS = (
    ("swing", "swing"),
    ("pdh", "previous_day"), ("pdl", "previous_day"),
    ("pwh", "previous_week"), ("pwl", "previous_week"),
    ("sma", "moving_average"), ("ema", "moving_average"),
    ("atr", "atr_projection"),
    ("pivot", "pivot"),
)
_HISTORY_KINDS = {"swing", "previous_day", "previous_week"}


def _level_kinds(level: dict) -> set[str]:
    """ชนิดที่มาของระดับ — โซนที่รวมหลายระดับดูจากรายชื่อสมาชิก"""
    if level.get("type") != "zone":
        return {level.get("type") or "other"}
    kinds: set[str] = set()
    for member in level.get("members") or []:
        for prefix, kind in _LEVEL_MEMBER_KINDS:
            if member.startswith(prefix):
                kinds.add(kind)
                break
        else:
            kinds.add("other")
    return kinds or {"other"}


def public_level_side(level: dict, reference_price: float) -> str:
    """ฝั่งของระดับเทียบราคาปัจจุบัน — 'support' หรือ 'resistance' เท่านั้น

    ระดับ bias_divider (เช่น Pivot P) ผู้อ่านไม่ต้องรู้จัก — จัดฝั่งตามตำแหน่งจริง
    """
    role = level.get("role")
    if role in ("support", "resistance"):
        return role
    anchor = level.get("value")
    if anchor is None:
        anchor = (float(level["zone_low"]) + float(level["zone_high"])) / 2
    return "support" if float(anchor) < reference_price else "resistance"


def public_level_label(level: dict, reference_price: float) -> str:
    """ป้ายระดับที่ผู้อ่านเห็นบนกราฟและใน article.json ฝั่ง public

    - จุดสูง/ต่ำในอดีต (swing, วันก่อน, สัปดาห์ก่อน) → จุดสูงสุดเดิม / จุดต่ำสุดเดิม
    - เส้นค่าเฉลี่ยเดี่ยว → เส้นค่าเฉลี่ย N วัน · กรอบจากช่วงแกว่ง → กรอบแกว่งรายวัน
    - ที่เหลือเรียกตามบทบาท: แนวรับ / แนวต้าน
    """
    side = public_level_side(level, reference_price)
    kinds = _level_kinds(level)
    if kinds <= _HISTORY_KINDS:
        return "จุดต่ำสุดเดิม" if side == "support" else "จุดสูงสุดเดิม"
    if kinds == {"moving_average"} and level.get("type") != "zone":
        return indicator_public_name(level.get("id", ""))
    if kinds == {"atr_projection"}:
        return "กรอบแกว่งรายวัน"
    return "แนวรับ" if side == "support" else "แนวต้าน"


# ---------------------------------------------------------------- 3. เกณฑ์กริยา "แรง"
# spec ตาราง 2.6 — |change%| กำหนดกลุ่มกริยาที่อนุญาต ทิศต้องตรงเครื่องหมาย change เสมอ
#
# **ทุกชนิดสินทรัพย์ต้องมีเกณฑ์ของตัวเองในตารางนี้** ห้ามปล่อยให้ตกไปใช้ค่าเริ่มต้น
# เพราะค่าเริ่มต้นคือเกณฑ์ของ forex ซึ่งแคบที่สุดในบรรดาสินทรัพย์ที่เรามี
# ทุกคู่ตัวเลขด้านล่างวัดจากข้อมูลจริง 198 วันทำการ (2026-08-04) ไม่ได้ตั้งจากสามัญสำนึก
# วิธีเลือก: หาคู่ที่ทำให้สัดส่วนวัน "เงียบ/ปกติ/แรง" ใกล้เคียงกันข้ามสินทรัพย์
#
#   ชนิด          ค่ากลาง |change%|   เกณฑ์      เงียบ    แรง
#   forex_spot          0.21%       0.15/0.75   39.9%    5.6%
#   spot_metal          0.97%       0.5 /2.5    29.8%   12.6%
#   crypto_spot         1.32%       1.0 /3.0    37.9%   15.2%
#   stock_cfd           1.54%       1.0 /3.0    33.3%   19.7%
#   commodity_cfd       2.03%       1.25/4.0    34.8%   21.2%   (WTI · วัด 2026-08-11)
#
# spot_metal เคยตกไปใช้เกณฑ์ forex จนคำว่า "แรง" ยิง 59.1% ของวัน — ผู้อ่านเห็น
# "ร่วงลงอย่างแรง" เกือบ 3 ใน 5 วัน คำเตือนจึงหมดน้ำหนัก แก้ตามมติผู้ใช้ 2026-08-04
#
# commodity_cfd วัดจากแท่งจริงของ WTI 198 วันทำการล่าสุด (วิธีเดียวกับตารางบน):
# น้ำมันแกว่งแรงกว่าทุกตัวที่มี — ใช้เกณฑ์ทอง (0.5/2.5) คำว่า "แรง" จะยิง 39.4% ของวัน
MOVE_THRESHOLDS = {
    "forex_spot": (0.15, 0.75),
    "spot_metal": (0.5, 2.5),
    "crypto_spot": (1.0, 3.0),
    "stock_cfd": (1.0, 3.0),
    "commodity_cfd": (1.25, 4.0),
}
DEFAULT_MOVE_THRESHOLDS = (0.15, 0.75)

MOVE_QUIET = "quiet"      # แกว่งตัวในกรอบ / ทรงตัว
MOVE_NORMAL = "normal"    # ขึ้น/ลงปกติ
MOVE_STRONG = "strong"    # ร่วงลงอย่างแรง / ทะยานพุ่ง
MOVE_UNKNOWN = "unknown"  # ไม่มีฐานเทียบ (ไม่มีราคาปิดก่อนหน้า) — ตัดประโยคทิศทางเงียบ


def classify_move(percent_magnitude: float | None, instrument_type: str | None) -> str:
    if percent_magnitude is None:
        return MOVE_UNKNOWN
    low, high = MOVE_THRESHOLDS.get(instrument_type or "", DEFAULT_MOVE_THRESHOLDS)
    if percent_magnitude < low:
        return MOVE_QUIET
    if percent_magnitude > high:
        return MOVE_STRONG
    return MOVE_NORMAL


# ---------------------------------------------------------------- 4. ตัวนับคำ + เพดาน
# PyThaiNLP ไม่มีในเครื่องและห้ามเพิ่ม dependency — ใช้ตัวนับ deterministic นิยามเดียว:
#   - ตัด frontmatter และบรรทัด markup ภาพ (ขึ้นต้น ![) ออก
#   - คำละติน 1 token = 1 คำ · ตัวเลข 1 ก้อน (รวม , . : %) = 1 คำ
#   - อักษรไทยประมาณจากความยาวอักขระ: 4.5 อักขระ = 1 คำ (ปัดครึ่งขึ้น ต่ำสุด 1)
# ค่า 4.5 คือค่าเฉลี่ยความยาวคำไทยที่สอบเทียบกับ reference corpus (สเกล ~250-450 คำต่อชิ้น)
# นิยามนี้ถูกล็อกด้วยเทส (tests/test_voice_rules.py) — เปลี่ยนสูตรคือเปลี่ยนมาตรฐาน
#
# เพดาน v1.1 (คำสั่งผู้ใช้ 2026-08-04 "ต้องขยายความเนื้อหาให้มากกว่านี้"): 350-560 คำ
# ต่ำกว่า 350 = fail เพราะผู้ใช้ต้องการเนื้อหามากกว่าฉบับ v1 ชัดเจน (ฉบับ v1 อยู่ราว 259 คำ)
# เพดานบน 560 กันบทความบวมเกินสเกล corpus (ชิ้นยาวสุดของ corpus อยู่ราว 470 คำ)
THAI_CHARS_PER_WORD = 4.5
WORD_MIN = 350
WORD_MAX = 560

_THAI_RUN = re.compile(r"[฀-๿]+")
_LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z0-9']*")
_NUMBER_RUN = re.compile(r"\d[\d,.:%]*")


def count_public_words(text: str) -> int:
    body = text.split("---", 2)[2] if text.startswith("---") else text
    total = 0
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("!["):
            continue
        total += len(_LATIN_RUN.findall(stripped))
        total += len(_NUMBER_RUN.findall(stripped))
        for run in _THAI_RUN.findall(stripped):
            total += max(1, int(len(run) / THAI_CHARS_PER_WORD + 0.5))
    return total


# ---------------------------------------------------------------- 5. กันคัดลอก corpus
# spec หลักการข้อ 2: ห้ามตรงกับ corpus ต่อเนื่องเกิน 10 คำ — ไม่มีตัวตัดคำไทยในเครื่อง
# จึงใช้ตัวแทนเชิงอักขระ: 10 คำ x 4.5 อักขระ/คำ = 45 อักขระต่อเนื่อง (หลังยุบช่องว่าง)
COPY_SHINGLE_CHARS = 45


def _normalize_for_overlap(text: str) -> str:
    # หัวข้อ "ข้อมูลเทคนิค (Technical Analysis)" เป็นข้อความบังคับตาม spec — ยกเว้นจากการเทียบ
    return re.sub(r"\s+", " ", text.replace(TECHNICAL_HEADING, " "))


def find_corpus_overlap(article_text: str, corpus_text: str,
                        min_chars: int = COPY_SHINGLE_CHARS) -> str | None:
    """คืนช่วงข้อความแรกที่ยาว >= min_chars และตรงกับ corpus — None คือสะอาด"""
    article = _normalize_for_overlap(article_text)
    corpus = _normalize_for_overlap(corpus_text)
    if len(corpus) < min_chars or len(article) < min_chars:
        return None
    shingles = {corpus[index:index + min_chars]
                for index in range(len(corpus) - min_chars + 1)}
    for index in range(len(article) - min_chars + 1):
        window = article[index:index + min_chars]
        if window in shingles:
            return window
    return None


# ---------------------------------------------------------------- วันเวลาแบบไทย
def _to_bangkok(moment: str | datetime) -> datetime | None:
    if isinstance(moment, str):
        try:
            parsed = datetime.fromisoformat(moment.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        parsed = moment
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(BANGKOK)


def thai_date_text(moment: str | datetime) -> str:
    """เช่น '3 ส.ค. 2026' — ใช้ทั้งบรรทัดเวลาและสูตรเปิดเรื่อง 'วันนี้ ( ... )'"""
    local = _to_bangkok(moment)
    if local is None:
        return str(moment)
    return f"{local.day} {THAI_MONTHS[local.month - 1]} {local.year}"


def thai_day_key(moment: str | datetime) -> str | None:
    """วันแบบ DD-MMYYYY ตามเวลาไทย เช่น '04-082026' — ใช้ตั้งชื่อโฟลเดอร์รายวัน

    ต้องยึดเวลาไทยไม่ใช่ UTC เพราะผู้ใช้อ่านวันจากปฏิทินของตัวเอง
    หลังสองทุ่มไทยเป็นต้นไป สองเขตเวลานี้จะคนละวันกันแล้ว
    """
    local = _to_bangkok(moment)
    if local is None:
        return None
    return f"{local.day:02d}-{local.month:02d}{local.year}"


def thai_time_text(moment: str | datetime) -> str:
    """เช่น '17:09'"""
    local = _to_bangkok(moment)
    if local is None:
        return str(moment)
    return f"{local.hour:02d}:{local.minute:02d}"


# ---------------------------------------------------------------- ตัวช่วยด่านตรวจตัวเลข
# ตัวเลขเชิงโครงสร้างที่ไม่ใช่ข้อมูลตลาด — ลอกออกจากบรรทัดก่อนตรวจ (แทนด้วยช่องว่าง
# เพื่อรักษาตำแหน่งอักขระ): เวลา HH:MM · วันที่ไทย 'D เดือนย่อ ปี' · จำนวนวัน เช่น
# 'เส้นค่าเฉลี่ย 20 วัน' 'ปิดลบ 3 วันทำการ' — ตรงตาม spec ข้อ 4 ที่ระบุว่าจำนวนวันเป็นเลข
# ที่ "ดึงจากฟิลด์ evidence ตรง ๆ ไม่ผ่านการปัด" · v1.1 ผูกจำนวนวันทุกตัวกับฟิลด์ใน
# article.json/technical.evidence.json (context.streak.days, context.ranges.*.window,
# context.volatility.window) และล็อกด้วยเทสว่าเลขในบทความ = ค่าในฟิลด์นั้นจริง
_MONTH_ALTERNATION = "|".join(re.escape(month) for month in THAI_MONTHS)
NUMBER_SKIP_PATTERNS = (
    re.compile(r"\d{1,2}:\d{2}"),
    re.compile(rf"\d{{1,2}}\s*(?:{_MONTH_ALTERNATION})\s*\d{{4}}"),
    re.compile(r"\d+\s*วัน"),
    # เลขลำดับหัวข้อของสไตล์ที่มีหัวข้อย่อย เช่น "## 2. โครงสร้างกราฟ" — เป็นเลขนับหัวข้อ
    # ไม่ใช่ข้อมูลตลาด · ผูกกับต้นบรรทัดที่เป็น heading เท่านั้น จึงไปโดนเลขในเนื้อไม่ได้
    re.compile(r"^\s*#{1,6}\s*\d+\."),
)


def strip_structural_numbers(line: str) -> str:
    for pattern in NUMBER_SKIP_PATTERNS:
        line = pattern.sub(lambda match: " " * len(match.group(0)), line)
    return line
