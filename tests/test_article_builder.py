"""เทสตัวประกอบบทความโครงเล่าเรื่อง 4 ช่วง (Voice v1 + ส่วนขยาย v1.1) และสายท่อรวม

บทความที่ generate ต้อง: ตรงโครง spec ทุกช่วง · ผ่านด่านของตัวเองแบบ fatal 0 ·
ไม่มีคำ denylist · เลขชุดเดียวกันทุกตำแหน่ง · ยาว 350-560 คำ · ไม่ลอก corpus ·
ไม่มีหมายเหตุ/disclaimer ในฝั่ง public · ทุกค่าที่ย่อหน้าขยายเล่ามาจาก `context` ใน evidence
"""

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import article_builder, build_daily_package, chart_renderer, integrity  # noqa: E402
from tools import levels as level_engine, license_gate, public_copy_validator  # noqa: E402
from tools import voice_rules  # noqa: E402


CUTOFF = "2026-08-03T07:00:00+00:00"
CORPUS_PATH = (REPO_ROOT.parents[2]
               / "03-RR" / "Input" / "2026-08-03_corpus-ตัวอย่างบทวิเคราะห์-4ชิ้น.md")


def build_sample(tmp: Path) -> tuple[dict, str]:
    rows = json.loads((FIXTURES / "xau_valid_120_sessions.json").read_text(encoding="utf-8"))["rows"]
    report = integrity.assess(rows, "xauusd", calculated_at=CUTOFF)
    level_map = level_engine.build_level_map(report)
    # เหมือนสายท่อจริง: ระดับผ่านชั้นแปลงภาษาคนก่อนเข้ากราฟ + เลขบนภาพปัดแบบบทความ
    chart_levels, _ = article_builder.public_level_views(
        level_map["zones"], float(report["candles"][-1]["close"]))
    chart_metadata = chart_renderer.render_daily_chart(
        candles=report["candles"], output_path=tmp / "chart-daily.png",
        symbol="XAU/USD", cutoff_at=CUTOFF, levels=chart_levels,
        indicator_series={"sma20": chart_renderer.rolling_mean_series(report["candles"], 20)},
        decimals=2,
        price_text=lambda value: voice_rules.format_price(value, "spot_metal"),
    )
    data = article_builder.build_article_data(
        report=report, level_map=level_map, chart_metadata=chart_metadata,
        license_result=license_gate.evaluate("xauusd"), symbol="XAU/USD",
        instrument_type="spot_metal", unit="ดอลลาร์ต่อออนซ์", decimals=2,
        cutoff_at=CUTOFF, batch_id="2026-08-03T07-00Z-daily-market",
    )
    return data, article_builder.render_markdown(data)


