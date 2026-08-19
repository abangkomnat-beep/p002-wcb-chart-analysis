"""เทสสไตล์ F/G — บทสั้นตอนเช้าที่แกะจากบทจริงของ InterGold (ผู้ใช้สั่ง 2026-08-10)

หลักที่ล็อกไว้ในเทสชุดนี้:

1. **ตัวแยกสองสไตล์ต้องตัดสินได้เอง** — F เมื่อไม่มีอะไรรอ · G เมื่อมีเหตุการณ์แรงรอ
   **และ**ช่องแนวโน้มพิสูจน์ได้ **และ**ราคายังอยู่ในช่อง (ครบสามข้อเท่านั้น)
2. **ภาพกับบทต้องเล่าเรื่องเดียวกัน** — ราคาหลุดออกนอกช่องแล้วห้ามเขียนว่า "แกว่งในกรอบ"
3. **แนวรับ/แนวต้านของบทเช้าคือขอบกรอบ ไม่ใช่ระดับโครงสร้างของสไตล์ D**
   (ระดับ D ห่างได้ถึง 10×ATR — เขียน "รอย่อเข้าหาแนวรับ" ไม่ได้)
4. เลขทุกตัวในบทต้องชี้กลับ brief ได้ (fail-closed) — เลขแปลกปลอมตัวเดียวก็ตก
5. ตกด่าน = โฟลเดอร์ของสไตล์นั้นต้องว่าง ไม่เหลือชุดครึ่ง ๆ กลาง ๆ
"""

import math
import re
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import brief_pipeline, brief_renderer, brief_story, brief_writer  # noqa: E402
from tools import image_output, intraday_bars, wcb_writers  # noqa: E402


def make_rows(n=420, *, start=300.0, step=0.35, wave=6.0, body=0.4, wick=1.2,
              last_close=None):
    """แท่งสังเคราะห์แบบเดียวกับเทสสไตล์ D — เส้นตรงบวกคลื่น sine ให้เกิด swing จริง

    `last_close` ดันราคาปิดแท่งสุดท้ายไปที่ค่าที่กำหนด (ใช้จำลอง 'ทะลุออกนอกช่อง')
    """
    rows = []
    first_day = date(2025, 1, 1)
    for i in range(n):
        close = start + step * i + wave * math.sin(i / 6)
        open_value = close - body
        high = max(open_value, close) + wick
        low = min(open_value, close) - wick
        rows.append({"date": (first_day + timedelta(days=i)).isoformat(),
                     "open": open_value, "high": high, "low": low, "close": close})
    if last_close is not None:
        row = rows[-1]
        row["close"] = last_close
        row["high"] = max(row["high"], last_close + wick)
        row["low"] = min(row["low"], last_close - wick)
    return rows


def calendar_events(*, impact="High", country="USD", actual=None, at="2026-02-25 20:30"):
    return [{"at": at, "country": country, "impact": impact,
             "title": "การจ้างงานนอกภาคเกษตร", "previous": "57", "forecast": "80",
             "actual": actual}]


TODAY = "2026-02-24"


def build(rows=None, *, style=None, events=None, sentences=None, asset="xauusd"):
    return brief_story.build_brief(
        rows if rows is not None else make_rows(), asset=asset, style=style,
        calendar=events, calendar_sentences=sentences, local_date=TODAY)


class ตัวแยกสไตล์(unittest.TestCase):
    """F กับ G ต่างกันที่ 'ตลาดอยู่ในสภาพไหน' ไม่ใช่ลีลาการเขียน — ระบบต้องตัดสินเอง"""

    def test_ไม่มีเหตุการณ์รออยู่_ได้สไตล์F(self):
        self.assertEqual(build()["style"], brief_story.STYLE_F)

    def test_มีเหตุการณ์แรงรออยู่และช่องพิสูจน์ได้_ได้สไตล์G(self):
        brief = build(events=calendar_events())
        self.assertEqual(brief["style"], brief_story.STYLE_G)
        self.assertEqual(brief["event"]["title"], "การจ้างงานนอกภาคเกษตร")

    def test_เหตุการณ์ประกาศไปแล้ว_ไม่นับว่ารออยู่(self):
        self.assertEqual(build(events=calendar_events(actual="92"))["style"],
                         brief_story.STYLE_F)

    def test_เหตุการณ์ของประเทศอื่นไม่นับ(self):
        """🐞 รันจริงรอบแรก 08-10: บททองเขียนว่าตลาดรอ 'NAB ออสเตรเลีย' ซึ่งไม่จริง"""
        self.assertEqual(build(events=calendar_events(country="AUD"))["style"],
                         brief_story.STYLE_F)

    def test_เหตุการณ์ผลกระทบกลางไม่นับ(self):
        self.assertEqual(build(events=calendar_events(impact="Medium"))["style"],
                         brief_story.STYLE_F)

    def test_เหตุการณ์ไกลเกินหน้าต่างไม่นับ(self):
        far = calendar_events(at="2026-03-20 20:30")
        self.assertEqual(build(events=far)["style"], brief_story.STYLE_F)


