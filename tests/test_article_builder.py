"""เทสตัวประกอบบทความ v3 และสายท่อรวม — บทความต้องผ่านด่านของตัวเองเสมอ"""

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


CUTOFF = "2026-08-03T07:00:00+00:00"


def build_sample(tmp: Path) -> tuple[dict, str]:
    rows = json.loads((FIXTURES / "xau_valid_120_sessions.json").read_text(encoding="utf-8"))["rows"]
    report = integrity.assess(rows, "xauusd", calculated_at=CUTOFF)
    level_map = level_engine.build_level_map(report)
    chart_metadata = chart_renderer.render_daily_chart(
        candles=report["candles"], output_path=tmp / "chart-daily.png",
        symbol="XAU/USD", cutoff_at=CUTOFF, levels=level_map["zones"],
        indicator_series={"sma20": chart_renderer.rolling_mean_series(report["candles"], 20)},
        decimals=2,
    )
    data = article_builder.build_article_data(
        report=report, level_map=level_map, chart_metadata=chart_metadata,
        license_result=license_gate.evaluate("xauusd"), symbol="XAU/USD",
        instrument_type="spot_metal", unit="ดอลลาร์ต่อออนซ์", decimals=2,
        cutoff_at=CUTOFF, batch_id="2026-08-03T07-00Z-daily-market",
    )
    return data, article_builder.render_markdown(data)


class ArticleStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data, cls.markdown = build_sample(Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_all_v3_sections_appear_in_order(self):
        positions = []
        for section in article_builder.SECTIONS:
            if section == "มุมสำหรับผู้ลงทุนไทย":
                continue  # แสดงเฉพาะเมื่อมีข้อมูลไทยจริง
            heading = f"## {section}"
            self.assertIn(heading, self.markdown)
            positions.append(self.markdown.index(heading))
        self.assertEqual(positions, sorted(positions))

    def test_thai_investor_section_only_with_real_data(self):
        self.assertNotIn("## มุมสำหรับผู้ลงทุนไทย", self.markdown)

    def test_headline_and_lead_exist(self):
        self.assertTrue(self.data["headline"])
        self.assertIn(f"# {self.data['headline']}", self.markdown)
        self.assertIn("ข้อมูล ณ", self.markdown)

    def test_public_time_is_thai_not_iso(self):
        self.assertIn("เวลาไทย", self.markdown)
        self.assertNotIn("T07:00:00", self.markdown.split("---", 2)[2])


class ArticleHonestyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data, cls.markdown = build_sample(Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_article_passes_its_own_validator(self):
        result = public_copy_validator.validate(
            self.markdown, evidence=self.data, instrument_type="spot_metal"
        )
        self.assertEqual(result["status"], "pass", result["findings"])

    def test_no_causal_claim_without_verified_news(self):
        self.assertFalse(self.data["drivers"]["causal_claims_allowed"])
        for word in ("เพราะดอลลาร์", "จากแรงหนุน", "ตอบรับข่าว"):
            self.assertNotIn(word, self.markdown)

    def test_scenarios_stay_daily_without_intraday_data(self):
        for scenario in self.data["scenarios"]:
            with self.subTest(scenario=scenario["name"]):
                self.assertEqual(scenario["classification"], level_engine.DAILY_SCENARIO)
                self.assertFalse(scenario["executable"])
        for phrase in ("เข้า Buy ตรงนี้", "เข้า Sell ตรงนี้", "Entry confirmed"):
            self.assertNotIn(phrase, self.markdown)

    def test_every_scenario_target_is_an_approved_level(self):
        for scenario in self.data["scenarios"]:
            with self.subTest(scenario=scenario["name"]):
                self.assertTrue(scenario["target_check"]["valid"])

    def test_risk_section_names_the_single_source_limit(self):
        self.assertIn("ผู้ให้ข้อมูลรายเดียว", self.markdown)

    def test_word_count_ignores_tables_and_headings(self):
        with_table = article_builder.approximate_thai_words(self.markdown)
        prose = article_builder.prose_only(self.markdown)

        self.assertNotIn("|", prose)
        self.assertNotIn("##", prose)
        self.assertLess(with_table, len(self.markdown) / 4)


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
                     "source-log.json", "qa-report.json", "license-report.json"):
            with self.subTest(file=name):
                self.assertTrue((asset_dir / "internal" / name).is_file())
        for name in ("article.md", "article.json", "chart-daily.png", "meta.json"):
            with self.subTest(file=name):
                self.assertTrue((asset_dir / "public" / name).is_file())

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
            "status": "fail", "instrument_type": "spot_metal", "max_decimals": 2,
            "findings": [{"rule": "number_without_evidence", "severity": "fatal",
                          "line": 1, "detail": "จงใจให้ไม่ผ่านเพื่อทดสอบ fail-closed"}],
            "fatal_count": 1, "validator_version": "test",
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
