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
from tools import chart_story_renderer, chart_story_writer, image_output, wcb_source, wcb_writers  # noqa: E402

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


class คำโปรยสไตล์ดี(unittest.TestCase):

    def test_ทองใช้ถ้อยคำฉบับที่ผู้ใช้เลือก(self):
        story = chart_story.build_story(REAL_ROWS, asset="xauusd")
        money = chart_story_writer.money_for(story)
        expected = (
            f"ราคาทองปิดล่าสุดที่ {money(story['current']['close'])} ดอลลาร์ "
            f"ยังมีแนวต้าน {money(story['resistance'][0]['mean'])} รออยู่ด้านบน "
            f"ขณะที่โซน {money(story['zones'][0]['mean'])} เป็นฐานรับสำคัญ "
            "มาดูกันว่าโครงสร้างกราฟรายวันกำลังบอกอะไร"
        )
        article = chart_story_writer.render_article(story)
        self.assertIn(f"excerpt: {expected}\n", article)
        self.assertNotIn("ทุกระดับคำนวณจากแท่งราคาจริง", article)


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

    def test_ระดับราคาเป็นตารางสามคอลัมน์และเรียงตามค่าจริง(self):
        header = "| ระดับเทคนิค | กรอบราคา (USD) | ความสำคัญและบทบาททางเทคนิค |"
        self.assertEqual(self.markdown.count(header), 1)
        self.assertNotIn(chart_story_writer.H3_SUPPLY, self.markdown)
        self.assertNotIn(chart_story_writer.H3_DEMAND, self.markdown)
        expected = [row["label"] for row in chart_story_writer._level_table_rows(self.story)]
        section = chart_story_writer._levels_section(self.markdown)
        actual = [chart_story_writer._table_cells(line)[0] for line in section
                  if line.strip().startswith("|")][2:]
        self.assertEqual(actual, expected)

    def test_ตารางระดับราคาที่สลับแถวหรือลบราคาปัจจุบันต้องตกด่าน(self):
        lines = self.markdown.splitlines()
        indexes = [i for i, line in enumerate(lines)
                   if line.startswith("| แนวต้าน") or line.startswith("| ราคาปัจจุบัน")]
        lines[indexes[0]], lines[indexes[1]] = lines[indexes[1]], lines[indexes[0]]
        swapped = "\n".join(lines)
        rules = {f["rule"] for f in chart_story_writer.validate(swapped, self.story)["findings"]}
        self.assertIn("levels_table_order", rules)
        missing = "\n".join(line for i, line in enumerate(self.markdown.splitlines())
                              if i != indexes[-1])
        rules = {f["rule"] for f in chart_story_writer.validate(missing, self.story)["findings"]}
        self.assertIn("levels_table_current", rules)

    def test_ข้อมูลระดับไม่ครบไม่มีแถวปลอม(self):
        story = json.loads(json.dumps(self.story))
        story["resistance"] = []
        story["zones"] = []
        story["sma50_last"] = None
        rows = chart_story_writer._level_table_rows(story)
        self.assertEqual([row["label"] for row in rows], ["ราคาปัจจุบัน"])

    def test_โซนเหนือราคาปัจจุบันไม่ถูกเรียกแนวรับ(self):
        story = json.loads(json.dumps(self.story))
        current = story["current"]["close"]
        story["zones"] = [{"low": current + 10, "high": current + 20, "touches": 1}]
        rows = chart_story_writer._level_table_rows(story)
        self.assertFalse(any(row["kind"] == "zone" for row in rows))

    def test_SMA_ที่อยู่ในโซนถูกรวมเป็นบทบาทไม่สร้างแถวซ้ำ(self):
        story = json.loads(json.dumps(self.story))
        current = story["current"]["close"]
        zone = {"low": current - 10, "high": current - 5, "touches": 2,
                "includes_week52_low": False}
        story["zones"] = [zone]
        story["sma50_last"] = zone["low"]
        rows = chart_story_writer._level_table_rows(story)
        self.assertFalse(any(row["kind"] == "sma" for row in rows))
        support = next(row for row in rows if row["kind"] == "zone")
        self.assertIn("เส้นค่าเฉลี่ยนี้ช่วยรองรับราคา", support["role_text"])

    def test_current_ที่ไม่ใช่ตัวเลขต้องหยุดก่อนสร้างตาราง(self):
        story = json.loads(json.dumps(self.story))
        story["current"]["close"] = float("nan")
        with self.assertRaises(ValueError):
            chart_story_writer._level_table_rows(story)

    def test_slug_D_แยกสไตล์และส่งซ้ำทับใบเดิมได้(self):
        expected = chart_story_writer.publication_slug(self.story, kind="levels")
        self.assertIn(f"slug: {expected}\n", self.markdown)
        self.assertRegex(expected, r"^xauusd-levels-\d{4}-\d{2}-\d{2}$")

        broken = self.markdown.replace(f"slug: {expected}", "slug: xauusd-signals-2026-08-21")
        validation = chart_story_writer.validate(broken, self.story)
        self.assertTrue(any(f["rule"] == "slug_invalid" for f in validation["findings"]))

    def test_บทวิเคราะห์สไตล์_D_ต้องไม่มี_emoji(self):
        """คำสั่งหัวหน้า 2026-08-18: ตัด Emoji ออกจากบทวิเคราะห์ทั้งหมด."""
        forbidden = "🟢🔴🟡✅⚠️📌📈📉"
        calendar = {"events": [{
            "at": "2026-08-20T19:30:00+07:00", "title": "Nonfarm Payrolls",
            "impact": "high", "forecast": "57", "previous": "42",
        }], "sentences": ["พรุ่งนี้มี Nonfarm Payrolls"]}
        with_calendar = chart_story_writer.render_article(
            chart_story.build_story(self.rows, asset="xauusd", calendar=calendar))
        self.assertFalse(set(self.markdown + with_calendar) & set(forbidden))

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
        event = {"at": "2026-08-20 19:30", "country": "USD", "impact": "High",
                 "title": "Nonfarm Payrolls", "actual": None,
                 "forecast": "80 พันตำแหน่ง", "previous": "57 พันตำแหน่ง"}
        calendar = {"sentences": [chart_story_pipeline._calendar_sentence(event)],
                    "events": [event], "week_start": "2026-08-17",
                    "week_end": "2026-08-21", "countries": ["USD"]}
        story = chart_story.build_story(self.rows, asset="xauusd", calendar=calendar)
        markdown = chart_story_writer.render_article(story)
        validation = chart_story_writer.validate(markdown, story)

        self.assertIn(chart_story_writer.H2_CALENDAR, markdown)
        self.assertIn(chart_story_writer.calendar_image_name(story), markdown)
        self.assertIn("วันจันทร์ถึงวันศุกร์", markdown)
        self.assertEqual(validation["status"], "pass", msg=str(validation["findings"]))

        broken = markdown.replace(f"({chart_story_writer.calendar_image_name(story)})",
                                  "(ภาพปฏิทินหาย)")
        self.assertTrue(any(finding["rule"] == "missing_image"
                            for finding in chart_story_writer.validate(broken, story)["findings"]))

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

    def test_บทไม่พกย่อหน้าฉากทัศน์ที่ผู้ใช้สั่งถอด(self):
        self.assertNotIn("ระดับฉากทัศน์ที่กำกับไว้บนภาพที่สอง", self.markdown)
        self.assertNotIn("ไม่ใช่คำทำนาย", self.markdown)
        self.assertEqual(chart_story_writer.validate(self.markdown, self.story)["status"],
                         "pass")

    def test_ชื่อสินทรัพย์ในร้อยแก้วไม่มีอักษรละตินติดคำไทยและไม่ซ้ำซ้อน(self):
        """🐞 บั๊กจากรอบเขียนใหม่ 08-14 — ใช้ `seo_name` (ชื่อสำหรับช่องคำค้น) ใน
        ร้อยแก้ว ⇒ "ราคาEUR/USD (EUR/USD)" กับ "ภาพรวมราคาSOLวันนี้"

        ไล่ครบทุกคู่ในทะเบียน ไม่ใช่แค่ทองคำ — บั๊กนี้มองไม่เห็นเลยถ้าดูแต่ xauusd
        (บทเรียนเดียวกับที่ `wcb_source` เตือนเรื่อง NVDA)
        """
        import re as _re
        for asset in ("xauusd", "eurusd", "gbpusd", "btcusd",
                      "nvda", "usdthb", "solusd", "wtiusd"):
            profile = wcb_source.profile_for(asset)
            with self.subTest(asset=asset):
                name = chart_story_writer._asset_name(profile)
                self.assertRegex(name, r"^[ก-๙\s]+$",
                                 "ชื่อในร้อยแก้วต้องเป็นไทยล้วน ไม่งั้นละตินติดคำไทย")
                self.assertNotRegex(name, r"^ราคา(ราคา|ค่าเงิน|หุ้น)",
                                    "คำนำหน้าซ้อนกันสองชั้น")

    def test_เส้น_MA50_ถูกพูดถึงครั้งเดียวในหัวข้อ_2(self):
        """มติ 08-18 — คงเส้นนี้เพียงรายการเดียวในกลุ่มแนวรับ/แนวต้าน"""
        markers = ("SMA50", "MA 50", "เส้นค่าเฉลี่ย 50 วัน")
        self.assertEqual(sum(self.markdown.count(marker) for marker in markers), 1)
        self.assertIn(f"{self.story['sma50_last']:,.2f}", self.markdown)
        if self.story["zones"]:
            self.assertIn("เส้นค่าเฉลี่ย 50 วัน", self.markdown)

    def test_ไม่มีย่อหน้าคำเตือนความเสี่ยงในบทแล้ว(self):
        """ผู้ใช้สั่ง 08-14: เว็บมีคำเตือนของตัวเองอยู่แล้ว บทจึงไม่พกซ้ำ (ทำพร้อมสไตล์ E)

        ⚠️ ด่าน `risk_disclaimer` ถูกถอดพร้อมกัน — เทสนี้ยืนยันว่าถอดจริงทั้งคู่
        (ย่อหน้าหาย + validate ยังผ่าน) ไม่ใช่ถอดย่อหน้าแล้วลืมด่านจนบทตกทุกวัน
        · ย่อหน้าฉากทัศน์และด่าน `scenario_disclaimer` ถูกถอดตามคำสั่งผู้ใช้ 08-24"""
        self.assertNotIn("คำเตือนความเสี่ยง", self.markdown)
        self.assertEqual(chart_story_writer.validate(self.markdown, self.story)["status"],
                         "pass")
        self.assertNotIn("ไม่ใช่คำทำนาย", self.markdown)

    def test_หัวข้อสรุปไม่ใช้ตาราง_และbulletตามสวิตช์ของเว็บ(self):
        """บรีฟ v2 ใช้ Weekly Executive Summary แบบ bulletin สามบรรทัด"""
        self.assertNotIn("| สถานการณ์ |", self.markdown)
        self.assertTrue(any(line.strip().startswith("- ")
                            for line in self.markdown.splitlines()),
                        "สวิตช์ bullet เปิดอยู่ (นโยบายจริง) แต่บทไม่มี bullet เลย")
        with mock.patch.object(chart_story_writer.wcb_writers.web_features,
                               "bullets_enabled", return_value=False):
            prose = chart_story_writer.render_article(self.story)
        for line in prose.splitlines():
            stripped = line.strip()
            self.assertFalse(stripped.startswith(("- ", "* ")),
                             msg=f"ปิดสวิตช์แล้วยังเหลือ bullet: {line!r}")

    def test_ศัพท์เปลี่ยนตามคำสั่งผู้ใช้_08_11(self):
        """คำที่ผู้ใช้สั่งเปลี่ยน — คำเก่าทุกยุคห้ามหลงเหลือที่ไหนในบท:

            แต้มต่อราคา (Risk to Reward)   → อัตราส่วนความเสี่ยงต่อผลตอบแทน   (08-11)
            จุดยกเลิกมุมมอง (Invalidation) → จุดที่ต้องล้มเลิกความคิดเดิม      (08-11)
            จุดที่ต้องล้มเลิกความคิดเดิม   → จุด Stoploss                     (08-13)
            จุด Stoploss                  → จุดตัดขาดทุน (Stop Loss)          (08-14)
        """
        for old in ("แต้มต่อราคา", "Risk to Reward", "จุดยกเลิกมุมมอง", "(Invalidation)",
                    "จุดที่ต้องล้มเลิกความคิดเดิม", "จุด Stoploss"):
            self.assertNotIn(old, self.markdown, f"คำเก่า '{old}' ยังหลงเหลือในบท")
        for old in ("จุดกลับตัวจริง (Swing Points)", "โซน Unfilled Supply",
                    "เป้าหมายกำไร (Take Profit)", "ขั้นตอนปฏิบัติ (Execution Steps)"):
            self.assertNotIn(old, self.markdown)
        self.assertIn("มักชะลอตัวหรือเปลี่ยนทิศ", self.markdown)
        self.assertIn("ระดับโครงสร้างที่มีหลักฐานการทดสอบ", self.markdown)

    def test_ฉากทัศน์ไม่เขียนเป็นใบสั่งเข้าเทรด(self):
        for phrase in ("จุดตัดขาดทุน", "เปิดสถานะ Buy", "เปิดสถานะ Sell",
                       "แผนการเทรด", "เป้าหมายกำไร"):
            self.assertNotIn(phrase, self.markdown)
        self.assertEqual(self.markdown.count(chart_story_writer.H2_LEVELS), 1)
        self.assertEqual(self.markdown.count(chart_story_writer.H2_SCENARIOS), 1)

    def test_ฉากทัศน์และสรุปใช้โครงบรีฟ_v2(self):
        up = self.story["scenarios"]["up"]
        self.assertIsNotNone(up, "story ของเทสนี้ต้องมีฉากทัศน์ฝั่งขึ้น")
        expected_scenarios = sum(bool(self.story["scenarios"].get(side))
                                 for side in ("up", "down"))
        self.assertEqual(self.markdown.count("**เงื่อนไขทางเทคนิค:**"),
                         expected_scenarios)
        self.assertEqual(self.markdown.count("**ปัจจัยข่าวชี้นำ:**"),
                         expected_scenarios)
        self.assertIn("**เป้าหมายราคา:**", self.markdown)
        self.assertIn("ราคาปิดรายวันสูงกว่า", self.markdown)
        if self.story["scenarios"]["down"]:
            self.assertIn("**แนวรับถัดไป:**", self.markdown)
            self.assertIn("ราคาปิดรายวันต่ำกว่า", self.markdown)
        for label in ("**ทิศทางหลักสัปดาห์นี้:**",
                      "**กรอบราคาประจำสัปดาห์:**",
                      "**จุดเปลี่ยนโมเมนตัม (Key Pivot):**"):
            self.assertEqual(self.markdown.count(label), 1)
        for old in ("**ผลที่ต้องติดตาม:**", "**ผลลัพธ์ทางเทคนิค:**",
                    "**เงื่อนไขฝั่งขึ้น:**", "**เงื่อนไขฝั่งลง:**"):
            self.assertNotIn(old, self.markdown)
        self.assertNotIn("ส่วนระดับราคาที่อยู่ไกลกว่านี้ใช้สำหรับดูโครงสร้างหลัก",
                         self.markdown)

    def test_ปัจจัยข่าวในฉากทัศน์มาจาก_calendar_evidence(self):
        events = [
            {"at": "2026-08-20 19:30", "country": "USD", "impact": "Medium",
             "title": "ดัชนีภาคการผลิต", "family_id": "us_empire_state"},
            {"at": "2026-08-20 20:30", "country": "USD", "impact": "Medium",
             "title": "ถ้อยแถลงของเฟด", "family_id": "us_fed_speeches"},
            {"at": "2026-08-21 19:30", "country": "USD", "impact": "High",
             "title": "จำนวนผู้ขอรับสวัสดิการว่างงาน",
             "family_id": "us_initial_jobless_claims"},
        ]
        calendar = {"sentences": [chart_story_pipeline._calendar_sentence(event)
                                  for event in events],
                    "events": events, "week_start": "2026-08-17",
                    "week_end": "2026-08-21", "countries": ["USD"]}
        story = chart_story.build_story(REAL_ROWS, asset="xauusd", calendar=calendar)
        markdown = chart_story_writer.render_article(story)

        self.assertIsNotNone(story["scenarios"]["up"])
        self.assertIsNotNone(story["scenarios"]["down"])
        self.assertIn("จำนวนผู้ขอรับสวัสดิการว่างงาน: มากกว่าคาดการณ์", markdown)
        self.assertIn("จำนวนผู้ขอรับสวัสดิการว่างงาน: น้อยกว่าคาดการณ์", markdown)
        self.assertIn("ดัชนีภาคการผลิต: น้อยกว่าคาดการณ์", markdown)
        self.assertIn("ดัชนีภาคการผลิต: มากกว่าคาดการณ์", markdown)
        self.assertNotIn("ถ้อยแถลงของเฟด:", markdown)
        self.assertEqual(chart_story_writer.validate(markdown, story)["status"], "pass")

    def test_ด่านปฏิเสธโครงบรรณาธิการเก่าที่แทรกกลับมา(self):
        broken = self.markdown.replace(
            "**เงื่อนไขทางเทคนิค:**", "**ผลที่ต้องติดตาม:**", 1)
        rules = {finding["rule"]
                 for finding in chart_story_writer.validate(broken, self.story)["findings"]}
        self.assertIn("editorial_v2_contract", rules)

    def test_ด่านปฏิเสธลูกศรในสรุปรายสัปดาห์(self):
        broken = self.markdown.replace(
            "**จุดเปลี่ยนโมเมนตัม (Key Pivot):**",
            "**จุดเปลี่ยนโมเมนตัม (Key Pivot):** ➔", 1)
        rules = {finding["rule"]
                 for finding in chart_story_writer.validate(broken, self.story)["findings"]}
        self.assertIn("arrow_forbidden", rules)

    def test_สรุปร้อยแก้วผ่านด่านตัวเลข(self):
        self.assertNotIn("| สถานการณ์ |", self.markdown)
        self.assertEqual(chart_story_writer.validate(self.markdown, self.story)["status"],
                         "pass")

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

    def test_คำว่าราคาทองคำต้นเรื่องลิงก์ไปหน้าทอง_S3(self):
        """คำสั่งผู้ใช้ 08-19 — ลิงก์เฉพาะคำ ไม่ครอบราคา/ข้อสรุปทั้งประโยค"""
        body = self.markdown.split("---", 2)[-1]
        paragraphs = [part.strip() for part in body.split("\n\n") if part.strip()]
        opening = next(part for part in paragraphs if "ปิดที่" in part)
        self.assertTrue(
            opening.startswith("&emsp;[ราคาทองคำ](/thailand/asset-xauusd)ปิดที่ "),
            f"ประโยคเปิดไม่ได้ลิงก์เฉพาะคำว่า ราคาทองคำ: {opening!r}",
        )
        first_h2 = body.index(f"## {chart_story_writer.H2_STRUCTURE}")
        self.assertGreater(body.index(opening), first_h2,
                           "ราคา/วันที่/แนวโน้มต้องย้ายมาอยู่ใต้หัวข้อแรก")

    def test_สินทรัพย์อื่นไม่รับลิงก์หน้าทองในประโยคเปิด_S3(self):
        """ขอบเขตคำสั่ง 08-19 ต้องไม่ทำให้บทของสินทรัพย์อื่นชี้ไปหน้าทอง"""
        story = chart_story.build_story(self.rows, asset="eurusd")
        markdown = chart_story_writer.render_article(story)
        body = markdown.split("---", 2)[-1]
        paragraphs = [part.strip() for part in body.split("\n\n") if part.strip()]
        opening = next(part for part in paragraphs if "ปิดที่" in part)

        self.assertNotIn("/thailand/asset-xauusd", opening)
        self.assertTrue(opening.startswith("&emsp;ราคายูโรปิดที่ "), opening)

    def test_ก่อนหัวข้อแรกมีเฉพาะคำโปรยตามต้นแบบ_และร้อยแก้วเยื้องหนึ่ง_tab(self):
        body = self.markdown.split("---", 2)[-1]
        lines = body.splitlines()
        h1_index = next(i for i, line in enumerate(lines) if line.startswith("# "))
        h2_index = next(i for i, line in enumerate(lines) if line.startswith("## "))
        before_first_h2 = [line.strip() for line in lines[h1_index + 1:h2_index]
                           if line.strip() and line.strip() != "---"]
        self.assertEqual(len(before_first_h2), 1)
        self.assertRegex(before_first_h2[0], r"^\*\*.+\*\*$")

        list_item = re.compile(r"^\s*(?:[-+*]\s|\d+\.\s)")
        standalone_bold = re.compile(r"^\*\*.+\*\*$")
        for line in lines[h2_index + 1:]:
            self.assertEqual(line, line.rstrip(), f"มีช่องว่างลอยท้ายบรรทัด: {line!r}")
            stripped = line.strip()
            if (not stripped or stripped.startswith(("#", "![", "|")) or stripped == "---"
                    or list_item.match(line) or standalone_bold.fullmatch(stripped)):
                continue
            self.assertTrue(line.startswith(chart_story_writer.PROSE_INDENT), line)
            sentence_count = len(re.split(r"(?<=[.!?])\s+", stripped))
            self.assertLessEqual(sentence_count, 3, line)


