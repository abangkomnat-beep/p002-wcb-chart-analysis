"""เทสชั้นข้อมูลของกฎ "แท่งที่ยังไม่ปิด ห้ามถูกเรียกว่าปิด" — A-1

🐞 **อาการจริงที่ทีมเว็บจับได้ (ตรวจรอบสาม 2026-08-09)**
บทสไตล์ D ของ 7 ส.ค. เขียนว่า "แท่งล่าสุดปิดที่ 4,304.52 ดอลลาร์" แต่ราคาปิดจริง
ในฐานข้อมูลของเว็บคือ 4,342.63 (ต่าง 38.11 = 0.88%) — ข้อมูลไม่ผิด แต่บทถูกผลิต
ตอนแท่งรายวันของทองยังไม่ปิด แล้วเรียกราคาระหว่างวันว่า "ปิด"

หลักที่เทสชุดนี้ล็อกไว้:
1. ระบบรู้เวลาปิดแท่ง **จากข้อมูลจริง** (ป้าย session + `config/market_calendar.json`)
   ไม่ใช่จากการเดาว่า "รันตอนตี 5 แปลว่าปิดแล้ว"
2. แท่งที่ยังไม่ปิดถูกตัดทิ้ง **ก่อนคำนวณอะไรทั้งสิ้น** ไม่ใช่ติดธงไว้เฉย ๆ
3. พิสูจน์ไม่ได้ว่าปิด = ตกด่าน ไม่มีทางเลือก "ปล่อยผ่านพร้อมป้ายเตือน"
"""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import candle_close, market_calendar  # noqa: E402

BANGKOK = timezone(timedelta(hours=7))


class เวลาปิดแท่งมาจากปฏิทินจริง(unittest.TestCase):

    def test_ทองปิดตีสี่เวลาไทยของวันถัดไป(self):
        """ค่าที่ทีมเว็บยืนยัน: ทองเปิดจันทร์–ศุกร์ แท่งรายวันปิด 04:00 น. เวลาไทย"""
        calendar = market_calendar.for_asset("xauusd")
        closed_at = calendar.daily_close_at("2026-08-07").astimezone(BANGKOK)

        self.assertEqual(closed_at.strftime("%Y-%m-%d %H:%M"), "2026-08-08 04:00")

    def test_คริปโทปิดเที่ยงคืน_UTC_ของวันถัดไป(self):
        calendar = market_calendar.for_asset("btcusd")
        closed_at = calendar.daily_close_at("2026-08-07")

        self.assertEqual(closed_at.isoformat(), "2026-08-08T00:00:00+00:00")

    def test_ชนิดสินทรัพย์ที่ไม่ประกาศเวลาปิดต้องโยนทิ้ง_ไม่ใช่เดาให้(self):
        """ค่าไหนไม่มี = ไม่เขียนถึง — ห้ามตั้งค่าตั้งต้นเงียบ ๆ แล้วบทเชื่อว่าปิดแล้ว"""
        calendar = market_calendar.for_asset("xauusd")
        calendar.daily_close = None

        with self.assertRaises(market_calendar.UnknownCloseTime):
            calendar.daily_close_at("2026-08-07")

    def test_เวลาไร้โซนเทียบไม่ได้ต้องฟ้อง(self):
        calendar = market_calendar.for_asset("xauusd")
        with self.assertRaises(ValueError):
            calendar.is_daily_candle_closed("2026-08-07", datetime(2026, 8, 8))


