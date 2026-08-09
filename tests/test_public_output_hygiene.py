"""เทสกันหลุดซ้ำ — ของภายในต้องไม่อยู่ในไฟล์ฝั่ง public แม้แต่ไฟล์เดียว

ตรวจสองชั้นกับทุกไฟล์ .json/.md ใต้ public/ ของ batch:
1. ชื่อ field นโยบายภายใน (article_builder.PUBLIC_FIELD_DENYLIST) — ทุกชั้นของ JSON
2. คำ robot ตาม Voice Spec ข้อ 3 (voice_rules.VOICE_DENYLIST) — ระดับข้อความทั้งไฟล์
   จับทั้งค่าใน label/caption/alt_text และชื่อ field อย่าง sma20 ที่ผู้อ่านเห็นได้

denylist ทั้งสองชุดอยู่ที่เดียว — เพิ่มรายการใหม่แล้วถูกตรวจทันทีโดยไม่ต้องแก้เทส
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import article_builder, build_daily_package, voice_rules  # noqa: E402


DENYLIST = article_builder.PUBLIC_FIELD_DENYLIST
CUTOFF = "2026-08-03T07:00:00+00:00"


def _json_keys(node) -> set[str]:
    """รวมชื่อ key ทุกชั้นของโครงสร้าง JSON"""
    keys: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            keys.add(key)
            keys |= _json_keys(value)
    elif isinstance(node, list):
        for item in node:
            keys |= _json_keys(item)
    return keys


def scan_public_dir(public_dir: Path) -> list[str]:
    """คืนรายการทุกจุดที่พบของต้องห้ามในไฟล์ .json/.md ใต้ public/

    สองชั้น: (1) ชื่อ field ภายใน — .json ตรวจระดับชื่อ key ทุกชั้น, .md ตรวจแบบ
    ข้อความเพราะ field หลุดมาในรูป frontmatter ได้ · (2) คำ robot ตาม Voice Spec
    ตรวจระดับข้อความทั้งไฟล์ (ละตินไม่สนตัวพิมพ์) — ป้าย/label ที่ผู้อ่านเห็นต้องเป็นภาษาคน
    """
    findings: list[str] = []
    for path in sorted(public_dir.rglob("*")):
        if path.suffix.lower() not in {".json", ".md"}:
            continue
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            leaked = _json_keys(json.loads(text)) & DENYLIST
        else:
            leaked = {field for field in DENYLIST if field in text}
        findings.extend(f"{path.name}: {field}" for field in sorted(leaked))

        lowered = text.lower()
        robot_words = {term for term in voice_rules.VOICE_DENYLIST if term in lowered}
        findings.extend(f"{path.name}: คำต้องห้าม \"{term}\"" for term in sorted(robot_words))
    return findings


class DenylistScannerTests(unittest.TestCase):
    """ตัว scan ต้องจับของจริงได้ — ไม่ใช่เขียวเพราะไม่เคยตรวจเจออะไรเลย"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.public = Path(self.tmp.name) / "public"
        self.public.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_scanner_catches_forbidden_field_in_json(self):
        (self.public / "article.json").write_text(
            json.dumps({"levels": [{"label": "R1", "merge_tolerance": 0.0017}]}),
            encoding="utf-8",
        )
        self.assertEqual(scan_public_dir(self.public), ["article.json: merge_tolerance"])

    def test_scanner_catches_forbidden_field_nested_deep(self):
        payload = {"scenarios": [{"nested": {"deeper": {"forbidden_language": ["x"]}}}]}
        (self.public / "article.json").write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(scan_public_dir(self.public), ["article.json: forbidden_language"])

    def test_scanner_catches_forbidden_field_in_markdown(self):
        (self.public / "article.md").write_text(
            "---\ntitle: x\napproved_for_publication: true\n---\n", encoding="utf-8",
        )
        self.assertEqual(scan_public_dir(self.public), ["article.md: approved_for_publication"])

    def test_scanner_checks_every_field_in_the_denylist(self):
        """จงใจใส่ field ต้องห้ามครบทุกตัว — ต้องโดนจับครบทุกตัว"""
        payload = {field: "internal" for field in DENYLIST}
        (self.public / "meta.json").write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(len(scan_public_dir(self.public)), len(DENYLIST))

    def test_scanner_catches_robot_word_in_json_value(self):
        """คำ denylist ใน "ค่า" ของ JSON (label/caption) ต้องโดนจับ ไม่ใช่แค่ชื่อ field"""
        payload = {"levels": [{"label": "Pivot S3 + SMA20", "value": 1.5}],
                   "caption": "แท่งล่าสุดกำลังก่อตัว พร้อมระดับตัดสินใจ"}
        (self.public / "chart-daily.chart.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8",
        )
        findings = scan_public_dir(self.public)
        for term in ("pivot", "sma", "กำลังก่อตัว", "ระดับตัดสินใจ"):
            with self.subTest(term=term):
                self.assertIn(f"chart-daily.chart.json: คำต้องห้าม \"{term}\"", findings)

    def test_scanner_catches_robot_word_in_json_field_name(self):
        """ชื่อ field เองก็ห้ามมีคำ robot — เช่น sma20 หรือ session_timezone"""
        (self.public / "article.json").write_text(
            json.dumps({"technical": {"sma20": 1.5}, "session_timezone": "UTC"}),
            encoding="utf-8",
        )
        findings = scan_public_dir(self.public)
        self.assertIn("article.json: คำต้องห้าม \"sma\"", findings)
        self.assertIn("article.json: คำต้องห้าม \"session\"", findings)

    def test_scanner_catches_robot_word_in_markdown(self):
        (self.public / "article.md").write_text(
            "# หัวเรื่อง\n\nราคาแตะ ATR projection ลง\n", encoding="utf-8",
        )
        findings = scan_public_dir(self.public)
        self.assertIn("article.md: คำต้องห้าม \"atr\"", findings)
        self.assertIn("article.md: คำต้องห้าม \"projection\"", findings)

    def test_clean_files_produce_no_findings(self):
        (self.public / "article.json").write_text(
            json.dumps({"levels": [{"label": "R1", "value": 1.5}]}), encoding="utf-8",
        )
        (self.public / "article.md").write_text("# สะอาด\n", encoding="utf-8")
        self.assertEqual(scan_public_dir(self.public), [])


