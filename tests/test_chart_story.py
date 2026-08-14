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
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import candle_close, chart_story, chart_story_pipeline  # noqa: E402
from tools import headline_format  # noqa: E402
from tools import chart_story_renderer, chart_story_writer, image_output  # noqa: E402

# ชุดแท่งจริงของทองคำถึง 2026-08-07 (ราคาปิดจริง 4,342.63) — ชุดเดียวกับที่ทีมเว็บ
# ดึงไปคำนวณใหม่แล้วยืนยันว่าเลขของเราตรงทั้ง swing / SMA50 / Fibonacci
REAL_ROWS = json.loads(
    (REPO_ROOT / "tests" / "fixtures" / "xau_420_sessions_2026-08-07.json")
    .read_text(encoding="utf-8"))


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
        entries = chart_story._entries(zones, 2.0)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["rank"], 1)
        self.assertEqual(entries[0]["price"], 95.0)
        # B-1: จุดยกเลิกต้องพ้นขอบล่างโซน 1×ATR ไม่ใช่เท่ากับขอบโซน (93.0 − 2.0)
        self.assertEqual(entries[0]["invalidation"], 91.0)
        self.assertEqual(chart_story._entries([], 2.0), [])

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

        self.assertIn(chart_story_writer.H2_CALENDAR, markdown)
        self.assertIn("Nonfarm Payrolls", markdown)
        self.assertEqual(validation["status"], "pass", msg=str(validation["findings"]))

    def test_ไม่มีปฏิทินบทต้องไม่มีหัวข้อปัจจัยพื้นฐาน(self):
        self.assertNotIn(chart_story_writer.H2_CALENDAR, self.markdown)

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

    def test_ไม่มีย่อหน้าคำเตือนความเสี่ยงในบทแล้ว(self):
        """ผู้ใช้สั่ง 08-14: เว็บมีคำเตือนของตัวเองอยู่แล้ว บทจึงไม่พกซ้ำ (ทำพร้อมสไตล์ E)

        ⚠️ ด่าน `risk_disclaimer` ถูกถอดพร้อมกัน — เทสนี้ยืนยันว่าถอดจริงทั้งคู่
        (ย่อหน้าหาย + validate ยังผ่าน) ไม่ใช่ถอดย่อหน้าแล้วลืมด่านจนบทตกทุกวัน
        · วลี "ไม่ใช่คำทำนาย" ของด่าน `scenario_disclaimer` ต้องรอดมาต่างหาก"""
        self.assertNotIn("คำเตือนความเสี่ยง", self.markdown)
        self.assertEqual(chart_story_writer.validate(self.markdown, self.story)["status"],
                         "pass")
        self.assertIn("ไม่ใช่คำทำนาย", self.markdown)

    def test_ห้ามมีตาราง_และbulletตามสวิตช์ของเว็บ(self):
        """🔄 กลับด้านครึ่งเดียว 08-11 บ่าย (ผู้ใช้สั่งหัวข้อ 3/4 เป็น bullet)

        กฎเดิม (ฟีดแบ็ก 08-07) ห้าม bullet เพราะ `.an-body` ไม่มี CSS ให้ `ul` —
        ข้อจำกัดนั้นย้ายไปอยู่ใต้สวิตช์ `web_bullets_enabled` แล้ว (เปิด 08-10)
        ⇒ D ต้องเดินตามสวิตช์เหมือน A/B/C และ F/G: **ปิดสวิตช์ = ร้อยแก้วทั้งใบ
        โดยไม่ต้องแก้โค้ด** · ส่วน**ตารางยังห้ามเสมอ** — ไม่เคยมีสวิตช์ของมัน
        """
        for line in self.markdown.splitlines():
            self.assertFalse(line.strip().startswith("|"),
                             msg=f"พบตารางที่ยังไม่มี CSS รองรับ: {line!r}")
        self.assertTrue(any(line.strip().startswith("- ")
                            for line in self.markdown.splitlines()),
                        "สวิตช์ bullet เปิดอยู่ (นโยบายจริง) แต่บทไม่มี bullet เลย")
        with mock.patch.object(chart_story_writer.wcb_writers.web_features,
                               "bullets_enabled", return_value=False):
            prose = chart_story_writer.render_article(self.story)
        for line in prose.splitlines():
            stripped = line.strip()
            self.assertFalse(stripped.startswith(("- ", "* ", "|")),
                             msg=f"ปิดสวิตช์แล้วยังเหลือ bullet/table: {line!r}")

    def test_ศัพท์เปลี่ยนตามคำสั่งผู้ใช้_08_11(self):
        """คำที่ผู้ใช้สั่งเปลี่ยน — คำเก่าทุกยุคห้ามหลงเหลือที่ไหนในบท:

            แต้มต่อราคา (Risk to Reward)   → อัตราส่วนความเสี่ยงต่อผลตอบแทน   (08-11)
            จุดยกเลิกมุมมอง (Invalidation) → จุดที่ต้องล้มเลิกความคิดเดิม      (08-11)
            จุดที่ต้องล้มเลิกความคิดเดิม   → จุด Stoploss                     (08-13)
        """
        for old in ("แต้มต่อราคา", "Risk to Reward", "จุดยกเลิกมุมมอง", "(Invalidation)",
                    "จุดที่ต้องล้มเลิกความคิดเดิม"):
            self.assertNotIn(old, self.markdown, f"คำเก่า '{old}' ยังหลงเหลือในบท")
        self.assertIn("จุด Stoploss", self.markdown)

    def test_ชื่อจุด_Stoploss_ต้องเรียกเหมือนกันทั้งบท(self):
        """ผู้ใช้ยกมาแค่ขั้นที่ 4 แต่คำนี้โผล่หลายที่ในบทเดียว — เปลี่ยนไม่ครบ
        = บทเดียวมีสองชื่อสำหรับของอย่างเดียวกัน ซึ่งแย่กว่าใช้ชื่อเก่าทั้งบท

        นับจากบทจริง: ต้องมีอย่างน้อยที่หัวข้อขั้นตอนเข้าเทรดและที่ฉากทัศน์
        """
        self.assertGreaterEqual(self.markdown.count("จุด Stoploss"), 2,
                                "คำนี้ควรโผล่หลายที่ในบท — ถ้าเหลือที่เดียวแปลว่ามีที่อื่นถูกเปลี่ยนพลาด")
        self.assertIn("**ขั้นที่ 4 —** จุด Stoploss:", self.markdown,
                      "ขั้นที่ 4 คือจุดที่ผู้ใช้ยกมาสั่งโดยตรง")

    def test_สรุปภาพรวมตอบครบสี่คำถาม(self):
        """ผู้ใช้สั่ง 08-11 บ่าย: สรุปต้องคม — ดูอะไร ทำไม อย่างไร แล้วจะเป็นอย่างไรต่อ
        (โผล่เมื่อมีระดับให้ดูจริง — story ของเทสนี้มีฉากทัศน์ฝั่งขึ้นครบ)"""
        for label in ("**ต้องดูอะไร:**", "**ทำไมต้องดูราคาปิด:**",
                      "**ทำอย่างไร:**", "**แล้วจะเป็นอย่างไรต่อ:**"):
            self.assertIn(label, self.markdown, f"สรุปภาพรวมขาดข้อ {label}")

    def test_พาดหัวต้องมีคำว่าทองคำ_S1(self):
        """S-1 (ฟีดแบ็กหัวหน้า 08-07) — จุดกระทบ SEO มากที่สุด: Title เดิมไม่มี
        คำว่า "ทองคำ" คนไทยค้น "ราคาทองวันนี้" ไม่ได้ค้น "XAU/USD"

        🆕 สเปก 2026-08-10 แบ่งหน้าที่ใหม่: **คำค้นภาษาคนอยู่ทั้งสองที่** ส่วน
        **สัญลักษณ์คู่เงินย้ายไปอยู่ใน Title tag** ซึ่งเป็นช่องที่ Google อ่านเป็นหัวข้อ
        (H1 เหลือไว้เล่าสาระของวัน) ⇒ ตรวจแยกกันตามหน้าที่ ไม่ใช่บังคับให้มีครบทั้งคู่
        """
        h1 = next(line for line in self.markdown.splitlines() if line.startswith("# "))
        self.assertIn("ทองคำ", h1)
        title = chart_story_writer.seo_title(self.story)
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
            overview_path = Path(tmp) / "overview.webp"
            zoom_path = Path(tmp) / "zoom.webp"
            overview = chart_story_renderer.render_overview(story, rows, overview_path)
            zoom = chart_story_renderer.render_zoom(story, rows, zoom_path)

            self.assertGreater(overview_path.stat().st_size, 10_000)
            self.assertGreater(zoom_path.stat().st_size, 10_000)
            self.assertEqual(overview["bars"], story["display"]["bars"])
            self.assertEqual(zoom["bars"], story["display"]["zoom_bars"])
            self.assertTrue(overview["elements"]["channel"])
            # กติกาเว็บ 08-09 — วัดจากไฟล์จริง ไม่ใช่เชื่อค่าคุณภาพที่ตั้งไว้
            for path, info in ((overview_path, overview), (zoom_path, zoom)):
                self.assertEqual(image_output.verify(path), info["bytes"])


