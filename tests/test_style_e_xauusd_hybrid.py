"""Contract tests for Style E XAUUSD H1 Fibonacci Hybrid revision 3.

ชุดนี้เป็น reconstructed RED evidence เมื่อรันบน parent 3dbdf1f: ไฟล์ test
ถูก materialize ก่อน implementation และผลล้มเหลวที่ helper/contract ที่ยังไม่มี
ไม่ใช่หลักฐานร่วมสมัยก่อน candidate 8f9557b.
"""

from __future__ import annotations

import copy
import re
import unittest
from datetime import datetime, timezone

from tools import chart_indicator_writer, intraday_bars


def _fib(direction: str = "up") -> dict:
    """Frozen XAUUSD revision-3 Fibonacci values from the accepted preview."""
    return {
        "direction": direction,
        "swing_high": {"date": "2026-08-25", "price": 4_695.94},
        "swing_low": {"date": "2026-08-19", "price": 4_325.97},
        "levels": [
            {"ratio": 0.0, "price": 4_325.97},
            {"ratio": 0.236, "price": 4_608.63},
            {"ratio": 0.382, "price": 4_554.61},
            {"ratio": 0.5, "price": 4_510.96},
            {"ratio": 0.618, "price": 4_467.30},
            {"ratio": 0.786, "price": 4_405.15},
            {"ratio": 1.0, "price": 4_695.94},
        ],
        "golden": [4_405.15, 4_467.30],
        "extension": 4_796.57,
    }


def _story(close: float, *, asset: str = "xauusd", timeframe: str = "1h",
           direction: str = "up") -> dict:
    return {
        "asset": asset,
        "symbol": "XAU/USD" if asset == "xauusd" else "USD/JPY",
        "timeframe": timeframe,
        "current": {"close": close, "date": "2026-08-26",
                     "at": "2026-08-26 10:00:00"},
        "fib": _fib(direction),
    }


def _full_story(close: float = 4_638.16) -> dict:
    story = _story(close)
    fib = story["fib"]
    story.update({
        "display": {"bars": 160, "fib_bars": 120,
                    "start_date": "2026-08-19", "end_date": "2026-08-26"},
        "regime": {"down": False, "flip_date": None},
        "atr14": 40.0,
        "sma50_last": 4_600.0,
        "rsi": {"value": 47.2, "rising": False, "zone": "bearish"},
        "macd": {"line": 1.0, "signal": 0.5, "histogram": 0.5,
                 "bullish": True, "cross_date": None,
                 "histogram_shrinking": True},
        "scenarios": {"primary": {
            "side": "buy", "name": "ขาขึ้น", "daily_entry": False,
            "active": False, "entry_low": 4_405.15, "entry_high": 4_467.30,
            "entry_mid": 4_436.225, "sl": 4_317.49,
            "tps": [4_608.63, 4_695.94, 4_796.57],
        }, "counter": None},
        "candle_basis": intraday_bars.basis_for(
            "xauusd", "2026-08-26 10:00:00", timeframe="1h",
            now=datetime(2026, 8, 27, tzinfo=timezone.utc)),
    })
    return story