class VoiceStructureTests(unittest.TestCase):
    """โครง 4 ช่วงต้องมาครบและเรียงตามลำดับตายตัวของ spec"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data, cls.markdown = build_sample(Path(cls.tmp.name))
        cls.body = cls.markdown.split("---", 2)[2]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_four_parts_appear_in_locked_order(self):
        markers = (
            f"# {self.data['headline']}",              # หัวเรื่อง
            "*ข้อมูล ณ ",                               # บรรทัดเวลา
            "วันนี้ ( ",                                 # ช่วง ① สูตรเปิดเรื่อง
            voice_rules.TECHNICAL_HEADING,              # ช่วง ③
            f"{self.data['instrument']['block_label']}:",  # ช่วง ④
            "แนวรับ ",
            "แนวต้าน ",                                  # v1.1: บล็อกจบตรงนี้ ไม่มีหมายเหตุ
            "![",                                       # กราฟอยู่ท้ายสุด
        )
        # เดินหาแบบต่อเนื่อง: marker แต่ละตัวต้องอยู่ "หลัง" ตัวก่อนหน้าในเนื้อบทความ
        # (ค้นเฉพาะ body เพราะบางคำ เช่น แนวต้าน โผล่ใน frontmatter title ได้)
        cursor = 0
        for marker in markers:
            with self.subTest(marker=marker):
                position = self.body.find(marker, cursor)
                self.assertGreaterEqual(position, 0,
                                        f"ไม่พบ {marker!r} หลังตำแหน่ง {cursor}")
                cursor = position

    def test_no_subheadings_no_tables_no_bullets(self):
        for line in self.body.splitlines():
            stripped = line.strip()
            with self.subTest(line=stripped[:40]):
                self.assertFalse(stripped.startswith("##"))
                self.assertNotIn("|", stripped)
                self.assertFalse(stripped.startswith("- "))

    def test_phase1_has_no_news_section_and_no_excuses(self):
        # ช่วง ② ต้องถูกตัดเงียบ: จบช่วง ① แล้วเข้าหัวข้อเทคนิคทันที
        for forbidden in ("ยังไม่มีข่าว", "ไม่มีปฏิทิน", "ไม่ระบุสาเหตุ", "จับตาเหตุการณ์"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.markdown)

    def test_no_denylist_or_system_words_in_body(self):
        lowered = self.body.lower()
        for term in voice_rules.VOICE_DENYLIST:
            with self.subTest(term=term):
                self.assertNotIn(term, lowered)

    def test_headline_has_no_code_words_and_reasonable_length(self):
        headline = self.data["headline"]
        for word in ("Pivot", "R1", "SMA", "session", "จุดตัดสิน"):
            self.assertNotIn(word.lower(), headline.lower())
        self.assertLessEqual(voice_rules.count_public_words(headline), 12)

    def test_time_line_is_thai_not_iso(self):
        self.assertIn("(เวลาไทย)", self.markdown)
        self.assertIn("เวลา 14:00 น.", self.markdown)  # 07:00Z = 14:00 เวลาไทย
        self.assertNotIn("T07:00:00", self.body)

    def test_note_and_disclaimer_are_gone_from_the_public_article(self):
        """V1 ของ v1.1: ผู้ใช้สั่งตัดหมายเหตุและ disclaimer ออกจากบทความสาธารณะ"""
        self.assertNotIn("หมายเหตุ", self.markdown)
        self.assertNotIn(voice_rules.NOTE_FORMING, self.markdown)
        self.assertNotIn(voice_rules.NOTE_CLOSED, self.markdown)
        self.assertNotIn(voice_rules.DISCLAIMER, self.markdown)
        self.assertNotIn("note", self.data["sr_block"])

    def test_block_ends_at_the_resistance_line_then_chart(self):
        """บล็อกช่วง ④ จบที่บรรทัดแนวต้าน แล้วต่อด้วยกราฟทันที"""
        lines = [line for line in self.body.splitlines() if line.strip()]
        block_index = lines.index(f"{self.data['instrument']['block_label']}:")
        after_block = lines[block_index + 1:]
        self.assertTrue(after_block[0].startswith("แนวรับ "))
        self.assertTrue(after_block[1].startswith("แนวต้าน "))
        self.assertTrue(after_block[2].startswith("!["))

    def test_note_and_disclaimer_stay_available_for_internal_audit(self):
        forming = article_builder.internal_note_lines("forming")
        closed = article_builder.internal_note_lines("closed")
        self.assertEqual(forming["note"], voice_rules.NOTE_FORMING)
        self.assertEqual(closed["note"], voice_rules.NOTE_CLOSED)
        self.assertEqual(forming["disclaimer"], voice_rules.DISCLAIMER)

    def test_chart_is_present_with_human_caption(self):
        self.assertIn("](chart-daily.png)", self.markdown)
        caption_lines = [line for line in self.body.splitlines()
                        if line.startswith("*กราฟ")]
        self.assertEqual(len(caption_lines), 1)

    def test_polished_phrases_from_tester_round(self):
        """รอบเก็บงานขั้น 7: ประโยคที่ Tester ชี้ต้องไม่กลับมาอีก"""
        self.assertNotIn("ของเครื่องมือ", self.markdown)      # ภาษาอธิบายระบบ
        self.assertNotIn("ทะลุขึ้นยืนเหนือ", self.markdown)     # ค2: "ทะลุขึ้นเหนือ...ได้อย่างชัดเจน"
        self.assertNotIn("ได้ชัดเจน ", self.markdown)
        self.assertNotIn("กรอบแคบ", self.markdown)            # ก8 คือ "แกว่งตัวในกรอบ" เฉย ๆ
        if "RSI" in self.markdown:
            self.assertIn("โซนกลาง", self.markdown)

    def test_caption_with_two_average_lines_avoids_double_lae(self):
        """caption สองเส้น: "20 กับ 50 วัน" — ไม่ใช่ "และ...และ..." ซ้อนกัน"""
        data = json.loads(json.dumps(self.data))
        data["visuals"]["average_line_days"] = [20, 50]
        markdown = article_builder.render_markdown(data)
        self.assertIn("เส้นค่าเฉลี่ย 20 กับ 50 วัน", markdown)
        self.assertNotIn("20 วัน และ 50 วัน", markdown)


class EvidenceDisciplineTests(unittest.TestCase):
    """ตัวเลขและถ้อยคำทุกจุดต้องมี evidence รองรับ และผ่านด่านของตัวเอง"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data, cls.markdown = build_sample(Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_article_passes_its_own_validator_with_zero_fatal(self):
        result = public_copy_validator.validate(
            self.markdown, evidence=self.data, instrument_type="spot_metal"
        )
        self.assertEqual(result["status"], "pass", result["findings"])
        self.assertEqual(result["fatal_count"], 0)

    def test_word_count_is_inside_spec_range(self):
        words = voice_rules.count_public_words(self.markdown)
        self.assertGreaterEqual(words, voice_rules.WORD_MIN, "สั้นเกิน = ตัดเนื้อจนโหว่")
        self.assertLessEqual(words, voice_rules.WORD_MAX)

    def test_headline_level_matches_block_value_exactly(self):
        # ค่าเดียวต่อค่าดิบ: เลขในหัวเรื่องต้องเป็นเลขเดียวกับบล็อกช่วง ④
        resistances = self.data["sr_block"]["resistances"]
        self.assertTrue(resistances)
        self.assertIn(resistances[0]["text"], self.data["headline"])
        self.assertIn(f"แนวต้าน {' / '.join(item['text'] for item in resistances)}",
                      self.markdown)

    def test_block_levels_are_rounded_from_their_raw_values(self):
        for side in ("supports", "resistances"):
            for item in self.data["sr_block"][side]:
                with self.subTest(side=side, level=item["level_id"]):
                    self.assertEqual(
                        item["text"],
                        voice_rules.format_price(item["raw"], "spot_metal"),
                    )

    def test_block_sides_are_ordered_near_to_far_and_unique(self):
        price = self.data["snapshot"]["price"]
        supports = [item["raw"] for item in self.data["sr_block"]["supports"]]
        resistances = [item["raw"] for item in self.data["sr_block"]["resistances"]]
        self.assertEqual(supports, sorted(supports, reverse=True))
        self.assertEqual(resistances, sorted(resistances))
        self.assertTrue(all(value < price for value in supports))
        self.assertTrue(all(value > price for value in resistances))
        texts = [item["text"] for item in self.data["sr_block"]["supports"]]
        self.assertEqual(len(texts), len(set(texts)), "ปัดแล้วชนกันต้องข้ามไประดับถัดไป")

    def test_sr_block_references_public_level_codes(self):
        """level_id ฝั่ง public เป็นรหัสกลาง — id ภายใน (zone_pivot_...) มีศัพท์ระบบฝังอยู่"""
        for side in ("supports", "resistances"):
            for item in self.data["sr_block"][side]:
                with self.subTest(side=side, level=item["level_id"]):
                    self.assertRegex(item["level_id"], r"^level-\d{2}$")

    def test_public_payload_has_no_internal_visual_keys(self):
        for key in ("metadata_path", "absolute_path", "plotted_indicator_codes",
                    "hidden_indicator_codes"):
            with self.subTest(key=key):
                self.assertNotIn(key, self.data["visuals"])
        self.assertNotIn("session_timezone", self.data["instrument"])

    def test_no_causal_claim_without_verified_news(self):
        self.assertFalse(self.data["drivers"]["causal_claims_allowed"])
        for word in ("เพราะดอลลาร์", "จากแรงหนุน", "ตอบรับข่าว", "หลังตัวเลข"):
            self.assertNotIn(word, self.markdown)

    def test_direction_words_match_change_sign(self):
        move = self.data["move"]
        if move["direction"] == "up":
            self.assertNotIn("ลดลงราว", self.markdown)
            self.assertNotIn("เผชิญแรงเทขาย", self.markdown)
        elif move["direction"] == "down":
            self.assertNotIn("เพิ่มขึ้นราว", self.markdown)
            self.assertNotIn("แรงซื้อเพิ่มเติมหนุนราคา", self.markdown)

    def test_buy_sell_phrase_obeys_evidence_conditions(self):
        # จ1/จ3: จะพูดว่าแรงขายได้เปรียบ/แรงซื้ออ่อนแรง ได้ต่อเมื่อเงื่อนไข evidence จริง
        price = self.data["snapshot"]["price"]
        sma20 = self.data["technical"]["ma20"]
        rsi = self.data["technical"]["rsi14"]
        if "แรงขายยังได้เปรียบ" in self.markdown:
            self.assertTrue((rsi is not None and rsi < 50) or (sma20 and price < sma20))
        if "แรงซื้อยังได้เปรียบ" in self.markdown:
            self.assertTrue(rsi is None or rsi >= 50)

    def test_two_way_condition_present(self):
        self.assertIn("หาก", self.markdown)
        self.assertIn("ในทางกลับกัน", self.markdown)

    def test_intentional_denylist_word_makes_validator_fail(self):
        dirty = self.markdown.replace(
            voice_rules.TECHNICAL_HEADING,
            voice_rules.TECHNICAL_HEADING + "\n\nฉากทัศน์ทางขึ้นยังเปิดอยู่", 1)
        result = public_copy_validator.validate(
            dirty, evidence=self.data, instrument_type="spot_metal")
        self.assertEqual(result["status"], "fail")
        self.assertIn("voice_denylist", {item["rule"] for item in result["findings"]})

    def test_article_does_not_copy_corpus_ten_word_runs(self):
        if not CORPUS_PATH.is_file():
            self.skipTest("ไม่มีไฟล์ corpus ในเครื่องนี้")
        corpus = CORPUS_PATH.read_text(encoding="utf-8")
        overlap = voice_rules.find_corpus_overlap(self.markdown, corpus)
        self.assertIsNone(overlap, f"ข้อความซ้ำ corpus เกินเกณฑ์: {overlap!r}")


