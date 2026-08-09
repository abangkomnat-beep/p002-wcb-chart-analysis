"""ปฏิทินตลาดต่อชนิดสินทรัพย์ — ตอบว่าวันไหนเป็น session ที่ตลาดเปิดจริง

โมดูลนี้ไม่พึ่งโมดูลอื่นในโปรเจกต์ ผู้เรียกส่ง object ที่ได้จาก for_asset() ต่อไปให้
candles/gap_detector/pivots ใช้ร่วมกัน
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "market_calendar.json"


def as_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def load_config(path: Path | None = None) -> dict:
    return json.loads((path or CONFIG_PATH).read_text(encoding="utf-8"))


class UnknownCloseTime(RuntimeError):
    """ชนิดสินทรัพย์นี้ยังไม่ประกาศเวลาปิดแท่งรายวัน — พิสูจน์ไม่ได้ = ตกด่าน ไม่ใช่เดา"""


class MarketCalendar:
    """ปฏิทินของชนิดสินทรัพย์หนึ่ง เช่น crypto_spot, forex_spot, spot_metal"""

    def __init__(self, asset_class: str, spec: dict, holidays: list[str]):
        self.asset_class = asset_class
        self.calendar = spec["calendar"]
        self.trading_weekdays = set(spec["trading_weekdays"])
        self.session_timezone = spec["session_timezone"]
        self.public_timezone = spec["public_timezone"]
        self.holidays = {as_date(day) for day in holidays}
        # ไม่ใส่ค่าตั้งต้นให้ `daily_close` โดยเจตนา — ชนิดสินทรัพย์ที่ยังไม่ประกาศ
        # เวลาปิดต้องพิสูจน์ไม่ได้ว่าแท่งปิดแล้ว แล้วตกด่าน ไม่ใช่เดาเวลาให้เอง
        self.daily_close = spec.get("daily_close")

    # ------------------------------------------------------------ เวลาปิดแท่ง
    #
    # 🐞 **A-1 (ทีมเว็บตรวจรอบสาม 2026-08-09):** บทประกาศว่า "แท่งล่าสุดปิดที่ X"
    # ทั้งที่แท่งรายวันยังก่อตัวอยู่ ⇒ ตัวเลขในบทไม่ตรงกับกราฟ/แผงราคาบนหน้าเดียวกัน
    # ที่แสดงราคาปิดจริงของวันนั้น · **ห้ามแก้ด้วยการเดาจากเวลาที่รัน** ("รันตอนตี 5
    # แปลว่าปิดแล้ว") เพราะวันหยุด/วันตลาดปิดจะทำให้เดาผิดเงียบ ๆ — ต้องคำนวณจาก
    # ป้ายวันของแท่ง + เวลาปิดตลาดของสินทรัพย์นั้นที่ประกาศไว้ใน config

    def daily_close_at(self, session_date) -> datetime:
        """เวลาที่แท่งรายวันของ session นี้ปิดจริง (คืนเป็น UTC)"""
        spec = self.daily_close
        if not spec:
            raise UnknownCloseTime(
                f"{self.asset_class}: ยังไม่ประกาศ daily_close ใน market_calendar.json "
                "จึงพิสูจน์ไม่ได้ว่าแท่งรายวันปิดแล้ว")
        hour, minute = (int(part) for part in str(spec["time"]).split(":")[:2])
        day = as_date(session_date) + timedelta(days=int(spec.get("day_offset", 0)))
        local = datetime.combine(day, time(hour, minute), tzinfo=ZoneInfo(spec["timezone"]))
        return local.astimezone(timezone.utc)

    def is_daily_candle_closed(self, session_date, now: datetime) -> bool:
        if now.tzinfo is None:
            raise ValueError("now ต้องเป็นเวลาที่มี timezone — เวลาลอยเทียบข้ามโซนไม่ได้")
        return self.daily_close_at(session_date) <= now

    def daily_close_rule_text(self) -> str:
        """ประโยคอธิบายกติกาเวลาปิด — ใช้เป็นหลักฐานในรายงาน/ด่านตรวจ"""
        spec = self.daily_close
        if not spec:
            return f"{self.asset_class}: ไม่ประกาศเวลาปิดแท่งรายวัน"
        offset = int(spec.get("day_offset", 0))
        tail = f" ของวันถัดไปอีก {offset} วัน" if offset else ""
        return (f"แท่งรายวันของ {self.asset_class} ปิดเวลา {spec['time']} "
                f"ตามเขตเวลา {spec['timezone']}{tail}")

    @property
    def is_continuous(self) -> bool:
        """ตลาด 24/7 คาดหวังแท่งทุกวันปฏิทิน"""
        return self.calendar == "24_7"

    def classify(self, session_date) -> str:
        day = as_date(session_date)
        if day.weekday() not in self.trading_weekdays:
            return "weekend"
        if day in self.holidays:
            return "holiday"
        return "expected"

    def is_expected_session(self, session_date) -> bool:
        return self.classify(session_date) == "expected"

    def previous_expected_session(self, session_date) -> date:
        day = as_date(session_date) - timedelta(days=1)
        for _ in range(30):
            if self.is_expected_session(day):
                return day
            day -= timedelta(days=1)
        raise ValueError(f"ไม่พบ session ที่คาดหวังก่อน {session_date} ภายใน 30 วัน")

    def expected_sessions(self, start, end) -> list[date]:
        first, last = as_date(start), as_date(end)
        sessions, day = [], first
        while day <= last:
            if self.is_expected_session(day):
                sessions.append(day)
            day += timedelta(days=1)
        return sessions


def for_asset_class(asset_class: str, config: dict | None = None) -> MarketCalendar:
    config = config or load_config()
    if asset_class not in config["asset_classes"]:
        raise ValueError(f"ไม่รู้จักชนิดสินทรัพย์: {asset_class}")
    return MarketCalendar(
        asset_class,
        config["asset_classes"][asset_class],
        config.get("holidays", {}).get(asset_class, []),
    )


def for_asset(asset: str, config: dict | None = None) -> MarketCalendar:
    config = config or load_config()
    assets = config.get("assets", {})
    if asset not in assets:
        raise ValueError(f"ยังไม่ได้ลงทะเบียนสินทรัพย์ {asset} ใน market_calendar.json")
    return for_asset_class(assets[asset], config)
