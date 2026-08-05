"""เทสแหล่งแท่งราคาจาก WCB series API — ตัวแทน MT5 ในสายภายใน

เน้นสามเรื่องที่พังแล้วเงียบได้: จำนวนแท่งที่ได้ไม่เท่าที่ขอ · ข้อมูลค้าง · แมปชื่อสินทรัพย์
"""

import io
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import build_daily_package, license_gate, mt5_source, wcb_series_source  # noqa: E402


NOW = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)


def candle(day: int, close: float = 100.0) -> dict:
    return {"t": f"2026-08-{day:02d}", "o": close - 1, "h": close + 2,
            "l": close - 2, "c": close, "v": None}


def payload(candles, *, symbol="XAU/USD", interval="1day", ok=True) -> dict:
    return {"ok": ok, "symbol": symbol, "interval": interval, "candles": candles}


class จำลองปลายทาง:
    """ตัวเปิด URL ปลอม — เก็บ URL ที่ถูกยิงไว้ให้ตรวจ"""

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.urls = []

    def __call__(self, request, timeout=None):
        self.urls.append(request.full_url)
        body = self.payloads[0] if len(self.payloads) == 1 else self.payloads.pop(0)
        return _Response(json.dumps(body).encode("utf-8"))


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class รูปแท่งต้องเข้ากันได้กับสายท่อ(unittest.TestCase):
    def test_แปลงแท่งเป็น_rows_รูปเดียวกับ_mt5(self):
        rows, empty = wcb_series_source.rows_from_candles([candle(3), candle(4, 101.0)])
        self.assertEqual(set(rows[0]), {"date", "open", "high", "low", "close"})
        self.assertEqual(rows[0]["date"], "2026-08-03")
        self.assertEqual(rows[1]["close"], 101.0)
        self.assertEqual(empty, [])

    def test_แท่งค่าว่างถูกบันทึกไม่ใช่ข้ามเงียบ(self):
        broken = {"t": "2026-08-04", "o": 0, "h": 0, "l": 0, "c": 0, "v": None}
        rows, empty = wcb_series_source.rows_from_candles([candle(3), broken])
        self.assertEqual(len(rows), 1)
        self.assertEqual(empty, ["2026-08-04"])

    def test_เรียงวันจากเก่าไปใหม่เสมอ(self):
        rows, _ = wcb_series_source.rows_from_candles([candle(5), candle(3), candle(4)])
        self.assertEqual([row["date"] for row in rows],
                         ["2026-08-03", "2026-08-04", "2026-08-05"])


class ขอเผื่อแล้วตัดท้าย(unittest.TestCase):
    """ปลายทางคืนแท่งน้อยกว่า outputsize ที่ขอ — วัดจริงแล้ว ขอ 200 ได้ 143"""

    def test_ยิง_outputsize_มากกว่าจำนวนแท่งที่ต้องการ(self):
        opener = จำลองปลายทาง([payload([candle(d % 28 + 1) for d in range(20)])])
        wcb_series_source.fetch_series_rows("xauusd", count=5, now=NOW, opener=opener)
        self.assertIn(f"outputsize={5 * wcb_series_source.OVERSIZE_FACTOR}", opener.urls[0])

    def test_ตัดเหลือเท่าที่ขอและเก็บแท่งใหม่สุดไว้(self):
        candles = [candle(day) for day in range(1, 6)]
        opener = จำลองปลายทาง([payload(candles)])
        meta, rows, _ = wcb_series_source.fetch_series_rows(
            "xauusd", count=3, now=NOW, opener=opener)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[-1]["date"], "2026-08-05")
        self.assertEqual(meta["returned_count"], 5)
        self.assertEqual(meta["used_count"], 3)

    def test_ได้แท่งไม่ครบต้องฟ้องไม่ใช่เขียนบทความจากของที่ไม่พอ(self):
        opener = จำลองปลายทาง([payload([candle(4), candle(5)])])
        with self.assertRaises(wcb_series_source.SeriesUnavailable) as ctx:
            wcb_series_source.fetch_series_rows("xauusd", count=130, now=NOW, opener=opener)
        self.assertIn("130", str(ctx.exception))


