"""เทสสมุดสถิติ RR (ข้อ 3ก — หัวหน้าเคาะ 2026-08-11)

สิ่งที่เทสชุดนี้ต้องกันจริง ๆ คือ **สถิติที่ดูน่าเชื่อแต่ผิด** เพราะข้อสรุปจากสมุดนี้
จะถูกเอาไปตัดสินว่าจะรื้อโครงแผนเทรดทั้งชุดหรือไม่ — นับผิดวันเดียวก็เปลี่ยนคำตอบได้
"""

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import chart_indicator_writer, rr_ledger  # noqa: E402

FLOOR = chart_indicator_writer.RR_FLOOR


def _story(date: str, primary_rr: float | None, counter_rr: float | None) -> dict:
    def side(rr, name):
        return None if rr is None else {"side": name, "rr1": rr, "daily_entry": True}
    return {"current": {"date": date},
            "scenarios": {"primary": side(primary_rr, "sell"),
                          "counter": side(counter_rr, "buy")}}


class การบันทึก(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def _record(self, date, primary, counter):
        return rr_ledger.record(_story(date, primary, counter),
                                asset="xauusd", publish_root=self.root)

    def test_เก็บค่าดิบไม่ปัด(self):
        """เคสขอบ 1.19 vs 1.2 คือเคสที่น่าสนใจที่สุด — ปัดแล้วหาย"""
        row = self._record("2026-08-11", 1.194, 0.8)
        self.assertAlmostEqual(row["primary"]["rr1"], 1.194)
        self.assertFalse(row["any_pass"])

    def test_ผ่านเมื่อฝั่งใดฝั่งหนึ่งแตะเกณฑ์(self):
        row = self._record("2026-08-11", 0.9, FLOOR)
        self.assertTrue(row["any_pass"])
        self.assertAlmostEqual(row["best_rr"], FLOOR)

    def test_รันซ้ำวันเดิมต้องไม่กลายเป็นสองวัน(self):
        """🐞 กันบั๊กที่จะทำให้ข้อสรุปผิด — รอบผลิตวันเดียวกันรันซ้ำได้บ่อย

        (รันมือทับรอบตาราง · แก้บั๊กแล้วรันใหม่) ถ้า append ตรง ๆ วันที่รัน 3 รอบ
        จะกลายเป็น 3 วันในสถิติ แล้ว "เก็บครบ 7 วัน" จะมาถึงเร็วกว่าความจริง
        """
        self._record("2026-08-11", 0.9, 0.8)
        self._record("2026-08-11", 0.9, 0.8)
        self._record("2026-08-11", 1.5, 0.8)     # รอบที่สามค่าเปลี่ยน
        report = rr_ledger.summarize(self.root)
        self.assertEqual(report["days"], 1, "วันเดียวกันต้องเหลือแถวเดียว")
        self.assertEqual(report["days_passed"], 1, "ต้องใช้ค่าของรอบล่าสุด")

    def test_คนละสินทรัพย์วันเดียวกันอยู่ร่วมกันได้(self):
        self._record("2026-08-11", 0.9, 0.8)
        rr_ledger.record(_story("2026-08-11", 1.4, 0.8),
                         asset="btcusd", publish_root=self.root)
        self.assertEqual(rr_ledger.summarize(self.root)["days"], 2)
        self.assertEqual(rr_ledger.summarize(self.root, asset="xauusd")["days"], 1)

    def test_เรียงตามวันแม้บันทึกสลับลำดับ(self):
        self._record("2026-08-11", 0.9, 0.8)
        self._record("2026-08-09", 0.9, 0.8)
        report = rr_ledger.summarize(self.root)
        self.assertEqual(report["first_date"], "2026-08-09")
        self.assertEqual(report["last_date"], "2026-08-11")

    def test_ไม่มีแผนเลยก็ยังนับเป็นวันที่เก็บ(self):
        """วันที่ระบบไม่ตั้งแผนให้ = ข้อมูลสำคัญของข้อ 3ก ไม่ใช่วันที่ควรข้าม"""
        row = self._record("2026-08-11", None, None)
        self.assertIsNone(row["best_rr"])
        self.assertFalse(row["any_pass"])
        self.assertEqual(rr_ledger.summarize(self.root)["days"], 1)


class ความน่าเชื่อของสมุด(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_ยังไม่มีไฟล์ไม่ใช่ข้อผิดพลาด(self):
        self.assertEqual(rr_ledger.summarize(self.root)["days"], 0)

    def test_บรรทัดเสียต้องระเบิดไม่ใช่ข้ามเงียบ(self):
        """ข้ามเงียบ = สมุดบอกว่าเก็บ 8 วันทั้งที่จริง 6 — สถิติที่โกหกแย่กว่าไม่มีสถิติ"""
        path = rr_ledger.ledger_path(self.root)
        path.write_text('{"date": "2026-08-09"}\nไม่ใช่ JSON\n', encoding="utf-8")
        with self.assertRaises(ValueError):
            rr_ledger.summarize(self.root)

    def test_สมุดไม่แตะเกณฑ์_RR_FLOOR(self):
        """สมุดเป็นตัวบันทึก ไม่ใช่ด่าน — ห้ามมีทางที่มันไปเปลี่ยนเกณฑ์"""
        before = chart_indicator_writer.RR_FLOOR
        rr_ledger.record(_story("2026-08-11", 0.5, 0.4),
                         asset="xauusd", publish_root=self.root)
        self.assertEqual(chart_indicator_writer.RR_FLOOR, before)


if __name__ == "__main__":
    unittest.main()