class ภาพกับบทต้องเล่าเรื่องเดียวกัน(unittest.TestCase):
    """🐞 พบตอนดูภาพรอบแรก 08-10 — ช่องพิสูจน์ได้แต่ราคาปิดทะลุขึ้นเหนือขอบบนไปแล้ว
    บทเขียน 'แกว่งตัวในกรอบ' ขณะที่ภาพแสดงการทะลุออกชัด ๆ ในหน้าเดียวกัน"""

    def test_ราคาหลุดออกนอกช่อง_บังคับGแล้วต้องล้ม(self):
        rows = make_rows(last_close=900.0)
        with self.assertRaises(brief_story.BriefUnavailable) as caught:
            build(rows, style=brief_story.STYLE_G, events=calendar_events())
        self.assertIn("นอกช่อง", str(caught.exception))

    def test_ราคาหลุดออกนอกช่อง_เลือกอัตโนมัติได้F(self):
        rows = make_rows(last_close=900.0)
        self.assertEqual(build(rows, events=calendar_events())["style"],
                         brief_story.STYLE_F)


class แนวรับแนวต้านของบทเช้า(unittest.TestCase):
    """ระดับของสไตล์ D ห่างได้ถึง 10×ATR — บทเช้าใช้ไม่ได้ ต้องเป็นขอบกรอบเสมอ"""

    def test_สไตล์F_ใช้ขอบกล่องกรอบ(self):
        brief = build()
        box = brief["range_box"]
        self.assertEqual(brief["support"], min(box["low"], brief["current"]["close"]
                                               - 0.1 * brief["atr14"]))
        self.assertEqual(brief["resistance"], max(box["high"], brief["current"]["close"]
                                                  + 0.1 * brief["atr14"]))

    def test_สไตล์G_ใช้ขอบช่องและต้องคร่อมราคา(self):
        brief = build(events=calendar_events())
        close = brief["current"]["close"]
        self.assertLess(brief["support"], close)
        self.assertLess(close, brief["resistance"])
        edges = brief_story.channel_edges(brief["channel"],
                                          [{"close": close}] * brief["display"]["bars"])
        self.assertAlmostEqual(brief["support"], edges[0], places=6)
        self.assertAlmostEqual(brief["resistance"], edges[1], places=6)

    def test_แนวรับแนวต้านต้องอยู่คนละฝั่งของราคาเสมอ(self):
        for events in (None, calendar_events()):
            brief = build(events=events)
            self.assertLess(brief["support"], brief["current"]["close"], msg=brief["style"])
            self.assertLess(brief["current"]["close"], brief["resistance"],
                            msg=brief["style"])

    def test_แผนFใช้หนึ่งATRเป็นSLและสองATRเป็นTP(self):
        brief = build(style=brief_story.STYLE_F)
        plan = brief["trade_plan"]
        risk = round(brief["atr14"], 2)
        support, resistance = round(brief["support"], 2), round(brief["resistance"], 2)
        self.assertEqual(plan["sell"], {
            "open": resistance,
            "tp": round(resistance - 2 * risk, 2),
            "sl": round(resistance + risk, 2),
        })
        self.assertEqual(plan["buy"], {
            "open": support,
            "tp": round(support + 2 * risk, 2),
            "sl": round(support - risk, 2),
        })


class จุดสัมผัสช่องแนวโน้ม(unittest.TestCase):
    """เส้นที่ไม่มีจุดแตะกำกับคือเส้นที่ลากตามใจ — หัวใจของสไตล์ G"""

    def test_จุดแตะไม่ครบสองจุดต่อเส้น_ไม่ใช่ช่องที่ใช้ได้(self):
        # คลื่นแบนมาก = ไม่มี swing แตะขอบช่องจริง
        rows = make_rows(wave=0.05, wick=0.02, body=0.01)
        brief = build(rows, events=calendar_events())
        self.assertEqual(brief["style"], brief_story.STYLE_F)

    def test_ช่องที่ใช้ได้ต้องมีจุดแตะครบทั้งสองขอบ(self):
        brief = build(events=calendar_events())
        touches = brief["channel_touches"]
        self.assertGreaterEqual(len(touches["upper"]), brief_story.CHANNEL_TOUCH_MIN)
        self.assertGreaterEqual(len(touches["lower"]), brief_story.CHANNEL_TOUCH_MIN)


class โครงบท(unittest.TestCase):
    def test_มีหัวข้อครบตามใบตัวอย่างและไม่มีตาราง(self):
        """🔄 **กลับด้านจากเทสเดิม 2026-08-11** — เดิมชื่อ "ไม่มีหัวข้อย่อยและไม่มีตาราง"
        และบังคับว่าบทเช้าห้ามมี `## ` เลย (ต้นแบบ InterGold 08-10 ไม่มีสักอัน)
        · ใบตัวอย่างชุดใหม่ที่ผู้ใช้ส่งมามีครบสี่หัว ⇒ กลับเป็นบังคับให้มี
        **ข้อห้ามตารางยังอยู่ครบ** — คนละเรื่องกัน และ CSS ของเว็บยังไม่รองรับ `table`
        """
        for events in (None, calendar_events()):
            brief = build(events=events)
            markdown = brief_writer.render_article(brief)
            body = markdown.split("---", 2)[-1]
            self.assertNotIn("|", body)
            summary = (brief_writer.SUMMARY_G if brief["style"] == brief_story.STYLE_G
                       else brief_writer.H2_SUMMARY)
            for head in (brief_writer.h2_box(brief), brief_writer.h2_technical(brief),
                         brief_writer.H2_PLAN[brief["style"]], summary,
                         brief_writer.H3_UP[brief["style"]],
                         brief_writer.H3_DOWN[brief["style"]]):
                self.assertIn(head, body)

    def test_กล่องกลยุทธ์ครบสามบรรทัด(self):
        brief = build()
        markdown = brief_writer.render_article(brief)
        self.assertIn(brief_writer.h2_box(brief), markdown)
        for label in ("* **กลยุทธ์หลัก:**", "* **แนวต้านสำคัญ:**", "* **แนวรับสำคัญ:**"):
            self.assertIn(label, markdown)

    def test_สไตล์F_จบด้วยเงื่อนไขเดียว(self):
        markdown = brief_writer.render_article(build())
        self.assertNotIn("แต่หาก", markdown)

    def test_สไตล์G_จบด้วยฉากทัศน์คู่และเอ่ยชื่อเหตุการณ์(self):
        brief = build(events=calendar_events())
        markdown = brief_writer.render_article(brief)
        self.assertIn("แต่หาก", markdown)
        self.assertIn("การจ้างงานนอกภาคเกษตร", markdown)
        self.assertIn("* **กลยุทธ์หลัก:** ติดตามผลการจ้างงานนอกภาคเกษตร", markdown)

    def test_ไม่มีปฏิทิน_ตัดย่อหน้าปัจจัยเงียบ_บทยังผ่านด่าน(self):
        brief = build()
        markdown = brief_writer.render_article(brief)
        self.assertNotIn(brief_writer.CALENDAR_SOURCE, markdown)
        self.assertTrue(brief_writer.validate(markdown, brief)["ok"])

    def test_มีปฏิทิน_ต้องมีวลีที่มา(self):
        brief = build(sentences=["จันทร์ 24 ก.พ. เวลา 20:30 น. รายการทดสอบ"])
        markdown = brief_writer.render_article(brief)
        self.assertIn(brief_writer.CALENDAR_SOURCE, markdown)
        self.assertTrue(brief_writer.validate(markdown, brief)["ok"])


