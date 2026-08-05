"""แหล่งข้อมูลจาก snapshot API ของ WorldClassBroker — สายสาธารณะ

ต่างจาก `tools/mt5_source.py` สองเรื่องที่เปลี่ยนวิธีเขียนบทความทั้งหมด:

1. **มีหลายกรอบเวลา** — 30min/1h/4h/1day มาพร้อมกันในก้อนเดียว สายเดิมมีแต่ D1
   จึงมีกฎห้ามภาษาชี้จังหวะระหว่างวัน · สายนี้ไม่ต้องมีกฎนั้น แต่ได้กฎวินัย TF มาแทน
   (1day + 4h เป็นหลัก · 1h/30min ประกอบและต้องเขียนกำกับ · ห้ามหยิบ TF ที่เข้าทางตัวเอง)
2. **อินดิเคเตอร์กับ pivot ผู้ให้บริการคำนวณมาให้** — เราไม่คำนวณเอง ⇒ ไม่มีสิทธิ์
   แต่งเลขใหม่ในชั้นบทความเลยแม้แต่ตัวเดียว ทุกเลขต้องยกมาจากก้อนตรง ๆ

**กับดักที่โมดูลนี้กันให้:** ไฟล์ snapshot ที่เซฟผ่านเชลล์บางตัวได้ข้อความไทยเป็น
ลำดับไบต์ UTF-8 ที่ถูกตีความเป็น latin-1 (mojibake) — ตัวเลขไม่กระทบแต่ชื่อรายการ
ในปฏิทินอ่านไม่ออก · `_mend()` ซ่อมให้ตอนอ่าน ไม่ใช่ตอนเขียนบทความ เพื่อให้จุดซ่อม
อยู่ที่เดียวและบทความไม่ต้องรู้เรื่องนี้
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


BANGKOK = timezone(timedelta(hours=7))
TIMEFRAMES = ("30min", "1h", "4h", "1day")

# โฮสต์ไม่ใช่ความลับ · **รหัสเป็นความลับ** และห้ามอยู่ในไฟล์นี้หรือไฟล์ใดในรีโป
# (คำสั่งผู้ใช้ 2026-08-05: ห้ามส่งออก ห้ามขึ้น git ใช้ในเครื่องเท่านั้น)
BASE_URL = "https://worldclassbroker.worldclassbroker-com.workers.dev/api/analysis/snapshot"
KEY_ENV = "WCB_SNAPSHOT_KEY"
KEY_FILE_ENV = "WCB_SNAPSHOT_KEY_FILE"

DEFAULT_TIMEOUT = 20
MAX_ATTEMPTS = 3
RETRY_SLEEP_SECONDS = 2.0

# **ต้องส่ง User-Agent เสมอ** — ปลายทางอยู่หลัง Cloudflare ซึ่งตอบ 403 ให้กับ
# ค่าเริ่มต้นของ urllib (`Python-urllib/3.x`) · วัดจริงเมื่อ 2026-08-05:
# ไม่ส่ง header เลย → 403 · ส่งแค่ Accept → 403 · ส่ง User-Agent ด้วย → 200
# ถ้าเจอ 403 อีกในอนาคต ให้สงสัยตรงนี้ก่อนสงสัยว่ารหัสหมดอายุ
USER_AGENT = "Mozilla/5.0 (compatible; WCB-analysis-bot/1.0)"
# ก้อนที่เก่ากว่านี้ใช้เขียนบทความไม่ได้ — ราคาระหว่างวันเปลี่ยนเร็วกว่านั้นมาก
MAX_AGE_MINUTES = 90

# ชื่อหัวข้อของสายท่อ → tag ที่ WCB API รู้จัก
# อยู่ที่นี่ที่เดียวเพราะ **ทั้งสอง endpoint ของ API เจ้านี้ใช้ทะเบียนชื่อเดียวกัน**
# (snapshot ที่โมดูลนี้ยิง และ series ที่ `wcb_series_source` ยิง)
# เคยแยกกันอยู่พักหนึ่งแล้วสายสาธารณะส่งชื่อ `btcusd` เข้าไปตรง ๆ ซึ่งปลายทางไม่รู้จัก
ASSET_TAGS = {
    "eurusd": "eurusd",
    "btcusd": "btc",
    "xauusd": "xauusd",
    "nvda": "nvda",
}


def tag_for(asset: str) -> str:
    """แปลงชื่อหัวข้อของสายท่อเป็น tag ของ API — ไม่รู้จัก = ฟ้อง ไม่ส่งชื่อดิบไปเดา"""
    try:
        return ASSET_TAGS[asset]
    except KeyError as exc:
        raise SnapshotUnusable(
            f"ยังไม่ได้แมปหัวข้อ {asset} เข้ากับ tag ของ WCB API — "
            f"tag ที่รู้จักตอนนี้: {', '.join(sorted(ASSET_TAGS.values()))}"
        ) from exc


class SnapshotUnusable(RuntimeError):
    """ก้อนข้อมูลใช้เขียนบทความไม่ได้ — ต้องหยุด ห้ามเขียนต่อจากก้อนที่ไม่ครบ"""


class SnapshotStale(RuntimeError):
    """ได้ก้อนมาแต่เก่าเกินกว่าจะใช้ตัดสินใจ — บทเรียนเดียวกับ `mt5_source.MT5StaleData`

    ดึงสำเร็จไม่เท่ากับข้อมูลสด ปลายทางที่ค้างจะคืนก้อนเดิมเรื่อย ๆ โดยไม่มี error
    ถ้าปล่อยผ่าน บทความจะอ้างราคาที่ตลาดทิ้งไปแล้วโดยไม่มีใครรู้
    """


class KeyMissing(RuntimeError):
    """ไม่มีรหัสเข้าถึง API — ต้องตั้งค่าในเครื่อง ห้ามฝังไว้ในโค้ด"""


def _resolve_key(explicit: str | None = None) -> str:
    """หารหัสจากในเครื่องเท่านั้น ตามลำดับ: อาร์กิวเมนต์ → ตัวแปรสภาพแวดล้อม → ไฟล์

    **ไม่มีค่าตั้งต้น** โดยตั้งใจ · ถ้าเผลอใส่ค่าตั้งต้นไว้สักครั้ง รหัสจะติดไปกับรีโป
    ตลอดไปแม้จะลบทีหลัง เพราะประวัติ git เก็บไว้หมด
    """
    if explicit:
        return explicit.strip()
    from_env = os.environ.get(KEY_ENV)
    if from_env:
        return from_env.strip()
    path = os.environ.get(KEY_FILE_ENV)
    if path and Path(path).is_file():
        return Path(path).read_text(encoding="utf-8").strip()
    raise KeyMissing(
        f"ไม่พบรหัสเข้าถึง snapshot API — ตั้งค่า {KEY_ENV} หรือชี้ {KEY_FILE_ENV} "
        "ไปที่ไฟล์รหัสในเครื่อง (ห้ามเก็บรหัสไว้ในรีโปหรือส่งออกนอกเครื่อง)")


def redact(text: str, secret: str) -> str:
    """ลบรหัสออกจากข้อความก่อนแสดงผลหรือบันทึก log

    urllib ใส่ URL เต็มลงในข้อความ error เอง ⇒ ถ้าไม่กรอง รหัสจะโผล่ใน traceback
    ที่คนมักคัดลอกไปแปะถามคนอื่น ซึ่งเป็นทางหลุดที่พบบ่อยที่สุดของรหัสแบบใส่ใน query
    """
    return text.replace(secret, "***") if secret else text


def build_request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})


def fetch_payload(asset: str = "xauusd", *, key: str | None = None, base_url: str = BASE_URL,
                  timeout: int = DEFAULT_TIMEOUT) -> dict:
    """คืน **ก้อนดิบ** ตามที่ปลายทางส่งมา — ยังไม่แปลงรูป

    แยกออกมาเพราะผู้เรียกที่อยากเก็บก้อนไว้ตรวจย้อนกลับต้องได้รูปเดิมเป๊ะ
    ก้อนที่แปลงแล้วเอากลับเข้า `normalize()` ไม่ได้ และด่านตรวจบทความก็อ่านไม่ออก
    (บั๊กที่เจอตอนรันจริงครั้งแรก 2026-08-05 — `--save-snapshot` เคยเก็บก้อนที่แปลงแล้ว)
    """
    secret = _resolve_key(key)
    url = f"{base_url}?asset={asset}&k={secret}"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(build_request(url), timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            message = redact(str(error), secret)
            # 4xx คือคำตอบว่า "คำขอผิด" ไม่ใช่ปัญหาชั่วคราว — ยิงซ้ำได้ผลเดิมและ
            # เป็นการรบกวนปลายทางเปล่า ๆ · ยกเว้น 429 ที่แปลว่าให้รอแล้วค่อยมาใหม่
            code = getattr(error, "code", None)
            if code and 400 <= code < 500 and code != 429:
                raise SnapshotUnusable(f"ปลายทางปฏิเสธคำขอ ({code}): {message}") from None
            if attempt == MAX_ATTEMPTS:
                raise SnapshotUnusable(
                    f"ดึง snapshot ไม่สำเร็จหลังพยายาม {MAX_ATTEMPTS} ครั้ง: {message}") from None
            time.sleep(RETRY_SLEEP_SECONDS)
    return payload


def ensure_fresh(evidence: dict, max_age_minutes: int = MAX_AGE_MINUTES) -> dict:
    """ด่านความสด — คืน evidence เดิมเมื่อผ่าน โยนเมื่อไม่ผ่าน ไม่มีทางเลือกที่สาม"""
    age = age_minutes(evidence)
    if age is not None and age > max_age_minutes:
        raise SnapshotStale(
            f"ก้อนข้อมูลเก่า {int(age)} นาที เกินเพดาน {max_age_minutes} นาที — "
            "หยุดสายท่อ ห้ามเขียนบทความจากราคาที่ตลาดทิ้งไปแล้ว")
    return evidence


def fetch(asset: str = "xauusd", *, key: str | None = None, base_url: str = BASE_URL,
          timeout: int = DEFAULT_TIMEOUT, max_age_minutes: int = MAX_AGE_MINUTES) -> dict:
    """ดึงสดแล้วคืน evidence pack ที่ผ่านด่านความสดแล้ว — ทางที่ผู้เรียกทั่วไปควรใช้"""
    payload = fetch_payload(asset, key=key, base_url=base_url, timeout=timeout)
    return ensure_fresh(normalize(payload), max_age_minutes)


def age_minutes(evidence: dict) -> float | None:
    stamp = evidence.get("generated_at")
    if not stamp:
        return None
    generated = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - generated).total_seconds() / 60


def _mend(value):
    """ซ่อมข้อความไทยที่ถูกบันทึกเป็น latin-1 ของไบต์ UTF-8"""
    if not isinstance(value, str):
        return value
    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def _indicators(block: dict) -> dict:
    """แปลงลิสต์อินดิเคเตอร์เป็น dict คีย์ตามชื่อ เพื่อให้ชั้นบทความหยิบตรงตัวได้"""
    result = {}
    for item in (block or {}).get("indicators") or []:
        name = item.get("name")
        if name:
            result[name] = {"signal": item.get("signal"), "value": item.get("value")}
    return result


def load(path: Path | str) -> dict:
    """อ่านไฟล์ snapshot แล้วคืน evidence pack ที่ชั้นนักเขียนใช้ได้ทันที"""
    raw = Path(path).read_text(encoding="utf-8-sig")
    return normalize(json.loads(raw))


def normalize(payload: dict) -> dict:
    if not payload.get("ok"):
        raise SnapshotUnusable("snapshot ตอบ ok:false — ห้ามเขียนบทความจากก้อนนี้")
    quote = payload.get("quote") or {}
    if quote.get("price") is None:
        raise SnapshotUnusable("snapshot ไม่มีราคาล่าสุด — ห้ามเขียนบทความจากก้อนนี้")

    generated = payload.get("generatedAt") or ""
    local = None
    if generated:
        stamp = datetime.fromisoformat(generated.replace("Z", "+00:00"))
        local = stamp.astimezone(BANGKOK)

    by_tf = {}
    for name in TIMEFRAMES:
        block = (payload.get("technicalsByTf") or {}).get(name) or {}
        if block:
            by_tf[name] = {
                "summary": block.get("summary"),
                "counts": block.get("counts") or {},
                "indicators": _indicators(block),
                "pivots": block.get("pivots") or {},
                "price": block.get("price"),
            }

    daily = payload.get("technicals") or {}
    calendar = []
    for event in ((payload.get("calendar") or {}).get("events") or []):
        calendar.append({
            "at": event.get("at"),
            "country": event.get("country"),
            "impact": event.get("impact"),
            "title": _mend(event.get("title") or ""),
            "previous": event.get("previous"),
            "forecast": event.get("forecast"),
            "actual": event.get("actual"),
        })

    news = []
    for item in (payload.get("news") or []):
        news.append({"title": _mend(item.get("title") or ""),
                     "published_at": item.get("published_at")})

    return {
        "asset": payload.get("asset"),
        "generated_at": generated,
        "local_time": local.strftime("%H:%M") if local else None,
        "local_date": local.strftime("%Y-%m-%d") if local else None,
        "quote": quote,
        "performance": payload.get("performance") or {},
        "daily": {
            "summary": daily.get("summary"),
            "counts": daily.get("counts") or {},
            "indicators": _indicators(daily),
            "pivots": daily.get("pivots") or {},
        },
        "by_tf": by_tf,
        "recent_daily": payload.get("recentDaily") or [],
        "recent_by_tf": payload.get("recentByTf") or {},
        "news": news,
        "calendar": calendar,
    }


def pivot_values(evidence: dict) -> list[float]:
    """ค่า pivot ทุกตัวทุกกรอบเวลา — ชุดเดียวที่หมุดกราฟมีสิทธิ์อ้างถึง"""
    values: list[float] = []
    groups = [evidence["daily"]["pivots"]]
    groups += [block["pivots"] for block in evidence["by_tf"].values()]
    for group in groups:
        for key in ("p", "r1", "r2", "r3", "s1", "s2", "s3"):
            if (group or {}).get(key) is not None:
                values.append(float(group[key]))
    return values


def upcoming(evidence: dict, *, impacts=("High", "Medium"), limit: int | None = None) -> list[dict]:
    """รายการปฏิทินที่ยังไม่ถึง เรียงตามเวลา — ฐานของหัวข้อปัจจัยพื้นฐานทุกสไตล์"""
    cutoff = evidence.get("local_date") or ""
    items = [event for event in evidence["calendar"]
             if event["impact"] in impacts and str(event["at"] or "")[:10] >= cutoff]
    items.sort(key=lambda event: str(event["at"] or ""))
    return items[:limit] if limit else items
