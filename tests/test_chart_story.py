"""เทสสไตล์ D — เครื่องอ่านโครงสร้าง · นักเขียน+ด่าน · ตัววาด · สายผลิต

หลักที่ล็อกไว้ในเทสชุดนี้:
1. เลขทุกตัวในบทต้องชี้กลับ story ได้ (fail-closed) — เลขแปลกปลอมตัวเดียวก็ตก
2. หนามราคาแหลมครั้งเดียวห้ามกำหนดความกว้างกรอบ (กฎอันดับสอง)
3. ตกด่าน/วาดล้มกลางคัน = โฟลเดอร์ D ต้องว่าง ไม่เหลือชุดครึ่ง ๆ กลาง ๆ
"""

import json
import math
import re
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import chart_story, chart_story_pipeline, chart_story_renderer  # noqa: E402
from tools import chart_story_writer  # noqa: E402


def make_rows(n=420, *, start=300.0, step=-0.3, wave=6.0, body=0.4, wick=1.2):
    """แท่งสังเคราะห์: เส้นตรง start + step*i บวกคลื่น sine ให้เกิด swing จริง

    คลื่นต้องชันกว่าเทรนด์ (อนุพันธ์สูงสุด wave/6 ต่อแท่ง > |step|) ไม่งั้นราคา
    วิ่งทางเดียวไม่มี swing เลย แล้วกรอบแนวโน้มจะสร้างไม่ได้ — เจอจริงตอนเขียนเทสรอบแรก

    `body`/`wick` ต้องย่อตามสเกลราคาเมื่อทดสอบคู่เงิน — ค่าตั้งต้นเป็นสเกลทอง
    ถ้าปล่อยไว้กับราคา 1.15 จะได้ไส้เทียนยาว 1.2 ดอลลาร์ คือแท่งที่ไม่มีจริงในตลาด
    """
    rows = []
    first_day = date(2025, 1, 1)
    for i in range(n):
        base = start + step * i
        close = base + wave * math.sin(i / 6)
        open_value = close - body
        high = max(open_value, close) + wick
        low = min(open_value, close) - wick
        rows.append({"date": (first_day + timedelta(days=i)).isoformat(),
                     "open": open_value, "high": high, "low": low, "close": close})
    return rows


# แท่งสเกลคู่เงิน — ราคาเดินทีละ 0.00001 ไส้เทียนจึงต้องเล็กตามสเกล ไม่ใช่ 1.2 ดอลลาร์แบบทอง
FX_ROWS = make_rows(start=1.15, step=-1e-5, wave=2e-4, body=2e-5, wick=6e-5)


class ทศนิยมตามสินทรัพย์(unittest.TestCase):
    """🐞 บั๊กจริง 2026-08-07 — สั่งผลิต EUR/USD ครั้งแรกแล้วทั้งบทเป็นตัวเลขใช้ไม่ได้

    `price_text` ถูกตรึงไว้ `,.2f` ตายตัวเพราะสไตล์ D/E เกิดมาในโลกของทองล้วน
    ระดับราคาของคู่เงินจึงถูกปัดเหลือ `1.15` `1.17` `1.18` ทั้งที่เดินทีละ 0.00001
    · **บั๊กตัวเดียวกับที่เคยเกิดกับ `wcb_writers.price()` (08-05) และ E7 ฝั่งปลายทาง**
    ⇒ กลับมาซ้ำทุกครั้งที่มีตัวเขียนใหม่เกิดขึ้นโดยทดสอบกับทองอย่างเดียว
    """

    def test_ทองสองตำแหน่ง_คู่เงินห้าตำแหน่ง(self):
        gold = chart_story.build_story(make_rows(), asset="xauusd")
        fx = chart_story.build_story(FX_ROWS, asset="eurusd")
        self.assertEqual(chart_story_renderer.money_for(gold)(1.153456), "1.15")
        self.assertEqual(chart_story_renderer.money_for(fx)(1.153456), "1.15346")
        # MACD เป็นสเกลราคา ไม่ใช่ 0-100 — ต้องใช้ทศนิยมชุดเดียวกับราคา (เหตุผลเดียวกับ E7)
        self.assertEqual(chart_story_renderer.macd_for(fx)(0.00314), "0.00314")

    def test_บทของคู่เงินต้องไม่มีราคาที่ถูกปัดจนซ้ำกัน(self):
        story = chart_story.build_story(FX_ROWS, asset="eurusd")
        article = chart_story_writer.render_article(story)
        prices = re.findall(r"\b1\.\d+\b", article)
        self.assertTrue(prices, "บทคู่เงินต้องมีราคาอยู่จริง")
        self.assertTrue(all(len(p.split(".")[1]) == 5 for p in prices),
                        f"ราคาทุกตัวต้องมีทศนิยมห้าตำแหน่ง เจอ {sorted(set(prices))[:6]}")
        # ด่านตรวจต้องยอมรับรูปแบบเดียวกัน ไม่งั้นบทที่ถูกจะตกด่านเอง
        self.assertEqual(chart_story_writer.validate(article, story)["status"], "pass")


