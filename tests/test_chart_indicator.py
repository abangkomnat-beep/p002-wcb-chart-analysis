"""เทสสไตล์ E — เครื่องอินดิเคเตอร์ · นักเขียน+ด่าน · ตัววาด · สายผลิต

หลักที่ล็อกไว้ (ชุดเดียวกับสไตล์ D):
1. เลขทุกตัวในบทต้องชี้กลับ story ได้ (fail-closed) — เลขแปลกปลอมตัวเดียวก็ตก
2. ระดับทุกเส้นมาจากการคำนวณ — swing เล็กกว่าเกณฑ์ = ไม่วาง Fibonacci ไม่เดา
3. ตกด่าน/วาดล้มกลางคัน = โฟลเดอร์ E ต้องว่าง ไม่เหลือชุดครึ่ง ๆ กลาง ๆ
"""

import json
import math
import re
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import candle_close, chart_indicator, chart_indicator_pipeline  # noqa: E402
from tools import chart_story  # noqa: E402
from tools import chart_indicator_renderer, chart_indicator_writer  # noqa: E402
from tools import image_output  # noqa: E402


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


class บทสาธารณะแสดงเฉพาะฝั่งหลักฐานมากที่สุด(unittest.TestCase):
    """ระบบคำนวณอีกฝั่งไว้ภายในได้ แต่บทสาธารณะต้องเสนอเพียงแผนหลักฝั่งเดียว"""

    @classmethod
    def setUpClass(cls):
        # ทั้งสองฉากทัศน์ผ่านเกณฑ์ภายใน และราคาอยู่ในโซน counter เท่านั้น
        # เพื่อพิสูจน์ว่าระบบไม่เผลอนำอีกฝั่งมาแสดงแม้สถานะ active
        #
        # 🔄 **ขยับสเกลขึ้นเป็นแถวราคาทองจริงเมื่อ 08-11** — ของเดิม (swing 100–200 ·
        # ราคา 115 · ATR 20) ให้ ATR = 17% ของราคา และ Golden Zone ห่างราคา 48%
        # ซึ่งไม่ใช่ตัวเลขที่เกิดได้จริง · พอเพิ่มเพดาน % ตามข้อ 1ก เซ็ตอัปนี้เลยตกทันที
        # ⇒ แก้ที่ **ความสมจริงของเซ็ตอัป** ไม่ใช่ผ่อนเกณฑ์ · อัตราส่วน Fibonacci
        # ทุกตัวเหมือนเดิมเป๊ะ (สเกลเลื่อนทั้งชุด) เทสที่อ้างอัตราส่วนจึงไม่กระทบ
        fib = _synthetic_fib(low=4100.0, high=4200.0)
        cls.story = {
            "asset": "xauusd", "symbol": "XAU/USD",
            "display": {"bars": 160, "fib_bars": 160,
                       "start_date": "2025-01-01", "end_date": "2026-08-07"},
            "current": {"date": "2026-08-07", "close": 4115.0},
            "atr14": 20.0, "sma50_last": 4150.0,
            "regime": {"down": True, "rule": "x", "flip_date": None},
            "rsi": {"value": 45.0, "rising": True, "zone": "bearish"},
            "macd": {"line": 1.0, "signal": 0.5, "histogram": 0.5, "bullish": True,
                    "cross_date": None, "histogram_shrinking": False},
            "fib": fib,
            "scenarios": chart_indicator._scenarios(fib, True, atr=20.0, current_price=4115.0),
            # A-1: story ที่ประกอบมือก็ต้องพกก้อนหลักฐานแท่งปิด ไม่งั้นตกด่าน
            # `closed_candle_required` — สร้างจากตัวสร้างเดียวกับสายผลิตจริง
            "candle_basis": candle_close.basis_for("xauusd", "2026-08-07"),
        }
        cls.article = chart_indicator_writer.render_article(cls.story)

    def test_ทั้งสองฉากทัศน์ยังคำนวณเป็นหลักฐานภายในได้(self):
        self.assertTrue(self.story["scenarios"]["primary"]["daily_entry"])
        self.assertTrue(self.story["scenarios"]["counter"]["daily_entry"])

    def test_บทไม่แสดง_counter_แม้ราคาอยู่ในโซนของมัน(self):
        self.assertTrue(self.story["scenarios"]["counter"]["active"])
        self.assertIn("### แผน A:", self.article)
        self.assertNotIn("แผน B:", self.article)
        self.assertNotIn("Counter Trend", self.article)

    def test_แผนไม่มีป้าย_Fib_แต่ที่มาของตัวเลขยังไล่ได้จากหัวข้อ_3(self):
        """🔄 08-14 รอบสอง (ผู้ใช้สั่ง): ป้าย "(Fibonacci …)/(Fib …)" ท้าย Entry/TP ถูกถอด
        — ที่มาของทุกระดับยังอยู่ในหัวข้อ 3 ซึ่งลิสต์ราคาของทุกชั้น Fib (ด่าน
        `fib_level_not_in_article` ตรวจที่ราคา จึงยังคุ้มครองเหมือนเดิม)"""
        self.assertNotIn("(Fib ", self.article)
        self.assertNotIn("(Fibonacci 0", self.article)
        for level in self.story["fib"]["levels"]:
            price = chart_indicator_writer.money_for(self.story)(level["price"])
            self.assertIn(price, self.article, f"ราคา Fib {level['ratio']:g} หายจากบท")

    def test_บทของตัวเองต้องผ่านด่านของตัวเอง(self):
        validation = chart_indicator_writer.validate(self.article, self.story)
        self.assertEqual(validation["status"], "pass", msg=str(validation["findings"]))