class ปฏิทินเป็นบูลเลตจัดกลุ่มตามวัน(unittest.TestCase):
    """ผู้ใช้สั่ง 08-11 บ่าย: หัวข้อ 2 ของบทเช้าเป็น bullet ตามใบตัวอย่าง F/G

    ประโยคกับรายการต้นทางประกอบผ่านเส้นทางจริง (`_calendar_sentences` +
    `_calendar_events` บน pseudo-evidence เดียวกัน) — วิธีเดียวกับ `brief_pipeline`
    เพื่อให้เทสล้มเมื่อสองตัวนั้นเลิกให้ผล 1:1 กัน ไม่ใช่ล้มเฉพาะเมื่อ fixture เพี้ยน
    """

    AT_EARLY, AT_LATE, AT_NEXT = "2026-02-25 19:15", "2026-02-25 21:00", "2026-02-26 19:30"

    def _calendar(self):
        events = [{"at": at, "country": "USD", "impact": "Medium", "title": title,
                   "previous": "57", "forecast": "80", "actual": None}
                  for at, title in ((self.AT_EARLY, "รายการหนึ่ง"),
                                    (self.AT_LATE, "รายการสอง"),
                                    (self.AT_NEXT, "รายการสาม"))]
        pseudo = {"calendar": events, "local_date": TODAY}
        return (wcb_writers._calendar_sentences(pseudo, limit=3),
                wcb_writers._calendar_events(pseudo, 3))

    def test_สไตล์F_จัดกลุ่มตามวันและเวลาเป็นตัวหนา(self):
        sentences, selected = self._calendar()
        brief = brief_story.build_brief(
            make_rows(), asset="xauusd", calendar=None, calendar_sentences=sentences,
            calendar_events=selected, local_date=TODAY)
        self.assertEqual(brief["style"], brief_story.STYLE_F)
        markdown = brief_writer.render_article(brief)
        # วันเดียวกันสองรายการต้องอยู่ใต้หัววันเดียว (หัววันโผล่ครั้งเดียว)
        day_head = f"- **{wcb_writers.when(self.AT_EARLY)}**"
        self.assertEqual(markdown.count(day_head), 1, markdown)
        # 🔄 08-11 ค่ำชุดสาม: ลูกของหัววันมี NBSP เยื้อง (CSS เว็บตัด padding ลิสต์ซ้อน)
        self.assertIn(f"  - {wcb_writers.VISUAL_INDENT}**19:15 น.**", markdown)
        self.assertIn(f"  - {wcb_writers.VISUAL_INDENT}**21:00 น.**", markdown)
        self.assertIn(f"- **{wcb_writers.when(self.AT_NEXT)}**", markdown)
        # ร้อยแก้วแบบเดิมต้องไม่เหลือ — ผู้ใช้สั่งเปลี่ยนเป็น bullet
        self.assertNotIn("รายการที่ตลาดจับตาในช่วงนี้เรียงตามเวลาคือ", markdown)
        result = brief_writer.validate(markdown, brief)
        self.assertTrue(result["ok"], msg=result["findings"])

    def test_สไตล์G_ใช้บูลเลตชุดเดียวกัน(self):
        sentences, selected = self._calendar()
        brief = brief_story.build_brief(
            make_rows(), asset="xauusd", calendar=calendar_events(),
            calendar_sentences=sentences, calendar_events=selected, local_date=TODAY)
        self.assertEqual(brief["style"], brief_story.STYLE_G)
        markdown = brief_writer.render_article(brief)
        self.assertIn(f"  - {wcb_writers.VISUAL_INDENT}**19:15 น.**", markdown)
        result = brief_writer.validate(markdown, brief)
        self.assertTrue(result["ok"], msg=result["findings"])

    def test_ไม่มีรายการต้นทาง_ถอยไปร้อยแก้วไม่ใช่เดา(self):
        """brief ที่มีแต่ประโยค (ไม่มี `calendar_events` — เช่นผู้เรียกยุคก่อน)
        ต้องได้ร้อยแก้วแบบเดิมทั้งชุด ไม่ใช่ bullet ที่หั่นหัววันจากการเดา"""
        brief = build(sentences=["จันทร์ 24 ก.พ. เวลา 20:30 น. รายการทดสอบ"])
        markdown = brief_writer.render_article(brief)
        self.assertIn("รายการที่ตลาดจับตาในช่วงนี้เรียงตามเวลาคือ", markdown)
        self.assertNotIn("  - **20:30 น.**", markdown)
        self.assertTrue(brief_writer.validate(markdown, brief)["ok"])


