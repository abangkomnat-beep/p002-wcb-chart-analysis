"""เทสด่านตรวจบทความ (Voice v1) — ต้องจับของจริงได้ และต้องไม่ตีบทความที่สะอาดว่าผิด

บทความสั้น ๆ ในเทสหน่วยใช้ check_completeness=False เพื่อโฟกัสกฎรายข้อ
ส่วนกฎความยาว/ความครบเครื่องมีเทสของตัวเองด้านล่าง
"""

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _resolve_contract_dir() -> Path:
    """หาชุด pilot ตัวจริงที่ใช้เป็นตัวเทียบฝั่งลบของด่านตรวจ

    ต้องเป็น pilot **ตัวจริง** เท่านั้น — ชุดใน tests/fixtures/pilot-baseline ใช้แทนไม่ได้
    เพราะถูกทำให้เป็นตัวอย่างสังเคราะห์ไว้โดยเจตนา (เลขสมมติ ไม่มีศัพท์ระบบหลุด)
    จึงพิสูจน์กฎ system_term ไม่ได้ ซึ่งเป็นสิ่งที่เทสนี้มีไว้พิสูจน์

    ที่ต้องค้นแบบลึกไม่จำกัดชั้น: โฟลเดอร์ผลผลิตถูกจัดใหม่เมื่อ 2026-08-04 ของเก่าถูกย้าย
    ลงไปอีกชั้นเป็น `output/_รอบเก่า/<batch>/contract-v2-pilot/` · ตอนแรกเขียน glob ไว้
    ชั้นเดียว (`*/contract-v2-pilot`) แล้วเทสนี้เปลี่ยนเป็น "ข้าม" เงียบ ๆ ทันทีที่ย้าย
    จำนวนเทสที่ผ่านไม่ลด มันแค่ย้ายช่อง — ถ้าไม่กด -rs ดู จะไม่มีทางรู้ว่าด่านนี้เลิกถูกพิสูจน์
    """
    root = REPO_ROOT.parent / "OUTPUT"
    direct = root / "contract-v2-pilot"
    if direct.is_dir():
        return direct
    nested = sorted(root.glob("**/contract-v2-pilot"), reverse=True)
    return nested[0] if nested else direct


OUTPUT_DIR = _resolve_contract_dir()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import public_copy_validator as validator  # noqa: E402
from tools import voice_rules  # noqa: E402


# บทความย่อส่วนที่ถูกกติกาทุกข้อ ยกเว้นความยาว (เทสหน่วยปิด check_completeness)
# เลขทุกตัวปัดถูกตามกติกา forex 4 ตำแหน่ง และมีค่าดิบใน EVIDENCE รองรับ
CLEAN_ARTICLE = """---
title: EUR/USD ทรงตัวก่อนเข้าโซนสำคัญ
symbol: EUR/USD
instrument_type: forex_spot
timezone: Asia/Bangkok
---

# EUR/USD ทรงตัวก่อนเข้าโซนสำคัญ

*ข้อมูล ณ 3 ส.ค. 2026 เวลา 13:30 น. (เวลาไทย)*

ราคาล่าสุดเคลื่อนไหวแถว 1.1535 โดยเพิ่มขึ้นราว 0.09% จากราคาปิดวันก่อนหน้า

ข้อมูลเทคนิค (Technical Analysis)

แนวต้านแรกอยู่ที่ 1.1562 และแนวรับแรกอยู่ที่ 1.1530
"""

EVIDENCE = {
    "snapshot": {"price": 1.15354, "percent_magnitude": 0.09},
    "levels": [{"label": "ระดับบน", "value": 1.15620}, {"label": "ระดับล่าง", "value": 1.15300}],
}


def _validate(article, **kwargs):
    kwargs.setdefault("check_completeness", False)
    return validator.validate(article, **kwargs)


class CleanArticleTests(unittest.TestCase):
    def test_clean_article_passes(self):
        result = _validate(CLEAN_ARTICLE, evidence=EVIDENCE)
        self.assertEqual(result["status"], "pass", result["findings"])
        self.assertEqual(result["fatal_count"], 0)


class SystemTermTests(unittest.TestCase):
    def test_system_word_in_body_fails(self):
        article = CLEAN_ARTICLE.replace("ราคาล่าสุดเคลื่อนไหวแถว", "ส่วนนี้เป็น unavailable ที่")
        result = _validate(article, evidence=EVIDENCE)

        self.assertEqual(result["status"], "fail")
        self.assertIn("system_term", {item["rule"] for item in result["findings"]})

    def test_machine_timestamp_in_body_fails(self):
        article = CLEAN_ARTICLE.replace("เวลา 13:30 น. (เวลาไทย)", "2026-08-03T06:33:53.081296+00:00")
        result = _validate(article, evidence=EVIDENCE)

        self.assertIn("machine_timestamp", {item["rule"] for item in result["findings"]})
        self.assertEqual(result["status"], "fail")

    def test_local_path_fails(self):
        article = CLEAN_ARTICLE + "\nดูไฟล์ที่ C:\\Users\\wcb\\article.md\n"
        result = _validate(article, evidence=EVIDENCE)

        self.assertIn("local_path", {item["rule"] for item in result["findings"]})


