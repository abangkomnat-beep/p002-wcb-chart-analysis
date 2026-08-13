"""ชุด regression ของมาตรฐานภาษา — เคสที่ต้องผ่านทุกครั้งที่แก้กฎ

## ทำไมเทสชุดนี้อ่านเคสจากแพ็ก ไม่ฝังเคสไว้ในโค้ด

`regression-cases.json` อยู่ในแพ็กภาษา และจะถูกเติมทุกครั้งที่ผู้ใช้อนุมัติกฎใหม่
ระหว่าง calibration ถ้าเคสฝังอยู่ในไฟล์เทส คนที่เติมกฎจะลืมเติมเทส แล้ว
"regression suite" จะค้างอยู่ที่วันแรกตลอดไป — อ่านจากแพ็กทำให้เคสใหม่ถูกคุ้มครองทันที

## กติกาที่ล็อกไว้

    แก้ baseline แล้วเคสเดิมพัง = ห้าม promote

เทสนี้คือรูปแบบที่รันได้ของประโยคนั้น
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import language_patch as patch  # noqa: E402
from tools import language_review as review  # noqa: E402
from tools.locale_loader import load_locale  # noqa: E402


class RegressionCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = load_locale("th-TH")
        cls.cases = cls.pack.regression_cases.get("cases") or []

    def test_the_suite_is_not_empty(self):
        self.assertTrue(self.cases, "แพ็กที่ไม่มีเคส regression เลย ล็อกไม่ได้")

    def test_every_case_declares_what_it_protects(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                self.assertTrue(case.get("input"))
                self.assertTrue(case.get("must_preserve") or case.get("must_avoid"),
                                "เคสที่ไม่บอกว่าคุ้มครองอะไร ใช้ตัดสินอะไรไม่ได้")

    def test_identity_rewrite_always_passes(self):
        """ข้อความเดิมเทียบกับตัวเอง ต้องไม่มีปัญหา — ถ้าฟ้องแปลว่าด่านตั้งไวเกินจนใช้งานไม่ได้"""
        for case in self.cases:
            with self.subTest(case=case["id"]):
                self.assertEqual(patch.compare_fragment(case["input"], case["input"]), [])

    def test_changing_a_protected_number_is_caught(self):
        for case in self.cases:
            numbers = (case.get("must_preserve") or {}).get("numbers") or []
            if not numbers:
                continue
            with self.subTest(case=case["id"]):
                target = numbers[0]
                mutated = case["input"].replace(target, target + "9", 1)
                self.assertNotEqual(mutated, case["input"])
                problems = patch.compare_fragment(case["input"], mutated)
                self.assertTrue(any(problem["kind"] == "number_changed" for problem in problems),
                                f"[{case['id']}] เปลี่ยนตัวเลข {target} แล้วด่านไม่จับ")

    def test_dropping_the_condition_is_caught(self):
        for case in self.cases:
            if not (case.get("must_preserve") or {}).get("conditional"):
                continue
            with self.subTest(case=case["id"]):
                mutated = case["input"].replace("หาก", "", 1)
                problems = patch.compare_fragment(case["input"], mutated)
                self.assertTrue(any(problem["kind"] == "certainty_changed" for problem in problems),
                                f"[{case['id']}] ตัดเงื่อนไขออกแล้วด่านไม่จับ")

    def test_raising_certainty_is_caught(self):
        for case in self.cases:
            level = (case.get("must_preserve") or {}).get("certainty")
            if level != "may":
                continue
            with self.subTest(case=case["id"]):
                mutated = case["input"].replace("อาจ", "", 1)
                problems = patch.compare_fragment(case["input"], mutated)
                self.assertTrue(any(problem["kind"] == "certainty_changed" for problem in problems),
                                f"[{case['id']}] ยกระดับความมั่นใจแล้วด่านไม่จับ")

    def test_forbidden_wording_cannot_be_introduced(self):
        for case in self.cases:
            for banned in case.get("must_avoid") or []:
                if banned not in patch.FORBIDDEN_TO_INTRODUCE:
                    continue
                with self.subTest(case=case["id"], banned=banned):
                    problems = patch.compare_fragment(case["input"], case["input"] + " " + banned)
                    self.assertTrue(
                        any(problem["kind"] == "forbidden_introduced" for problem in problems),
                        f"[{case['id']}] เพิ่มคำ {banned!r} เข้ามาแล้วด่านไม่จับ")

    def test_words_the_case_forbids_are_reported_by_the_reviewer(self):
        """คำที่เคสบอกว่าต้องไม่มี ถ้ามันอยู่ในข้อความ ตัวตรวจต้องเห็น"""
        for case in self.cases:
            for banned in case.get("must_avoid") or []:
                if banned not in case["input"]:
                    continue
                with self.subTest(case=case["id"], banned=banned):
                    text = f"# หัวข้อ\n\n{case['input']}\n"
                    result = review.review_text(text, self.pack, review_id=case["id"])
                    found = [item["original"] for item in result["revisions"]]
                    self.assertIn(banned, found,
                                  f"[{case['id']}] ตัวตรวจมองไม่เห็นคำที่เคสห้าม: {banned!r}")


if __name__ == "__main__":
    unittest.main()
