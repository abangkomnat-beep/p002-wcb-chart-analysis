import json
import unittest
from pathlib import Path

from PIL import Image


BASES = (
    "2026-08-03_forex-eurusd",
    "2026-08-03_crypto-btcusd",
    "2026-08-03_xauusd",
)


# ชุด baseline อยู่ใน tests/fixtures/ ของรีโป ไม่ใช่ใน OUTPUT/ ของโปรเจกต์
#
# เดิมเทสอ่านผลผลิตจริงจาก <โปรเจกต์>/OUTPUT/ ซึ่งอยู่นอก git จึงไม่มีประวัติกู้คืน
# และหายทั้งชุดเมื่อ 2026-08-04 ทำให้เทสตก 19 subtests โดยกู้อะไรไม่ได้เลย
#
# ย้ายผลผลิตจริงเข้ารีโปแทนไม่ได้ เพราะรีโปนี้มีไว้ส่งมอบสู่ภายนอก แต่บทความกับ
# snapshot มีราคาจาก Raw Trading ที่สัญญาไม่ให้สิทธิ์เผยแพร่ และ git ลบย้อนหลัง
# ไม่ได้จริง จึงใช้ fixture สังเคราะห์แทน (ตัวสร้าง: fixtures/pilot-baseline/_generate.py)
#
# ⚠️ สิ่งที่เทสชุดนี้ตรวจได้/ไม่ได้หลังเปลี่ยน
#   ตรวจได้:  รูปแบบเอกสารตาม contract (หัวข้อครบและเรียงถูก · ป้าย Trigger/Target/
#             Invalidation · คำต้องห้าม · ขนาดภาพ · ความสอดคล้องของแท่งเทียน)
#   ตรวจไม่ได้แล้ว: ผลผลิตจริงของสายท่อยังตรงตาม contract อยู่ไหม
#             ⇒ ถ้าอยากได้ความมั่นใจนั้นกลับมา ต้องเพิ่มเทสที่รันสายท่อแล้วตรวจผลลัพธ์สด
OUTPUT_DIR = Path(__file__).parent / "fixtures" / "pilot-baseline"
COMPARISON_DIR = OUTPUT_DIR / "comparison-v2-rrvv"
COMPARISON_BASES = (
    "2026-08-03_rrvv-forex-eurusd",
    "2026-08-03_rrvv-crypto-btcusd",
    "2026-08-03_rrvv-xauusd",
)
CONTRACT_V2_DIR = OUTPUT_DIR / "contract-v2-pilot"
CONTRACT_V2_BASE = "2026-08-03_xauusd"
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


def frontmatter_value(article: str, key: str):
    """อ่านค่า frontmatter แบบไม่ผูกกับการจัดรูป

    เครื่องมือจัดการโน้ตภายนอกอาจ re-serialize YAML แล้วถอดเครื่องหมายคำพูดออก
    การตรวจจึงต้องดูที่ "ค่า" ไม่ใช่ตัวอักษรดิบทั้งบรรทัด
    """
    if not article.startswith("---"):
        return None
    block = article.split("---", 2)[1]
    for line in block.splitlines():
        name, separator, value = line.partition(":")
        if separator and name.strip() == key:
            return value.strip().strip("\"'")
    return None


class PilotOutputTests(unittest.TestCase):
    def test_contract_v2_pilot_has_complete_output_package_and_sections(self):
        for suffix in (".md", ".png", ".snapshot.json", ".chart.json", ".article-data.json", ".source-log.json", ".meta.json"):
            with self.subTest(suffix=suffix):
                self.assertTrue((CONTRACT_V2_DIR / f"{CONTRACT_V2_BASE}{suffix}").is_file())

        article_path = CONTRACT_V2_DIR / f"{CONTRACT_V2_BASE}.md"
        self.assertTrue(article_path.is_file())
        article = article_path.read_text(encoding="utf-8")
        self.assertNotIn("—", article)
        headings = (
            "## Market Snapshot",
            "## สรุปตลาด",
            "## ปัจจัยพื้นฐาน",
            "## วิเคราะห์ทางเทคนิค",
            "## ระดับตัดสินใจ",
            "## แนวคิดการซื้อขาย",
            "## ข่าวและสิ่งที่ต้องติดตาม",
            "## ภาพและลิงก์ประกอบ",
            "## คำเตือนความเสี่ยง",
        )
        positions = [article.index(heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))
        for label in ("Trigger", "Target", "Invalidation", "No-trade"):
            self.assertIn(label, article)

        source_log = json.loads((CONTRACT_V2_DIR / f"{CONTRACT_V2_BASE}.source-log.json").read_text(encoding="utf-8"))
        logged_fields = {entry["field"] for entry in source_log["entries"]}
        self.assertIn("quote.change", logged_fields)
        self.assertIn("quote.percent", logged_fields)
        for entry in source_log["entries"]:
            self.assertIn("value", entry)
            self.assertIn("published_at", entry)

        meta = json.loads((CONTRACT_V2_DIR / f"{CONTRACT_V2_BASE}.meta.json").read_text(encoding="utf-8"))
        self.assertIn("word_count", meta)
        self.assertLessEqual(meta["word_count"], 650)

    def test_contract_v2_forex_and_crypto_have_complete_article_packages(self):
        headings = (
            "## Market Snapshot", "## สรุปตลาด", "## ปัจจัยพื้นฐาน", "## วิเคราะห์ทางเทคนิค",
            "## ระดับตัดสินใจ", "## แนวคิดการซื้อขาย", "## ข่าวและสิ่งที่ต้องติดตาม",
            "## ภาพและลิงก์ประกอบ", "## คำเตือนความเสี่ยง",
        )
        for base in ("2026-08-03_forex-eurusd", "2026-08-03_crypto-btcusd"):
            with self.subTest(base=base):
                article = (CONTRACT_V2_DIR / f"{base}.md").read_text(encoding="utf-8")
                self.assertTrue(article.startswith("---"))
                self.assertEqual(sum(article.count(h) for h in headings), len(headings))
                for label in ("Bias", "Trigger", "Target", "Invalidation", "No-trade"):
                    self.assertIn(label, article)
                self.assertNotIn("—", article)
                meta = json.loads((CONTRACT_V2_DIR / f"{base}.meta.json").read_text(encoding="utf-8"))
                self.assertGreaterEqual(meta["word_count"], 450)
                self.assertLessEqual(meta["word_count"], 650)

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
                self.assertEqual(frontmatter_value(article, "comparison_group"), "B-rrvv")
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
                self.assertEqual(frontmatter_value(article, "byline"), "natthaphon-s")
                self.assertEqual(frontmatter_value(article, "status"), "pilot-not-for-publication")
                self.assertEqual(
                    frontmatter_value(article, "publication_clearance"), "hold-data-license-review"
                )
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