class VoiceDenylistTests(unittest.TestCase):
    """เทส DoD ขั้น 6: จงใจใส่คำ denylist แล้วด่านต้อง fail จริง"""

    def test_every_denylist_word_fails_individually(self):
        for term in voice_rules.VOICE_DENYLIST:
            with self.subTest(term=term):
                article = CLEAN_ARTICLE + f"\nประโยคทดสอบที่มีคำว่า {term} ปนอยู่\n"
                result = _validate(article, evidence=EVIDENCE)
                self.assertEqual(result["status"], "fail")
                self.assertIn("voice_denylist", {item["rule"] for item in result["findings"]})

    def test_latin_denylist_is_case_insensitive(self):
        article = CLEAN_ARTICLE + "\nระดับนี้มาจาก Pivot ที่คำนวณไว้\n"
        result = _validate(article, evidence=EVIDENCE)
        self.assertIn("voice_denylist", {item["rule"] for item in result["findings"]})

    def test_allowed_technical_words_do_not_trigger(self):
        # RSI, EMA, Bearish/Bullish, รีบาวด์, เสียโมเมนตัม มีใน corpus จริง — ต้องไม่โดนแบน
        article = CLEAN_ARTICLE + "\nRSI ยังชี้ Bullish (ขาขึ้น) แม้มีรีบาวด์และเสียโมเมนตัมบางช่วง\n"
        result = _validate(article, evidence=EVIDENCE)
        self.assertNotIn("voice_denylist", {item["rule"] for item in result["findings"]})


class StructureRuleTests(unittest.TestCase):
    def test_markdown_table_fails(self):
        article = CLEAN_ARTICLE + "\n| รายการ | ค่า |\n|---|---|\n| ราคา | 1.1535 |\n"
        result = _validate(article, evidence=EVIDENCE)
        self.assertIn("table_forbidden", {item["rule"] for item in result["findings"]})

    def test_extra_subheading_fails(self):
        article = CLEAN_ARTICLE + "\n## ภาพรวมตลาด\n"
        result = _validate(article, evidence=EVIDENCE)
        self.assertIn("heading_forbidden", {item["rule"] for item in result["findings"]})

    def test_second_h1_fails(self):
        article = CLEAN_ARTICLE + "\n# หัวเรื่องที่สอง\n"
        result = _validate(article, evidence=EVIDENCE)
        self.assertIn("heading_forbidden", {item["rule"] for item in result["findings"]})


class FrontmatterTests(unittest.TestCase):
    def test_internal_field_in_frontmatter_fails(self):
        article = CLEAN_ARTICLE.replace(
            "timezone: Asia/Bangkok",
            "timezone: Asia/Bangkok\npublication_clearance: hold-data-license-review",
        )
        result = _validate(article, evidence=EVIDENCE)

        self.assertEqual(result["status"], "fail")
        self.assertIn("internal_frontmatter", {item["rule"] for item in result["findings"]})

    def test_missing_contract_field_fails(self):
        article = CLEAN_ARTICLE.replace("instrument_type: forex_spot\n", "")
        result = _validate(article, evidence=EVIDENCE, instrument_type="forex_spot")

        self.assertIn("contract_field_missing", {item["rule"] for item in result["findings"]})

    def test_iso_in_frontmatter_is_warning_only(self):
        article = CLEAN_ARTICLE.replace(
            "timezone: Asia/Bangkok",
            "timezone: Asia/Bangkok\ncutoff_at: '2026-08-03T06:33:53Z'",
        )
        result = _validate(article, evidence=EVIDENCE)

        rules = {item["rule"]: item["severity"] for item in result["findings"]}
        self.assertEqual(rules.get("machine_timestamp_frontmatter"), "warning")
        self.assertEqual(result["status"], "pass")


