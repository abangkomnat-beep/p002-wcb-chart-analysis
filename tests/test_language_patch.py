"""แก้ภาษาแบบเจาะจุด และด่านตรวจว่าความหมายไม่เปลี่ยน

กฎที่เทสชุดนี้ล็อกไว้: **อนุมัติ 3 จุด = แก้ 3 จุด** ไม่ใช่เขียนบทใหม่ทั้งใบ
และของที่ห้ามเปลี่ยน (ตัวเลข ความมั่นใจ เงื่อนไข ทิศ) ต้องถูกจับได้ก่อนเขียนไฟล์
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import language_patch as patch  # noqa: E402
from tools import language_review as review  # noqa: E402
from tools.locale_loader import load_locale  # noqa: E402

ARTICLE = """---
title: 'ทดสอบ'
---

# ทดสอบ

ราคาล่าสุดอยู่ที่ 3,410 ดอลลาร์ หากราคายืนเหนือ 3,400 ได้ จะเปิดทางไปแนวต้านถัดไป

การนับหัวของสัญญาณรายวันยังเอนไปฝั่งซื้อ
"""


def _review_of(text: str, pack) -> dict:
    return review.review_text(text, pack, review_id="T", source_path="t/article.md")


class SurgicalApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = load_locale("th-TH")

    def setUp(self):
        self.review = _review_of(ARTICLE, self.pack)
        self.target = next(item for item in self.review["revisions"]
                           if item["original"] == "การนับหัว")

    def test_only_the_approved_span_changes(self):
        result = patch.apply_approved(ARTICLE, self.review, [self.target["id"]])
        self.assertTrue(result["ok"])
        self.assertIn("จำนวนสัญญาณของสัญญาณรายวัน", result["text"])

        before, after = ARTICLE.splitlines(), result["text"].splitlines()
        self.assertEqual(len(before), len(after))
        changed = [index for index, (old, new) in enumerate(zip(before, after)) if old != new]
        self.assertEqual(changed, [self.target["line"] - 1],
                         "ต้องเปลี่ยนบรรทัดเดียวคือบรรทัดที่อนุมัติ")

    def test_approving_nothing_changes_nothing(self):
        result = patch.apply_approved(ARTICLE, self.review, [])
        self.assertEqual(result["text"], ARTICLE)
        self.assertEqual(result["diff"], "")

    def test_revision_without_replacement_is_skipped_not_guessed(self):
        """ข้อที่เครื่องเสนอคำแทนไม่ได้ (เช่น "ย่อหน้ายาวไป") ต้องถูกข้าม ไม่ใช่เดาคำมาใส่

        สร้างเคสตรง ๆ แทนการรอให้บททดสอบบังเอิญมีข้อแบบนี้ — ไม่งั้นเทสจะกลายเป็น skip
        เงียบ ๆ วันที่เนื้อบทเปลี่ยน ซึ่งคือ "เทสตาย" ที่กติกาของโปรเจกต์ห้ามไว้
        """
        judgement_only = {
            **self.review,
            "revisions": [{
                "id": "L-900", "category": "sentence_density", "severity": "warning",
                "line": self.target["line"], "original": "การนับหัว", "proposed": None,
                "reason": "ต้องใช้วิจารณญาณ", "rule_id": "paragraph_density",
                "auto_applicable": False,
            }],
        }
        result = patch.apply_approved(ARTICLE, judgement_only, ["L-900"], strict=False)
        self.assertEqual(result["text"], ARTICLE, "ไม่มีคำแทน = ห้ามแตะไฟล์")
        self.assertEqual(result["skipped"][0]["id"], "L-900")
        self.assertEqual(result["applied"], [])

    def test_stale_source_is_refused(self):
        with self.assertRaises(patch.StaleReviewError) as ctx:
            patch.apply_approved(ARTICLE + "\nย่อหน้าที่เพิ่มมาทีหลัง\n",
                                 self.review, [self.target["id"]])
        self.assertEqual(ctx.exception.code, "STALE_REVIEW")

    def test_stale_baseline_is_refused(self):
        with self.assertRaises(patch.StaleReviewError):
            patch.apply_approved(ARTICLE, self.review, [self.target["id"]],
                                 pack_sha256="0" * 64)

    def test_moved_anchor_stops_instead_of_patching_the_wrong_place(self):
        broken = dict(self.review)
        broken["revisions"] = [dict(item) for item in self.review["revisions"]]
        for item in broken["revisions"]:
            if item["id"] == self.target["id"]:
                item["original"] = "ข้อความที่ไม่มีอยู่จริงในบรรทัดนี้"
        with self.assertRaises(patch.PatchAnchorError) as ctx:
            patch.apply_approved(ARTICLE, broken, [self.target["id"]])
        self.assertEqual(ctx.exception.code, "PATCH_ANCHOR_LOST")

    def test_unknown_revision_id_is_refused(self):
        with self.assertRaises(patch.PatchError):
            patch.apply_approved(ARTICLE, self.review, ["L-999"])

    def test_multiple_edits_on_different_lines_keep_their_anchors(self):
        """แก้จากบรรทัดท้ายขึ้นหน้า เพื่อไม่ให้การแก้บรรทัดหลังทำให้ anchor ของบรรทัดก่อนเลื่อน"""
        text = "# หัว\n\nการนับหัวรอบเช้า\n\nการนับหัวรอบบ่าย\n"
        made = _review_of(text, self.pack)
        ids = [item["id"] for item in made["revisions"] if item["original"] == "การนับหัว"]
        self.assertEqual(len(ids), 2)
        result = patch.apply_approved(text, made, ids)
        self.assertNotIn("การนับหัว", result["text"])
        self.assertEqual(result["text"].count("จำนวนสัญญาณ"), 2)


class ProtectedContentTests(unittest.TestCase):
    def test_number_change_is_caught(self):
        self.assertTrue(patch.compare_fragment("แนวต้านที่ 3,400", "แนวต้านที่ 3,500"))
        self.assertFalse(patch.compare_fragment("แนวต้านที่ 3,400", "ระดับ 3,400 เป็นแนวต้าน"))

    def test_dropping_a_condition_is_caught(self):
        problems = patch.compare_fragment("หากราคายืนเหนือ 3,400 จะเปิดทางขึ้น",
                                          "ราคายืนเหนือ 3,400 เปิดทางขึ้น")
        self.assertTrue(any(problem["kind"] == "certainty_changed" for problem in problems))

    def test_raising_certainty_is_caught(self):
        problems = patch.compare_fragment("ราคาอาจแกว่งในกรอบเดิม", "ราคาแกว่งในกรอบเดิม")
        self.assertTrue(any(problem["kind"] == "certainty_changed" for problem in problems))

    def test_longest_marker_wins_so_words_are_not_double_counted(self):
        """"อาจจะ" ต้องนับเป็นคำเดียว ไม่ใช่ "อาจ" ซ้อน "จะ" — ไม่งั้นด่านจะฟ้องผิด"""
        counted = patch.certainty_of("ราคาอาจจะปรับขึ้น")
        self.assertEqual(sum(counted.values()), 1)
        self.assertIn("possibility:อาจจะ", counted)

    def test_direction_word_cannot_disappear(self):
        problems = patch.compare_fragment("สัญญาณเอนไปฝั่งซื้อ", "สัญญาณเอนไปทางนั้น")
        self.assertTrue(any(problem["kind"] == "direction_lost" for problem in problems))

    def test_rewording_that_keeps_direction_is_allowed(self):
        self.assertFalse(patch.compare_fragment("สัญญาณเอนไปฝั่งซื้อ",
                                                "น้ำหนักอยู่ทางฝั่งซื้อ"))

    def test_trade_instruction_cannot_be_introduced(self):
        problems = patch.compare_fragment("เป็นระดับที่ควรจับตา", "เป็นระดับที่ควรซื้อ")
        self.assertTrue(any(problem["kind"] == "forbidden_introduced" for problem in problems))

    def test_document_level_number_net_catches_what_the_span_check_misses(self):
        report = patch.integrity_report("ราคา 3,400 และ 3,500", "ราคา 3,400 และ 3,600")
        self.assertFalse(report["ok"])
        self.assertEqual(report["problems"][0]["kind"], "document_numbers_changed")


class ApprovalParsingTests(unittest.TestCase):
    """รูปแบบคำตอบที่ผู้ใช้ใช้จริงในชุดประจำวัน"""

    @classmethod
    def setUpClass(cls):
        cls.review = _review_of(ARTICLE, load_locale("th-TH"))
        cls.all_ids = [item["id"] for item in cls.review["revisions"]]

    def test_approve_all(self):
        self.assertEqual(patch._parse_approval("all", self.review), self.all_ids)
        self.assertEqual(patch._parse_approval("ทั้งหมด", self.review), self.all_ids)

    def test_reject_all(self):
        self.assertEqual(patch._parse_approval("none", self.review), [])
        self.assertEqual(patch._parse_approval("ปฏิเสธทั้งหมด", self.review), [])

    def test_approve_all_except(self):
        self.assertEqual(patch._parse_approval("except:L-001", self.review),
                         [rid for rid in self.all_ids if rid != "L-001"])

    def test_approve_specific(self):
        self.assertEqual(patch._parse_approval("L-001, L-002", self.review), ["L-001", "L-002"])


if __name__ == "__main__":
    unittest.main()
