import json
import unittest
from pathlib import Path

from PIL import Image


OUTPUT_DIR = Path(__file__).parents[2] / "OUTPUT"
BASES = (
    "2026-08-03_forex-eurusd",
    "2026-08-03_crypto-btcusd",
    "2026-08-03_xauusd",
)
COMPARISON_DIR = OUTPUT_DIR / "comparison-v2-rrvv"
COMPARISON_BASES = (
    "2026-08-03_rrvv-forex-eurusd",
    "2026-08-03_rrvv-crypto-btcusd",
    "2026-08-03_rrvv-xauusd",
)
BLACKLIST = (
    "การันตี",
    "ขึ้นแน่",
    "ซื้อเลย",
    "ห้ามพลาด",
    "พูดง่าย",
    "ตามที่ได้กล่าวไปข้างต้น",
    "ในบทความนี้เราจะ",
    "—",
)


class PilotOutputTests(unittest.TestCase):
    def test_rrvv_comparison_articles_follow_decision_product_contract(self):
        required_labels = ("**Bias:**", "**Action:**", "**Trigger:**", "**Invalidation:**", "**Next event:**")
        required_sections = (
            "## กราฟบอกอะไร",
            "## แผนขึ้น แผนลง และแผนพัก",
            "## ข่าวและสิ่งที่ต้องติดตาม",
            "## กรอบตัดสินใจวันนี้",
        )
        for basename in COMPARISON_BASES:
            with self.subTest(basename=basename):
                article_path = COMPARISON_DIR / f"{basename}.md"
                image_path = COMPARISON_DIR / f"{basename}.png"
                self.assertTrue(article_path.is_file())
                self.assertTrue(image_path.is_file())
                article = article_path.read_text(encoding="utf-8")
                self.assertIn('comparison_group: "B-rrvv"', article)
                self.assertIn(f"]({basename}.png)", article)
                for label in required_labels:
                    self.assertIn(label, article)
                for section in required_sections:
                    self.assertIn(section, article)
                news_body = article.split("## ข่าวและสิ่งที่ต้องติดตาม", 1)[1].split("## ", 1)[0]
                self.assertIn("ยังไม่มีข่าวอัปเดต", news_body)
                self.assertLessEqual(len(news_body.split()), 20)
                for phrase in BLACKLIST:
                    self.assertNotIn(phrase, article)

    def test_articles_have_matching_charts_and_required_voice_contract(self):
        for basename in BASES:
            with self.subTest(basename=basename):
                article_path = OUTPUT_DIR / f"{basename}.md"
                image_path = OUTPUT_DIR / f"{basename}.png"
                snapshot_path = OUTPUT_DIR / f"{basename}.snapshot.json"

                self.assertTrue(article_path.is_file())
                self.assertTrue(image_path.is_file())
                self.assertTrue(snapshot_path.is_file())

                article = article_path.read_text(encoding="utf-8")
                self.assertIn('byline: "natthaphon-s"', article)
                self.assertIn('status: "pilot-not-for-publication"', article)
                self.assertIn('publication_clearance: "hold-data-license-review"', article)
                self.assertIn(f"]({basename}.png)", article)
                self.assertEqual(article.count("\n## "), 3)
                for phrase in BLACKLIST:
                    self.assertNotIn(phrase, article)

                with Image.open(image_path) as image:
                    self.assertEqual(image.format, "PNG")
                    self.assertEqual(image.size, (1440, 1080))

    def test_snapshot_candles_are_internally_valid(self):
        for basename in BASES:
            with self.subTest(basename=basename):
                payload = json.loads(
                    (OUTPUT_DIR / f"{basename}.snapshot.json").read_text(encoding="utf-8")
                )
                for row in payload["rows"]:
                    self.assertLessEqual(row["low"], min(row["open"], row["close"]))
                    self.assertGreaterEqual(row["high"], max(row["open"], row["close"]))


if __name__ == "__main__":
    unittest.main()
