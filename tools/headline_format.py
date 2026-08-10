"""รูปแบบพาดหัวและวันที่ไทย — **แหล่งเดียวของทั้งระบบ** (สเปก SEO ของหัวหน้า 2026-08-10)

เดิมรูปแบบวันที่กระจายอยู่สามที่ (`chart_renderer` · `wcb_writers` · `chart_story_renderer`)
และ Title tag เคยถูกพิมพ์มือลงจดหมาย ⇒ เพี้ยนจาก H1 โดยไม่มีอะไรจับ (ข้อ B-3.3 ที่ทีมเว็บ
ตีกลับ 08-09) · โมดูลนี้รวมทั้งสองเรื่องไว้จุดเดียวเพื่อไม่ให้เกิดซ้ำ

## สัญญารูปแบบ (คำสั่งหัวหน้าผ่านผู้ใช้ 2026-08-10 — ห้ามแก้เองโดยไม่ผ่านผู้ใช้)

    Title : วิเคราะห์ทองคำวันนี้ 6 สิงหาคม 2569 — แนวโน้มราคาทอง XAU/USD
    H1    : วิเคราะห์ทองคำวันนี้ 6 ส.ค. 2569 — ทองยืน 4,262 รอ Fed ชี้ทาง
            └──── คงที่ ────┘ └── ตามวันจริง ──┘   └──── ปรับตามเนื้อหา ────┘

สามส่วน:

1. **`วิเคราะห์<ชื่อสินทรัพย์>วันนี้`** — คงที่ ห้ามเปลี่ยนถ้อยคำ · ชื่อสินทรัพย์มาจากช่อง
   `seo_name` ในทะเบียน (ไม่ใช่ `thai_name` ซึ่งยาวกว่าและเขียนเพื่ออ่านในเนื้อบท —
   `thai_name` ของทองคือ "ทองคำโลก" แต่คนไทยค้นคำว่า "ทองคำ")
2. **วันที่** — Title ใช้**เดือนเต็ม** · H1 ใช้**เดือนย่อ** (ต่างกันตามตัวอย่างที่หัวหน้าให้มา)
3. **หางหลัง `—`** — ปรับตามเนื้อหาได้ แต่ **Title กับ H1 ต้องไม่เหมือนกัน**
   (บังคับด้วยด่าน `title_equals_h1` ในตัวตรวจของสไตล์ D/E)

⚠️ **หางของ Title เป็นค่าคงที่ต่อสินทรัพย์โดยเจตนา** — Title tag คือช่องคำค้น ควรนิ่ง
และมีคำที่คนค้นจริง · ส่วน H1 เป็นช่องเล่าสาระของวันนั้น จึงผูกกับราคา/เหตุการณ์ได้
สลับหน้าที่กันเมื่อไหร่ SEO เสียทั้งคู่: Title ที่เปลี่ยนทุกวันจัดอันดับไม่ติด และ H1
ที่คงที่ไม่บอกอะไรคนอ่าน

## ปี พ.ศ.

ตัวอย่างที่หัวหน้าให้มาใช้ **พ.ศ.** และผู้ใช้ตัดสิน 2026-08-10 ว่า **เปลี่ยนทั้งบท**
ไม่ใช่เฉพาะพาดหัว — เพราะพาดหัวเขียน 2569 แต่ย่อหน้าแรกกับหัวกราฟเขียน 2026
คือบทที่ขัดกันเองในหน้าเดียว ซึ่งเป็นอาการที่ทีมเว็บตีกลับมาแล้ว (D-4.5)

⚠️ **ทะเบียนวันที่ภายในยังเป็น ค.ศ. ทั้งหมด** (`story["current"]["date"]` = `"2026-08-07"`)
แปลงเป็น พ.ศ. **เฉพาะตอนพิมพ์ออกเป็นข้อความ** เท่านั้น — ห้ามแปลงในชั้นข้อมูล ไม่งั้น
การเทียบวันกับก้อนข้อมูลจริงพังทั้งระบบ · ชื่อไฟล์ภาพก็ยังเป็น ค.ศ. ตามเดิม
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import wcb_source  # noqa: E402

BUDDHIST_OFFSET = 543

MONTH_ABBR = ("ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
              "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.")
MONTH_FULL = ("มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
              "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม")

PREFIX_TEMPLATE = "วิเคราะห์{name}วันนี้"
SEPARATOR = " — "

# เพดานที่ใช้ **ตอนเทส** ไม่ใช่ตอนรัน — Title tag ที่ยาวเกินนี้ถูก Google ตัดกลางคัน
# ทำให้คำท้ายที่ตั้งใจใส่หายไป · ไม่ทำเป็นด่าน fail-closed เพราะหางเป็นค่าคงที่ในทะเบียน
# อยู่แล้ว (ควบคุมได้ตั้งแต่ตอนเขียน) การให้บทตกตอนรันด้วยเรื่องความยาวพาดหัวคือ
# การแลกของที่ผิด — เทสจับตอน commit ทันเสมอ
SEO_TITLE_BUDGET = 70


def buddhist_year(year: int | str) -> int:
    return int(year) + BUDDHIST_OFFSET


def thai_date(date_text: str, *, full_month: bool = False) -> str:
    """'2026-08-06' → '6 ส.ค. 2569' (หรือ '6 สิงหาคม 2569' เมื่อ full_month)

    ใช้ทั้งบนภาพและในบททุกสไตล์ ให้สะกดตรงกันหมด
    """
    year, month, day = date_text.split("-")
    table = MONTH_FULL if full_month else MONTH_ABBR
    return f"{int(day)} {table[int(month) - 1]} {buddhist_year(year)}"


def seo_name(asset: str) -> str:
    """คำเรียกสินทรัพย์ที่ใช้ในพาดหัว — คนละช่องกับ `thai_name` ที่ใช้ในเนื้อบท"""
    profile = wcb_source.profile_for(asset)
    return profile.get("seo_name") or profile["thai_name"]


def seo_tail(asset: str) -> str:
    """หางคงที่ของ Title tag ต่อสินทรัพย์ — ช่องคำค้น ต้องนิ่ง"""
    profile = wcb_source.profile_for(asset)
    return profile.get("seo_tail") or f"แนวโน้มราคา {profile['symbol']}"


def prefix(asset: str, date_text: str, *, full_month: bool) -> str:
    """ส่วนหน้าที่ทุกสไตล์ใช้ร่วมกัน — จุดเดียวที่ประกอบ ชื่อ + คำว่า 'วันนี้' + วันที่"""
    return (PREFIX_TEMPLATE.format(name=seo_name(asset))
            + " " + thai_date(date_text, full_month=full_month))


def build(asset: str, date_text: str, tail: str, *, full_month: bool) -> str:
    """ประกอบพาดหัวเต็มรูป — ตัวเดียวที่ต่อ `—` ให้ทั้งระบบ"""
    return prefix(asset, date_text, full_month=full_month) + SEPARATOR + str(tail).strip()


def title(asset: str, date_text: str, tail: str | None = None) -> str:
    """Title tag — เดือนเต็ม · หางคงที่ตามทะเบียน เว้นแต่ผู้เรียกส่งหางของสไตล์มาเอง"""
    return build(asset, date_text, tail or seo_tail(asset), full_month=True)


def h1(asset: str, date_text: str, tail: str) -> str:
    """พาดหัวในบท — เดือนย่อ · หางเล่าสาระของวันนั้น"""
    return build(asset, date_text, tail, full_month=False)


def same_headline(title_text: str, h1_text: str) -> bool:
    """Title กับ H1 ซ้ำกันไหม — เทียบแบบไม่สนช่องว่างส่วนเกิน

    เงื่อนไขของหัวหน้า: สองอันต้องไม่เหมือนกัน · ตัวที่เรียกใช้จริงคือด่านของสไตล์ D/E
    (`title_equals_h1`) ⇒ เขียนหางชนกันเมื่อไหร่ บทไม่ออก ไม่ใช่ออกไปแล้วค่อยรู้ทีหลัง
    """
    return " ".join(title_text.split()) == " ".join(h1_text.split())