class ฉากทัศน์ไกลเกินไม่แสดงในบท(unittest.TestCase):
    def test_ไม่กล่าวถึงฝั่งตรงข้ามเมื่อแผนหลักยังใช้ได้(self):
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
            "candle_basis": candle_close.basis_for("xauusd", "2026-08-07"),
        }
        article = chart_indicator_writer.render_article(story)
        self.assertIn("### แผน A: ฝั่ง SELL (Follow Trend — เทรดตามแนวโน้มใหญ่)", article)
        self.assertNotIn("แผน B:", article)
        self.assertNotIn("Counter Trend", article)
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

    def test_ระดับ_1_272_เรียกเป็นแนวอ้างอิงไม่ใช่เป้าขยาย(self):
        self.assertIn("**1.272**", self.markdown)
        self.assertIn("แนวอ้างอิงด้านล่าง หากราคาหลุดจุดต่ำสุดเดิม", self.markdown)
        self.assertNotIn("เป้าขยาย", self.markdown)

    def test_บทนำไม่มีย่อหน้ารับรองที่ผู้ใช้สั่งตัด(self):
        self.assertNotIn("ทุกค่าและทุกระดับในบทนี้คำนวณจากแท่งราคาชุดเดียว", self.markdown)
        self.assertNotIn("จึงสามารถตรวจสอบที่มาของตัวเลขได้", self.markdown)

    def test_บทนำจบด้วยภาพรวมแนวโน้มรายวัน(self):
        trend = "ขาลง" if self.story["regime"]["down"] else "ขาขึ้น"
        self.assertIn(f"ขณะที่ภาพรวมรายวันยังอยู่ในแนวโน้ม{trend}", self.markdown)
        self.assertNotIn("ท่ามกลางโหมดตลาด", self.markdown)

    def test_เลขที่ไม่ได้คำนวณต้องตกทั้งบท(self):
        tampered = self.markdown.replace(
            chart_indicator_writer.rsi_text(self.story["rsi"]["value"]),
            "88.8", 1)
        validation = chart_indicator_writer.validate(tampered, self.story)

        self.assertEqual(validation["status"], "fail")
        self.assertTrue(any(f["rule"] == "number_not_in_story"
                            for f in validation["findings"]))

    def test_บทต้องอ้างภาพประกอบ(self):
        image = chart_indicator_writer.image_name(
            "xauusd", self.story["current"]["date"], self.story.get("timeframe", "1day"))
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

    def test_สไตล์Eไม่แสดงหรือรับแผน_RR(self):
        """ผู้ใช้สั่ง 08-19: E คง Entry/SL/TP แต่ถอด R:R ออกจากบททั้งระบบ"""
        for term in ("อัตราส่วนเสี่ยง:ผลตอบแทน", "R:R", "Risk/Reward",
                     "ต่ำกว่าเกณฑ์ ยังไม่เข้า"):
            self.assertNotIn(term, self.markdown)

        broken = self.markdown + "\n\nอัตราส่วนเสี่ยง:ผลตอบแทน"
        validation = chart_indicator_writer.validate(broken, self.story)
        self.assertTrue(any(f["rule"] == "risk_reward_forbidden"
                            for f in validation["findings"]))

    def test_ไม่มีย่อหน้าคำเตือนความเสี่ยงในบทแล้ว(self):
        """ผู้ใช้สั่ง 08-14: เว็บมีคำเตือนของตัวเองอยู่แล้ว บทจึงไม่พกซ้ำ

        ⚠️ ด่าน `risk_disclaimer` ถูกถอดพร้อมกัน — เทสนี้ยืนยันว่าถอดจริงทั้งคู่
        (ย่อหน้าหาย + validate ยังผ่าน) ไม่ใช่ถอดย่อหน้าแล้วลืมด่านจนบทตกทุกวัน"""
        self.assertNotIn("คำเตือนความเสี่ยง", self.markdown)
        self.assertEqual(chart_indicator_writer.validate(self.markdown, self.story)["status"],
                         "pass")

    def test_หัวข้อ_1_เจาะ_RSI_MACD_Fibonacci_โดยไม่ยืมภาษาโครงสร้าง_D(self):
        start = self.markdown.index(f"## 1. {chart_indicator_writer.H2_STRUCTURE}")
        end = self.markdown.index("\n---", start)
        section = self.markdown[start:end]

        for term in ("RSI", "MACD", "Fibonacci"):
            self.assertIn(term, section)
        self.assertNotIn("MA 50 วัน", section)
        self.assertNotIn("Major Downleg", section)
        self.assertNotIn("ภาพรวมโครงสร้างตลาด", section)

    def test_หัวข้อ_4_ไม่มีบล็อกขยายความ(self):
        """ผู้ใช้สั่ง 08-14: หัวข้อ 4 เอาแค่ตัวเลขสำคัญ — บล็อกขั้นตอนปฏิบัติ (เพิ่ม 08-11)
        กับวงเล็บอธิบายที่มาของ SL ถูกถอด"""
        self.assertNotIn("**ขั้นตอนปฏิบัติ — ลำดับก่อนเข้าเทรด:**", self.markdown)
        self.assertNotIn("เลยจุดตั้งต้น swing และห่างขอบโซนเข้า", self.markdown)
        self.assertNotIn("จากขอบที่เสียเปรียบของโซนเข้า", self.markdown)
        # วลีบังคับของด่านยังต้องอยู่แม้ย่อประโยคแล้ว
        self.assertIn("ไม่ใช่คำทำนาย", self.markdown)

    def test_สรุปเป็นสรุปจริงและจบในหัวข้อ(self):
        """🔄 08-14 รอบสอง/สาม (ผู้ใช้สั่ง): สรุปต้องอ่านหัวข้อเดียวแล้วจบ — ราคาวันนี้
        อยู่ตรงไหน รอเข้าฝั่ง BUY/SELL ที่เท่าไร ต้องสังเกตอะไร · ห้ามอ้างหัวข้อ 4
        (โผล่เมื่อมี fib + แผนรายวันอย่างน้อยหนึ่งฝั่ง — story ของเทสนี้มีครบ)"""
        if self.story["scenarios"]["primary"].get("daily_entry", True):
            for label in ("**ราคาวันนี้:**", "**ฝั่งที่รอเข้า:**",
                          "**จุดที่รอเข้า:**", "**สิ่งที่ต้องสังเกต:**"):
                self.assertIn(label, self.markdown, f"สรุปขาดข้อ {label}")
        else:
            self.assertIn("แผนหลักอยู่ห่างเกินเกณฑ์รายวัน", self.markdown)
        self.assertNotIn("ในหัวข้อ 4", self.markdown)
        self.assertNotIn("สรุปสั้นที่สุดได้ว่า", self.markdown)
        # ฝั่งที่รอเข้าต้องบอก BUY หรือ SELL จริง ๆ ไม่ใช่ชื่อแผนเปล่า ๆ · ป้ายแผน
        # ขึ้นนำได้เฉพาะวันที่มีสองแผนพร้อมกัน (ต้องจับคู่กับ "จุดที่รอเข้า" ได้)
        if "**ฝั่งที่รอเข้า:**" in self.markdown:
            self.assertRegex(self.markdown, r"\*\*ฝั่งที่รอเข้า:\*\* (BUY|SELL)")
            side_line = next(line for line in self.markdown.splitlines()
                             if "**ฝั่งที่รอเข้า:**" in line)
            self.assertNotIn("เทรนด์หลัก", side_line)

    def test_สิ่งที่ต้องสังเกตบอกเงื่อนไขที่ยังไม่ครบจริง(self):
        """🔄 08-14 รอบสาม/สี่ — บรรทัดนี้ต้องบอกว่า "ต้องเห็นอะไรถึงจะเข้า" ไม่ใช่
        ทวนสถานะเฉย ๆ: ราคาเข้าโซนหรือยัง + แรงรับ/แรงต้านใน TF ย่อย แล้วจบ
        (ผู้ใช้สั่งรอบสี่: ตัดหมายเหตุ MACD กับวลีปิดท้ายออก)"""
        story = json.loads(json.dumps(self.story))
        primary = story["scenarios"]["primary"]
        story["current"]["close"] = primary["entry_mid"]
        story["scenarios"] = chart_indicator._scenarios(
            story["fib"], story["regime"]["down"], story["atr14"], primary["entry_mid"])
        markdown = chart_indicator_writer.render_article(story)
        watch = next(line for line in markdown.splitlines()
                     if "**สิ่งที่ต้องสังเกต:**" in line)

        self.assertIn("1H/15M", watch)
        self.assertRegex(watch, r"แรงรับ|แรงต้าน|สัญญาณยืนยัน")
        self.assertNotIn("Histogram", watch)
        self.assertNotIn("ไม่ใช่คำทำนาย", watch)
        # ⚠️ วลีบังคับย้ายไปอยู่ที่ประโยคปิดหัวข้อ 4 ที่เดียว — ต้องยังอยู่ในบท
        self.assertIn("ไม่ใช่คำทำนาย", markdown)