class ตัววาด(unittest.TestCase):

    def test_ขยายตัวอักษรโดยคง_canvas_เดิม(self):
        self.assertEqual(chart_story_renderer.KEY_TEXT_SCALE, 1.20)
        self.assertEqual(chart_story_renderer.SECONDARY_TEXT_SCALE, 1.10)
        self.assertEqual(tuple(size * chart_story_renderer.DPI
                               for size in chart_story_renderer.FIGURE_SIZE),
                         (1920.0, 1080.0))
        self.assertEqual(tuple(size * chart_story_renderer.DPI
                               for size in chart_story_renderer.CALENDAR_TABLE_ONLY_FIGURE_SIZE),
                         (1920.0, 1140.0))
        self.assertIsNone(chart_story_renderer.ZOOM_FOOTER_TEXT)
        self.assertEqual(chart_story_renderer.CALENDAR_SOURCE_TEXT,
                         "ที่มา: ปฎิทินเศรษฐกิจ World Class Broker")

    def test_แนวต้านรองเป็นเส้นทึบเต็มกราฟและติดราคาเฉพาะขอบขวา(self):
        story = chart_story.build_story(REAL_ROWS, asset="xauusd")
        secondary = sorted(story["resistance"], key=lambda level: level["mean"])[1:3]
        specs = chart_story_renderer.secondary_resistance_line_specs(story, secondary)

        self.assertEqual(len(specs), 2)
        self.assertEqual([spec["value"] for spec in specs],
                         [level["mean"] for level in secondary])
        for spec in specs:
            self.assertEqual(spec["linestyle"], "-")
            self.assertEqual(spec["span"], "full_plot")
            self.assertEqual(spec["label_position"], "right_axis")
            self.assertEqual(spec["tag"], chart_story_renderer.money_for(story)(spec["value"]))

    def test_ภาพโครงสร้างแยกแนวโน้มหลักออกจากกรอบย่อย(self):
        story = chart_story.build_story(REAL_ROWS, asset="xauusd")
        candidate = json.loads(json.dumps(story))
        candidate["regime"]["down"] = True
        candidate["current"]["close"] = max(
            candidate["channel"]["main_at_last"],
            candidate["channel"]["parallel_at_last"],
            candidate["sma50_last"],
        ) + 1.0
        candidate["scenarios"]["up"]["trigger"] = candidate["current"]["close"] + 100.0

        status = chart_story_renderer.structure_status(candidate)
        self.assertEqual(status["primary"], "ลง")
        self.assertEqual(status["channel"], "ทะลุ")
        self.assertTrue(status["above_sma"])
        self.assertFalse(status["reversal_confirmed"])

    def test_ภาพรวมมีทั้งเส้นกดขาลงและเส้นยกจากฐาน(self):
        story = chart_story.build_story(REAL_ROWS, asset="xauusd", display_bars=180)
        trends = story["overview_trends"]

        self.assertLess(trends["descending_resistance"]["slope"], 0)
        self.assertGreater(trends["ascending_support"]["slope"], 0)
        self.assertEqual(trends["descending_resistance"]["anchor_dates"],
                         ["2026-01-29", "2026-03-02"])
        self.assertEqual(trends["ascending_support"]["anchor_dates"],
                         ["2026-06-30", "2026-07-17"])
        geometry = chart_story_renderer._overview_trend_geometry(story, n=180)
        self.assertEqual(list(geometry), ["descending_resistance"])

    def test_กรอบโครงสร้างหยุดที่แท่งล่าสุดไม่ลากไปพื้นที่อนาคต(self):
        story = chart_story.build_story(REAL_ROWS, asset="xauusd")
        n = story["display"]["bars"]
        x_right = n - 1 + n * chart_story_renderer.RIGHT_PAD_FRACTION
        geometry = chart_story_renderer._channel_geometry(
            story, n=n, x_right=x_right)
        self.assertEqual(geometry["xs"][-1], n - 1)
        self.assertEqual(geometry["mid_xs"][-1], n - 1)

    def test_แผนที่ตัดสินใจใช้ราคาปิดและขอบล่างโซน(self):
        story = chart_story.build_story(REAL_ROWS, asset="xauusd")
        plan = chart_story_renderer.decision_map(story)

        self.assertEqual(plan["close"], story["current"]["close"])
        self.assertEqual(plan["bullish_confirmation"],
                         story["scenarios"]["up"]["trigger"])
        self.assertEqual(plan["invalidation"], plan["zone"]["low"])
        self.assertNotEqual(plan["invalidation"], plan["zone"]["mean"])
        expected_role = ("support" if plan["close"] >= plan["sma50"] else "resistance")
        self.assertEqual(plan["sma_role"], expected_role)
        self.assertEqual(
            plan["secondary_resistance"],
            story["scenarios"]["up"]["targets"][:1],
        )

    def test_callout_แผนที่ตัดสินใจสื่อความหมายอย่างเดียวไม่มีราคา(self):
        story = chart_story.build_story(REAL_ROWS, asset="xauusd")
        plan = chart_story_renderer.decision_map(story)
        labels = chart_story_renderer._zoom_callout_labels(story, plan)

        self.assertEqual(labels, {
            "bullish": "ยืนยันขาขึ้น · ปิด D1 เหนือเส้น",
            "bearish": "ยืนยันขาลง · ปิด D1 ต่ำกว่าฐาน",
            "current": "ราคาปัจจุบัน",
            "zone": "ฐานหลัก",
            "sma50": "MA50",
        })
        joined = " ".join(labels.values())
        money = chart_story_renderer.money_for(story)
        price_values = [plan["bullish_confirmation"], plan["invalidation"],
                        plan["close"], plan["sma50"], plan["zone"]["high"]]
        for value in price_values:
            self.assertNotIn(money(value), joined)
        self.assertNotIn("รับแรก", joined)
        self.assertNotIn("ด่านแรก", joined)
        self.assertNotIn("ดีขึ้น", joined)
        self.assertNotIn("แย่ลง", joined)

    def test_price_tag_ขวาครบห้าบทบาทและไม่มีราคาปัจจุบันหรือกึ่งกลางฐาน(self):
        story = chart_story.build_story(REAL_ROWS, asset="xauusd")
        plan = chart_story_renderer.decision_map(story)
        secondary_specs = chart_story_renderer.secondary_resistance_line_specs(
            story, list(plan["secondary_resistance"]))
        tags = chart_story_renderer._zoom_right_tag_specs(
            story, plan, secondary_specs)
        money = chart_story_renderer.money_for(story)

        self.assertEqual(
            [tag["role"] for tag in tags],
            ["bullish_confirmation", "zone_low", "zone_high", "sma50",
             "secondary_resistance"],
        )
        self.assertEqual(
            [tag["y"] for tag in tags],
            [plan["bullish_confirmation"], plan["zone"]["low"],
             plan["zone"]["high"], plan["sma50"], secondary_specs[0]["value"]],
        )
        self.assertEqual(len({tag["text"] for tag in tags}), len(tags))
        self.assertNotIn(money(plan["close"]), [tag["text"] for tag in tags])
        self.assertNotIn(money(plan["zone"]["mean"]),
                         [tag["text"] for tag in tags])

    def test_หัว_levels_เหลือรายละเอียดต่อท้าย_d1_บรรทัดเดียว(self):
        story = chart_story.build_story(REAL_ROWS, asset="xauusd")
        title, detail = chart_story_renderer.zoom_header_parts(story, 120)

        self.assertEqual(title, "XAU/USD · รายวัน (D1)")
        self.assertEqual(
            detail,
            f"120 แท่ง · ข้อมูลถึง "
            f"{chart_story_renderer.thai_date(story['current']['date'])} · "
            f"ปิด {chart_story_renderer.money_for(story)(story['current']['close'])}",
        )
        self.assertNotIn("แผนที่ตัดสินใจ", detail)

    def test_จุดราคาปัจจุบันในภาพ_levels_ใช้กรอบสี่เหลี่ยมมุมมน(self):
        story = chart_story.build_story(REAL_ROWS, asset="xauusd")
        label = chart_story_renderer.current_price_label(
            story, story["current"]["close"])

        self.assertEqual(chart_story_renderer.CURRENT_PRICE_MARKER, "s")
        self.assertTrue(
            chart_story_renderer.CURRENT_PRICE_BOXSTYLE.startswith("round,"))
        self.assertGreater(chart_story_renderer.CURRENT_PRICE_LABEL_X_OFFSET, 0.8)
        self.assertLess(chart_story_renderer.SCENARIO_ARROW_ALPHA, 1.0)
        self.assertEqual(label, "ราคาปัจจุบัน")
        self.assertNotIn("\n", label)

    def test_แผนที่ตัดสินใจคงฐานหลักแม้ไม่มี_daily_entry(self):
        story = chart_story.build_story(REAL_ROWS, asset="xauusd")
        candidate = json.loads(json.dumps(story))
        for zone in candidate["zones"]:
            zone["daily_entry"] = False

        plan = chart_story_renderer.decision_map(candidate)

        self.assertIs(plan["zone"], candidate["zones"][0])
        self.assertEqual(plan["invalidation"], candidate["zones"][0]["low"])

    def test_ป้ายฐานหลักกับป้ายหลุดฐานอยู่คนละด้านของโซน(self):
        story = chart_story.build_story(REAL_ROWS, asset="xauusd")
        zone = chart_story_renderer.decision_map(story)["zone"]
        layout = chart_story_renderer.decision_label_layout(zone, story["atr14"])

        self.assertGreater(layout["zone_y"], zone["high"])
        self.assertEqual(layout["zone_va"], "bottom")
        self.assertLess(layout["invalidation_y"], zone["low"])
        self.assertEqual(layout["invalidation_va"], "top")

    def test_สถานะแผนที่ตัดสินใจเปลี่ยนจากราคาปิดเท่านั้น(self):
        story = chart_story.build_story(REAL_ROWS, asset="xauusd")
        zone = next(zone for zone in story["zones"] if zone["daily_entry"])
        confirm = story["scenarios"]["up"]["trigger"]

        cases = (
            (confirm + 1.0, "bullish_confirmation"),
            (zone["low"] - 1.0, "bearish_continuation"),
            (story["sma50_last"] + 1.0, "recovery_not_confirmed"),
            (story["sma50_last"] - 1.0, "weak_below_sma50"),
        )
        for close, expected in cases:
            with self.subTest(expected=expected):
                candidate = json.loads(json.dumps(story))
                candidate["current"]["close"] = close
                self.assertEqual(chart_story_renderer.decision_map(candidate)["state"],
                                 expected)

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
            self.assertFalse(overview["elements"]["channel"])
            self.assertEqual(overview["elements"]["trend_lines"],
                             sum(line is not None
                                 for line in story["overview_trends"].values()))
            self.assertTrue(zoom["elements"]["decision_map"])
            self.assertFalse(zoom["elements"]["current_price_right_tag"])
            self.assertFalse(zoom["elements"]["legacy_channel_band"])
            self.assertIsInstance(zoom["elements"]["descending_trendline"], bool)
            self.assertFalse(overview["elements"]["sma50"])
            self.assertTrue(zoom["elements"]["sma50"])
            expected_secondary = len(
                chart_story_renderer.decision_map(story)["secondary_resistance"])
            self.assertEqual(zoom["elements"]["secondary_resistance_lines"],
                             expected_secondary)
            self.assertEqual(zoom["elements"]["resistance_visible"],
                             1 + expected_secondary)
            self.assertEqual(zoom["levels"]["invalidation"],
                             zoom["levels"]["zone_low"])
            # กติกาเว็บ 08-09 — วัดจากไฟล์จริง ไม่ใช่เชื่อค่าคุณภาพที่ตั้งไว้
            for path, info in ((overview_path, overview), (zoom_path, zoom)):
                self.assertEqual(image_output.verify(path), info["bytes"])

    def test_วาดตารางปฏิทินรายสัปดาห์เป็นภาพที่สาม(self):
        event = {"at": "2026-08-20 19:30", "country": "USD", "impact": "High",
                 "title": "ดัชนีภาคการผลิต", "actual": None,
                 "forecast": "24.1 จุด", "previous": "41.4 จุด",
                 "family_id": "us_empire_state", "relevance": "indirect",
                 "asset_effect": "บวก"}
        calendar = {"sentences": [chart_story_pipeline._calendar_sentence(event)],
                    "events": [event], "week_start": "2026-08-17",
                    "week_end": "2026-08-21", "countries": ["USD"],
                    "table_only": True}
        story = chart_story.build_story(REAL_ROWS, asset="xauusd", calendar=calendar)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / chart_story_writer.calendar_image_name(story)
            info = chart_story_renderer.render_weekly_calendar(story, path)
            self.assertEqual(info["rows"], 1)
            self.assertEqual(info["week_start"], "2026-08-17")
            self.assertEqual(info["palette"],
                             {"green": "#0E2A1D", "gold": "#C9A227"})
            self.assertNotIn("ผลจริง", info["columns"])
            self.assertEqual(info["columns"][-2:],
                             ["เงื่อนไขขาลง", "เงื่อนไขขาขึ้น"])
            self.assertNotIn("ทิศทางต่อสินทรัพย์", info["columns"])
            self.assertEqual(info["effects"], ["สูง · บวก"])
            self.assertEqual(info["conditions"], [{
                "bearish": "มากกว่าคาดการณ์",
                "bullish": "น้อยกว่าคาดการณ์"}])
            self.assertEqual(info["canvas"], [1920, 1140])
            self.assertEqual(info["source_text"],
                             "ที่มา: ปฎิทินเศรษฐกิจ World Class Broker")
            self.assertAlmostEqual(info["source_y"], 0.01789474, places=6)
            self.assertEqual(info["outer_margins_px"], [40.8, 40.8])
            self.assertGreaterEqual(info["table_area_fraction"], 0.69)
            self.assertGreater(path.stat().st_size, 10_000)
            self.assertEqual(image_output.verify(path), info["bytes"])
            self.assertEqual(chart_story_renderer.CALENDAR_WEBP_QUALITY, 84)
            self.assertGreaterEqual(chart_story_renderer.CALENDAR_WEBP_QUALITY,
                                    image_output.MIN_WEBP_QUALITY)

    def test_เงื่อนไขปฏิทินแยกขาลงขาขึ้นและไม่เดาข่าวที่ไม่รู้จัก(self):
        normal = {"family_id": "us_empire_state", "title_en": "Empire State"}
        jobless = {"family_id": "us_initial_jobless_claims",
                   "title_en": "Initial Jobless Claims"}
        speech = {"family_id": "us_fed_official_speeches",
                  "title_en": "Fed Barkin Speech"}
        mortgage = {"family_id": "us_housing_activity",
                    "title_en": "MBA 30-Year Mortgage Rate"}

        self.assertEqual(chart_story_renderer.calendar_split_conditions(
            normal, "xauusd"), ("มากกว่าคาดการณ์", "น้อยกว่าคาดการณ์"))
        self.assertEqual(chart_story_renderer.calendar_split_conditions(
            jobless, "xauusd"), ("น้อยกว่าคาดการณ์", "มากกว่าคาดการณ์"))
        self.assertEqual(chart_story_renderer.calendar_split_conditions(
            speech, "xauusd"), ("เข้มงวด", "ผ่อนคลาย"))
        self.assertEqual(chart_story_renderer.calendar_split_conditions(
            mortgage, "xauusd"), ("ดอกเบี้ยขึ้น", "ดอกเบี้ยลง"))
        self.assertEqual(chart_story_renderer.calendar_split_conditions(
            {"family_id": "unknown"}, "xauusd"), ("รอผลจริง", "รอผลจริง"))


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

    @staticmethod
    def fake_weekly_calendar(asset):
        event = {"at": "2026-08-20 19:30", "country": "USD", "impact": "High",
                 "title": "รายการทดสอบ", "actual": None,
                 "forecast": "24.1 จุด", "previous": "41.4 จุด"}
        return ({"sentences": [chart_story_pipeline._calendar_sentence(event)], "events": [event],
                 "week_start": "2026-08-17", "week_end": "2026-08-21",
                 "countries": ["USD"]}, "ok")

    def _image_names(self):
        return chart_story_writer.image_names("xauusd", make_rows()[-1]["date"])

    def test_ผ่านด่านแล้ววางบทกับภาพครบชุด_และกวาดภาพชื่อยุคเก่า(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "06-08-2026" / chart_story_writer.FOLDER
            folder.mkdir(parents=True)
            (folder / "xauusd-1.png").write_bytes(b"png")  # ชื่อไฟล์ยุคเก่าค้างจากรอบก่อน
            result = chart_story_pipeline.run(
                asset="xauusd", publish_root=Path(tmp), cutoff_at=self.CUTOFF,
                fetcher=self.fake_fetcher, calendar_source=self.fake_calendar,
                zone_state_dir=Path(tmp) / "state", writing_mode="weekly_delta")

            self.assertEqual(result["status"], "pass", msg=str(result["findings"]))
            # state ต้องถูกเขียนใน tmp ไม่ใช่โฟลเดอร์จริง (บทเรียน 08-10)
            self.assertTrue((Path(tmp) / "state" / "zones-xauusd.json").exists())
            self.assertTrue((Path(tmp) / "state" / "style-d-weekly-xauusd.json").exists())
            self.assertEqual(result["writing_mode"], "weekly_delta")
            self.assertTrue((folder / "xauusd.md").exists())
            for name in self._image_names():
                self.assertTrue((folder / name).exists())
            self.assertFalse((folder / "xauusd-1.png").exists())
            # ทุกใบที่วางลงโฟลเดอร์วันต้องผ่านกติกาเว็บ (.webp ≤ 200 KB)
            self.assertEqual(len(image_output.verify_folder(folder)), 2)

    def test_มีปฏิทินรายสัปดาห์ต้องวางภาพที่สามด้วย(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = chart_story_pipeline.run(
                asset="xauusd", publish_root=Path(tmp), cutoff_at=self.CUTOFF,
                fetcher=self.fake_fetcher, calendar_source=self.fake_weekly_calendar,
                zone_state_dir=Path(tmp) / "state")
            self.assertEqual(result["status"], "pass", msg=str(result["findings"]))
            self.assertEqual(len(result["images"]), 3)
            self.assertIsNotNone(result["weekly_calendar"])
            self.assertEqual(len(image_output.verify_folder(Path(result["directory"]))), 3)
            self.assertIsNone(result["calendar_evidence"])
            evidence_name = chart_story_writer.calendar_evidence_name(
                chart_story.build_story(
                    make_rows(), asset="xauusd",
                    calendar=self.fake_weekly_calendar("xauusd")[0],
                ))
            self.assertFalse((Path(result["directory"]) / evidence_name).exists())

    def test_ตกด่านต้องไม่เหลือไฟล์แม้ของรอบก่อน(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "06-08-2026" / chart_story_writer.FOLDER
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
                    zone_state_dir=Path(tmp) / "state", writing_mode="weekly_delta")

            self.assertEqual(result["status"], "fail")
            # รอบตกด่านห้ามล็อกระดับ — ต้องไม่มี state ถูกเขียน
            self.assertFalse((Path(tmp) / "state" / "zones-xauusd.json").exists())
            self.assertFalse((Path(tmp) / "state" / "style-d-weekly-xauusd.json").exists())
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
            folder = Path(tmp) / "06-08-2026" / chart_story_writer.FOLDER
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
        # 🔄 08-14 บทนำเขียนใหม่ — ประโยคเปลี่ยน แต่เลขที่ทีมเว็บทานสอบต้องเป็นตัวเดิม
        # 🔄 08-14 — ประโยคระบุ**วันของแท่งฐาน**แล้ว (พาดหัวลงวันเผยแพร่)
        # ⇒ เลขที่ทีมเว็บทานสอบต้องมาคู่กับวันของมันเสมอ ไม่ใช่ลอยเดี่ยว
        self.assertIn("[ราคาทองคำ](/thailand/asset-xauusd)ปิดที่ 4,342.63 ดอลลาร์ "
                      "จากตลาดวันที่ 7 ส.ค. 2026", self.markdown)
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
    """สเปก Title เดิม + H1/คำโปรยจากต้นแบบที่ผู้ใช้ยืนยัน 2026-08-25

        Title : วิเคราะห์ทองคำวันนี้ 6 สิงหาคม 2026 — แนวโน้มราคาทอง XAU/USD
        H1    : วิเคราะห์ราคาทองคำ XAU/USD ประจำวันที่ 6 สิงหาคม 2026
        คำโปรย: ทองยืน 4,262 ...
    """

    def setUp(self):
        self.story = chart_story.build_story(REAL_ROWS, asset="xauusd")
        self.markdown = chart_story_writer.render_article(self.story)
        # บรรทัดแรกคือ frontmatter ตั้งแต่ 2026-08-10 (ทุกสไตล์ต้องมี title) — หา H1 ด้วยรูปแบบ
        self.h1 = next(line for line in self.markdown.splitlines()
                       if line.startswith("# "))[2:]
        self.title = chart_story_writer.seo_title(self.story)

    def test_Title_และ_H1_ทำหน้าที่คนละแบบตามต้นแบบ(self):
        self.assertTrue(self.title.startswith("วิเคราะห์ทองคำวันนี้ "), self.title)
        self.assertTrue(self.h1.startswith("วิเคราะห์ราคาทองคำ XAU/USD ประจำวันที่ "),
                        self.h1)
        self.assertNotIn("ทองคำโลก", self.title)
        self.assertNotIn("ทองคำโลก", self.h1)

    def test_Title_และ_H1_ใช้เดือนเต็ม(self):
        date_text = self.story["current"]["date"]
        self.assertIn(headline_format.thai_date(date_text, full_month=True), self.title)
        self.assertIn(headline_format.thai_date(date_text, full_month=True), self.h1)

    def test_ปีเป็น_คศ_ทั้งคู่(self):
        year = self.story["current"]["date"][:4]
        for text in (self.title, self.h1):
            self.assertIn(year, text)
            # กันการกลับไป พ.ศ. แบบเงียบ ๆ (หัวหน้าสั่งกลับเป็น ค.ศ. 08-11)
            self.assertNotIn(str(int(year) + 543), text)

    def test_Title_กับ_H1_ต้องไม่เหมือนกัน(self):
        """Title เป็นช่อง SEO ส่วน H1 เป็นหัวบทตามต้นแบบ จึงต้องไม่เหมือนกัน"""
        self.assertNotEqual(self.title, self.h1)

    def test_ด่านตีตกเมื่อหางชนกัน(self):
        """เขียนชนกันเมื่อไหร่บทต้องไม่ออก ไม่ใช่ออกไปแล้วค่อยรู้ตอนขึ้นเว็บ"""
        clashed = self.markdown.replace(self.h1, self.title, 1)
        result = chart_story_writer.validate(clashed, self.story)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any(f["rule"] == "title_equals_h1" for f in result["findings"]),
                        [f["rule"] for f in result["findings"]])

    def test_คำโปรยใต้_H1_ผูกกับราคาปิดจริง(self):
        deck = next(line for line in self.markdown.splitlines()
                    if line.startswith("**") and line.endswith("**"))
        self.assertIn(f"{self.story['current']['close']:,.0f}", deck)


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
    """ผู้ใช้ยืนยัน 2026-08-25 ให้ไฟล์ตัวอย่างเป็นสัญญาโครงสร้างของ Style D"""

    CALENDAR = {"sentences": [
        "พรุ่งนี้เวลา 19:30 น. Nonfarm Payrolls ซึ่งจัดเป็นรายการผลกระทบสูง ครั้งก่อนอยู่ที่ 57",
    ]}

    def _heads(self, markdown: str, mark: str) -> list[str]:
        return [line.strip() for line in markdown.splitlines() if line.startswith(mark + " ")]

    def test_มีปฏิทิน_ได้ห้าหัวข้อตามต้นแบบ(self):
        story = chart_story.build_story(REAL_ROWS, asset="xauusd", calendar=self.CALENDAR)
        markdown = chart_story_writer.render_article(story)
        self.assertEqual(self._heads(markdown, "##"), [
            f"## {chart_story_writer.H2_STRUCTURE}",
            f"## {chart_story_writer.H2_LEVELS}",
            f"## {chart_story_writer.H2_SCENARIOS}",
            f"## {chart_story_writer.H2_CALENDAR}",
            f"## {chart_story_writer.summary_heading(story)}",
        ])

    def test_ไม่มีปฏิทิน_ทุกหัวข้อยังไม่มีเลขนำหน้า(self):
        """หัวข้อปฏิทินหาย = เหลือสี่หัว โดย Style D ไม่สร้างเลขลำดับ"""
        story = chart_story.build_story(REAL_ROWS, asset="xauusd")
        markdown = chart_story_writer.render_article(story)
        ordinals = [int(m.group(1)) for m in re.finditer(r"(?m)^## (\d+)\. ", markdown)]
        self.assertEqual(ordinals, [])
        self.assertEqual(self._heads(markdown, "##"), [
            f"## {chart_story_writer.H2_STRUCTURE}",
            f"## {chart_story_writer.H2_LEVELS}",
            f"## {chart_story_writer.H2_SCENARIOS}",
            f"## {chart_story_writer.summary_heading(story)}",
        ])
        self.assertNotIn("Economic Events", markdown)

    def test_ด่านปฏิเสธหัวข้อเก่าและอีโมจิ(self):
        story = chart_story.build_story(REAL_ROWS, asset="xauusd")
        markdown = chart_story_writer.render_article(story)

        old_heading = markdown.replace(
            f"## {chart_story_writer.H2_SCENARIOS}",
            "## 3. แผนการเคลื่อนไหวของราคา",
        )
        old_rules = {finding["rule"]
                     for finding in chart_story_writer.validate(old_heading, story)["findings"]}
        self.assertIn("heading_contract", old_rules)
        self.assertIn("numbered_heading_forbidden", old_rules)

        with_emoji = markdown.replace(
            f"## {chart_story_writer.H2_SUMMARY}",
            f"## {chart_story_writer.H2_SUMMARY} 📌",
        )
        emoji_rules = {finding["rule"]
                       for finding in chart_story_writer.validate(with_emoji, story)["findings"]}
        self.assertIn("heading_contract", emoji_rules)
        self.assertIn("emoji_forbidden", emoji_rules)

    def test_หัวข้อย่อยต้องอยู่ในทะเบียนของใบตัวอย่างเท่านั้น(self):
        story = chart_story.build_story(REAL_ROWS, asset="xauusd", calendar=self.CALENDAR)
        markdown = chart_story_writer.render_article(story)
        allowed = (chart_story_writer.H3_BULLISH, chart_story_writer.H3_BEARISH)
        subheads = self._heads(markdown, "###")
        self.assertEqual(len(subheads), 2, subheads)
        for head in subheads:
            self.assertTrue(head.startswith(allowed), f"หัวข้อย่อยนอกทะเบียน: {head!r}")

    def test_ถอดหัวข้อแผนเข้าโซนรับออกจากบทแล้ว(self):
        """ผู้ใช้สั่ง 2026-08-14 — หัวข้อ 3 เหลือฉากทัศน์สองฝั่ง ไม่มีบล็อกจุดเข้าซื้อ"""
        story = chart_story.build_story(REAL_ROWS, asset="xauusd", calendar=self.CALENDAR)
        markdown = chart_story_writer.render_article(story)
        self.assertNotIn("แผนการเข้าเทรดบริเวณโซนรับ", markdown)
        self.assertNotIn("Execution Plan — ลำดับขั้นตอนก่อนเข้าเทรด", markdown)
        self.assertNotIn("จุดเข้าซื้อ 1 ที่", markdown)
        # ผู้ใช้สั่ง 2026-08-24 ให้ถอดข้อความอธิบายซ้ำท้ายบทและท้ายฉากทัศน์
        self.assertNotIn("ไม่ใช่คำทำนาย", markdown)
        self.assertNotIn("ภาพกราฟสองใบกับตัวเลขราคาในบทนี้", markdown)
        self.assertNotIn("ส่วนระดับราคาที่อยู่ไกลกว่านี้ใช้สำหรับดูโครงสร้างหลัก",
                         markdown)
        self.assertIsNone(re.search(r"พบ \d+ รายการ แสดงครบใน \d+ ภาพ", markdown))

    def test_ฉากทัศน์ฝั่งลงใช้ดูโครงสร้างไม่ใช่ลำดับเข้าเทรด(self):
        """ผู้ใช้สั่ง 2026-08-17 — ระดับไกลใช้ดูโครงสร้างหลักเท่านั้น"""
        story = chart_story.build_story(REAL_ROWS, asset="xauusd", calendar=self.CALENDAR)
        down = story["scenarios"]["down"]
        self.assertIsNotNone(down, "ชุดข้อมูลนี้ต้องมีฉากทัศน์ฝั่งลงจึงจะทดสอบได้")
        markdown = chart_story_writer.render_article(story)
        self.assertNotIn("ขั้นตอนปฏิบัติ", markdown)
        self.assertNotIn("เปิดสถานะ Sell", markdown)
        self.assertIn(
            f"ราคาปิดรายวันต่ำกว่า **{down['trigger']:,.2f} ดอลลาร์**", markdown)
        self.assertIn("**แนวรับถัดไป:**", markdown)
        for target in down["targets"]:
            self.assertIn(f"**{target:,.2f}**", markdown)
        self.assertEqual(chart_story_writer.validate(markdown, story)["findings"], [])

    def test_สรุปอธิบายผลหลังผ่านและหลุดโดยไม่ใช้ลูกศร(self):
        story = chart_story.build_story(REAL_ROWS, asset="xauusd", calendar=self.CALENDAR)
        markdown = chart_story_writer.render_article(story)
        up = story["scenarios"]["up"]
        down = story["scenarios"]["down"]

        self.assertIsNotNone(up)
        self.assertIsNotNone(down)
        expected_direction = ("ขาลง (Bearish)" if story["regime"]["down"]
                              else "ขาขึ้น (Bullish)")
        self.assertIn(expected_direction, markdown)
        self.assertIn(f"**ผ่าน {up['trigger']:,.2f} ดอลลาร์:**", markdown)
        self.assertIn(f"**หลุด {down['trigger']:,.2f} ดอลลาร์:**", markdown)
        expected_up_effect = ("เปิดทางทดสอบ" if story["regime"]["down"]
                              else "มุ่งหน้าทดสอบ")
        self.assertIn(expected_up_effect, markdown)
        self.assertIn(f"**{down['targets'][0]:,.2f} ดอลลาร์**", markdown)
        self.assertFalse(any(mark in markdown for mark in ("➔", "→", "➡")))


if __name__ == "__main__":
    unittest.main()
