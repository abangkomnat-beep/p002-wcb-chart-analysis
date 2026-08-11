"""เทสภาพซูมแนบของสายเว็บ A/B/C — ทางเลือกแทนหมุด (ผู้ใช้สั่ง 08-10 ค่ำ)

กติกาที่ต้องพิสูจน์: เส้นบนภาพ = เลขชุดเดียวกับหมุดเป๊ะ (D-4.5) ·
.webp ≤200 KB ตามสเปกเว็บ · ป้ายผ่านด่านความสอดคล้อง · ฉบับแนบภาพไม่เหลือหมุด
"""

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import chart_public_renderer, publish_selection, wcb_source, wcb_writers  # noqa: E402

ROWS = json.loads(
    (REPO_ROOT / "tests" / "fixtures" / "xau_420_sessions_2026-08-07.json")
    .read_text(encoding="utf-8"))
SNAPSHOT = json.loads(
    (REPO_ROOT / "tests" / "fixtures" / "wcb-snapshot-xauusd.json")
    .read_text(encoding="utf-8"))


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = wcb_source.normalize(SNAPSHOT)
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.daily = chart_public_renderer.render_daily_zoom(
            list(ROWS), cls.evidence, root / "d1.webp")
        cls.h4 = chart_public_renderer.render_h4(cls.evidence, root / "h4.webp")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_ไฟล์เป็น_webp_ไม่เกินเพดานเว็บ(self):
        for result in (self.daily, self.h4):
            self.assertTrue(Path(result["path"]).is_file())
            self.assertTrue(result["path"].endswith(".webp"))
            self.assertLessEqual(result["kb"], 200)

    def test_ระยะซูมตามสเปก(self):
        self.assertEqual(self.daily["bars"], 60)
        self.assertEqual(self.h4["bars"], 24)

    def test_เส้นบนภาพคือเลขชุดเดียวกับหมุดเป๊ะ(self):
        # หมุดจริงที่บทใช้ — ต้องตรงกับเส้นที่ภาพวาดทุกตัว (D-4.5)
        marker = wcb_writers.chart_marker(self.evidence, "1day")
        pin_values = {float(x) for x in re.findall(r"[sr]=([\d.,]+)", marker)[0].split(",")} | \
                     {float(x) for x in re.findall(r"[sr]=([\d.,]+)", marker)[1].split(",")}
        image_values = set(self.daily["levels"]["s"]) | set(self.daily["levels"]["r"])
        self.assertEqual(image_values, pin_values,
                         "เส้นบนภาพกับเลขในหมุด/บทต้องเป็นชุดเดียวกัน")

    def test_สวมบั๊กกลับ_แท่ง_4h_ไม่พอต้องระเบิด(self):
        thin = dict(self.evidence)
        thin["recent_by_tf"] = {"4h": self.evidence["recent_by_tf"]["4h"][:3]}
        with self.assertRaises(ValueError):
            chart_public_renderer.render_h4(thin, Path(self.tmp.name) / "thin.webp")


class SwapPinsTests(unittest.TestCase):
    MD = ("---\ntitle: x\n---\n\nเนื้อบท\n\n"
          "[[chart:1day|s=4324,4315|r=4341,4342]]\n\nกลางบท\n\n"
          "[[chart:4h|s=4324,4315|r=4341,4342]]\n\nท้ายบท\n")

    def test_แทนหมุดครบและไม่เหลือหมุด(self):
        out = chart_public_renderer.swap_pins_for_images(self.MD, "a.webp", "b.webp")
        self.assertNotIn("[[chart", out, "ห้ามเหลือหมุดปนภาพ — เว็บจะวาดกราฟซ้ำ")
        self.assertIn("](a.webp)", out)
        self.assertIn("](b.webp)", out)
        # เนื้อบทส่วนอื่นต้องไม่ถูกแตะ
        for text in ("เนื้อบท", "กลางบท", "ท้ายบท", "title: x"):
            self.assertIn(text, out)

    def test_alt_text_ไม่มีตัวเลข(self):
        # เลขใน alt จะไปเพิ่มภาระทะเบียนด่านตรวจโดยไม่จำเป็น
        out = chart_public_renderer.swap_pins_for_images(self.MD, "a.webp", "b.webp")
        for alt in re.findall(r"!\[([^\]]*)\]", out):
            self.assertFalse(re.search(r"\d", alt), f"alt มีตัวเลข: {alt!r}")


