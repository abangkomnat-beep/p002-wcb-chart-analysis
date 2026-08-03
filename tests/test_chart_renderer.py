"""เทสกราฟรุ่นใหม่ — ป้ายไม่ทับ แท่งก่อตัวต่างจากแท่งปิด และไม่วาดสิ่งที่ข้อมูลไม่รองรับ"""

import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import article_builder, chart_renderer, integrity  # noqa: E402
from tools import levels as level_engine, voice_rules  # noqa: E402


class ThaiTimeTests(unittest.TestCase):
    def test_iso_becomes_readable_thai_time(self):
        text = chart_renderer.thai_datetime_text("2026-08-03T06:33:53.081296+00:00")

        self.assertEqual(text, "3 ส.ค. 2026 13:33 น. เวลาไทย")
        self.assertNotIn("T", text)
        self.assertNotIn("+00:00", text)

    def test_bad_input_is_returned_untouched(self):
        self.assertEqual(chart_renderer.thai_datetime_text("ไม่ใช่เวลา"), "ไม่ใช่เวลา")


class LabelPlacementTests(unittest.TestCase):
    def test_labels_are_pushed_apart(self):
        entries = [
            {"y": 100.0, "priority": 0},
            {"y": 100.2, "priority": 3},
            {"y": 100.3, "priority": 5},
        ]
        placed = chart_renderer.place_labels(entries, minimum_gap=1.0)
        positions = sorted(item["label_y"] for item in placed)

        for first, second in zip(positions, positions[1:]):
            self.assertGreaterEqual(second - first, 1.0 - 1e-9)

    def test_highest_priority_keeps_its_true_position(self):
        entries = [
            {"y": 100.0, "priority": 5},
            {"y": 100.1, "priority": 0},
        ]
        placed = chart_renderer.place_labels(entries, minimum_gap=1.0)
        top = next(item for item in placed if item["priority"] == 0)

        self.assertAlmostEqual(top["label_y"], 100.1)


class RollingMeanTests(unittest.TestCase):
    def test_early_bars_stay_empty_instead_of_flat(self):
        candles = [{"close": float(value)} for value in range(10)]
        series = chart_renderer.rolling_mean_series(candles, 5)

        self.assertEqual(series[:4], [None, None, None, None])
        self.assertAlmostEqual(series[4], 2.0)
        self.assertNotIn(0.0, [value for value in series if value is not None])


