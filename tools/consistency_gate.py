"""ด่านความสอดคล้อง D-4.5 — จับ "บทขัดกันเอง" ก่อนไฟล์ออกจากโรงงาน

ที่มา: ทีมเว็บเคยตีกลับบทที่พาดหัวทิศหนึ่งเนื้ออีกทิศ/ปีปนกัน (รหัส D-4.5)
หลังเส้นแบ่งงานใหม่ 08-09 ไม่มีตาข่ายฝั่งเว็บแล้ว — ด่านนี้คือตัวแทนฝั่งเรา
(ผู้ใช้เคาะ 08-10: ทำทั้งบีบต้นทางและด่านท้าย fail-closed)

กฎทุกตัวเป็น fatal — ผิดข้อเดียวตกทั้งใบ ไม่ออกไฟล์ ตามมาตรฐานระบบ

ขอบเขตโดยเจตนา: ตรวจเฉพาะคู่ที่ **วัดได้เป็นเครื่องจักร** (ทิศ/ปี/วันที่)
ความขัดแย้งเชิงความหมาย ("ย่อหน้าสามพูดกลับทาง") เป็นวิจารณญาณ ไม่อยู่ในด่านนี้
— อย่าพยายามยัดเข้ามา เดี๋ยวได้ด่านที่เดาสุ่มแล้วทุกคนเลิกเชื่อมัน

หมายเหตุกันวินิจฉัยผิด: กฎ "เลขใน Title/excerpt/H1 ต้องอยู่ในทะเบียน story"
**มีอยู่แล้ว** ใน validate ของ D/E (`number_not_in_story` กวาดทุกบรรทัดรวม
frontmatter) — ด่านนี้จึงไม่ทำซ้ำ จะได้ไม่มีทะเบียนสองชุดให้เพี้ยนจากกัน
"""

import re
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import headline_format  # noqa: E402

# ปี พ.ศ. โดด 2560–2585 (= ค.ศ. 2017–2042) — แคบพอไม่กินราคา
# lookbehind กันเลขที่เป็นหางของจำนวน (`14,2569` ไม่มีจริงแต่กันไว้) ·
# lookahead กันทศนิยม ("2569.50" เป็นราคาได้จริง เช่น ETH)
#
# 🔄 **กฎนี้กลับขั้วเมื่อ 2026-08-11** — เดิมจับ ค.ศ. เพราะบทเขียน พ.ศ.
# หัวหน้าสั่งกลับเป็น ค.ศ. ทั้งใบ (ทั้งเว็บบังคับ locale ค.ศ. ⇒ พาดหัว พ.ศ. ทำให้
# หน้าเดียวกันมีปีต่างกัน 543 ปี) ⇒ ของที่เคยผิดกลายเป็นถูก และกลับกัน
# ⚠️ ห้ามแก้ข้างเดียว: ตัวพิมพ์วันที่อยู่ที่ `headline_format.thai_date()` จุดเดียว
# เปลี่ยนที่นั่นแล้วไม่กลับด่านนี้ = บททุกใบตกด่าน · กลับด่านแล้วไม่เปลี่ยนที่นั่น =
# ด่านนี้ตีตกงานของตัวเอง
_BUDDHIST = re.compile(r"(?<![\d.,])25(?:[67]\d|8[0-5])(?!\d|[.,]\d)")

# วันที่แบบ ISO ในเนื้อความ — บทต้องเขียนวันที่เป็นไทย ("7 ส.ค. 2026") เสมอ
#
# ⚠️ **กฎนี้แยกออกมาตั้งเป็นกฎของตัวเองเมื่อ 08-11 ไม่ใช่กฎใหม่** — เดิม ISO ถูกจับ
# โดยบังเอิญเพราะกฎปีจับ ค.ศ. อยู่ ("2026-08-07" มี "2026") · พอกลับขั้วเป็นจับ พ.ศ.
# ISO จะรอดทันทีถ้าไม่ตั้งกฎแยก ⇒ การกลับขั้วจะกลายเป็นการผ่อนด่านแบบไม่ตั้งใจ
_ISO_DATE = re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)")

# เป้าหมายของลิงก์/ภาพ markdown — `](xauusd-d1-structure-2026-08-07.webp)`
# ชื่อไฟล์ภาพใช้วันที่ ISO โดยสเปก จึงต้องยกเว้นให้กฎ ISO (ไม่เกี่ยวกับกฎปี)
_LINK_TARGET = re.compile(r"\]\([^)]*\)")
_SLUG_FIELD = re.compile(r"^\s*slug:\s*")

_TREND = re.compile(r"(?m)^trend:\s*(up|dn|fl)\s*$")
_TITLE = re.compile(r"(?m)^title:\s*(.+)$")

# วันที่ไทยในพาดหัว — รองรับทั้งเดือนย่อ (H1) และเดือนเต็ม (Title)
_MONTHS = {name: number
           for number, name in enumerate(headline_format.MONTH_ABBR, start=1)}
_MONTHS.update({name: number
                for number, name in enumerate(headline_format.MONTH_FULL, start=1)})
_THAI_DATE = re.compile(
    r"(\d{1,2})\s+(" + "|".join(map(re.escape, _MONTHS)) + r")\s+(\d{4})")


def _fatal(rule: str, line: int, message: str) -> dict:
    return {"rule": rule, "severity": "fatal", "line": line, "message": message}