class RealPackageHygieneTests(unittest.TestCase):
    """สร้าง package จริงจาก fixture แล้ว scan ทุกไฟล์ public — ต้องสะอาดทั้ง batch"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        rows = json.loads(
            (FIXTURES / "xau_valid_120_sessions.json").read_text(encoding="utf-8")
        )["rows"]
        snapshot = root / "snapshot.json"
        snapshot.write_text(json.dumps({"rows": rows}, ensure_ascii=False), encoding="utf-8")
        cls.result = build_daily_package.build(
            "xauusd", batch_id="hygiene-batch", output_root=root,
            snapshot_path=snapshot, cutoff_at=CUTOFF,
        )
        cls.asset_dir = root / "hygiene-batch" / "xauusd"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_package_was_actually_built(self):
        self.assertEqual(self.result["status"], "built")

    def test_every_public_file_is_free_of_internal_fields(self):
        findings = scan_public_dir(self.asset_dir / "public")
        self.assertEqual(findings, [], f"field ภายในหลุดไปฝั่ง public: {findings}")

    def test_public_levels_keep_reader_facing_fields(self):
        """ระดับฝั่ง public เหลือเฉพาะ field ที่ผู้อ่านใช้ — รายละเอียดเทคนิคย้ายไป internal"""
        article = json.loads(
            (self.asset_dir / "public" / "article.json").read_text(encoding="utf-8")
        )
        self.assertTrue(article["levels"])
        for level in article["levels"]:
            for key in ("id", "label", "role"):
                self.assertIn(key, level)
            for internal_key in ("calculation_method", "source_field", "members",
                                 "basis_timestamp", "type"):
                self.assertNotIn(internal_key, level)
            self.assertTrue(level["id"].startswith("level-"),
                            f"id ฝั่ง public ต้องเป็นรหัสกลาง ไม่ใช่ {level['id']}")
            self.assertIn(level["role"], ("support", "resistance"))

    def test_internal_level_map_keeps_full_technical_detail(self):
        """ชื่อเทคนิคเต็มและตารางแปลงรหัสต้องยังครบฝั่ง internal เพื่อ audit ได้"""
        level_map = json.loads(
            (self.asset_dir / "internal" / "level-map.json").read_text(encoding="utf-8")
        )
        self.assertTrue(level_map["zones"])
        for zone in level_map["zones"]:
            for key in ("id", "label", "source_field", "calculation_method"):
                self.assertIn(key, zone)
        approved_ids = {zone["id"] for zone in level_map["zones"]
                        if zone.get("approved_for_publication")}
        self.assertEqual(set(level_map["public_id_map"]), approved_ids)


class BuilderStripTests(unittest.TestCase):
    def test_strip_internal_fields_removes_denylist_at_every_depth(self):
        payload = {
            "merge_tolerance": 1,
            "levels": [{"label": "R1", "quality_status": "valid",
                        "approved_for_publication": True}],
            "scenarios": [{"allowed_language": ["x"], "forbidden_language": ["y"],
                           "target_check": {"valid": True}}],
        }
        cleaned = article_builder.strip_internal_fields(payload)
        self.assertEqual(_json_keys(cleaned) & DENYLIST, set())
        self.assertEqual(cleaned["levels"][0]["label"], "R1")
        self.assertTrue(cleaned["scenarios"][0]["target_check"]["valid"])

    def test_unapproved_levels_never_reach_public_data(self):
        """ระดับที่ไม่ผ่านการตรวจต้องถูกกรองออกก่อนตัดธง approved ทิ้ง"""
        report_rows = json.loads(
            (FIXTURES / "xau_valid_120_sessions.json").read_text(encoding="utf-8")
        )["rows"]
        from tools import chart_renderer, integrity, license_gate
        from tools import levels as level_engine

        report = integrity.assess(report_rows, "xauusd", calculated_at=CUTOFF)
        level_map = level_engine.build_level_map(report)
        with tempfile.TemporaryDirectory() as tmp:
            chart_metadata = chart_renderer.render_daily_chart(
                candles=report["candles"], output_path=Path(tmp) / "chart-daily.webp",
                symbol="XAU/USD", cutoff_at=CUTOFF, levels=level_map["zones"], decimals=2,
            )
        data = article_builder.build_article_data(
            report=report, level_map=level_map, chart_metadata=chart_metadata,
            license_result=license_gate.evaluate("xauusd"), symbol="XAU/USD",
            instrument_type="spot_metal", unit="ดอลลาร์ต่อออนซ์", decimals=2,
            cutoff_at=CUTOFF, batch_id="hygiene-batch",
        )
        approved_ids = {level["id"] for level in level_map["zones"]
                        if level.get("approved_for_publication")}
        views, id_map = article_builder.public_level_views(
            level_map["zones"], level_map["reference_price"])
        self.assertEqual(set(id_map), approved_ids, "id_map ต้องครอบเฉพาะระดับที่ผ่านตรวจ")
        self.assertEqual({level["id"] for level in data["levels"]},
                         {view["id"] for view in views})
        self.assertEqual(len(data["levels"]), len(approved_ids))
        self.assertEqual(_json_keys(data) & DENYLIST, set())


if __name__ == "__main__":
    unittest.main()