class ตัววาด(unittest.TestCase):

    def test_ป้ายภาพใช้ภาษาไทยและซ่อน_fibonacci_ระดับระหว่างทาง(self):
        self.assertEqual(chart_indicator_renderer.VISIBLE_FIB_RATIOS,
                         frozenset({0.236, 0.618, 0.786}))
        self.assertEqual(chart_indicator_renderer._rsi_status(41.3),
                         "ฝั่งขายครองตลาด")
        self.assertEqual(chart_indicator_renderer._rsi_status(58.7),
                         "ฝั่งซื้อครองตลาด")
        self.assertEqual(chart_indicator_renderer._macd_status(1.29),
                         "รีบาวด์ระยะสั้น")
        self.assertEqual(chart_indicator_renderer._macd_status(-1.29),
                         "แรงขายระยะสั้น")

        sell = {"side": "sell", "entry_low": 4_396.62, "entry_high": 4_420.00}
        label = chart_indicator_renderer._entry_zone_label(sell, lambda value: f"{value:,.2f}")
        self.assertIn("โซนรอ SELL (ตามเทรนด์หลัก)", label)
        self.assertIn("โซนรอเข้าออเดอร์ · แนวต้านสำคัญ (61.8%–78.6%)", label)
        self.assertIn("4,396.62–4,420.00", label)
        self.assertEqual(chart_indicator_renderer._entry_zone_label_position(
            {"asset": "xauusd"}, 160, 191.0), (189.5, "right"))
        self.assertEqual(chart_indicator_renderer._entry_zone_label_position(
            {"asset": "eurusd"}, 160, 191.0), (89, "center"))

    def test_วาดภาพรวมใบเดียวได้ไฟล์จริงพร้อม_metadata(self):
        rows = make_rows()
        story = chart_indicator.build_indicators(rows, asset="xauusd")
        with tempfile.TemporaryDirectory() as tmp:
            combined_path = Path(tmp) / "combined.webp"
            combined = chart_indicator_renderer.render_combined(story, rows, combined_path)

            self.assertGreater(combined_path.stat().st_size, 10_000)
            # กติกาเว็บ 08-09 — วัดจากไฟล์จริง ไม่ใช่เชื่อค่าคุณภาพที่ตั้งไว้
            self.assertEqual(image_output.verify(combined_path), combined["bytes"])
            self.assertEqual(combined["bars"], story["display"]["bars"])
            self.assertTrue(combined["elements"]["fib"])
            self.assertTrue(combined["elements"]["rsi"])
            self.assertTrue(combined["elements"]["macd"])
            self.assertFalse(combined["elements"]["header"])
            self.assertFalse(combined["elements"]["counter"])
            self.assertEqual(combined["background"], "#ffffff")
            self.assertEqual(combined["layout"]["entry_zone_label"], "right")
            self.assertEqual(combined["layout"]["current_price"], "latest_candle")

            from PIL import Image
            with Image.open(combined_path) as rendered:
                corner = rendered.convert("RGB").getpixel((0, 0))
            self.assertTrue(all(channel >= 248 for channel in corner), corner)


