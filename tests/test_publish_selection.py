"""เทสชั้นเลือกใบขึ้นเว็บ — นโยบาย "วันละ 1 บท เฉพาะทองคำ" (หัวหน้าตอบ 2026-08-06)

สิ่งที่เทสชุดนี้ล็อกไว้:
- **กำลังผลิตต้องไม่ลด** — นโยบายเผยแพร่เปลี่ยน แต่หัวข้ออื่นยังต้องอยู่ในโฟลเดอร์วัน
- **Lane หลักมีบทได้ใบเดียวเสมอ** เพราะปลายทางตั้งชื่อบทจากสินทรัพย์+วันที่
  ⇒ วางสองสไตล์ของวันเดียวกันแล้วไฟล์ทับกันเองโดยไม่มีอะไรฟ้อง
- **ล้างของรอบก่อนเฉพาะ Lane หลัก** — ใบเมื่อวานที่ค้างใน Lane
  คือกับดักที่แพงที่สุดของโฟลเดอร์แบบนี้
- **ห้ามสร้างไฟล์คำแนะนำในโฟลเดอร์ขึ้นเว็บ** — ปลายทางมีเฉพาะบทและภาพที่ต้องอัป
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
        self.day = Path(self.tmp.name) / "06-08-2026"
        current = publish_selection.load_policy()
        # ชุดนี้ล็อก backward compatibility ของ selector schema v1 โดยเฉพาะ
        self.policy = {
            "schema_version": 1,
            "web_asset": current["web_asset"],
            "web_style": current["web_style"],
            "articles_per_day": 1,
            # This schema-v1 fixture deliberately exercises legacy copy mode;
            # production v2 now uses country_references with null fields.
            "selection_folder": current["selection_folder"] or "0-ขึ้นเว็บวันนี้",
            "selection_lane": current["selection_lane"] or "01-Primary-Selection",
            "web_chart_mode": current["web_chart_mode"],
        }
        for writer in wcb_writers.WCB_WRITERS:
            folder = self.day / writer["folder"]
            folder.mkdir(parents=True, exist_ok=True)
            for asset in ("xauusd", "eurusd", "gbpusd", "btcusd", "nvda"):
                (folder / f"{asset}.md").write_text(
                    f"บท {asset} สไตล์ {writer['id']}", encoding="utf-8")
        # สไตล์ D อยู่นอกทะเบียน `WCB_WRITERS` โดยเจตนา — ต้องปูโฟลเดอร์เองแยก
        # (จำเป็นตั้งแต่ 08-14 ที่ผู้ใช้สั่งให้ D เป็นบทหลัก · ก่อนหน้านี้ setUp
        # ปูแค่ A/B/C แล้วเทสยังผ่านเพราะนโยบายชี้ A)
        d_folder = self.day / publish_selection.style_folder("d_chart_story")
        d_folder.mkdir(parents=True, exist_ok=True)
        for asset in ("xauusd", "eurusd", "gbpusd", "btcusd", "nvda"):
            (d_folder / f"{asset}.md").write_text(
                f"# บท {asset} สไตล์ D", encoding="utf-8")
        self.addCleanup(self.tmp.cleanup)

    def test_นโยบายที่ส่งมอบต้องเป็นทองคำวันละบทเดียว(self):
        """ค่าที่หัวหน้าสั่งมาโดยตรง — เปลี่ยนต้องผ่านผู้ใช้ ไม่ใช่แก้ไฟล์เงียบ ๆ

        `web_style` เป็น `d_chart_story` ตั้งแต่ 2026-08-14 (ผู้ใช้สั่งให้ D แทน A)
        ⇒ เช็คว่าอยู่ใน**ทะเบียนที่ระบบรู้จัก** ไม่ใช่เฉพาะทะเบียนของ A/B/C
        """
        self.assertEqual(self.policy["web_asset"], "xauusd")
        self.assertEqual(self.policy["articles_per_day"], 1)
        self.assertTrue(publish_selection.style_folder(self.policy["web_style"]))

    def test_วางเฉพาะบทที่เลือก_ไม่สร้างอ่านก่อน(self):
        result = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(result["status"], "ready")
        target = Path(result["directory"])
        articles = sorted(path.name for path in target.glob("*.md"))
        self.assertEqual(articles, ["xauusd.md"])
        self.assertFalse((target / "อ่านก่อน.md").exists())

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

    def test_ห้ามลบ_lane_พี่น้อง(self):
        root = self.day / self.policy["selection_folder"]
        sentinels = []
        for lane in ("02-XAUUSD-Style-E", "04-Forex-Style-L", "05-BTCUSD-Style-M"):
            folder = root / lane
            folder.mkdir(parents=True, exist_ok=True)
            file = folder / "sentinel.txt"
            file.write_text(lane, encoding="utf-8")
            sentinels.append(file)
        publish_selection.select(self.day, policy=self.policy)
        self.assertTrue(all(path.read_text(encoding="utf-8") == path.parent.name
                            for path in sentinels))

    def test_หัวข้อที่ตกด่านคืนเหตุผล_แต่ไม่สร้างไฟล์(self):
        (self.day / publish_selection.style_folder(self.policy["web_style"])
         / f"{self.policy['web_asset']}.md").unlink()
        result = publish_selection.select(self.day, policy=self.policy)
        self.assertEqual(result["status"], "missing")
        self.assertIn("รอบนี้ไม่มีไฟล์", result["reason"])
        self.assertEqual(list(Path(result["directory"]).iterdir()), [])

    def test_สไตล์ที่ไม่มีในทะเบียนต้องล้มดังๆ(self):
        """ตกไปใช้สไตล์ตั้งต้นเงียบ ๆ = วันหนึ่งบทผิดสไตล์ขึ้นเว็บโดยไม่มีใครรู้"""
        policy = dict(self.policy, web_style="ไม่มีสไตล์นี้")
        with self.assertRaises(publish_selection.SelectionUnavailable):
            publish_selection.select(self.day, policy=policy)


class เลือกสไตล_D_เป็นบทหลัก(unittest.TestCase):
    """สไตล์ D เป็นใบขึ้นเว็บจริงตั้งแต่ 2026-08-14 (ผู้ใช้สั่งให้แทน A)

    เดิมชุดนี้ชื่อ "เตรียมสลับไปสไตล์ D" และพิสูจน์แค่ว่าโค้ดพร้อมสลับ โดย
    `config/publishing_policy.json` ยังชี้ `a_standard` · ตอนนี้แฟ้มนโยบายชี้
    `d_chart_story` แล้ว ⇒ ชุดนี้กลายเป็นเทสของเส้นทางจริง ไม่ใช่เส้นทางสำรอง

    ทีมเว็บยืนยัน 2026-08-21 แล้วว่ารับ Markdown frontmatter และภาพ WebP ตามชื่อไฟล์ได้
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.day = Path(self.tmp.name) / "07-08-2026"
        self.folder = self.day / publish_selection.style_folder("d_chart_story")
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / "xauusd.md").write_text(
            "# วิเคราะห์ทองคำโลก (XAU/USD) วันนี้\n\nเนื้อบท", encoding="utf-8")
        (self.folder / "xauusd-d1-structure-2026-08-07.webp").write_bytes(b"png1")
        (self.folder / "xauusd-d1-levels-2026-08-07.webp").write_bytes(b"png2")
        current = publish_selection.load_policy()
        self.policy = {
            "schema_version": 1,
            "web_asset": "xauusd",
            "web_style": "d_chart_story",
            "articles_per_day": 1,
            "selection_folder": current["selection_folder"],
            "selection_lane": current["selection_lane"],
            "web_chart_mode": current["web_chart_mode"],
        }
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
        self.assertTrue((target / "xauusd-d1-structure-2026-08-07.webp").is_file())
        self.assertTrue((target / "xauusd-d1-levels-2026-08-07.webp").is_file())
        self.assertEqual(sorted(result["images"]),
                          sorted(["xauusd-d1-structure-2026-08-07.webp",
                                 "xauusd-d1-levels-2026-08-07.webp"]))

    def test_วันจันทร์ที่มีภาพปฏิทินต้องคัดลอกภาพที่สาม(self):
        calendar_name = "xauusd-weekly-calendar-2026-08-03-2026-08-07.webp"
        (self.folder / calendar_name).write_bytes(b"png3")
        result = publish_selection.select(self.day, policy=self.policy)
        target = Path(result["directory"])
        self.assertTrue((target / calendar_name).is_file())
        self.assertEqual(len(result["images"]), 3)
        self.assertFalse((target / "อ่านก่อน.md").exists())

    def test_โฟลเดอร์_D_มีเฉพาะบทและภาพ(self):
        result = publish_selection.select(self.day, policy=self.policy)
        target = Path(result["directory"])
        self.assertEqual(
            sorted(path.name for path in target.iterdir()),
            ["xauusd-d1-levels-2026-08-07.webp",
             "xauusd-d1-structure-2026-08-07.webp", "xauusd.md"],
        )


if __name__ == "__main__":
    unittest.main()
