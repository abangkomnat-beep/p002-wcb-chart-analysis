"""เทสด่านไฟล์ภาพที่ส่งขึ้นเว็บ — นามสกุล `.webp` และเพดาน 200 KB ต่อใบ

ทีมเว็บ WCB ไม่แปลงและไม่บีบไฟล์ให้ (กติกาหัวหน้า 2026-08-09) ⇒ ไฟล์ผิดกติกา
= ตีกลับทั้งใบ ไม่ใช่แค่รูปใบนั้น · เทสชุดนี้ล็อกสองอย่างที่ผ่อนไม่ได้:

1. **ตัวเลขเกณฑ์** — เพดานกับนามสกุลเป็นค่าที่ปลายทางกำหนด ไม่ใช่ค่าที่เราปรับ
   เพื่อให้ของออก (ถ้าไฟล์ล้น ต้องลดคุณภาพการบีบ ไม่ใช่ยกเพดาน)
2. **ด่านต้องวัดไฟล์จริง** — ไม่ใช่เชื่อค่าคุณภาพที่ตั้งไว้ เพราะขนาดไฟล์ขึ้นกับ
   ความรกของกราฟแต่ละวัน
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import chart_indicator_writer, chart_story_writer, image_output  # noqa: E402
from tools import publish_layout, publish_selection  # noqa: E402


def _figure():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(figsize=(4, 3), dpi=100)
    axes.plot([0, 1, 2], [1, 3, 2])
    return figure


class เกณฑ์ที่ผ่อนไม่ได้(unittest.TestCase):

    def test_เพดานกับนามสกุลตรงกับที่ทีมเว็บกำหนด(self):
        """ค่าคู่นี้มาจากปลายทาง ไม่ใช่ค่าที่ปรับได้เองเวลาไฟล์ล้น"""
        self.assertEqual(image_output.IMAGE_SUFFIX, ".webp")
        self.assertEqual(image_output.MAX_IMAGE_BYTES, 200 * 1024)

    def test_ค่าคุณภาพอยู่ในช่วงที่ให้ภาพชัดจริง(self):
        # ต่ำกว่านี้เริ่มเห็นรอยบีบบนเส้นกราฟบาง ๆ และตัวหนังสือไทยบนภาพ
        self.assertGreaterEqual(image_output.WEBP_QUALITY, 80)
        self.assertLessEqual(image_output.WEBP_QUALITY, 100)
        self.assertEqual(image_output.MIN_WEBP_QUALITY, 80)


class ด่านตรวจไฟล์เดี่ยว(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ไฟล์_png_ตกด่านแม้ขนาดจะเล็ก(self):
        stale = self.folder / "xauusd-d1-levels-2026-08-09.png"
        stale.write_bytes(b"tiny")

        with self.assertRaises(image_output.ImageGateError) as caught:
            image_output.verify(stale)
        self.assertIn(".webp", str(caught.exception))

    def test_ไฟล์เกินเพดานตกด่านและข้อความบอกขนาดจริง(self):
        heavy = self.folder / "หนัก.webp"
        heavy.write_bytes(b"x" * (image_output.MAX_IMAGE_BYTES + 1))

        with self.assertRaises(image_output.ImageGateError) as caught:
            image_output.verify(heavy)
        self.assertIn("200.0 KB", str(caught.exception))

    def test_ไฟล์พอดีเพดานยังผ่าน_ไม่ตัดทิ้งเกินจำเป็น(self):
        exact = self.folder / "พอดี.webp"
        exact.write_bytes(b"x" * image_output.MAX_IMAGE_BYTES)

        self.assertEqual(image_output.verify(exact), image_output.MAX_IMAGE_BYTES)

    def test_ไม่มีไฟล์ก็ต้องตก_ไม่ใช่เงียบผ่าน(self):
        with self.assertRaises(image_output.ImageGateError):
            image_output.verify(self.folder / "ไม่มีจริง.webp")

    def test_verify_folder_ไล่ทุกใบและข้ามไฟล์บท(self):
        (self.folder / "xauusd.md").write_text("บท", encoding="utf-8")
        (self.folder / "a.webp").write_bytes(b"x" * 10)
        (self.folder / "b.webp").write_bytes(b"x" * 20)

        self.assertEqual(image_output.verify_folder(self.folder), {"a.webp": 10, "b.webp": 20})

    def test_verify_folder_สะดุดทันทีที่เจอใบผิดกติกา(self):
        (self.folder / "a.webp").write_bytes(b"x" * 10)
        (self.folder / "b.png").write_bytes(b"x" * 10)

        with self.assertRaises(image_output.ImageGateError):
            image_output.verify_folder(self.folder)


class เซฟภาพผ่านด่านเสมอ(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_เซฟแล้วได้ไฟล์_webp_จริงและคืนขนาด(self):
        target = self.folder / "กราฟ.webp"

        size = image_output.save_figure(_figure(), target)

        self.assertTrue(target.is_file())
        self.assertEqual(size, target.stat().st_size)
        self.assertEqual(target.read_bytes()[:4], b"RIFF")   # ลายเซ็นไฟล์ webp จริง
        self.assertEqual(target.read_bytes()[8:12], b"WEBP")

    def test_ภาพรายละเอียดสูงกำหนดคุณภาพเฉพาะใบได้แต่ห้ามต่ำกว่าพื้น(self):
        target = self.folder / "ตาราง.webp"
        size = image_output.save_figure(
            _figure(), target, webp_quality=image_output.MIN_WEBP_QUALITY)
        self.assertEqual(size, target.stat().st_size)

        with self.assertRaises(image_output.ImageGateError):
            image_output.save_figure(
                _figure(), self.folder / "ต่ำเกิน.webp",
                webp_quality=image_output.MIN_WEBP_QUALITY - 1)

    def test_สั่งเซฟเป็น_png_ต้องถูกปฏิเสธตั้งแต่ยังไม่วาด(self):
        target = self.folder / "กราฟ.png"

        with self.assertRaises(image_output.ImageGateError):
            image_output.save_figure(_figure(), target)
        self.assertFalse(target.exists())

    def test_ไฟล์ล้นเพดานต้องถูกลบทิ้ง_ไม่ปล่อยให้คนหยิบไปอัป(self):
        """fail-closed: ตกด่านแล้วต้องไม่มีไฟล์เหลือให้เข้าใจผิดว่าใช้ได้"""
        target = self.folder / "ล้น.webp"

        with mock.patch.object(image_output, "MAX_IMAGE_BYTES", 10):
            with self.assertRaises(image_output.ImageGateError):
                image_output.save_figure(_figure(), target)

        self.assertFalse(target.exists())


class ชื่อไฟล์ทั้งสายต้องเป็น_webp(unittest.TestCase):

    def test_สไตล์_D_สองใบ(self):
        for name in chart_story_writer.image_names("xauusd", "2026-08-09"):
            self.assertTrue(name.endswith(".webp"), name)

    def test_ภาพปฏิทินรายสัปดาห์ของสไตล์_D(self):
        story = {"asset": "xauusd", "publish_date": "2026-08-03",
                 "calendar": {"week_start": "2026-08-03", "week_end": "2026-08-07"}}
        self.assertTrue(chart_story_writer.calendar_image_name(story).endswith(".webp"))

    def test_สไตล์_E_ใบเดียว(self):
        self.assertTrue(
            chart_indicator_writer.image_name("xauusd", "2026-08-09").endswith(".webp"))


class ด่านตอนส่งของขึ้นเว็บ(unittest.TestCase):
    """สองจุดสุดท้ายก่อนไฟล์ถึงมือคน — โฟลเดอร์วันเป็นของที่แก้ด้วยมือได้"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.day = Path(self.tmp.name) / "09-08-2026"
        self.folder = self.day / chart_story_writer.FOLDER
        self.folder.mkdir(parents=True)
        (self.folder / "xauusd.md").write_text("# บท\n", encoding="utf-8")
        self.policy = {"web_asset": "xauusd", "web_style": chart_story_writer.STYLE_ID,
                       "articles_per_day": 1, "decided_by": "เทส", "reason": "เทส"}

    def tearDown(self):
        self.tmp.cleanup()

    def test_รูปยุค_png_ค้างในโฟลเดอร์วันต้องหยุดการวางใบขึ้นเว็บ(self):
        (self.folder / "xauusd-d1-structure-2026-08-09.png").write_bytes(b"old")

        with self.assertRaises(image_output.ImageGateError):
            publish_selection.select(self.day, policy=self.policy)

    def test_รูปเกินเพดานต้องหยุดการวางใบขึ้นเว็บ(self):
        (self.folder / "xauusd-d1-structure-2026-08-09.webp").write_bytes(
            b"x" * (image_output.MAX_IMAGE_BYTES + 1))

        with self.assertRaises(image_output.ImageGateError):
            publish_selection.select(self.day, policy=self.policy)

    def test_รูปถูกกติกาผ่านฉลุยและถูกคัดลอกตามไป(self):
        (self.folder / "xauusd-d1-structure-2026-08-09.webp").write_bytes(b"x" * 100)

        result = publish_selection.select(self.day, policy=self.policy)

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["images"], ["xauusd-d1-structure-2026-08-09.webp"])

    def test_สาย_ABC_ต้องหยุดตั้งแต่ยังไม่วางไฟล์ถ้ากราฟต้นทางผิดกติกา(self):
        """`publish_asset` ใช้กราฟใบเดียวกับทุกสไตล์ — ผิดใบเดียวคือผิดทั้งสามโฟลเดอร์"""
        bad = Path(self.tmp.name) / "source-chart.png"
        bad.write_bytes(b"tiny")
        out = Path(self.tmp.name) / "out"

        with self.assertRaises(image_output.ImageGateError):
            publish_layout.publish_asset(
                asset="xauusd", article_data={}, technical_evidence={},
                chart_source=bad, publish_root=out,
                cutoff_at="2026-08-09T12:00:00+00:00", instrument_type="spot_metal")
        self.assertFalse(out.exists(), "ตกด่านแล้วต้องไม่มีโฟลเดอร์ผลผลิตโผล่มาเลย")


if __name__ == "__main__":
    unittest.main()
