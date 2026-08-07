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

    def test_FIB_BARS_ต้องเท่ากับ_PANEL_BARS(self):
        """E-4 (ฟีดแบ็กหัวหน้า 08-07): หน้าต่างหา swing ต้องเท่ากับหน้าต่างที่วาดภาพ

        เดิม FIB_BARS=120 < PANEL_BARS=160 ⇒ จุดสูงสุดจริงอยู่ในช่วง 121-160 (มองเห็น
        บนภาพ) แต่ตัวหา swing ไม่เห็นเพราะค้นแค่ 120 แท่งหลังสุด — บั๊กจริง: D บอกจุดสูงสุด
        5,597.23 แต่ E ลาก Fib จาก 5,417.76 ทั้งที่แท่งที่สูงกว่าอยู่ในภาพเดียวกัน
        """
        self.assertEqual(chart_indicator.FIB_BARS, chart_indicator.PANEL_BARS)


def _synthetic_fib(*, direction="down", low=100.0, high=200.0):
    """fib สังเคราะห์ที่คุมตัวเลขได้แม่นยำ — ใช้ทดสอบ _scenarios() ตรง ๆ โดยไม่ต้อง
    พึ่งแท่งราคาสังเคราะห์ที่ควบคุมตำแหน่ง swing ยากกว่ามาก"""
    span = high - low
    fib = {"direction": direction,
          "swing_high": {"date": "2026-01-01", "price": high},
          "swing_low": {"date": "2026-02-01", "price": low}, "span": span}
    fib["levels"] = [{"ratio": r, "price": chart_indicator.fib_level(fib, r)}
                     for r in chart_indicator.FIB_RATIOS]
    fib["golden"] = sorted([chart_indicator.fib_level(fib, chart_indicator.GOLDEN_LOW_RATIO),
                            chart_indicator.fib_level(fib, chart_indicator.GOLDEN_HIGH_RATIO)])
    fib["extension"] = chart_indicator.fib_level(
        fib, -(chart_indicator.EXTENSION_RATIO - 1.0))
    return fib


class เกณฑ์ระยะห่างรายวันของฉากทัศน์(unittest.TestCase):
    """E-1 (ฟีดแบ็กหัวหน้า 08-07): บังคับกฎ 10×ATR กับสไตล์ E ด้วย ไม่ใช่แค่ D

    บั๊กจริง: Golden Zone เคยห่างราคา 14.8–20.6% (13.8–19.2×ATR) แต่ยังถูกเสนอเป็น
    แผนหลักของบทรายวัน — ทะเบียน STATUS.md รายการ #14 บอกว่ากฎนี้ต้องบังคับทุกสไตล์
    """

    def test_โซนไกลเกิน10เท่าATRต้องติดธง_daily_entry_False(self):
        fib = _synthetic_fib()   # primary entry ~170.2 · counter entry ~111.8
        scenarios = chart_indicator._scenarios(fib, True, atr=1.0, current_price=165.0)
        self.assertTrue(scenarios["primary"]["daily_entry"],
                        "primary entry_mid≈170.2 ห่างราคา165 แค่ ~5.2×ATR ต้องยังนับเป็นรายวัน")
        self.assertFalse(scenarios["counter"]["daily_entry"],
                         "counter entry_mid≈111.8 ห่างราคา165 ถึง ~53×ATR ต้องไม่นับเป็นรายวัน")

    def test_ไม่ส่งราคาปัจจุบันมาต้องถือว่าผ่านเกณฑ์เสมอ(self):
        """ผู้เรียกเก่าที่ยังไม่ส่ง current_price (ถ้ามี) ต้องไม่พังหรือเงียบเปลี่ยนพฤติกรรม"""
        fib = _synthetic_fib()
        scenarios = chart_indicator._scenarios(fib, True, atr=1.0)
        self.assertTrue(scenarios["primary"]["daily_entry"])
        self.assertTrue(scenarios["counter"]["daily_entry"])
        self.assertFalse(scenarios["primary"]["active"])

    def test_ราคาปัจจุบันอยู่ในโซนต้องติดธง_active(self):
        fib = _synthetic_fib()
        scenarios = chart_indicator._scenarios(fib, True, atr=1.0, current_price=165.0)
        self.assertTrue(scenarios["primary"]["active"],
                        "165 อยู่ในช่วง entry ของ primary (161.8–178.6) ต้อง active")
        self.assertFalse(scenarios["counter"]["active"])