class เครื่องอ่านโครงสร้าง(unittest.TestCase):

    def test_ขาลงต้องได้โหมดลงและกรอบชี้ลง(self):
        story = chart_story.build_story(make_rows(), asset="xauusd")

        self.assertTrue(story["regime"]["down"])
        self.assertIsNotNone(story["channel"])
        self.assertLess(story["channel"]["slope"], 0)
        self.assertTrue(story["channel"]["main_is_upper"])
        self.assertEqual(story["display"]["bars"], chart_story.DISPLAY_BARS)
        self.assertEqual(story["current"]["close"],
                         make_rows()[-1]["close"])

    def test_ขาขึ้นต้องได้โหมดขึ้นและเส้นหลักเป็นขอบล่าง(self):
        story = chart_story.build_story(make_rows(start=100.0, step=0.3), asset="xauusd")

        self.assertFalse(story["regime"]["down"])
        self.assertIsNotNone(story["channel"])
        self.assertGreater(story["channel"]["slope"], 0)
        self.assertFalse(story["channel"]["main_is_upper"])

    def test_หนามแหลมครั้งเดียวห้ามกำหนดความกว้างกรอบ(self):
        """กฎอันดับสอง — หลักเดียวกับ provider_step ที่ปิด E7"""
        residuals = [-100.0, -5.0, -3.0, -1.0]
        self.assertEqual(chart_story.second_rank_offset(residuals, downtrend=True), -5.0)
        self.assertEqual(chart_story.second_rank_offset([7.0], downtrend=True), 7.0)
        self.assertEqual(
            chart_story.second_rank_offset([1.0, 5.0, 100.0], downtrend=False), 5.0)

    def test_ระดับใกล้กันถูกยุบเป็นกลุ่มพร้อมนับครั้งที่แตะ(self):
        clusters = chart_story.cluster_levels(
            [(1, 100.0), (5, 100.5), (9, 120.0)], tolerance=1.0)

        self.assertEqual(len(clusters), 2)
        self.assertEqual(clusters[0]["touches"], 2)
        self.assertAlmostEqual(clusters[0]["mean"], 100.25)
        self.assertEqual(clusters[0]["last_index"], 5)
        self.assertEqual(clusters[1]["touches"], 1)

    def test_ฉากทัศน์สร้างจากระดับที่มีจริงเท่านั้น(self):
        resistance = [{"mean": 110.0}, {"mean": 120.0}, {"mean": 130.0}]
        zones = [{"mean": 95.0, "low": 93.0}, {"mean": 85.0, "low": 83.0}]
        scenarios = chart_story._scenarios(100.0, resistance, zones,
                                           week52_low=80.0, atr=2.0)

        self.assertEqual(scenarios["up"]["trigger"], 110.0)
        self.assertEqual(scenarios["up"]["targets"], [120.0, 130.0])
        # จุดเข้าฝั่งขึ้นแบบ breakout-continuation (ฟีดแบ็กหัวหน้าข้อ 4)
        self.assertEqual(scenarios["up"]["entry_low"], 110.0)
        self.assertEqual(scenarios["up"]["entry_high"], 111.0)
        # D-1 (ฟีดแบ็กหัวหน้า 08-07): invalidation ต้องต่ำกว่าขอบโซนเข้า 1×ATR
        # ไม่ใช่เท่ากับขอบโซน (ของเดิม = ระยะเสี่ยงเป็นศูนย์ ทำตามไม่ได้จริง)
        self.assertEqual(scenarios["up"]["entry_invalidation"], 108.0)
        self.assertLess(scenarios["up"]["entry_invalidation"], scenarios["up"]["entry_low"])
        self.assertEqual(scenarios["down"]["trigger"], 93.0)
        self.assertEqual(scenarios["down"]["targets"], [85.0, 80.0])
        empty = chart_story._scenarios(100.0, [], [], week52_low=80.0, atr=2.0)
        self.assertIsNone(empty["up"])
        self.assertIsNone(empty["down"])

    def test_ระดับที่ใกล้ราคาเกินไปไม่ถูกเลือกเป็นแนวต้านหรือแนวรับ(self):
        """D-3 (ฟีดแบ็กหัวหน้า 08-07): ระดับห่างราคาไม่ถึง 1×ATR คือ noise

        ใช้ swing สังเคราะห์สองชุด — ชุดหนึ่งมีจุดกลับตัวใกล้ราคาปัจจุบันมาก
        (ต่ำกว่า 1×ATR) อีกชุดห่างพอ แล้วตรวจว่าเฉพาะชุดที่ห่างพอถูกเลือก
        """
        rows = make_rows(n=420, start=300.0, step=0.0, wave=1.0)
        # เติมยอดปลอมใกล้ราคาปัจจุบันมาก (ห่าง < 1×ATR) ไว้ท้ายชุด
        atr_now = chart_story.atr14(rows)
        near_spike = rows[-1]["close"] + 0.3 * atr_now
        rows[-6] = {**rows[-6], "high": near_spike, "low": near_spike - 0.5,
                    "close": near_spike - 0.2, "open": near_spike - 0.3}
        story = chart_story.build_story(rows, asset="xauusd")
        for level in story["resistance"]:
            self.assertGreaterEqual(level["mean"] - story["current"]["close"],
                                    chart_story.RESISTANCE_MIN_DISTANCE_ATR * story["atr14"])

    def test_จุดเข้าซื้อมาจากโซนใกล้เท่านั้น_โซนไกลไม่เป็นแผนรายวัน(self):
        """ฟีดแบ็กหัวหน้าข้อ 5: โซนห่างเกินเกณฑ์ = ระดับหลายเดือน ไม่ใช่จุดเข้ารายวัน"""
        zones = [{"rank": 1, "mean": 95.0, "low": 93.0, "high": 97.0, "touches": 6,
                  "daily_entry": True},
                 {"rank": 2, "mean": 85.0, "low": 83.0, "high": 87.0, "touches": 7,
                  "daily_entry": False}]
        entries = chart_story._entries(zones)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["rank"], 1)
        self.assertEqual(entries[0]["price"], 95.0)
        self.assertEqual(entries[0]["invalidation"], 93.0)
        self.assertEqual(chart_story._entries([]), [])

    def test_แท่งไม่พอต้องหยุดดังๆ(self):
        with self.assertRaises(chart_story.StoryUnavailable):
            chart_story.build_story(make_rows(n=150), asset="xauusd")