class แท่งวันหยุดตามปฏิทิน(unittest.TestCase):
    """WCB มีแท่งทองคำวัน Good Friday 2026-04-03 แต่ปฏิทินของสายท่อถือว่าตลาดปิด

    ทานสอบกับผลจริงของ MT5 ชุด 130 แท่งเมื่อ 2026-08-05 แล้ว ทับกันทุกวันยกเว้นวันนี้วันเดียว
    ปล่อยไว้ = `integrity` กั้นทั้งหัวข้อทุกปี · ผ่อนด่านแทน = ฐาน Pivot เปลี่ยนจากที่วัดเกณฑ์ไว้
    """

    def test_แท่งวันหยุดถูกคัดออกและบันทึกไว้(self):
        calendar = wcb_series_source.market_calendar.for_asset("xauusd")
        rows = [{"date": "2026-04-02", "open": 1, "high": 1, "low": 1, "close": 1},
                {"date": "2026-04-03", "open": 1, "high": 1, "low": 1, "close": 1},
                {"date": "2026-04-06", "open": 1, "high": 1, "low": 1, "close": 1}]
        kept, dropped = wcb_series_source.drop_holiday_candles(rows, calendar)

        self.assertEqual([row["date"] for row in kept], ["2026-04-02", "2026-04-06"])
        self.assertEqual(dropped, ["2026-04-03"])

    def test_ไม่ส่งปฏิทินมาก็ไม่คัดอะไรทิ้ง(self):
        rows = [{"date": "2026-04-03", "open": 1, "high": 1, "low": 1, "close": 1}]
        kept, dropped = wcb_series_source.drop_holiday_candles(rows, None)

        self.assertEqual(kept, rows)
        self.assertEqual(dropped, [])

    def test_การคัดต้องขึ้น_meta_ไม่ใช่ทิ้งเงียบ(self):
        candles = [{"t": "2026-04-02", "o": 1, "h": 1, "l": 1, "c": 1, "v": None},
                   {"t": "2026-04-03", "o": 1, "h": 1, "l": 1, "c": 1, "v": None},
                   candle(5)]
        opener = จำลองปลายทาง([payload(candles)])
        meta, rows, _ = wcb_series_source.fetch_series_rows(
            "xauusd", count=2, now=NOW, opener=opener,
            calendar=wcb_series_source.market_calendar.for_asset("xauusd"))

        self.assertEqual(meta["p002_holiday_candles_dropped"], ["2026-04-03"])
        self.assertTrue(any("2026-04-03" in text for text in meta["warnings"]))
        self.assertNotIn("2026-04-03", [row["date"] for row in rows])

    def test_เรียกด้วยชื่อหัวข้อต้องแนบปฏิทินให้เอง(self):
        opener = จำลองปลายทาง([payload([
            {"t": "2026-04-03", "o": 1, "h": 1, "l": 1, "c": 1, "v": None}, candle(5)])])
        meta, _, _ = wcb_series_source.fetch_asset_rows(
            "xauusd", count=1, now=NOW, opener=opener)

        self.assertEqual(meta["p002_holiday_candles_dropped"], ["2026-04-03"])


class ด่านความสด(unittest.TestCase):
    def test_แท่งล่าสุดเก่าเกินเพดานต้องหยุดสายท่อ(self):
        old = [candle(day) for day in range(1, 4)]   # ล่าสุด 2026-08-03 เก่าสองวัน
        opener = จำลองปลายทาง([payload(old)])
        with self.assertRaises(wcb_series_source.SeriesStaleData):
            wcb_series_source.fetch_series_rows(
                "xauusd", count=2, now=NOW, max_age_days=1, attempts=1, opener=opener)

    def test_แท่งสดผ่านและบันทึกอายุไว้(self):
        opener = จำลองปลายทาง([payload([candle(4), candle(5)])])
        meta, _, _ = wcb_series_source.fetch_series_rows(
            "xauusd", count=2, now=NOW, opener=opener)
        self.assertEqual(meta["last_bar_session_date"], "2026-08-05")
        self.assertEqual(meta["last_bar_age_days"], 0)

    def test_ยิงซ้ำจนได้แท่งสด(self):
        stale = payload([candle(1), candle(2), candle(3)])
        fresh = payload([candle(3), candle(4), candle(5)])
        opener = จำลองปลายทาง([stale, fresh])
        _, rows, _ = wcb_series_source.fetch_series_rows(
            "xauusd", count=2, now=NOW, max_age_days=1,
            attempts=2, sleep_seconds=0, opener=opener)
        self.assertEqual(rows[-1]["date"], "2026-08-05")
        self.assertEqual(len(opener.urls), 2)


