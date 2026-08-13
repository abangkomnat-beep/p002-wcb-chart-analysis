"""แท่งราคาระหว่างวัน (1h/4h) สำหรับบทเช้าสไตล์ F/G — ชั้นข้อมูล + ด่านแท่งปิดของตัวเอง

ที่มา: ผู้ใช้สั่ง 2026-08-10 ให้สไตล์ F/G ใช้กรอบเวลาตามต้นแบบ InterGold ซึ่งเป็น
กราฟราย 1 ชั่วโมง · เหตุผลเชิงเนื้อหา: บนแท่งรายวัน แนวรับที่บทประกาศห่างราคา 5–10%
ซึ่งเขียนว่า "รอย่อเข้าหาแนวรับ" ไม่ได้จริง (ต้นแบบห่าง ~1.2%)

**ทำไมเป็นโมดูลแยก ไม่ไปแก้ `candle_close`:** ด่านรายวันของสไตล์ A–E ผ่านการตรวจ
ของทีมเว็บและหัวหน้ามาแล้วหลายรอบ (A-1) การไปเติมสาขา intraday เข้าไปในนั้นแปลว่า
ทุกสไตล์รับความเสี่ยงจากโค้ดที่มีสไตล์เดียวใช้ ⇒ แยกไฟล์ ใช้กติกาเดียวกันแต่คนละเส้นทาง
**เส้นทางรายวันไม่ถูกแตะแม้แต่บรรทัดเดียว**

กติกาแท่งปิดของ intraday ง่ายกว่ารายวันมาก และไม่ต้องพึ่งปฏิทินตลาด:

    แท่งที่ป้ายเวลา t ครอบช่วง [t, t+ช่วง) ⇒ ปิดเมื่อ now >= t + ช่วง

วัดจริง 2026-08-10: ปลายทางส่งแท่งสุดท้ายเป็น**แท่งที่กำลังเดิน** (ราคาปิดของแท่ง
19:00 เท่ากับราคาล่าสุดของแท่งรายวันเป๊ะ) ⇒ ต้องตัดทิ้งเสมอ ไม่ใช่บางครั้ง

🔴 **เวลาที่ปลายทางส่งมาไม่มี timezone กำกับ และไม่เหมือนกันทุกสัญลักษณ์**

~~เดิมที่นี่เขียนว่า "วัดแล้วตรงกับเวลาไทย" โดยอ้างว่าแท่ง 4h เรียงที่
03:00/07:00/11:00/15:00/19:00 ซึ่งคือรอบ UTC+7~~ — **ข้อสรุปนั้นผิด** การเรียงบนกริด
บอกได้แค่ offset *เศษของช่วงแท่ง* ไม่ได้บอก offset จริง (กริดทุก 4 ชั่วโมงเหมือนกันหมด
ไม่ว่าจะบวกไปกี่รอบ 4 ชั่วโมง)

**การวัดที่ชี้ขาด 2026-08-13** — เฝ้าดูว่าปลายทางเปิดแท่งถัดไปตอนไหน:

    btcusd 06:15 → 06:30   ณ UTC 06:34:33
    xauusd 16:15 → 16:30   ณ UTC 06:34:34

เปิดแท่งใหม่**พร้อมกันในวินาทีเดียวกัน** แต่ป้ายต่างกัน **10 ชั่วโมงเป๊ะ**
⇒ เดินตามนาฬิกาโลกใบเดียวกันแต่เขียนป้ายคนละเขตเวลา และ**ไม่มีตัวไหนเป็นเวลาไทย**
(บิทคอยน์ ≈ UTC · ทอง ≈ UTC+10)

ผลของการเดาผิดแยกเป็นสองทิศและอันตรายคนละแบบ:

* บิทคอยน์ (เราอ่านเร็วไป 7 ชม.) — แท่งที่**ยังก่อตัว**ดูเหมือนปิดนานแล้ว ⇒ ด่านแท่งปิดถูกข้าม
* ทอง (เราอ่านช้าไป 3 ชม.) — แท่งจริงที่ปิดแล้ว**ถูกตัดทิ้ง** ⇒ เขียนบทจากแท่งเก่า

**วิธีแก้ที่ใช้อยู่:** `config/intraday_feed_timezones.json` เก็บ offset ที่วัดได้ต่อหัวข้อ
แล้ว `rows_from_candles` **แปลงป้ายเวลาเป็นเวลาไทยทันทีตอนรับเข้า** ⇒ ทุกอย่างหลังจากนั้น
ทำงานบนเวลาไทยจริงโดยไม่ต้องรู้เรื่องนี้ · และทุกรอบที่ดึงแท่งจะ **วัด offset สดแล้วเทียบ
กับทะเบียน** (`verify_offset`) เพื่อไม่ให้ปลายทางขยับฐานเวลาแล้วเราผิดเงียบ
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import wcb_series_source, wcb_source  # noqa: E402

BAR_TZ = wcb_source.BANGKOK
FEED_TZ_PATH = Path(_REPO_ROOT) / "config" / "intraday_feed_timezones.json"

# กรอบเวลาที่รองรับ — ชื่อคีย์ตรงกับพารามิเตอร์ `interval` ของปลายทาง
#
# ✅ **`15min` / `30min` เพิ่มเมื่อ 2026-08-13 สำหรับสไตล์ H/I/J — ยิงถามปลายทางจริง
# ก่อนเพิ่ม ไม่ได้เดาชื่อ** (ข้อเสนอ H–J §27 สั่งไว้ตรง ๆ ว่าห้ามเดาชื่อ interval
# แล้ว fallback เงียบ) · วัด 2026-08-13 ด้วย BTCUSD: `interval=15min` คืน
# `{"ok":true,"interval":"15min",...}` แท่งเรียงทีละ 15 นาที · `30min` เช่นกัน
# ⇒ ชื่อคีย์ฝั่งเราตรงกับที่ปลายทางตอบกลับมาเป๊ะ ไม่ต้องมีตารางแปลงชื่อ
#
# 📌 บันทึกไว้กันวินิจฉัยผิดในอนาคต: ปลายทางส่งช่อง `v` มาเป็น **null** ทุกแท่ง
# ทั้งสองกรอบ ⇒ สไตล์สาย Volume/VWAP (K ในข้อเสนอ) ยังทำไม่ได้จริง ไม่ใช่แค่
# "ยังไม่ได้ทำ" — หลักฐานอยู่ที่ payload ไม่ใช่ที่ความเห็น
TIMEFRAMES = {
    "15min": {"minutes": 15, "thai": "ราย 15 นาที", "short": "15 นาที", "ma_unit": "แท่ง"},
    "30min": {"minutes": 30, "thai": "ราย 30 นาที", "short": "30 นาที", "ma_unit": "แท่ง"},
    "1h": {"minutes": 60, "thai": "ราย 1 ชั่วโมง", "short": "1 ชั่วโมง", "ma_unit": "แท่ง"},
    "4h": {"minutes": 240, "thai": "ราย 4 ชั่วโมง", "short": "4 ชั่วโมง", "ma_unit": "แท่ง"},
}

# ขอเผื่อจากปลายทาง — ต้องคลุม SMA200 (200 แท่ง) + หน้าต่างที่จะแสดง + แท่งที่ถูกตัด
DEFAULT_OUTPUTSIZE = 500


class IntradayUnavailable(RuntimeError):
    """ดึงแท่งระหว่างวันไม่ได้หรือได้ไม่พอ — หยุดสาย F/G ห้ามเดาต่อ"""


class NoClosedBar(RuntimeError):
    """ไม่เหลือแท่งที่ปิดแล้ว — ห้ามเขียนคำว่า 'ปิด' ทับแท่งที่กำลังเดิน"""


def spec_for(timeframe: str) -> dict:
    try:
        return TIMEFRAMES[timeframe]
    except KeyError as exc:
        raise IntradayUnavailable(
            f"ไม่รู้จักกรอบเวลา '{timeframe}' — รองรับ {', '.join(TIMEFRAMES)}") from exc


def parse_at(text: str) -> datetime:
    """'2026-08-10 19:00:00' → datetime ที่มี timezone ไทยติดมาด้วย

    ใช้กับป้ายเวลาที่**แปลงเป็นเวลาไทยแล้ว** (ทุกแถวที่ออกจาก `rows_from_candles`)
    ไม่ใช่กับป้ายเวลาดิบจากปลายทาง — ป้ายดิบต้องผ่าน `to_bangkok` ก่อน
    """
    return datetime.strptime(str(text)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=BAR_TZ)


# ------------------------------------------------- เขตเวลาของป้ายเวลาที่ปลายทางส่งมา

class FeedTimezoneUnknown(IntradayUnavailable):
    """ไม่รู้ว่าป้ายเวลาของหัวข้อนี้นับจากนาฬิกาเรือนไหน — หยุดสาย ห้ามเดาว่าเป็นเวลาไทย

    เดาแล้วผิดไม่ได้แค่ "เวลาเพี้ยน" แต่ทำให้ด่านแท่งปิดตัดสินผิดทั้งสองทิศ
    (รับแท่งที่ยังก่อตัว หรือทิ้งแท่งที่ปิดแล้ว) ซึ่งเป็นด่านที่ทั้งระบบพึ่งพา
    """


class FeedTimezoneDrift(IntradayUnavailable):
    """offset ที่วัดสดได้ ต่างจากที่ทะเบียนบอกเกินที่ยอมให้คลาด — ปลายทางน่าจะขยับฐานเวลา"""


def load_feed_timezones(path: Path | None = None) -> dict:
    return json.loads((path or FEED_TZ_PATH).read_text(encoding="utf-8"))


def feed_zone(asset: str, *, registry: dict | None = None):
    """นาฬิกาที่ปลายทางใช้เขียนป้ายเวลาของหัวข้อนี้ — อ่านจากทะเบียนเท่านั้น ไม่มีค่าเดาสำรอง

    ทะเบียนรับได้สองรูป และความต่างสำคัญ:

    * `offset_minutes` — ระยะคงที่จาก UTC · ใช้กับตลาดที่ไม่ขยับตามฤดู
      (คริปโท = UTC · ฟอเร็กซ์/ทอง/น้ำมันของฟีดนี้ = UTC+10)
    * `timezone` — ชื่อเขตเวลาแบบ IANA · **จำเป็นเมื่อป้ายเวลาเดินตามเวลาตลาดที่มี DST**
      เช่น NVDA ที่ป้ายเป็นเวลานิวยอร์ก (ฤดูร้อน UTC−4 ฤดูหนาว UTC−5)
      ⇒ ใส่ตัวเลขตายตัวจะถูกครึ่งปีและผิดอีกครึ่งปีโดยไม่มีอะไรเตือน
    """
    book = registry or load_feed_timezones()
    entry = (book.get("assets") or {}).get(asset) or {}
    if entry.get("timezone"):
        return ZoneInfo(entry["timezone"])
    minutes = entry.get("offset_minutes", book.get("default_offset_minutes"))
    if minutes is None:
        raise FeedTimezoneUnknown(
            f"{asset}: ไม่รู้ว่าป้ายเวลาแท่งระหว่างวันของหัวข้อนี้เป็นเขตเวลาอะไร "
            f"— ต้องวัดแล้วลงทะเบียนใน {FEED_TZ_PATH.name} ก่อน "
            "ห้ามเดาว่าเป็นเวลาไทย (เดาผิดแล้วด่านแท่งปิดตัดสินผิด)")
    return timezone(timedelta(minutes=int(minutes)))


def feed_offset(asset: str, *, raw_at: str | None = None,
                registry: dict | None = None) -> timedelta:
    """ป้ายเวลาของหัวข้อนี้ล้ำ UTC ไปเท่าไร **ณ ช่วงเวลานั้น**

    ต้องผูกกับเวลาเพราะเขตเวลาที่มี DST ให้คำตอบไม่เท่ากันตามฤดู — ถามลอย ๆ
    โดยไม่บอกว่าเมื่อไหร่ จะได้คำตอบของ "ตอนนี้" ซึ่งใช้กับแท่งย้อนหลังไม่ได้
    """
    zone = feed_zone(asset, registry=registry)
    ref = (datetime.strptime(str(raw_at)[:19], "%Y-%m-%d %H:%M:%S")
           if raw_at else datetime.now())
    return ref.replace(tzinfo=zone).utcoffset()


def to_bangkok(raw_at: str, *, asset: str, registry: dict | None = None) -> datetime:
    """ป้ายเวลาดิบจากปลายทาง → เวลาไทยจริง

    ป้ายดิบคือ "เวลาผนังของนาฬิกาที่ปลายทางใช้" ⇒ ติดนาฬิกาเรือนนั้นให้ก่อน
    แล้วค่อยแปลงเป็นเวลาไทย · ทำที่นี่ที่เดียวในระบบ
    """
    naive = datetime.strptime(str(raw_at)[:19], "%Y-%m-%d %H:%M:%S")
    return naive.replace(tzinfo=feed_zone(asset, registry=registry)).astimezone(BAR_TZ)


def measure_offset(raw_newest_at: str, *, timeframe: str,
                   now: datetime | None = None) -> timedelta | None:
    """วัด offset สดจากแท่งใหม่สุด — คืน None เมื่อวัดไม่ได้ ไม่ใช่เดาให้

    หลักการ: **แท่งใหม่สุดที่ปลายทางส่งมาคือแท่งที่กำลังก่อตัว** (วัดยืนยัน 2026-08-13
    ทั้งสองหัวข้อ: ราคาปิดของแท่งใหม่สุดเท่ากับราคาล่าสุดของชุดรายวันเป๊ะ)
    ⇒ ป้ายของมันควรตรงกับช่องเวลาปัจจุบันในนาฬิกาของปลายทาง

    ⚠️ ใช้ไม่ได้ตอนตลาดปิด — เสาร์-อาทิตย์ของทอง แท่งใหม่สุดคือแท่งของวันศุกร์
    ค่าที่คำนวณได้จะมหาศาลและผิด ⇒ คืน None ให้ผู้เรียกใช้ค่าในทะเบียนแทน
    (นี่คือเหตุผลที่ระบบ **ไม่** ใช้ค่าที่วัดสดเป็นตัวจริง แต่ใช้เป็นตัวตรวจทะเบียน)
    """
    span = timedelta(minutes=spec_for(timeframe)["minutes"])
    moment = (now or datetime.now(tz=timezone.utc)).astimezone(timezone.utc)
    # ปัดนาฬิกาจริงลงเป็นต้นช่องแท่งปัจจุบัน แล้วเทียบกับป้ายที่ปลายทางเขียน
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    floored = epoch + (moment - epoch) // span * span
    naive = datetime.strptime(str(raw_newest_at)[:19], "%Y-%m-%d %H:%M:%S")
    return naive.replace(tzinfo=timezone.utc) - floored


def verify_offset(raw_newest_at: str, *, asset: str, timeframe: str,
                  now: datetime | None = None, registry: dict | None = None,
                  forming: bool | None = None) -> dict:
    """เทียบ offset ที่วัดสดกับทะเบียน — กันปลายทางขยับฐานเวลาแล้วเราผิดเงียบ

    คืนก้อนหลักฐานเสมอ (เก็บลง basis ให้ตรวจย้อนได้) และโยน `FeedTimezoneDrift`
    เมื่อค่าต่างเกินที่ยอมและทะเบียนสั่งให้หยุด

    การยอมให้คลาดได้ 1 ช่วงแท่งไม่ใช่ความหละหลวม — ปลายทางเผยแพร่แท่งช้ากว่าเวลา
    เปิดจริงไม่กี่นาที (วัดได้ 2026-08-13: แท่ง 06:30 โผล่ตอน 06:34) ⇒ บางจังหวะ
    แท่งใหม่สุดยังเป็นแท่งก่อนหน้าอยู่

    `forming` = ป้ายที่ส่งมาเป็นของแท่งที่ติดธง `forming: true` ไหม (ธงที่ปลายทาง
    เพิ่มให้ 2026-08-13) — การวัดตั้งสมมติฐานว่า "แท่งที่วัดคือแท่งของช่องเวลาปัจจุบัน"
    ซึ่งจริงแน่เฉพาะแท่ง forming · ฟีดสภาพคล่องบางแท่งปิดใหม่สุดตามหลังได้หลายช่วง
    (วัดจริง 08-13: wtiusd ตามหลัง 75 นาทีโดยไม่มีแท่ง forming ในชุดเลย)
    ⇒ `forming=False` แล้วค่าคลาดเกิน = **บันทึกแต่ไม่หยุดสาย** เพราะแยกไม่ออกว่า
    ฐานเวลาขยับหรือแค่ฟีดตามหลัง · `None` = ผู้เรียกไม่รู้ (โค้ด/เทสเก่า) ⇒ เข้มเท่าเดิม
    """
    book = registry or load_feed_timezones()
    rules = book.get("verification") or {}
    expected = feed_offset(asset, raw_at=raw_newest_at, registry=book)
    measured = measure_offset(raw_newest_at, timeframe=timeframe, now=now)
    span = timedelta(minutes=spec_for(timeframe)["minutes"])
    low, high = rules.get("plausible_range_minutes") or [-720, 840]

    evidence = {"asset": asset, "expected_offset_minutes": int(expected.total_seconds() // 60),
                "measured_offset_minutes": None, "verified": False,
                "reason": "วัดไม่ได้ในรอบนี้ — ใช้ค่าในทะเบียน"}
    if measured is None or not (timedelta(minutes=low) <= measured <= timedelta(minutes=high)):
        # ตลาดปิดหรือฟีดค้าง — วัดไม่ได้ ไม่ใช่ offset เปลี่ยน ⇒ เดินต่อด้วยค่าทะเบียน
        return evidence

    evidence["measured_offset_minutes"] = int(measured.total_seconds() // 60)
    drift = abs(measured - expected)
    if drift <= span * int(rules.get("tolerance_spans", 1)):
        evidence |= {"verified": True, "reason": "ค่าที่วัดสดตรงกับทะเบียน"}
        return evidence

    if forming is False:
        # วัดจากแท่งปิดแล้ว (ชุดนี้ไม่มีแท่ง forming เลย) — ค่าที่คลาดเกินอาจเป็นแค่
        # ฟีดตามหลัง ไม่ใช่ฐานเวลาขยับ ⇒ บันทึกไว้ให้ตรวจย้อน แต่ไม่หยุดสาย
        evidence["reason"] = (
            f"{asset}: วัดจากแท่งปิดแล้วได้ {evidence['measured_offset_minutes']} นาที "
            f"ต่างจากทะเบียน {evidence['expected_offset_minutes']} นาที — "
            "ชุดนี้ไม่มีแท่ง forming ให้เทียบนาฬิกา แยกไม่ออกว่าฐานเวลาขยับ"
            "หรือฟีดตามหลัง ⇒ ใช้ค่าทะเบียนต่อและบันทึกไว้")
        return evidence

    evidence["reason"] = (
        f"{asset}: offset ที่วัดสดได้ {evidence['measured_offset_minutes']} นาที "
        f"ต่างจากทะเบียน {evidence['expected_offset_minutes']} นาที "
        f"เกินที่ยอมให้คลาด ({int(span.total_seconds() // 60)} นาที) "
        f"— ปลายทางน่าจะขยับฐานเวลา ต้องวัดใหม่แล้วแก้ "
        f"{FEED_TZ_PATH.name} ห้ามปล่อยบทที่เวลาอาจผิด")
    if str(rules.get("on_mismatch", "raise")).lower() == "raise":
        raise FeedTimezoneDrift(evidence["reason"])
    return evidence


def rows_from_candles(candles, *, timeframe: str, asset: str,
                      registry: dict | None = None) -> list[dict]:
    """แปลงแท่งดิบเป็นรูปที่สายท่อของเราใช้

    **ช่อง `date` ยังเป็นวัน (YYYY-MM-DD) เหมือนเดิมโดยตั้งใจ** — ทั้งระบบ (พาดหัว
    บรรทัดวันที่ ชื่อไฟล์ภาพ ด่านความสอดคล้อง) อ่านช่องนี้อยู่ ถ้าเปลี่ยนเป็นเวลาเต็ม
    จะต้องไล่แก้ทุกจุดและพลาดจุดใดจุดหนึ่งแน่ ⇒ เพิ่มช่อง `at` ขึ้นมาใหม่แทน
    ใครอยากได้เวลาละเอียดก็อ่าน `at` ใครอยากได้วันก็อ่าน `date` เหมือนเดิม

    🕐 **จุดแปลงเขตเวลาของทั้งระบบอยู่ตรงนี้ที่เดียว** — ป้ายเวลาดิบของปลายทางเป็นเวลา
    ของนาฬิกาเรือนที่เราไม่ได้เลือก (และคนละเรือนกันในแต่ละหัวข้อ) ⇒ แปลงเป็นเวลาไทย
    ตั้งแต่รับเข้า แล้วทุกชั้นถัดไปทำงานบนเวลาไทยจริงโดยไม่ต้องรู้เรื่องนี้
    เก็บป้ายดิบไว้ในช่อง `at_feed` ด้วย เพื่อให้ตรวจย้อนได้ว่าแปลงมาจากอะไร
    """
    spec_for(timeframe)
    book = registry or load_feed_timezones()
    feed_zone(asset, registry=book)  # ไม่รู้จักหัวข้อ = หยุดตั้งแต่ต้น ไม่ใช่แปลงมั่ว
    rows = []
    for candle in candles:
        at = str(candle.get("t") or "")
        if len(at) < 19:
            raise IntradayUnavailable(
                f"แท่งระหว่างวันต้องมีเวลาเต็ม แต่ปลายทางส่ง '{at}' มา — "
                "ตรวจว่าขอ interval ถูกตัวหรือไม่")
        local = to_bangkok(at, asset=asset, registry=book)
        rows.append({
            "date": local.strftime("%Y-%m-%d"),
            "at": local.strftime("%Y-%m-%d %H:%M:%S"),
            "at_feed": at[:19],
            "open": float(candle["o"]), "high": float(candle["h"]),
            "low": float(candle["l"]), "close": float(candle["c"]),
        })
    rows.sort(key=lambda row: row["at"])
    return rows


def trim_to_closed(rows: list[dict], *, timeframe: str,
                   now: datetime | None = None) -> tuple[list[dict], list[str]]:
    """ตัดแท่งท้ายที่ยังเดินอยู่ออก คืน (rows ที่เหลือ, เวลาของแท่งที่ถูกตัด)

    ไล่จากท้ายเข้ามาเหมือนเส้นทางรายวัน เพราะปลายทางเคยส่งแท่งล่วงหน้ามาหลายแท่ง
    พร้อมกัน (บันทึกไว้ใน `candle_close.trim_to_closed`) — ตัดแท่งเดียวไม่พอ
    """
    span = timedelta(minutes=spec_for(timeframe)["minutes"])
    moment = now or datetime.now(tz=timezone.utc)
    kept, dropped = list(rows), []
    while kept and parse_at(kept[-1]["at"]) + span > moment:
        dropped.append(kept[-1]["at"])
        kept.pop()
    dropped.reverse()
    return kept, dropped


def basis_for(asset: str, bar_at: str, *, timeframe: str,
              now: datetime | None = None, dropped: list[str] | None = None) -> dict:
    """ก้อนหลักฐานของแท่งฐาน — ตัวสร้างเดียวที่ใช้ทั้งสายผลิตและเทส

    รูปก้อนตั้งใจให้ใกล้เคียงของรายวัน (`candle_close.basis_for`) เพื่อให้คนอ่าน
    หลักฐานสองสายเทียบกันได้ แต่ **คีย์ไม่ซ้ำกัน** เพื่อไม่ให้ด่านรายวันเผลอรับก้อนนี้ผ่าน
    """
    span = timedelta(minutes=spec_for(timeframe)["minutes"])
    close_at = parse_at(bar_at) + span
    return {
        "asset": asset,
        "timeframe": timeframe,
        "candle_state": "closed",
        "basis_bar_at": bar_at,
        "basis_session_date": bar_at[:10],
        "basis_close_at": close_at.isoformat(),
        "evaluated_at": (now or datetime.now(tz=timezone.utc)).isoformat(),
        "rule": f"แท่ง{spec_for(timeframe)['thai']}ปิดเมื่อพ้นเวลาเริ่มแท่งไป "
                f"{spec_for(timeframe)['short']} (เวลาไทย)",
        "dropped_forming_bars": list(dropped or []),
    }


def evaluate(rows: list[dict], *, asset: str, timeframe: str,
             now: datetime | None = None) -> tuple[list[dict], dict]:
    """คืน (rows ที่ทุกแท่งปิดแล้ว, ก้อนหลักฐาน) — คู่ขนานกับ `candle_close.evaluate`"""
    kept, dropped = trim_to_closed(rows, timeframe=timeframe, now=now)
    if not kept:
        raise NoClosedBar(
            f"{asset}: ไม่มีแท่ง{spec_for(timeframe)['thai']}ที่ปิดแล้วในชุดข้อมูลเลย "
            "— หยุดสายผลิต ห้ามเขียนคำว่า 'ปิด' ทับราคาที่ยังก่อตัว")
    return kept, basis_for(asset, kept[-1]["at"], timeframe=timeframe, now=now,
                           dropped=dropped)


def verify(basis: dict | None, *, asset: str, bar_at: str,
           now: datetime | None = None) -> str | None:
    """ด่าน fail-closed — คืน None เมื่อพิสูจน์ได้ว่าแท่งปิดแล้ว ไม่งั้นคืนเหตุที่ตก

    พิสูจน์ใหม่จากศูนย์เหมือนด่านรายวัน: คำนวณเวลาปิดของแท่งจากป้ายเวลากับความยาว
    กรอบ แล้วเทียบนาฬิกา ณ ตอนตรวจ — **ไม่อ่านค่าธง `candle_state` มาตัดสิน**
    ตั้งธงเองแล้วผ่านด่านไม่ได้
    """
    if not basis:
        return ("บทไม่มีก้อนหลักฐานสถานะแท่ง — พิสูจน์ไม่ได้ว่าแท่งล่าสุดปิดแล้ว "
                "จึงเขียนคำว่า 'ปิด' ทับราคาไม่ได้")
    if basis.get("basis_bar_at") != bar_at:
        return (f"ฐานแท่งของบท ({bar_at}) ไม่ตรงกับก้อนหลักฐาน "
                f"({basis.get('basis_bar_at')}) — บทกับข้อมูลพูดถึงคนละแท่ง")
    timeframe = basis.get("timeframe")
    if timeframe not in TIMEFRAMES:
        return f"ก้อนหลักฐานไม่บอกกรอบเวลาที่รู้จัก (ได้ '{timeframe}')"
    if basis.get("asset") != asset:
        return f"ก้อนหลักฐานเป็นของ {basis.get('asset')} ไม่ใช่ {asset}"
    span = timedelta(minutes=TIMEFRAMES[timeframe]["minutes"])
    close_at = parse_at(bar_at) + span
    moment = now or datetime.now(tz=timezone.utc)
    if moment < close_at:
        return (f"แท่ง {bar_at} ({TIMEFRAMES[timeframe]['thai']}) ปิดเวลา "
                f"{close_at.astimezone(BAR_TZ):%Y-%m-%d %H:%M} น. ซึ่งยังไม่ถึง")
    return None


def fetch_rows(asset: str, *, timeframe: str = "1h",
               outputsize: int = DEFAULT_OUTPUTSIZE,
               now: datetime | None = None,
               fetch_payload=wcb_series_source.fetch_payload) -> tuple[dict, list[dict], str]:
    """ดึงแท่งระหว่างวันของหัวข้อหนึ่ง — คืน (meta, rows, ป้ายแหล่ง)

    รูปคืนค่าตรงกับ `wcb_series_source.fetch_asset_rows` เพื่อให้เสียบแทนกันได้ใน
    สายผลิตโดยไม่ต้องแยกโค้ดสองทาง

    ⚠️ **ตรวจเขตเวลาก่อนแปลงเสมอ** — ป้ายเวลาดิบต้องผ่าน `verify_offset` ก่อนที่ใคร
    จะได้เห็นแถวที่แปลงแล้ว มิฉะนั้นปลายทางขยับฐานเวลาแล้วเราจะเขียนบทด้วยเวลาที่ผิด
    โดยไม่มีใครรู้ (บทเรียน 2026-08-13)
    """
    spec_for(timeframe)
    tag = wcb_series_source.ASSET_TAGS.get(asset, asset)
    url = wcb_series_source.build_url(tag, interval=timeframe, outputsize=outputsize)
    payload = fetch_payload(url)
    candles = list(wcb_series_source.candles_from_payload(payload, tag))
    if not candles:
        raise IntradayUnavailable(f"{asset}: ปลายทางไม่ส่งแท่ง {timeframe} มาเลย")

    book = load_feed_timezones()
    newest_raw = max(str(candle.get("t") or "") for candle in candles)
    # วัดจากแท่งที่ติดธง forming เท่านั้น — แท่งเดียวที่รู้แน่ว่าเป็นช่องเวลาปัจจุบัน
    # ของนาฬิกาปลายทาง (ธงมาตั้งแต่ 2026-08-13) · ไม่มีธงเลย = วัดสดไม่ได้รอบนี้
    # ใช้ค่าทะเบียนต่อ (เกิดจริงกับ wtiusd ที่สภาพคล่องบาง)
    forming_raw = max((str(candle.get("t") or "") for candle in candles
                       if candle.get("forming")), default="")
    timezone_check = verify_offset(forming_raw or newest_raw, asset=asset,
                                   timeframe=timeframe, now=now, registry=book,
                                   forming=bool(forming_raw))
    rows = rows_from_candles(candles, timeframe=timeframe, asset=asset, registry=book)
    if not rows:
        raise IntradayUnavailable(f"{asset}: ปลายทางไม่ส่งแท่ง {timeframe} มาเลย")
    return ({"asset": asset, "timeframe": timeframe, "count": len(rows),
             "timezone_check": timezone_check}, rows, f"WCB series API · {timeframe}")