class ตัดแท่งที่ยังไม่ปิดก่อนคำนวณ(unittest.TestCase):

    ROWS = [{"date": "2026-08-05", "open": 1.0, "high": 2.0, "low": 0.5, "close": 4240.82},
            {"date": "2026-08-06", "open": 1.0, "high": 2.0, "low": 0.5, "close": 4240.82},
            {"date": "2026-08-07", "open": 1.0, "high": 2.0, "low": 0.5, "close": 4304.52}]

    def test_เล่นซ้ำอาการจริง_ผลิตก่อนแท่งปิดต้องไม่ได้ราคาระหว่างวัน(self):
        """เวลาที่บทมีอาการถูกผลิตจริง: work/build/2026-08-07T02-53Z-daily"""
        moment = datetime(2026, 8, 7, 2, 53, tzinfo=timezone.utc)
        kept, basis = candle_close.evaluate(self.ROWS, asset="xauusd", now=moment)

        self.assertEqual(basis["dropped_forming_sessions"], ["2026-08-07"])
        self.assertEqual(kept[-1]["date"], "2026-08-06")
        self.assertNotEqual(kept[-1]["close"], 4304.52)   # ราคาระหว่างวันต้องไม่ถูกใช้เลย

    def test_ผลิตหลังแท่งปิดแล้วต้องใช้แท่งวันนั้นได้(self):
        """ทางที่ผู้ใช้เลือก (ทาง 1): เลื่อนเวลาผลิตไปหลังแท่งปิด แล้วคงคำว่า 'ปิด' ได้"""
        moment = datetime(2026, 8, 7, 21, 0, tzinfo=timezone.utc)   # 04:00 น. ไทยของ 8 ส.ค.
        kept, basis = candle_close.evaluate(self.ROWS, asset="xauusd", now=moment)

        self.assertEqual(basis["dropped_forming_sessions"], [])
        self.assertEqual(basis["basis_session_date"], "2026-08-07")
        self.assertEqual(basis["candle_state"], candle_close.CLOSED)

    def test_ตัดได้มากกว่าหนึ่งแท่งเมื่อปลายทางส่งล่วงหน้าหลายวัน(self):
        rows = self.ROWS + [{"date": "2026-08-10", "open": 1.0, "high": 2.0,
                             "low": 0.5, "close": 9.0}]
        moment = datetime(2026, 8, 7, 2, 53, tzinfo=timezone.utc)
        kept, basis = candle_close.evaluate(rows, asset="xauusd", now=moment)

        self.assertEqual(basis["dropped_forming_sessions"], ["2026-08-07", "2026-08-10"])
        self.assertEqual(kept[-1]["date"], "2026-08-06")

    def test_ไม่เหลือแท่งปิดเลยต้องหยุดดังๆ(self):
        moment = datetime(2026, 8, 5, 0, 0, tzinfo=timezone.utc)
        with self.assertRaises(candle_close.NoClosedCandle):
            candle_close.evaluate(self.ROWS[:1], asset="xauusd", now=moment)


class ด่านพิสูจน์สถานะแท่ง(unittest.TestCase):
    """ด่านคำนวณเวลาปิดใหม่เองทุกครั้ง — ตั้งธง candle_state เองแล้วผ่านด่านไม่ได้"""

    def test_ไม่มีก้อนหลักฐานต้องตก(self):
        detail = candle_close.verify(None, asset="xauusd", session_date="2026-08-07")
        self.assertIsNotNone(detail)

    def test_ก้อนหลักฐานชี้คนละแท่งกับบทต้องตก(self):
        basis = candle_close.basis_for("xauusd", "2026-08-06")
        detail = candle_close.verify(basis, asset="xauusd", session_date="2026-08-07")

        self.assertIn("คนละแท่ง", detail)

    def test_ธงบอกปิดแต่เวลายังไม่ถึงต้องตก(self):
        """หัวใจของ fail-closed: ด่านไม่เชื่อธง แต่ไปคำนวณเวลาปิดใหม่จาก config"""
        basis = candle_close.basis_for("xauusd", "2026-08-07")
        basis["candle_state"] = candle_close.CLOSED
        detail = candle_close.verify(
            basis, asset="xauusd", session_date="2026-08-07",
            now=datetime(2026, 8, 7, 2, 53, tzinfo=timezone.utc))

        self.assertIn("ยังมาไม่ถึง", detail)

    def test_ปิดจริงแล้วต้องผ่าน(self):
        basis = candle_close.basis_for("xauusd", "2026-08-07")
        detail = candle_close.verify(
            basis, asset="xauusd", session_date="2026-08-07",
            now=datetime(2026, 8, 8, 0, 0, tzinfo=timezone.utc))

        self.assertIsNone(detail)


if __name__ == "__main__":
    unittest.main()