class ด่านตรวจ(unittest.TestCase):
    def test_บทที่เขียนตามระบบต้องผ่าน(self):
        for events in (None, calendar_events()):
            brief = build(events=events)
            result = brief_writer.validate(brief_writer.render_article(brief), brief)
            self.assertTrue(result["ok"], msg=result["findings"])

    def test_เลขนอกทะเบียนตกทันที(self):
        brief = build()
        markdown = brief_writer.render_article(brief) + "\nแนวรับถัดไปอยู่ที่ 1,234.56\n"
        result = brief_writer.validate(markdown, brief)
        self.assertFalse(result["ok"])
        self.assertIn("number_not_in_brief", [f["rule"] for f in result["findings"]])

    def test_หัวข้อบังคับที่หายไปตกทันที(self):
        """🔄 กลับด้านจาก `subheading_forbidden` (ดูเหตุผลใน `brief_writer`)

        ไล่ทีละหัวแทนการลบหัวเดียว — ไม่งั้นเทสจะรับรองแค่หัวที่บังเอิญเลือกมาตรวจ
        """
        brief = build()
        markdown = brief_writer.render_article(brief)
        for head in (brief_writer.h2_box(brief), brief_writer.H2_PLAN[brief["style"]],
                     brief_writer.H2_SUMMARY, brief_writer.H3_UP[brief["style"]],
                     brief_writer.H3_DOWN[brief["style"]]):
            with self.subTest(head=head):
                result = brief_writer.validate(markdown.replace(head, "ข้อความธรรมดา"), brief)
                self.assertIn("heading_missing", [f["rule"] for f in result["findings"]])

    def test_กล่องกลยุทธ์ขาดบรรทัดตกทันที(self):
        brief = build()
        markdown = brief_writer.render_article(brief).replace(
            "* **แนวรับสำคัญ:**", "แนวรับสำคัญ")
        result = brief_writer.validate(markdown, brief)
        self.assertIn("strategy_box_incomplete", [f["rule"] for f in result["findings"]])

    def test_สไตล์Fที่หลุดไปเขียนฉากทัศน์คู่ตกทันที(self):
        brief = build()
        markdown = brief_writer.render_article(brief) + "\nแต่หากตัวเลขแข็งแกร่ง\n"
        result = brief_writer.validate(markdown, brief)
        self.assertIn("single_condition_required", [f["rule"] for f in result["findings"]])

    def test_บทยาวเกินเพดานตกทันที(self):
        """บทเช้าต้องสั้น — ยาวกว่านี้คือกลายพันธุ์เป็นบท D/E เงียบ ๆ"""
        brief = build()
        markdown = brief_writer.render_article(brief) + "\nทองคำ" * 1200
        result = brief_writer.validate(markdown, brief)
        self.assertIn("article_too_long", [f["rule"] for f in result["findings"]])


class ภาษาสไตล์Fฉบับมนุษย์(unittest.TestCase):

    def test_ตัดศัพท์อังกฤษและเปอร์เซ็นต์ตำแหน่งในกรอบ(self):
        markdown = brief_writer.render_article(build())
        for forbidden in ("Sideway", "Chart Structure", "Buy at Support",
                          "Sell at Resistance", "เปอร์เซ็นต์ของความสูงกรอบ"):
            self.assertNotIn(forbidden, markdown)

    def test_พาดหัวใช้แนวรับแนวต้านชุดเดียวกับภาพ(self):
        brief = build()
        headline = next(line for line in brief_writer.render_article(brief).splitlines()
                        if line.startswith("# "))
        money = brief_writer.money_for(brief)
        self.assertIn(f"{money(brief['support'])}–{money(brief['resistance'])}", headline)

    def test_วันเผยแพร่แยกจากวันแท่งฐาน(self):
        brief = build()
        brief["publication_date"] = "2026-02-25"
        markdown = brief_writer.render_article(brief)
        headline = next(line for line in markdown.splitlines() if line.startswith("# "))
        self.assertIn("25 ก.พ. 2026", headline)
        self.assertIn(f"ของ {brief_writer.thai_date(brief['current']['date'])}", markdown)

    def test_ปฏิทินไม่มีภาษาในระบบหรือคำอังกฤษในวงเล็บ(self):
        brief = build(sentences=[
            "จันทร์ 24 ก.พ. เวลา 20:30 น. ดัชนีรัฐนิวยอร์ก (Empire State) "
            "โดยรายการนี้ไม่มีตัวเลขครั้งก่อนหรือค่าคาดที่อ้างอิงได้ในระบบ "
            "จึงระบุได้แค่วันและเวลา"])
        markdown = brief_writer.render_article(brief)
        self.assertNotIn("ในระบบ", markdown)
        self.assertNotIn("(Empire State)", markdown)


