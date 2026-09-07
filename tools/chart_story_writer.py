"""นักเขียนสไตล์ D — บทวิเคราะห์อ่านโครงสร้างกราฟ + ด่านตรวจของสไตล์นี้เอง

สำนวนตามบทอ้างอิงที่หัวหน้าเลือก (th.investing.com/analysis/article-200458003):
เน้นบรรยาย + ศัพท์เทคนิคสาย SMC/Price Action หนาแน่น (Market Structure, Demand
Zone, Deep Discount, Smart Money, CHoCH, Stop Hunt, BOS, Dynamic Resistance,
Timeframe ย่อย) · จัดเรียงอ่านง่าย: ย่อหน้าสั้น หัวข้อย่อยตัวหนา bullet นำด้วยชื่อโซน

เส้นแบ่งที่ยึดไว้: **ศัพท์กรอบวิเคราะห์ใช้ได้ แต่ตัวเลขต้องมาจาก story เท่านั้น**
คำอย่าง "Liquidity ใต้โซน" เป็นภาษากรอบวิเคราะห์ (ตำรา SMC) ไม่ใช่ค่าที่วัด —
เขียนให้ชัดว่าเป็นการตีความตามแนวคิด ไม่แอบอ้างเป็นข้อมูล

กติกาที่ทำให้ D ต่างจาก A/B/C:
- บทความอ่านจาก story artifact ก้อนเดียวกับที่ตัววาดใช้ — เลขทุกตัวชี้กลับภาพได้
- ด่าน `validate` แบบ fail-closed: เลขนอกทะเบียน story ตัวเดียว = ตกทั้งบท
- ฉากทัศน์ต้องประกาศว่าเป็น "เงื่อนไข ไม่ใช่คำทำนาย" · ต้องมีคำเตือนความเสี่ยง
  ท้ายบท — ด่านบังคับทั้งสองข้อ
  (ข้อ "จุดเข้าซื้อ (SMC POI) ต้องมีเสมอ" ถูกถอด 2026-08-14 ตามคำสั่งผู้ใช้ที่ให้
   ถอดหัวข้อแผนเข้าโซนรับออกจากบท — หัวข้อ 3 เหลือฉากทัศน์สองฝั่งที่มีขั้นตอนของตัวเอง)

สไตล์นี้ไม่อยู่ใน `WCB_WRITERS` โดยเจตนา (คำสั่งหัวหน้า 2026-08-06:
"ไม่นำไปใช้กับ A/B/C") — ทะเบียนและด่านของสองสายต้องแยกขาดจากกัน
"""

from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from math import isfinite
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import candle_close, chart_story, consistency_gate, headline_format, image_output  # noqa: E402
from tools import wcb_source, wcb_writers, web_frontmatter_contract  # noqa: E402
from tools.chart_story_renderer import (calendar_split_conditions, decimals_for,
                                        money_for, thai_date)  # noqa: E402

STYLE_ID = "d_chart_story"
STYLE_NAME = "D — อ่านโครงสร้างกราฟ"
FOLDER = "D-โครงสร้างกราฟ"
# นับเฉพาะตัวอักษร — ภาษาไทยไม่เว้นวรรคระหว่างคำ นับคำแบบสายอื่นไม่ได้
# เกณฑ์ตั้งจากบทที่โครงครบแต่ตลาด "จนระดับ" (ไม่มีโซน/แนวต้านผ่านเกณฑ์เลย) ~1,700
# อักขระ ซึ่งยังเป็นบทที่ถูกต้อง · ของจริงข้อมูลครบจะได้ ~4,000+ · ต่ำกว่านี้ = โครงหาย
MIN_CHARS = 1500
_NUMBER = re.compile(r"\d[\d,\.]*")


# 🔄 **ถอดบรรทัด byline ออกจากเนื้อบททุกสไตล์ 2026-08-11 (คำสั่งผู้ใช้)**
# ตรงกับสเปกไฟล์ของทีมเว็บที่เขียนไว้ว่า "⛔ ห้ามใส่บรรทัดชื่อผู้เขียน" — หน้าเว็บมี
# กล่องผู้เขียนของมันเองซึ่งอ่านจาก `author_slug` ⇒ เขียนชื่อในเนื้อบทอีกที = ชื่อซ้ำสองที่
# ตัวคนเขียนตอนนี้สื่อผ่าน `wcb_writers.author_slug_for()` ช่องเดียว

# วลีบอกแหล่งของย่อหน้าปัจจัยพื้นฐาน — ต้องเหมือน A/B/C เป๊ะ (กฎเหล็ก: ปัจจัยพื้นฐาน
# ต้องมีแหล่งอ้างอิงเสมอ) · เก็บเป็นค่าคงที่เพื่อให้ด่าน `calendar_source_missing`
# เทียบข้อความเดียวกับที่เขียนลงบท ไม่ใช่พิมพ์ซ้ำสองที่แล้วเพี้ยนกัน
CALENDAR_SOURCE_NOTE = "ที่มา: ปฏิทินเศรษฐกิจ WorldClassBroker"

# ------------------------------------------- ชื่อหัวข้อตามใบตัวอย่าง (ผู้ใช้สั่ง 08-11)
#
# คัดลอกจาก `01-CC/Input/ภาษาการเขียน/สไตล์D.md` ทีละตัวอักษร — ห้ามแก้ถ้อยคำเอง
# **จำนวนหัวข้อลดจากหกเหลือห้า** เพราะใบตัวอย่างรวบ "จุดเข้าซื้อ" กับ "แผนการอ่านกราฟ"
# เป็นหัวข้อเดียว (SMC Execution Plan) แล้วแยกด้วยหัวข้อย่อยแทน — ซึ่งอ่านลื่นกว่า
# เพราะฉากทัศน์กับจุดเข้าคือเรื่องเดียวกัน คนอ่านไม่ต้องเลื่อนกลับไปมาระหว่างสองหัวข้อ
#
# ⚠️ Style D ไม่ใส่เลขนำหน้าหัวข้อแล้ว (ผู้ใช้สั่ง 2026-08-19) — คงชื่อล้วนไว้ที่นี่
# และประกอบเป็น H2 โดยตรง เพื่อไม่ให้การมี/ไม่มีหัวข้อปฏิทินกระทบรูปแบบหัวข้ออื่น
RULE = ("---", "")
H2_WEEKLY_DELTA = "สัปดาห์นี้เปลี่ยนอะไร"
H2_STRUCTURE = "ภาพรวมโครงสร้างตลาด"
H2_LEVELS = "แนวรับ แนวต้าน และระดับสำคัญ"
H2_SCENARIOS = "เงื่อนไขการเคลื่อนไหวของราคาและปัจจัยชี้นำ"
H3_SUPPLY = "### แนวต้านด้านบน"
H3_DEMAND = "### แนวรับด้านล่าง"
# 🔄 "ฉากทัศน์ฝั่งขึ้น/ฝั่งลง" → "กรณีขาขึ้น/กรณีขาลง" (ผู้ใช้สั่ง 2026-08-14)
# เปลี่ยนทั้งชื่อหัวข้อและประโยคสรุปที่เรียกชื่อเดียวกัน — เหตุผลเดียวกับครั้ง
# "จุด Stoploss": ของอย่างเดียวกันต้องมีชื่อเดียวทั้งบท
H3_BULLISH = "### กรณีขาขึ้น"
H3_BEARISH = "### กรณีขาลง"
H2_CALENDAR = "ปัจจัยเศรษฐกิจที่ต้องติดตาม"
H2_SUMMARY = "สรุปภาพรวมรายสัปดาห์ (Weekly Executive Summary)"
PROSE_INDENT = "&emsp;"
def image_names(asset: str, date_text: str) -> tuple[str, str]:
    """ชื่อไฟล์ภาพคู่บท — สองภาพแยกตามคำสั่งผู้ใช้ 2026-08-07 (D ไม่รวมภาพ)
    รูปแบบชื่อมีความหมาย+วันที่ ตามที่หัวหน้าแนะนำในฟีดแบ็ก 08-06
    นามสกุลมาจาก `image_output` ที่เดียว — เว็บรับเฉพาะ .webp (กติกา 08-09)"""
    suffix = image_output.IMAGE_SUFFIX
    return (f"{asset}-d1-structure-{date_text}{suffix}",
            f"{asset}-d1-levels-{date_text}{suffix}")


def calendar_week_bounds(story: dict) -> tuple[str, str]:
    """ช่วงจันทร์–ศุกร์ของภาพปฏิทิน โดยเชื่อ metadata จากแหล่งข่าวก่อน"""
    calendar = story.get("calendar") or {}
    if calendar.get("week_start") and calendar.get("week_end"):
        return str(calendar["week_start"]), str(calendar["week_end"])
    event_dates = [str(event.get("at") or "")[:10]
                   for event in calendar.get("events") or []
                   if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(event.get("at") or "")[:10])]
    anchor = date.fromisoformat(min(event_dates) if event_dates else publish_date_of(story))
    monday = anchor - timedelta(days=anchor.weekday())
    return monday.isoformat(), (monday + timedelta(days=4)).isoformat()


def calendar_image_names(story: dict) -> tuple[str, ...]:
    """ชื่อภาพปฏิทินทุกหน้า — ไม่จำกัดจำนวนข่าวที่ผ่านทะเบียน.

    คงชื่อเดิมเมื่อมีหน้าเดียวเพื่อไม่ทำลายลิงก์ของบทเก่า; เมื่อหลายหน้าใส่เลขหน้า
    ในชื่อไฟล์อย่างชัดเจน ทำให้ด่านตรวจนับและเรียงไฟล์ได้แบบ deterministic.
    """
    week_start, week_end = calendar_week_bounds(story)
    page_count = max(1, len((story.get("calendar") or {}).get("pages") or [[]]))
    stem = f"{story['asset']}-weekly-calendar-{week_start}-{week_end}"
    if page_count == 1:
        return (f"{stem}{image_output.IMAGE_SUFFIX}",)
    return tuple(
        f"{stem}-p{page:02d}-of-{page_count:02d}{image_output.IMAGE_SUFFIX}"
        for page in range(1, page_count + 1))


def calendar_image_name(story: dict) -> str:
    """ชื่อหน้าแรกสำหรับผู้เรียกรุ่นเก่า; โค้ดผลิตใหม่ต้องใช้ plural helper."""
    return calendar_image_names(story)[0]


def calendar_evidence_name(story: dict) -> str:
    week_start, week_end = calendar_week_bounds(story)
    return (f"{story['asset']}-weekly-calendar-{week_start}-{week_end}"
            "-evidence.json")


def has_calendar_image(story: dict) -> bool:
    calendar = story.get("calendar") or {}
    # feed ที่ใช้ได้แต่ไม่มีข่าวตรงทะเบียนเป็นผลลัพธ์จริง: ต้องมีภาพ empty state
    # เพื่อแยกจาก dependency ล่ม (ซึ่ง pipeline จะ hard-fail และไม่ออกบท)
    if calendar and isinstance(calendar.get("pages"), list):
        return True
    events = calendar.get("events") or []
    return bool(events and len(events) == len(calendar.get("sentences") or []))


# ---------------------------------------------------------------- ตัวเขียนบท

_THAI_ONLY = re.compile(r"[ก-๙\s]+")


def publish_date_of(story: dict) -> str:
    """วันที่เผยแพร่ของบท — ใช้ในพาดหัวและ Title tag เท่านั้น

    ก้อนเก่าที่ยังไม่มีช่องนี้ (เช่น artifact ที่ถูกบันทึกไว้ก่อน 08-14) ถอยไปใช้
    วันแท่งฐาน ⇒ อ่านก้อนเก่าไม่พังและได้พฤติกรรมเดิม
    """
    return story.get("publish_date") or story["current"]["date"]


def summary_heading(story: dict) -> str:
    """หัวข้อสรุปรายสัปดาห์; สินทรัพย์และวันที่อยู่ใน H1 แล้ว."""
    return H2_SUMMARY