class สายผลิต(unittest.TestCase):

    CUTOFF = "2026-08-06T12:00:00+00:00"

    def fake_fetcher(self, asset, *, timeframe):
        rows = [{**row, "at": f"{row['date']} 00:00:00", "forming": False}
                for row in make_rows()]
        return {"endpoint": "เทส", "timeframe": timeframe}, rows, "ชุดเทส H1"

    def test_ผ่านด่านแล้ววางบทกับภาพครบชุด_และกวาดภาพชื่อยุคเก่า(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "06-08-2026" / chart_indicator_writer.FOLDER
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
            # ทุกใบที่วางลงโฟลเดอร์วันต้องผ่านกติกาเว็บ (.webp ≤ 200 KB)
            self.assertEqual(len(image_output.verify_folder(folder)), 1)

    def test_ตกด่านต้องไม่เหลือไฟล์แม้ของรอบก่อน(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "06-08-2026" / chart_indicator_writer.FOLDER
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
            # กวาดต้องครอบรูปยุค `.png` ด้วย ไม่ใช่เฉพาะนามสกุลปัจจุบัน
            self.assertEqual(list(folder.glob("xauusd*")), [])

    def test_วาดล้มกลางคันต้องเก็บกวาดก่อนโยนต่อ(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(chart_indicator_renderer, "render_combined",
                                   side_effect=RuntimeError("จอแตก")):
                with self.assertRaises(RuntimeError):
                    chart_indicator_pipeline.run(
                        asset="xauusd", publish_root=Path(tmp),
                        cutoff_at=self.CUTOFF, fetcher=self.fake_fetcher)
            folder = Path(tmp) / "06-08-2026" / chart_indicator_writer.FOLDER
            self.assertEqual(list(folder.glob("xauusd*.webp")), [])
            self.assertFalse((folder / "xauusd.md").exists())


REAL_ROWS = json.loads(
    (REPO_ROOT / "tests" / "fixtures" / "xau_420_sessions_2026-08-07.json")
    .read_text(encoding="utf-8"))


class สไตล์_E_ก็ต้องยืนบนแท่งที่ปิดแล้ว(unittest.TestCase):
    """A-1 — บทสไตล์ E เปิดด้วย "แท่งรายวันล่าสุดปิดที่ X" เหมือนกัน ⇒ ต้องผ่านด่านเดียวกัน
    และต้องยืนบนชุดแท่งเดียวกับสไตล์ D ไม่งั้นสองสไตล์เล่าคนละความจริงในวันเดียวกัน
    """

    @classmethod
    def setUpClass(cls):
        cls.story = chart_indicator.build_indicators(REAL_ROWS, asset="xauusd")
        cls.article = chart_indicator_writer.render_article(cls.story)

    def test_แท่งที่ยังไม่ปิดถูกตัดก่อนคำนวณอินดิเคเตอร์(self):
        future = (date.today() + timedelta(days=1)).isoformat()
        rows = REAL_ROWS + [{**REAL_ROWS[-1], "date": future, "close": 1.0}]

        story = chart_indicator.build_indicators(rows, asset="xauusd")

        self.assertNotEqual(story["current"]["date"], future)
        self.assertEqual(story["rsi"]["value"], self.story["rsi"]["value"])
        self.assertEqual(story["fib"]["swing_high"], self.story["fib"]["swing_high"])

    def test_ราคาปิดในบทตรงกับที่ทีมเว็บทานสอบ(self):
        # 🔄 08-14 — วงเล็บวันของแท่งฐานถูกเพิ่ม (พาดหัวลงวันเผยแพร่แล้ว)
        self.assertIn("โดยใช้แท่งรายวันล่าสุด (7 ส.ค. 2026) ซึ่งปิดที่ 4,342.63 ดอลลาร์",
                      self.article)

    def test_ด่านตกเมื่อพิสูจน์ไม่ได้ว่าแท่งปิดแล้ว(self):
        broken = dict(self.story, candle_basis=None)

        validation = chart_indicator_writer.validate(self.article, broken)

        self.assertEqual(validation["status"], "fail")
        self.assertTrue(any(f["rule"] == "closed_candle_required"
                            for f in validation["findings"]))


class SL_ของสไตล์_E_ต้องผ่านเกณฑ์เดียวกับสไตล์_D(unittest.TestCase):
    """🐞 **B-1 (2026-08-09)** — SL เดิมเผื่อจากจุดตั้งต้น swing แค่ 0.5×ATR ⇒ ฝั่ง
    สวนเทรนด์ได้ SL ห่างขอบโซนเข้าเพียง 0.5×ATR ต่ำกว่าเกณฑ์ 1×ATR ที่บังคับสไตล์ D
    หัวหน้าสั่งชัดว่าเกณฑ์เดียวต้องคุมทุกสไตล์ ไม่ใช่เฉพาะคู่ที่เคยถูกฟ้อง
    """

    @classmethod
    def setUpClass(cls):
        cls.story = chart_indicator.build_indicators(REAL_ROWS, asset="xauusd")
        cls.article = chart_indicator_writer.render_article(cls.story)

    def test_ทุกฉากทัศน์ที่แสดงในบทต้องมีระยะอย่างน้อยหนึ่งเท่าของ_ATR(self):
        pairs = chart_indicator_writer.invalidation_pairs(self.story)
        expected = 1 if self.story["scenarios"]["primary"].get("daily_entry", True) else 0
        self.assertEqual(len(pairs), expected)
        for pair in pairs:
            gap = chart_story.invalidation_gap_atr(
                pair["zone_low"], pair["zone_high"], pair["invalidation"],
                self.story["atr14"])
            self.assertGreaterEqual(round(gap, 6), chart_story.MIN_INVALIDATION_ATR,
                                    msg=pair["label"])

    def test_ฉากทัศน์สวนเทรนด์เคยได้แค่ครึ่ง_ATR_ตอนนี้ต้องเต็มหนึ่ง(self):
        counter = self.story["scenarios"]["counter"]
        zone_edge = min(counter["entry_low"], counter["entry_high"])
        self.assertAlmostEqual((zone_edge - counter["sl"]) / self.story["atr14"], 1.0,
                               places=6)

    def test_ด่านตกเมื่อ_SL_ถูกดันเข้ามาใกล้โซนเกินไป(self):
        broken = json.loads(json.dumps(self.story))
        primary = broken["scenarios"]["primary"]
        primary["daily_entry"] = True
        article = chart_indicator_writer.render_article(broken)
        primary["sl"] = (min(primary["entry_low"], primary["entry_high"])
                         if primary["side"] == "buy"
                         else max(primary["entry_low"], primary["entry_high"]))

        validation = chart_indicator_writer.validate(article, broken)

        self.assertTrue(any(f["rule"] == "invalidation_inside_entry_zone"
                            for f in validation["findings"]))


class เส้นบนภาพต้องเท่ากับเส้นที่บทพูดถึง(unittest.TestCase):
    """🐞 **B-3.2 (ทีมเว็บ 2026-08-09)** — ภาพวาดเส้น 0.705 และ 0.886 ที่บทไม่ได้พูดถึง
    เลย ขัดกติกาเดิมของระบบ (ขีดเฉพาะระดับที่พูดถึงจริง ไม่ใช่ยัดทุกค่าที่มี)
    อาการเดียวกับ "เส้นกำพร้า" ที่หัวหน้าเคยติสไตล์ D จนต้องลดแนวต้านจาก 6 เหลือ 3
    """

    @classmethod
    def setUpClass(cls):
        cls.story = chart_indicator.build_indicators(REAL_ROWS, asset="xauusd")
        cls.article = chart_indicator_writer.render_article(cls.story)

    def test_ชุดอัตราส่วนไม่มีระดับที่บทไม่เคยพูดถึง(self):
        self.assertNotIn(0.705, chart_indicator.FIB_RATIOS)
        self.assertNotIn(0.886, chart_indicator.FIB_RATIOS)

    def test_ทุกเส้นที่ภาพจะขีดต้องมีราคาปรากฏในบท(self):
        money = chart_indicator_renderer.money_for(self.story)
        for level in self.story["fib"]["levels"]:
            self.assertIn(money(level["price"]), self.article,
                          msg=f"Fib {level['ratio']:g}")

    def test_ด่านตกเมื่อ_artifact_มีเส้นที่บทไม่ได้พูดถึง(self):
        broken = json.loads(json.dumps(self.story))
        broken["fib"]["levels"].append(
            {"ratio": 0.886, "price": chart_indicator.fib_level(broken["fib"], 0.886)})

        validation = chart_indicator_writer.validate(self.article, broken)

        self.assertEqual(validation["status"], "fail")
        self.assertTrue(any(f["rule"] == "fib_level_not_in_article"
                            for f in validation["findings"]))


class โครงหัวข้อตามใบตัวอย่าง(unittest.TestCase):
    """ผู้ใช้สั่ง 2026-08-11 — ยึด `01-CC/Input/ภาษาการเขียน/สไตล์E.md`

    ล็อกทั้งชุดและลำดับ เพราะสิ่งที่เปลี่ยนคือ**โครงบท** (RSI/MACD เคยเป็นสองหัวข้อ
    ตอนนี้รวบเป็นหัวเดียว) — เทสรายหัวจะไม่จับการแยกกลับเป็นสองหัวเงียบ ๆ
    """

    @classmethod
    def setUpClass(cls):
        fib = _synthetic_fib(low=4100.0, high=4200.0)
        cls.story = {
            "asset": "xauusd", "symbol": "XAU/USD",
            "display": {"bars": 160, "fib_bars": 160,
                        "start_date": "2025-01-01", "end_date": "2026-08-07"},
            "current": {"date": "2026-08-07", "close": 4115.0},
            "atr14": 10.0, "sma50_last": 4150.0,
            "regime": {"down": True, "rule": "x", "flip_date": None},
            "rsi": {"value": 45.0, "rising": True, "zone": "bearish"},
            "macd": {"line": 1.0, "signal": 0.5, "histogram": 0.5, "bullish": True,
                     "cross_date": None, "histogram_shrinking": False},
            "fib": fib,
            "scenarios": chart_indicator._scenarios(fib, True, atr=10.0, current_price=4115.0),
            "candle_basis": candle_close.basis_for("xauusd", "2026-08-07"),
        }
        cls.article = chart_indicator_writer.render_article(cls.story)

    def test_สี่หัวข้อเรียงตามโครงที่ผู้ใช้เลือก(self):
        heads = [line.strip() for line in self.article.splitlines()
                 if line.startswith("## ")]
        self.assertEqual(heads, [
            f"## 1. {chart_indicator_writer.H2_STRUCTURE}",
            f"## 2. {chart_indicator_writer.H2_INDICATORS}",
            f"## 3. {chart_indicator_writer.H2_SCENARIOS}",
            f"## 4. {chart_indicator_writer.H2_SUMMARY}",
        ])

    def test_เลขลำดับต่อเนื่องและ_RSI_MACD_Fibonacci_อยู่หัวข้อเดียวกัน(self):
        ordinals = [int(m.group(1)) for m in re.finditer(r"(?m)^## (\d+)\. ", self.article)]
        self.assertEqual(ordinals, [1, 2, 3, 4])
        # ชื่อเครื่องมือต้องไม่หายไปกับหัวข้อที่ถูกรวบ — ย้ายไปอยู่ต้น bullet แทน
        self.assertIn("- RSI (14)", self.article)
        self.assertIn("- MACD (12, 26, 9)", self.article)
        self.assertIn(chart_indicator_writer.FIB_BLOCK, self.article)
        self.assertEqual(self.article.count("## 2. "), 1)

    def test_หัวข้อย่อยของแผนตรงใบตัวอย่าง(self):
        subheads = [line.strip() for line in self.article.splitlines()
                    if line.startswith("### ")]
        self.assertEqual(subheads, [
            "### แผน A: ฝั่ง SELL (Follow Trend — เทรดตามแนวโน้มใหญ่)",
        ])

    def test_บทยังผ่านด่านของตัวเอง(self):
        result = chart_indicator_writer.validate(self.article, self.story)
        self.assertEqual(result["status"], "pass", msg=str(result["findings"]))


if __name__ == "__main__":
    unittest.main()