class เหตุผลสไตล์Gไม่ฟันธงจากข่าว(unittest.TestCase):

    def test_ข่าวเป็นเงื่อนไขร่วมไม่ใช่คำทำนายทิศทาง(self):
        markdown = brief_writer.render_article(build(events=calendar_events()))
        self.assertIn("ผลประกาศเพียงอย่างเดียวยังไม่ยืนยันทิศทางราคา", markdown)
        self.assertIn("ดอลลาร์ อัตราผลตอบแทนพันธบัตร และภาวะรับความเสี่ยง", markdown)
        self.assertIn("ระหว่างสองระดับยังไม่ยืนยันทิศทาง", markdown)
        self.assertNotIn("ผลประกอบการของบริษัท", markdown)
        self.assertNotIn("หุ้นกลุ่มเติบโต", markdown)
        for forbidden in ("ตัวกำหนดทิศทางระยะสั้น", "แรงหนุนจะส่งให้ราคา",
                          "จุดสะสมฝั่งซื้อ", "Bullish Case", "Bearish Case"):
            self.assertNotIn(forbidden, markdown)

    def test_สรุปGใช้แท่งยืนยันและไม่สั่งซื้อโดยตรง(self):
        markdown = brief_writer.render_article(build(events=calendar_events()))
        self.assertIn("จึงควรรอให้แท่ง", markdown)
        self.assertIn("ปิดเหนือ", markdown)
        self.assertIn("ปิดต่ำกว่า", markdown)
        self.assertNotIn("เพื่อหาจังหวะเข้าเทรดฝั่งซื้อ", markdown)


class บทต้องไม่พูดถึงทองเมื่อไม่ใช่ทอง(unittest.TestCase):
    """🐞 พบตอนตรวจใบตัวอย่างก่อนส่งหัวหน้า 08-10 — พาดหัวใบ SOL เขียนว่า
    `วิเคราะห์ SOL วันนี้ 9 ส.ค. 2026 — ทองพักฐานเหนือ 72.14` เพราะหางพาดหัว
    ฮาร์ดโค้ดคำว่า "ทอง" ไว้ทั้งสองสไตล์ · บั๊กตระกูลเดียวกับ `price_text` ที่เคย
    ตรึงทศนิยม 2 ตำแหน่ง — ตัวเขียนใหม่เกิดในโลกของทองเสมอ"""

    def test_พาดหัวใช้ชื่อสินทรัพย์จากทะเบียน(self):
        rows = make_rows(start=60.0, step=0.06, wave=1.2, body=0.08, wick=0.25)
        for events, style in ((None, brief_story.STYLE_F),
                              (calendar_events(), brief_story.STYLE_G)):
            brief = build(rows, events=events, asset="solusd")
            self.assertEqual(brief["style"], style)
            markdown = brief_writer.render_article(brief)
            headline = [line for line in markdown.splitlines() if line.startswith("# ")][0]
            self.assertNotIn("ทอง", headline, msg=headline)
            expected = "โซลานา" if style == brief_story.STYLE_F else "SOL/USD"
            self.assertIn(expected, headline, msg=headline)


class คำเรียกกรอบต้องตรงกับสิ่งที่ภาพวาด(unittest.TestCase):
    """🐞 พบพร้อมกัน 08-10 — บท G ของ SOL เขียน "กรอบ Sideway-Down" ขณะที่ภาพเป็น
    ช่องขาขึ้นชัด ๆ เพราะตัวเขียนหยิบทิศของ**กล่องกรอบ 30 แท่งท้าย** มาใช้กับทุกสไตล์
    ทั้งที่สไตล์ G วาด**ช่องแนวโน้ม** ลงภาพ ไม่ใช่กล่อง"""

    def test_สไตล์Gเรียกกรอบตามช่องแนวโน้ม(self):
        brief = build(events=calendar_events())
        self.assertEqual(brief_writer.bias_of(brief),
                         brief_story.channel_bias(brief["channel"], brief["atr14"]))

    def test_สไตล์Fเรียกกรอบตามกล่อง(self):
        brief = build()
        self.assertEqual(brief_writer.bias_of(brief), brief["range_box"]["bias"])

    def test_ช่องขาขึ้นห้ามถูกเรียกว่าขาลง(self):
        brief = build(events=calendar_events())
        self.assertGreater(brief["channel"]["slope"], 0)   # ชุดแท่งนี้เป็นขาขึ้น
        markdown = brief_writer.render_article(brief)
        self.assertIn("จุดต่ำและจุดสูงระยะสั้นขยับสูงขึ้น", markdown)
        self.assertNotIn("จุดต่ำและจุดสูงระยะสั้นขยับต่ำลง", markdown)


class ทศนิยมตามสินทรัพย์(unittest.TestCase):
    """🪤 บั๊กประจำที่กลับมาทุกครั้งที่มีตัวเขียนใหม่เกิดในโลกของทอง (D · E · A/B/C)"""

    def test_คู่เงินต้องไม่ถูกปัดเหลือสองตำแหน่ง(self):
        rows = make_rows(start=1.15, step=1e-5, wave=2e-4, body=2e-5, wick=6e-5)
        brief = build(rows, asset="usdthb")
        markdown = brief_writer.render_article(brief)
        places = brief_writer.money_for(brief)(brief["current"]["close"])
        self.assertIn(places, markdown)
        self.assertGreaterEqual(len(places.split(".")[-1]), 3)


