"""เทสกติกากลางตาม WCB Voice Spec v1 — ล็อกมาตรฐานปัดเลข นับคำ denylist และกันคัดลอก corpus

ตัวเลขตัวอย่างของกติกาปัดมาจาก spec ข้อ 4 ตรง ๆ — เทสนี้คือตัวล็อกว่า
"เปลี่ยนสูตรคือเปลี่ยนมาตรฐาน" ห้ามแก้ให้ผ่านโดยไม่กลับไปแก้ spec ก่อน
"""

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import voice_rules  # noqa: E402

# corpus อ้างอิงอยู่นอก repo (พื้นที่ทีมหลัก) — ถ้าเครื่องอื่นไม่มีให้ข้ามเทสที่ใช้
CORPUS_PATH = (REPO_ROOT.parents[2]
               / "03-RR" / "Input" / "2026-08-03_corpus-ตัวอย่างบทวิเคราะห์-4ชิ้น.md")


class RoundingRuleTests(unittest.TestCase):
    """spec ข้อ 4 — round half up ครั้งเดียวจากค่าดิบ ค่าเดียวกันทุกตำแหน่ง"""

    def test_forex_rounds_to_four_decimals(self):
        cases = {1.15274: "1.1527", 1.15467: "1.1547", 1.14848: "1.1485",
                 1.15260: "1.1526", 0.00039: "0.0004"}
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(voice_rules.format_price(raw, "forex_spot"), expected)

    def test_forex_half_up_not_bankers(self):
        # เศษ .5 ของหลักที่ 5 ต้องปัดขึ้นเสมอ ไม่ใช่ปัดเข้าคู่แบบ banker's rounding
        self.assertEqual(voice_rules.format_price(1.15265, "forex_spot"), "1.1527")
        self.assertEqual(voice_rules.format_price(1.15275, "forex_spot"), "1.1528")

    def test_btc_rounds_to_nearest_hundred_with_comma(self):
        cases = {67842.35: "67,800", 67850.0: "67,900", 115234.56: "115,200"}
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(voice_rules.format_price(raw, "crypto_spot"), expected)

    def test_gold_rounds_to_integer_dollar_with_comma(self):
        self.assertEqual(voice_rules.format_price(4088.47, "spot_metal"), "4,088")
        self.assertEqual(voice_rules.format_price(4021.5, "spot_metal"), "4,022")

    def test_percent_two_decimals(self):
        self.assertEqual(voice_rules.format_percent(0.0338), "0.03")
        self.assertEqual(voice_rules.format_percent(1.4492912), "1.45")
        self.assertEqual(voice_rules.format_percent(0.125), "0.13")

    def test_rsi_integer_half_up(self):
        self.assertEqual(voice_rules.format_int(64.4), "64")
        self.assertEqual(voice_rules.format_int(64.5), "65")


class MoveClassificationTests(unittest.TestCase):
    """spec ตาราง 2.6 — เกณฑ์เลือกกลุ่มกริยาตามขนาด |change%|"""

    def test_forex_thresholds(self):
        self.assertEqual(voice_rules.classify_move(0.10, "forex_spot"), voice_rules.MOVE_QUIET)
        self.assertEqual(voice_rules.classify_move(0.15, "forex_spot"), voice_rules.MOVE_NORMAL)
        self.assertEqual(voice_rules.classify_move(0.75, "forex_spot"), voice_rules.MOVE_NORMAL)
        self.assertEqual(voice_rules.classify_move(0.76, "forex_spot"), voice_rules.MOVE_STRONG)

    def test_crypto_thresholds(self):
        self.assertEqual(voice_rules.classify_move(0.9, "crypto_spot"), voice_rules.MOVE_QUIET)
        self.assertEqual(voice_rules.classify_move(2.0, "crypto_spot"), voice_rules.MOVE_NORMAL)
        self.assertEqual(voice_rules.classify_move(3.5, "crypto_spot"), voice_rules.MOVE_STRONG)

    def test_no_previous_close_means_unknown(self):
        self.assertEqual(voice_rules.classify_move(None, "forex_spot"), voice_rules.MOVE_UNKNOWN)


class DenylistTests(unittest.TestCase):
    def test_covers_all_twenty_spec_entries(self):
        # spec ข้อ 3 มี 20 รายการ (ข้อ 19 มีสองรูป จึงมี 21 pattern)
        self.assertEqual(len(voice_rules.VOICE_DENYLIST), 21)
        for term in ("ฉากทัศน์", "ระดับตัดสินใจ", "pivot", "sma", "atr", "swing",
                     "session", "กำลังก่อตัว", "หลักฐาน", "ตรวจสอบได้", "แหล่งที่มา"):
            with self.subTest(term=term):
                self.assertIn(term, voice_rules.VOICE_DENYLIST)

    def test_latin_terms_are_stored_lowercase(self):
        for term in voice_rules.VOICE_DENYLIST:
            with self.subTest(term=term):
                self.assertEqual(term, term.lower())


