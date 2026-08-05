"""แหล่งแท่งราคา D1 จาก series endpoint ของ WCB — แหล่งเดียวของสายภายใน

เหตุผลที่มีโมดูลนี้: แหล่งเดิมคือ MetaTrader 5 ซึ่งบังคับให้ผู้รับ repo ต้องติดตั้ง
terminal เปิดบัญชีโบรก และอยู่บน Windows · endpoint นี้เรียกผ่าน HTTP ธรรมดา
**ไม่ต้องใช้รหัส** และรันได้ทุกระบบปฏิบัติการ (ถอด MT5 ออกครบ 2026-08-05)

คืน rows ตามสัญญาเดิมของสายท่อเป๊ะ ๆ (`date` + OHLC) เพื่อให้เสียบแทนของเดิมได้
โดยไม่ต้องแตะ integrity / levels / pivots / risk_auditor — ข้อนี้สำคัญกว่าที่เห็น
เพราะเกณฑ์ความเสี่ยงของ `risk_auditor` วัดมาจากข้อมูลจริง 484 วัน ถ้าเปลี่ยนไปใช้
pivot สำเร็จรูปที่ API คำนวณมาให้ เกณฑ์ชุดนั้นจะใช้ไม่ได้ทันทีทั้งชุด
⇒ สายภายในเอา "แท่งดิบ" จาก API มาเข้าเครื่องคำนวณเดิม ไม่เอาค่าสำเร็จรูป
   ส่วนค่าสำเร็จรูปยังใช้ในสายสาธารณะ A/B/C ตามเดิม คนละสายคนละหน้าที่

สามกับดักที่โมดูลนี้กันโดยตรง (พบจากการวัดจริง 2026-08-05):

1. **outputsize ไม่ใช่จำนวนแท่งที่จะได้** — ขอ 200 แล้วได้ 143 แท่งในคู่เงินและทองคำ
   (ปลายทางตัดเสาร์อาทิตย์ออกหลังนับ) แต่หุ้นกับคริปโทขอ 200 ได้ 200 พอดี
   จึงต้อง**ขอเผื่อแล้วตัดท้าย** ไม่ใช่ขอเท่าที่ต้องการแล้วเชื่อว่าได้ครบ

2. **ข้อมูลค้างเงียบ** — ได้แท่งครบจำนวนไม่ได้แปลว่าแท่งล่าสุดสด
   ไม่สดครบจำนวนรอบ = raise SeriesStaleData ไม่ใช่ warning และไม่คืนของเก่า

3. **Cloudflare ปิดประตูใส่ urllib** — ไม่ใส่ User-Agent ได้ 403 ทุกครั้ง
   ใช้ตัวสร้างคำขอร่วมกับ `wcb_source` เพื่อไม่ให้แก้ที่เดียวแล้วลืมอีกที่
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone

from tools import market_calendar, wcb_source


BASE_URL = "https://worldclassbroker.worldclassbroker-com.workers.dev/api/md"
PROVIDER_KEY = "wcb_series_api"

# ต้องคลุม `minimum_completed_bars.sma200` = 200 แท่งที่ปิดแล้ว **บวกส่วนเผื่อ**
# สำหรับแท่งที่ถูกคัดออกด้วยปฏิทินวันหยุดและแท่งวันนี้ที่ยังไม่ปิด
#
# เดิมเป็น 130 ซึ่งต่ำกว่า 200 อยู่แล้วตั้งแต่ต้น ⇒ `sma200` ขึ้น `insufficient_data`
# ทุกหัวข้อทุกวัน **ไม่ใช่เพราะปลายทางไม่มีข้อมูล** (ให้ได้ถึง 4,857 แท่งย้อนถึงปี 2007)
# แต่เพราะค่าตั้งต้นฝั่งเราเอง · MA200 เป็นเส้นที่บทวิเคราะห์อ้างบ่อยที่สุดเส้นหนึ่ง
#
# วัดผลก่อนเปลี่ยนแล้วด้วยสายท่อจริงทั้งสี่หัวข้อ (2026-08-05): เทียบ 130 กับ 420
# ⇒ แผนการเทรด **ไม่เปลี่ยน** (NVDA ที่ตลาดปิดอยู่ต่างกันศูนย์ช่อง · อีกสามตัวต่างแค่
# `reference_price` ที่ราคาสดขยับระหว่างสองรอบ) · ตารางระดับ **เพิ่ม `sma200`
# มาหนึ่งเส้น ไม่มีเส้นเดิมหายและไม่มีเส้นเดิมเปลี่ยนค่า**
# ⇒ เกณฑ์ความเสี่ยงที่ผู้ใช้ล็อกไว้ (`minimum_rr` = 1.2) ยังยืนบนฐานเดิม
#
# `OVERSIZE_FACTOR` คูณสองอีกชั้นตอนยิงจริง จึงขอปลายทางไป 840 แท่ง (เพดาน 5,000)
DEFAULT_COUNT = 420
MAX_BAR_AGE_DAYS = 3
MAX_ATTEMPTS = 3
RETRY_SLEEP_SECONDS = 1.5

# เพดานของปลายทางตามคู่มือ — ขอเกินนี้ไม่ได้อะไรเพิ่ม
MAX_OUTPUTSIZE = 5000
# ตัวคูณเผื่อวันหยุด: หนึ่งปีปฏิทินมีวันทำการราว 70% ขอสองเท่าจึงเหลือเฟือทุกสินทรัพย์
OVERSIZE_FACTOR = 2

INTERVAL_D1 = "1day"

# ทะเบียนชื่อหัวข้ออยู่ที่ `wcb_source` ที่เดียว — endpoint ทั้งสองของ API เจ้านี้ใช้ชุดเดียวกัน
# `btcusd` เป็นตัวเดียวที่ชื่อไม่ตรง ปล่อยผ่านไปจะได้ 404 เงียบ ๆ ตอนรันจริง
ASSET_TAGS = wcb_source.ASSET_TAGS


class SeriesUnavailable(RuntimeError):
    """ดึงแท่งไม่ได้หรือได้ไม่ครบ — ห้ามเขียนบทความต่อ ให้หยุดสายท่อ"""


class SeriesStaleData(RuntimeError):
    """ด่านความสดไม่ผ่าน — ได้แท่งมาแต่แท่งล่าสุดเก่าเกินกว่าจะใช้ตัดสินใจ"""


def build_url(tag: str, *, interval: str = INTERVAL_D1, outputsize: int = DEFAULT_COUNT,
              base_url: str = BASE_URL) -> str:
    size = max(1, min(int(outputsize), MAX_OUTPUTSIZE))
    return f"{base_url}?kind=series&asset={tag}&interval={interval}&outputsize={size}"


def fetch_payload(url: str, *, timeout: int = 30, opener=None) -> dict:
    """ยิงหนึ่งครั้ง คืน payload ดิบ — 4xx ที่ไม่ใช่ 429 โยนทิ้งทันทีไม่ลองซ้ำ"""
    request = wcb_source.build_request(url)
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if 400 <= exc.code < 500 and exc.code != 429:
            raise SeriesUnavailable(
                f"ปลายทางตอบ {exc.code} สำหรับ {url} — ยิงซ้ำได้ผลเดิม "
                "ตรวจชื่อ tag สินทรัพย์กับพารามิเตอร์ก่อน"
            ) from exc
        raise


def candles_from_payload(payload: dict, tag: str) -> list[dict]:
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise SeriesUnavailable(f"{tag}: ปลายทางตอบว่าไม่สำเร็จ · payload={str(payload)[:200]}")
    candles = payload.get("candles")
    if not isinstance(candles, list) or not candles:
        raise SeriesUnavailable(f"{tag}: ปลายทางไม่คืนแท่งเลย")
    return candles


def rows_from_candles(candles) -> tuple[list[dict], list[str]]:
    """แปลงแท่งของ API เป็น rows ของสายท่อ + รายชื่อ session ที่ค่าว่าง

    ค่า 0 หรือ None ถือเป็นแท่งว่าง — บันทึกไว้ให้ด่านตรวจเห็น ไม่ข้ามเงียบ ๆ
    (ธรรมเนียมเดิมของสายท่อ เพื่อให้รายงานของทุกแหล่งเทียบกันได้)
    """
    rows: list[dict] = []
    empty_sessions: list[str] = []
    for candle in candles:
        session_date = str(candle.get("t", ""))[:10]
        if not session_date:
            continue
        values = {
            "open": candle.get("o"), "high": candle.get("h"),
            "low": candle.get("l"), "close": candle.get("c"),
        }
        if any(value is None or float(value) == 0.0 for value in values.values()):
            empty_sessions.append(session_date)
            continue
        rows.append({
            "date": session_date,
            **{key: float(value) for key, value in values.items()},
        })
    rows.sort(key=lambda row: row["date"])
    return rows, empty_sessions


def drop_holiday_candles(rows: list[dict], calendar) -> tuple[list[dict], list[str]]:
    """คัดแท่งที่ตกวันหยุดตามปฏิทินของสายท่อออก คืน (rows ที่เหลือ, วันที่ถูกคัด)

    ทำไมต้องคัด: ปลายทางของ WCB ให้แท่งบางวันที่ปฏิทินของเราถือว่าตลาดปิด
    เช่นทองคำวัน Good Friday 2026-04-03 ซึ่ง MT5 ไม่มีแท่ง (ทานสอบแล้ว 2026-08-05
    ชุด 130 แท่งทับกันทุกวันยกเว้นวันนี้วันเดียว) แท่งนั้นแคบผิดปกติ — กว้างราว 12 ดอลลาร์
    เทียบกับวันก่อนหน้าที่กว้าง 243 ดอลลาร์ ⇒ เป็นการซื้อขายบางตาไม่ใช่ session เต็มวัน

    ถ้าปล่อยไว้ ด่าน `integrity` จะกั้นทั้งหัวข้อด้วย `unexpected_holiday_candle` ทุกปี
    และถ้าแก้ด้วยการผ่อนด่านแทน ฐานคำนวณ Pivot จะเปลี่ยนไปจากที่วัดเกณฑ์ความเสี่ยงไว้
    การคัดออกจึงเป็นทางที่ทำให้สองแหล่งให้ชุด session เดียวกันเป๊ะ = ทานสอบกันได้ต่อไป
    """
    if calendar is None:
        return rows, []
    kept: list[dict] = []
    dropped: list[str] = []
    for row in rows:
        if calendar.classify(row["date"]) == "holiday":
            dropped.append(row["date"])
        else:
            kept.append(row)
    return kept, dropped


def bar_age_days(session_date: str, reference_date: date) -> int:
    return (reference_date - date.fromisoformat(session_date)).days


def fetch_series_rows(
    tag: str,
    count: int = DEFAULT_COUNT,
    *,
    interval: str = INTERVAL_D1,
    now: datetime | None = None,
    max_age_days: int = MAX_BAR_AGE_DAYS,
    attempts: int = MAX_ATTEMPTS,
    sleep_seconds: float = RETRY_SLEEP_SECONDS,
    base_url: str = BASE_URL,
    timeout: int = 30,
    opener=None,
    calendar=None,
) -> tuple[dict, list[dict], str]:
    """คืน (meta, rows, source) — ลายเซ็นเดิมของตัวดึงแท่งราคาในสายท่อ

    ส่ง `calendar` มาด้วยเมื่อรู้ว่าหัวข้อนี้ใช้ปฏิทินตลาดใด — แท่งที่ตกวันหยุด
    ตามปฏิทินจะถูกคัดออกและบันทึกไว้ใน meta ไม่ใช่ทิ้งเงียบ (ดูเหตุผลที่ `drop_holiday_candles`)
    """
    now = now or datetime.now(tz=timezone.utc)
    today = now.date()
    requested_size = min(count * OVERSIZE_FACTOR, MAX_OUTPUTSIZE)
    url = build_url(tag, interval=interval, outputsize=requested_size, base_url=base_url)

    rows: list[dict] = []
    empty_sessions: list[str] = []
    last_seen: str | None = None
    age: int | None = None
    attempt = 0

    for attempt in range(1, attempts + 1):
        payload = fetch_payload(url, timeout=timeout, opener=opener)
        candles = candles_from_payload(payload, tag)
        rows, empty_sessions = rows_from_candles(candles)
        rows, holiday_sessions = drop_holiday_candles(rows, calendar)
        if not rows:
            if attempt < attempts:
                time.sleep(sleep_seconds)
                continue
            raise SeriesUnavailable(f"{tag}: ทุกแท่งที่ได้มาเป็นค่าว่าง")

        last_seen = rows[-1]["date"]
        age = bar_age_days(last_seen, today)
        if age <= max_age_days:
            break
        if attempt < attempts:
            time.sleep(sleep_seconds)

    if age is None or age > max_age_days:
        raise SeriesStaleData(
            f"{tag}: แท่งล่าสุดคือ {last_seen} เก่า {age} วัน เกินเพดาน {max_age_days} วัน "
            f"หลังลอง {attempts} รอบ — หยุดสายท่อ ไม่เขียนบทความจากข้อมูลค้าง "
            "(ถ้าเป็นวันหยุดยาวจริง ให้สั่งด้วย --max-bar-age-days พร้อมระบุเหตุผล)"
        )

    available = len(rows)
    if available < count:
        raise SeriesUnavailable(
            f"{tag}: ขอ {count} แท่ง (ยิง outputsize={requested_size}) แต่ได้ {available} แท่ง — "
            "ไม่พอสำหรับเครื่องคำนวณระดับราคา ให้เพิ่มตัวคูณเผื่อหรือลดจำนวนแท่งที่ต้องการ"
        )
    rows = rows[-count:]

    meta = {
        "provider": PROVIDER_KEY,
        "endpoint": base_url,
        "asset_tag": tag,
        "symbol": payload.get("symbol"),
        "timeframe": payload.get("interval", interval),
        "requested_count": count,
        "requested_outputsize": requested_size,
        "returned_count": available,
        "used_count": len(rows),
        "reference_date": today.isoformat(),
        "last_bar_session_date": last_seen,
        "last_bar_age_days": age,
        "freshness_max_age_days": max_age_days,
        "freshness_attempts_used": attempt,
        "freshness_method": "ยิงซ้ำจนแท่งล่าสุดสด เทียบกับวันที่ UTC",
        "retrieved_at": now.isoformat(timespec="seconds"),
        "warnings": (
            [f"คัดแท่งวันหยุดตามปฏิทินออก {len(holiday_sessions)} วัน: "
             f"{', '.join(holiday_sessions)}"] if holiday_sessions else []
        ),
        "p002_empty_sessions": empty_sessions,
        "p002_holiday_candles_dropped": holiday_sessions,
    }
    source = f"WCB series API · {payload.get('symbol', tag)} {meta['timeframe']}"
    return meta, rows, source


def fetch_asset_rows(asset: str, **kwargs) -> tuple[dict, list[dict], str]:
    """เรียกด้วยชื่อหัวข้อของสายท่อ (eurusd / btcusd / xauusd / nvda)

    ทางนี้รู้ว่าหัวข้อใช้ปฏิทินตลาดใด จึงส่งปฏิทินให้ตัวคัดแท่งวันหยุดด้วยเสมอ
    """
    try:
        tag = wcb_source.tag_for(asset)
    except wcb_source.SnapshotUnusable as exc:
        raise SeriesUnavailable(str(exc)) from exc
    kwargs.setdefault("calendar", market_calendar.for_asset(asset))
    return fetch_series_rows(tag, **kwargs)