class SelectionCopyTests(unittest.TestCase):
    """publish_selection ต้องพาชุดแนบภาพตามไปโฟลเดอร์ขึ้นเว็บ — และไม่พังเมื่อไม่มีชุด"""

    POLICY = {"web_asset": "xauusd", "web_style": "a_standard",
              "articles_per_day": 1, "decided_by": "เทส", "reason": "เทส",
              "produced_but_not_published": []}

    def _day_dir(self, tmp: Path, *, with_images: bool,
                 style: str = "a_standard") -> Path:
        folder = tmp / publish_selection.style_folder(style)
        folder.mkdir(parents=True)
        (folder / "xauusd.md").write_text(SwapPinsTests.MD, encoding="utf-8")
        if with_images:
            evidence = wcb_source.normalize(SNAPSHOT)
            daily_name, h4_name = chart_public_renderer.image_names("xauusd", "2026-08-07")
            chart_public_renderer.render_daily_zoom(list(ROWS), evidence, folder / daily_name)
            chart_public_renderer.render_h4(evidence, folder / h4_name)
            (folder / "xauusd-แนบภาพ.md").write_text(
                chart_public_renderer.swap_pins_for_images(
                    SwapPinsTests.MD, daily_name, h4_name), encoding="utf-8")
        return tmp

    def test_มีชุดแนบภาพ_ใบหลักคือฉบับแนบภาพและใบหมุดเป็นตัวสำรอง(self):
        """ผู้ใช้สั่ง 08-11: คนที่หยิบ `xauusd.md` ไปวางต้องได้ฉบับที่อ้างภาพซูม

        ใช้สไตล์ B เป็นตัวทดสอบกลไกใบสำรอง — A เลิกมีใบหมุดแล้ว (ธง `pin_fallback`)
        จึงเป็นตัวแทนของกลไกนี้ไม่ได้อีก (มีเทสของตัวเองแยกด้านล่าง)
        """
        with tempfile.TemporaryDirectory() as tmp:
            day_dir = self._day_dir(Path(tmp), with_images=True, style="b_technical")
            policy = dict(self.POLICY, web_style="b_technical")
            result = publish_selection.select(day_dir, policy=policy)
            self.assertEqual(result["status"], "ready")
            self.assertEqual(len(result["images"]), 2)
            self.assertEqual(result["chart_mode"], publish_selection.CHART_MODE_IMAGES)
            self.assertEqual(result["pin_fallback"], "xauusd-หมุดกราฟ.md")
            target = day_dir / "0-ขึ้นเว็บวันนี้"
            main = (target / "xauusd.md").read_text(encoding="utf-8")
            self.assertNotIn("[[chart", main, "ใบหลักต้องไม่เหลือหมุด — เว็บจะวาดกราฟซ้ำ")
            self.assertIn("](xauusd-web-", main)
            fallback = (target / "xauusd-หมุดกราฟ.md").read_text(encoding="utf-8")
            self.assertIn("[[chart:1day", fallback, "ใบหมุดต้องยังอยู่เป็นทางถอย")
            # ฉบับชื่อเดิมต้องไม่นอนคู่กันอีก — สามใบในโฟลเดอร์เดียวคือกับดักวางผิดใบ
            self.assertFalse((target / "xauusd-แนบภาพ.md").exists())
            note = (target / "อ่านก่อน.md").read_text(encoding="utf-8")
            self.assertIn("อัปโหลดรูปในโฟลเดอร์นี้ด้วยทั้ง 2 ใบ", note)
            self.assertIn("xauusd-หมุดกราฟ.md", note)
            self.assertIn("ห้ามใช้สองฉบับพร้อมกัน", note)

    def test_สไตล์A_ไม่มีใบหมุดในโฟลเดอร์ขึ้นเว็บตามคำสั่งผู้ใช้_08_11(self):
        """ผู้ใช้สั่ง 08-11 บ่าย: "เอาไฟล์ md -หมุดกราฟ ออกทั้งหมด ไม่ต้องทำแล้ว"

        ครอบทั้งสองยุคของโฟลเดอร์สไตล์ — โครงเก่า (`-แนบภาพ.md`) และโครงที่มี
        ใบหมุดตกค้าง: ปลายทางต้องไม่มี `-หมุดกราฟ.md` และใบอธิบายห้ามชวนไปหยิบ
        """
        for leftover_fallback in (False, True):
            with self.subTest(leftover_fallback=leftover_fallback), \
                    tempfile.TemporaryDirectory() as tmp:
                day_dir = self._day_dir(Path(tmp), with_images=True)
                folder = day_dir / publish_selection.style_folder("a_standard")
                if leftover_fallback:
                    # จำลองใบหมุดตกค้างจากรอบก่อนธงถูกปิด + ใบหลักที่สลับเป็นแนบภาพแล้ว
                    (folder / "xauusd-หมุดกราฟ.md").write_text(
                        SwapPinsTests.MD, encoding="utf-8")
                    (folder / "xauusd.md").write_text(
                        (folder / "xauusd-แนบภาพ.md").read_text(encoding="utf-8"),
                        encoding="utf-8")
                    (folder / "xauusd-แนบภาพ.md").unlink()
                result = publish_selection.select(day_dir, policy=dict(self.POLICY))
                self.assertEqual(result["status"], "ready")
                self.assertEqual(result["chart_mode"],
                                 publish_selection.CHART_MODE_IMAGES)
                self.assertIsNone(result["pin_fallback"])
                target = day_dir / "0-ขึ้นเว็บวันนี้"
                main = (target / "xauusd.md").read_text(encoding="utf-8")
                self.assertNotIn("[[chart", main)
                self.assertIn("](xauusd-web-", main)
                self.assertFalse((target / "xauusd-หมุดกราฟ.md").exists(),
                                 "สไตล์ A ต้องไม่มีใบหมุดในโฟลเดอร์ขึ้นเว็บอีก")
                note = (target / "อ่านก่อน.md").read_text(encoding="utf-8")
                self.assertNotIn("xauusd-หมุดกราฟ.md", note)
                self.assertIn("ไม่มีใบหมุดสำรองแล้ว", note)

    def test_โหมดหมุด_ยังกลับพฤติกรรมเดิมได้โดยไม่แก้โค้ด(self):
        """ทางถอยของ 08-10 ต้องยังใช้ได้ — วันที่หน้าหลังบ้านไม่มีช่องแนบรูป"""
        with tempfile.TemporaryDirectory() as tmp:
            day_dir = self._day_dir(Path(tmp), with_images=True)
            policy = dict(self.POLICY, web_chart_mode=publish_selection.CHART_MODE_PINS)
            result = publish_selection.select(day_dir, policy=policy)
            self.assertEqual(result["chart_mode"], publish_selection.CHART_MODE_PINS)
            self.assertEqual(result["attach_variant"], "xauusd-แนบภาพ.md")
            target = day_dir / "0-ขึ้นเว็บวันนี้"
            self.assertIn("[[chart:1day",
                          (target / "xauusd.md").read_text(encoding="utf-8"))
            self.assertTrue((target / "xauusd-แนบภาพ.md").is_file())
            self.assertFalse((target / "xauusd-หมุดกราฟ.md").exists())

    def test_โหมดที่ไม่มีในทะเบียนต้องล้มดังๆ(self):
        with tempfile.TemporaryDirectory() as tmp:
            day_dir = self._day_dir(Path(tmp), with_images=True)
            policy = dict(self.POLICY, web_chart_mode="ไม่มีโหมดนี้")
            with self.assertRaises(publish_selection.SelectionUnavailable):
                publish_selection.select(day_dir, policy=policy)

    def test_ไม่มีชุดแนบภาพ_พฤติกรรมเดิมทุกช่อง(self):
        with tempfile.TemporaryDirectory() as tmp:
            day_dir = self._day_dir(Path(tmp), with_images=False)
            result = publish_selection.select(day_dir, policy=dict(self.POLICY))
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["images"], [])
            self.assertIsNone(result["attach_variant"])
            self.assertIsNone(result["pin_fallback"])
            self.assertEqual(result["chart_mode"], publish_selection.CHART_MODE_PINS)
            note = (day_dir / "0-ขึ้นเว็บวันนี้" / "อ่านก่อน.md").read_text(encoding="utf-8")
            self.assertNotIn("ช่องแนบ/อัปโหลดรูป", note)


if __name__ == "__main__":
    unittest.main()