class WordCounterTests(unittest.TestCase):
    """นิยามตัวนับถูกล็อกที่นี่ — token ละติน/ตัวเลขนับตรง คำไทย = อักขระ/4.5 ปัดครึ่งขึ้น"""

    def test_ratio_is_locked(self):
        self.assertEqual(voice_rules.THAI_CHARS_PER_WORD, 4.5)
        self.assertEqual((voice_rules.WORD_MIN, voice_rules.WORD_MAX), (250, 450))

    def test_latin_and_number_tokens_count_one_each(self):
        # EUR กับ USD เป็นคนละ token (คั่นด้วย /) + RSI + เลข 3 ก้อน = 6 คำ
        self.assertEqual(voice_rules.count_public_words("EUR/USD RSI 1.1547 0.03% 67,800"), 6)

    def test_thai_run_is_estimated_from_characters(self):
        # "ราคาทองคำ" = 9 อักขระ / 4.5 = 2 คำ
        self.assertEqual(voice_rules.count_public_words("ราคาทองคำ"), 2)
        # 9 + 5 อักขระ ("แนวรับ" 6 + ... ) — ล็อกด้วยค่าคงที่ที่คำนวณมือ
        self.assertEqual(voice_rules.count_public_words("แนวรับสำคัญ"), 2)  # 11/4.5 = 2.44 -> 2

    def test_frontmatter_and_image_lines_are_ignored(self):
        text = "---\ntitle: อะไรก็ได้ยาวมาก\n---\n\nราคาทองคำ\n![คำอธิบายภาพยาวมาก](x.png)\n"
        self.assertEqual(voice_rules.count_public_words(text), 2)


class CorpusOverlapTests(unittest.TestCase):
    def test_planted_overlap_is_detected(self):
        corpus = "ราคาทองคำวันนี้ปรับตัวขึ้นอย่างต่อเนื่องหลังตลาดเปิดทำการในช่วงเช้าที่ผ่านมา และมีแรงซื้อหนาแน่น"
        article = "บทนำอื่น ๆ " + corpus[:60] + " ตอนท้ายที่แต่งเอง"
        self.assertIsNotNone(voice_rules.find_corpus_overlap(article, corpus))

    def test_short_common_phrases_do_not_trigger(self):
        corpus = "ทองโลกเปิดตลาดที่ระดับ 4,001 ดอลลาร์ ฉุดราคาทองแท่งในประเทศ"
        article = "วันนี้ EUR/USD เปิดตลาดที่ระดับ 1.1546 ดอลลาร์ต่อยูโร ก่อนเผชิญแรงเทขาย"
        self.assertIsNone(voice_rules.find_corpus_overlap(article, corpus))

    def test_technical_heading_is_exempt(self):
        heading = voice_rules.TECHNICAL_HEADING
        padded = f"ข้อความนำหน้า {heading} ข้อความตามหลัง"
        self.assertIsNone(voice_rules.find_corpus_overlap(padded, padded[:len(padded) // 1]))


class StructuralNumberTests(unittest.TestCase):
    def test_times_dates_and_day_counts_are_stripped(self):
        line = "ข้อมูล ณ 3 ส.ค. 2026 เวลา 17:09 น. เส้นค่าเฉลี่ย 20 วัน ราคา 1.1547"
        stripped = voice_rules.strip_structural_numbers(line)
        self.assertNotIn("17:09", stripped)
        self.assertNotIn("2026", stripped)
        self.assertNotIn("20 วัน", stripped)
        self.assertIn("1.1547", stripped)
        # ต้องแทนด้วยช่องว่างยาวเท่าเดิม เพื่อรักษาตำแหน่งอักขระของเลขที่เหลือ
        self.assertEqual(len(stripped), len(line))


class CorpusCalibrationTests(unittest.TestCase):
    """สอบเทียบตัวนับกับ corpus จริง — สเกลของ corpus คือ ~250-450 คำต่อชิ้น"""

    def test_corpus_pieces_land_on_the_expected_scale(self):
        if not CORPUS_PATH.is_file():
            self.skipTest("ไม่มีไฟล์ corpus ในเครื่องนี้")
        text = CORPUS_PATH.read_text(encoding="utf-8").split("## ลักษณะร่วม")[0]
        pieces = text.split("## ชิ้นที่")[1:]
        self.assertEqual(len(pieces), 4)
        for index, piece in enumerate(pieces, start=1):
            lines = [line for line in piece.splitlines()
                     if not line.startswith(("**โครงที่สังเกต", "---", "#", ">"))]
            body = "\n".join(lines[1:])
            words = voice_rules.count_public_words(body)
            with self.subTest(piece=index, words=words):
                self.assertGreaterEqual(words, 250)
                self.assertLessEqual(words, 500)  # ชิ้น 2 เป็นชิ้นเปิดยาวสุดของ corpus


if __name__ == "__main__":
    unittest.main()