class NumberRoundingTests(unittest.TestCase):
    """spec ข้อ 4: เลขทุกตัว = round_half_up(ค่าดิบใน evidence) — ผิดรูปหรือไม่มีที่มา = fail"""

    def test_five_decimal_forex_number_fails(self):
        # ค่าดิบตรง evidence แต่ไม่ได้ปัด 4 ตำแหน่ง = ปัดผิดกติกา
        article = CLEAN_ARTICLE.replace("1.1535", "1.15354")
        result = _validate(article, evidence=EVIDENCE)
        self.assertIn("number_rounding", {item["rule"] for item in result["findings"]})

    def test_wrongly_rounded_number_fails(self):
        # 1.15620 ปัดถูกคือ 1.1562 — เขียน 1.1563 คือแต่งเลข
        article = CLEAN_ARTICLE.replace("1.1562", "1.1563")
        result = _validate(article, evidence=EVIDENCE)

        findings = [item for item in result["findings"] if item["rule"] == "number_rounding"]
        self.assertTrue(findings)
        self.assertIn("1.1563", findings[0]["detail"])

    def test_number_missing_from_evidence_fails(self):
        article = CLEAN_ARTICLE.replace("1.1562", "1.1999")
        result = _validate(article, evidence=EVIDENCE)
        self.assertIn("number_rounding", {item["rule"] for item in result["findings"]})

    def test_percent_must_have_two_decimals(self):
        article = CLEAN_ARTICLE.replace("0.09%", "0.090%")
        result = _validate(article, evidence=EVIDENCE)
        self.assertIn("number_rounding", {item["rule"] for item in result["findings"]})

    def test_btc_prices_need_hundred_step_and_comma(self):
        article = """---
title: BTC/USD อ่อนตัวลง
symbol: BTC/USD
instrument_type: crypto_spot
timezone: Asia/Bangkok
---

ราคาเคลื่อนไหวแถว 62,600 โดยลดลงราว 1.45% จากราคาปิดวันก่อนหน้า
"""
        evidence = {"latest_close": 62561.9609375, "change_percent_magnitude": 1.4492912}
        self.assertEqual(_validate(article, evidence=evidence)["status"], "pass")

        # เลขเดียวกันแต่ไม่ปัดหลักร้อย = fail
        bad = article.replace("62,600", "62,561")
        result = _validate(bad, evidence=evidence)
        self.assertIn("number_rounding", {item["rule"] for item in result["findings"]})

    def test_rsi_integer_matches_raw_value(self):
        article = CLEAN_ARTICLE + "\nขณะที่ค่าโมเมนตัม RSI อยู่ที่ 64 ซึ่งอยู่เหนือระดับกลาง\n"
        evidence = {**EVIDENCE, "rsi14": 64.4}
        self.assertEqual(_validate(article, evidence=evidence)["status"], "pass")

        wrong = article.replace("อยู่ที่ 64", "อยู่ที่ 65")
        result = _validate(wrong, evidence=evidence)
        self.assertIn("number_rounding", {item["rule"] for item in result["findings"]})

    def test_structural_numbers_are_not_flagged(self):
        # วันที่ เวลา และ "N วัน" เป็นเลขโครงสร้าง ไม่ใช่ข้อมูลตลาด — ต้องไม่โดนตรวจ
        article = CLEAN_ARTICLE + "\nเส้นค่าเฉลี่ย 20 วัน ยังชี้ขึ้นตั้งแต่ 28 ก.ค. 2026 เวลา 09:00 น.\n"
        result = _validate(article, evidence=EVIDENCE)
        self.assertEqual(result["status"], "pass", result["findings"])

    def test_number_check_can_be_switched_off(self):
        article = CLEAN_ARTICLE.replace("1.1562", "1.1999")
        result = _validate(article, evidence=EVIDENCE, check_numbers=False)

        self.assertEqual(result["status"], "pass")


class CompletenessTests(unittest.TestCase):
    """กฎที่ใช้กับบทความเต็มฉบับ: เพดานคำ + หัวข้อเทคนิคต้องมีครั้งเดียว"""

    def test_short_article_fails_word_floor(self):
        result = validator.validate(CLEAN_ARTICLE, evidence=EVIDENCE, check_completeness=True)
        rules = {item["rule"] for item in result["findings"]}
        self.assertIn("word_count", rules)

    def test_overlong_article_fails_word_ceiling(self):
        filler = "\nประโยคยัดคำเพิ่มความยาวของบทความสำหรับการทดสอบเพดานความยาวสูงสุด" * 60
        result = validator.validate(CLEAN_ARTICLE + filler, evidence=EVIDENCE,
                                    check_completeness=True)
        self.assertIn("word_count", {item["rule"] for item in result["findings"]})

    def test_missing_technical_heading_fails(self):
        article = CLEAN_ARTICLE.replace(voice_rules.TECHNICAL_HEADING + "\n\n", "")
        result = validator.validate(article, evidence=EVIDENCE, check_completeness=True)
        self.assertIn("technical_heading", {item["rule"] for item in result["findings"]})


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

    def test_old_v3_robot_article_is_blocked_by_voice_rules(self):
        """ตัวเทียบฝั่งลบของ Voice Spec (บทความ work-c) ต้องโดนกฎใหม่ตีตก"""
        article_path = (REPO_ROOT.parent / "outputs" / "2026-08-03T13-00Z-work-c"
                        / "eurusd" / "public" / "article.md")
        if not article_path.is_file():
            self.skipTest("ไม่มีบทความตัวเทียบฝั่งลบในเครื่องนี้")
        result = validator.validate(article_path.read_text(encoding="utf-8"),
                                    check_numbers=False)

        self.assertEqual(result["status"], "fail")
        rules = {item["rule"] for item in result["findings"]}
        self.assertIn("voice_denylist", rules)
        self.assertIn("table_forbidden", rules)
        self.assertIn("heading_forbidden", rules)


if __name__ == "__main__":
    unittest.main()
