"""แหล่งข้อมูลราคาจาก MetaTrader 5 — แทน Yahoo Finance เป็นทางหลักของสายท่อ

คืน rows รูปแบบเดียวกับ pilot_generator.fetch_yahoo_rows() เพื่อให้เสียบแทนกันได้
โดยไม่ต้องแก้ integrity / levels / chart_renderer / article_builder

สองกับดักที่โมดูลนี้มีหน้าที่กันโดยตรง (พบจากการทดสอบจริง 2026-08-04):

1. **ข้อมูลค้างเงียบ** — copy_rates_from_pos() เคยคืนแท่งครบจำนวนแต่แท่งล่าสุดเก่า 1 เดือน
   โดยไม่มี error ใด ๆ  โมดูลนี้จึงใช้ copy_rates_from(now) และวนซ้ำจนแท่งล่าสุดสด
   ไม่สดครบจำนวนรอบ = raise MT5StaleData ไม่ใช่ warning และไม่คืนของเก่า

2. **เวลาเซิร์ฟเวอร์ไม่ใช่ UTC** — โบรกอยู่ GMT+2/+3 แท่ง D1 จึงปิดตามเวลาเซิร์ฟเวอร์
   MT5 ประทับ epoch ของแท่งเป็น "เวลาเซิร์ฟเวอร์ที่ห่อในรูป epoch" อยู่แล้ว
   session date จึงต้องอ่านจาก epoch นั้นตรง ๆ **ห้ามแปลงกลับเป็น UTC จริง**
   ถ้าแปลง วันที่จะเลื่อนถอยหนึ่งวันทั้งชุด = บั๊กวันฐาน Pivot แบบเดียวกับที่แก้ไปเมื่อ 08-03

หมายเหตุการออกแบบ: offset ของเซิร์ฟเวอร์ถูกตรวจตอน runtime เพื่อ "บันทึกและเฝ้าระวัง"
ไม่ใช่เพื่อนำไปลบออกจากเวลาแท่ง — ค่า session date ไม่ได้พึ่ง offset จึงไม่พังเวลาโบรกสลับ DST
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone


DEFAULT_TERMINAL = r"C:\Program Files\MetaTrader 5\terminal64.exe"
PROVIDER_KEY = "mt5_raw_trading"
EXPECTED_BROKER = "Raw Trading Ltd"

DEFAULT_COUNT = 130
MAX_BAR_AGE_DAYS = 3
MAX_ATTEMPTS = 3
RETRY_SLEEP_SECONDS = 1.5

# โบรก MT5 ตั้งเซิร์ฟเวอร์ที่ GMT+2/+3 เพื่อให้หนึ่งสัปดาห์ได้ 5 แท่งพอดี
# หลุดกรอบนี้ = ธรรมเนียมขอบแท่งเปลี่ยน ต้องทบทวนก่อนเชื่อ session date
PLAUSIBLE_OFFSET_HOURS = (1.0, 4.0)

# สัญลักษณ์ 24/7 ใช้เป็นนาฬิกาอ้างอิง — วันหยุดสุดสัปดาห์ forex ไม่มี tick ใหม่
# ถ้าใช้ tick ของ EURUSD วัด offset วันอาทิตย์จะได้ค่าเพี้ยนเป็นหลักสิบชั่วโมง
CLOCK_SYMBOL = "BTCUSD"

SYMBOLS = {
    "eurusd": "EURUSD",
    "btcusd": "BTCUSD",
    "xauusd": "XAUUSD",
}


class MT5Unavailable(RuntimeError):
    """terminal ไม่พร้อม — ห้ามเขียนบทความต่อจากข้อมูลเก่า ให้หยุดสายท่อ"""


class MT5StaleData(RuntimeError):
    """ด่านความสดไม่ผ่าน — ได้ข้อมูลมาแต่เก่าเกินกว่าจะใช้ตัดสินใจ"""


def session_date_from_server_epoch(epoch) -> str:
    """แปลง epoch ของแท่ง MT5 เป็น session date

    MT5 ส่ง epoch ที่ "ห่อเวลาเซิร์ฟเวอร์ไว้ในรูป UTC" มาแล้ว การอ่านด้วย tz=utc
    จึงได้เวลาหน้าปัดของเซิร์ฟเวอร์ ซึ่งคือขอบวันของแท่ง D1 ตรงตามที่ต้องการ

    ห้ามลบ offset ออกจากค่านี้ — แท่งที่ประทับ 2026-08-04 00:00 คือ session ของวันที่
    2026-08-04 ถ้าแปลงเป็น UTC จริงจะกลายเป็น 2026-08-03 21:00 แล้ววันฐาน Pivot เลื่อนทั้งชุด
    """
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).date().isoformat()


def load_client(terminal_path: str = DEFAULT_TERMINAL):
    """เปิดการเชื่อมต่อ terminal — ล้มเหลว = MT5Unavailable ไม่ใช่คืน None เงียบ ๆ"""
    try:
        import MetaTrader5 as client  # noqa: PLC0415 — นำเข้าเมื่อใช้จริงเท่านั้น
    except ImportError as exc:  # pragma: no cover — เครื่องที่ไม่ได้ติดตั้ง
        raise MT5Unavailable(
            "ไม่พบแพ็กเกจ MetaTrader5 — ติดตั้งด้วย pip install MetaTrader5 (Windows เท่านั้น)"
        ) from exc

    if not client.initialize(terminal_path):
        raise MT5Unavailable(
            f"เปิด terminal ไม่สำเร็จที่ {terminal_path} · last_error={client.last_error()} · "
            "ตรวจว่าเปิดโปรแกรม MT5 และล็อกอินบัญชีค้างไว้แล้ว"
        )

    info = client.terminal_info()
    if info is not None and not getattr(info, "connected", True):
        client.shutdown()
        raise MT5Unavailable(
            "terminal เปิดอยู่แต่ยังไม่ได้เชื่อมต่อโบรก — ตรวจอินเทอร์เน็ตและสถานะล็อกอิน"
        )
    return client


def broker_name(client) -> str:
    account = client.account_info()
    return getattr(account, "company", "") or "unknown"


def detect_server_offset_hours(client, now_utc: datetime, *, reference_symbol: str = CLOCK_SYMBOL):
    """คืน (offset_hours, status, reference_symbol) — offset เป็น None ได้ถ้าวัดไม่ได้

    วัดจาก tick ล่าสุดของสัญลักษณ์ 24/7 เทียบเวลาจริง ถ้า tick เก่าเกิน 6 ชั่วโมง
    แปลว่านาฬิกาอ้างอิงหยุดเดิน (ตลาดปิด/ไม่มีสิทธิ์ดูสัญลักษณ์นั้น) → รายงาน unknown
    ดีกว่ารายงานตัวเลขที่ผิด
    """
    if not client.symbol_select(reference_symbol, True):
        return None, "unknown_no_reference_symbol", reference_symbol
    tick = client.symbol_info_tick(reference_symbol)
    if tick is None or not getattr(tick, "time", 0):
        return None, "unknown_no_reference_tick", reference_symbol

    server_dt = datetime.fromtimestamp(int(tick.time), tz=timezone.utc)
    offset = (server_dt - now_utc).total_seconds() / 3600
    # tick ของตลาด 24/7 ควรสด — ถ้าห่างเกินกรอบที่เป็นไปได้ แปลว่านาฬิกาอ้างอิงหยุดเดิน
    if not PLAUSIBLE_OFFSET_HOURS[0] - 6 <= offset <= PLAUSIBLE_OFFSET_HOURS[1] + 6:
        return None, "unknown_stale_reference_tick", reference_symbol
    return round(offset, 2), "detected", reference_symbol


def offset_warnings(offset_hours) -> list[str]:
    if offset_hours is None:
        return ["วัด offset ของเซิร์ฟเวอร์ไม่ได้ในรอบนี้ — ใช้เวลาหน้าปัดของแท่งตามที่ MT5 ส่งมา"]
    low, high = PLAUSIBLE_OFFSET_HOURS
    if not low <= offset_hours <= high:
        return [
            f"offset เซิร์ฟเวอร์ {offset_hours:+g} ชม. หลุดกรอบที่คาด ({low:+g} ถึง {high:+g}) — "
            "ธรรมเนียมขอบแท่งอาจเปลี่ยน ให้ตรวจว่ามีแท่งเสาร์อาทิตย์โผล่มาหรือไม่ก่อนเชื่อผล"
        ]
    return []


def rows_from_rates(rates) -> tuple[list[dict], list[str]]:
    """แปลง rates ของ MT5 เป็น rows ของสายท่อ + รายชื่อ session ที่ค่าว่าง

    ค่า 0 หรือ None ถือเป็นแท่งว่าง — บันทึกไว้ให้ด่านตรวจเห็น ไม่ข้ามเงียบ ๆ
    (บทเรียนจาก BTC ที่ Yahoo ส่งแท่งค่า null มาแล้วโค้ดเดิมข้ามไป)
    """
    rows: list[dict] = []
    empty_sessions: list[str] = []
    for rate in rates:
        session_date = session_date_from_server_epoch(rate["time"])
        values = {key: rate[key] for key in ("open", "high", "low", "close")}
        if any(value is None or float(value) == 0.0 for value in values.values()):
            empty_sessions.append(session_date)
            continue
        rows.append({
            "date": session_date,
            **{key: float(value) for key, value in values.items()},
        })
    return rows, empty_sessions


def bar_age_days(session_date: str, reference_date: date) -> int:
    return (reference_date - date.fromisoformat(session_date)).days


def fetch_mt5_rows(
    symbol: str,
    count: int = DEFAULT_COUNT,
    *,
    client=None,
    now: datetime | None = None,
    max_age_days: int = MAX_BAR_AGE_DAYS,
    attempts: int = MAX_ATTEMPTS,
    sleep_seconds: float = RETRY_SLEEP_SECONDS,
    terminal_path: str = DEFAULT_TERMINAL,
) -> tuple[dict, list[dict], str]:
    """คืน (meta, rows, source) — ลายเซ็นเดียวกับ pilot_generator.fetch_yahoo_rows

    ปิดการเชื่อมต่อให้เองเฉพาะกรณีที่เปิดเอง (ไม่ได้รับ client มาจากผู้เรียก)
    """
    owns_client = client is None
    client = client or load_client(terminal_path)
    now = now or datetime.now(tz=timezone.utc)

    try:
        offset_hours, offset_status, offset_symbol = detect_server_offset_hours(client, now)
        # วันที่หน้าปัดของเซิร์ฟเวอร์ = ฐานนับอายุแท่ง (ต่างจาก UTC ได้ถึง 3 ชม.)
        server_now = now + timedelta(hours=offset_hours or 0)
        server_today = server_now.date()

        if not client.symbol_select(symbol, True):
            raise MT5Unavailable(
                f"เลือกสัญลักษณ์ {symbol} ไม่ได้ · last_error={client.last_error()} — "
                "ตรวจว่าบัญชีนี้มีสัญลักษณ์ดังกล่าวใน Market Watch"
            )

        timeframe = client.TIMEFRAME_D1
        last_seen: str | None = None
        rows: list[dict] = []
        empty_sessions: list[str] = []
        age: int | None = None

        for attempt in range(1, attempts + 1):
            rates = client.copy_rates_from(symbol, timeframe, now, count)
            if rates is None or len(rates) == 0:
                if attempt < attempts:
                    time.sleep(sleep_seconds)
                    continue
                raise MT5Unavailable(
                    f"{symbol}: MT5 ไม่คืนแท่งเลย · last_error={client.last_error()}"
                )

            rows, empty_sessions = rows_from_rates(rates)
            if not rows:
                if attempt < attempts:
                    time.sleep(sleep_seconds)
                    continue
                raise MT5Unavailable(f"{symbol}: ทุกแท่งที่ได้มาเป็นค่าว่าง")

            last_seen = rows[-1]["date"]
            age = bar_age_days(last_seen, server_today)
            if age <= max_age_days:
                break
            if attempt < attempts:
                time.sleep(sleep_seconds)

        if age is None or age > max_age_days:
            raise MT5StaleData(
                f"{symbol}: แท่งล่าสุดคือ {last_seen} เก่า {age} วัน เกินเพดาน {max_age_days} วัน "
                f"หลังลอง {attempts} รอบ — หยุดสายท่อ ไม่เขียนบทความจากข้อมูลค้าง "
                "(ถ้าเป็นวันหยุดยาวจริง ให้สั่งด้วย --max-bar-age-days พร้อมระบุเหตุผล)"
            )

        meta = {
            "provider": PROVIDER_KEY,
            "broker": broker_name(client),
            "terminal_path": terminal_path,
            "symbol": symbol,
            "timeframe": "D1",
            "requested_count": count,
            "returned_count": len(rows),
            "server_offset_hours": offset_hours,
            "server_offset_status": offset_status,
            "server_offset_reference": offset_symbol,
            "server_today": server_today.isoformat(),
            "last_bar_session_date": last_seen,
            "last_bar_age_days": age,
            "freshness_max_age_days": max_age_days,
            "freshness_attempts_used": attempt,
            "freshness_method": "copy_rates_from(now) + วนซ้ำจนแท่งล่าสุดสด",
            "retrieved_at": now.isoformat(timespec="seconds"),
            "warnings": offset_warnings(offset_hours),
            "p002_empty_sessions": empty_sessions,
        }
        source = f"MetaTrader 5 · {meta['broker']} · {symbol} D1"
        return meta, rows, source
    finally:
        if owns_client:
            client.shutdown()


def fetch_asset_rows(asset: str, **kwargs) -> tuple[dict, list[dict], str]:
    """เรียกด้วยชื่อสินทรัพย์ของสายท่อ (eurusd / btcusd / xauusd)"""
    try:
        symbol = SYMBOLS[asset]
    except KeyError as exc:
        raise MT5Unavailable(f"ยังไม่ได้แมปสินทรัพย์ {asset} เข้ากับสัญลักษณ์ MT5") from exc
    return fetch_mt5_rows(symbol, **kwargs)