class กรอบราคาต้องไม่ตัดกรอบแนวโน้มทิ้ง(unittest.TestCase):
    """ผู้ใช้แจ้ง 2026-08-10: "เส้นกราฟที่ตีมันขาดไป" — แผงซูมตั้งแกนราคาจากแท่งเทียน
    กับระดับที่บทพูดถึงเท่านั้น ไม่ได้นับกรอบแนวโน้ม เส้นจึงถูกขอบภาพตัด

    วัดของจริงวันนั้น (ทอง 120 แท่ง): แกนได้ 3,853–5,506 แต่กรอบแนวโน้มกินถึง
    3,510–5,554 ⇒ ขาดบน 47.86 ล่าง 343.50
    """

    def setUp(self):
        self.rows = make_rows()
        self.story = chart_story.build_story(self.rows, asset="xauusd")
        self.assertTrue(self.story["channel"], "ชุดเทสต้องมีกรอบแนวโน้มถึงจะวัดเรื่องนี้ได้")

    def _zoom_bounds(self):
        display = self.story["display"]
        n = display["zoom_bars"]
        x_right = n - 1 + n * chart_story_renderer.ZOOM_RIGHT_PAD_FRACTION
        geometry = chart_story_renderer._channel_geometry(
            self.story, n=n, x_right=x_right, view_offset=display["bars"] - n)
        view = self.rows[-n:]
        anchors = [r["low"] for r in view] + [r["high"] for r in view]
        low, high = min(anchors), max(anchors)
        pad = (high - low) * 0.06
        extents = chart_story_renderer._channel_extents(geometry, with_mid=False)
        return geometry, extents, chart_story_renderer._fit_range(low, high, pad, extents)

    def test_แกนราคาต้องขยายเพื่อรับกรอบแนวโน้ม(self):
        _, extents, bounds = self._zoom_bounds()
        self.assertLessEqual(min(extents), max(extents))
        self.assertLessEqual(bounds[0], min(extents) + 1e-6,
                             "ขอบล่างของแกนยังตัดกรอบแนวโน้มทิ้ง")
        self.assertGreaterEqual(bounds[1], max(extents) - 1e-6,
                                "ขอบบนของแกนยังตัดกรอบแนวโน้มทิ้ง")

    def test_เพดานกันแกนยืดจนแท่งถูกบีบ(self):
        """ฟีดแบ็กหัวหน้าข้อ 6 (08-06) — ขยายไม่จำกัดคือคนละบั๊กที่แย่พอกัน"""
        low, high, pad = 100.0, 200.0, 6.0
        span = (high + pad) - (low - pad)
        room = span * chart_story_renderer.CHANNEL_FIT_MAX_EXPANSION
        bounds = chart_story_renderer._fit_range(low, high, pad, [-10_000.0, 10_000.0])
        self.assertAlmostEqual(bounds[0], (low - pad) - room)
        self.assertAlmostEqual(bounds[1], (high + pad) + room)

    def test_เส้นที่ยังหลุดเพดานต้องถูกตัดในแนวนอน_ไม่ใช่ปล่อยขอบภาพตัด(self):
        # เส้นลาดลงจาก 150 ไป 50 แต่กรอบราคารับได้แค่ 100–200 ⇒ ต้องเหลือครึ่งแรก
        span = chart_story_renderer._segment_within(150.0, 50.0, 0.0, (100.0, 200.0))
        self.assertIsNotNone(span)
        self.assertAlmostEqual(span[0], 0.0)
        self.assertAlmostEqual(span[1], 0.5)

    def test_เส้นที่อยู่นอกกรอบทั้งเส้นต้องไม่ถูกวาดเลย(self):
        self.assertIsNone(
            chart_story_renderer._segment_within(10.0, 20.0, 0.0, (100.0, 200.0)))

    def test_ความหนาแถบถูกนับด้วย_ไม่ใช่วัดแค่เส้นกลาง(self):
        """แถบหนา ±band — วัดแต่เส้นกลางแล้วขอบแถบจะยังล้นออกไป"""
        self.assertIsNone(
            chart_story_renderer._segment_within(150.0, 150.0, 60.0, (100.0, 200.0)))
        self.assertIsNotNone(
            chart_story_renderer._segment_within(150.0, 150.0, 40.0, (100.0, 200.0)))


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
                fetcher=self.fake_fetcher, calendar_source=self.fake_calendar,
                zone_state_dir=Path(tmp) / "state")

            self.assertEqual(result["status"], "pass", msg=str(result["findings"]))
            # state ต้องถูกเขียนใน tmp ไม่ใช่โฟลเดอร์จริง (บทเรียน 08-10)
            self.assertTrue((Path(tmp) / "state" / "zones-xauusd.json").exists())
            self.assertTrue((folder / "xauusd.md").exists())
            for name in self._image_names():
                self.assertTrue((folder / name).exists())
            self.assertFalse((folder / "xauusd-1.png").exists())
            # ทุกใบที่วางลงโฟลเดอร์วันต้องผ่านกติกาเว็บ (.webp ≤ 200 KB)
            self.assertEqual(len(image_output.verify_folder(folder)), 2)

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
                    fetcher=self.fake_fetcher, calendar_source=self.fake_calendar,
                    zone_state_dir=Path(tmp) / "state")

            self.assertEqual(result["status"], "fail")
            # รอบตกด่านห้ามล็อกระดับ — ต้องไม่มี state ถูกเขียน
            self.assertFalse((Path(tmp) / "state" / "zones-xauusd.json").exists())
            self.assertTrue(result["removed_stale"])
            self.assertFalse((folder / "xauusd.md").exists())
            # กวาดต้องครอบรูปยุค `.png` ด้วย ไม่ใช่เฉพาะนามสกุลปัจจุบัน
            self.assertEqual(list(folder.glob("xauusd*")), [])

    def test_วาดล้มกลางคันต้องเก็บกวาดก่อนโยนต่อ(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(chart_story_renderer, "render_zoom",
                                   side_effect=RuntimeError("จอแตก")):
                with self.assertRaises(RuntimeError):
                    chart_story_pipeline.run(
                        asset="xauusd", publish_root=Path(tmp), cutoff_at=self.CUTOFF,
                        fetcher=self.fake_fetcher, calendar_source=self.fake_calendar,
                        zone_state_dir=Path(tmp) / "state")
            folder = Path(tmp) / "06-082026" / chart_story_writer.FOLDER
            self.assertEqual(list(folder.glob("xauusd*.webp")), [])
            self.assertFalse((folder / "xauusd.md").exists())


class แท่งที่ยังไม่ปิดห้ามถูกเรียกว่าปิด(unittest.TestCase):
    """🐞 **A-1 (ทีมเว็บตรวจรอบสาม 2026-08-09)** — บทเขียนว่า "แท่งล่าสุดปิดที่
    4,304.52" แต่ราคาปิดจริงของวันนั้นคือ 4,342.63 · ข้อมูลไม่ผิด แต่บทถูกผลิตขณะ
    แท่งรายวันยังก่อตัว ⇒ ตัวเลขในบทไม่ตรงกับกราฟบนหน้าเว็บเดียวกัน

    ผู้ใช้เลือก "ทาง 1": ผลิตหลังแท่งปิดแล้ว คงคำว่า "ปิด" ได้ — เทสชุดนี้ล็อกว่า
    ถ้อยคำถูกบังคับด้วย **สภาพจริงของแท่ง** ไม่ใช่ความเชื่อว่ารันถูกเวลา
    """

    @classmethod
    def setUpClass(cls):
        cls.story = chart_story.build_story(REAL_ROWS, asset="xauusd")
        cls.markdown = chart_story_writer.render_article(cls.story)

    def test_ชั้นข้อมูล_แท่งที่ยังไม่ปิดถูกตัดก่อนคำนวณทุกค่า(self):
        future = (date.today() + timedelta(days=1)).isoformat()
        rows = REAL_ROWS + [{**REAL_ROWS[-1], "date": future, "close": 1.0}]

        story = chart_story.build_story(rows, asset="xauusd")

        self.assertNotEqual(story["current"]["date"], future)
        self.assertEqual(story["candle_basis"]["dropped_forming_sessions"], [future])
        # ค่าที่ผูกกับแท่งล่าสุดต้องมาจากชุดเดียวกันทั้งหมด — ห้ามผสมปิดกับยังไม่ปิด
        self.assertEqual(story["atr14"], self.story["atr14"])
        self.assertEqual(story["sma50_last"], self.story["sma50_last"])

    def test_บทพูดราคาปิดจริงที่ทีมเว็บทานสอบแล้ว(self):
        self.assertEqual(self.story["current"]["date"], "2026-08-07")
        self.assertIn("แท่งล่าสุดปิดที่ 4,342.63 ดอลลาร์", self.markdown)
        self.assertNotIn("4,304.52", self.markdown)   # ราคาระหว่างวันของรอบที่มีอาการ

    def test_ด่านตกเมื่อไม่มีก้อนหลักฐานสถานะแท่ง(self):
        broken = json.loads(json.dumps(self.story))
        broken["candle_basis"] = None

        validation = chart_story_writer.validate(self.markdown, broken)

        self.assertEqual(validation["status"], "fail")
        self.assertTrue(any(f["rule"] == "closed_candle_required"
                            for f in validation["findings"]))

    def test_ด่านตกเมื่อแท่งฐานยังไม่ถึงเวลาปิด_แม้ธงจะบอกว่าปิดแล้ว(self):
        """หัวใจของ fail-closed: ตั้งธงเองแล้วผ่านด่านไม่ได้ ด่านคำนวณเวลาปิดใหม่เสมอ"""
        future = (date.today() + timedelta(days=1)).isoformat()
        broken = json.loads(json.dumps(self.story))
        broken["current"]["date"] = future
        broken["candle_basis"] = candle_close.basis_for("xauusd", future)
        broken["candle_basis"]["candle_state"] = "closed"

        validation = chart_story_writer.validate(self.markdown, broken)

        self.assertTrue(any(f["rule"] == "closed_candle_required"
                            for f in validation["findings"]))


class จุดยกเลิกต้องพ้นขอบโซนทุกคู่(unittest.TestCase):
    """🐞 **B-1 (ทีมเว็บ 2026-08-09)** — D-1 แก้เฉพาะโซน Retest จุดเดียว ทีมเว็บจึงยัง
    เจอ "จุดเข้าซื้อ 1 (Demand Zone) 3,944.04–4,037.54 · จุดยกเลิก: ปิดวันต่ำกว่า
    3,944.04" ซึ่งเท่ากับขอบล่างโซนพอดี — แตะโซนเมื่อไหร่ก็ยกเลิกทันที
    """

    @classmethod
    def setUpClass(cls):
        cls.story = chart_story.build_story(REAL_ROWS, asset="xauusd")
        cls.markdown = chart_story_writer.render_article(cls.story)

    def test_ชุดข้อมูลจริงต้องมีคู่ให้ตรวจมากกว่าหนึ่งคู่(self):
        """กันเทสข้างล่างกลายเป็นเทสว่างเปล่าเมื่อชุดข้อมูลเปลี่ยน"""
        pairs = chart_story_writer.invalidation_pairs(self.story)
        self.assertGreaterEqual(len(pairs), 2)
        self.assertTrue(any("จุดเข้าซื้อ" in pair["label"] for pair in pairs))

    def test_ทุกคู่ในบทจริงต้องห่างขอบโซนอย่างน้อยหนึ่งเท่าของ_ATR(self):
        for pair in chart_story_writer.invalidation_pairs(self.story):
            gap = chart_story.invalidation_gap_atr(
                pair["zone_low"], pair["zone_high"], pair["invalidation"],
                self.story["atr14"])
            self.assertGreaterEqual(round(gap, 6), chart_story.MIN_INVALIDATION_ATR,
                                    msg=pair["label"])

    def test_จุดเข้าซื้อที่จุดยกเลิกเท่ากับขอบโซนต้องตกด่าน(self):
        """เคสที่ทีมเว็บฟ้องมาเป๊ะ ๆ — เดิมด่านไม่เคยไล่ตรวจคู่นี้เลย"""
        broken = json.loads(json.dumps(self.story))
        broken["entries"][0]["invalidation"] = broken["entries"][0]["zone_low"]

        validation = chart_story_writer.validate(self.markdown, broken)

        self.assertEqual(validation["status"], "fail")
        self.assertTrue(any(f["rule"] == "invalidation_inside_entry_zone"
                            for f in validation["findings"]))

    def test_จุดยกเลิกห่างไม่ถึงหนึ่ง_ATR_ก็ยังต้องตก(self):
        """ไม่ใช่แค่ 'อยู่ในโซน' — ห่างแค่ 0.5×ATR ก็ยังทำตามจริงไม่ได้"""
        broken = json.loads(json.dumps(self.story))
        entry = broken["entries"][0]
        entry["invalidation"] = entry["zone_low"] - 0.5 * broken["atr14"]

        validation = chart_story_writer.validate(self.markdown, broken)

        self.assertTrue(any(f["rule"] == "invalidation_inside_entry_zone"
                            for f in validation["findings"]))


class ตัวนับอ้างอิงโซนต้องนับในโซนที่บทตีพิมพ์(unittest.TestCase):
    """🐞 **B-3.1 (ทีมเว็บ 2026-08-09 สงสัยว่าตัวนับมีเพดานที่ 7)** — ไม่มีเพดาน
    แต่เจอของที่แย่กว่า: `cluster_levels` รวมกลุ่มแบบลูกโซ่ กลุ่มจึงกว้างกว่าโซนที่
    บทตีพิมพ์ได้ · ข้อมูลจริง 08-07 กลุ่ม Demand Zone กิน 3,900.0–4,104.8 (2.1×ATR)
    แต่โซนที่บทเขียนคือ 3,942.19–4,039.38 ⇒ 2 ใน 7 ครั้งอยู่นอกโซนที่บทพูดถึง
    """

    @classmethod
    def setUpClass(cls):
        cls.story = chart_story.build_story(REAL_ROWS, asset="xauusd")

    def test_ไม่มีเพดานที่เจ็ด_แต่ทุกครั้งที่นับต้องอยู่ในโซนจริง(self):
        self.assertTrue(self.story["zones"])
        for zone in self.story["zones"]:
            self.assertEqual(zone["touches"], len(zone["touch_prices"]))
            for value in zone["touch_prices"]:
                self.assertGreaterEqual(value, zone["low"])
                self.assertLessEqual(value, zone["high"])

    def test_ตัวเลขที่เคยเกินจริงถูกแก้เป็นค่าที่ตรวจนับตามได้(self):
        """โซน Demand เคยอ้าง 7 ครั้ง ทั้งที่ในโซนมีจริง 5 — เลขต้องตรงกับที่นับได้"""
        demand = self.story["zones"][0]
        self.assertEqual(demand["touches"], 5)

    def test_ด่านตกเมื่อจำนวนครั้งไม่ตรงกับจุดที่อยู่ในโซน(self):
        story = json.loads(json.dumps(self.story))
        markdown = chart_story_writer.render_article(story)
        story["zones"][0]["touch_prices"].append(story["zones"][0]["low"] - 1.0)
        story["zones"][0]["touches"] += 1

        validation = chart_story_writer.validate(markdown, story)

        self.assertTrue(any(f["rule"] == "zone_touch_count_mismatch"
                            for f in validation["findings"]))


class พาดหัวตามสเปก_SEO(unittest.TestCase):
    """สเปกพาดหัวของหัวหน้า (ผ่านผู้ใช้ 2026-08-10) — ตัวอย่างที่ให้มาเป็นสัญญา

        Title : วิเคราะห์ทองคำวันนี้ 6 สิงหาคม 2026 — แนวโน้มราคาทอง XAU/USD
        H1    : วิเคราะห์ทองคำวันนี้ 6 ส.ค. 2026 — ทองยืน 4,262 รอ Fed ชี้ทาง

    🐞 **ยังต้องคุม B-3.3 ต่อ (ทีมเว็บ 2026-08-09)** — เดิม H1 เขียน "ทองคำโลก" แต่
    Title tag เขียน "ทองคำ" เพราะ Title ถูกพิมพ์มือ · สเปกใหม่สั่งให้สองอัน**ต่างกัน**
    ⇒ ต่างได้เฉพาะ**หาง** ส่วนหน้า (ชื่อสินทรัพย์ + วันที่) ต้องมาจากที่เดียวเสมอ
    """

    def setUp(self):
        self.story = chart_story.build_story(REAL_ROWS, asset="xauusd")
        self.markdown = chart_story_writer.render_article(self.story)
        # บรรทัดแรกคือ frontmatter ตั้งแต่ 2026-08-10 (ทุกสไตล์ต้องมี title) — หา H1 ด้วยรูปแบบ
        self.h1 = next(line for line in self.markdown.splitlines()
                       if line.startswith("# "))[2:]
        self.title = chart_story_writer.seo_title(self.story)

    def test_ส่วนหน้าคงที่ตามสเปก_ไม่ใช่ชื่อยาวที่ใช้ในเนื้อบท(self):
        for text in (self.title, self.h1):
            self.assertTrue(text.startswith("วิเคราะห์ทองคำวันนี้ "), text)
        # "ทองคำโลก" คือชื่อสำหรับเนื้อบท ไม่ใช่คำที่คนค้น — ห้ามหลุดมาที่พาดหัว
        self.assertNotIn("ทองคำโลก", self.title)
        self.assertNotIn("ทองคำโลก", self.h1)

    def test_Title_ใช้เดือนเต็ม_H1_ใช้เดือนย่อ(self):
        date_text = self.story["current"]["date"]
        self.assertIn(headline_format.thai_date(date_text, full_month=True), self.title)
        self.assertIn(headline_format.thai_date(date_text), self.h1)

    def test_ปีเป็น_คศ_ทั้งคู่(self):
        year = self.story["current"]["date"][:4]
        for text in (self.title, self.h1):
            self.assertIn(year, text)
            # กันการกลับไป พ.ศ. แบบเงียบ ๆ (หัวหน้าสั่งกลับเป็น ค.ศ. 08-11)
            self.assertNotIn(str(int(year) + 543), text)

    def test_Title_กับ_H1_ต้องไม่เหมือนกัน(self):
        """เงื่อนไขสำคัญที่หัวหน้าย้ำ — และส่วนหน้าต้องยังตรงกัน (กันบั๊ก B-3.3 กลับมา)"""
        self.assertNotEqual(self.title, self.h1)
        prefix = headline_format.prefix("xauusd", self.story["current"]["date"],
                                        full_month=False)
        self.assertTrue(self.h1.startswith(prefix))

    def test_ด่านตีตกเมื่อหางชนกัน(self):
        """เขียนชนกันเมื่อไหร่บทต้องไม่ออก ไม่ใช่ออกไปแล้วค่อยรู้ตอนขึ้นเว็บ"""
        clashed = self.markdown.replace(self.h1, self.title, 1)
        result = chart_story_writer.validate(clashed, self.story)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any(f["rule"] == "title_equals_h1" for f in result["findings"]),
                        [f["rule"] for f in result["findings"]])

    def test_หางของ_H1_ผูกกับราคาปิดจริง(self):
        self.assertIn(f"{self.story['current']['close']:,.0f}", self.h1)


