"""ระยะ 1 — บทรายเหตุการณ์: เล่าว่า "ตัวเลขออกมาที่เท่าไหร่เทียบกับที่คาด"

**ขอบเขตที่ตั้งใจแคบ และห้ามขยายเองโดยไม่ผ่านผู้ใช้:**

    ทำ        รายงานค่าที่ประกาศ เทียบกับค่าคาดและค่าครั้งก่อน + สภาพราคาที่บันทึก
              ไว้ในก้อนข้อมูลเดียวกัน
    ไม่ทำ     บอกว่าตัวเลขนี้จะพาราคาไปทางไหน · แนะนำจุดเข้าออก · ตีความเชิงนโยบาย

การชี้ทิศคือระยะ 3b (`RL-006`) ซึ่ง **ผู้ใช้ยังไม่เคาะกติกา** — ห้ามเปิดเอง
บทนี้ยังเป็น **ต้นแบบภายใน** เขียนลง `work/` เท่านั้น ห้ามวางในโฟลเดอร์เผยแพร่

**กติกาตัวเลขเดียวกับสายรายวันทุกข้อ:** ยกค่าจากก้อนตรง ๆ · ห้ามคำนวณส่วนต่างเอง
(บอกว่าสูงกว่า/ต่ำกว่าได้ เพราะเป็นการเปรียบเทียบ ไม่ใช่เลขตัวใหม่ — แต่ **ห้ามพิมพ์
ผลลบ**) · ห้ามแปลงหน่วย · ค่าที่อ่านไม่ออกให้เงียบ ไม่ใช่เดา
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import wcb_writers  # noqa: E402

# สัญลักษณ์ที่ต้นทางติดมากับค่า — ใช้ **แค่ตัดสินว่าอ่านเป็นตัวเลขได้ไหม**
# ไม่ได้ใช้แปลงหน่วย และไม่ถูกพิมพ์ซ้ำเป็นคำ (ค่าดิบถูกพิมพ์ทั้งก้อนอยู่แล้ว)
_STRIP = str.maketrans("", "", "€$£¥%, ")
_HAS_UNIT_MARK = re.compile(r"[€$£¥%]")

# ชื่อประเทศ/เขตเศรษฐกิจเป็นภาษาคน — **จงใจไม่มีค่าตั้งต้น** ตามหลักเดียวกับ
# `wcb_writers._thai_code`: รหัสที่ไม่รู้จักต้องหยุดให้เห็น ไม่ใช่ปล่อย "ของEUR"
# ขึ้นบทเงียบ ๆ (เกิดจริงในบทใบแรกที่ผลิต 2026-08-07)
COUNTRY_THAI = {"USD": "สหรัฐ", "EUR": "ยูโรโซน", "GBP": "อังกฤษ", "CNY": "จีน",
                "CAD": "แคนาดา", "JPY": "ญี่ปุ่น", "AUD": "ออสเตรเลีย", "NZD": "นิวซีแลนด์",
                "CHF": "สวิตเซอร์แลนด์"}


def country_thai(code) -> str:
    try:
        return COUNTRY_THAI[code]
    except KeyError:
        raise ValueError(f"ประเทศที่ยังไม่มีชื่อไทยในทะเบียน: {code!r} "
                         "— เติมใน COUNTRY_THAI ก่อน อย่าปล่อยรหัสดิบขึ้นบท") from None


def as_number(raw):
    """อ่านค่าปฏิทินเป็นตัวเลข — คืน None เมื่ออ่านไม่ออก **ห้ามเดาแทน**

    ต้นทางส่งค่ามาเป็นข้อความติดสัญลักษณ์ เช่น `"80"` `"4.2%"` `"€15.4"` `"$112.5"`
    `"-0.4%"` · รูปแบบใหม่ที่ยังไม่เคยเห็นต้องตกมาที่ None แล้วบทจะเงียบเรื่อง
    การเปรียบเทียบไปเลย ดีกว่าเปรียบเทียบผิดทาง
    """
    if raw in (None, ""):
        return None
    try:
        return float(str(raw).translate(_STRIP))
    except ValueError:
        return None


def comparison(actual, other) -> str:
    """คำเปรียบเทียบสองค่า — ค่าว่างหรืออ่านไม่ออก = คืนค่าว่างให้ผู้เรียกตัดวลีทิ้ง"""
    left, right = as_number(actual), as_number(other)
    if left is None or right is None:
        return ""
    if left > right:
        return "สูงกว่า"
    if left < right:
        return "ต่ำกว่า"
    return "เท่ากับ"


def has_unit(raw) -> bool:
    """ค่ามีหน่วยกำกับมาด้วยไหม (`4.2%` มี · `80` ไม่มี)

    ผูกกับ **E9** ที่ยังค้างกับทีมเว็บ — ปฏิทินส่ง 7 ช่องและไม่มีช่องหน่วย
    ค่าที่ติดสัญลักษณ์มาเองจึงเป็นหน่วยเดียวที่เรามีสิทธิ์เขียน **ห้ามเติมคำว่า
    "พันตำแหน่ง" หรือ "พันล้าน" เอง** แม้จะเดาถูกก็ตาม เพราะเป็นเลขที่ไม่มีต้นทาง
    """
    return bool(_HAS_UNIT_MARK.search(str(raw or "")))


def headline(event: dict) -> str:
    """พาดหัว — ตัดตามเพดานเดียวกับสายเว็บเพื่อให้ย้ายไปใช้จริงได้โดยไม่ต้องแก้"""
    title = f"{event['title']}ของ{country_thai(event.get('country'))} ประกาศที่ {event['actual']}"
    if event.get("forecast") not in (None, ""):
        word = comparison(event["actual"], event["forecast"])
        title += f" {word}ที่ตลาดคาด" if word else f" ตลาดคาดไว้ที่ {event['forecast']}"
    return title[:wcb_writers.TITLE_MAX]


def _released_sentence(event: dict) -> str:
    """ประโยครายงานค่าที่ประกาศ — **ต้องมีวันที่จริง ห้ามอ้างเวลาแบบสัมพัทธ์**

    เดิมขึ้นต้นว่า "เมื่อเวลา 19:30 น." เฉย ๆ ซึ่งอ่านวันที่เผยแพร่แล้วเข้าใจตรง แต่บท
    ถูกเก็บถาวรและอ่านย้อนหลังได้ ⇒ วันรุ่งขึ้นก็ไม่รู้แล้วว่า 19:30 น. ของวันไหน
    (เหตุผลเดียวกับที่ `wcb_writers.when()` เลิกใช้ "คืนนี้" · ทีมเว็บข้อ A-3 2026-08-09)

    ทั้งวันที่และเวลามาจากฟิลด์ `at` ของรายการเดียวกัน จึงชี้กลับหลักฐานได้ตรง
    · `at` ที่อ่านไม่ออก = ตัดวลีวันที่ทิ้งทั้งวลี ไม่ใช่พิมพ์ค้างไว้ครึ่งเดียว
    """
    stamp = wcb_writers.date_thai(event["at"])
    hhmm = wcb_writers.clock(event["at"])
    moment = " ".join(part for part in
                      (f"เมื่อวัน{stamp}" if stamp else "", f"เวลา {hhmm} น." if hhmm else "")
                      if part)
    text = ((f"{moment} ตามเวลาไทย " if moment else "") +
            f"{event['title']}ของ{country_thai(event.get('country'))}")
    if event.get("impact") == "High":
        text += " ซึ่งจัดเป็นรายการผลกระทบสูง"
    text += f" ประกาศออกมาที่ {event['actual']}"

    forecast, previous = event.get("forecast"), event.get("previous")
    if forecast not in (None, ""):
        word = comparison(event["actual"], forecast)
        text += (f" {word}ที่ตลาดคาดไว้ที่ {forecast}" if word
                 else f" ขณะที่ตลาดคาดไว้ที่ {forecast}")
    if previous not in (None, ""):
        word = comparison(event["actual"], previous)
        text += (f" และ{word}ครั้งก่อนที่อยู่ที่ {previous}" if word
                 else f" และครั้งก่อนอยู่ที่ {previous}")
    return text + " (ที่มา: ปฏิทินเศรษฐกิจ WorldClassBroker)"


def _unit_caveat(event: dict) -> str:
    """คำกำกับหน่วย — คำนวณจากค่าจริงทุกรอบ ไม่เขียนตายตัว

    บทเรียน `_forecast_caveat` (บั๊ก 2026-08-07): คำกำกับที่บรรยายสภาพของข้อมูล
    ถ้าเขียนตายตัวจะขัดกับประโยคของตัวเองทันทีที่ปลายทางเปลี่ยน ⇒ ถ้า E9 ปิดเมื่อไหร่
    และค่ามีหน่วยติดมาครบ ประโยคนี้จะหายไปเองโดยไม่ต้องแก้โค้ด
    """
    bare = [str(v) for v in (event.get("actual"), event.get("forecast"), event.get("previous"))
            if v not in (None, "") and not has_unit(v)]
    if not bare:
        return ""
    return ("ปฏิทินส่งค่าชุดนี้มาเป็นตัวเลขเปล่าโดยไม่มีช่องบอกหน่วย "
            "บทจึงเขียนตามที่ต้นทางส่งมาทั้งก้อน การเติมหน่วยเองคือการสร้างข้อมูลที่ไม่มีต้นทาง")


def render(event: dict, evidence: dict) -> str:
    """ประกอบบทหนึ่งใบ — หนึ่งรายการประกาศ ต่อ หนึ่งสินทรัพย์

    `event` ต้องเป็นแถวจากปฏิทินของ **ก้อนเดียวกับ `evidence`** เท่านั้น
    (ค่า `previous` ถูกทบทวนย้อนหลังภายในวันเดียวกันได้จริง — เห็นมาแล้ว 08-07)
    """
    if event.get("actual") in (None, ""):
        raise ValueError(f"รายการยังไม่ประกาศ เขียนบทรายเหตุการณ์ไม่ได้: {event.get('title')!r}")

    profile = wcb_writers.profile_of(evidence)
    lines = ["---",
             f"asset: {evidence['asset']}",
             f"title: {headline(event)}",
             f"excerpt: {event['title']} ออกมาที่ {event['actual']} "
             f"รายงานคู่กับสภาพราคา{profile['short_name']}ในก้อนข้อมูลเดียวกัน",
             "kind: event-report",
             "status: ต้นแบบภายใน ยังไม่เผยแพร่",
             "---", "",
             "## ตัวเลขที่ประกาศ", "",
             _released_sentence(event), ""]

    caveat = _unit_caveat(event)
    if caveat:
        lines += [caveat, ""]

    lines += [f"## ราคา{profile['short_name']} ณ ก้อนข้อมูลเดียวกัน", "",
              wcb_writers._opening(evidence) +
              " ตัวเลขราคาชุดนี้คือสภาพที่บันทึกไว้ในก้อนข้อมูลรอบเดียวกับค่าที่ประกาศ "
              "ไม่ใช่ราคาหลังตลาดย่อยข่าวเสร็จแล้ว", "",
              "## ขอบเขตของบทนี้", "",
              "บทนี้รายงานสองอย่างเท่านั้นคือค่าที่ปฏิทินประกาศ และสภาพราคาที่บันทึกไว้ในก้อนเดียวกัน "
              "ยังไม่สรุปว่าตัวเลขนี้จะพาราคาไปทางไหน เพราะการชี้ทิศต้องมีกติกาที่ตรวจย้อนกลับได้ก่อน "
              "และกติกานั้นยังไม่ถูกกำหนด", ""]
    return "\n".join(lines)