def _scenario_catalyst_text(story: dict, side: str) -> str:
    """สรุปปัจจัยชี้นำจาก calendar evidence โดยไม่แต่งเหตุการณ์เพิ่มเอง.

    ใช้ไม่เกินสองเหตุการณ์ โดยให้ผลกระทบสูงมาก่อนและคงลำดับเวลาในระดับเดียวกัน
    เพื่อให้บรรทัดยังสแกนไว และใช้กฎแปลผลชุดเดียวกับภาพปฏิทิน จึงไม่มีกรณีบท
    บอกทิศหนึ่งแต่ภาพบอกอีกทิศ.
    """
    calendar = story.get("calendar") or {}
    catalysts: list[str] = []
    events = list(calendar.get("events") or [])
    prioritized = sorted(
        enumerate(events),
        key=lambda item: (0 if str(item[1].get("impact") or "").lower() == "high" else 1,
                          item[0]),
    )
    for _index, event in prioritized:
        title = " ".join(str(event.get("title") or "").split())
        if not title:
            continue
        bearish, bullish = calendar_split_conditions(event, str(story.get("asset") or ""))
        condition = bullish if side == "up" else bearish
        item = f"{title}: {condition}"
        if item not in catalysts:
            catalysts.append(item)
        if len(catalysts) == 2:
            break
    if catalysts:
        return " · ".join(catalysts)
    if calendar:
        return "รอผลจริงจากเหตุการณ์ในปฏิทินเศรษฐกิจประจำสัปดาห์"
    return "รอบนี้ไม่มีปัจจัยข่าวที่ผ่านเกณฑ์ของระบบ"


def _asset_name(profile: dict) -> str:
    """ชื่อสินทรัพย์สำหรับร้อยแก้วไทย — "ราคาทองคำ" · "ค่าเงินบาท" · "ราคายูโร"

    🐞 **บั๊กจากรอบเขียนใหม่ 08-14 (จับได้ตอนไล่ดูครบทั้งแปดคู่):** ของเดิมใช้
    `seo_name` ตรง ๆ ซึ่งเป็นชื่อสำหรับ**ช่องคำค้น** ไม่ใช่ร้อยแก้ว ⇒ ได้
    "ราคาEUR/USD (EUR/USD)" (ซ้ำสองรอบ + อักษรละตินติดคำไทย) และ
    "ภาพรวมราคาSOLวันนี้" — บทเรียนเดียวกับที่ `wcb_source` เตือนไว้เรื่อง NVDA

    กติกา: `seo_name` ใช้ได้เฉพาะเมื่อเป็นภาษาไทยล้วน · มีอักษรละตินเมื่อไหร่
    ถอยไปใช้ `short_name` ซึ่งเขียนไว้ให้ต่อกับคำไทยตรง ๆ ได้ทุกตัว ·
    ชื่อที่ขึ้นต้นด้วย "ค่าเงิน/ราคา/หุ้น" อยู่แล้วไม่ต้องเติม "ราคา" ซ้ำหน้า
    """
    name = profile["seo_name"]
    if not _THAI_ONLY.fullmatch(name):
        name = profile["short_name"]
    return name if name.startswith(("ค่าเงิน", "ราคา", "หุ้น")) else f"ราคา{name}"


def _opening_asset_name(story: dict, profile: dict) -> str:
    """ชื่อสินทรัพย์ในประโยคเปิด — ทองคำพาไปหน้าราคาของเว็บโดยตรง

    ลิงก์วางเฉพาะคำว่า ``ราคาทองคำ`` ไม่ครอบตัวเลขหรือข้อสรุปตลาด เพื่อให้คำเชื่อมโยง
    ตรงกับหน้าปลายทางและไม่รบกวนการอ่านประโยคแรก · ใช้ relative URL ที่ทีมเว็บ
    ยืนยันแล้วเหมือน `_internal_links`; สินทรัพย์อื่นคงพฤติกรรมเดิมตามขอบเขตคำสั่งนี้
    """
    name = _asset_name(profile)
    if story["asset"] == "xauusd":
        return f"[{name}](/thailand/asset-xauusd)"
    return name


def _h2(title: str) -> str:
    """หัวข้อ Style D ไม่มีเลขลำดับตามรูปแบบที่ผู้ใช้อนุมัติ 2026-08-19"""
    return f"## {title}"


def _indent_prose_lines(lines: list[str]) -> list[str]:
    """เยื้องเฉพาะย่อหน้าร้อยแก้วหนึ่ง tab ที่มองเห็นได้บนหน้าเว็บ

    Markdown มักยุบ tab/space ต้นบรรทัดและสี่ช่องว่างอาจกลายเป็น code block จึงใช้
    ``&emsp;`` ตามมติผู้ใช้ ส่วนหัวข้อ ภาพ เส้นคั่น และรายการยังคงโครงสร้างเดิม
    """
    result: list[str] = []
    in_frontmatter = False
    frontmatter_closed = False
    structural_list = re.compile(r"^\s*(?:[-+*]\s|\d+\.\s)")
    standalone_bold = re.compile(r"^\*\*.+\*\*$")
    for line in lines:
        stripped = line.strip()
        if not frontmatter_closed and stripped == "---":
            in_frontmatter = not in_frontmatter
            if not in_frontmatter:
                frontmatter_closed = True
            result.append(line)
            continue
        is_structure = (
            in_frontmatter or not stripped or stripped.startswith(("#", "!["))
            or stripped == "---" or structural_list.match(line)
            or stripped.startswith("|")
            or standalone_bold.fullmatch(stripped)
        )
        result.append(line if is_structure else PROSE_INDENT + line)
    return result


def _channel_position(story: dict) -> str:
    """ตำแหน่งราคาปัจจุบันเทียบเส้นหลักของกรอบ — คำพูดต้องตามเลข ไม่ใช่ตามอารมณ์"""
    channel = story["channel"]
    if not channel:
        return ""
    # 🔄 ถ้อยคำเขียนใหม่ 08-14 (ผู้ใช้สั่ง) — ต่อท้ายประโยค "ราคาปิดตลาด ณ ระดับ …"
    # ทุกกิ่งจึงต้องขึ้นต้นด้วยคำที่ต่อประโยคเดิมได้ ไม่ใช่ประโยคใหม่ที่ขึ้นต้นด้วย "ราคา…"
    edge = "ขอบบน" if channel["main_is_upper"] else "ขอบล่าง"
    frame = "Bearish Channel" if story["regime"]["down"] else "Bullish Channel"
    gap = story["current"]["close"] - channel["main_at_last"]
    if channel["main_is_upper"]:
        if gap > 0:
            return (f"พร้อมส่งสัญญาณทะลุกรอบ{edge}ของ {frame} "
                    "ซึ่งยังต้องติดตามการย้อนทดสอบเพื่อยืนยันว่าเป็นสัญญาณทะลุจริงหรือไม่")
        if abs(gap) <= story["atr14"]:
            return f"โดยราคาเข้าชนกรอบ{edge}ของ {frame} พอดี — เป็นจุดวัดใจของทั้งสองฝั่ง"
        return f"โดยยังเคลื่อนไหวอยู่ภายในกรอบ {frame} ใต้แนว{edge}"
    if gap < 0:
        return (f"พร้อมส่งสัญญาณหลุดกรอบ{edge}ของ {frame} "
                "ซึ่งยังต้องติดตามการย้อนทดสอบเพื่อยืนยันว่าเป็นสัญญาณหลุดจริงหรือไม่")
    if gap <= story["atr14"]:
        return f"โดยราคาเข้าทดสอบกรอบ{edge}ของ {frame} พอดี"
    return f"โดยยังเคลื่อนไหวอยู่ภายในกรอบ {frame} เหนือแนว{edge}"


def headline_price_for(story: dict):
    """ตัวจัดรูปราคา**เฉพาะในพาดหัว** — กระชับกว่าในเนื้อบท

    ตัวอย่างของหัวหน้าเขียน "ทองยืน 4,262" ไม่ใช่ "4,262.35" · พาดหัวมีที่จำกัดและ
    ทศนิยมไม่ได้ช่วยให้ตัดสินใจคลิก · ตัวเลขเต็มความละเอียดยังอยู่ในเนื้อบทครบทุกตัว

    ⚠️ **คู่เงินปัดจำนวนเต็มไม่ได้** — 1.15403 จะเหลือ "1" ซึ่งไม่มีความหมาย
    ⇒ ปัดเฉพาะสินทรัพย์ที่ราคาเป็นหลักร้อยขึ้นไปและทะเบียนใช้ทศนิยมไม่เกิน 2
    """
    money = money_for(story)
    places = decimals_for(story)

    def render(value: float) -> str:
        if places <= 2 and abs(value) >= 100:
            return f"{value:,.0f}"
        return money(value)
    return render


def _headline_hook(story: dict) -> str:
    """วลีพาดหัวจากสภาพจริงของโครงสร้าง — เลือกจากเงื่อนไขที่วัดได้เท่านั้น

    🆕 **เขียนใหม่ 2026-08-10 (ผู้ใช้: "อ่านแล้วยังงง ไม่เข้าใจ")** — ของเดิมเป็นศัพท์
    ของคนอ่านกราฟ ("จังหวะวัดใจหน้ากรอบขาลง" / "โครงสร้างขาขึ้นยังคุมเกม") คนที่เห็น
    พาดหัวในผลค้นหายังไม่ได้อ่านบท จึงไม่รู้ว่ากรอบไหน วัดใจอะไร ⇒ ไม่มีเหตุผลให้คลิก

    หลักที่ใช้แทน — ตรงกับตัวอย่างที่หัวหน้าให้มา ("ทองยืน 4,262 รอ Fed ชี้ทาง"):
    **บอกว่าตอนนี้อยู่ตรงไหน แล้วต้องจับตาอะไรต่อ** ด้วยคำที่คนทั่วไปใช้จริง

    ⛔ **ยังห้ามชี้ทิศราคา** (ระยะ 3b/`RL-006` ผู้ใช้ยังไม่เคาะ) — ใช้ "จับตา"/"ทดสอบ"
    ซึ่งบอกว่าระดับนั้นสำคัญ ไม่ได้บอกว่าราคาจะไปถึง · ห้ามใช้ "ลุ้น"/"เป้า"/"พุ่ง"
    """
    close = story["current"]["close"]
    money = headline_price_for(story)
    above = sorted(level["mean"] for level in story["resistance"] if level["mean"] > close)
    below = sorted((zone["mean"] for zone in story["zones"] if zone["mean"] < close),
                   reverse=True)
    # ระดับที่ใกล้ราคาที่สุดคือระดับที่คนอ่านต้องดูก่อน — เลือกฝั่งตามโหมดตลาด
    # เพื่อไม่ให้พาดหัวชวนคิดว่าราคาจะวิ่งสวนโหมดที่บทกำลังเล่า
    if story["regime"]["down"] and below:
        return f"จับตาโซนรับ {money(below[0])}"
    if not story["regime"]["down"] and above:
        return f"จับตาแนวต้าน {money(above[0])}"
    if above:
        return f"จับตาแนวต้าน {money(above[0])}"
    if below:
        return f"จับตาโซนรับ {money(below[0])}"
    return "อ่านระดับสำคัญของรอบนี้"


def _h1_tail(story: dict) -> str:
    """หางของ H1 — สาระของ**วันนั้น** ตามตัวอย่างที่หัวหน้าให้มา ("ทองยืน 4,262 รอ Fed ชี้ทาง")

    ประกอบจากของที่วัดได้ล้วน: คำสั้นของสินทรัพย์ + ยืน/หลุดเทียบเส้นค่าเฉลี่ย 50 วัน +
    ราคาปิดจริง + วลีโครงสร้าง · **ราคาปัดเป็นจำนวนเต็มเฉพาะในพาดหัว** เพื่อความกระชับ
    (ตัวอย่างของหัวหน้าเขียน "4,262" ไม่ใช่ "4,262.35") ตัวเลขเต็มยังอยู่ในเนื้อบทครบ
    """
    profile = wcb_source.profile_for(story["asset"])
    close = story["current"]["close"]
    sma50 = story["sma50_last"]
    verb = "ยืน" if sma50 is None or close >= sma50 else "หลุด"
    return f"{profile['short_name']}{verb} {close:,.0f} {_headline_hook(story)}"


def headline(story: dict) -> str:
    """H1 ตามต้นแบบ Style D ที่ผู้ใช้ยืนยัน 2026-08-25.

    Title tag ยังคงเป็นช่อง SEO แยกต่างหาก ส่วนสาระรายวันย้ายไปอยู่คำโปรยใต้ H1
    เพื่อให้ชื่อบทนิ่ง อ่านง่าย และไม่สูญเสียข้อมูลที่เดิมอยู่ในหางพาดหัว
    """
    profile = wcb_source.profile_for(story["asset"])
    name = profile["seo_name"]
    symbol = profile["symbol"]
    label = name if symbol in name else f"{name} {symbol}"
    spacer = " " if label[:1].isascii() else ""
    date_text = headline_format.thai_date(publish_date_of(story), full_month=True)
    return f"วิเคราะห์ราคา{spacer}{label} ประจำวันที่ {date_text}"