def make_candles(rows: list[dict], start: str = "2026-07-01") -> list[dict]:
    """แท่งสังเคราะห์สำหรับเทสหน่วยของชั้นหลักฐาน — ปิดรอบแล้วและอยู่ในปฏิทินทุกแท่ง"""
    from datetime import date, timedelta

    first = date.fromisoformat(start)
    candles = []
    for index, row in enumerate(rows):
        close = float(row["close"])
        candles.append({
            "session_date": (first + timedelta(days=index)).isoformat(),
            "open": float(row.get("open", close)),
            "high": float(row.get("high", close)),
            "low": float(row.get("low", close)),
            "close": close,
            "candle_state": "closed",
            "is_expected_session": True,
        })
    return candles


class ContextEvidenceUnitTests(unittest.TestCase):
    """ชั้นหลักฐานเชิงบริบทของ v1.1 — คำนวณที่นี่ที่เดียว บทความแค่หยิบไปเล่า"""

    def test_streak_counts_consecutive_closes_in_one_direction(self):
        candles = make_candles([{"close": value} for value in (10, 9, 8, 7)])
        streak = article_builder.close_streak(candles)
        self.assertEqual((streak["direction"], streak["days"]), ("down", 3))
        self.assertEqual(streak["last_date"], candles[-1]["session_date"])

    def test_streak_stops_at_the_first_turn(self):
        candles = make_candles([{"close": value} for value in (10, 9, 8, 9, 10)])
        streak = article_builder.close_streak(candles)
        self.assertEqual((streak["direction"], streak["days"]), ("up", 2))

    def test_streak_is_none_when_price_is_unchanged(self):
        candles = make_candles([{"close": value} for value in (10, 10)])
        self.assertIsNone(article_builder.close_streak(candles)["days"])

    def test_range_window_reports_extremes_with_their_dates(self):
        candles = make_candles([
            {"close": 10, "high": 12, "low": 9},    # นอกหน้าต่าง 3 วัน
            {"close": 10, "high": 11, "low": 8},
            {"close": 10, "high": 10.5, "low": 9.5},
            {"close": 10, "high": 10.2, "low": 9.8},
        ])
        window = article_builder.range_window(candles, 3, price=10.0)
        self.assertEqual(window["window"], 3)
        self.assertEqual(window["high"], 11)
        self.assertEqual(window["high_date"], candles[1]["session_date"])
        self.assertEqual(window["low"], 8)
        self.assertEqual(window["low_date"], candles[1]["session_date"])
        self.assertEqual(window["price_side_high"], "below")
        self.assertEqual(window["price_side_low"], "above")
        self.assertAlmostEqual(window["percent_from_high"], (11 - 10) / 11 * 100)
        self.assertAlmostEqual(window["percent_from_low"], (10 - 8) / 8 * 100)

    def test_range_window_is_none_when_bars_are_not_enough(self):
        candles = make_candles([{"close": 10}] * 3)
        self.assertIsNone(article_builder.range_window(candles, 20, price=10.0))

    def test_moving_average_context_records_distance_structure_and_slope(self):
        candles = make_candles([{"close": value} for value in range(1, 41)])
        context = article_builder.moving_average_context(
            candles, price=40.0, ma20=30.0, ma50=None)
        entry = context["entries"]["ma20"]
        self.assertEqual(entry["period"], 20)
        self.assertEqual(entry["price_side"], "above")
        self.assertAlmostEqual(entry["distance_percent"], (40 - 30) / 30 * 100)
        self.assertEqual(entry["slope"], "up")          # ราคาไต่ขึ้นทุกวัน เส้นต้องชี้ขึ้น
        self.assertEqual(entry["slope_lookback"], article_builder.SLOPE_LOOKBACK)
        self.assertNotIn("ma50", context["entries"])    # ไม่มีค่า = ตัดเงียบ
        self.assertIsNone(context["structure"])

    def test_moving_average_structure_compares_short_against_long(self):
        candles = make_candles([{"close": 10}] * 60)
        below = article_builder.moving_average_context(candles, 10.0, ma20=9.0, ma50=9.5)
        above = article_builder.moving_average_context(candles, 10.0, ma20=9.5, ma50=9.0)
        self.assertEqual(below["structure"], "short_below_long")
        self.assertEqual(above["structure"], "short_above_long")

    def test_volatility_compares_today_range_with_the_fourteen_day_average(self):
        rows = [{"close": 100, "high": 101, "low": 100}] * 13
        wide = article_builder.volatility_context(
            make_candles(rows + [{"close": 100, "high": 105, "low": 100}]),
            latest={"high": 105, "low": 100}, price=100.0)
        self.assertEqual(wide["window"], article_builder.VOLATILITY_WINDOW)
        self.assertEqual(wide["comparison"], "wider")
        self.assertAlmostEqual(wide["today_range"], 5.0)
        self.assertAlmostEqual(wide["today_range_percent"], 5.0)

        narrow = article_builder.volatility_context(
            make_candles(rows + [{"close": 100, "high": 100.1, "low": 100}]),
            latest={"high": 100.1, "low": 100}, price=100.0)
        self.assertEqual(narrow["comparison"], "narrower")

    def test_volatility_is_none_without_enough_bars(self):
        candles = make_candles([{"close": 100, "high": 101, "low": 99}] * 5)
        self.assertIsNone(article_builder.volatility_context(
            candles, latest=candles[-1], price=100.0))

    def test_level_structure_measures_distance_and_position_in_band(self):
        block = {"supports": [{"raw": 90.0, "text": "90"}],
                 "resistances": [{"raw": 110.0, "text": "110"}]}
        middle = article_builder.level_structure(block, price=100.0)
        self.assertAlmostEqual(middle["support_distance_percent"], 10.0)
        self.assertAlmostEqual(middle["resistance_distance_percent"], 10.0)
        self.assertEqual(middle["band_position"], "middle")
        self.assertAlmostEqual(middle["band_position_percent"], 50.0)

        lower = article_builder.level_structure(block, price=92.0)
        self.assertEqual(lower["band_position"], "lower")
        upper = article_builder.level_structure(block, price=108.0)
        self.assertEqual(upper["band_position"], "upper")

    def test_level_structure_survives_a_missing_side(self):
        result = article_builder.level_structure(
            {"supports": [], "resistances": [{"raw": 110.0, "text": "110"}]}, price=100.0)
        self.assertIsNone(result["support_distance_percent"])
        self.assertIsNone(result["band_position"])