class HybridActivationTests(unittest.TestCase):
    def test_hybrid_requires_xauusd_h1_and_fib(self):
        self.assertTrue(chart_indicator_writer._is_xauusd_h1_hybrid(_story(4_638.16)))
        for story in (
            _story(4_638.16, asset="usdjpy"),
            _story(4_638.16, timeframe="1day"),
            {"asset": "xauusd", "timeframe": "1h"},
            {"asset": "xauusd", "timeframe": "1H", "fib": _fib()},
            {"asset": "xauusd", "timeframe": "1h", "fib": None},
        ):
            self.assertFalse(chart_indicator_writer._is_xauusd_h1_hybrid(story))

    def test_legacy_xauusd_and_usdjpy_paths_remain_non_hybrid(self):
        for story in (_story(4_638.16, timeframe="1day"),
                      _story(4_638.16, asset="usdjpy")):
            text = "\n".join(chart_indicator_writer._fib_lines(story))
            price = chart_indicator_writer.money_for(story)(4_608.63)
            self.assertIn(f"- **0.236** — {price} ดอลลาร์", text)
            self.assertNotIn("**ระดับอ้างอิง:**", text)

    def test_xauusd_h1_without_fib_keeps_legacy_no_fib_message(self):
        story = _story(4_638.16)
        story["fib"] = None
        self.assertEqual(
            chart_indicator_writer._fib_lines(story),
            ["รอบนี้ระบบไม่พบ swing ที่กว้างพอผ่านเกณฑ์ (อย่างน้อย 2 เท่าของ ATR) "
             "จึงไม่วาง Fibonacci และจะไม่ตั้งระดับขึ้นเองจากความรู้สึกแทนครับ"],
        )


class HybridRevision3SnapshotTests(unittest.TestCase):
    EXPECTED_BLOCK = (
        "**ระดับ Fibonacci Retracement**\n\n"
        "&emsp;กราฟ H1 วัดคลื่นขาขึ้นจาก 4,325.97 ดอลลาร์ (19 ส.ค. 2026) ถึง "
        "4,695.94 ดอลลาร์ (25 ส.ค. 2026)\n\n"
        "**ระดับอ้างอิง:**\n\n"
        "- **แนวรับย่อตัว:** `0.236` 4,608.63 · `0.382` 4,554.61 · `0.5` 4,510.96\n"
        "- **โซนหลัก/เป้าหมาย:** `Golden Zone` 4,405.15–4,467.30 · `1.272` 4,796.57\n\n"
        "**จุดที่ต้องจับตาวันนี้:** ราคาปิด **4,638.16** ดอลลาร์ อยู่เหนือแนวรับ "
        "**0.236 (4,608.63)** ซึ่งเป็นระดับใกล้สุด ส่วนแนวรับถัดไปคือ "
        "**0.382 (4,554.61)**"
    )

    def test_accepted_revision3_copy_is_exact_and_image_precedes_it(self):
        article = chart_indicator_writer.render_article(_full_story())
        start = article.index(chart_indicator_writer.FIB_BLOCK)
        image = (f"![{chart_indicator_writer.fibonacci_alt(_full_story())}]"
                 f"({chart_indicator_writer.fibonacci_image_name('xauusd', '2026-08-26')})")
        self.assertEqual(
            article[start:start + len(chart_indicator_writer.FIB_BLOCK) + 2 + len(image)],
            chart_indicator_writer.FIB_BLOCK + "\n\n" + image)
        copy_start = article.index("\n\n", start + len(chart_indicator_writer.FIB_BLOCK)) + 2
        copy_start = article.index("\n\n", copy_start) + 2
        end = article.index("\n\n---\n\n## ", copy_start)
        block = chart_indicator_writer.FIB_BLOCK + "\n\n" + article[copy_start:end]
        self.assertEqual(block, self.EXPECTED_BLOCK)
        self.assertEqual(len(block), 455)

    def test_hybrid_block_has_no_trade_commands_and_mobile_shape(self):
        text = "\n".join(chart_indicator_writer._fib_lines(_story(4_638.16)))
        self.assertNotRegex(text, r"(?i)BUY|SELL|Entry|SL|TP|เงื่อนไข")
        self.assertNotIn("|", text)
        self.assertEqual(text.count("·"), 3)
        bullets = [line for line in text.splitlines() if line.startswith("-")]
        self.assertEqual(len(bullets), 2)
        self.assertTrue(all(len(line) <= 80 for line in bullets))

    def test_down_direction_uses_resistance_wording_without_changing_numbers(self):
        text = "\n".join(chart_indicator_writer._fib_lines(
            _story(4_638.16, direction="down")))
        self.assertIn("วัดจากจุดสูงสุดเดิมที่ 4,695.94 ดอลลาร์ (25 ส.ค. 2026) ลงมาถึงจุดต่ำสุดเดิมที่ 4,325.97 ดอลลาร์ (19 ส.ค. 2026)", text)
        self.assertIn("แนวต้านรีบาวด์", text)
        self.assertIn("4,608.63", text)


