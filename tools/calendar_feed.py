"""ปฏิทินเศรษฐกิจตัวใหม่ — `/api/calendar/feed` ของทีมเว็บ (ขึ้น prod 2026-08-07)

**แทนที่ช่อง `calendar` ที่มากับก้อน snapshot เป็นแหล่งปฏิทินหลัก** — ของเดิมส่งมา
แค่ 7 ช่อง (at/country/impact/title/forecast/previous/actual) ไม่มีหน่วย ไม่มีรหัส
ประจำรายการ และครอบคลุมแค่ ~40 แถว/7 วัน (เท่าที่ snapshot ตัดมาให้พอใช้ต่อบทเดียว)
ตัวใหม่ให้ **1,691 แถว · 59 วัน · 10 สกุลเงิน** พร้อมหน่วยที่มาจากต้นทางหรือ
พจนานุกรมของทีมเว็บ (`unit_source`) และรหัสประจำรายการที่คงที่ (`id`)

🔒 **ใช้รหัสเดียวกับ snapshot ได้เลย** (`WCB_SNAPSHOT_KEY`) — ทดสอบยิงจริงแล้ว
2026-08-07 ไม่ต้องขอรหัส prod แยก (คู่มือของทีมเว็บเตือนว่าอาจเป็นคนละตัว
แต่ของจริงตัวเดียวกัน)

⚠️ **กติกาหน่วย (ห้ามฝืนแม้จะดูปลอดภัย):**

    unit_source == "feed"  ต้นทางส่งหน่วยมาเอง                → เขียนได้
    unit_source == "dict"  ไม่ส่ง แต่เราเติมจากพจนานุกรมของเว็บ  → เขียนได้
    kind == "index"        ดัชนี ไม่มีหน่วยโดยธรรมชาติ           → เขียนเลขเปล่าได้
    unit_source is None    ไม่รู้หน่วยจริง ๆ                    → **ห้ามเขียนค่านี้เลย**
    scale_unknown is True  รู้สกุลเงินแต่ไม่รู้มาตราส่วน           → **ห้ามเขียนค่านี้เลย**
                            (ตัวอย่างจริง: ดุลการค้าจีน "$107" คือ 107 พันล้านดอลลาร์
                            ถ้าเขียนว่า "107 ดอลลาร์" จะผิดไปพันล้านเท่า)

**เลขเปล่าไม่ใช่ทางออกที่ปลอดภัยกว่า** — เคยคิดว่าตัด `unit_th` ทิ้งแล้วเขียนเลขเปล่า
พอ แต่ทีมเว็บตีกลับข้อ D-2 ด้วยตัวอย่างจริง: *"ยอดขายบ้านมือสอง ครั้งก่อนอยู่ที่ 4.09"*
คนอ่านไม่มีทางรู้ว่า 4.09 คืออะไร (ของจริงคือ 4.09 **ล้านหลัง**) ⇒ ทั้ง `unit_source is None`
และ `scale_unknown` จึง**ข้ามทั้งค่าเหมือนกัน** ต่างกันแค่เหตุผล

เส้นแบ่งที่ต้องไม่สับสน (ทีมเว็บย้ำเอง): *"ไม่มีหน่วยเพราะเป็นดัชนี"* (`kind == "index"`
เช่น PMI 54.1) กับ *"ไม่รู้หน่วย"* (`unit_source is None`) **คนละเรื่องกัน** — อย่างแรก
เลขเปล่าคือคำตอบที่ถูกต้อง อย่างหลังเลขเปล่าคือการปล่อยให้คนอ่านเดาเอง

**การจับคู่หลักฐานสำหรับด่านตรวจ:** ฟีดนี้เป็นคนละ endpoint จาก snapshot API —
เลขที่มันให้มาจึง **ไม่อยู่ในก้อน snapshot ที่ `wcb_copy_validator.collect_evidence`
เดินอยู่** ผู้เรียกต้องส่งก้อนดิบของฟีดนี้ (จาก `fetch_raw`) เข้าพารามิเตอร์
`calendar_feed=` ของ `wcb_copy_validator.validate()` ด้วยเสมอ ไม่งั้นตัวเลข
ที่มาจากฟีดนี้ (โดยเฉพาะรายการนอกช่วง/นอกประเทศที่ snapshot ไม่เคยมี) จะตกด่าน
`number_unsupported` — รูปแบบเดียวกับที่ `plan_numbers()` ทำให้หัวข้อแผนเทรด
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import wcb_source  # noqa: E402

BASE_URL = "https://worldclassbroker.worldclassbroker-com.workers.dev/api/calendar/feed"
DEFAULT_TIMEOUT = 15
DEFAULT_SPAN_DAYS = 30            # พอสำหรับหน้าต่างที่ _calendar_events คัดจริง (few สัปดาห์)
EVENT_UNITS_PATH = Path(__file__).resolve().parents[1] / "config" / "calendar_event_units.json"


class CalendarFeedUnusable(RuntimeError):
    """ฟีดนี้ใช้ไม่ได้รอบนี้ — ผู้เรียกต้อง fallback ไปปฏิทินเดิมใน snapshot ไม่ใช่ล้มทั้งบท"""


def _resolve_key(key: str | None) -> str:
    """รหัสเดียวกับ snapshot — ยืมตัวอ่านของ wcb_source แทนการเขียนซ้ำ"""
    return wcb_source._resolve_key(key)  # noqa: SLF001 — เจตนาใช้ตัวอ่านรหัสร่วมกัน จุดเดียว


def fetch_raw(*, from_date: str | None = None, to_date: str | None = None,
             impact: str | None = None, country: str | None = None,
             key: str | None = None, base_url: str = BASE_URL,
             timeout: int = DEFAULT_TIMEOUT) -> dict:
    """คืน **ก้อนดิบ** ตามที่ปลายทางส่งมา — ก้อนนี้ต้องเก็บไว้ส่งต่อให้ด่านตรวจด้วย

    ค่าตั้งต้นของช่วงวันคือวันนี้ถึงอีก `DEFAULT_SPAN_DAYS` วัน (ทาง UTC ตามที่
    เอกสาร API ระบุ) — ผู้เรียกที่ต้องการช่วงอื่นระบุ `from_date`/`to_date` เอง

    **`impact` ค่าตั้งต้นคือไม่กรอง (ดึงทุกระดับ)** — วัดกับ prod จริง 2026-08-10:
    ตัวกรองรับค่าเดี่ยวแบบตรงตัวเท่านั้น (`High` → 61 รายการ · `High,Medium` ถูก
    เมิน ได้ทั้งหมด 873 รายการเท่ากับไม่กรอง) ⇒ ขอทั้งหมดแล้วให้ตัวคัดฝั่งเรา
    (`wcb_writers._calendar_events` ผ่าน `upcoming(impacts=("High","Medium"))`)
    เป็นคนกรอง เพราะกติกา "ที่นั่งจองให้รายการใกล้ที่สุด" ตั้งใจให้รายการ Medium
    ของคืนนี้ (เช่น ADP) ยังโผล่ในบทได้ — เคยกรอง `High` ที่ชั้นนี้แล้วรายการ
    Medium หายจากบททั้งที่ตัวคัดออกแบบมารองรับ
    """
    if from_date is None or to_date is None:
        today = date.today()
        from_date = from_date or today.isoformat()
        to_date = to_date or (today + timedelta(days=DEFAULT_SPAN_DAYS)).isoformat()
    secret = _resolve_key(key)
    params = [f"from={from_date}", f"to={to_date}", f"k={secret}"]
    if impact:
        params.append(f"impact={impact}")
    if country:
        params.append(f"country={country}")
    url = f"{base_url}?{'&'.join(params)}"
    try:
        with urllib.request.urlopen(wcb_source.build_request(url), timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        message = wcb_source.redact(str(error), secret)
        raise CalendarFeedUnusable(f"เรียก /api/calendar/feed ไม่สำเร็จ: {message}") from None
    if not payload.get("ok"):
        raise CalendarFeedUnusable(f"ปลายทางตอบว่าไม่ ok: {payload}")
    # Metadata from the actual I/O boundary, not a caller's article as-of time.  Style C
    # uses this to prove the release values existed before its analysis cutoff.
    payload.setdefault("retrieved_at", datetime.now(tz=timezone.utc).isoformat())
    return payload


def format_value(field: dict | None) -> str | None:
    """แปลงค่าหนึ่งช่อง (forecast/previous/actual) เป็นข้อความที่เขียนลงบทได้

    `None` = ไม่มีค่า หรือมีแต่ห้ามเขียน (สภาพ `scale_unknown`) — ผู้เรียกปลายทาง
    (`_calendar_events`/`_calendar_sentences` ของ `wcb_writers`) จัดการค่า `None`
    อยู่แล้วโดยตัดวลีนั้นทิ้งเงียบ ๆ ตามกติกาเดิม ไม่ต้องมีโค้ดพิเศษเพิ่ม
    """
    if not field:
        return None
    if field.get("scale_unknown"):
        # รู้สกุลเงินแต่ไม่รู้มาตราส่วน — เลขเปล่าก็ยังชวนเข้าใจผิดว่าเป็นหน่วยเดิม
        # (ตัวอย่างจริง: "$107" ที่จริงคือ 107 พันล้าน) ⇒ ข้ามทั้งค่า ไม่ใช่แค่ตัดหน่วย
        return None
    raw = field.get("raw")
    if raw in (None, ""):
        return None
    if field.get("unit_source") is None and field.get("kind") != "index":
        # ไม่รู้หน่วยจริง ๆ — **ข้ามทั้งค่า** ไม่ใช่เขียนเลขเปล่า
        # นี่คือข้อ D-2 ที่ทีมเว็บตีกลับมาเอง: "ยอดขายบ้านมือสอง ครั้งก่อนอยู่ที่ 4.09"
        # อ่านแล้วไม่รู้ว่า 4.09 อะไร (ของจริงคือ 4.09 ล้านหลัง) — คำสั่งตรงตัวคือ
        # *"ค่าที่ไม่มีหน่วย ให้ตัดออกจากบท ไม่ต้องเขียน 'ครั้งก่อน' เลย ดีกว่าเขียนแล้วคนอ่านงง"*
        # ยกเว้น `kind == "index"` ซึ่งไม่มีหน่วยโดยธรรมชาติ (ดัชนี PMI ฯลฯ) เลขเปล่าถูกต้องแล้ว
        # — ทีมเว็บย้ำเองว่า "ไม่มีหน่วยเพราะเป็นดัชนี" กับ "ไม่รู้หน่วย" คนละเรื่องกัน
        return None
    unit_th = field.get("unit_th")
    # หน่วยที่เป็นสัญลักษณ์ (%) ติดอยู่ใน raw แล้ว ("4.2%") — เติมคำว่า "เปอร์เซ็นต์"
    # ซ้ำจะกลายเป็น "4.2% เปอร์เซ็นต์" ⇒ ไม่เติมเมื่อ unit เป็นสัญลักษณ์ที่ raw มีอยู่แล้ว
    if field.get("unit") == "%":
        return str(raw) if "%" in str(raw) else f"{raw}%"
    if not unit_th:
        return str(raw)
    return f"{raw} {unit_th}"


@lru_cache(maxsize=1)
def _event_unit_families() -> tuple[dict, ...]:
    """โหลดทะเบียนหน่วยกลางครั้งเดียว; ทะเบียนเสียให้กลับสู่โหมดตัดค่าแบบปลอดภัย"""
    try:
        payload = json.loads(EVENT_UNITS_PATH.read_text(encoding="utf-8"))
        families = payload.get("families") or []
        if not isinstance(families, list):
            return ()
        return tuple(family for family in families if isinstance(family, dict))
    except (OSError, json.JSONDecodeError):
        return ()


def _event_unit_family(event: dict) -> dict | None:
    """จับครอบครัวด้วยรหัสคงที่ก่อน แล้วจึงใช้นามอังกฤษที่อนุมัติเป็นทางสำรอง"""
    source_id = str(event.get("id") or event.get("event_id") or "").strip()
    title_en = str(event.get("title_en") or "").strip().casefold()
    country = str(event.get("country") or "").strip().upper()
    for family in _event_unit_families():
        if str(family.get("country") or "").upper() not in ("", country):
            continue
        ids = {str(value) for value in family.get("source_ids") or []}
        aliases = {str(value).strip().casefold()
                   for value in family.get("approved_aliases") or []}
        if (source_id and source_id in ids) or (title_en and title_en in aliases):
            return family
    return None


def _enrich_value_unit(field: dict | None, family: dict | None) -> dict | None:
    """เติมหน่วยเฉพาะค่าที่ทะเบียนยืนยัน; ไม่ลบล้างสถานะ scale_unknown จากต้นทาง"""
    if not field or not family or field.get("scale_unknown"):
        return field
    if field.get("unit_source") is not None or field.get("kind") == "index":
        return field
    enriched = dict(field)
    enriched["kind"] = family.get("kind")
    enriched["unit"] = family.get("unit")
    enriched["unit_th"] = family.get("unit_th")
    enriched["unit_source"] = "dict"
    return enriched


def _event_title(event: dict) -> str:
    """คงชื่อไทย แต่เติมช่วงเทียบจากชื่ออังกฤษเพื่อไม่รวมค่าคนละหน่วยเป็นแถวเดียว"""
    title = str(event.get("title_th") or event.get("title_en") or "").strip()
    title_en = str(event.get("title_en") or "")
    if re.search(r"\bMoM\b", title_en, flags=re.IGNORECASE) and "รายเดือน" not in title:
        title = f"{title} (รายเดือน)"
    elif re.search(r"\bYoY\b", title_en, flags=re.IGNORECASE) and "รายปี" not in title:
        title = f"{title} (รายปี)"
    return title


def strip_snapshot_values(evidence: dict) -> int:
    """ตัดค่า previous/forecast/actual ทิ้งทั้งปฏิทิน — ด่านหน่วยของสายสำรอง

    ช่อง `calendar` เดิมใน snapshot ไม่มีข้อมูลหน่วยติดมาเลย (ต่างจาก `/feed`
    ที่มี `unit_source` ให้ `format_value` ตัดสินรายค่า) ⇒ เลขทุกตัวจากช่องนั้น
    คือ "ไม่รู้หน่วย" ตามนิยามข้างบน และต้องถูกตัดทั้งค่าแบบเดียวกัน
    ประโยคปฏิทินยังจบในตัวเองได้ เพราะกิ่ง `else` ของ `_calendar_sentences`
    ปิดประโยคให้เมื่อไม่เหลือค่า

    🐞 ที่มา (ทีมเว็บรอบสี่ 2026-08-10 · ข้อ A-3 ครึ่งหลัง): "ADP อยู่ที่ 15" /
    "บ้านมือสอง 4.09" หลุดขึ้นบทจริง เพราะรอบผลิตเดินสายปฏิทินเก่าที่ไม่ผ่าน
    `format_value` เลย — ด่านหน่วยมีครบแต่คุมเฉพาะสายฟีดใหม่ที่ปิดสวิตช์อยู่

    คืนจำนวนรายการที่ถูกตัดค่าจริง (ผู้เรียกใช้พิมพ์บอกหน้างาน)
    """
    stripped = 0
    for event in evidence.get("calendar") or []:
        if any(event.get(field) not in (None, "")
               for field in ("previous", "forecast", "actual")):
            stripped += 1
        event["previous"] = event["forecast"] = event["actual"] = None
    return stripped


def to_calendar_event(event: dict) -> dict:
    """แปลงหนึ่งรายการจาก `/feed` พร้อมคง identity สำหรับ relevance/audit.

    ช่องเดิมยังอยู่ครบเพื่อไม่กระทบผู้เรียก A/B/C ส่วน `source_id` และชื่ออังกฤษ
    เป็นข้อมูลบังคับของ Style D: ใช้ match ทะเบียนแบบ exact โดยไม่เดาจากชื่อไทย
    ที่ผ่านการแปลหรือเปลี่ยนถ้อยคำแล้ว
    """
    title = _event_title(event)
    family = _event_unit_family(event)
    title_suffix = str((family or {}).get("title_suffix_th") or "").strip()
    if title_suffix and title_suffix not in title:
        title = f"{title} ({title_suffix})"
    return {
        "source_id": str(event.get("id") or event.get("event_id") or ""),
        "title_en": str(event.get("title_en") or "").strip(),
        "title_th": str(event.get("title_th") or "").strip(),
        "at": event.get("at_th"),
        "country": event.get("country"),
        "impact": event.get("impact"),
        "title": title,
        "previous": format_value(_enrich_value_unit(event.get("previous"), family)),
        "forecast": format_value(_enrich_value_unit(event.get("forecast"), family)),
        "actual": format_value(_enrich_value_unit(event.get("actual"), family)),
    }


def to_calendar_events(raw: dict) -> list[dict]:
    """แปลงรูปของ `/feed` ให้ตรงช่องเดิมและคง provenance สำหรับ Style D

    ทำแบบนี้เพื่อให้ `wcb_writers._calendar_events`/`_calendar_sentences` (ตัวคัด
    และตัวเรียงประโยคของสาย A/B/C/D) **ใช้ต่อได้โดยไม่ต้องแก้โค้ดตัวมันเองสักบรรทัด**
    — จุดเดียวที่เปลี่ยนคือแหล่งข้อมูลที่ป้อนเข้าช่อง `calendar`
    """
    return [to_calendar_event(event) for event in raw.get("events") or []]


def merge(evidence: dict, raw: dict) -> None:
    """แทนที่ `evidence["calendar"]` ด้วยรายการจากฟีดใหม่ — mutate in place

    เรียกหลัง `wcb_source.normalize()`/`ensure_fresh()` เสมอ เพื่อไม่ให้ทับ
    ค่าที่ด่านความสดยังไม่ได้ตรวจ · ไม่เรียกฟังก์ชันนี้เลย = ยังใช้ปฏิทินเดิมใน
    snapshot ตามปกติ (พฤติกรรมเดิมทุกประการ — การไม่เรียกต้องปลอดภัยเสมอ)
    """
    evidence["calendar"] = to_calendar_events(raw)