class RRที่ขอบเสียเปรียบ(unittest.TestCase):
    """E-2 (ฟีดแบ็กหัวหน้า 08-07): RR เดิมคำนวณจากกลางโซน โซนกว้าง 5% เข้าคนละขอบ
    ตัวเลขคนละเรื่อง — บทบอก RR 1:1.4 แต่เข้าขอบเสียเปรียบได้แค่ 0.93 (ตกเกณฑ์ 1.2)
    """

    def test_SELL_ขอบเสียเปรียบคือ_entry_low_ให้_RR_ต่ำกว่าคำนวณจากกลางโซน(self):
        fib = _synthetic_fib()
        scenario = chart_indicator._scenarios(fib, True, atr=1.0)["primary"]
        self.assertEqual(scenario["side"], "sell")
        self.assertEqual(scenario["disadvantaged_entry"], scenario["entry_low"],
                         "SELL อยากขายแพง — ขอบเสียเปรียบคือราคาต่ำกว่า (entry_low)")

        mid_risk = abs(scenario["sl"] - scenario["entry_mid"])
        mid_reward = abs(scenario["tps"][0] - scenario["entry_mid"])
        rr_from_mid = mid_reward / mid_risk
        self.assertLess(scenario["rr1"], rr_from_mid,
                        "RR จากขอบเสียเปรียบต้องต่ำกว่า RR ที่คำนวณจากกลางโซนเสมอสำหรับ SELL")
        self.assertAlmostEqual(scenario["rr1"], 38.2 / 38.7, places=2)

    def test_BUY_ขอบเสียเปรียบคือ_entry_high(self):
        fib = _synthetic_fib(direction="up")
        scenario = chart_indicator._scenarios(fib, False, atr=1.0)["primary"]
        self.assertEqual(scenario["side"], "buy")
        self.assertEqual(scenario["disadvantaged_entry"], scenario["entry_high"],
                         "BUY อยากซื้อถูก — ขอบเสียเปรียบคือราคาสูงกว่า (entry_high)")


