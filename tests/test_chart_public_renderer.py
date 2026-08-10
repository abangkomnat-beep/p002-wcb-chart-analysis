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

    def _day_dir(self, tmp: Path, *, with_images: bool) -> Path:
        folder = tmp / publish_selection.style_folder("a_standard")
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

    def test_มีชุดแนบภาพ_คัดลอกครบและใบแนะนำอธิบายสองทาง(self):
        with tempfile.TemporaryDirectory() as tmp:
            day_dir = self._day_dir(Path(tmp), with_images=True)
            result = publish_selection.select(day_dir, policy=dict(self.POLICY))
            self.assertEqual(result["status"], "ready")
            self.assertEqual(len(result["images"]), 2)
            self.assertEqual(result["attach_variant"], "xauusd-แนบภาพ.md")
            target = day_dir / "0-ขึ้นเว็บวันนี้"
            self.assertTrue((target / "xauusd-แนบภาพ.md").is_file())
            note = (target / "อ่านก่อน.md").read_text(encoding="utf-8")
            self.assertIn("ช่องแนบ/อัปโหลดรูป", note)
            self.assertIn("ห้ามใช้สองฉบับพร้อมกัน", note)

    def test_ไม่มีชุดแนบภาพ_พฤติกรรมเดิมทุกช่อง(self):
        with tempfile.TemporaryDirectory() as tmp:
            day_dir = self._day_dir(Path(tmp), with_images=False)
            result = publish_selection.select(day_dir, policy=dict(self.POLICY))
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["images"], [])
            self.assertIsNone(result["attach_variant"])
            note = (day_dir / "0-ขึ้นเว็บวันนี้" / "อ่านก่อน.md").read_text(encoding="utf-8")
            self.assertNotIn("ช่องแนบ/อัปโหลดรูป", note)


if __name__ == "__main__":
    unittest.main()
