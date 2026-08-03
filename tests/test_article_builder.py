"""เทสตัวประกอบบทความโครงเล่าเรื่อง 4 ช่วง (Voice v1) และสายท่อรวม

บทความที่ generate ต้อง: ตรงโครง spec ทุกช่วง · ผ่านด่านของตัวเองแบบ fatal 0 ·
ไม่มีคำ denylist · เลขชุดเดียวกันทุกตำแหน่ง · ยาว 250-450 คำ · ไม่ลอก corpus
"""

import json
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
            "แนวต้าน ",
            "หมายเหตุ ",
            voice_rules.DISCLAIMER,
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

    def test_note_line_carries_forming_candle_condition(self):
        # เรื่องแท่งยังไม่ปิดถูกย้ายจากบรรทัดเวลาไปเป็นหมายเหตุ 1 บรรทัดของช่วง ④
        self.assertIn(f"หมายเหตุ {voice_rules.NOTE_FORMING}", self.markdown)

    def test_chart_is_present_with_human_caption(self):
        self.assertIn("](chart-daily.png)", self.markdown)
        caption_lines = [line for line in self.body.splitlines()
                        if line.startswith("*กราฟ")]
        self.assertEqual(len(caption_lines), 1)


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
        self.assertIn("แกว่งตัวในกรอบแคบ", text)
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