class ฉากทัศน์Bต้องปรากฏในบท(unittest.TestCase):
    """E-3 (ฟีดแบ็กหัวหน้า 08-07): Scenario B ไม่เคยถูกวาด/อธิบายมาก่อน

    บั๊กจริงที่ต้องอ่านสองรอบ: ราคาอยู่ในโซนของ Scenario B แล้ว แต่บทเขียนว่า
    "รอราคาย่อกลับลงมา" — ขัดกับความจริงตรง ๆ
    """

    @classmethod
    def setUpClass(cls):
        # ATR กว้างพอให้ทั้งสองฉากทัศน์ยังนับเป็นแผนรายวัน (ต้องการทดสอบว่าทั้งคู่
        # ปรากฏในบทพร้อมกัน) แต่ current_price อยู่เฉพาะในโซนของ counter เท่านั้น
        # เพื่อพิสูจน์ธง active แยกความแตกต่างระหว่างสองฉากทัศน์ได้จริง
        fib = _synthetic_fib()
        cls.story = {
            "asset": "xauusd", "symbol": "XAU/USD",
            "display": {"bars": 160, "fib_bars": 160,
                       "start_date": "2025-01-01", "end_date": "2026-08-07"},
            "current": {"date": "2026-08-07", "close": 115.0},
            "atr14": 20.0, "sma50_last": 150.0,
            "regime": {"down": True, "rule": "x", "flip_date": None},
            "rsi": {"value": 45.0, "rising": True, "zone": "bearish"},
            "macd": {"line": 1.0, "signal": 0.5, "histogram": 0.5, "bullish": True,
                    "cross_date": None, "histogram_shrinking": False},
            "fib": fib,
            "scenarios": chart_indicator._scenarios(fib, True, atr=20.0, current_price=115.0),
        }
        cls.article = chart_indicator_writer.render_article(cls.story)

    def test_ทั้งสองฉากทัศน์ต้องผ่านเกณฑ์รายวันพร้อมกันในเซ็ตอัปนี้(self):
        """ยืนยันสมมติฐานของชุดเทสนี้ก่อน — กันไม่ให้แก้ atr/current_price ในอนาคต
        แล้วเทสข้างล่างพังแบบดูไม่ออกว่าเพราะอะไร"""
        self.assertTrue(self.story["scenarios"]["primary"]["daily_entry"])
        self.assertTrue(self.story["scenarios"]["counter"]["daily_entry"])

    def test_ราคาอยู่ในโซน_counter_ต้องบอกว่า_active_ไม่ใช่รอ(self):
        self.assertTrue(self.story["scenarios"]["counter"]["active"])
        idx_b = self.article.find("Scenario B")
        idx_next = self.article.find("Scenario", idx_b + 1)
        block_b = self.article[idx_b: idx_next if idx_next != -1 else idx_b + 1500]
        self.assertIn("🟢", block_b)
        self.assertIn("active", block_b)
        self.assertNotIn("⚪", block_b)

    def test_TPและEntry_ต้องอ้างอิงอัตราส่วน_Fibonacci_ที่มาของตัวเลข(self):
        """บั๊กจริง: TP1 ถูกใช้ทั้งสองฉากทัศน์แต่บทไม่เคยบอกว่ามันคือ Fib 0.236"""
        self.assertIn("Fib 0.236", self.article)
        self.assertIn("Fibonacci Golden Zone", self.article)
        self.assertIn("Fibonacci 0–0.236", self.article)

    def test_บทของตัวเองต้องผ่านด่านของตัวเอง(self):
        validation = chart_indicator_writer.validate(self.article, self.story)
        self.assertEqual(validation["status"], "pass", msg=str(validation["findings"]))


class ฉากทัศน์ไกลเกินไม่แสดงในบท(unittest.TestCase):
    def test_ฉากทัศน์ที่ไกลเกินต้องมีข้อความอธิบายแทนที่จะเงียบหาย(self):
        fib = _synthetic_fib()
        # ราคาห่างจาก counter (entry_mid≈111.8) เกิน 10×ATR แต่ใกล้ primary (≈170.2)
        scenarios = chart_indicator._scenarios(fib, True, atr=1.0, current_price=165.0)
        story = {
            "asset": "xauusd", "symbol": "XAU/USD",
            "display": {"bars": 160, "fib_bars": 160,
                       "start_date": "2025-01-01", "end_date": "2026-08-07"},
            "current": {"date": "2026-08-07", "close": 165.0},
            "atr14": 1.0, "sma50_last": 150.0,
            "regime": {"down": True, "rule": "x", "flip_date": None},
            "rsi": {"value": 45.0, "rising": True, "zone": "bearish"},
            "macd": {"line": 1.0, "signal": 0.5, "histogram": 0.5, "bullish": True,
                    "cross_date": None, "histogram_shrinking": False},
            "fib": fib, "scenarios": scenarios,
        }
        article = chart_indicator_writer.render_article(story)
        self.assertIn("Scenario B (BUY (Counter Trend)) ไม่แสดงในบทนี้", article)
        self.assertIn("Scenario A: SELL", article)
        validation = chart_indicator_writer.validate(article, story)
        self.assertEqual(validation["status"], "pass", msg=str(validation["findings"]))


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
