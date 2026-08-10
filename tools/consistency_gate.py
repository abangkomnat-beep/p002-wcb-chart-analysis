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

# ปี ค.ศ. โดด 2020–2035 — แคบพอไม่กินราคา (ทอง 2,026.50 · ETH 2026.50 มีจริง)
# lookbehind กันเลขที่เป็นหางของจำนวน (1,2026 ไม่มีจริงแต่กันไว้) ·
# lookahead กันทศนิยม ("2026.50") แต่ปล่อยวันที่ ISO ("2026-08-07") ให้โดนจับ
# เพราะ ISO ในเนื้อความคือความผิดจริง (บทต้องเขียนไทย พ.ศ. เท่านั้น)
_GREGORIAN = re.compile(r"(?<![\d.,])20(?:2\d|3[0-5])(?!\d|[.,]\d)")

# เป้าหมายของลิงก์/ภาพ markdown — `](xauusd-d1-structure-2026-08-07.webp)`
# ชื่อไฟล์เป็น ค.ศ. โดยสเปก (ทะเบียนวันที่ภายในเป็น ค.ศ. แปลงตอนพิมพ์เท่านั้น)
_LINK_TARGET = re.compile(r"\]\([^)]*\)")

_TREND = re.compile(r"(?m)^trend:\s*(up|dn)\s*$")
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
            expected = "dn" if story["regime"]["down"] else "up"
            if trend.group(1) != expected:
                findings.append(_fatal(
                    "trend_regime_mismatch", 1,
                    f"frontmatter บอกเว็บว่า trend: {trend.group(1)} "
                    f"แต่ story ชี้ {expected} — ป้ายเทรนด์บนเว็บจะสวนเนื้อบท"))

    # กฎ 2 — ปีทั้งใบเป็น พ.ศ. (ยกเว้นเป้าหมายลิงก์/ชื่อไฟล์ภาพซึ่งเป็น ค.ศ. โดยสเปก)
    for line_number, line in enumerate(markdown.splitlines(), start=1):
        scannable = _LINK_TARGET.sub("]", line)
        for match in _GREGORIAN.finditer(scannable):
            findings.append(_fatal(
                "gregorian_year", line_number,
                f"พบปี ค.ศ. '{match.group(0)}' ในเนื้อความ — บทต้องเป็น พ.ศ. "
                "ทั้งใบ (D-4.5: ปีสองระบบในหน้าเดียวคือบทขัดกันเอง)"))

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

    ป้ายบนภาพไม่มีข้อยกเว้นชื่อไฟล์ — ค.ศ. บนภาพผิดเสมอ
    (เคสจริง: บทเป็น พ.ศ. แต่หัวกราฟเป็น ค.ศ. — รายงานหัวหน้าไว้ในจดหมายรอบห้า)
    """
    findings: list[dict] = []
    for index, label in enumerate(labels, start=1):
        for match in _GREGORIAN.finditer(label):
            findings.append(_fatal(
                "gregorian_year_label", index,
                f"ป้ายภาพชิ้นที่ {index} มีปี ค.ศ. '{match.group(0)}': {label!r} "
                "— ภาพกับบทต้องเป็น พ.ศ. ชุดเดียวกัน"))
    return findings
