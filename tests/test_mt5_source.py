"""เทสแหล่งข้อมูล MT5 — ใช้ client ปลอมทั้งหมด รันได้บนเครื่องที่ไม่มี MetaTrader5

จุดที่ต้องล็อกไว้ด้วยเทส (บทเรียนจริงจากการทดสอบ 2026-08-04):
- แท่งค้างเก่าต้อง "หยุด" ไม่ใช่คืนของเก่าเงียบ ๆ
- session date ต้องอ่านจากเวลาหน้าปัดเซิร์ฟเวอร์ ห้ามแปลงกลับเป็น UTC จริง
  (ถ้าแปลง วันฐาน Pivot จะเลื่อนทั้งชุด = บั๊กเดียวกับที่แก้ไปเมื่อ 2026-08-03)
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import build_daily_package, integrity, license_gate  # noqa: E402
from tools import market_calendar, mt5_source  # noqa: E402


NOW = datetime(2026, 8, 4, 2, 30, tzinfo=timezone.utc)


class FakeTick:
    def __init__(self, epoch: int):
        self.time = epoch


class FakeClient:
    """เลียนแบบเฉพาะส่วนของ MetaTrader5 ที่ adapter เรียกใช้"""

    TIMEFRAME_D1 = 16408

    def __init__(self, batches, *, offset_hours=3, company="Raw Trading Ltd",
                 selectable=True):
        # batches = ลิสต์ของชุด rates ที่จะคืนทีละรอบ (จำลองการวนซ้ำ)
        self.batches = list(batches)
        self.offset_hours = offset_hours
        self.company = company
        self.selectable = selectable
        self.calls = 0
        self.shutdown_called = False

    def symbol_select(self, symbol, enable=True):
        return self.selectable

    def symbol_info_tick(self, symbol):
        if self.offset_hours is None:
            return None
        server_now = NOW + timedelta(hours=self.offset_hours)
        return FakeTick(int(server_now.timestamp()))

    def copy_rates_from(self, symbol, timeframe, when, count):
        self.calls += 1
        index = min(self.calls - 1, len(self.batches) - 1)
        return self.batches[index]

    def account_info(self):
        return type("Acct", (), {"company": self.company})()

    def last_error(self):
        return (1, "fake")

    def shutdown(self):
        self.shutdown_called = True


def server_epoch(day: str) -> int:
    """epoch แบบที่ MT5 ส่งมา — เวลาหน้าปัดเซิร์ฟเวอร์ห่อในรูป UTC"""
    return int(datetime.fromisoformat(f"{day}T00:00:00+00:00").timestamp())


def bars(dates, close=1.1):
    return [
        {"time": server_epoch(day), "open": close, "high": close + 0.01,
         "low": close - 0.01, "close": close, "tick_volume": 100}
        for day in dates
    ]


FRESH = ["2026-07-30", "2026-07-31", "2026-08-03", "2026-08-04"]
STALE = ["2026-06-29", "2026-06-30", "2026-07-01", "2026-07-06"]


# ---------- session date: หัวใจของบั๊กวันฐาน Pivot ----------

def test_session_date_อ่านจากเวลาหน้าปัดเซิร์ฟเวอร์ไม่แปลงกลับเป็น_utc():
    """แท่งประทับ 2026-08-04 00:00 เวลาเซิร์ฟเวอร์ = session ของวันที่ 2026-08-04

    ถ้าเผลอลบ offset 3 ชม. ออก จะกลายเป็น 2026-08-03 21:00 → session date เลื่อนถอยหนึ่งวัน
    """
    assert mt5_source.session_date_from_server_epoch(server_epoch("2026-08-04")) == "2026-08-04"


@pytest.mark.parametrize("offset", [2, 3])
def test_session_date_ไม่ขยับตาม_offset_ของโบรก(offset):
    """โบรกสลับ DST ระหว่างปี (GMT+2 ↔ +3) session date ต้องคงเดิม"""
    client = FakeClient([bars(FRESH)], offset_hours=offset)
    _, rows, _ = mt5_source.fetch_mt5_rows("EURUSD", 4, client=client, now=NOW)
    assert [row["date"] for row in rows] == FRESH


def test_วันฐาน_pivot_ตรงกับ_session_ที่ปิดจริง():
    """regression ของบั๊ก 2026-08-03 — pivot ต้องใช้แท่งวันจันทร์ที่ปิดแล้ว ไม่ใช่แท่งที่เลื่อนไปหนึ่งวัน

    ยิงผ่าน integrity.assess เพื่อทดสอบเส้นทางเดียวกับที่สายท่อใช้จริง
    ถ้า adapter เผลอลบ offset 3 ชม. ออก วันฐานจะกลายเป็น 2026-07-31
    """
    client = FakeClient([bars(FRESH)], offset_hours=3)
    _, rows, _ = mt5_source.fetch_mt5_rows("EURUSD", 4, client=client, now=NOW)

    report = integrity.assess(rows, "eurusd", calculated_at=NOW.isoformat())

    # แท่งล่าสุด (08-04) เป็น forming จึงต้องใช้ 08-03 เป็นวันฐาน
    assert report["pivots"]["basis_session_date"] == "2026-08-03"
    assert report["pivots"]["basis_candle_state"] == "closed"
    assert not report["anomalies"], "ไม่ควรมีแท่งนอกปฏิทินจาก MT5 ฝั่ง forex"


def test_แท่งเสาร์อาทิตย์ของ_crypto_ไม่ถูกตีว่าผิดปฏิทิน():
    """BTC เดิน 7 วัน — MT5 ส่งแท่งครบทุกวัน ต้องไม่มี anomaly และไม่มีวันหาย"""
    dates = ["2026-07-30", "2026-07-31", "2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04"]
    client = FakeClient([bars(dates, close=63000.0)], offset_hours=3)
    _, rows, _ = mt5_source.fetch_mt5_rows("BTCUSD", 6, client=client, now=NOW)

    report = integrity.assess(rows, "btcusd", calculated_at=NOW.isoformat())

    assert not report["anomalies"]
    assert report["gap_check"]["missing_sessions"] == []


# ---------- freshness gate ----------

def test_แท่งค้างเก่าต้องหยุดสายท่อไม่ใช่คืนของเก่า():
    client = FakeClient([bars(STALE)], offset_hours=3)
    with pytest.raises(mt5_source.MT5StaleData) as err:
        mt5_source.fetch_mt5_rows("XAUUSD", 4, client=client, now=NOW, sleep_seconds=0)
    assert "2026-07-06" in str(err.value)
    assert client.calls == mt5_source.MAX_ATTEMPTS, "ต้องลองซ้ำจนครบก่อนยอมแพ้"


def test_วนซ้ำแล้วได้ของสดถือว่าผ่าน():
    """รอบแรกได้ของค้าง รอบสองได้ของสด — ต้องใช้ของสดและบันทึกจำนวนรอบ"""
    client = FakeClient([bars(STALE), bars(FRESH)], offset_hours=3)
    meta, rows, _ = mt5_source.fetch_mt5_rows("XAUUSD", 4, client=client, now=NOW, sleep_seconds=0)
    assert rows[-1]["date"] == "2026-08-04"
    assert meta["freshness_attempts_used"] == 2
    assert meta["last_bar_age_days"] == 0


def test_สุดสัปดาห์แท่งวันศุกร์ยังถือว่าสด():
    """วันอาทิตย์ แท่งล่าสุดของ forex คือวันศุกร์ อายุ 2 วัน ต้องไม่ถูกตีตก"""
    sunday = datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc)
    client = FakeClient([bars(["2026-07-29", "2026-07-30", "2026-07-31"])], offset_hours=3)
    meta, rows, _ = mt5_source.fetch_mt5_rows("EURUSD", 3, client=client, now=sunday)
    assert meta["last_bar_age_days"] == 2
    assert rows[-1]["date"] == "2026-07-31"


def test_แท่งค่าว่างถูกบันทึกไม่ใช่ข้ามเงียบ():
    """บทเรียนจาก BTC ที่ provider ส่งแท่งค่า null มาแล้วโค้ดเดิมข้ามไป"""
    rates = bars(FRESH)
    rates[1] = {**rates[1], "open": 0.0, "high": 0.0, "low": 0.0, "close": 0.0}
    client = FakeClient([rates], offset_hours=3)
    meta, rows, _ = mt5_source.fetch_mt5_rows("BTCUSD", 4, client=client, now=NOW)
    assert meta["p002_empty_sessions"] == ["2026-07-31"]
    assert len(rows) == 3


# ---------- offset: ตรวจตอน runtime ไม่ hardcode ----------

def test_offset_ถูกตรวจตอน_runtime_และบันทึกไว้():
    client = FakeClient([bars(FRESH)], offset_hours=3)
    meta, _, _ = mt5_source.fetch_mt5_rows("EURUSD", 4, client=client, now=NOW)
    assert meta["server_offset_hours"] == 3.0
    assert meta["server_offset_status"] == "detected"
    assert meta["warnings"] == []


def test_offset_หลุดกรอบต้องเตือนแต่ไม่ล้ม():
    """โบรกย้ายเซิร์ฟเวอร์ไป GMT+0 = ขอบแท่งเปลี่ยน อาจมีแท่งเสาร์อาทิตย์โผล่"""
    client = FakeClient([bars(FRESH)], offset_hours=0)
    meta, rows, _ = mt5_source.fetch_mt5_rows("EURUSD", 4, client=client, now=NOW)
    assert rows, "ยังต้องคืนข้อมูล — นี่เป็นคำเตือน ไม่ใช่ด่านตัด"
    assert meta["warnings"], "ต้องมีคำเตือนให้คนตรวจเห็น"


def test_วัด_offset_ไม่ได้ยังทำงานต่อได้():
    """ไม่มี tick อ้างอิง — session date ไม่ได้พึ่ง offset จึงต้องไปต่อได้พร้อมคำเตือน"""
    client = FakeClient([bars(FRESH)], offset_hours=None)
    meta, rows, _ = mt5_source.fetch_mt5_rows("EURUSD", 4, client=client, now=NOW)
    assert meta["server_offset_hours"] is None
    assert meta["server_offset_status"] == "unknown_no_reference_tick"
    assert rows[-1]["date"] == "2026-08-04"
    assert meta["warnings"]


# ---------- terminal ไม่พร้อม ----------

def test_เลือกสัญลักษณ์ไม่ได้ต้องหยุด():
    client = FakeClient([bars(FRESH)], selectable=False)
    with pytest.raises(mt5_source.MT5Unavailable):
        mt5_source.fetch_mt5_rows("XAUUSD", 4, client=client, now=NOW)


def test_ไม่มีแท่งเลยต้องหยุด():
    client = FakeClient([[]], offset_hours=3)
    with pytest.raises(mt5_source.MT5Unavailable):
        mt5_source.fetch_mt5_rows("XAUUSD", 4, client=client, now=NOW, sleep_seconds=0)


def test_client_ที่ผู้เรียกส่งมาเองต้องไม่ถูกปิด():
    """ผู้เรียกอาจดึงหลายสินทรัพย์ต่อการเชื่อมต่อครั้งเดียว"""
    client = FakeClient([bars(FRESH)], offset_hours=3)
    mt5_source.fetch_mt5_rows("EURUSD", 4, client=client, now=NOW)
    assert not client.shutdown_called


# ---------- ปฏิทิน: วันหยุดของ FX กับทองไม่เหมือนกัน ----------

def test_good_friday_เป็นวันหยุดของทองแต่ไม่ใช่ของ_fx():
    """ยืนยันด้วยข้อมูลโบรกจริง 2026-08-04: EURUSD มีแท่ง 2026-04-03 แต่ XAUUSD ไม่มี

    ถ้าตั้งให้ FX หยุดวันนี้ด้วย แท่งจริงจะถูกตีเป็น unexpected_holiday_candle
    แล้ว EUR ทั้งชุดถูกด่านกั้นทั้งที่ข้อมูลถูกต้อง
    """
    assert market_calendar.for_asset("eurusd").classify("2026-04-03") == "expected"
    assert market_calendar.for_asset("xauusd").classify("2026-04-03") == "holiday"
    # วันปีใหม่ปิดทั้งคู่ (ทั้ง EURUSD และ XAUUSD ไม่มีแท่ง)
    assert market_calendar.for_asset("eurusd").classify("2026-01-01") == "holiday"
    assert market_calendar.for_asset("xauusd").classify("2026-01-01") == "holiday"


# ---------- ทะเบียนสิทธิ์: ของใหม่ต้องยังบล็อกการเผยแพร่ ----------

def test_ทะเบียนสิทธิ์_mt5_ตรวจแล้วว่าเผยแพร่ไม่ได้():
    """อ่านสัญญาจบแล้ว 2026-08-04 — คำตอบคือ "ไม่ได้" ไม่ใช่ "ยังไม่รู้"

    Client Agreement ของ Raw Trading Ltd ข้อ 28.7 สงวนสิทธิ์ใน Quotes ไว้กับโบรก
    และข้อ 10.19 ให้ใช้เพื่อ personal use เท่านั้น จึงไม่มีทางผ่านด่านเผยแพร่
    ห้ามมีใครแก้ค่าเหล่านี้เป็น true โดยไม่มีหนังสืออนุญาตจากฝ่าย compliance ของโบรก
    """
    registry = license_gate.load_registry()
    entry = registry["providers"][mt5_source.PROVIDER_KEY]

    assert entry["verified_at"] == "2026-08-04", "ต้องบันทึกวันที่อ่านสัญญาจริง"
    assert entry["use_case"]["internal_analysis"] is True, "ใช้วิเคราะห์ภายในได้"
    for field in ("public_display", "commercial_use", "redistribution"):
        assert entry["use_case"][field] is False, f"{field} สัญญาไม่อนุญาต"

    for asset in ("eurusd", "btcusd", "xauusd"):
        assert registry["asset_providers"][asset] == [mt5_source.PROVIDER_KEY]
        result = license_gate.evaluate(
            asset, registry=registry, content_qa_passed=True, data_quality_passed=True)
        assert result["clearance"] == license_gate.APPROVED_INTERNAL
        assert not license_gate.is_publishable(result)


def test_ค่าตั้งต้นของสายท่อชี้ไป_mt5_ทั้งสามสินทรัพย์():
    for asset, config in build_daily_package.ASSETS.items():
        assert config["provider"] == mt5_source.PROVIDER_KEY
        assert config["mt5"] == mt5_source.SYMBOLS[asset]
    assert build_daily_package.resolve_source(None, None) == build_daily_package.SOURCE_MT5


def test_สั่งแหล่งขัดกันต้องฟ้องไม่ใช่เลือกข้างเอง():
    """--source mt5 พร้อม --snapshot = คำสั่งขัดกัน · แนบ snapshot เฉย ๆ = ใช้ snapshot"""
    with pytest.raises(SystemExit):
        build_daily_package.resolve_source(
            build_daily_package.SOURCE_MT5, Path("some-snapshot.json"))
    assert build_daily_package.resolve_source(None, Path("some-snapshot.json")) == \
        build_daily_package.SOURCE_SNAPSHOT


def test_แมปชื่อสินทรัพย์ของสายท่อเข้ากับสัญลักษณ์():
    assert mt5_source.SYMBOLS == {
        "eurusd": "EURUSD", "btcusd": "BTCUSD", "xauusd": "XAUUSD",
        "nvda": "NVDA.NAS"}
    client = FakeClient([bars(FRESH)], offset_hours=3)
    meta, _, source = mt5_source.fetch_asset_rows("xauusd", count=4, client=client, now=NOW)
    assert meta["symbol"] == "XAUUSD"
    assert "Raw Trading Ltd" in source