class นักเขียนและด่าน(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.rows = make_rows()
        cls.story = chart_story.build_story(cls.rows, asset="xauusd")
        cls.markdown = chart_story_writer.render_article(cls.story)

    def test_บทของตัวเองต้องผ่านด่านของตัวเอง(self):
        validation = chart_story_writer.validate(self.markdown, self.story)

        self.assertEqual(validation["status"], "pass",
                         msg=str(validation["findings"]))

    def test_เลขที่ไม่อยู่บนภาพต้องตกทั้งบท(self):
        tampered = self.markdown.replace(
            chart_story_renderer.price_text(self.story["current"]["close"]),
            "9,999.99", 1)
        validation = chart_story_writer.validate(tampered, self.story)

        self.assertEqual(validation["status"], "fail")
        self.assertTrue(any(f["rule"] == "number_not_in_story"
                            for f in validation["findings"]))

    def test_บทต้องอ้างภาพครบทั้งสองใบ(self):
        first_image, _ = chart_story_writer.image_names(
            "xauusd", self.story["current"]["date"])
        broken = self.markdown.replace(f"({first_image})", "(หายไป)")
        validation = chart_story_writer.validate(broken, self.story)

        self.assertTrue(any(f["rule"] == "missing_image"
                            for f in validation["findings"]))

    def test_มีปฏิทินแล้วบทต้องมีหัวข้อปัจจัยพื้นฐานและผ่านด่าน(self):
        """ฟีดแบ็กหัวหน้าข้อ 3 + มติผู้ใช้: ปฏิทินจริงแทนลิงก์ข่าว — เลขในประโยค
        ปฏิทินเป็นส่วนหนึ่งของ story จึงต้องผ่านทะเบียนเลขได้ทั้งชุด"""
        calendar = {"sentences": [
            "พรุ่งนี้เวลา 19:30 น. Nonfarm Payrolls ซึ่งจัดเป็นรายการผลกระทบสูง ครั้งก่อนอยู่ที่ 57",
        ]}
        story = chart_story.build_story(self.rows, asset="xauusd", calendar=calendar)
        markdown = chart_story_writer.render_article(story)
        validation = chart_story_writer.validate(markdown, story)

        self.assertIn("## ปัจจัยพื้นฐานที่ต้องจับตา", markdown)
        self.assertIn("Nonfarm Payrolls", markdown)
        self.assertEqual(validation["status"], "pass", msg=str(validation["findings"]))

    def test_ไม่มีปฏิทินบทต้องไม่มีหัวข้อปัจจัยพื้นฐาน(self):
        self.assertNotIn("ปัจจัยพื้นฐานที่ต้องจับตา", self.markdown)

    def test_invalidation_อยู่ในโซนเข้าต้องตกด่าน(self):
        """🐞 D-1 (ฟีดแบ็กหัวหน้า 08-07): จุดเข้า = จุดตัดขาดทุน ⇒ ระยะเสี่ยงศูนย์

        เทสฝั่งเครื่องคิด (ด้านบน) กันการถอด `- atr` ออก — เทสนี้กันอีกชั้น:
        ต่อให้เครื่องคิดถูกเปลี่ยนไปยังไงในอนาคต ด่านของ validate ต้องจับ story
        ที่ invalidation อยู่ในโซนเข้าให้ตกเสมอ ตามที่หัวหน้าสั่ง
        "ถ้า Invalidation อยู่ในโซนเข้าหรือเท่ากับขอบโซน = ไม่วางไฟล์"
        """
        broken = json.loads(json.dumps(self.story))
        broken["scenarios"]["up"]["entry_invalidation"] = \
            broken["scenarios"]["up"]["entry_low"]          # ขอบโซนพอดี = เคสจริงที่เคยเกิด
        validation = chart_story_writer.validate(self.markdown, broken)

        self.assertEqual(validation["status"], "fail")
        self.assertTrue(any(f["rule"] == "invalidation_inside_entry_zone"
                            for f in validation["findings"]))

    def test_บทต้องประกาศว่าฉากทัศน์ไม่ใช่คำทำนาย(self):
        broken = self.markdown.replace("ไม่ใช่คำทำนาย", "")
        validation = chart_story_writer.validate(broken, self.story)

        self.assertTrue(any(f["rule"] == "scenario_disclaimer"
                            for f in validation["findings"]))

    def test_ห้ามมีตารางหรือbulletจนกว่าเว็บจะเพิ่มCSS(self):
        """ฟีดแบ็กหัวหน้า 08-07 — `.an-body` ยังไม่มี CSS ให้ `table`/`ul`

        ตารางเปล่าไม่มีเส้น bullet ไม่มีระยะห่าง อ่านแทบไม่ได้บนมือถือ — เขียนเป็น
        ย่อหน้าปกติจนกว่าฝั่งเว็บจะเพิ่ม `.an-body table/th/td` และ `.an-body ul`
        """
        for line in self.markdown.splitlines():
            stripped = line.strip()
            self.assertFalse(stripped.startswith(("- ", "* ", "|")),
                             msg=f"พบ bullet/table ที่ยังไม่มี CSS รองรับ: {line!r}")

    def test_พาดหัวต้องมีคำว่าทองคำ_S1(self):
        """S-1 (ฟีดแบ็กหัวหน้า 08-07) — จุดกระทบ SEO มากที่สุด: Title เดิมไม่มี
        คำว่า "ทองคำ" คนไทยค้น "ราคาทองวันนี้" ไม่ได้ค้น "XAU/USD" """
        title = self.markdown.splitlines()[0]
        self.assertIn("ทองคำ", title)
        self.assertIn("XAU/USD", title)

    def test_บทต้องมี_internal_link_S2(self):
        """S-2 (ฟีดแบ็กหัวหน้า 08-07) — เดิมไม่มี internal link เลยสักลิงก์
        ใช้เฉพาะที่อยู่จริงที่ทีมเว็บยืนยันแล้ว (EXTERNAL.md E5) ห้ามใส่โดเมนเต็ม"""
        self.assertIn("(/thailand/asset-xauusd)", self.markdown)
        self.assertIn("(/thailand/analysis)", self.markdown)
        self.assertNotIn("https://", self.markdown)
        self.assertNotIn("http://", self.markdown)


class ตัววาด(unittest.TestCase):

    def test_วาดสองใบได้ไฟล์จริงพร้อม_metadata(self):
        rows = make_rows()
        story = chart_story.build_story(rows, asset="xauusd")
        with tempfile.TemporaryDirectory() as tmp:
            overview_path = Path(tmp) / "overview.png"
            zoom_path = Path(tmp) / "zoom.png"
            overview = chart_story_renderer.render_overview(story, rows, overview_path)
            zoom = chart_story_renderer.render_zoom(story, rows, zoom_path)

            self.assertGreater(overview_path.stat().st_size, 10_000)
            self.assertGreater(zoom_path.stat().st_size, 10_000)
            self.assertEqual(overview["bars"], story["display"]["bars"])
            self.assertEqual(zoom["bars"], story["display"]["zoom_bars"])
            self.assertTrue(overview["elements"]["channel"])


class สายผลิต(unittest.TestCase):

    CUTOFF = "2026-08-06T12:00:00+00:00"

    def fake_fetcher(self, asset):
        return {"endpoint": "เทส"}, make_rows(), "ชุดเทส"

    @staticmethod
    def fake_calendar(asset):
        # เทสห้ามยิง snapshot API จริง — สายผลิตจริงเท่านั้นที่เรียก _calendar_block
        return None, "เทส"

    def _image_names(self):
        return chart_story_writer.image_names("xauusd", make_rows()[-1]["date"])

    def test_ผ่านด่านแล้ววางบทกับภาพครบชุด_และกวาดภาพชื่อยุคเก่า(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "06-082026" / chart_story_writer.FOLDER
            folder.mkdir(parents=True)
            (folder / "xauusd-1.png").write_bytes(b"png")  # ชื่อไฟล์ยุคเก่าค้างจากรอบก่อน
            result = chart_story_pipeline.run(
                asset="xauusd", publish_root=Path(tmp), cutoff_at=self.CUTOFF,
                fetcher=self.fake_fetcher, calendar_source=self.fake_calendar)

            self.assertEqual(result["status"], "pass", msg=str(result["findings"]))
            self.assertTrue((folder / "xauusd.md").exists())
            for name in self._image_names():
                self.assertTrue((folder / name).exists())
            self.assertFalse((folder / "xauusd-1.png").exists())

    def test_ตกด่านต้องไม่เหลือไฟล์แม้ของรอบก่อน(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "06-082026" / chart_story_writer.FOLDER
            folder.mkdir(parents=True)
            (folder / "xauusd.md").write_text("ของรอบก่อน", encoding="utf-8")
            (folder / "xauusd-1.png").write_bytes(b"png")
            failing = {"status": "fail", "fatal_count": 1, "char_count": 0,
                       "findings": [{"rule": "x", "severity": "fatal",
                                     "line": 1, "message": "เทส"}]}
            with mock.patch.object(chart_story_writer, "validate",
                                   return_value=failing):
                result = chart_story_pipeline.run(
                    asset="xauusd", publish_root=Path(tmp), cutoff_at=self.CUTOFF,
                    fetcher=self.fake_fetcher, calendar_source=self.fake_calendar)

            self.assertEqual(result["status"], "fail")
            self.assertTrue(result["removed_stale"])
            self.assertFalse((folder / "xauusd.md").exists())
            self.assertEqual(list(folder.glob("xauusd*.png")), [])

    def test_วาดล้มกลางคันต้องเก็บกวาดก่อนโยนต่อ(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(chart_story_renderer, "render_zoom",
                                   side_effect=RuntimeError("จอแตก")):
                with self.assertRaises(RuntimeError):
                    chart_story_pipeline.run(
                        asset="xauusd", publish_root=Path(tmp), cutoff_at=self.CUTOFF,
                        fetcher=self.fake_fetcher, calendar_source=self.fake_calendar)
            folder = Path(tmp) / "06-082026" / chart_story_writer.FOLDER
            self.assertEqual(list(folder.glob("xauusd*.png")), [])
            self.assertFalse((folder / "xauusd.md").exists())


if __name__ == "__main__":
    unittest.main()
