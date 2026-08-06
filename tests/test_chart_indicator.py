"""เทสสไตล์ E — เครื่องอินดิเคเตอร์ · นักเขียน+ด่าน · ตัววาด · สายผลิต

หลักที่ล็อกไว้ (ชุดเดียวกับสไตล์ D):
1. เลขทุกตัวในบทต้องชี้กลับ story ได้ (fail-closed) — เลขแปลกปลอมตัวเดียวก็ตก
2. ระดับทุกเส้นมาจากการคำนวณ — swing เล็กกว่าเกณฑ์ = ไม่วาง Fibonacci ไม่เดา
3. ตกด่าน/วาดล้มกลางคัน = โฟลเดอร์ E ต้องว่าง ไม่เหลือชุดครึ่ง ๆ กลาง ๆ
"""

import math
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import chart_indicator, chart_indicator_pipeline  # noqa: E402
from tools import chart_indicator_renderer, chart_indicator_writer  # noqa: E402


def make_rows(n=420, *, start=300.0, step=-0.3, wave=6.0):
    """แท่งสังเคราะห์แบบเดียวกับเทสสไตล์ D — คลื่นชันกว่าเทรนด์เพื่อให้มี swing จริง"""
    rows = []
    first_day = date(2025, 1, 1)
    for i in range(n):
        base = start + step * i
        close = base + wave * math.sin(i / 6)
        open_value = close - 0.4
        high = max(open_value, close) + 1.2
        low = min(open_value, close) - 1.2
        rows.append({"date": (first_day + timedelta(days=i)).isoformat(),
                     "open": open_value, "high": high, "low": low, "close": close})
    return rows


class เครื่องอินดิเคเตอร์(unittest.TestCase):

    def test_RSI_ขึ้นล้วนต้องได้_100_ลงล้วนต้องเข้าใกล้_0(self):
        rising = [float(i) for i in range(40)]
        self.assertAlmostEqual(chart_indicator.rsi(rising)[-1], 100.0)
        falling = [float(40 - i) for i in range(40)]
        self.assertLess(chart_indicator.rsi(falling)[-1], 1.0)
        self.assertIsNone(chart_indicator.rsi([1.0, 2.0])[-1])

    def test_MACD_ราคาเร่งตัวขึ้น_histogram_ต้องเป็นบวก(self):
        # ใช้ชุดเร่งตัว (กำลังสอง) — เส้นตรงสมบูรณ์ทำให้ MACD ลู่เข้าค่าคงที่และ
        # histogram เป็น 0 พอดี ซึ่งไม่ใช่กรณีที่อยากล็อก
        closes = [100.0 + i * i * 0.05 for i in range(80)]
        line, signal, hist = chart_indicator.macd(closes)
        self.assertEqual(len(line), len(closes))
        self.assertGreater(line[-1], 0)
        self.assertGreater(hist[-1], 0)
        self.assertIsNone(line[chart_indicator.MACD_SLOW - 2])

    def test_Fibonacci_ขาลงวางระดับถูกทิศ_0คือปลายล่าง_1คือยอด(self):
        story = chart_indicator.build_indicators(make_rows(), asset="xauusd")
        fib = story["fib"]

        self.assertIsNotNone(fib)
        self.assertEqual(fib["direction"], "down")
        levels = {f"{level['ratio']:g}": level["price"] for level in fib["levels"]}
        self.assertAlmostEqual(levels["0"], fib["swing_low"]["price"])
        self.assertAlmostEqual(levels["1"], fib["swing_high"]["price"])
        self.assertLess(levels["0.382"], levels["0.618"])
        self.assertLess(fib["extension"], levels["0"])
        golden_low, golden_high = fib["golden"]
        self.assertLess(golden_low, golden_high)

    def test_ขาขึ้นแผนหลักต้องเป็น_BUY_ขาลงต้องเป็น_SELL(self):
        down_story = chart_indicator.build_indicators(make_rows(), asset="xauusd")
        self.assertTrue(down_story["regime"]["down"])
        self.assertEqual(down_story["scenarios"]["primary"]["side"], "sell")
        self.assertEqual(down_story["scenarios"]["counter"]["side"], "buy")

        up_story = chart_indicator.build_indicators(
            make_rows(start=100.0, step=0.3), asset="xauusd")
        self.assertFalse(up_story["regime"]["down"])
        self.assertEqual(up_story["scenarios"]["primary"]["side"], "buy")
        self.assertEqual(up_story["scenarios"]["counter"]["side"], "sell")

    def test_แผนต้องมี_SL_เลยจุดตั้งต้นและ_RR_เป็นบวก(self):
        story = chart_indicator.build_indicators(make_rows(), asset="xauusd")
        primary = story["scenarios"]["primary"]
        fib = story["fib"]

        self.assertGreater(primary["sl"], fib["swing_high"]["price"])
        self.assertGreater(primary["rr1"], 0)
        self.assertEqual(len(primary["tps"]), 3)

    def test_swing_เล็กกว่าเกณฑ์ต้องไม่วาง_fib(self):
        view = make_rows(n=120, step=0.0, wave=0.5)
        self.assertIsNone(chart_indicator.build_fib(view, True, atr=10.0))

    def test_แท่งไม่พอต้องหยุดดังๆ(self):
        with self.assertRaises(chart_indicator.IndicatorUnavailable):
            chart_indicator.build_indicators(make_rows(n=150), asset="xauusd")