def intraday_rows(n=420, *, start=4000.0, step=0.9, wave=18.0, first="2026-02-01 00:00:00"):
    """แท่งราย 1 ชั่วโมงสังเคราะห์ — ป้ายเวลาเดินทีละชั่วโมงจริง"""
    begin = datetime.strptime(first, "%Y-%m-%d %H:%M:%S")
    rows = []
    for i in range(n):
        close = start + step * i + wave * math.sin(i / 6)
        open_value = close - 1.2
        at = (begin + timedelta(hours=i)).strftime("%Y-%m-%d %H:%M:%S")
        rows.append({"date": at[:10], "at": at, "open": open_value, "close": close,
                     "high": max(open_value, close) + 3.6,
                     "low": min(open_value, close) - 3.6})
    return rows


class แท่งระหว่างวัน(unittest.TestCase):
    """ผู้ใช้สั่ง 08-10 ให้ F/G ใช้กรอบเวลาตามต้นแบบ (ราย 1 ชั่วโมง)

    เหตุผลเชิงเนื้อหา: บนแท่งรายวัน แนวรับที่บทประกาศห่างราคา 5–10% ⇒ ประโยค
    "รอย่อตัวเข้าหาแนวรับ" ทำตามไม่ได้จริง · ต้นแบบห่าง ~1.2%
    """

    def test_แท่งที่ยังเดินอยู่ต้องถูกตัดทิ้ง(self):
        rows = intraday_rows(n=5, first="2026-02-01 00:00:00")
        # นาฬิกาอยู่กลางแท่ง 04:00 ⇒ แท่งนั้นยังไม่ปิด
        now = datetime(2026, 2, 1, 4, 30, tzinfo=intraday_bars.BAR_TZ)
        kept, dropped = intraday_bars.trim_to_closed(rows, timeframe="1h", now=now)
        self.assertEqual(dropped, ["2026-02-01 04:00:00"])
        self.assertEqual(kept[-1]["at"], "2026-02-01 03:00:00")

    def test_ด่านแท่งปิดพิสูจน์ใหม่เอง_ตั้งธงเองไม่ผ่าน(self):
        basis = intraday_bars.basis_for("xauusd", "2026-02-01 04:00:00", timeframe="1h",
                                        now=datetime(2026, 2, 1, 5, tzinfo=intraday_bars.BAR_TZ))
        basis["candle_state"] = "closed"      # ธงบอกว่าปิด แต่ด่านไม่อ่านธง
        early = datetime(2026, 2, 1, 4, 30, tzinfo=intraday_bars.BAR_TZ)
        self.assertIsNotNone(intraday_bars.verify(
            basis, asset="xauusd", bar_at="2026-02-01 04:00:00", now=early))
        late = datetime(2026, 2, 1, 6, tzinfo=intraday_bars.BAR_TZ)
        self.assertIsNone(intraday_bars.verify(
            basis, asset="xauusd", bar_at="2026-02-01 04:00:00", now=late))

    def test_ฐานแท่งของบทต้องตรงกับก้อนหลักฐาน(self):
        basis = intraday_bars.basis_for("xauusd", "2026-02-01 04:00:00", timeframe="1h")
        detail = intraday_bars.verify(basis, asset="xauusd", bar_at="2026-02-01 05:00:00")
        self.assertIn("คนละแท่ง", detail)

    def test_สายintradayต้องส่งก้อนหลักฐานมาเสมอ(self):
        """ไม่ตัดแท่งเองในตัวคิด — ไม่งั้นจะมีกติกาแท่งปิดสองชุดในระบบ"""
        with self.assertRaises(brief_story.BriefUnavailable):
            brief_story.build_brief(intraday_rows(), asset="xauusd", timeframe="1h",
                                    local_date=TODAY)

    def test_บทและภาพบอกกรอบเวลาเสมอ(self):
        rows, basis = intraday_bars.evaluate(
            intraday_rows(), asset="xauusd", timeframe="1h",
            now=datetime(2026, 3, 1, tzinfo=intraday_bars.BAR_TZ))
        brief = brief_story.build_brief(rows, asset="xauusd", timeframe="1h",
                                        candle_basis=basis, local_date=TODAY)
        markdown = brief_writer.render_article(brief)
        result = brief_writer.validate(markdown, brief)
        self.assertTrue(result["ok"], msg=result["findings"])
        self.assertIn("แท่งราย 1 ชั่วโมง", markdown)
        self.assertIn("timeframe: 1H", markdown)
        self.assertIn("เส้นค่าเฉลี่ย 50 แท่ง", markdown)   # ไม่ใช่ "50 วัน"
        self.assertNotIn("เส้นค่าเฉลี่ย 50 วัน", markdown)
        self.assertIn("-1h-", brief_writer.image_name(brief))

    def test_ชื่อไฟล์ภาพต้องมีกรอบเวลา_กันใบคนละกรอบทับกัน(self):
        rows, basis = intraday_bars.evaluate(
            intraday_rows(), asset="xauusd", timeframe="1h",
            now=datetime(2026, 3, 1, tzinfo=intraday_bars.BAR_TZ))
        hourly = brief_story.build_brief(rows, asset="xauusd", timeframe="1h",
                                         candle_basis=basis, local_date=TODAY)
        daily = build()
        self.assertNotEqual(brief_writer.image_name(hourly),
                            brief_writer.image_name(daily))
        self.assertIn("-d1-", brief_writer.image_name(daily))

    def test_แท่งระหว่างวันต้องมีเวลาเต็ม(self):
        with self.assertRaises(intraday_bars.IntradayUnavailable):
            intraday_bars.rows_from_candles(
                [{"t": "2026-02-01", "o": 1, "h": 2, "l": 0, "c": 1}],
                timeframe="1h", asset="xauusd")

    def test_ไม่รู้จักกรอบเวลา_ล้มทันที(self):
        with self.assertRaises(intraday_bars.IntradayUnavailable):
            intraday_bars.spec_for("15m")

    def test_ป้ายวันบนภาพกระจายตามระยะแกนไม่เบียดกัน(self):
        rows = intraday_rows()
        brief = {"timeframe": "1h"}
        positions, _ = brief_renderer._tick_labels(brief, rows)
        self.assertLessEqual(len(positions), 6)
        self.assertTrue(all(right - left >= len(rows) / 7
                            for left, right in zip(positions, positions[1:])))


