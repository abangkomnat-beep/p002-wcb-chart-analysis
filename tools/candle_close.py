"""ชั้นข้อมูลของกฎ "แท่งที่ยังไม่ปิด ห้ามถูกเรียกว่าปิด" — ใช้ร่วมกันทุกสไตล์

🐞 **A-1 (ทีมเว็บตรวจรอบสาม 2026-08-09)** — บทสไตล์ D เขียนว่า *"แท่งล่าสุดปิดที่
4,304.52 ดอลลาร์"* แต่ราคาปิดจริงของ 7 ส.ค. คือ **4,342.63** (ต่าง 38.11 = 0.88%)
**ข้อมูลไม่ได้ผิด** — บทถูกผลิตขณะแท่งรายวันของทองยังก่อตัว ก้อนข้อมูลคืนราคา ณ
ขณะนั้นมาถูกต้องแล้ว **แต่บทขึ้นเว็บวันถัดไป** คนอ่านเห็นกราฟและแผงราคาบนหน้า
เดียวกันที่แสดง "ราคาปิดจริง" ⇒ ตัวเลขในบทไม่ตรงกับกราฟบนหน้าเดียวกัน ซึ่งเป็น
กฎเหล็กข้อเดียวกับที่ห้ามหยิบราคาจากเว็บนอกมาใส่

**ทางที่ผู้ใช้เลือก (2026-08-09): ผลิตบทหลังแท่งวันปิดแล้ว แล้วคงคำว่า "ปิด" ไว้**
ทางที่ไม่เอา: คงเวลาผลิตเดิมแล้วเปลี่ยนถ้อยคำเป็น "ราคาล่าสุด ณ …" — เพราะแก้แค่ป้าย
ตัวเลขในบทยังต่างจากกราฟบนหน้าเดียวกันอยู่ดี

**ทำไมโมดูลนี้ต้องมี ไม่ใช่แค่ไปตั้งตารางรันให้ดึก:** ตารางรันเป็นสัญญาปากเปล่า —
รันเร็วไปหนึ่งชั่วโมง, ตลาดหยุดวันนั้น, หรือ provider ส่งแท่งของวันถัดไปมาก่อนเวลา
ก็ทำให้คำว่า "ปิด" กลายเป็นเท็จอีกเงียบ ๆ ⇒ ถ้อยคำต้องถูกบังคับด้วย**สภาพจริงของแท่ง**
ที่คำนวณจาก (ป้าย session ของแท่ง + เวลาปิดตลาดของสินทรัพย์นั้นใน
`config/market_calendar.json` + เวลาปัจจุบัน) ไม่ใช่จากความเชื่อว่ารันถูกเวลา

**ชั้นข้อมูล = ตัดแท่งที่ยังไม่ปิดทิ้งก่อนคำนวณอะไรทั้งสิ้น** ไม่ใช่ติดธงไว้เฉย ๆ
เพราะค่าที่ผูกกับแท่งล่าสุดมีเต็มบท (Fibonacci swing · SMA50 · ATR14 · ระยะห่างโซน ·
ราคาที่ใช้ตัดสิน active/รอ ของฉากทัศน์) — **ห้ามผสมแท่งปิดกับแท่งที่ยังไม่ปิดในบทเดียว**
ถ้าตัดที่ปลายทางทีละจุดจะลืมจุดใดจุดหนึ่งเสมอ (บทเรียนซ้ำของโปรเจกต์นี้:
"แก้เฉพาะตัวที่ฟ้องอย่างเดียวไม่พอ ต้องกวาดทั้งไฟล์")
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import market_calendar  # noqa: E402

CLOSED = "closed"
FORMING = "forming"


class NoClosedCandle(RuntimeError):
    """ไม่เหลือแท่งที่ปิดแล้วเลย — หยุดสายผลิต ห้ามเขียนบทจากแท่งที่ยังก่อตัว"""


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(tz=timezone.utc)


def trim_to_closed(rows: list[dict], calendar, *, now: datetime | None = None) -> tuple[list[dict], list[str]]:
    """ตัดแท่งท้ายที่ยังไม่ถึงเวลาปิดออก คืน (rows ที่เหลือ, วันที่ถูกตัด)

    ไล่จากท้ายเข้ามาเรื่อย ๆ เพราะ provider เคยส่งแท่งของวันถัดไปมาล่วงหน้าพร้อมกัน
    มากกว่าหนึ่งแท่ง (เจอกับ endpoint ที่ให้ค่า intraday ของสองวันซ้อน) — ตัดแค่แท่ง
    สุดท้ายแท่งเดียวจึงไม่พอ
    """
    moment = _now(now)
    dropped: list[str] = []
    kept = list(rows)
    while kept and not calendar.is_daily_candle_closed(kept[-1]["date"], moment):
        dropped.append(kept[-1]["date"])
        kept.pop()
    dropped.reverse()
    return kept, dropped


def evaluate(rows: list[dict], *, asset: str, now: datetime | None = None,
             calendar=None) -> tuple[list[dict], dict]:
    """คืน (rows ที่ทุกแท่งปิดแล้ว, ก้อนหลักฐาน) — ไม่เหลือแท่งปิด = โยน NoClosedCandle

    ก้อนหลักฐานถูกฝังใน story เพื่อให้ด่านตรวจ **คำนวณซ้ำได้เอง** ไม่ใช่เชื่อธง
    (ดู `verify()` — ด่านไม่อ่านค่าธง `candle_state` มาตัดสิน แต่ไล่คำนวณเวลาปิด
    จาก config ใหม่ทั้งชุดแล้วเทียบกับนาฬิกาจริงตอนตรวจ)
    """
    calendar = calendar or market_calendar.for_asset(asset)
    moment = _now(now)
    kept, dropped = trim_to_closed(rows, calendar, now=moment)
    if not kept:
        raise NoClosedCandle(
            f"{asset}: ไม่มีแท่งรายวันที่ปิดแล้วในชุดข้อมูลเลย ({calendar.daily_close_rule_text()}) "
            "— หยุดสายผลิต ห้ามเขียนคำว่า 'ปิด' ทับราคาที่ยังก่อตัว")
    return kept, basis_for(asset, kept[-1]["date"], now=moment, calendar=calendar,
                           dropped=dropped)


def basis_for(asset: str, session_date: str, *, now: datetime | None = None,
              calendar=None, dropped: list[str] | None = None) -> dict:
    """ก้อนหลักฐานของแท่งฐานหนึ่งแท่ง — ตัวสร้างเดียวที่ใช้ทั้งสายผลิตและเทส

    มีตัวสร้างตัวเดียวเพื่อไม่ให้เทสประกอบก้อนหลักฐานด้วยมือแล้วเผลอเขียนรูปแบบที่
    ด่านจริงไม่เคยเจอ (เทสจะผ่านทั้งที่ของจริงตก — หรือกลับกัน)
    """
    calendar = calendar or market_calendar.for_asset(asset)
    return {
        "asset": asset,
        "asset_class": calendar.asset_class,
        "candle_state": CLOSED,
        "basis_session_date": session_date,
        "basis_close_at": calendar.daily_close_at(session_date).isoformat(),
        "evaluated_at": _now(now).isoformat(),
        "rule": calendar.daily_close_rule_text(),
        "dropped_forming_sessions": list(dropped or []),
    }


def verify(basis: dict | None, *, asset: str, session_date: str,
           now: datetime | None = None) -> str | None:
    """ด่าน fail-closed — คืน None เมื่อพิสูจน์ได้ว่าแท่งปิดแล้ว ไม่งั้นคืนเหตุที่ตก

    พิสูจน์ใหม่จากศูนย์ทุกครั้ง: อ่านเวลาปิดของสินทรัพย์จาก `market_calendar.json`
    คำนวณเวลาปิดของ session ที่บทใช้เป็นฐาน แล้วเทียบกับนาฬิกา ณ ตอนตรวจ
    **ไม่มีทางผ่านด่านด้วยการตั้งค่าธงเอง** — ก้อนหลักฐานถูกใช้เพื่อยืนยันว่า
    ชั้นข้อมูลกับชั้นบทพูดถึงแท่งเดียวกันเท่านั้น
    """
    if not basis:
        return ("บทไม่มีก้อนหลักฐานสถานะแท่ง (candle_basis) — พิสูจน์ไม่ได้ว่าแท่งล่าสุดปิดแล้ว "
                "จึงเขียนคำว่า 'ปิด' ทับราคาไม่ได้")
    if basis.get("basis_session_date") != session_date:
        return (f"ฐานแท่งของบท ({session_date}) ไม่ตรงกับก้อนหลักฐาน "
                f"({basis.get('basis_session_date')}) — บทกับข้อมูลพูดถึงคนละแท่ง")
    try:
        calendar = market_calendar.for_asset(asset)
    except ValueError as exc:
        return f"ไม่รู้ปฏิทินตลาดของ {asset}: {exc}"
    try:
        close_at = calendar.daily_close_at(session_date)
    except market_calendar.UnknownCloseTime as exc:
        return str(exc)
    moment = _now(now)
    if close_at > moment:
        return (f"แท่ง {session_date} ปิดเวลา {close_at.isoformat()} ซึ่งยังมาไม่ถึง "
                f"(ตรวจเมื่อ {moment.isoformat()}) — {calendar.daily_close_rule_text()} "
                "· บทเรียกราคาของแท่งที่ยังก่อตัวว่า 'ปิด' ไม่ได้")
    return None
