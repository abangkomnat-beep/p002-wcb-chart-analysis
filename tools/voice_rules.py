"""กติกากลางตาม WCB Voice Spec v1 — แหล่งเดียวที่ตัวประกอบบทความและด่านตรวจใช้ร่วมกัน

อ้างอิง: 03-RR/Output/2026-08-03_WCB-Voice-Spec-v1.md (ฉบับที่ CC ล็อกเมื่อ 2026-08-03)
ครอบคลุม 5 เรื่อง:
1. กติกาปัดตัวเลขต่อชนิดสินทรัพย์ (spec ข้อ 4 — round half up ครั้งเดียวจากค่าดิบ)
2. denylist คำ robot 20 รายการ (spec ข้อ 3)
3. เกณฑ์เลือกกริยาตามขนาดการเปลี่ยนแปลง (spec ตาราง 2.6)
4. ตัวนับคำแบบ deterministic + เพดานความยาว (spec ข้อ 5)
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


SPEC_REFERENCE = "WCB Voice Spec v1 (2026-08-03)"

# ---------------------------------------------------------------- ข้อความตายตัว
TECHNICAL_HEADING = "ข้อมูลเทคนิค (Technical Analysis)"
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
# สินทรัพย์ที่ไม่อยู่ในตาราง (เช่น spot_metal ที่ยังเป็นของสำรองอนาคต) ใช้เกณฑ์ forex
MOVE_THRESHOLDS = {"crypto_spot": (1.0, 3.0)}
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
# ค่า 4.5 คือค่าเฉลี่ยความยาวคำไทยที่ใช้เทียบเพดาน 250-450 คำจริงของ spec ข้อ 5
# นิยามนี้ถูกล็อกด้วยเทส (tests/test_voice_rules.py) — เปลี่ยนสูตรคือเปลี่ยนมาตรฐาน
THAI_CHARS_PER_WORD = 4.5
WORD_MIN = 250
WORD_MAX = 450

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


def thai_time_text(moment: str | datetime) -> str:
    """เช่น '17:09'"""
    local = _to_bangkok(moment)
    if local is None:
        return str(moment)
    return f"{local.hour:02d}:{local.minute:02d}"


# ---------------------------------------------------------------- ตัวช่วยด่านตรวจตัวเลข
# ตัวเลขเชิงโครงสร้างที่ไม่ใช่ข้อมูลตลาด — ลอกออกจากบรรทัดก่อนตรวจ (แทนด้วยช่องว่าง
# เพื่อรักษาตำแหน่งอักขระ): เวลา HH:MM · วันที่ไทย 'D เดือนย่อ ปี' · จำนวนวันของเครื่องมือ
# เช่น 'เส้นค่าเฉลี่ย 20 วัน' (ระยะ 1 บทความไม่เล่าจำนวนวันที่เป็นข้อมูลตลาด เช่น 'ปิดลบ 3
# วันติด' — ถ้าจะเล่าในอนาคตต้องถอดกติกานี้แล้วผูกกับ evidence จริง)
_MONTH_ALTERNATION = "|".join(re.escape(month) for month in THAI_MONTHS)
NUMBER_SKIP_PATTERNS = (
    re.compile(r"\d{1,2}:\d{2}"),
    re.compile(rf"\d{{1,2}}\s*(?:{_MONTH_ALTERNATION})\s*\d{{4}}"),
    re.compile(r"\d+\s*วัน"),
)


def strip_structural_numbers(line: str) -> str:
    for pattern in NUMBER_SKIP_PATTERNS:
        line = pattern.sub(lambda match: " " * len(match.group(0)), line)
    return line