class ThresholdCalibrationTests(unittest.TestCase):
    """ล็อกเกณฑ์ตัวเลขที่ปรับเมื่อ 2026-08-04 หลังวัดข้อมูลจริง 198 วัน × 3 สินทรัพย์

    บันทึกผลวัด: 01-CC/Output/2026-08-04_ผลวัดเกณฑ์ตัวเลข-P002.md
    """

    def _closes(self, values):
        return [{"session_date": f"2026-01-{index + 1:02d}", "close": value,
                 "high": value, "low": value, "open": value}
                for index, value in enumerate(values)]

    # ---- streak: 2 วันติดไม่มีนัย ต้องถึง 3 วันจึงเล่า ----

    def test_ปิดติดกันสองวันยังไม่เล่า(self):
        """2 วันติดเกิดราว 30% ของวันตามธรรมชาติ = อัตราเดียวกับการโยนเหรียญ"""
        self.assertEqual(article_builder.STREAK_MIN_DAYS, 3)
        candles = self._closes([100, 99, 100, 101])  # ขึ้น 2 วันติด
        streak = article_builder.close_streak(candles)

        self.assertEqual(streak["days"], 2)
        self.assertLess(streak["days"], article_builder.STREAK_MIN_DAYS,
                        "2 วันต้องต่ำกว่าเกณฑ์ จึงถูกตัดเงียบ")

    def test_ปิดติดกันสามวันเล่าได้(self):
        candles = self._closes([100, 99, 100, 101, 102])  # ขึ้น 3 วันติด
        streak = article_builder.close_streak(candles)

        self.assertEqual(streak["days"], 3)
        self.assertGreaterEqual(streak["days"], article_builder.STREAK_MIN_DAYS)

    # ---- ความชันเส้นค่าเฉลี่ย: "flat" ต้องมีแถบผ่อนผัน ไม่ใช่เท่ากันเป๊ะ ----

    def test_เส้นค่าเฉลี่ยขยับน้อยมากต้องอ่านว่าแทบไม่เปลี่ยนทิศ(self):
        """ก่อนแก้ เงื่อนไข flat ต้องการค่าเท่ากันเป๊ะ วัดจริง 546 จุดไม่เจอสักครั้ง"""
        period = 20
        # ราคานิ่งแล้วขยับปลายทางนิดเดียว — เส้นค่าเฉลี่ยเปลี่ยนไม่ถึงเกณฑ์
        values = [100.0] * (period + article_builder.SLOPE_LOOKBACK)
        values[-1] = 100.5
        slope, reference = article_builder._average_line_slope(self._closes(values), period)

        self.assertEqual(slope, "flat")
        self.assertIsNotNone(reference)

    def test_เส้นค่าเฉลี่ยขยับมากพอยังอ่านทิศได้ตามเดิม(self):
        period = 20
        rising = [100.0 + index for index in range(period + article_builder.SLOPE_LOOKBACK)]
        falling = list(reversed(rising))

        self.assertEqual(article_builder._average_line_slope(self._closes(rising), period)[0], "up")
        self.assertEqual(article_builder._average_line_slope(self._closes(falling), period)[0], "down")

    def test_เกณฑ์_flat_ผูกกับค่าคงที่ที่วัดมา(self):
        self.assertEqual(article_builder.SLOPE_FLAT_PERCENT, 0.2)
        period = 20
        base = [100.0] * (period + article_builder.SLOPE_LOOKBACK)

        # ขยับให้ค่าเฉลี่ยเปลี่ยนราว 0.1% (ต่ำกว่าเกณฑ์) → flat
        under = list(base)
        under[-1] = 100.0 + 0.1 * period / 100 * 100
        self.assertEqual(article_builder._average_line_slope(self._closes(under), period)[0],
                         "flat")

        # ขยับให้เปลี่ยนราว 0.4% (เกินเกณฑ์) → up
        over = list(base)
        over[-1] = 100.0 + 0.4 * period / 100 * 100
        self.assertEqual(article_builder._average_line_slope(self._closes(over), period)[0],
                         "up")


