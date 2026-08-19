"""เทสภาพซูมแนบของสายเว็บ A/B/C — ทางเลือกแทนหมุด (ผู้ใช้สั่ง 08-10 ค่ำ)

กติกาที่ต้องพิสูจน์: เส้นบนภาพ = เลขชุดเดียวกับหมุดเป๊ะ (D-4.5) ·
.webp ≤200 KB ตามสเปกเว็บ · ป้ายผ่านด่านความสอดคล้อง · ฉบับแนบภาพไม่เหลือหมุด
"""

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (chart_public_renderer, publish_layout, publish_selection,  # noqa: E402
                   wcb_source, wcb_writers)

ROWS = json.loads(
    (REPO_ROOT / "tests" / "fixtures" / "xau_420_sessions_2026-08-07.json")
    .read_text(encoding="utf-8"))
SNAPSHOT = json.loads(
    (REPO_ROOT / "tests" / "fixtures" / "wcb-snapshot-xauusd.json")
    .read_text(encoding="utf-8"))


def _daily_plan(evidence):
    lower, upper = chart_public_renderer.sr_lines(evidence)
    entry, stop, target = upper[0], lower[0], upper[-1]
    return {
        "classification": "daily_scenario",
        "executable": False,
        "bias": "up",
        "entry": {"edge": entry, "condition": "หากแท่งรายวันปิดเหนือระดับนี้"},
        "stop": {"value": stop},
        "targets": [{"value": target, "rr": (target - entry) / (entry - stop)}],
        "rr": (target - entry) / (entry - stop),
    }


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

    def test_ภาพ_style_a_ซูม_60_แท่งและเหลือสี่อินดิเคเตอร์ที่แสดงจริง(self):
        preview = chart_public_renderer.render_daily_indicator_lines(
            list(ROWS), self.evidence, Path(self.tmp.name) / "lines.webp",
            verify_endpoints=False)
        expected = list(chart_public_renderer.STYLE_A_FOCUS_INDICATORS)
        self.assertEqual(preview["bars"], 60)
        self.assertEqual(expected, ["SMA20", "SMA50", "RSI(14)", "MACD(12,26)"])
        self.assertEqual(preview["indicator_count"], len(expected))
        self.assertEqual([row["name"] for row in preview["endpoint_checks"]], expected)
        self.assertEqual(sum(preview["signal_counts"].values()), len(expected))
        self.assertEqual(preview["levels"], {"s": [], "r": []})
        self.assertLessEqual(preview["kb"], 200)

    def test_ภาพ_style_a_ผูก_daily_trigger_sl_tp_จากแผนโดยไม่เปลี่ยนเป็น_intraday(self):
        plan = _daily_plan(self.evidence)
        daily = chart_public_renderer.render_daily_indicator_lines(
            list(ROWS), self.evidence, Path(self.tmp.name) / "daily-plan.webp",
            plan=plan, verify_endpoints=False)
        h4 = chart_public_renderer.render_h4(
            self.evidence, Path(self.tmp.name) / "h4-plan.webp", plan=plan)
        for result in (daily, h4):
            overlay = result["plan_overlay"]
            self.assertEqual(overlay["trigger"], plan["entry"]["edge"])
            self.assertEqual(overlay["stop"], plan["stop"]["value"])
            self.assertEqual(overlay["target"], plan["targets"][0]["value"])
            self.assertEqual(overlay["condition"], "daily_close")
            self.assertFalse(overlay["executable"])
            self.assertLessEqual(result["kb"], 200)
        self.assertEqual(daily["trigger_band"]["meaning"], "visual_highlight_only")
        self.assertEqual(h4["volume"]["status"], "unavailable")
        self.assertEqual(h4["scenario"]["confirmation"], "daily_close")
        self.assertEqual(daily["layout"], "d1_dashboard")
        self.assertEqual(h4["layout"], "h4_action_plan")

    def test_เส้นแนวโน้มวาดเฉพาะ_swing_low_ยกสูงขึ้น(self):
        rows = [
            {"low": 10}, {"low": 9}, {"low": 7}, {"low": 9}, {"low": 10},
            {"low": 9}, {"low": 8}, {"low": 10}, {"low": 11},
        ]
        self.assertEqual(chart_public_renderer.uptrend_anchors(rows), ((2, 7.0), (6, 8.0)))
        rows[6]["low"] = 6
        self.assertIsNone(chart_public_renderer.uptrend_anchors(rows))

    def test_ฉากทัศน์ขาลงกลับทิศลูกศรและยังรอปิด_d1(self):
        lower, upper = chart_public_renderer.sr_lines(self.evidence)
        plan = {
            "classification": "daily_scenario", "executable": False, "bias": "down",
            "entry": {"edge": lower[0]}, "stop": {"value": upper[0]},
            "targets": [{"value": lower[-1]}],
        }
        result = chart_public_renderer.render_h4(
            self.evidence, Path(self.tmp.name) / "h4-down.webp", plan=plan)
        points = result["scenario"]["points"]
        self.assertGreater(points[1][1], points[0][1])
        self.assertLess(points[-1][1], points[-2][1])
        self.assertEqual(result["scenario"]["confirmation"], "daily_close")

    def test_ด่านปลายเส้นยอมเฉพาะค่าที่ปัดสองตำแหน่งตรง_snapshot(self):
        names = chart_public_renderer.STYLE_A_FOCUS_INDICATORS
        matching = [{"name": name, "calculated": 1.234, "reference": 1.23}
                    for name in names]
        chart_public_renderer.validate_indicator_endpoints(matching)
        broken = [dict(item) for item in matching]
        broken[0]["calculated"] = 1.25
        with self.assertRaisesRegex(ValueError, "ไม่ตรง snapshot"):
            chart_public_renderer.validate_indicator_endpoints(broken)

    def test_แท่งสดใช้_quote_price_เป็น_close_ของอินดิเคเตอร์(self):
        """กรณี GBPUSD จริง: recentDaily.c ล้าหลัง quote แต่ RSI ใน snapshot ใช้ quote"""
        rows = [{"date": "2026-08-19", "open": 1.35, "high": 1.36,
                 "low": 1.34, "close": 1.35523}]
        evidence = {
            "quote": {"price": 1.35490},
            "recent_daily": [{"t": "2026-08-19", "o": 1.35321,
                              "h": 1.35571, "l": 1.35237, "c": 1.35509}],
        }
        basis = chart_public_renderer.synchronize_live_tail(rows, evidence)
        self.assertEqual(basis, "snapshot_quote")
        self.assertEqual(rows[-1]["close"], 1.35490)
        self.assertEqual(rows[-1]["high"], 1.35571)
        self.assertEqual(rows[-1]["low"], 1.35237)

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

    def test_รันซ้ำต้องตัด_hardlink_เก่าก่อนวาดภาพเฉพาะสไตล์(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            style_a, style_b = root / "A", root / "B"
            style_a.mkdir()
            style_b.mkdir()
            name = "xauusd-web-4h.webp"
            (style_a / name).write_bytes(b"old-shared-chart")
            os.link(style_a / name, style_b / name)
            self.assertTrue((style_a / name).samefile(style_b / name))

            publish_layout._reset_chart_outputs(style_b, (name,))
            (style_b / name).write_bytes(b"style-b-plain")

            self.assertEqual((style_a / name).read_bytes(), b"old-shared-chart")
            self.assertEqual((style_b / name).read_bytes(), b"style-b-plain")
            self.assertFalse((style_a / name).samefile(style_b / name))

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

        ตอนนี้**ไม่มีสไตล์ไหนเปิดธง `pin_fallback` แล้ว** (ผู้ใช้สั่งเลิกครบ A/B/C
        08-11 บ่าย) — เทสนี้เปิดธงชั่วคราวเพื่อคุม**ทางกลับ**ให้ยังทำงานจริง
        แบบเดียวกับที่โหมด `pins` มีเทสของตัวเองทั้งที่รอบผลิตจริงไม่ใช้
        """
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(wcb_writers.by_id("b_technical"),
                                {"pin_fallback": True}):
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
