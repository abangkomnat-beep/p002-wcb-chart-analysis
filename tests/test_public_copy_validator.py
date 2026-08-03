"""เทสด่านตรวจบทความ — ต้องจับของจริงได้ และต้องไม่ตีบทความที่สะอาดว่าผิด"""

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
def _resolve_contract_dir() -> Path:
    """ชุด pilot อาจอยู่ใน OUTPUT/contract-v2-pilot หรือ OUTPUT/<วันที่>/contract-v2-pilot"""
    root = REPO_ROOT.parent / "OUTPUT"
    direct = root / "contract-v2-pilot"
    if direct.is_dir():
        return direct
    nested = sorted(root.glob("*/contract-v2-pilot"), reverse=True)
    return nested[0] if nested else direct


OUTPUT_DIR = _resolve_contract_dir()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import public_copy_validator as validator  # noqa: E402


CLEAN_ARTICLE = """---
title: EUR/USD ทรงตัวก่อนตัวเลขจ้างงาน
symbol: EUR/USD
instrument_type: forex_spot
timezone: Asia/Bangkok
---

*ข้อมูล ณ 13:30 น. เวลาไทย — แท่งรายวันกำลังก่อตัว*

ราคาปิดล่าสุดที่ 1.15354 และแกว่งในกรอบแคบ

## ระดับตัดสินใจ

แนวต้านแรกอยู่ที่ 1.15620 และแนวรับที่ 1.15300
"""

EVIDENCE = {
    "snapshot": {"price": 1.15354, "percent": 0.09},
    "levels": [{"label": "R1", "value_or_zone": 1.15620}, {"label": "S1", "value_or_zone": 1.15300}],
}


class CleanArticleTests(unittest.TestCase):
    def test_clean_article_passes(self):
        result = validator.validate(CLEAN_ARTICLE, evidence=EVIDENCE)
        self.assertEqual(result["status"], "pass", result["findings"])
        self.assertEqual(result["fatal_count"], 0)

    def test_forex_allows_five_decimals(self):
        result = validator.validate(CLEAN_ARTICLE, evidence=EVIDENCE)
        self.assertEqual(result["max_decimals"], 5)


class SystemTermTests(unittest.TestCase):
    def test_system_word_in_body_fails(self):
        article = CLEAN_ARTICLE.replace("แกว่งในกรอบแคบ", "ส่วนนี้เป็น unavailable")
        result = validator.validate(article, evidence=EVIDENCE)

        self.assertEqual(result["status"], "fail")
        self.assertIn("system_term", {item["rule"] for item in result["findings"]})

    def test_machine_timestamp_in_body_fails(self):
        article = CLEAN_ARTICLE.replace("13:30 น.", "2026-08-03T06:33:53.081296+00:00")
        result = validator.validate(article, evidence=EVIDENCE)

        self.assertIn("machine_timestamp", {item["rule"] for item in result["findings"]})
        self.assertEqual(result["status"], "fail")

    def test_local_path_fails(self):
        article = CLEAN_ARTICLE + "\nดูไฟล์ที่ C:\\Users\\wcb\\article.md\n"
        result = validator.validate(article, evidence=EVIDENCE)

        self.assertIn("local_path", {item["rule"] for item in result["findings"]})


class FrontmatterTests(unittest.TestCase):
    def test_internal_field_in_frontmatter_fails(self):
        article = CLEAN_ARTICLE.replace(
            "timezone: Asia/Bangkok",
            "timezone: Asia/Bangkok\npublication_clearance: hold-data-license-review",
        )
        result = validator.validate(article, evidence=EVIDENCE)

        self.assertEqual(result["status"], "fail")
        self.assertIn("internal_frontmatter", {item["rule"] for item in result["findings"]})

    def test_missing_contract_field_fails(self):
        article = CLEAN_ARTICLE.replace("instrument_type: forex_spot\n", "")
        result = validator.validate(article, evidence=EVIDENCE)

        self.assertIn("contract_field_missing", {item["rule"] for item in result["findings"]})

    def test_iso_in_frontmatter_is_warning_only(self):
        article = CLEAN_ARTICLE.replace(
            "timezone: Asia/Bangkok",
            "timezone: Asia/Bangkok\ncutoff_at: '2026-08-03T06:33:53Z'",
        )
        result = validator.validate(article, evidence=EVIDENCE)

        rules = {item["rule"]: item["severity"] for item in result["findings"]}
        self.assertEqual(rules.get("machine_timestamp_frontmatter"), "warning")
        self.assertEqual(result["status"], "pass")


class NumberTests(unittest.TestCase):
    def test_precision_over_limit_fails(self):
        article = CLEAN_ARTICLE.replace("1.15354", "1.1535356")
        result = validator.validate(article, evidence={"snapshot": {"price": 1.1535356}})

        self.assertIn("precision", {item["rule"] for item in result["findings"]})

    def test_number_missing_from_evidence_fails(self):
        article = CLEAN_ARTICLE.replace("1.15620", "1.19999")
        result = validator.validate(article, evidence=EVIDENCE)

        findings = [item for item in result["findings"] if item["rule"] == "number_without_evidence"]
        self.assertTrue(findings)
        self.assertIn("1.19999", findings[0]["detail"])

    def test_rounded_number_still_matches_evidence(self):
        article = CLEAN_ARTICLE.replace("1.15354", "1.1535")
        result = validator.validate(article, evidence=EVIDENCE)

        self.assertEqual(result["status"], "pass", result["findings"])

    def test_number_check_can_be_switched_off(self):
        article = CLEAN_ARTICLE.replace("1.15620", "1.19999")
        result = validator.validate(article, evidence=EVIDENCE, check_numbers=False)

        self.assertEqual(result["status"], "pass")


class RealPilotArticleTests(unittest.TestCase):
    """บทความ pilot ชุดเดิมต้องไม่ผ่าน — ใช้เป็นหลักฐานว่าด่านทำงานจริง"""

    def test_xau_pilot_article_is_blocked(self):
        article_path = OUTPUT_DIR / "2026-08-03_xauusd.md"
        if not article_path.is_file():
            self.skipTest("ไม่มีบทความ pilot ในเครื่องนี้")
        result = validator.validate(article_path.read_text(encoding="utf-8"), check_numbers=False)

        self.assertEqual(result["status"], "fail")
        rules = {item["rule"] for item in result["findings"]}
        self.assertIn("system_term", rules)
        self.assertIn("internal_frontmatter", rules)


if __name__ == "__main__":
    unittest.main()