class ContextNarrationTests(unittest.TestCase):
    """ย่อหน้าขยายของ v1.1 ต้องเล่าเฉพาะสิ่งที่อยู่ใน context — ห้ามมีเลขนอกหลักฐาน"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data, cls.markdown = build_sample(Path(cls.tmp.name))
        cls.context = cls.data["context"]
        cls.body = cls.markdown.split("---", 2)[2]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_evidence_pack_carries_every_context_group(self):
        for group in ("streak", "ranges", "moving_average", "volatility", "levels"):
            with self.subTest(group=group):
                self.assertIn(group, self.context)
        self.assertEqual(self.context["ranges"]["short"]["window"],
                         article_builder.LOOKBACK_SHORT)
        self.assertEqual(self.context["ranges"]["long"]["window"],
                         article_builder.LOOKBACK_LONG)

    def test_context_field_names_are_free_of_denylist_words(self):
        """article.json เป็นไฟล์ public — ชื่อ field ห้ามมีคำ robot (เช่น session)"""
        blob = json.dumps(self.context, ensure_ascii=False).lower()
        for term in voice_rules.VOICE_DENYLIST:
            with self.subTest(term=term):
                self.assertNotIn(term, blob)

    def test_day_counts_in_prose_come_from_evidence_fields(self):
        """จำนวนวันเป็นเลขที่ spec ให้ดึงจากฟิลด์ตรง ๆ — ต้องตรงกับ evidence เป๊ะ"""
        streak = self.context["streak"]
        if streak["days"] and streak["days"] >= article_builder.STREAK_MIN_DAYS:
            self.assertIn(f"{streak['days']} วันทำการ", self.markdown)
        for key in ("short", "long"):
            window = self.context["ranges"][key]
            if window:
                self.assertIn(f"{window['window']} วันทำการ", self.markdown)
        if self.context["volatility"]:
            self.assertIn(f"{self.context['volatility']['window']} วันทำการ", self.markdown)

    def test_streak_direction_word_matches_the_evidence_direction(self):
        streak = self.context["streak"]
        if not (streak["days"] and streak["days"] >= article_builder.STREAK_MIN_DAYS):
            self.skipTest(
                f"ชุดข้อมูลนี้ปิดติดต่อกันไม่ถึง {article_builder.STREAK_MIN_DAYS} วัน "
                "— ประโยคถูกตัดเงียบตาม spec")
        if streak["direction"] == "up":
            self.assertIn("ปิดบวกติดต่อกัน", self.markdown)
            self.assertNotIn("ปิดลบติดต่อกัน", self.markdown)
        else:
            self.assertIn("ปิดลบติดต่อกัน", self.markdown)
            self.assertNotIn("ปิดบวกติดต่อกัน", self.markdown)

    def test_range_extremes_are_printed_with_the_shared_rounding_rule(self):
        window = self.context["ranges"]["short"]
        for key in ("high", "low"):
            with self.subTest(key=key):
                self.assertIn(voice_rules.format_price(window[key], "spot_metal"),
                              self.markdown)

    def test_percent_values_in_prose_all_exist_in_the_context(self):
        """เก็บทุกเลข % ในบทความแล้วเทียบกับชุดค่าที่ evidence มีจริง"""
        allowed = set()
        for value in (self.data["snapshot"]["percent_magnitude"],
                      self.context["levels"]["support_distance_percent"],
                      self.context["levels"]["resistance_distance_percent"]):
            if value is not None:
                allowed.add(voice_rules.format_percent(value))
        window = self.context["ranges"]["short"]
        for key in ("percent_from_high", "percent_from_low"):
            if window and window[key] is not None:
                allowed.add(voice_rules.format_percent(window[key]))
        for entry in self.context["moving_average"]["entries"].values():
            allowed.add(voice_rules.format_percent(entry["distance_percent"]))
        volatility = self.context["volatility"]
        if volatility:
            for key in ("today_range_percent", "average_range_percent"):
                allowed.add(voice_rules.format_percent(volatility[key]))

        printed = set(re.findall(r"(\d+\.\d+)%", self.body))
        self.assertTrue(printed, "บทความ v1.1 ต้องมีตัวเลขเปอร์เซ็นต์อย่างน้อยหนึ่งค่า")
        self.assertEqual(printed - allowed, set())

    def test_article_grew_into_the_new_length_band(self):
        words = voice_rules.count_public_words(self.markdown)
        self.assertGreaterEqual(words, 350)
        self.assertLessEqual(words, 560)

    def test_opening_has_two_paragraphs_and_technical_has_two(self):
        paragraphs = [line.strip() for line in self.body.splitlines()
                      if line.strip() and not line.strip().startswith(("#", "!", "*"))]
        heading_at = paragraphs.index(voice_rules.TECHNICAL_HEADING)
        opening = paragraphs[:heading_at]
        self.assertEqual(len(opening), 2, "ช่วง ① ของ v1.1 มีสองย่อหน้า")
        block_at = next(index for index, line in enumerate(paragraphs)
                        if line.endswith(":") and index > heading_at)
        self.assertEqual(len(paragraphs[heading_at + 1:block_at]), 2,
                         "ช่วง ③ ของ v1.1 มีสองย่อหน้า")

    def test_strategy_view_is_bound_to_evidence_conditions(self):
        if "ในเชิงกลยุทธ์" not in self.markdown:
            self.skipTest("ไม่มีระดับให้ผูกเงื่อนไข — ประโยคถูกตัดเงียบ")
        price = self.data["snapshot"]["price"]
        rsi = self.data["technical"]["rsi14"]
        sma20 = self.data["technical"]["ma20"]
        if "ฝั่งขายยังเป็นต่อ" in self.markdown:
            self.assertTrue((rsi is not None and rsi < 50) or (sma20 and price < sma20))
        if "ฝั่งซื้อยังเป็นต่อ" in self.markdown:
            self.assertTrue(rsi is None or rsi >= 50)

    def test_paragraphs_disappear_silently_when_evidence_is_missing(self):
        """หลักการข้อ 3 ของ spec: ไม่มีข้อมูล = ประโยคหาย ไม่ใช่เขียนคำแก้ตัว"""
        bare = json.loads(json.dumps(self.data))
        bare["context"] = {"streak": {"direction": None, "days": None, "last_date": None},
                           "ranges": {"short": None, "long": None},
                           "moving_average": {"entries": {}, "structure": None},
                           "volatility": None,
                           "levels": {"support_distance_percent": None,
                                      "resistance_distance_percent": None,
                                      "band_position": None, "band_position_percent": None}}
        self.assertEqual(article_builder._context_paragraph(bare), "")
        markdown = article_builder.render_markdown(bare)
        for excuse in ("ไม่มีข้อมูล", "ไม่เพียงพอ", "ยังคำนวณไม่ได้", "ไม่ปรากฏ"):
            with self.subTest(excuse=excuse):
                self.assertNotIn(excuse, markdown)


class CryptoRenderingTests(unittest.TestCase):
    """ย่อหน้าขยายต้องปัดเลขตามชนิดสินทรัพย์ — BTC = หลักร้อย + comma (spec ข้อ 4)

    สายท่อจริงของ btcusd ถูกกั้นที่ด่านข้อมูลในวันที่ทำงาน (provider ส่งแท่งว่าง)
    เทสนี้จึงเป็นตัวยืนยันเส้นทาง crypto ของ v1.1 แทนการรันสด
    """

    def _data(self) -> dict:
        return {
            "instrument": {"instrument_type": "crypto_spot", "unit": "ดอลลาร์ต่อบิตคอยน์",
                           "symbol": "BTC/USD", "cutoff_at": CUTOFF},
            "snapshot": {"price": 67842.35, "open": 67500.0, "previous_close": 67000.0,
                         "percent_magnitude": 1.26, "high": 68010.0, "low": 67210.0},
            "move": {"direction": "up", "class": voice_rules.MOVE_NORMAL},
            "technical": {"ma20": 66000.0, "ma50": 64000.0, "rsi14": 58.0},
            "sr_block": {"supports": [{"raw": 67210.0, "text": "67,200"}],
                         "resistances": [{"raw": 68010.0, "text": "68,000"}]},
            "context": {
                "streak": {"direction": "up", "days": 3, "last_date": "2026-08-02"},
                "ranges": {
                    "short": {"window": 20, "high": 69150.4, "high_date": "2026-07-28",
                              "low": 61240.9, "low_date": "2026-07-15",
                              "price_side_high": "below", "price_side_low": "above",
                              "percent_from_high": 1.89, "percent_from_low": 10.78},
                    "long": {"window": 60, "high": 72400.0, "high_date": "2026-06-10",
                             "low": 58900.0, "low_date": "2026-06-25",
                             "price_side_high": "below", "price_side_low": "above",
                             "percent_from_high": 6.29, "percent_from_low": 15.19},
                },
                "moving_average": {
                    "entries": {"ma20": {"period": 20, "price_side": "above",
                                         "distance_percent": 2.79, "slope": "up",
                                         "slope_lookback": 5,
                                         "slope_reference_date": "2026-07-28"}},
                    "structure": "short_above_long"},
                "volatility": {"window": 14, "today_range": 800.0, "average_range": 640.0,
                               "today_range_percent": 1.18, "average_range_percent": 0.94,
                               "comparison": "wider"},
                "levels": {"support_distance_percent": 0.93,
                           "resistance_distance_percent": 0.25,
                           "band_position": "upper", "band_position_percent": 79.1},
            },
        }

    def test_context_paragraph_uses_hundred_step_prices_with_comma(self):
        text = article_builder._context_paragraph(self._data())
        for expected in ("ปิดบวกติดต่อกัน 3 วันทำการ", "69,200", "61,200", "72,400", "58,900"):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)
        self.assertNotIn("69150", text)      # ห้ามหลุดค่าดิบที่ยังไม่ปัด
        self.assertIn("1.89%", text)
        self.assertIn("10.78%", text)

    def test_technical_paragraphs_carry_the_new_readings(self):
        paragraphs = article_builder._technical_paragraphs(self._data())
        self.assertEqual(len(paragraphs), 2)
        first, second = paragraphs
        self.assertIn("2.79%", first)                       # ระยะห่างจากเส้นค่าเฉลี่ย
        self.assertIn("เส้นระยะสั้นนำเส้นระยะยาว", first)      # โครงสร้างสั้น-ยาว
        self.assertIn("ยังไต่ขึ้น", first)                    # ความชัน
        self.assertIn("กว้างกว่าการเคลื่อนไหวตามปกติ", first)   # ความผันผวน
        self.assertIn("ในเชิงโครงสร้างระดับ", second)
        self.assertIn("ค่อนไปทางขอบบนของกรอบ", second)
        self.assertIn("ในเชิงกลยุทธ์", second)

    def test_percent_tokens_are_all_two_decimals(self):
        data = self._data()
        text = " ".join([article_builder._context_paragraph(data),
                         *article_builder._technical_paragraphs(data)])
        for token in re.findall(r"([\d,.]+)%", text):
            with self.subTest(token=token):
                self.assertRegex(token, r"^\d+\.\d{2}$")


class SchemaContractTests(unittest.TestCase):
    """สัญญาโครง article.json ต้องเดินตามของจริง — ไม่ใช่ไฟล์ schema ที่ล้าหลังโค้ด"""

    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(
            (REPO_ROOT / "schemas" / "article-voice-v1.schema.json").read_text(encoding="utf-8")
        )
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data, _ = build_sample(Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_required_top_level_key_is_produced(self):
        for key in self.schema["required"]:
            with self.subTest(key=key):
                self.assertIn(key, self.data)

    def test_schema_no_longer_requires_the_removed_note(self):
        sr_block = self.schema["properties"]["sr_block"]
        self.assertNotIn("note", sr_block["required"])
        self.assertNotIn("note", sr_block["properties"])
        self.assertEqual(sr_block["not"], {"required": ["note"]})

    def test_schema_documents_the_new_context_groups(self):
        context = self.schema["properties"]["context"]
        for group in ("streak", "ranges", "moving_average", "volatility", "levels"):
            with self.subTest(group=group):
                self.assertIn(group, context["required"])
                self.assertIn(group, self.data["context"])


class MoveVerbSelectionTests(unittest.TestCase):
    """กริยาต่อเนื่องช่วง ① ต้องเลือกตามตาราง 2.6 — ห้ามสุ่ม ห้ามโกหกทิศ"""

    def _render_opening(self, direction: str, move_class: str) -> str:
        data = {
            "instrument": {"instrument_type": "forex_spot", "unit": "ดอลลาร์ต่อยูโร",
                           "symbol": "EUR/USD", "cutoff_at": CUTOFF},
            "snapshot": {"open": 1.15460, "price": 1.15260, "previous_close": 1.15235,
                         "percent_magnitude": 0.5, "high": 1.15620, "low": 1.15234},
            "move": {"direction": direction, "class": move_class},
        }
        return article_builder._opening_paragraph(data)

    def test_normal_up_uses_buying_support_verb(self):
        text = self._render_opening("up", voice_rules.MOVE_NORMAL)
        self.assertIn("แรงซื้อเพิ่มเติมหนุนราคา", text)

    def test_strong_down_uses_strong_fall_verb(self):
        text = self._render_opening("down", voice_rules.MOVE_STRONG)
        self.assertIn("ร่วงลงอย่างแรง", text)

    def test_quiet_day_uses_range_verb_without_direction(self):
        text = self._render_opening("up", voice_rules.MOVE_QUIET)
        # ก8 ของคลังคือ "แกว่งตัวในกรอบ" เฉย ๆ — ห้ามเติม "แคบ" เอง (Tester #4)
        self.assertIn("แกว่งตัวในกรอบ", text)
        self.assertNotIn("กรอบแคบ", text)
        self.assertNotIn("แรงซื้อเพิ่มเติม", text)

    def test_unknown_change_cuts_direction_sentence_silently(self):
        data = {
            "instrument": {"instrument_type": "forex_spot", "unit": "ดอลลาร์ต่อยูโร",
                           "symbol": "EUR/USD", "cutoff_at": CUTOFF},
            "snapshot": {"open": 1.15460, "price": 1.15260, "previous_close": None,
                         "percent_magnitude": None, "high": 1.15620, "low": 1.15234},
            "move": {"direction": "unknown", "class": voice_rules.MOVE_UNKNOWN},
        }
        text = article_builder._opening_paragraph(data)
        self.assertNotIn("จากราคาปิดวันก่อนหน้า", text)
        self.assertIn("เปิดตลาดที่ระดับ", text)


class PackagePipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _snapshot(self, fixture: str) -> Path:
        rows = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))["rows"]
        path = self.root / f"{fixture}"
        path.write_text(json.dumps({"rows": rows}, ensure_ascii=False), encoding="utf-8")
        return path

    def test_blocked_asset_gets_no_public_folder(self):
        result = build_daily_package.build(
            "xauusd", batch_id="test-batch", output_root=self.root,
            snapshot_path=self._snapshot("xau_5_points_with_weekend.json"), cutoff_at=CUTOFF,
        )

        self.assertEqual(result["status"], "blocked")
        asset_dir = self.root / "test-batch" / "xauusd"
        self.assertTrue((asset_dir / "internal" / "qa-report.json").is_file())
        self.assertFalse((asset_dir / "public").exists())

    def test_clean_asset_produces_the_full_package(self):
        result = build_daily_package.build(
            "xauusd", batch_id="test-batch", output_root=self.root,
            snapshot_path=self._snapshot("xau_valid_120_sessions.json"), cutoff_at=CUTOFF,
        )

        self.assertEqual(result["status"], "built")
        asset_dir = self.root / "test-batch" / "xauusd"
        for name in ("raw.snapshot.json", "normalized.market.json", "technical.evidence.json",
                     "source-log.json", "qa-report.json", "license-report.json",
                     "level-map.json"):
            with self.subTest(file=name):
                self.assertTrue((asset_dir / "internal" / name).is_file())
        for name in ("article.md", "article.json", "chart-daily.png", "meta.json"):
            with self.subTest(file=name):
                self.assertTrue((asset_dir / "public" / name).is_file())

    def test_meta_records_deterministic_word_count(self):
        result = build_daily_package.build(
            "xauusd", batch_id="test-batch", output_root=self.root,
            snapshot_path=self._snapshot("xau_valid_120_sessions.json"), cutoff_at=CUTOFF,
        )
        meta = json.loads((self.root / "test-batch" / "xauusd" / "public" / "meta.json")
                          .read_text(encoding="utf-8"))
        article = (self.root / "test-batch" / "xauusd" / "public" / "article.md") \
            .read_text(encoding="utf-8")

        self.assertEqual(meta["word_count"], voice_rules.count_public_words(article))
        self.assertEqual(meta["word_count"], result["words"])
        self.assertIn("voice_rules", meta["word_count_method"])
        self.assertEqual(meta["contract"], article_builder.CONTRACT)

    def test_internal_fields_stay_out_of_the_public_article(self):
        build_daily_package.build(
            "xauusd", batch_id="test-batch", output_root=self.root,
            snapshot_path=self._snapshot("xau_valid_120_sessions.json"), cutoff_at=CUTOFF,
        )
        article = (self.root / "test-batch" / "xauusd" / "public" / "article.md").read_text(encoding="utf-8")
        meta = json.loads((self.root / "test-batch" / "xauusd" / "public" / "meta.json").read_text(encoding="utf-8"))

        for key in ("qa_status", "publication_clearance", "data_status"):
            with self.subTest(key=key):
                self.assertNotIn(f"{key}:", article)
                self.assertIn(key, meta)

    def test_change_values_are_recorded_in_technical_evidence(self):
        """C6: ค่า change ที่บทความใช้ต้องอยู่ใน technical.evidence.json พร้อมขนาดที่แสดงจริง"""
        build_daily_package.build(
            "xauusd", batch_id="test-batch", output_root=self.root,
            snapshot_path=self._snapshot("xau_valid_120_sessions.json"), cutoff_at=CUTOFF,
        )
        evidence = json.loads(
            (self.root / "test-batch" / "xauusd" / "internal" / "technical.evidence.json")
            .read_text(encoding="utf-8")
        )
        article = json.loads(
            (self.root / "test-batch" / "xauusd" / "public" / "article.json")
            .read_text(encoding="utf-8")
        )

        for key in ("change", "change_percent", "change_magnitude",
                    "change_percent_magnitude", "previous_close", "latest_close"):
            with self.subTest(key=key):
                self.assertIn(key, evidence)
        self.assertEqual(evidence["change"], article["snapshot"]["change"])
        self.assertEqual(evidence["change_percent"], article["snapshot"]["percent"])
        if evidence["change"] is not None:
            self.assertEqual(evidence["change_magnitude"], abs(evidence["change"]))

    def test_context_evidence_is_recorded_on_the_internal_side(self):
        """v1.1: ค่าที่ย่อหน้าขยายใช้ต้องอยู่ใน technical.evidence.json ตรงกับ article.json"""
        build_daily_package.build(
            "xauusd", batch_id="test-batch", output_root=self.root,
            snapshot_path=self._snapshot("xau_valid_120_sessions.json"), cutoff_at=CUTOFF,
        )
        evidence = json.loads(
            (self.root / "test-batch" / "xauusd" / "internal" / "technical.evidence.json")
            .read_text(encoding="utf-8")
        )
        article = json.loads(
            (self.root / "test-batch" / "xauusd" / "public" / "article.json")
            .read_text(encoding="utf-8")
        )

        self.assertIn("context", evidence)
        self.assertEqual(evidence["context"], article["context"])
        for group in ("streak", "ranges", "moving_average", "volatility", "levels"):
            with self.subTest(group=group):
                self.assertIn(group, evidence["context"])

    def test_removed_public_lines_are_kept_for_audit(self):
        """V1: หมายเหตุ/disclaimer หายจากบทความ แต่ยังบันทึกไว้ใน qa-report เพื่อ audit"""
        build_daily_package.build(
            "xauusd", batch_id="test-batch", output_root=self.root,
            snapshot_path=self._snapshot("xau_valid_120_sessions.json"), cutoff_at=CUTOFF,
        )
        asset_dir = self.root / "test-batch" / "xauusd"
        article = (asset_dir / "public" / "article.md").read_text(encoding="utf-8")
        qa = json.loads((asset_dir / "internal" / "qa-report.json").read_text(encoding="utf-8"))

        self.assertNotIn(voice_rules.DISCLAIMER, article)
        self.assertNotIn("หมายเหตุ", article)
        self.assertEqual(qa["omitted_public_lines"]["disclaimer"], voice_rules.DISCLAIMER)
        self.assertIn(qa["omitted_public_lines"]["note"],
                      (voice_rules.NOTE_FORMING, voice_rules.NOTE_CLOSED))

    def test_failed_article_gate_leaves_no_public_folder(self):
        """fail-closed: ด่านบทความไม่ผ่าน = ไม่มีโฟลเดอร์ public ของ asset นั้น"""
        forced_fail = {
            "status": "fail", "instrument_type": "spot_metal",
            "findings": [{"rule": "number_rounding", "severity": "fatal",
                          "line": 1, "detail": "จงใจให้ไม่ผ่านเพื่อทดสอบ fail-closed"}],
            "fatal_count": 1, "word_count": 0, "validator_version": "test",
        }
        with mock.patch.object(build_daily_package.public_copy_validator, "validate",
                               return_value=forced_fail):
            result = build_daily_package.build(
                "xauusd", batch_id="test-batch", output_root=self.root,
                snapshot_path=self._snapshot("xau_valid_120_sessions.json"), cutoff_at=CUTOFF,
            )

        asset_dir = self.root / "test-batch" / "xauusd"
        self.assertEqual(result["status"], "rejected")
        self.assertFalse((asset_dir / "public").exists())

        # ของทั้งหมดต้องย้ายไป internal/rejected/ เพื่อ audit ได้ ไม่ใช่หายไปเฉย ๆ
        rejected = asset_dir / "internal" / "rejected"
        for name in ("article.md", "article.json", "chart-daily.png", "meta.json"):
            with self.subTest(file=name):
                self.assertTrue((rejected / name).is_file())

        qa = json.loads((asset_dir / "internal" / "qa-report.json").read_text(encoding="utf-8"))
        self.assertEqual(qa["status"], "rejected")
        self.assertEqual(qa["public_output"], "internal/rejected/")

    def test_license_holds_publication_even_when_content_passes(self):
        result = build_daily_package.build(
            "xauusd", batch_id="test-batch", output_root=self.root,
            snapshot_path=self._snapshot("xau_valid_120_sessions.json"), cutoff_at=CUTOFF,
        )

        self.assertTrue(result["content_ok"])
        self.assertEqual(result["clearance"], license_gate.APPROVED_INTERNAL)


if __name__ == "__main__":
    unittest.main()