class ย่อหน้าปฏิทินต้องบอกแหล่งเหมือนสไตล์อื่น(unittest.TestCase):
    """เก็บของค้างจากใบก่อน — A/B/C ปิดท้ายด้วยวลีที่มา แต่ D ปิดท้ายด้วยช่องว่างเปล่า
    ทั้งที่ยกตัวเลขจากปฏิทินเหมือนกัน (กฎเหล็ก: ปัจจัยพื้นฐานต้องมีแหล่งอ้างอิงเสมอ)
    """

    CALENDAR = {"sentences": [
        "พรุ่งนี้เวลา 19:30 น. Nonfarm Payrolls ซึ่งจัดเป็นรายการผลกระทบสูง ครั้งก่อนอยู่ที่ 57",
    ]}

    def setUp(self):
        self.story = chart_story.build_story(REAL_ROWS, asset="xauusd",
                                             calendar=self.CALENDAR)
        self.markdown = chart_story_writer.render_article(self.story)

    def test_มีวลีที่มาและไม่มีช่องว่างลอยท้ายย่อหน้า(self):
        self.assertIn(chart_story_writer.CALENDAR_SOURCE_NOTE.strip(), self.markdown)
        paragraph = next(line for line in self.markdown.splitlines()
                         if "ด่านแรกคือ" in line)
        self.assertEqual(paragraph, paragraph.rstrip())
        self.assertEqual(chart_story_writer.validate(self.markdown, self.story)["status"],
                         "pass")

    def test_ด่านตกเมื่อวลีที่มาหาย(self):
        broken = self.markdown.replace(chart_story_writer.CALENDAR_SOURCE_NOTE, "")

        validation = chart_story_writer.validate(broken, self.story)

        self.assertTrue(any(f["rule"] == "calendar_source_missing"
                            for f in validation["findings"]))