class IndicatorPublicNameTests(unittest.TestCase):
    def test_moving_averages_become_thai_day_lines(self):
        self.assertEqual(chart_renderer.indicator_public_name("sma20"), "เส้นค่าเฉลี่ย 20 วัน")
        self.assertEqual(chart_renderer.indicator_public_name("SMA50"), "เส้นค่าเฉลี่ย 50 วัน")
        self.assertEqual(chart_renderer.indicator_public_name("ema200"), "เส้นค่าเฉลี่ย 200 วัน")

    def test_rsi_is_allowed_as_is_and_unknown_codes_pass_through(self):
        self.assertEqual(chart_renderer.indicator_public_name("rsi14"), "RSI")
        # โค้ดที่ไม่รู้จักคงชื่อเดิม — เทส hygiene ของ batch จะเป็นคนจับถ้าเป็นคำต้องห้าม
        self.assertEqual(chart_renderer.indicator_public_name("obv"), "obv")


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows = json.loads((FIXTURES / "xau_valid_120_sessions.json").read_text(encoding="utf-8"))["rows"]
        cls.report = integrity.assess(rows, "xauusd", calculated_at="2026-08-03T06:33:53Z")
        cls.level_map = level_engine.build_level_map(cls.report)
        # เทสวาดด้วยของแบบเดียวกับสายท่อจริง: ระดับผ่านชั้นแปลงภาษาคนก่อนเสมอ
        cls.public_levels, _ = article_builder.public_level_views(
            cls.level_map["zones"], float(cls.report["candles"][-1]["close"]))

    def _render(self, **overrides):
        directory = Path(self.tmp.name)
        options = {
            "candles": self.report["candles"],
            "output_path": directory / "chart.png",
            "symbol": "XAU/USD",
            "cutoff_at": "2026-08-03T06:33:53Z",
            "levels": self.public_levels,
            "indicator_series": {
                "sma20": chart_renderer.rolling_mean_series(self.report["candles"], 20),
                "sma50": chart_renderer.rolling_mean_series(self.report["candles"], 50),
            },
            "price_text": lambda value: voice_rules.format_price(value, "spot_metal"),
        }
        options.update(overrides)
        return chart_renderer.render_daily_chart(**options)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_chart_and_metadata_are_written(self):
        metadata = self._render()
        image_path = Path(metadata["absolute_path"])

        self.assertEqual(metadata["static_path"], "chart.png")  # ชื่อไฟล์เท่านั้น ไม่ใช่พาธในเครื่อง
        self.assertTrue(image_path.is_file())
        self.assertGreater(image_path.stat().st_size, 10_000)
        self.assertTrue(Path(metadata["metadata_path"]).is_file())

    def test_display_is_capped_at_ninety_bars(self):
        metadata = self._render()

        self.assertEqual(metadata["displayed_bars"], chart_renderer.DISPLAY_BARS)

    def test_caption_uses_human_time_not_iso(self):
        metadata = self._render()

        self.assertIn("เวลาไทย", metadata["public_caption"])
        self.assertNotIn("T06:33:53", metadata["public_caption"])
        self.assertNotIn("locked_snapshot", metadata["public_caption"])

    def test_forming_candle_is_reported_in_human_words(self):
        metadata = self._render()

        self.assertEqual(metadata["candle_state"], "forming")
        # "กำลังก่อตัว" เป็นคำ denylist — บนภาพต้องพูดว่า "ยังไม่ปิด"
        self.assertIn("แท่งล่าสุดยังไม่ปิด", metadata["public_caption"])
        self.assertNotIn("กำลังก่อตัว", metadata["public_caption"])

    def test_label_count_is_capped(self):
        metadata = self._render()

        self.assertLessEqual(len(metadata["labels_shown"]), chart_renderer.MAX_VISIBLE_LABELS)
        self.assertTrue(any("ล่าสุด" in label for label in metadata["labels_shown"]))

    def test_hidden_indicators_are_explained_in_the_caption(self):
        metadata = self._render(
            indicator_series={},
            hidden_indicators=[{"indicator": "sma50", "required_bars": 50, "visible_bars": 5}],
        )

        self.assertIn("เส้นค่าเฉลี่ย 50 วัน", metadata["public_caption"])
        self.assertIn("ไม่แสดง", metadata["public_caption"])
        self.assertNotIn("SMA50", metadata["public_caption"])
        self.assertEqual(metadata["plotted_indicators"], [])
        # โค้ดดิบยังอยู่ใน key ภายใน สำหรับ level-map.json ฝั่ง internal
        self.assertEqual(metadata["hidden_indicator_codes"][0]["indicator"], "sma50")

    def test_alt_text_describes_content_not_just_the_symbol(self):
        metadata = self._render()

        self.assertIn("XAU/USD", metadata["alt_text"])
        self.assertGreater(len(metadata["alt_text"]), 60)

    def test_labels_and_prices_follow_article_rounding(self):
        """เลขทุกป้ายบนภาพต้องปัดกติกาเดียวกับบทความ — spot_metal คือจำนวนเต็ม+comma"""
        metadata = self._render()

        for label in metadata["labels_shown"]:
            with self.subTest(label=label):
                self.assertNotRegex(label, r"\d+\.\d",
                                    "ป้าย spot_metal ห้ามมีทศนิยม — ต้องปัดแบบบทความ")

    def test_public_chart_metadata_file_is_free_of_robot_words(self):
        """ทุกข้อความในไฟล์ .chart.json ฝั่ง public ต้องไม่มีคำ denylist ของ Voice Spec"""
        metadata = self._render()
        written = Path(metadata["metadata_path"]).read_text(encoding="utf-8").lower()

        for term in voice_rules.VOICE_DENYLIST:
            with self.subTest(term=term):
                self.assertNotIn(term, written)
        # key ภายในต้องไม่ถูกเขียนลงไฟล์สาธารณะ
        payload = json.loads(Path(metadata["metadata_path"]).read_text(encoding="utf-8"))
        for key in chart_renderer.PRIVATE_METADATA_KEYS:
            with self.subTest(key=key):
                self.assertNotIn(key, payload)

    def test_level_labels_are_role_based_human_words(self):
        metadata = self._render()
        level_labels = [label for label in metadata["labels_shown"]
                        if not label.startswith("ล่าสุด")]

        self.assertTrue(level_labels)
        allowed_starts = ("แนวรับ", "แนวต้าน", "จุดสูงสุดเดิม", "จุดต่ำสุดเดิม",
                          "เส้นค่าเฉลี่ย", "กรอบแกว่งรายวัน")
        for label in level_labels:
            with self.subTest(label=label):
                self.assertTrue(label.startswith(allowed_starts),
                                f"ป้ายไม่ใช่ภาษาคนตามบทบาท: {label}")


if __name__ == "__main__":
    unittest.main()
