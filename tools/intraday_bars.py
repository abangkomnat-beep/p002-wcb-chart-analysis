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

⚠️ **เวลาที่ปลายทางส่งมาไม่มี timezone กำกับ** — วัดแล้วตรงกับเวลาไทย (แท่ง 4h
เรียงที่ 03:00/07:00/11:00/15:00/19:00 ซึ่งคือรอบ UTC+7) ⇒ ตีความเป็นเวลาไทยที่นี่
ที่เดียว ถ้าปลายทางเปลี่ยนฐานเวลาเมื่อไหร่ แก้ที่ `BAR_TZ` ตัวเดียว
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import wcb_series_source, wcb_source  # noqa: E402

BAR_TZ = wcb_source.BANGKOK

# กรอบเวลาที่บทเช้ารองรับ — ชื่อคีย์ตรงกับพารามิเตอร์ `interval` ของปลายทาง
TIMEFRAMES = {
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
    """'2026-08-10 19:00:00' → datetime ที่มี timezone ไทยติดมาด้วย"""
    return datetime.strptime(str(text)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=BAR_TZ)


def rows_from_candles(candles, *, timeframe: str) -> list[dict]:
    """แปลงแท่งดิบเป็นรูปที่สายท่อของเราใช้

    **ช่อง `date` ยังเป็นวัน (YYYY-MM-DD) เหมือนเดิมโดยตั้งใจ** — ทั้งระบบ (พาดหัว
    บรรทัดวันที่ ชื่อไฟล์ภาพ ด่านความสอดคล้อง) อ่านช่องนี้อยู่ ถ้าเปลี่ยนเป็นเวลาเต็ม
    จะต้องไล่แก้ทุกจุดและพลาดจุดใดจุดหนึ่งแน่ ⇒ เพิ่มช่อง `at` ขึ้นมาใหม่แทน
    ใครอยากได้เวลาละเอียดก็อ่าน `at` ใครอยากได้วันก็อ่าน `date` เหมือนเดิม
    """
    spec_for(timeframe)
    rows = []
    for candle in candles:
        at = str(candle.get("t") or "")
        if len(at) < 19:
            raise IntradayUnavailable(
                f"แท่งระหว่างวันต้องมีเวลาเต็ม แต่ปลายทางส่ง '{at}' มา — "
                "ตรวจว่าขอ interval ถูกตัวหรือไม่")
        rows.append({
            "date": at[:10],
            "at": at[:19],
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
               fetch_payload=wcb_series_source.fetch_payload) -> tuple[dict, list[dict], str]:
    """ดึงแท่งระหว่างวันของหัวข้อหนึ่ง — คืน (meta, rows, ป้ายแหล่ง)

    รูปคืนค่าตรงกับ `wcb_series_source.fetch_asset_rows` เพื่อให้เสียบแทนกันได้ใน
    สายผลิตโดยไม่ต้องแยกโค้ดสองทาง
    """
    spec_for(timeframe)
    tag = wcb_series_source.ASSET_TAGS.get(asset, asset)
    url = wcb_series_source.build_url(tag, interval=timeframe, outputsize=outputsize)
    payload = fetch_payload(url)
    rows = rows_from_candles(
        wcb_series_source.candles_from_payload(payload, tag), timeframe=timeframe)
    if not rows:
        raise IntradayUnavailable(f"{asset}: ปลายทางไม่ส่งแท่ง {timeframe} มาเลย")
    return ({"asset": asset, "timeframe": timeframe, "count": len(rows)}, rows,
            f"WCB series API · {timeframe}")