class เกณฑ์โซนไกลเกินแผนรายวัน(unittest.TestCase):
    """เกณฑ์คู่ ATR + เพดาน % (หัวหน้าเคาะข้อ 1ก · 2026-08-11)

    ตัวเลขในเทสนี้เป็นของจริงจากใบทอง 10 ส.ค. ที่ใช้ประกอบคำถามถึงหัวหน้า —
    ไม่ใช่ตัวเลขสมมติ เพื่อให้เทสตกตรงกับเคสที่เขาตีกลับจริง
    """

    PRICE = 4342.63

    def test_วันตลาดนิ่ง_ATR_เป็นตัวคุม(self):
        """ATR 1.07% → 10×ATR ≈ 10.7% ซึ่ง**เข้มน้อยกว่า**เพดาน 10% ⇒ เพดานคุมแทน"""
        atr = self.PRICE * 0.0107
        # 10.5% ห่าง — ผ่าน ATR (10.7%) แต่ต้องตกเพราะเกินเพดาน 10%
        level = self.PRICE * (1 - 0.105)
        self.assertFalse(chart_story.within_daily_entry_range(self.PRICE, level, atr))
        # 9% ห่าง — ผ่านทั้งคู่
        self.assertTrue(chart_story.within_daily_entry_range(
            self.PRICE, self.PRICE * (1 - 0.09), atr))

    def test_วันตลาดผันผวน_เพดานเปอร์เซ็นต์เป็นตัวคุม(self):
        """ATR 2.17% → 10×ATR ≈ 21.7% · นี่คือรูที่หัวหน้าชี้ว่าหลวมผิดจังหวะ"""
        atr = self.PRICE * 0.0217
        far = self.PRICE * (1 - 0.218)     # โซนที่ "เกือบผ่าน" ในใบจริง
        self.assertFalse(chart_story.within_daily_entry_range(self.PRICE, far, atr),
                         "โซนห่าง 21.8% ต้องตก — เกณฑ์ ATR ล้วนเคยปล่อยผ่าน")
        rejected_before = self.PRICE * (1 - 0.206)   # ใบที่หัวหน้าตีกลับรอบก่อน
        self.assertFalse(chart_story.within_daily_entry_range(
            self.PRICE, rejected_before, atr))

    def test_วันตลาดนิ่งมาก_ATR_ยังเข้มกว่าเพดาน(self):
        """ATR เล็ก ๆ ⇒ 10×ATR แคบกว่า 10% มาก — เพดานต้องไม่ไปผ่อนให้หลวมขึ้น"""
        atr = self.PRICE * 0.002          # 10×ATR = 2%
        level = self.PRICE * (1 - 0.05)   # 5% — ตกที่ ATR แต่ผ่านเพดาน
        self.assertFalse(chart_story.within_daily_entry_range(self.PRICE, level, atr),
                         "เพดาน % ต้องไม่กลายเป็นทางผ่านให้โซนที่ ATR ตีตกไปแล้ว")

    def test_เกณฑ์เป็น_AND_ไม่ใช่_OR(self):
        """สวมบั๊กกลับ: ถ้าใครเปลี่ยน `min` เป็น `max` เทสนี้ต้องตก

        เลือกจุดที่สองเกณฑ์ให้คำตอบต่างกัน ⇒ `or`/`max` จะปล่อยผ่าน `and`/`min` จะตี
        """
        atr = self.PRICE * 0.0217         # 10×ATR ≈ 21.7%
        level = self.PRICE * (1 - 0.15)   # ผ่าน ATR · เกินเพดาน 10%
        self.assertFalse(chart_story.within_daily_entry_range(self.PRICE, level, atr))

    def test_ใช้ได้ทั้งฝั่งบนและฝั่งล่างของราคา(self):
        atr = self.PRICE * 0.0107
        for direction in (1, -1):
            with self.subTest(direction=direction):
                near = self.PRICE * (1 + direction * 0.05)
                far = self.PRICE * (1 + direction * 0.15)
                self.assertTrue(chart_story.within_daily_entry_range(self.PRICE, near, atr))
                self.assertFalse(chart_story.within_daily_entry_range(self.PRICE, far, atr))