class HybridCandidateSelectionTests(unittest.TestCase):
    def assert_labels(self, close, expected):
        labels = [x["label"] for x in chart_indicator_writer._pick_fib_watch_candidates(
            _story(close))]
        self.assertEqual(labels, expected)

    def test_position_matrix_exact_and_between_cases(self):
        cases = [
            (5_000.0, ["1.272", "0.236"]),
            (4_796.57, ["1.272"]),
            (4_700.0, ["0.236", "1.272"]),
            (4_608.63, ["0.236"]),
            (4_581.62, ["0.236", "0.382"]),
            (4_554.61, ["0.382"]),
            (4_532.0, ["0.5", "0.382"]),
            (4_510.96, ["0.5"]),
            (4_480.0, ["Golden Zone", "0.5"]),
            (4_467.30, ["Golden Zone"]),
            (4_438.16, ["Golden Zone"]),
            (4_405.15, ["Golden Zone"]),
            (4_300.0, ["Golden Zone", "0.5"]),
        ]
        for close, expected in cases:
            with self.subTest(close=close):
                self.assert_labels(close, expected)

    def test_relation_wording_matches_position_and_exact_hits_are_single(self):
        def text(close):
            return "\n".join(chart_indicator_writer._fib_lines(_story(close)))

        self.assertIn("อยู่เหนือเป้าหมายอ้างอิง", text(5_000.0))
        self.assertIn("อยู่ระหว่าง **0.382 (4,554.61)** กับ **0.236 (4,608.63)**",
                      text(4_581.62))
        self.assertIn("อยู่ใน **Golden Zone (4,405.15–4,467.30)**", text(4_438.16))
        self.assertIn("อยู่ที่แนวรับ **0.236 (4,608.63)**", text(4_608.63))

    def test_tie_break_and_registry_input_order_are_deterministic(self):
        story = _story(4_581.62)
        first = chart_indicator_writer._pick_fib_watch_candidates(story)
        reordered = copy.deepcopy(story)
        reordered["fib"]["levels"] = list(reversed(reordered["fib"]["levels"]))
        second = chart_indicator_writer._pick_fib_watch_candidates(reordered)
        self.assertEqual([x["label"] for x in first], ["0.236", "0.382"])
        self.assertEqual([x["label"] for x in first], [x["label"] for x in second])

    def test_float_noise_equal_after_display_normalization_uses_at_relation(self):
        text = "\n".join(chart_indicator_writer._fib_lines(_story(4_608.634)))
        self.assertIn("อยู่ที่แนวรับ **0.236 (4,608.63)**", text)
        self.assertNotIn("อยู่เหนือแนวรับ", text)


class HybridValidatorMutationTests(unittest.TestCase):
    def test_positive_render_validates(self):
        story = _full_story()
        article = chart_indicator_writer.render_article(story)
        self.assertEqual(chart_indicator_writer.validate(article, story)["status"], "pass")

    def test_missing_fib_price_is_rejected_by_validator(self):
        story = _full_story()
        article = chart_indicator_writer.render_article(story)
        broken = article.replace("4,510.96", "4,510.95", 1)
        result = chart_indicator_writer.validate(broken, story)
        self.assertTrue(any(f["rule"] == "fib_level_not_in_article"
                            for f in result["findings"]))

    def test_number_outside_story_is_rejected_by_validator(self):
        story = _full_story()
        article = chart_indicator_writer.render_article(story)
        result = chart_indicator_writer.validate(article + "\nข้อมูล 9,999.99", story)
        self.assertTrue(any(f["rule"] == "number_not_in_story"
                            for f in result["findings"]))


if __name__ == "__main__":
    unittest.main()