def _first_thai_date(text: str) -> tuple[int, int, int] | None:
    """(ปี, เดือน, วัน) จากวันที่ไทยตัวแรกในข้อความ — ไม่เจอ = None"""
    match = _THAI_DATE.search(text)
    if not match:
        return None
    day, month_name, year = match.groups()
    return int(year), _MONTHS[month_name], int(day)


def check(markdown: str, story: dict | None = None) -> list[dict]:
    """ตรวจบทหนึ่งใบ — คืน findings (ว่าง = ผ่าน)

    `story` ใช้แค่ช่อง `regime.down` สำหรับกฎทิศ — ส่ง None ได้เมื่อผู้เรียก
    ไม่มี story (เช่นตรวจไฟล์เก่าย้อนหลัง) แล้วกฎทิศจะถูกข้าม
    """
    findings: list[dict] = []

    # กฎ 1 — trend ใน frontmatter ต้องตรงกับ regime ของ story
    if story is not None:
        trend = _TREND.search(markdown)
        if trend:
            expected = story.get("trend_code")
            if expected not in {"up", "dn", "fl"}:
                expected = "dn" if story["regime"]["down"] else "up"
            if trend.group(1) != expected:
                findings.append(_fatal(
                    "trend_regime_mismatch", 1,
                    f"frontmatter บอกเว็บว่า trend: {trend.group(1)} "
                    f"แต่ story ชี้ {expected} — ป้ายเทรนด์บนเว็บจะสวนเนื้อบท"))

    # กฎ 2 — ปีทั้งใบเป็น ค.ศ. · ไม่ต้องยกเว้นชื่อไฟล์ภาพอีกแล้ว เพราะชื่อไฟล์ก็เป็น
    # ค.ศ. เหมือนเนื้อบท (เดิมต้องยกเว้นเพราะสองชั้นใช้คนละระบบปี)
    for line_number, line in enumerate(markdown.splitlines(), start=1):
        for match in _BUDDHIST.finditer(line):
            findings.append(_fatal(
                "buddhist_year", line_number,
                f"พบปี พ.ศ. '{match.group(0)}' ในเนื้อความ — บทต้องเป็น ค.ศ. "
                "ทั้งใบ (หัวหน้าสั่ง 08-11: เว็บแสดงวันที่เผยแพร่เป็น ค.ศ. เสมอ "
                "ปีสองระบบในหน้าเดียวต่างกัน 543 ปี)"))

        # กฎ 3 — วันที่ ISO ในเนื้อความ (ยกเว้นชื่อไฟล์ภาพ/เป้าหมายลิงก์ และ slug
        # ซึ่งทีมเว็บกำหนดให้ลงท้าย YYYY-MM-DD โดยตรง)
        if not _SLUG_FIELD.match(line):
            for match in _ISO_DATE.finditer(_LINK_TARGET.sub("]", line)):
                findings.append(_fatal(
                    "iso_date_in_body", line_number,
                    f"พบวันที่แบบ ISO '{match.group(0)}' ในเนื้อความ — "
                    "บทต้องเขียนวันที่เป็นไทย เช่น '7 ส.ค. 2026'"))

    # กฎ 5 — วันที่ใน Title กับ H1 ต้องเป็นวันเดียวกัน (คนละรูปแบบได้)
    title_match = _TITLE.search(markdown)
    h1_line = next((line for line in markdown.splitlines()
                    if line.startswith("# ")), None)
    if title_match and h1_line:
        title_date = _first_thai_date(title_match.group(1))
        h1_date = _first_thai_date(h1_line)
        if title_date and h1_date and title_date != h1_date:
            findings.append(_fatal(
                "title_h1_date_mismatch", 1,
                f"Title ลงวันที่ {title_date} แต่ H1 ลงวันที่ {h1_date} — "
                "หน้าเดียวกันอ้างสองวันคือบทขัดกันเอง"))

    return findings


def check_labels(labels: list[str]) -> list[dict]:
    """ตรวจป้ายข้อความที่จะวาดลงภาพ — เรียก**ก่อน**วาดเสมอ

    ป้ายบนภาพต้องเป็นระบบปีเดียวกับบท ⇒ พ.ศ. บนภาพผิดเสมอ
    (เคสจริงที่ทำให้ด่านนี้เกิด: บทกับหัวกราฟใช้คนละระบบปี — คนอ่านเห็นสองปี
    ในหน้าเดียว · กลับขั้วพร้อมกฎ 2 เมื่อ 08-11 ตามคำสั่งหัวหน้า)
    """
    findings: list[dict] = []
    for index, label in enumerate(labels, start=1):
        for match in _BUDDHIST.finditer(label):
            findings.append(_fatal(
                "buddhist_year_label", index,
                f"ป้ายภาพชิ้นที่ {index} มีปี พ.ศ. '{match.group(0)}': {label!r} "
                "— ภาพกับบทต้องเป็น ค.ศ. ชุดเดียวกัน"))
        # ป้ายบนภาพไม่มีข้อยกเว้นชื่อไฟล์ — คนอ่านเห็นป้าย ไม่ได้เห็นพาธ
        for match in _ISO_DATE.finditer(label):
            findings.append(_fatal(
                "iso_date_label", index,
                f"ป้ายภาพชิ้นที่ {index} มีวันที่แบบ ISO '{match.group(0)}': {label!r} "
                "— ป้ายต้องเขียนวันที่เป็นไทย เช่น '7 ส.ค. 2026'"))
    return findings