class ตัววาดและสายผลิต(unittest.TestCase):
    def test_ภาพออกเป็นเว็บพีและไม่เกินเพดาน(self):
        for events in (None, calendar_events()):
            rows = make_rows()
            brief = build(rows, events=events)
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / brief_writer.image_name(brief)
                summary = brief_renderer.render(brief, rows, path)
            self.assertEqual(path.suffix, image_output.IMAGE_SUFFIX)
            self.assertLessEqual(summary["bytes"], image_output.MAX_IMAGE_BYTES)

    def test_หัวการ์ดใช้สัญลักษณ์คู่เงินไม่ใช่ชื่อไทย(self):
        """ผู้ใช้สั่ง 2026-08-10 — 'แนวโน้มราคาโซลานา' อ่านแล้วไม่รู้ว่าคู่ไหน"""
        self.assertEqual(brief_renderer.header_title("solusd"), "แนวโน้มราคา SOL/USD")
        self.assertEqual(brief_renderer.header_title("xauusd"), "แนวโน้มราคา XAU/USD")
        for asset in ("xauusd", "solusd", "usdthb", "nvda"):
            title = brief_renderer.header_title(asset)
            self.assertNotIn("ทองคำโลก", title)
            self.assertNotIn("โซลานา", title)
            # เว้นวรรคก่อนอักษรละตินเสมอ ไม่งั้นได้ 'แนวโน้มราคาSOL/USD'
            self.assertTrue(title.startswith("แนวโน้มราคา "), msg=title)

    def test_ชื่อไฟล์ภาพบอกสไตล์ได้(self):
        self.assertIn("-brief-range-d1-trade-plan-", brief_writer.image_name(build()))
        self.assertIn("-brief-channel-",
                      brief_writer.image_name(build(events=calendar_events())))

    def test_สายผลิตวางบทคู่ภาพครบ(self):
        rows = make_rows()
        with tempfile.TemporaryDirectory() as root:
            result = brief_pipeline.run(
                asset="xauusd", timeframe=None, publish_root=Path(root),
                cutoff_at="2026-02-24T02:00:00+00:00",
                fetcher=lambda asset: ({}, rows, "fixture"),
                calendar_source=lambda asset: ({"events": calendar_events(),
                                                "sentences": ["จันทร์ 24 ก.พ. รายการทดสอบ"],
                                                "local_date": TODAY}, "ok"))
            self.assertTrue(result["ok"], msg=result["findings"])
            folder = Path(result["folder"])
            self.assertTrue((folder / "xauusd.md").is_file())
            self.assertEqual(len(list(folder.glob("xauusd*.webp"))), 1)

    def test_ปฏิทินล่มไม่พาสายล้ม(self):
        rows = make_rows()
        with tempfile.TemporaryDirectory() as root:
            result = brief_pipeline.run(
                asset="xauusd", timeframe=None, publish_root=Path(root),
                cutoff_at="2026-02-24T02:00:00+00:00",
                fetcher=lambda asset: ({}, rows, "fixture"),
                calendar_source=lambda asset: ({"events": [], "sentences": [],
                                                "local_date": None}, "unavailable: ทดสอบ"))
        self.assertTrue(result["ok"], msg=result["findings"])
        self.assertEqual(result["style"], brief_story.STYLE_F)

    def test_ของรอบก่อนของอีกสไตล์ต้องถูกกวาดทิ้ง(self):
        """กติกา 'ห้ามวางสองสไตล์ของวันเดียวกันขึ้นเว็บ' — ใบหลังทับใบแรกเงียบ ๆ บนเว็บ"""
        rows = make_rows()
        with tempfile.TemporaryDirectory() as root:
            common = {"asset": "xauusd", "timeframe": None, "publish_root": Path(root),
                      "cutoff_at": "2026-02-24T02:00:00+00:00",
                      "fetcher": lambda asset: ({}, rows, "fixture")}
            brief_pipeline.run(calendar_source=lambda asset: (
                {"events": calendar_events(), "sentences": [], "local_date": TODAY}, "ok"),
                **common)
            stale = Path(root) / "24-02-2026" / brief_writer.FOLDERS[brief_story.STYLE_G]
            self.assertTrue((stale / "xauusd.md").is_file())
            brief_pipeline.run(calendar_source=lambda asset: (
                {"events": [], "sentences": [], "local_date": TODAY}, "empty"), **common)
            self.assertFalse((stale / "xauusd.md").exists())