class โครงหัวข้อตามใบตัวอย่าง(unittest.TestCase):
    """ผู้ใช้สั่ง 2026-08-11 — ชื่อและลำดับหัวข้อยึด `01-CC/Input/ภาษาการเขียน/สไตล์D.md`

    ล็อกทั้งชุด ไม่ใช่ทีละหัว เพราะสิ่งที่เปลี่ยนคือ**โครงบท** (หกหัวข้อ → ห้า)
    ถ้าใครรีแฟกเตอร์แล้วหัวข้อกลับไปแยกเป็นหกหัวเงียบ ๆ เทสรายหัวจะไม่จับ
    """

    CALENDAR = {"sentences": [
        "พรุ่งนี้เวลา 19:30 น. Nonfarm Payrolls ซึ่งจัดเป็นรายการผลกระทบสูง ครั้งก่อนอยู่ที่ 57",
    ]}

    def _heads(self, markdown: str, mark: str) -> list[str]:
        return [line.strip() for line in markdown.splitlines() if line.startswith(mark + " ")]

    def test_มีปฏิทิน_ได้ห้าหัวข้อเรียงตามใบตัวอย่าง(self):
        story = chart_story.build_story(REAL_ROWS, asset="xauusd", calendar=self.CALENDAR)
        markdown = chart_story_writer.render_article(story)
        self.assertEqual(self._heads(markdown, "##"), [
            f"## 1. {chart_story_writer.H2_STRUCTURE}",
            f"## 2. {chart_story_writer.H2_LEVELS}",
            f"## 3. {chart_story_writer.H2_PLAN}",
            f"## 4. {chart_story_writer.H2_CALENDAR}",
            f"## 5. {chart_story_writer.H2_SUMMARY}",
        ])

    def test_ไม่มีปฏิทิน_เลขลำดับต้องปิดช่องว่างเอง(self):
        """หัวข้อปฏิทินหาย = เหลือสี่หัว และต้องนับ 1-2-3-4 ไม่ใช่ 1-2-3-5"""
        story = chart_story.build_story(REAL_ROWS, asset="xauusd")
        markdown = chart_story_writer.render_article(story)
        ordinals = [int(m.group(1)) for m in re.finditer(r"(?m)^## (\d+)\. ", markdown)]
        self.assertEqual(ordinals, [1, 2, 3, 4])
        self.assertIn(f"## 4. {chart_story_writer.H2_SUMMARY}", markdown)

    def test_หัวข้อย่อยต้องอยู่ในทะเบียนของใบตัวอย่างเท่านั้น(self):
        story = chart_story.build_story(REAL_ROWS, asset="xauusd", calendar=self.CALENDAR)
        markdown = chart_story_writer.render_article(story)
        allowed = (chart_story_writer.H3_SUPPLY, chart_story_writer.H3_DEMAND,
                   chart_story_writer.H3_BULLISH, chart_story_writer.H3_BEARISH)
        subheads = self._heads(markdown, "###")
        self.assertGreaterEqual(len(subheads), 3, subheads)
        for head in subheads:
            self.assertTrue(head.startswith(allowed), f"หัวข้อย่อยนอกทะเบียน: {head!r}")

    def test_ถอดหัวข้อแผนเข้าโซนรับออกจากบทแล้ว(self):
        """ผู้ใช้สั่ง 2026-08-14 — หัวข้อ 3 เหลือฉากทัศน์สองฝั่ง ไม่มีบล็อกจุดเข้าซื้อ"""
        story = chart_story.build_story(REAL_ROWS, asset="xauusd", calendar=self.CALENDAR)
        markdown = chart_story_writer.render_article(story)
        self.assertNotIn("แผนการเข้าเทรดบริเวณโซนรับ", markdown)
        self.assertNotIn("Execution Plan — ลำดับขั้นตอนก่อนเข้าเทรด", markdown)
        self.assertNotIn("จุดเข้าซื้อ 1 ที่", markdown)
        # ประโยคประกาศฉากทัศน์ยังต้องอยู่ — เป็นคำประกาศบังคับของด่าน
        self.assertIn("ไม่ใช่คำทำนาย", markdown)

    def test_ฉากทัศน์ฝั่งลงมีลำดับขั้นตอนแบบเดียวกับฝั่งขึ้น(self):
        """ผู้ใช้สั่ง 2026-08-14 — ฝั่งลงต้องมีตัวเลขให้ทำตาม ไม่ใช่มีแต่เงื่อนไข"""
        story = chart_story.build_story(REAL_ROWS, asset="xauusd", calendar=self.CALENDAR)
        down = story["scenarios"]["down"]
        self.assertIsNotNone(down, "ชุดข้อมูลนี้ต้องมีฉากทัศน์ฝั่งลงจึงจะทดสอบได้")
        markdown = chart_story_writer.render_article(story)
        self.assertIn("**ขั้นตอนเข้าเทรดฝั่งลง (Breakdown-Continuation):**", markdown)
        for step in ("**ขั้นที่ 1 —**", "**ขั้นที่ 2 —**", "**ขั้นที่ 3 —**", "**ขั้นที่ 4 —**"):
            self.assertIn(step, markdown)
        # จุดยกเลิกต้องอยู่**เหนือ**โซนเข้า (กระจกเงาของฝั่งขึ้น) และห่างพอตามเกณฑ์กลาง
        self.assertGreater(down["entry_invalidation"], down["entry_high"])
        self.assertLess(down["entry_low"], down["entry_high"])
        labels = [pair["label"] for pair in chart_story_writer.invalidation_pairs(story)]
        self.assertIn("จุดเข้าฝั่งลง (Breakdown-Continuation)", labels)
        self.assertEqual(chart_story_writer.validate(markdown, story)["findings"], [])


if __name__ == "__main__":
    unittest.main()