class นักเขียนและด่าน(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.rows = make_rows()
        cls.story = chart_indicator.build_indicators(cls.rows, asset="xauusd")
        cls.markdown = chart_indicator_writer.render_article(cls.story)

    def test_บทของตัวเองต้องผ่านด่านของตัวเอง(self):
        validation = chart_indicator_writer.validate(self.markdown, self.story)

        self.assertEqual(validation["status"], "pass",
                         msg=str(validation["findings"]))

    def test_เลขที่ไม่ได้คำนวณต้องตกทั้งบท(self):
        tampered = self.markdown.replace(
            chart_indicator_writer.rsi_text(self.story["rsi"]["value"]),
            "88.8", 1)
        validation = chart_indicator_writer.validate(tampered, self.story)

        self.assertEqual(validation["status"], "fail")
        self.assertTrue(any(f["rule"] == "number_not_in_story"
                            for f in validation["findings"]))

    def test_บทต้องอ้างภาพประกอบ(self):
        image = chart_indicator_writer.image_name("xauusd", self.story["current"]["date"])
        broken = self.markdown.replace(f"({image})", "(หายไป)")
        validation = chart_indicator_writer.validate(broken, self.story)

        self.assertTrue(any(f["rule"] == "missing_image"
                            for f in validation["findings"]))

    def test_บทต้องประกาศว่าแผนไม่ใช่คำทำนาย(self):
        broken = self.markdown.replace("ไม่ใช่คำทำนาย", "")
        validation = chart_indicator_writer.validate(broken, self.story)

        self.assertTrue(any(f["rule"] == "scenario_disclaimer"
                            for f in validation["findings"]))

    def test_มีแผนแต่ไม่มีหัวข้อ_Trading_Scenario_ต้องตก(self):
        broken = self.markdown.replace("Trading Scenario", "แผน")
        validation = chart_indicator_writer.validate(broken, self.story)

        self.assertTrue(any(f["rule"] == "scenario_section"
                            for f in validation["findings"]))


class ตัววาด(unittest.TestCase):

    def test_วาดภาพรวมใบเดียวได้ไฟล์จริงพร้อม_metadata(self):
        rows = make_rows()
        story = chart_indicator.build_indicators(rows, asset="xauusd")
        with tempfile.TemporaryDirectory() as tmp:
            combined_path = Path(tmp) / "combined.png"
            combined = chart_indicator_renderer.render_combined(story, rows, combined_path)

            self.assertGreater(combined_path.stat().st_size, 10_000)
            self.assertEqual(combined["bars"], story["display"]["bars"])
            self.assertTrue(combined["elements"]["fib"])
            self.assertTrue(combined["elements"]["rsi"])
            self.assertTrue(combined["elements"]["macd"])


class สายผลิต(unittest.TestCase):

    CUTOFF = "2026-08-06T12:00:00+00:00"

    def fake_fetcher(self, asset):
        return {"endpoint": "เทส"}, make_rows(), "ชุดเทส"

    def test_ผ่านด่านแล้ววางบทกับภาพครบชุด_และกวาดภาพชื่อยุคเก่า(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "06-082026" / chart_indicator_writer.FOLDER
            folder.mkdir(parents=True)
            (folder / "xauusd-1.png").write_bytes(b"png")  # ชื่อไฟล์ยุคสองภาพค้างจากรอบเก่า
            result = chart_indicator_pipeline.run(
                asset="xauusd", publish_root=Path(tmp),
                cutoff_at=self.CUTOFF, fetcher=self.fake_fetcher)

            self.assertEqual(result["status"], "pass", msg=str(result["findings"]))
            image = chart_indicator_writer.image_name("xauusd", make_rows()[-1]["date"])
            self.assertTrue((folder / "xauusd.md").exists())
            self.assertTrue((folder / image).exists())
            self.assertFalse((folder / "xauusd-1.png").exists())

    def test_ตกด่านต้องไม่เหลือไฟล์แม้ของรอบก่อน(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "06-082026" / chart_indicator_writer.FOLDER
            folder.mkdir(parents=True)
            (folder / "xauusd.md").write_text("ของรอบก่อน", encoding="utf-8")
            (folder / "xauusd-1.png").write_bytes(b"png")
            failing = {"status": "fail", "fatal_count": 1, "char_count": 0,
                       "findings": [{"rule": "x", "severity": "fatal",
                                     "line": 1, "message": "เทส"}]}
            with mock.patch.object(chart_indicator_writer, "validate",
                                   return_value=failing):
                result = chart_indicator_pipeline.run(
                    asset="xauusd", publish_root=Path(tmp),
                    cutoff_at=self.CUTOFF, fetcher=self.fake_fetcher)

            self.assertEqual(result["status"], "fail")
            self.assertTrue(result["removed_stale"])
            self.assertFalse((folder / "xauusd.md").exists())
            self.assertEqual(list(folder.glob("xauusd*.png")), [])

    def test_วาดล้มกลางคันต้องเก็บกวาดก่อนโยนต่อ(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(chart_indicator_renderer, "render_combined",
                                   side_effect=RuntimeError("จอแตก")):
                with self.assertRaises(RuntimeError):
                    chart_indicator_pipeline.run(
                        asset="xauusd", publish_root=Path(tmp),
                        cutoff_at=self.CUTOFF, fetcher=self.fake_fetcher)
            folder = Path(tmp) / "06-082026" / chart_indicator_writer.FOLDER
            self.assertEqual(list(folder.glob("xauusd*.png")), [])
            self.assertFalse((folder / "xauusd.md").exists())


if __name__ == "__main__":
    unittest.main()