class แมปชื่อสินทรัพย์(unittest.TestCase):
    def test_btcusd_ต้องแปลงเป็น_btc(self):
        self.assertEqual(wcb_series_source.ASSET_TAGS["btcusd"], "btc")

    def test_ทุกหัวข้อในสายท่อมี_tag_ของ_api(self):
        for asset, config in build_daily_package.ASSETS.items():
            with self.subTest(asset=asset):
                self.assertIn("wcb", config)
                self.assertEqual(config["wcb"], wcb_series_source.ASSET_TAGS[asset])

    def test_หัวข้อที่ยังไม่แมปต้องฟ้อง(self):
        with self.assertRaises(wcb_series_source.SeriesUnavailable):
            wcb_series_source.fetch_asset_rows("ยังไม่มีหัวข้อนี้")


class คำขอที่ยิงออกไป(unittest.TestCase):
    def test_ต้องมี_user_agent_ไม่งั้น_cloudflare_ตอบ_403(self):
        request = wcb_series_source.wcb_source.build_request(
            wcb_series_source.build_url("xauusd"))
        self.assertIn("User-agent", request.headers)

    def test_url_มีพารามิเตอร์ครบและไม่มีรหัส(self):
        url = wcb_series_source.build_url("btc", outputsize=300)
        self.assertIn("kind=series", url)
        self.assertIn("asset=btc", url)
        self.assertIn("interval=1day", url)
        self.assertNotIn("key=", url)

    def test_outputsize_ไม่เกินเพดานปลายทาง(self):
        url = wcb_series_source.build_url("xauusd", outputsize=99999)
        self.assertIn(f"outputsize={wcb_series_source.MAX_OUTPUTSIZE}", url)


class แหล่งตั้งต้นของสายภายใน(unittest.TestCase):
    def test_ไม่ระบุแหล่งต้องได้_wcb_ไม่ใช่_mt5(self):
        self.assertEqual(build_daily_package.resolve_source(None, None),
                         build_daily_package.SOURCE_WCB)

    def test_mt5_ยังสั่งเองได้อยู่สำหรับทานสอบ(self):
        self.assertEqual(build_daily_package.resolve_source("mt5", None),
                         build_daily_package.SOURCE_MT5)

    def test_เพดานอายุแท่งของสองแหล่งตรงกัน(self):
        self.assertEqual(wcb_series_source.MAX_BAR_AGE_DAYS, mt5_source.MAX_BAR_AGE_DAYS)


class สิทธิ์ข้อมูลหลังย้ายแหล่ง(unittest.TestCase):
    def test_ทุกหัวข้อผูกกับ_wcb_series_api_ในทะเบียน(self):
        registry = license_gate.load_registry()
        for asset in build_daily_package.ASSETS:
            with self.subTest(asset=asset):
                self.assertEqual(registry["asset_providers"][asset],
                                 [wcb_series_source.PROVIDER_KEY])

    def test_สายภายในยังทำงานได้เท่าเดิมแม้สิทธิ์ยัง_unknown(self):
        result = license_gate.evaluate(
            "xauusd", content_qa_passed=True, data_quality_passed=True,
            providers=[wcb_series_source.PROVIDER_KEY])
        self.assertEqual(result["clearance"], license_gate.APPROVED_INTERNAL)

    def test_สิทธิ์ยัง_unknown_จึงเผยแพร่ไม่ได้(self):
        result = license_gate.evaluate(
            "xauusd", content_qa_passed=True, data_quality_passed=True,
            providers=[wcb_series_source.PROVIDER_KEY])
        self.assertFalse(license_gate.is_publishable(result))


if __name__ == "__main__":
    unittest.main()