def seo_title(story: dict) -> str:
    """Title tag ที่หลังบ้านเอาไปใช้ — เดือนเต็ม + หางของสไตล์ D (สเปก 2026-08-10)

    ระบบผลิตให้เอง ไม่มีใครพิมพ์มือ (สายผลิตส่งออกใน `chart_story_pipeline.run()`)

    ⚠️ **ห้ามปล่อยให้ตกไปใช้หางคงที่ของทะเบียน** — หางทะเบียนเป็นของสไตล์ A ที่ไม่ได้
    ส่งหางของตัวเองมา · เคยพลาดข้อนี้จริง (ผู้ใช้จับได้ 2026-08-10): D เรียก
    `headline_format.title()` เปล่า ๆ จึงได้หางเดียวกับ A เป๊ะทั้งบรรทัด และเทสไม่จับ
    เพราะตัวที่เทียบพาดหัวว่าซ้ำกันไหมดูแค่ A/B/C ซึ่งอยู่คนละโมดูลกับ D/E
    ⇒ ตอนนี้มีเทสเทียบครบทั้งห้าสไตล์แล้ว (`test_headline_format.พาดหัวข้ามทุกสไตล์`)

    หางของ D ชี้ไปที่ของที่บทนี้มีจริงและสไตล์อื่นไม่มี: ระดับแนวรับแนวต้านที่วาดลงภาพ
    """
    profile = wcb_source.profile_for(story["asset"])
    return headline_format.title(story["asset"], publish_date_of(story),
                                 f"แนวรับแนวต้านจากกราฟ {profile['symbol']}")


def publication_slug(story: dict, *, kind: str) -> str:
    """slug ที่ทีมเว็บยืนยันสำหรับ Style D/E — แยกสไตล์และส่งซ้ำแล้วทับใบเดิมได้"""
    if kind not in {"levels", "signals"}:
        raise ValueError(f"ไม่รู้จักชนิด slug ของ D/E: {kind}")
    asset = str(story["asset"]).strip().lower()
    publish_date = str(publish_date_of(story))
    slug = f"{asset}-{kind}-{publish_date}"
    if not re.fullmatch(r"[a-z0-9]+-(?:levels|signals)-\d{4}-\d{2}-\d{2}", slug):
        raise ValueError(f"slug ของ D/E ไม่ตรงสัญญาเว็บ: {slug}")
    return slug


def frontmatter_lines(story: dict, *, excerpt_clauses: list[str] | None = None,
                      title_text: str | None = None,
                      slug_kind: str = "levels") -> list[str]:
    """หัวไฟล์ของสไตล์ D/E — **เปิดใช้ 2026-08-10 ตามคำสั่งผู้ใช้ (ทุกสไตล์ต้องมี title)**

    เดิมสไตล์นี้ห้ามมี frontmatter (กฎ `frontmatter_forbidden`) ซึ่งตั้งไว้ตอนยังไม่รู้ว่า
    หลังบ้านรับได้ไหม · ทีมเว็บตอบแล้ว 08-09 ว่า **ส่งมาเองได้และแนะนำให้ส่ง** เพราะ
    ค่าที่ส่งมาชนะค่าที่ระบบเดาเสมอ ⇒ ส่ง `title`/`excerpt` เองดีกว่าปล่อยให้เว็บเดา

    `excerpt` = meta description ตัวจริงของหน้า — ยกจากคำโปรยที่บทมีอยู่แล้ว

    ⚠️ **สไตล์ E ใช้ฟังก์ชันนี้ร่วมกันแต่ story คนละโครง** (ไม่มีช่อง `resistance`/`zones`)
    ⇒ ผู้เรียกส่ง `excerpt_clauses` ของตัวเองมาได้ ห้ามให้ตัวนี้เดาโครงของอีกสไตล์
    """
    excerpt = wcb_writers.fit_excerpt(excerpt_clauses or _excerpt_clauses(story))
    title = title_text or seo_title(story)
    timeframe = story.get("timeframe") or story.get("display", {}).get("timeframe")
    timeframe_label = "1H" if timeframe == "1h" else "Daily"
    return [
        "---",
        f"asset: {web_frontmatter_contract.public_asset_tag(story['asset'])}",
        f"title: {wcb_writers.fit_title(title)}",
        f"slug: {publication_slug(story, kind=slug_kind)}",
        f"excerpt: {excerpt}",
        f"author_slug: {wcb_writers.author_slug_for(story['asset'])}",
        f"timeframe: {timeframe_label}",
        f"trend: {'dn' if story['regime']['down'] else 'up'}",
        "---",
        "",
    ]


def _excerpt_clauses(story: dict) -> list[str]:
    """ประโยคสำหรับคำโปรย — ต่อกันจนถึงช่วงความยาวที่ระบบนำเข้าบังคับ (120–160)"""
    money = money_for(story)
    profile = wcb_source.profile_for(story["asset"])
    if story["asset"] == "xauusd" and story["resistance"] and story["zones"]:
        # ถ้อยคำที่ผู้ใช้เลือก 2026-08-18 — ใช้กับทองเท่านั้นเพื่อไม่ขยายมติไปยัง
        # สินทรัพย์อื่น และคงตัวเลขจาก story เหมือนเดิมทุกวัน
        return [
            f"ราคาทองปิดล่าสุดที่ {money(story['current']['close'])} ดอลลาร์",
            f"ยังมีแนวต้าน {money(story['resistance'][0]['mean'])} รออยู่ด้านบน",
            f"ขณะที่โซน {money(story['zones'][0]['mean'])} เป็นฐานรับสำคัญ",
            "มาดูกันว่าโครงสร้างกราฟรายวันกำลังบอกอะไร",
        ]
    clauses = [f"{profile['short_name']}ปิดที่ {money(story['current']['close'])} ดอลลาร์"]
    if story["resistance"]:
        clauses.append(f"แนวต้านแรก {money(story['resistance'][0]['mean'])}")
    if story["zones"]:
        clauses.append(f"โซนรับ {money(story['zones'][0]['mean'])}")
    clauses += ["อ่านโครงสร้างกราฟรายวันพร้อมระดับที่ทำให้มุมมองเปลี่ยน",
                "ทุกระดับคำนวณจากแท่งราคาจริง"]
    return clauses


def _memory_note(level: dict, story: dict, *, kind: str = "โซน") -> str:
    """วลีกำกับความต่อเนื่อง — ระดับที่ล็อกข้ามวันบอกคนอ่านตรง ๆ ว่าเป็นชุดเดิม

    ผู้ใช้เคาะ 08-10 (#18ข): ระดับล็อกจนกว่าราคาปิดทะลุ — ความต่อเนื่องข้ามวัน
    คือจุดขายของบท ไม่ใช่แค่กติกาภายใน · วันเดียวกับที่ล็อกไม่ต้องกำกับ (ยังไม่ "เดิม")
    """
    if story.get("verified_continuity_only"):
        return ""
    locked_since = level.get("locked_since")
    if not locked_since or locked_since >= story["current"]["date"]:
        return ""
    return f"({kind}เดิมที่ใช้อ้างอิงมาตั้งแต่ {thai_date(locked_since)}) "


def _weekly_delta_section(story: dict, money) -> list[str]:
    """Lead with evidence-backed changes; never rotate synonyms at random."""
    if story.get("verified_continuity_only"):
        return []
    delta = story.get("weekly_delta")
    if not delta:
        return []
    current = delta["current"]
    previous = delta.get("previous")
    lines = [*RULE, _h2(H2_WEEKLY_DELTA), ""]
    if delta["status"] == "baseline" or not previous:
        lines += [
            "รอบนี้เป็นฐานเปรียบเทียบของระบบรายสัปดาห์ "
            "จึงยังไม่กล่าวอ้างว่าราคาเปลี่ยนจากสัปดาห์ก่อน "
            "ตั้งแต่รอบถัดไปบทจะสรุปเฉพาะสิ่งที่เปลี่ยนจากฐานนี้", "",
        ]
        items = [
            f"**ราคาปิด:** ฐานเปรียบเทียบอยู่ที่ {money(current['close'])} ดอลลาร์",
            ("**โครงสร้างหลัก:** เป็นขาลง" if current["regime_down"]
             else "**โครงสร้างหลัก:** เป็นขาขึ้น"),
        ]
        if current["resistance"]:
            items.append(
                f"**แนวต้านแรก:** อยู่ที่ "
                f"{money(current['resistance'][0]['mean'])} ดอลลาร์")
        if current["zones"]:
            zone = current["zones"][0]
            items.append(
                f"**แนวรับหลัก:** อยู่ที่ {money(zone['low'])}–"
                f"{money(zone['high'])} ดอลลาร์")
        return lines + wcb_writers.listing("", items) + [""]

    change = delta["close_change"]
    change_pct = delta["close_change_pct"]
    if abs(change) <= 1e-12:
        price_item = (f"**ราคาปิด:** ทรงตัวจากสัปดาห์ก่อนที่ "
                      f"{money(current['close'])} ดอลลาร์")
    else:
        direction = "เพิ่มขึ้น" if change > 0 else "ลดลง"
        price_item = (
            f"**ราคาปิด:** {direction} {money(abs(change))} ดอลลาร์ หรือ "
            f"{abs(change_pct):.2f}% จาก {money(previous['close'])} เป็น "
            f"{money(current['close'])} ดอลลาร์")
    items = [price_item]
    if delta["regime_changed"]:
        previous_direction = "ขาลง" if previous["regime_down"] else "ขาขึ้น"
        current_direction = "ขาลง" if current["regime_down"] else "ขาขึ้น"
        items.append(
            f"**โครงสร้างหลัก:** เปลี่ยนจาก{previous_direction}เป็น{current_direction}")
    else:
        current_direction = "ขาลง" if current["regime_down"] else "ขาขึ้น"
        items.append(
            f"**โครงสร้างหลัก:** ยังเป็น{current_direction}เหมือนสัปดาห์ก่อน")

    current_zone = current["zones"][0] if current["zones"] else None
    if delta["zone_status"] == "unchanged" and current_zone:
        zone_item = (
            f"**แนวรับหลัก:** ยังไม่เปลี่ยน อยู่ที่ {money(current_zone['low'])}–"
            f"{money(current_zone['high'])} ดอลลาร์")
        touches_change = delta.get("zone_touches_change")
        if touches_change and touches_change > 0:
            zone_item += f" และมีจุดอ้างอิงเพิ่ม {touches_change} ครั้ง"
        elif touches_change and previous.get("zones"):
            zone_item += (
                f" โดยจำนวนจุดอ้างอิงเปลี่ยนจาก {previous['zones'][0]['touches']} "
                f"เป็น {current_zone['touches']} ครั้ง")
        items.append(zone_item)
    elif delta["zone_status"] in {"new", "changed"} and current_zone:
        items.append(
            f"**แนวรับหลัก:** ปรับเป็น {money(current_zone['low'])}–"
            f"{money(current_zone['high'])} ดอลลาร์จากหลักฐานแท่งล่าสุด")
    elif delta["zone_status"] == "missing":
        items.append(
            "**แนวรับหลัก:** ชุดเดิมไม่ผ่านเกณฑ์ของรอบนี้ "
            "ระบบจึงไม่สร้างระดับใหม่ขึ้นแทน")

    current_resistance = (current["resistance"][0] if current["resistance"] else None)
    previous_resistance = (previous["resistance"][0]
                           if previous.get("resistance") else None)
    if delta["resistance_status"] == "changed" and current_resistance:
        if previous_resistance:
            items.append(
                f"**แนวต้านแรก:** ขยับจาก {money(previous_resistance['mean'])} เป็น "
                f"{money(current_resistance['mean'])} ดอลลาร์")
        else:
            items.append(
                f"**แนวต้านแรก:** รอบนี้อยู่ที่ "
                f"{money(current_resistance['mean'])} ดอลลาร์")
    elif delta["resistance_status"] == "unchanged" and current_resistance:
        items.append(
            f"**แนวต้านแรก:** ยังอยู่ที่ "
            f"{money(current_resistance['mean'])} ดอลลาร์")
    elif delta["resistance_status"] == "missing":
        items.append(
            "**แนวต้านแรก:** รอบนี้ไม่มีระดับที่ผ่านเกณฑ์พอให้ระบุเป็นด่านยืนยัน")
    return lines + wcb_writers.listing("", items) + [""]


