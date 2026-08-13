"""ด่านตรวจภาษาเชิงกล และชุดอนุมัติประจำวัน

สองอย่างที่เทสชุดนี้เฝ้า:
1. **ตัวตรวจต้องไม่ขัดกับด่านที่มีอยู่แล้ว** — บทที่ผ่าน `public_copy_validator` แล้ว
   ต้องไม่ถูกด่านภาษาฟ้องระดับ block (ไม่งั้นมีสองด่านที่ตัดสินคนละอย่างกับบทเดียวกัน)
2. **จังหวะถามผู้ใช้** — มติผู้ใช้ 2026-08-13 คือถามเป็นชุดวันละครั้ง ห้ามถามทีละข้อ
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import language_review as review  # noqa: E402
from tools import public_copy_validator as validator  # noqa: E402
from tools.locale_loader import load_locale  # noqa: E402

ARTICLE = """---
title: 'XAU/USD ทดสอบแนวต้าน'
symbol: XAU/USD
---

# XAU/USD ทดสอบแนวต้าน

ราคาล่าสุดอยู่ที่ 3,410 ดอลลาร์ หากราคายืนเหนือ 3,400 ได้ จะเปิดทางไปแนวต้านถัดไป

การนับหัวของสัญญาณรายวันยังเอนไปฝั่งซื้อ
"""


class ReviewBasicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = load_locale("th-TH")

    def test_line_numbers_point_at_the_real_file_line(self):
        """เลขบรรทัดต้องนับจากไฟล์จริง ไม่ใช่จากเนื้อที่ตัด frontmatter แล้ว — patch อาศัยเลขนี้"""
        result = review.review_text(ARTICLE, self.pack, review_id="T-001")
        lines = ARTICLE.splitlines()
        for item in result["revisions"]:
            self.assertIn(item["original"], lines[item["line"] - 1],
                          f"[{item['id']}] ข้อความเดิมไม่อยู่ที่บรรทัด {item['line']}")

    def test_glossary_avoid_word_is_caught_with_a_replacement(self):
        result = review.review_text(ARTICLE, self.pack, review_id="T-002")
        hits = [item for item in result["revisions"] if item["original"] == "การนับหัว"]
        self.assertTrue(hits, "คำที่แพ็กสั่งเลี่ยงต้องถูกจับ")
        self.assertEqual(hits[0]["proposed"], "จำนวนสัญญาณ")
        self.assertTrue(hits[0]["auto_applicable"])

    def test_findings_bind_to_both_hashes(self):
        result = review.review_text(ARTICLE, self.pack, review_id="T-003")
        self.assertEqual(result["source_sha256"], review.sha256_text(ARTICLE))
        self.assertEqual(result["baseline_sha256"], self.pack.sha256)

    def test_ids_are_sequential_and_sorted_by_severity(self):
        result = review.review_text(ARTICLE, self.pack, review_id="T-004")
        self.assertEqual([item["id"] for item in result["revisions"]],
                         [f"L-{n:03d}" for n in range(1, len(result["revisions"]) + 1)])
        severities = [review.SEVERITY_ORDER[item["severity"]] for item in result["revisions"]]
        self.assertEqual(severities, sorted(severities))

    def test_horizontal_rule_does_not_crash_the_word_counter(self):
        """`count_public_words` รับทั้งเอกสาร — ส่งเส้นคั่น `---` เดี่ยว ๆ เข้าไปเคยทำให้พังจริง"""
        text = ARTICLE + "\n---\n\nปิดท้ายด้วยย่อหน้าสั้น\n"
        result = review.review_text(text, self.pack, review_id="T-005")
        self.assertIsInstance(result["revisions"], list)

    def test_headings_and_images_are_not_reviewed(self):
        text = "# หัวข้อที่มีการนับหัวอยู่ในนั้น\n\n![alt ที่มีการนับหัว](x.png)\n"
        result = review.review_text(text, self.pack, review_id="T-006")
        self.assertEqual(result["revisions"], [])

    def test_inherited_denylist_exception_is_not_flagged(self):
        """มติผู้ใช้ 08-13: "ตรวจสอบได้" เป็นภาษาไทยปกติของบท A–G — ไม่ยกมาจากทะเบียนเดิม

        แต่วลีเต็ม "เป้าหมายที่ตรวจสอบได้" (ศัพท์ระบบของสาย ①②③) ยังต้องถูกจับ
        """
        text = "# ท\n\nสิ่งที่ตรวจสอบได้จริงคือปฏิทินเศรษฐกิจ\n"
        result = review.review_text(text, self.pack, review_id="T-007")
        self.assertEqual([item["original"] for item in result["revisions"]], [])

        text = "# ท\n\nนี่คือเป้าหมายที่ตรวจสอบได้ของแผน\n"
        result = review.review_text(text, self.pack, review_id="T-008")
        self.assertIn("เป้าหมายที่ตรวจสอบได้",
                      [item["original"] for item in result["revisions"]])

    def test_parallel_list_structure_is_not_redundancy(self):
        """มติผู้ใช้ 08-13: รายการ bullet ใช้โครงขนานโดยตั้งใจ (ปฏิทิน/ป้ายแผน) — ไม่ใช่ความซ้ำ"""
        bullet = ("- **21:00 น.** ยอดขายบ้านมือสอง ซึ่งจัดเป็นรายการผลกระทบสูงประจำรอบ\n"
                  "- **21:30 น.** สต็อกน้ำมันดิบ ซึ่งจัดเป็นรายการผลกระทบสูงประจำรอบ\n")
        result = review.review_text("# ท\n\n" + bullet, self.pack, review_id="T-009")
        self.assertFalse([item for item in result["revisions"]
                          if item["category"] == "redundancy"])

        prose = ("ประโยคแรกกล่าวว่าราคายังคงยืนเหนือเส้นค่าเฉลี่ยสำคัญของรอบนี้ได้ต่อเนื่อง "
                 "และย่อหน้าเดิมย้ำอีกครั้งว่าราคายังคงยืนเหนือเส้นค่าเฉลี่ยสำคัญของรอบนี้ได้")
        result = review.review_text("# ท\n\n" + prose + "\n", self.pack, review_id="T-010")
        self.assertTrue([item for item in result["revisions"]
                         if item["category"] == "redundancy"],
                        "ความซ้ำในร้อยแก้วจริงยังต้องถูกจับ")

    def test_latin_avoid_term_needs_word_boundary(self):
        """เจอจริงกับบทสไตล์ D 08-13: 'sma' จับกลางคำ 'Smart Money' — ห้ามเกิดซ้ำ

        ขอบเขตคำวัดด้วยตัวอักษรละตินเท่านั้น: 'SMA20' (เลขต่อท้าย) ยังต้องถูกจับ
        เพราะเป็นรูปใช้งานจริงของศัพท์ระบบ
        """
        smart = "จุดเข้าซื้อที่ได้เปรียบตามแนวคิด Smart Money รอราคากลับมาหาโซนเดิม\n"
        result = review.review_text("# ท\n\n" + smart, self.pack, review_id="T-011")
        self.assertFalse([item for item in result["revisions"]
                          if item["rule_id"] == "avoid:sma"],
                         "'Smart Money' ต้องไม่ถูกจับด้วยกฎ sma")

        sma20 = "ราคายืนเหนือเส้น SMA20 ได้ต่อเนื่องตลอดสัปดาห์\n"
        result = review.review_text("# ท\n\n" + sma20, self.pack, review_id="T-012")
        self.assertTrue([item for item in result["revisions"]
                         if item["rule_id"] == "avoid:sma"],
                        "'SMA20' ยังต้องถูกจับ (เลขต่อท้ายไม่ใช่ขอบเขตคำ)")


class NoConflictWithExistingGateTests(unittest.TestCase):
    """ด่านภาษาห้ามฟ้อง block กับบทที่ระบบยอมรับแล้ว

    มีสองกลุ่มที่ต้องไม่ขัดกัน และเป็นคนละด่านกัน:

    * สาย ①②③ (เก่า) — ด่านคือ `public_copy_validator` ซึ่งบังคับ `VOICE_DENYLIST`
    * สาย A–G (ที่ใช้จริง) — ด่านคือ `wcb_copy_validator` ซึ่ง **ไม่บังคับ** ทะเบียนนั้น
      ⇒ บทที่ขึ้นเว็บจริงมี `SMA`/`ฉากทัศน์` อยู่ ถ้าด่านภาษาตั้งคำเหล่านี้เป็น block
      มันจะฟ้องของที่เผยแพร่อยู่ทุกวัน (เจอจริง 2026-08-13 ตอนเริ่ม calibration)

    `wcb_copy_validator` ต้องใช้ snapshot ที่ไม่ได้เก็บคู่กับบท จึงรันย้อนหลังไม่ได้ —
    กลุ่มที่สองจึงตรวจด้วยเงื่อนไขที่ตรงกว่า: **บทที่ขึ้นเว็บจริง ต้องไม่มี block เลย**
    """

    @classmethod
    def setUpClass(cls):
        cls.pack = load_locale("th-TH")
        cls.corpus = Path(__file__).resolve().parents[2] / "output"
        cls.articles = []
        if cls.corpus.is_dir():
            for path in sorted(cls.corpus.rglob("*.md")):
                try:
                    text = path.read_text(encoding="utf-8")
                    verdict = validator.validate(text, check_numbers=False,
                                                 check_completeness=False)
                except Exception:  # ไฟล์ที่ไม่ใช่บท — ข้าม
                    continue
                if verdict.get("status") == "pass":
                    cls.articles.append((path, text))

    def test_clean_articles_get_no_block_level_finding(self):
        if not self.articles:
            self.skipTest("เครื่องนี้ไม่มีคลังบทใน output/ — เทียบด่านสองชั้นไม่ได้")
        for path, text in self.articles:
            with self.subTest(article=path.name):
                result = review.review_text(text, self.pack, review_id="X")
                blocking = [item for item in result["revisions"] if item["severity"] == "block"]
                self.assertFalse(
                    blocking,
                    f"{path} ผ่านด่านเดิมแล้วแต่ด่านภาษาฟ้อง block: "
                    f"{[item['original'] for item in blocking]}")

    def test_articles_that_actually_went_live_get_no_block_level_finding(self):
        published = sorted(self.corpus.glob("*/0-ขึ้นเว็บวันนี้/*.md")) \
            if self.corpus.is_dir() else []
        published = [path for path in published if path.stem != "อ่านก่อน"]
        if not published:
            self.skipTest("เครื่องนี้ไม่มีโฟลเดอร์บทที่ขึ้นเว็บ")
        for path in published:
            with self.subTest(article=f"{path.parent.parent.name}/{path.name}"):
                result = review.review_text(path.read_text(encoding="utf-8"), self.pack,
                                            review_id="LIVE")
                blocking = [item for item in result["revisions"] if item["severity"] == "block"]
                self.assertFalse(
                    blocking,
                    f"{path} ขึ้นเว็บไปแล้วแต่ด่านภาษาฟ้อง block: "
                    f"{[item['original'] for item in blocking]} — "
                    "ด่านภาษาเสนอได้ แต่ตัดสินแทนผู้ใช้เรื่องถ้อยคำที่เผยแพร่แล้วไม่ได้")


class DailyBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = load_locale("th-TH")

    def _batch(self):
        first = review.review_text(ARTICLE, self.pack, review_id="A", source_path="a/xauusd.md")
        second = review.review_text(ARTICLE.replace("XAU/USD", "BTC/USD"), self.pack,
                                    review_id="B", source_path="a/btcusd.md")
        return review.bundle_daily([first, second], batch_id="B-20260813", date="2026-08-13")

    def test_one_batch_carries_every_article_of_the_day(self):
        batch = self._batch()
        self.assertEqual(batch["batching"], "daily_batch")
        self.assertEqual(batch["summary"]["articles"], 2)
        self.assertEqual(batch["summary"]["revisions"],
                         sum(len(item["revisions"]) for item in batch["reviews"]))

    def test_rendered_batch_offers_group_answers_not_one_by_one(self):
        text = review.render_batch(self._batch())
        for phrase in ("อนุมัติทั้งหมด", "ยกเว้น", "ปฏิเสธทั้งหมด"):
            self.assertIn(phrase, text)
        self.assertIn("ไม่ block การผลิต", text,
                      "ต้องบอกชัดว่าวันที่ผู้ใช้ไม่ตอบ บทยังเดินต่อได้")

    def test_batch_ids_are_prefixed_per_article_so_they_do_not_collide(self):
        text = review.render_batch(self._batch())
        self.assertIn("[xauusd/L-001]", text)
        self.assertIn("[btcusd/L-001]", text)


if __name__ == "__main__":
    unittest.main()