class ออกทั้งFและGในวันที่เงื่อนไขครบ(unittest.TestCase):
    """คำสั่งผู้ใช้ 2026-08-13 — วันที่ G ผลิตได้ ต้องได้ F ควบมาด้วย ไม่ใช่เลือกอย่างเดียว

    G ผลิตไม่ได้ทุกวัน (ต้องมีเหตุการณ์แรงรอ + ช่องแนวโน้มพิสูจน์ได้ + ราคายังอยู่ในช่อง)
    ⇒ เทสต้องล็อกทั้งสองเส้นทาง ไม่ใช่แค่เส้นที่ออกคู่
    """

    def _common(self, root: str) -> dict:
        return {"asset": "xauusd", "timeframe": None, "publish_root": Path(root),
                "cutoff_at": "2026-02-24T02:00:00+00:00",
                "fetcher": lambda asset: ({}, make_rows(), "fixture")}

    def _folders(self, root: str) -> tuple[Path, Path]:
        day = Path(root) / "24-02-2026"
        return (day / brief_writer.FOLDERS[brief_story.STYLE_F],
                day / brief_writer.FOLDERS[brief_story.STYLE_G])

    def test_วันที่เงื่อนไขGครบได้ทั้งสองใบพร้อมภาพคนละพันธุ์(self):
        with tempfile.TemporaryDirectory() as root:
            results = brief_pipeline.run_pair(
                calendar_source=lambda asset: ({"events": calendar_events(),
                                                "sentences": [], "local_date": TODAY}, "ok"),
                **self._common(root))
            self.assertEqual([r["style"] for r in results],
                             [brief_story.STYLE_G, brief_story.STYLE_F])
            self.assertTrue(all(r["ok"] for r in results), msg=results)
            folder_f, folder_g = self._folders(root)
            for folder in (folder_f, folder_g):
                self.assertTrue((folder / "xauusd.md").is_file(), folder)
                # ภาพต้องเกิดคู่บททุกใบ — ใบที่ไม่มีภาพคือใบที่เว็บตีกลับทั้งใบ
                self.assertEqual(len(list(folder.glob("xauusd*.webp"))), 1, folder)
            # คนละพันธุ์จริง ไม่ใช่บทเดียวกันวางสองที่
            self.assertNotEqual((folder_f / "xauusd.md").read_text(encoding="utf-8"),
                                (folder_g / "xauusd.md").read_text(encoding="utf-8"))

    def test_วันที่เงื่อนไขGไม่ครบยังได้Fใบเดียวตามเดิม(self):
        with tempfile.TemporaryDirectory() as root:
            results = brief_pipeline.run_pair(
                calendar_source=lambda asset: ({"events": [], "sentences": [],
                                                "local_date": TODAY}, "empty"),
                **self._common(root))
            self.assertEqual([r["style"] for r in results], [brief_story.STYLE_F])
            folder_f, folder_g = self._folders(root)
            self.assertTrue((folder_f / "xauusd.md").is_file())
            self.assertFalse((folder_g / "xauusd.md").exists())

    def test_ใบของรอบก่อนไม่รอดมานอนปนของสด(self):
        """🪤 กับดักของการเลิกกวาดโฟลเดอร์อีกสไตล์ — รอบคู่ต้องเขียนทับ ไม่ใช่ปล่อยผ่าน"""
        with tempfile.TemporaryDirectory() as root:
            common = self._common(root)
            brief_pipeline.run_pair(calendar_source=lambda asset: (
                {"events": calendar_events(), "sentences": [], "local_date": TODAY}, "ok"),
                **common)
            folder_f, folder_g = self._folders(root)
            (folder_f / "xauusd.md").write_text("ของรอบก่อน", encoding="utf-8")
            # รอบถัดมาเงื่อนไข G ไม่ครบแล้ว ⇒ ได้ F ใบเดียว และ G เก่าต้องหาย
            brief_pipeline.run_pair(calendar_source=lambda asset: (
                {"events": [], "sentences": [], "local_date": TODAY}, "empty"), **common)
            self.assertFalse((folder_g / "xauusd.md").exists())
            self.assertNotEqual((folder_f / "xauusd.md").read_text(encoding="utf-8"),
                                "ของรอบก่อน")


class เลขลำดับหัวข้อต้องต่อเนื่องเสมอ(unittest.TestCase):
    """🪤 กับดักที่เกิดพร้อมโครงใหม่ 08-11 — หัวข้อปฏิทินหายได้ทั้งหัว

    ถ้าเลขลำดับถูกฝังไว้ในชื่อหัวข้อ รอบที่ไม่มีปฏิทินจะได้บทที่นับ 1 · 3 · 4
    ซึ่งคนอ่านตีความว่าหน้าเว็บโหลดไม่ครบ ไม่ใช่ว่าเราตั้งใจตัด
    · **ต้องตรวจทั้งสองรอบ** (มีปฏิทิน/ไม่มี) ไม่งั้นเทสรับรองแค่เส้นทางเดียว
    """

    def _ordinals(self, markdown: str) -> list[int]:
        return [int(m.group(1)) for m in re.finditer(r"(?m)^## (\d+)\. ", markdown)]

    def test_ทั้งสองสไตล์นับหัวข้อต่อเนื่องไม่ว่ามีปฏิทินหรือไม่(self):
        for events in (None, calendar_events()):
            for sentences in ([], ["จันทร์ 24 ก.พ. เวลา 20:30 น. รายการทดสอบ"]):
                brief = build(events=events, sentences=sentences)
                with self.subTest(style=brief["style"], calendar=bool(sentences)):
                    markdown = brief_writer.render_article(brief)
                    ordinals = self._ordinals(markdown)
                    self.assertEqual(ordinals, list(range(1, len(ordinals) + 1)), markdown)
                    # มีปฏิทิน = ต้องได้สี่หัว · ไม่มี = สามหัว (หัวปฏิทินหายทั้งหัว)
                    self.assertEqual(len(ordinals), 4 if sentences else 3)


if __name__ == "__main__":
    unittest.main()