def _weekly_zone_note(story: dict, zone: dict) -> str:
    """Explain the zone's current role instead of repeating support theory."""
    delta = {} if story.get("verified_continuity_only") else story.get("weekly_delta") or {}
    close = story["current"]["close"]
    if zone["low"] <= close <= zone["high"]:
        return ("ราคาปิดอยู่ภายในโซน จึงเป็นการทดสอบแนวรับที่กำลังเกิดขึ้นจริง "
                "ต้องดูแท่งรายวันชุดถัดไปว่าราคาจะกลับมายืนเหนือขอบบนได้หรือไม่")
    if close > zone["high"]:
        if delta.get("zone_status") == "unchanged":
            return ("ระดับนี้ยังเป็นฐานเดิมของโครงสร้าง แต่ราคาปิดล่าสุดอยู่เหนือโซน "
                    "จึงยังไม่ใช่การทดสอบแนวรับครั้งใหม่")
        return ("ราคาปิดล่าสุดยังอยู่เหนือโซน ระดับนี้จึงทำหน้าที่เป็นฐานของโครงสร้าง "
                "มากกว่าด่านใกล้ราคาของรอบนี้")
    return ("ราคาปิดอยู่ต่ำกว่าโซนรับที่แสดงอยู่ "
            "จึงต้องให้ด่านโครงสร้างตรวจระดับชุดใหม่ก่อนนำไปใช้ต่อ")


