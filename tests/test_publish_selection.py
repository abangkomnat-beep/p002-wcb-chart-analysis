"""เทสชั้นเลือกใบขึ้นเว็บ — นโยบาย "วันละ 1 บท เฉพาะทองคำ" (หัวหน้าตอบ 2026-08-06)

สิ่งที่เทสชุดนี้ล็อกไว้:
- **กำลังผลิตต้องไม่ลด** — นโยบายเผยแพร่เปลี่ยน แต่หัวข้ออื่นยังต้องอยู่ในโฟลเดอร์วัน
- **โฟลเดอร์ใบขึ้นเว็บมีบทได้ใบเดียวเสมอ** เพราะปลายทางตั้งชื่อบทจากสินทรัพย์+วันที่
  ⇒ วางสองสไตล์ของวันเดียวกันแล้วไฟล์ทับกันเองโดยไม่มีอะไรฟ้อง
- **ล้างของรอบก่อนทุกครั้ง** — ใบเมื่อวานที่ค้างในโฟลเดอร์ชื่อ "ขึ้นเว็บวันนี้"
  คือกับดักที่แพงที่สุดของโฟลเดอร์แบบนี้
- **หาไฟล์ไม่เจอต้องวางใบอธิบาย ไม่ใช่โฟลเดอร์ว่าง** — โฟลเดอร์ว่างกับ "วันนี้ไม่มีบท"
  หน้าตาเหมือนกันเป๊ะ
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import publish_selection, wcb_writers  # noqa: E402


class นโยบายใบขึ้นเว็บ(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.day = Path(self.tmp.name) / "06-082026"
        self.policy = publish_selection.load_policy()
        for writer in wcb_writers.WCB_WRITERS:
            folder = self.day / writer["folder"]
            folder.mkdir(parents=True, exist_ok=True)
            for asset in ("xauusd", "eurusd", "gbpusd", "btcusd", "nvda"):
                (folder / f"{asset}.md").write_text(
                    f"บท {asset} สไตล์ {writer['id']}", encoding="utf-8")
        self.addCleanup(self.tmp.cleanup)

    def test_นโยบายที่ส่งมอบต้องเป็นทองคำวันละบทเดียว(self):
        """ค่าที่หัวหน้าสั่งมาโดยตรง — เปลี่ยนต้องผ่านผู้ใช้ ไม่ใช่แก้ไฟล์เงียบ ๆ"""
        self.assertEqual(self.policy["web_asset"], "xauusd")
        self.assertEqual(self.policy["articles_per_day"], 1)
        self.assertIn(self.policy["web_style"],
                      [writer["id"] for writer in wcb_writers.WCB_WRITERS])

    def test_วางใบเดียวและมีใบอธิบายกำกับ(self):
        result = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(result["status"], "ready")
        target = Path(result["directory"])
        articles = sorted(path.name for path in target.glob("*.md"))
        self.assertEqual(articles, sorted(["xauusd.md", publish_selection.READ_ME]))
        self.assertIn("กดแล้วขึ้นเว็บทันที",
                      (target / publish_selection.READ_ME).read_text(encoding="utf-8"))

    def test_หัวข้ออื่นต้องยังผลิตและอยู่ครบ(self):
        """นโยบายเผยแพร่ต้องไม่ลดกำลังผลิต — วันที่นโยบายเปลี่ยนกลับจะไม่มีของเทียบ"""
        publish_selection.select(self.day, policy=self.policy)
        for writer in wcb_writers.WCB_WRITERS:
            for asset in ("eurusd", "gbpusd", "btcusd", "nvda"):
                with self.subTest(style=writer["id"], asset=asset):
                    self.assertTrue((self.day / writer["folder"] / f"{asset}.md").is_file())

    def test_ล้างใบของรอบก่อนทิ้งเสมอ(self):
        first = publish_selection.select(self.day, policy=self.policy)
        stale = Path(first["directory"]) / "eurusd.md"
        stale.write_text("ใบของเมื่อวานที่หลงเหลือ", encoding="utf-8")
        publish_selection.select(self.day, policy=self.policy)
        self.assertFalse(stale.exists(), "ใบของรอบก่อนยังค้างในโฟลเดอร์ขึ้นเว็บวันนี้")

    def test_หัวข้อที่ตกด่านต้องได้ใบอธิบาย_ไม่ใช่โฟลเดอร์ว่าง(self):
        (self.day / publish_selection.style_folder(self.policy["web_style"])
         / f"{self.policy['web_asset']}.md").unlink()
        result = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(result["status"], "missing")
        note = (Path(result["directory"]) / publish_selection.READ_ME).read_text(encoding="utf-8")
        self.assertIn("ห้ามหยิบสไตล์อื่นหรือหัวข้ออื่นขึ้นแทนเอง", note)
        self.assertEqual(list(Path(result["directory"]).glob("*.md")),
                         [Path(result["directory"]) / publish_selection.READ_ME])

    def test_สไตล์ที่ไม่มีในทะเบียนต้องล้มดังๆ(self):
        """ตกไปใช้สไตล์ตั้งต้นเงียบ ๆ = วันหนึ่งบทผิดสไตล์ขึ้นเว็บโดยไม่มีใครรู้"""
        policy = dict(self.policy, web_style="ไม่มีสไตล์นี้")
        with self.assertRaises(publish_selection.SelectionUnavailable):
            publish_selection.select(self.day, policy=policy)


class เตรียมสลับไปสไตล_D(unittest.TestCase):
    """เตรียมความสามารถให้ชั้นนี้เลือกสไตล์ D ได้ (ฟีดแบ็กหัวหน้า 08-07 ข้อ จ)

    **ยังไม่ได้แก้ `config/publishing_policy.json`** — `web_style` ยังเป็น
    `a_standard` เหมือนเดิม เพราะ D ต้องผ่านตรวจรอบสองจากหัวหน้าก่อน และยัง
    ไม่ยืนยันว่าหน้าหลังบ้านนำเข้าไฟล์ที่ไม่มี frontmatter + มีรูปแนบสองใบได้
    เทสชุดนี้แค่พิสูจน์ว่า**โค้ดพร้อมสลับ**เมื่อผู้ใช้ตัดสินใจแล้ว
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.day = Path(self.tmp.name) / "07-082026"
        self.folder = self.day / publish_selection.style_folder("d_chart_story")
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / "xauusd.md").write_text(
            "# วิเคราะห์ทองคำโลก (XAU/USD) วันนี้\n\nเนื้อบท", encoding="utf-8")
        (self.folder / "xauusd-d1-structure-2026-08-07.png").write_bytes(b"png1")
        (self.folder / "xauusd-d1-levels-2026-08-07.png").write_bytes(b"png2")
        self.policy = dict(publish_selection.load_policy(), web_style="d_chart_story")
        self.addCleanup(self.tmp.cleanup)

    def test_ทะเบียนรู้จักโฟลเดอร์ของสไตล_D_โดยไม่แตะทะเบียนของ_A_B_C(self):
        self.assertEqual(publish_selection.style_folder("d_chart_story"),
                         "D-โครงสร้างกราฟ")
        self.assertNotIn("d_chart_story", [w["id"] for w in wcb_writers.WCB_WRITERS],
                         "ห้ามยัด D เข้าทะเบียนของ A/B/C — ตั้งใจแยกขาดตามคำสั่งหัวหน้า 08-06")

    def test_เลือก_D_แล้วรูปทั้งสองใบต้องถูกคัดลอกไปด้วย(self):
        result = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(result["status"], "ready")
        target = Path(result["directory"])
        self.assertTrue((target / "xauusd.md").is_file())
        self.assertTrue((target / "xauusd-d1-structure-2026-08-07.png").is_file())
        self.assertTrue((target / "xauusd-d1-levels-2026-08-07.png").is_file())
        self.assertEqual(sorted(result["images"]),
                         sorted(["xauusd-d1-structure-2026-08-07.png",
                                "xauusd-d1-levels-2026-08-07.png"]))

    def test_ใบอธิบายของ_D_ต้องเตือนว่าเป็นคนละสัญญาและยังไม่ยืนยันการนำเข้า(self):
        result = publish_selection.select(self.day, policy=self.policy)
        note = (Path(result["directory"]) / publish_selection.READ_ME).read_text(
            encoding="utf-8")
        self.assertIn("คนละสัญญากับ A/B/C", note)
        self.assertIn("ไม่มีส่วนหัว (frontmatter)", note)
        self.assertIn("ยังไม่เคยยืนยันกับทีมเว็บ", note)
        self.assertIn("xauusd-d1-structure-2026-08-07.png", note)

    def test_สไตล_A_เดิมยังไม่มีคำเตือนของ_D_ปน(self):
        """กันการรั่วไหลข้ามสไตล์ — ใบอธิบายของ A ต้องเหมือนเดิมทุกประการ"""
        note = publish_selection._ready_note(
            publish_selection.load_policy(), "A-มาตรฐาน", "xauusd", "xauusd.md")
        self.assertNotIn("คนละสัญญากับ A/B/C", note)
        self.assertIn("หมุด `[[chart:...]]`", note)


if __name__ == "__main__":
    unittest.main()