def _level_number(value, *, field: str) -> float:
    """Return a finite numeric level or stop before rendering a partial table."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"levels_table_contract: {field} ต้องเป็นตัวเลข")
    value = float(value)
    if not isfinite(value):
        raise ValueError(f"levels_table_contract: {field} ต้องเป็นค่าจำกัด")
    return value


def _quote_currency(story: dict) -> str:
    """Get the quote code from the trusted asset registry, never from a literal."""
    profile = wcb_source.profile_for(story["asset"])
    symbol = str(profile.get("symbol") or "")
    parts = symbol.split("/")
    if len(parts) != 2 or not re.fullmatch(r"[A-Z]{3}", parts[1]):
        raise ValueError("levels_table_contract: ไม่พบ quote currency ในทะเบียนสินทรัพย์")
    return parts[1]


def _level_role(level: dict, story: dict, *, rank: int) -> str:
    """Use only evidence present on a source level; no inferred price claims."""
    trigger = (story.get("scenarios") or {}).get("up") or {}
    if rank == 1 and trigger.get("trigger") == level.get("mean"):
        return "จุดยืนยันการเปลี่ยนโมเมนตัมเมื่อราคาปิดเหนือระดับนี้"
    if level.get("touches") is not None:
        return f"ระดับโครงสร้างที่มีหลักฐานการทดสอบ {level['touches']} ครั้ง"
    return "ระดับโครงสร้างจากข้อมูลราคาจริง"


def _zone_role(zone: dict, story: dict, *, main: bool) -> str:
    parts = []
    if zone.get("touches") is not None:
        parts.append(f"มีหลักฐานการทดสอบ {zone['touches']} ครั้ง")
    if zone.get("includes_week52_low"):
        parts.append("ครอบจุดต่ำสุดในรอบ 52 สัปดาห์")
    if not parts:
        parts.append("เป็นฐานราคาจากข้อมูลโครงสร้าง")
    if main and (story.get("scenarios") or {}).get("down"):
        down = story["scenarios"]["down"]
        if down.get("trigger") is not None and zone.get("low") <= down["trigger"] <= zone.get("high"):
            parts.append("เป็นโซนที่ใช้ติดตามเงื่อนไขฝั่งลง")
    return " · ".join(parts)


def _level_table_rows(story: dict) -> list[dict]:
    """Build deterministic, evidence-backed rows for the Style D levels table."""
    current = _level_number(story.get("current", {}).get("close"), field="current.close")
    money = money_for(story)
    # Formatting is the dedup contract: two source values shown identically are one row.
    seen: set[tuple] = set()
    current_collision_roles: list[str] = []
    resistance: list[dict] = []
    raw_resistance = story.get("resistance") or []
    for index, level in enumerate(raw_resistance):
        mean = _level_number(level.get("mean"), field=f"resistance[{index}].mean")
        if mean <= current:
            continue
        key = ("price", money(mean))
        if key in seen:
            continue
        seen.add(key)
        resistance.append({"mean": mean, "source": level, "index": index})
    resistance.sort(key=lambda item: (item["mean"] - current, item["index"]))
    resistance = resistance[:3]
    rows: list[dict] = []
    # Rank is assigned by distance (nearest = 1), but presentation is far -> near.
    for rank, item in enumerate(resistance, 1):
        level = item["source"]
        if money(item["mean"]) == money(current):
            current_collision_roles.append(_level_role(level, story, rank=rank))
            continue
        rows.append({
            "kind": "resistance", "side": "resistance", "label": f"แนวต้าน {rank}",
            "low": item["mean"], "high": item["mean"], "sort_price": item["mean"],
            "distance": item["mean"] - current, "source_ids": (f"resistance:{item['index']}",),
            "role_text": _level_role(level, story, rank=rank),
        })

    current_row = {
        "kind": "current", "side": "current", "label": "ราคาปัจจุบัน",
        "low": current, "high": current, "sort_price": current, "distance": 0.0,
        "source_ids": ("current:close",),
        "role_text": "จุดอ้างอิงของราคาปิด ณ วันที่เผยแพร่",
    }
    if current_collision_roles:
        current_row["role_text"] += " · " + " · ".join(current_collision_roles)
    rows.append(current_row)

    # Qualifying zones are at or below current; a zone entirely above is not support.
    supports: list[dict] = []
    raw_zones = story.get("zones") or []
    for index, zone in enumerate(raw_zones):
        low = _level_number(zone.get("low"), field=f"zones[{index}].low")
        high = _level_number(zone.get("high"), field=f"zones[{index}].high")
        if low > high:
            raise ValueError(f"levels_table_contract: zones[{index}] ช่วงราคากลับด้าน")
        if low > current:
            continue
        range_key = ("range", money(low), money(high))
        if range_key in seen:
            continue
        seen.add(range_key)
        distance = 0.0 if low <= current <= high else max(0.0, current - high)
        supports.append({"zone": zone, "index": index, "low": low, "high": high,
                         "distance": distance, "range_key": range_key})

    # Stable source priority resolves equal-distance rows after the numeric sort.
    supports.sort(key=lambda item: (item["distance"], item["index"]))
    for position, item in enumerate(supports):
        zone = item["zone"]
        label = "แนวรับหลัก" if position == 0 else (
            "แนวรับระยะยาว" if position == 1 else f"แนวรับระยะยาว {position}")
        rows.append({
            "kind": "zone", "side": "support", "label": label,
            "low": item["low"], "high": item["high"],
            "sort_price": item["high"], "distance": item["distance"],
            "source_ids": (f"zone:{item['index']}",),
            "role_text": _zone_role(zone, story, main=position == 0),
        })

    sma = story.get("sma50_last")
    if sma is not None:
        sma = _level_number(sma, field="sma50_last")
        if sma == current or money(sma) == money(current):
            current_row["source_ids"] += ("sma50:current",)
            current_row["role_text"] += " · เส้นค่าเฉลี่ย 50 วันอยู่ที่ราคาปัจจุบัน"
        elif sma > current:
            row = {"kind": "sma", "side": "resistance",
                   "label": "แนวต้านจากเส้นค่าเฉลี่ย 50 วัน", "low": sma,
                   "high": sma, "sort_price": sma, "distance": sma - current,
                   "source_ids": ("sma50:resistance",),
                   "role_text": "เส้นค่าเฉลี่ยนี้ยังกดราคา หากปิดวันเหนือเส้นได้แรงซื้อจะเริ่มกลับมา"}
            if not any(money(row["sort_price"]) == money(existing["sort_price"])
                       for existing in rows if existing["side"] == "resistance"):
                rows.append(row)
        else:
            merged = next((row for row in rows if row["side"] == "support"
                           and (row["low"] <= sma <= row["high"]
                                or money(sma) in {money(row["low"]), money(row["high"])})), None)
            if merged:
                merged["source_ids"] += ("sma50:support",)
                merged["role_text"] += " · เส้นค่าเฉลี่ยนี้ช่วยรองรับราคา"
            else:
                rows.append({"kind": "sma", "side": "support",
                             "label": "แนวรับจากเส้นค่าเฉลี่ย 50 วัน", "low": sma,
                             "high": sma, "sort_price": sma, "distance": current - sma,
                             "source_ids": ("sma50:support",),
                             "role_text": "เส้นค่าเฉลี่ยนี้ช่วยรองรับราคา หากปิดวันหลุดใต้เส้นต้องติดตามโมเมนตัม"})

    # Render order is part of the public contract, not source-array order.
    resistance_rows = sorted((row for row in rows if row["side"] == "resistance"),
                             key=lambda row: (-row["sort_price"], row["label"]))
    support_rows = sorted((row for row in rows if row["side"] == "support"),
                          key=lambda row: (row["distance"], row["sort_price"], row["label"]))
    return resistance_rows + [current_row] + support_rows


def _level_cell(value, money) -> str:
    if value is None:
        return ""
    return money(value)


def _level_table_markdown(story: dict) -> list[str]:
    rows = _level_table_rows(story)
    money = money_for(story)
    quote = _quote_currency(story)
    lines = [f"| ระดับเทคนิค | กรอบราคา ({quote}) | ความสำคัญและบทบาททางเทคนิค |",
             "| :--- | :--- | :--- |"]
    for row in rows:
        price = (_level_cell(row["low"], money) if row["low"] == row["high"]
                 else f"{_level_cell(row['low'], money)}–{_level_cell(row['high'], money)}")
        cells = (row["label"], price, row["role_text"])
        lines.append("| " + " | ".join(str(cell).replace("|", "\\|") for cell in cells) + " |")
    return lines + [""]


def render_article(story: dict) -> str:
    money = money_for(story)
    profile = wcb_source.profile_for(story["asset"])
    first_image, second_image = image_names(story["asset"], story["current"]["date"])
    down = story["regime"]["down"]
    current_text = money(story["current"]["close"])
    zones = story["zones"]
    above = sorted(level["mean"] for level in story["resistance"])
    channel = story["channel"]
    opening_asset = _opening_asset_name(story, profile)

    # ---- ย่อหน้าแรกใต้หัวข้อโครงสร้าง ----
    # ผู้ใช้สั่ง 2026-08-19 ให้ตัดเกริ่นก่อน H2 และรวมราคา วันแท่งฐาน แนวโน้ม และลิงก์
    # ไว้ในย่อหน้าแรกใต้หัวข้อเดียวกัน เพื่อไม่ให้ราคา/แนวโน้มถูกเล่าซ้ำสองช่วง
    if down:
        close = story["current"]["close"]
        channel_top = (max(channel["main_at_last"], channel["parallel_at_last"])
                       if channel else None)
        first_resistance = min(above) if above else None
        if (channel_top is not None and close > channel_top
                and story["sma50_last"] is not None and close >= story["sma50_last"]
                and first_resistance is not None and close <= first_resistance):
            structure_view = (
                "ภาพรายวันยังมีโครงสร้างหลักเป็นขาลง แต่ราคาล่าสุดทะลุขอบบน"
                "ของกรอบขาลงย่อยแล้ว อย่างไรก็ตาม "
                f"ยังไม่ยืนยันการกลับตัวเต็มรูปแบบจนกว่าจะปิดวันเหนือ "
                f"{money(first_resistance)} ดอลลาร์")
        else:
            structure_view = "ภาพรายวันยังมีโครงสร้างหลักเป็นขาลง"
    else:
        structure_view = "ภาพรายวันยังอยู่ในแนวโน้มขาขึ้น"
        if channel and not channel["main_is_upper"]:
            structure_view += " โดยราคายังเคลื่อนไหวเหนือขอบล่างของกรอบ"
    structure_opening = (
        f"{opening_asset}ปิดที่ {current_text} ดอลลาร์ "
        f"จากตลาดวันที่ {thai_date(story['current']['date'])} {structure_view}")
    # ชื่อบทนิ่งตามต้นแบบ ส่วนประเด็นของวันอยู่ในคำโปรยตัวหนาใต้ H1
    lines = frontmatter_lines(story) + [
        "# " + headline(story), "",
        f"**{_h1_tail(story)}**", "",
    ]
    lines += _weekly_delta_section(story, money)
    lines += [*RULE, _h2(H2_STRUCTURE), "", structure_opening, ""]

    # ต้นแบบ 08-25 ให้เล่าโครงสร้างต่อจากย่อหน้าเปิดโดยไม่เพิ่มหัวข้อย่อยซ้ำ
    if channel:
        lines += [(f"กรอบนี้เชื่อมจุดกลับตัวได้ {channel['touch_count']} จุด "
                   "จึงใช้เป็นแนวอ้างอิงของโซนราคานี้ "
                   + _memory_note(channel, story, kind="กรอบ")).rstrip(), ""]
    if zones and story.get("weekly_delta"):
        zone1 = zones[0]
        lines += wcb_writers.listing("", [
            f"**ฐานราคา {money(zone1['mean'])} ดอลลาร์:** "
            f"{_weekly_zone_note(story, zone1)}",
        ]) + [""]
    elif zones:
        zone1 = zones[0]
        # การเล่าเรื่องจำนวนครั้งที่แตะ: ตามหลัก SMC โซนที่ถูกแตะซ้ำถือว่าถูกใช้
        # (mitigated) ไปมากแล้ว — ห้ามเล่าว่า "ยิ่งแตะยิ่งแข็ง"
        # (ฟีดแบ็กหัวหน้า 08-06 ข้อ 2 · เลือกทางเล่าแบบ "แนวอ้างอิงร่วมของตลาด")
        lines += [f"**บททดสอบแนวรับสำคัญ {money(zone1['mean'])} ดอลลาร์**", "",
                  f"บริเวณ {money(zone1['mean'])} ดอลลาร์ ทำหน้าที่เป็นแนวรับอ้างอิง"
                  f"และถูกทดสอบมาแล้วถึง {zone1['touches']} ครั้ง "
                  "จุดสำคัญคือ:", ""]
        lines += wcb_writers.listing("", [
            "การลงมาแตะแนวรับซ้ำ ๆ อาจทำให้แรงซื้อที่รออยู่บริเวณนี้ลดลงเรื่อย ๆ",
            "การกลับลงมาทดสอบในครั้งถัดไปจึง **ไม่ได้รับประกันว่าราคาจะดีดกลับ** "
            "แต่เป็นบททดสอบความแข็งแกร่งของโซน",
            "หากราคาปิดวันหลุดแนวรับนี้ แรงขายจะกลับมาได้เปรียบอีกครั้ง",
            "**สรุป:** โครงสร้างนี้รอการเลือกทางเพียง 2 ฝั่งเท่านั้น คือ "
            "\"เบรกทะลุกรอบขอบบนขึ้นไป\" หรือ \"หลุดฐานแนวรับลงมา\"",
        ]) + [""]
    # alt text ใส่ตัวเลขระดับสำคัญ — ฟีดแบ็กหัวหน้า (เรื่องเล็ก) · เลขต้องมาจาก story
    alt_parts = [f"ภาพที่ 1 — โครงสร้างรอบใหญ่ {story['symbol']} รายวัน"]
    if zones:
        alt_parts.append(f"โซนรับ {money(zones[0]['mean'])}")
    if above:
        alt_parts.append(f"แนวต้านแรก {money(above[0])}")
    lines += [f"![{' · '.join(alt_parts)}]({first_image})", "",
              *RULE,
              _h2(H2_LEVELS), ""]

    sma50 = story["sma50_last"]
    sma_supports = sma50 is not None and story["current"]["close"] >= sma50
    if (zones or above or sma50 is not None) and not story.get("weekly_delta"):
        lines += ["จากข้อมูลที่ผ่านมา เมื่อราคาเคลื่อนมาใกล้บริเวณนี้ "
                  "มักชะลอตัวหรือเปลี่ยนทิศ "
                  "จึงใช้เป็นจุดสังเกตว่าครั้งนี้ตลาดจะเคลื่อนไหวอย่างไร", ""]
    # ประโยคปิดของแต่ละชั้นต่างกันตามหน้าที่ — ชั้นแรกคือด่านตัดสิน BOS
    # ชั้นที่เหลือเป็นเป้าตามลำดับ ⇒ ห้ามใช้ประโยคเดียวซ้ำทุกชั้น
    supply_notes = [
        "แนวต้านด่านแรก หากราคาสามารถปิดวันเหนือระดับนี้ได้ "
        "แรงซื้อจะเริ่มกลับมาได้เปรียบ",
        "แนวต้านลำดับถัดไปจากยอดเดิม",
        "แนวต้านที่ยังไม่ได้ทดสอบ",
    ]
    supply_items = [
        f"**แนวต้าน {order} ({money(price)} ดอลลาร์):** "
        f"{supply_notes[min(order - 1, len(supply_notes) - 1)]}"
        for order, price in enumerate(above[:3], 1)]
    if sma50 is not None and not sma_supports:
        supply_items.append(
            f"**แนวต้านจากเส้นค่าเฉลี่ย 50 วัน:** {money(sma50)} ดอลลาร์ — "
            "เส้นนี้ยังกดราคาอยู่ หากปิดวันเหนือเส้นได้ "
            "จะเป็นสัญญาณแรกว่าแรงซื้อเริ่มกลับมา")
    if False and supply_items:
        lines += [H3_SUPPLY, ""] + wcb_writers.listing("", supply_items) + [""]

    demand_groups = []
    if False and zones:
        # ใบตัวอย่างเรียง Supply ก่อน Demand (ไล่จากบนลงล่างตามที่ตาอ่านกราฟ)
        zone1 = zones[0]
        touch_line = (f"แนวรับนี้ถูกทดสอบมาแล้ว {zone1['touches']} ครั้ง "
                      + _memory_note(zone1, story))
        if zone1["includes_week52_low"]:
            touch_line += " ครอบจุดต่ำสุดในรอบ 52 สัปดาห์ไว้ในตัว"
        if story.get("weekly_delta"):
            direction_note = (
                "**เงื่อนไขสำคัญ:** หากแท่งรายวันปิดใต้ขอบล่างของโซน "
                + ("แนวโน้มขาลงจะยังดำเนินต่อ"
                   if down else "โครงสร้างขาขึ้นจะเสียและต้องประเมินทิศทางใหม่"))
            # บทบาทของโซนถูกอธิบายใต้ภาพรวมแล้ว ตรงนี้เก็บเฉพาะหลักฐานการแตะ
            # และเงื่อนไขเสียโครงสร้าง เพื่อไม่เล่าความหมายเดิมซ้ำสองหัวข้อ
            demand_notes = [touch_line.strip(), direction_note]
        else:
            demand_notes = [
                touch_line.strip(),
                "แนวรับที่ถูกทดสอบหลายครั้งอาจเหลือแรงซื้อน้อยลง "
                "การกลับมาครั้งถัดไปจึงต้องดูว่าราคายังยืนอยู่ได้หรือไม่",
                "**เงื่อนไขสำคัญ:** หากราคาลงมาแล้วยังรับอยู่ แนวนี้ยังทำงาน "
                "แต่หากแท่งรายวันปิดใต้แนวรับ แนวโน้มขาลงจะยังดำเนินต่อ",
            ]
        demand_groups.append((
            f"**แนวรับหลัก:** {money(zone1['low'])} – "
            f"{money(zone1['high'])} ดอลลาร์", demand_notes))
    if False and sma50 is not None and sma_supports:
        demand_groups.append((
            f"**แนวรับจากเส้นค่าเฉลี่ย 50 วัน:** {money(sma50)} ดอลลาร์",
            ["เส้นนี้ยังช่วยรองรับราคา หากราคาย้อนกลับมาปิดหลุดใต้เส้น "
             "จะเป็นสัญญาณเตือนว่าโมเมนตัมเริ่มกลับเข้าสู่ฝั่งขายอีกครั้ง"]))
    if False and demand_groups:
        lines += [H3_DEMAND, ""] + wcb_writers.nested_listing(demand_groups) + [""]
    if False and zones:
        if len(zones) > 1:
            zone2 = zones[1]
            note = (f"**แนวรับระยะยาวชั้นถัดไป: {money(zone2['low'])} – "
                    f"{money(zone2['high'])} ดอลลาร์** บริเวณนี้เป็นฐานราคาเดิม"
                    f"ที่ถูกทดสอบถึง {zone2['touches']} ครั้ง")
            if zone2["includes_week52_low"]:
                note += (" และเป็นจุดต่ำสุดในรอบ 52 สัปดาห์ "
                         "ซึ่งเป็นจุดทับซ้อนระหว่างแนวรับเชิงเทคนิคและแนวรับเชิงจิตวิทยา")
            if not zone2.get("daily_entry", True):
                note += (" (ระดับนี้เป็นกรอบระยะยาวหลายเดือน อยู่ห่างจากราคาปัจจุบันพอสมควร "
                         "จึงใช้ประกอบการมองโครงสร้างใหญ่เท่านั้น)")
            else:
                note += " เป็นแนวรับชั้นถัดไปหากราคาลงมาถึง"
            lines += [note, ""]
    if False and not zones and not above and sma50 is None:
        lines += ["หน้าต่างนี้ไม่มีระดับที่ผ่านเกณฑ์การแตะซ้ำของระบบ "
                  "จึงไม่มีระดับให้ระบุ และบทความจะไม่สร้างระดับขึ้นเองแทนครับ", ""]

    # ตารางระดับราคาเป็นแหล่งเดียวของแนวรับ/แนวต้านในบท — สร้างจาก story ทุกครั้ง
    lines += _level_table_markdown(story)

    # Scenario Planning ตามบรีฟฉบับ v2: เหลือเฉพาะ Trigger + Catalyst + Target
    # และผูก Catalyst กับ calendar evidence ก้อนเดียวกับภาพข่าวเสมอ
    up = story["scenarios"]["up"]
    down_scenario = story["scenarios"]["down"]
    lines += [*RULE, _h2(H2_SCENARIOS), ""]
    if up:
        bullish_items = [
            f"**เงื่อนไขทางเทคนิค:** ราคาปิดรายวันสูงกว่า "
            f"**{money(up['trigger'])} ดอลลาร์**",
            f"**ปัจจัยข่าวชี้นำ:** {_scenario_catalyst_text(story, 'up')}",
        ]
        if up["targets"]:
            targets = " และ ".join(f"**{money(value)}**" for value in up["targets"])
            bullish_items.append(f"**เป้าหมายราคา:** {targets} ดอลลาร์")
        else:
            bullish_items.append("**เป้าหมายราคา:** ยอดเดิมของโครงสร้างปัจจุบัน")
        lines += [H3_BULLISH, ""] + wcb_writers.listing("", bullish_items) + [""]
    if down_scenario:
        bearish_items = [
            f"**เงื่อนไขทางเทคนิค:** ราคาปิดรายวันต่ำกว่า "
            f"**{money(down_scenario['trigger'])} ดอลลาร์**",
            f"**ปัจจัยข่าวชี้นำ:** {_scenario_catalyst_text(story, 'down')}",
        ]
        if down_scenario["targets"]:
            targets = " และ ".join(
                f"**{money(value)}**" for value in down_scenario["targets"])
            bearish_items.append(f"**แนวรับถัดไป:** {targets} ดอลลาร์")
        else:
            bearish_items.append("**แนวรับถัดไป:** ยังไม่มีระดับที่ผ่านเกณฑ์ของระบบ")
        lines += [H3_BEARISH, ""] + wcb_writers.listing("", bearish_items) + [""]
    if not up and not down_scenario:
        lines += ["รอบนี้ไม่มีระดับที่ผ่านเกณฑ์พอจะตั้งเงื่อนไขได้ทั้งสองฝั่ง "
                  "จึงยังสรุปการเปลี่ยนโครงสร้างไม่ได้", ""]

    zoom_alt_parts = [f"ภาพที่ 2 — แผนที่ตัดสินใจ {story['symbol']}"]
    if up:
        zoom_alt_parts.append(f"เงื่อนไขฝั่งขึ้น {money(up['trigger'])}")
    lines += [f"![{' · '.join(zoom_alt_parts)}]({second_image})", ""]

    # ---- ปัจจัยพื้นฐานจากปฏิทินจริง — ฟีดแบ็กหัวหน้าข้อ 3 · มติผู้ใช้ 08-06 ดึก:
    # ใช้ปฏิทินเศรษฐกิจที่วัดได้แทนลิงก์ข่าว (โรงงานข่าวของเว็บยังไม่ต่อ) ·
    # ระบบไม่เดาเหตุผลย้อนหลัง — เขียนได้เฉพาะกำหนดการข้างหน้าที่มีในข้อมูลจริง
    calendar = story.get("calendar")
    if calendar and (isinstance(calendar.get("pages"), list)
                     or calendar.get("sentences")):
        week_start, week_end = calendar_week_bounds(story)
        image_names_for_calendar = calendar_image_names(story)
        lines += [*RULE, _h2(H2_CALENDAR), "",
                  f"ตารางนี้รวบรวมเหตุการณ์ตั้งแต่วันจันทร์ถึงวันศุกร์ "
                  f"({thai_date(week_start)} – {thai_date(week_end)}) "
                  f"โดยคัดเฉพาะรายการผลกระทบสูงและปานกลางที่เกี่ยวข้องกับ "
                  f"{story['symbol']} เวลาในตารางเป็นเวลาไทย", ""]
        if has_calendar_image(story):
            for page, name in enumerate(image_names_for_calendar, start=1):
                page_suffix = (f" หน้า {page} จาก {len(image_names_for_calendar)}"
                               if len(image_names_for_calendar) > 1 else "")
                alt = (f"ภาพปฏิทินเศรษฐกิจ {story['symbol']}"
                       f" สัปดาห์ {thai_date(week_start)} ถึง {thai_date(week_end)}{page_suffix}")
                lines += [f"![{alt}]({name})", ""]
        else:  # compatibility สำหรับ story artifact รุ่นก่อนมี pagination manifest
            sentences = calendar.get("sentences") or []
            lines += ["ด่านแรกคือ" + sentences[0]
                      + (" ต่อด้วย " + " ต่อด้วย ".join(sentences[1:])
                         if sentences[1:] else ""), ""]
        # วลีที่มา (กฎเหล็ก: ปัจจัยพื้นฐานต้องมีแหล่งอ้างอิงเสมอ — ของค้าง 08-09)
        # ⚠️ ฉบับใหม่ของผู้ใช้ไม่มีย่อหน้าปิด แต่วลีนี้เป็นด่าน fatal
        # (`calendar_source_missing`) จึงเหลือไว้เป็นบรรทัดสั้นที่สุดที่ยังผ่านด่าน
        lines += [CALENDAR_SOURCE_NOTE, ""]

    # ---- Weekly Executive Summary: กรอบกับ pivot ใช้ระดับเดียวกัน แต่ pivot ต้อง
    # อธิบายผลของการผ่าน/หลุดและเป้าหมายถัดไป เพื่อไม่ให้เป็นการพิมพ์เลขซ้ำเฉย ๆ ----
    lines += [*RULE, _h2(summary_heading(story)), ""]
    if down:
        direction_summary = (
            "ขาลง (Bearish) — ราคายังถูกกดจากแนวต้านด้านบน"
            "และเคลื่อนไหวใต้กรอบต้านสำคัญ")
    else:
        direction_summary = (
            "ขาขึ้น (Bullish) — ราคายังยกฐานสูงขึ้นและยืนเหนือกรอบรับสำคัญ")

    range_parts: list[str] = []
    if down_scenario:
        range_parts.append(f"แนวรับ **{money(down_scenario['trigger'])} ดอลลาร์**")
    if up:
        range_parts.append(f"แนวต้าน **{money(up['trigger'])} ดอลลาร์**")
    weekly_range = " | ".join(range_parts) or "ยังไม่มีระดับที่ผ่านเกณฑ์ของระบบ"

    pivot_details: list[str] = []
    if up:
        if up["targets"]:
            target_text = "–".join(money(value) for value in up["targets"][:2])
            if down:
                up_explanation = (
                    f"โครงสร้างขาลงเริ่มเสียเปรียบ เปิดทางทดสอบ "
                    f"**{target_text} ดอลลาร์**")
            else:
                up_explanation = (
                    f"ขาขึ้นได้เปรียบสมบูรณ์ มุ่งหน้าทดสอบ "
                    f"**{target_text} ดอลลาร์**")
        else:
            up_explanation = "เปิดทางกลับไปทดสอบยอดเดิมของโครงสร้างปัจจุบัน"
        pivot_details.append(
            f"**ผ่าน {money(up['trigger'])} ดอลลาร์:** {up_explanation}")
    if down_scenario:
        if down_scenario["targets"]:
            support_text = money(down_scenario["targets"][0])
            if down:
                down_explanation = (
                    f"ขาลงได้เปรียบต่อเนื่อง ถอยลงหาโซน "
                    f"**{support_text} ดอลลาร์**")
            else:
                down_explanation = (
                    f"เสียทรงขาขึ้น เข้าสู่การพักตัวระยะยาว ถอยลงหาโซน "
                    f"**{support_text} ดอลลาร์**")
        else:
            down_explanation = "โครงสร้างอ่อนแรงลง แต่ยังไม่มีแนวรับถัดไปที่ผ่านเกณฑ์"
        pivot_details.append(
            f"**หลุด {money(down_scenario['trigger'])} ดอลลาร์:** {down_explanation}")
    if not pivot_details:
        pivot_details.append("รอระดับยืนยันรอบถัดไป")

    summary_items = [
        f"**ทิศทางหลักสัปดาห์นี้:** {direction_summary}",
        f"**กรอบราคาประจำสัปดาห์:** {weekly_range}",
    ]
    lines += wcb_writers.listing("", summary_items)
    lines += wcb_writers.nested_listing([
        ("**จุดเปลี่ยนโมเมนตัม (Key Pivot):**", pivot_details),
    ])

    # ⚠️ ย่อหน้า "**คำเตือนความเสี่ยง:** …" ถูกถอด 2026-08-14 (ผู้ใช้สั่ง — เว็บมี
    # คำเตือนของตัวเองอยู่แล้ว บทจึงไม่ต้องพกซ้ำ) พร้อมด่าน `risk_disclaimer`
    # ที่เฝ้ามัน ⇒ **คำเตือนความเสี่ยงของสไตล์ D ตอนนี้ขึ้นกับเทมเพลตเว็บทั้งหมด**
    # ถ้าวันใดเว็บถอดของตัวเองออก บทจะไม่มีคำเตือนเลยและไม่มีอะไรฟ้อง
    # 🔴 สไตล์ D เป็นบทที่ขึ้นเว็บจริง (`web_style` ใน publishing_policy.json)
    #    ⇒ ผลกระทบตรงกับหน้าเผยแพร่ ไม่ใช่แค่แฟ้มภายใน
    lines += [_internal_links(story, profile), "", ""]
    return "\n".join(_indent_prose_lines(lines))


def _internal_links(story: dict, profile: dict) -> str:
    """S-2 (ฟีดแบ็กหัวหน้า 2026-08-07): บทไม่มี internal link เลยสักลิงก์

    ใช้เฉพาะที่อยู่ที่ยืนยันแล้วว่ามีจริง (`EXTERNAL.md` E5 — ทีมเว็บส่งมา 2026-08-06)
    **ห้ามใส่โดเมนเต็ม** เว็บยังเปลี่ยนที่อยู่หลักอยู่ · สอง URL นี้ = 2 ลิงก์ ต่ำกว่า
    เพดาน 5 ลิงก์ที่ระบบอนุญาต — ยังไม่เพิ่มลิงก์บทเมื่อวานเพราะ slug ของบทที่ขึ้นเว็บ
    จริงถูกกำหนดตอนอัปโหลด เราไม่รู้ล่วงหน้าว่าลิงก์คงที่แบบไหนถูกต้อง
    """
    tag = wcb_source.tag_for(story["asset"])
    return (f"ติดตามราคา{profile['short_name']}แบบเรียลไทม์ได้ที่ "
            f"[หน้าราคา{profile['short_name']}]"
            f"(/thailand/asset-{tag}) และดูบทวิเคราะห์ย้อนหลังทั้งหมดได้ที่ "
            "[คลังบทวิเคราะห์](/thailand/analysis)")


# ---------------------------------------------------------------- ด่านตรวจ

def allowed_numbers(story: dict) -> set[str]:
    """ทะเบียนเลขที่บทความมีสิทธิ์พูดถึง — สร้างจาก story เท่านั้น

    "15" มาจาก Timeframe ย่อย 1H/15M ใน Execution Plan (ศัพท์กรอบวิเคราะห์ ไม่ใช่ค่าที่วัด)
    "1"–"5" คือ**เลขลำดับหัวข้อ** ของโครงห้าหัวข้อตามใบตัวอย่าง 08-11 (ก่อนหน้านั้น
    หัวข้อไม่มีเลขลำดับ และ "4" ไม่เคยอยู่ในทะเบียน ⇒ หัวข้อ 4 ทำบทตกด่านตัวเองทันที)
    """
    money = money_for(story)
    allowed = {
        str(story["display"]["bars"]), str(story["display"]["zoom_bars"]),
        "1", "2", "3", "4", "5", "15", "50", "52", "200",
    }
    for token in _NUMBER.findall(publication_slug(story, kind="levels")):
        allowed.add(token.rstrip(".,"))
    prices = [story["current"]["close"], story["peak"]["high"], story["trough"]["low"],
              story["week52_low"]]
    for key in ("sma50_last", "sma200_last"):
        if story.get(key) is not None:
            prices.append(story[key])
    for level in story["resistance"]:
        prices.append(level["mean"])
        allowed.add(str(level["touches"]))
    for zone in story["zones"]:
        prices += [zone["mean"], zone["low"], zone["high"]]
        allowed.add(str(zone["touches"]))
    # จุดยกเลิกของจุดเข้าไม่เท่ากับขอบโซนอีกแล้วหลังปิด B-1 ⇒ เป็นราคาที่ต้องขึ้นทะเบียนเอง
    for entry in story.get("entries", []):
        prices.append(entry["invalidation"])
    channel = story["channel"]
    if channel:
        allowed.add(str(channel["touch_count"]))
        prices += [channel["main_at_last"], channel["parallel_at_last"]]
    for side in ("up", "down"):
        scenario = story["scenarios"][side]
        if scenario:
            prices += [scenario["trigger"], *scenario["targets"]]
            for key in ("entry_low", "entry_high", "entry_invalidation"):
                if scenario.get(key) is not None:
                    prices.append(scenario[key])
    weekly_delta = story.get("weekly_delta")
    if weekly_delta:
        for weekly_snapshot in (weekly_delta.get("current"), weekly_delta.get("previous")):
            if not weekly_snapshot:
                continue
            prices.append(weekly_snapshot["close"])
            for key in ("sma50", "sma200", "atr14"):
                if weekly_snapshot.get(key) is not None:
                    prices.append(weekly_snapshot[key])
            for zone in weekly_snapshot.get("zones") or []:
                prices += [zone["low"], zone["high"], zone["mean"]]
                allowed.add(str(zone["touches"]))
            for level in weekly_snapshot.get("resistance") or []:
                prices.append(level["mean"])
                allowed.add(str(level["touches"]))
        if weekly_delta.get("close_change") is not None:
            prices.append(abs(weekly_delta["close_change"]))
        if weekly_delta.get("close_change_pct") is not None:
            allowed.add(f"{abs(weekly_delta['close_change_pct']):.2f}")
        touches_change = weekly_delta.get("zone_touches_change")
        if touches_change:
            allowed.add(str(abs(touches_change)))
    headline_money = headline_price_for(story)
    for value in prices:
        allowed.add(money(value))
        # รูปแบบกระชับที่ใช้ในพาดหัว — ค่าเดียวกัน คนละการจัดรูป ไม่ใช่เลขใหม่
        allowed.add(headline_money(value))
    # ชื่อไฟล์ภาพมีวันที่เต็มรูป (เช่น 2026-08-06) — เลขเดือน/วันแบบมีศูนย์นำ
    # ไม่ตรงกับทะเบียนวันที่ปกติ ต้องเพิ่มจากชื่อไฟล์ตรง ๆ
    for name in image_names(story["asset"], story["current"]["date"]):
        for token in _NUMBER.findall(name):
            allowed.add(token.rstrip(".,"))
    calendar = story.get("calendar")
    if calendar and (isinstance(calendar.get("pages"), list)
                     or calendar.get("sentences")):
        for calendar_name in calendar_image_names(story):
            for token in _NUMBER.findall(calendar_name):
                allowed.add(token.rstrip(".,"))
    # ประโยคปฏิทินมาจาก evidence จริงผ่าน `_calendar_sentences` — เลขในประโยค
    # (เวลา น. / ค่าครั้งก่อน) เป็นส่วนหนึ่งของ story จึงเข้าทะเบียนทั้งชุด
    if calendar and (isinstance(calendar.get("pages"), list)
                     or calendar.get("sentences")):
        allowed.add(str(len(calendar.get("events") or [])))
        allowed.add(str(max(1, len(calendar.get("pages") or [[]]))))
        for sentence in calendar.get("sentences") or []:
            for token in _NUMBER.findall(sentence):
                allowed.add(token.rstrip(".,"))
        # Scenario Planning v2 ใช้ชื่อเหตุการณ์จากก้อน events โดยตรง แม้ artifact
        # compatibility บางรุ่นจะไม่มีประโยค sentences ที่พกชื่อเดียวกันมาด้วย
        for event in calendar.get("events") or []:
            for token in _NUMBER.findall(str(event.get("title") or "")):
                allowed.add(token.rstrip(".,"))
        for boundary in calendar_week_bounds(story):
            for token in _NUMBER.findall(thai_date(boundary)):
                allowed.add(token.rstrip(".,"))
    # วันเผยแพร่โผล่ในพาดหัวและ Title tag (มติ 08-14) ⇒ ต้องอยู่ในทะเบียนด้วย
    # ไม่ใช่แค่วันแท่งฐาน ไม่งั้นบททุกใบตกด่าน `number_not_in_story` ทุกวัน
    dates = [publish_date_of(story),
             story["current"]["date"], story["peak"]["date"], story["trough"]["date"],
             story["regime"]["flip_date"],
             story["display"]["start_date"], story["display"]["end_date"]]
    if channel:
        dates.append(channel["start_date"])
    dates += [zone["last_date"] for zone in story["zones"]]
    dates += [level["last_date"] for level in story["resistance"]]
    # วันล็อกของความจำข้ามวัน (#18ข) — โผล่ในวลี "โซนเดิมที่ใช้อ้างอิงมาตั้งแต่..."
    dates += [zone.get("locked_since") for zone in story["zones"]]
    dates += [level.get("locked_since") for level in story["resistance"]]
    if channel:
        dates.append(channel.get("locked_since"))
    for date_text in dates:
        if not date_text:
            continue
        year, _month, day = date_text.split("-")
        # ปีเดียวพอ — บท ชื่อไฟล์ภาพ และทะเบียนภายใน เป็น ค.ศ. ระบบเดียวกันหมด
        # ตั้งแต่ 08-11 (เดิมต้องขึ้นทะเบียนคู่ ค.ศ./พ.ศ. เพราะบทพิมพ์คนละระบบกับข้อมูล)
        allowed.add(year)
        allowed.add(str(int(day)))
    # ราคาปิดแบบปัดจำนวนเต็มที่ใช้เฉพาะในพาดหัว ("ทองยืน 4,342") — ค่าเดียวกับ
    # ราคาปิดจริง ไม่ใช่เลขใหม่ แต่รูปแบบต่างจาก money() จึงต้องขึ้นทะเบียนแยก
    allowed.add(f"{story['current']['close']:,.0f}")
    return allowed


def _levels_section(markdown: str) -> list[str]:
    lines = markdown.splitlines()
    try:
        start = next(i for i, line in enumerate(lines)
                     if line.strip() == _h2(H2_LEVELS))
    except StopIteration:
        return []
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith("## ")), len(lines))
    return lines[start + 1:end]


def _table_cells(line: str) -> list[str]:
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return []
    return [cell.strip().replace("\\|", "|")
            for cell in re.split(r"(?<!\\)\|", stripped[1:-1])]


def _level_table_findings(markdown: str, story: dict) -> list[dict]:
    """Validate the table contract independently from prose/number gates."""
    findings: list[dict] = []
    section = _levels_section(markdown)
    table_lines = [line for line in section if line.strip().startswith("|")]
    if H3_SUPPLY in section or H3_DEMAND in section:
        findings.append({"rule": "levels_table_contract", "severity": "fatal", "line": 1,
                         "message": "section ระดับราคาห้ามมี H3 แนวต้านด้านบน/แนวรับด้านล่างแบบเดิม"})
    expected_header = ["ระดับเทคนิค", f"กรอบราคา ({_quote_currency(story)})",
                       "ความสำคัญและบทบาททางเทคนิค"]
    header_indexes = [i for i, line in enumerate(table_lines)
                      if _table_cells(line) == expected_header]
    if len(header_indexes) != 1 or len(table_lines) < 2:
        findings.append({"rule": "levels_table_contract", "severity": "fatal", "line": 1,
                         "message": "section ระดับราคาต้องมีตารางเดียวและหัวตารางตรงสัญญา"})
        return findings
    header_index = header_indexes[0]
    if header_index != 0 or len(_table_cells(table_lines[header_index + 1])) != 3:
        findings.append({"rule": "levels_table_contract", "severity": "fatal", "line": 1,
                         "message": "ตารางระดับราคาต้องเริ่มด้วย header และ alignment row สามช่อง"})
        return findings
    if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in _table_cells(table_lines[1])):
        findings.append({"rule": "levels_table_contract", "severity": "fatal", "line": 1,
                         "message": "alignment row ของตารางระดับราคาไม่ถูกต้อง"})
    actual_rows = [_table_cells(line) for line in table_lines[2:]]
    for row in actual_rows:
        if len(row) != 3 or any(not cell for cell in row):
            findings.append({"rule": "levels_table_contract", "severity": "fatal", "line": 1,
                             "message": "ทุกแถวของตารางระดับราคาต้องมีสาม cell และไม่ว่าง"})
    if any(len(row) != 3 for row in actual_rows):
        return findings
    keys = [(row[0], row[1]) for row in actual_rows]
    if len(keys) != len(set(keys)) or len([row[0] for row in actual_rows]) != len(set(row[0] for row in actual_rows)):
        findings.append({"rule": "levels_table_duplicate", "severity": "fatal", "line": 1,
                         "message": "ตารางระดับราคามี label หรือช่วงราคาซ้ำ"})
    try:
        expected_rows = _level_table_rows(story)
        money = money_for(story)
        expected_pairs = []
        for row in expected_rows:
            price = (money(row["low"]) if row["low"] == row["high"]
                     else f"{money(row['low'])}–{money(row['high'])}")
            expected_pairs.append((row["label"], price))
    except (KeyError, TypeError, ValueError) as exc:
        findings.append({"rule": "levels_table_contract", "severity": "fatal", "line": 1,
                         "message": f"story ไม่พร้อมสร้างตารางระดับราคา: {exc}"})
        return findings
    actual_pairs = [(row[0], row[1]) for row in actual_rows]
    current_count = sum(1 for row in actual_rows if row[0] == "ราคาปัจจุบัน")
    if current_count != 1:
        findings.append({"rule": "levels_table_current", "severity": "fatal", "line": 1,
                         "message": "ตารางระดับราคาต้องมีแถวราคาปัจจุบัน exactly 1 แถว"})
    if actual_pairs != expected_pairs:
        if sorted(actual_pairs) == sorted(expected_pairs):
            findings.append({"rule": "levels_table_order", "severity": "fatal", "line": 1,
                             "message": "ลำดับตารางไม่ตรง: แนวต้านต้องไกล→ใกล้และแนวรับต้องใกล้→ไกล"})
        else:
            findings.append({"rule": "levels_table_duplicate", "severity": "fatal", "line": 1,
                             "message": "แถวในตารางไม่ตรงกับระดับที่สร้างจาก story"})
    current = float(story["current"]["close"])
    for row in actual_rows:
        if row[0].startswith("แนวต้าน"):
            value = _level_number(float(row[1].replace(",", "")), field="table.resistance")
            if value <= current:
                findings.append({"rule": "levels_table_side_conflict", "severity": "fatal", "line": 1,
                                 "message": "แนวต้านในตารางอยู่ไม่สูงกว่าราคาปัจจุบัน"})
        if row[0].startswith("แนวรับ"):
            values = [float(token.replace(",", "")) for token in re.findall(r"\d[\d,\.]*", row[1])]
            if values and min(values) > current:
                findings.append({"rule": "levels_table_side_conflict", "severity": "fatal", "line": 1,
                                 "message": "แนวรับในตารางอยู่เหนือราคาปัจจุบันทั้งช่วง"})
    return findings


def invalidation_pairs(story: dict) -> list[dict]:
    """ทุกคู่ (โซนเข้า ↔ จุดยกเลิกมุมมอง) ที่บทสไตล์ D พูดถึง — B-1

    **ต้องครบทุกคู่** ไม่ใช่เฉพาะคู่ที่เคยถูกฟ้อง · เพิ่มจุดเข้าแบบใหม่เมื่อไหร่
    ต้องมาต่อรายการที่นี่ด้วย ไม่งั้นด่านจะเงียบใส่คู่ใหม่แบบเดียวกับที่เกิดกับ
    "จุดเข้าซื้อ 1" รอบนี้
    """
    pairs = [{
        "label": f"จุดเข้าซื้อ {entry['rank']} (Demand Zone)",
        "zone_low": entry["zone_low"],
        "zone_high": entry["zone_high"],
        "invalidation": entry["invalidation"],
    } for entry in story.get("entries", [])]
    up = story["scenarios"].get("up")
    if up and up.get("entry_invalidation") is not None:
        pairs.append({
            "label": "จุดเข้าฝั่งขึ้น (Breakout-Continuation)",
            "zone_low": up["entry_low"],
            "zone_high": up["entry_high"],
            "invalidation": up["entry_invalidation"],
        })
    down = story["scenarios"].get("down")
    if down and down.get("entry_invalidation") is not None:
        pairs.append({
            "label": "จุดเข้าฝั่งลง (Breakdown-Continuation)",
            "zone_low": down["entry_low"],
            "zone_high": down["entry_high"],
            "invalidation": down["entry_invalidation"],
        })
    return pairs


def validate(markdown: str, story: dict) -> dict:
    """ด่านของสไตล์ D — fail-closed: findings ระดับ fatal ตัวเดียวก็ตก"""
    findings: list[dict] = []
    # ด่านความสอดคล้อง D-4.5 (ผู้ใช้เคาะ 08-10): ทิศ frontmatter=regime ·
    # ปี พ.ศ. ทั้งใบ · วันที่ Title=H1 — บทขัดกันเองต้องตกก่อนออกไฟล์
    findings.extend(consistency_gate.check(markdown, story))

    # สัญญาโครงสร้างตามต้นแบบ Style D ที่ผู้ใช้ยืนยัน 2026-08-25
    # ตรวจทั้งชื่อ ลำดับ และจำนวนหัวข้อ เพื่อป้องกันเทมเพลตเก่าย้อนกลับมาโดยไม่รู้ตัว
    calendar_block = story.get("calendar")
    has_calendar_section = bool(
        calendar_block and (isinstance(calendar_block.get("pages"), list)
                            or calendar_block.get("sentences")))
    expected_h2 = []
    if story.get("weekly_delta") and not story.get("verified_continuity_only"):
        expected_h2.append(H2_WEEKLY_DELTA)
    expected_h2.extend((H2_STRUCTURE, H2_LEVELS, H2_SCENARIOS))
    if has_calendar_section:
        expected_h2.append(H2_CALENDAR)
    expected_h2.append(H2_SUMMARY)
    actual_h2 = [line[3:].strip() for line in markdown.splitlines()
                 if line.startswith("## ")]
    if actual_h2 != expected_h2:
        findings.append({
            "rule": "heading_contract", "severity": "fatal", "line": 1,
            "message": ("ลำดับหัวข้อ Style D ไม่ตรงต้นแบบ — "
                        f"ต้องเป็น {expected_h2} แต่พบ {actual_h2}"),
        })
    # สัญญาบรรณาธิการ v2: ฉากทัศน์มีเพียง Trigger/Catalyst/Target และบทสรุป
    # เป็น weekly bulletin สามแกน ห้ามรูปแบบอธิบายผลลัพธ์ซ้ำย้อนกลับมา
    scenario_count = sum(
        bool(story["scenarios"].get(side)) for side in ("up", "down"))
    editorial_counts = {
        "**เงื่อนไขทางเทคนิค:**": scenario_count,
        "**ปัจจัยข่าวชี้นำ:**": scenario_count,
        "**เป้าหมายราคา:**": int(bool(story["scenarios"].get("up"))),
        "**แนวรับถัดไป:**": int(bool(story["scenarios"].get("down"))),
        "**ทิศทางหลักสัปดาห์นี้:**": 1,
        "**กรอบราคาประจำสัปดาห์:**": 1,
        "**จุดเปลี่ยนโมเมนตัม (Key Pivot):**": 1,
        "**ผ่าน ": int(bool(story["scenarios"].get("up"))),
        "**หลุด ": int(bool(story["scenarios"].get("down"))),
    }
    mismatched = {label: (markdown.count(label), expected)
                  for label, expected in editorial_counts.items()
                  if markdown.count(label) != expected}
    forbidden_editorial = [phrase for phrase in (
        "**ผลที่ต้องติดตาม:**", "**ผลลัพธ์ทางเทคนิค:**",
        "**เงื่อนไขฝั่งขึ้น:**", "**เงื่อนไขฝั่งลง:**",
    ) if phrase in markdown]
    if mismatched or forbidden_editorial:
        findings.append({
            "rule": "editorial_v2_contract", "severity": "fatal", "line": 1,
            "message": ("โครงเนื้อหา Style D ไม่ตรงบรีฟ v2 — "
                        f"จำนวนป้ายผิด {mismatched}; พบป้ายเก่า {forbidden_editorial}"),
        })
    try:
        findings.extend(_level_table_findings(markdown, story))
    except (KeyError, TypeError, ValueError) as exc:
        findings.append({
            "rule": "levels_table_contract", "severity": "fatal", "line": 1,
            "message": f"ตรวจตารางระดับราคาไม่ได้: {exc}",
        })
    for line_number, line in enumerate(markdown.splitlines(), start=1):
        if re.match(r"^#{2,3}\s+\d+[.)]?\s+", line):
            findings.append({
                "rule": "numbered_heading_forbidden", "severity": "fatal",
                "line": line_number,
                "message": "ต้นแบบ Style D ไม่ใช้เลขนำหน้าหัวข้อ",
            })
        if any(mark in line for mark in ("🟢", "🟡", "🔴", "✅", "⚠", "📌", "📈", "📉")):
            findings.append({
                "rule": "emoji_forbidden", "severity": "fatal", "line": line_number,
                "message": "ต้นแบบ Style D ไม่ใช้อีโมจิในเนื้อหาบทความ",
            })
        if any(mark in line for mark in ("➔", "→", "➡")):
            findings.append({
                "rule": "arrow_forbidden", "severity": "fatal", "line": line_number,
                "message": "สรุปรายสัปดาห์ของ Style D ใช้ข้อความอธิบายแทนลูกศร",
            })
    if story["regime"]["down"]:
        contradictions = ("ภาพรายวันยังอยู่ในแนวโน้มขาขึ้น",
                          "ยังรักษาโครงสร้างขาขึ้นไว้ได้")
    else:
        contradictions = ("ภาพรายวันยังมีโครงสร้างหลักเป็นขาลง",
                          "มุมมองขาลงเดิมยังไม่เปลี่ยน",
                          "ยังอยู่ในกรอบขาลง")
    for phrase in contradictions:
        if phrase in markdown:
            findings.append({
                "rule": "direction_language_conflict", "severity": "fatal", "line": 1,
                "message": f"ข้อความ '{phrase}' ขัดกับ regime ของ Style D รอบนี้",
            })
    expected_slug = publication_slug(story, kind="levels")
    if not re.search(rf"(?m)^slug:\s*{re.escape(expected_slug)}\s*$", markdown):
        findings.append({
            "rule": "slug_invalid", "severity": "fatal", "line": 1,
            "message": f"Style D ต้องใช้ slug: {expected_slug}",
        })
    expected_public_asset = web_frontmatter_contract.public_asset_tag(story["asset"])
    if not re.search(rf"(?m)^asset:\s*{re.escape(expected_public_asset)}\s*$", markdown):
        findings.append({
            "rule": "public_asset_invalid", "severity": "fatal", "line": 1,
            "message": ("frontmatter asset ของ Style D ต้องเป็น "
                        f"{expected_public_asset} สำหรับ internal asset {story['asset']}"),
        })
    allowed = allowed_numbers(story)
    for line_number, line in enumerate(markdown.splitlines(), start=1):
        for token in _NUMBER.findall(line):
            token = token.rstrip(".,")
            if token and token not in allowed:
                findings.append({
                    "rule": "number_not_in_story", "severity": "fatal", "line": line_number,
                    "message": f"เลข '{token}' ไม่อยู่ในทะเบียนของ story — "
                               "บทสไตล์ D พูดได้เฉพาะเลขที่อยู่บนภาพ",
                })
    required_images = list(image_names(story["asset"], story["current"]["date"]))
    if has_calendar_image(story):
        required_images.extend(calendar_image_names(story))
    for name in required_images:
        if f"({name})" not in markdown:
            findings.append({
                "rule": "missing_image", "severity": "fatal", "line": 1,
                "message": f"บทความไม่ได้อ้างภาพ {name} — สไตล์ D ต้องอ้างภาพที่ใช้ให้ครบ",
            })
    # ด่าน `entry_section` (บังคับให้บทมีหัวข้อจุดเข้าซื้อเมื่อ story คำนวณได้) ถูกถอด
    # 2026-08-14 พร้อมกับบล็อกที่มันเฝ้า — ผู้ใช้สั่งถอดหัวข้อนั้นออกจากบท
    # ด่าน `risk_disclaimer` ถูกถอด 2026-08-14 พร้อมย่อหน้าที่มันเฝ้า (ผู้ใช้สั่ง —
    # เว็บมีคำเตือนของตัวเองแล้ว) ⚠️ เอาย่อหน้ากลับเมื่อไหร่ ต้องเอาด่านกลับด้วย
    # ไม่งั้นย่อหน้าหายเงียบได้โดยไม่มีอะไรฟ้อง — เหตุผลเดิมที่ตั้งด่านไว้ตั้งแต่แรก
    # (บทเรียนเดียวกับด่าน `entry_section` ที่ถอดไปเมื่อต้นวันเดียวกัน)
    # 🔄 **กลับด้าน 2026-08-10** — เดิมห้ามมี frontmatter · ตอนนี้ **บังคับให้มี**
    # เพราะทุกสไตล์ต้องส่ง `title` เอง (คำสั่งผู้ใช้ + ทีมเว็บแนะนำให้ส่งเองมาแต่แรก)
    if not markdown.lstrip().startswith("---"):
        findings.append({
            "rule": "frontmatter_required", "severity": "fatal", "line": 1,
            "message": "บทสไตล์ D ต้องมี frontmatter พร้อมช่อง title",
        })
    elif not re.search(r"(?m)^title:\s*\S", markdown):
        findings.append({
            "rule": "frontmatter_required", "severity": "fatal", "line": 1,
            "message": "frontmatter ไม่มีช่อง title",
        })
    # สเปก SEO ของหัวหน้า 2026-08-10: Title tag กับ H1 **ต้องไม่เหมือนกัน** —
    # คนละหน้าที่ (Title = ช่องคำค้น ต้องนิ่ง · H1 = ช่องเล่าสาระของวัน)
    # เขียนชนกันเมื่อไหร่บทไม่ออก ไม่ใช่ออกไปแล้วค่อยรู้ตอนขึ้นเว็บ
    first_line = next((line for line in markdown.splitlines() if line.startswith("# ")), "")
    if first_line and headline_format.same_headline(seo_title(story), first_line[2:]):
        findings.append({
            "rule": "title_equals_h1", "severity": "fatal", "line": 1,
            "message": "Title tag กับ H1 เหมือนกัน — สเปก SEO บังคับให้หางต่างกัน",
        })
    # กฎเหล็ก: ปัจจัยพื้นฐานต้องมีแหล่งอ้างอิงเสมอ — มีย่อหน้าปฏิทินแล้วไม่มีวลีที่มา = ตก
    if calendar_block and (isinstance(calendar_block.get("pages"), list)
                           or calendar_block.get("sentences")) \
            and CALENDAR_SOURCE_NOTE.strip() not in markdown:
        findings.append({
            "rule": "calendar_source_missing", "severity": "fatal", "line": 1,
            "message": "ย่อหน้าปัจจัยพื้นฐานยกตัวเลขจากปฏิทินแต่ไม่มีวลีบอกแหล่ง "
                       f"'{CALENDAR_SOURCE_NOTE.strip()}' — ต้องมีเหมือนสไตล์ A/B/C",
        })
    # 🐞 **A-1 (ทีมเว็บ 2026-08-09) — ด่านที่ผูกคำว่า "ปิด" เข้ากับสภาพจริงของแท่ง**
    # บททุกใบของสไตล์นี้เขียน "แท่งล่าสุดปิดที่ X" ⇒ ถ้าพิสูจน์ไม่ได้ว่าแท่งฐานปิดแล้ว
    # **บทตกด่าน ไม่ออกไฟล์** ไม่มีทางเลือก "ปล่อยผ่านพร้อมป้ายเตือน" เพราะป้ายเตือน
    # ไม่ได้ทำให้ตัวเลขในบทตรงกับกราฟบนหน้าเดียวกัน ซึ่งคือปัญหาที่แท้จริง
    # ด่านนี้**ไม่อ่านธง** `current.candle_state` มาตัดสิน แต่ให้ `candle_close.verify()`
    # ไล่คำนวณเวลาปิดจาก `config/market_calendar.json` ใหม่แล้วเทียบนาฬิกาจริงตอนตรวจ
    closed_detail = candle_close.verify(
        story.get("candle_basis"), asset=story["asset"],
        session_date=story["current"]["date"])
    if closed_detail:
        findings.append({
            "rule": "closed_candle_required", "severity": "fatal", "line": 1,
            "message": f"บทเรียกราคาแท่งล่าสุดว่า 'ปิด' แต่ {closed_detail}",
        })

    # 🐞 D-1 (08-07) → **B-1 (08-09): เดิมด่านนี้ตรวจคู่เดียว (โซน Retest ฝั่งขึ้น)**
    # ทีมเว็บจึงเจอ "จุดเข้าซื้อ 1" ที่จุดยกเลิกเท่ากับขอบล่างโซนเป๊ะหลุดออกไปได้
    # ⇒ ตอนนี้กวาด**ทุกคู่ในบท** ผ่านเกณฑ์กลางตัวเดียว (`chart_story.MIN_INVALIDATION_ATR`)
    # บทเรียนที่เกิดซ้ำในโปรเจกต์นี้: แก้เฉพาะตัวที่ฟ้องอย่างเดียวไม่พอ ต้องกวาดทั้งไฟล์
    for message in chart_story.invalidation_findings(
            invalidation_pairs(story), story["atr14"]):
        findings.append({
            "rule": "invalidation_inside_entry_zone", "severity": "fatal", "line": 1,
            "message": message,
        })

    # 🐞 **B-3.1 (08-09):** จำนวนครั้งที่บทอ้างต้องนับจากจุดที่อยู่ในโซนที่บทตีพิมพ์จริง
    # — เคยนับจากกลุ่มที่กว้างกว่าโซน 2 เท่า ทำให้บทอ้าง 7 ครั้งแต่ในโซนมีจริง 5 ครั้ง
    for zone in story["zones"]:
        touch_prices = zone.get("touch_prices")
        if touch_prices is None:
            findings.append({
                "rule": "zone_touch_evidence_missing", "severity": "fatal", "line": 1,
                "message": f"โซน {zone['mean']} ไม่มีรายการราคาที่ใช้นับจำนวนครั้ง "
                           "— ตัวเลข 'ถูกใช้อ้างอิง N ครั้ง' ต้องชี้กลับจุดจริงได้",
            })
            continue
        outside = [value for value in touch_prices
                   if not zone["low"] <= value <= zone["high"]]
        if outside or len(touch_prices) != zone["touches"]:
            findings.append({
                "rule": "zone_touch_count_mismatch", "severity": "fatal", "line": 1,
                "message": f"โซน {zone['low']}–{zone['high']} อ้างว่าถูกแตะ {zone['touches']} ครั้ง "
                           f"แต่มีจุดนอกโซน {len(outside)} จุด — บทพูดเกินสิ่งที่วัดได้",
            })
    char_count = len(re.sub(r"\s", "", markdown))
    if char_count < MIN_CHARS:
        findings.append({
            "rule": "style_length_floor", "severity": "fatal", "line": 1,
            "message": f"เนื้อหามี {char_count} อักขระ ต่ำกว่าเกณฑ์ {MIN_CHARS} ของสไตล์ D",
        })
    fatal_count = sum(1 for finding in findings if finding["severity"] == "fatal")
    return {
        "status": "pass" if fatal_count == 0 else "fail",
        "fatal_count": fatal_count,
        "char_count": char_count,
        "findings": findings,
    }
