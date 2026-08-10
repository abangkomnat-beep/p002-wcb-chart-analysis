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
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import brief_pipeline, brief_renderer, brief_story, brief_writer  # noqa: E402
from tools import image_output  # noqa: E402


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
    def test_ไม่มีหัวข้อย่อยและไม่มีตาราง(self):
        for events in (None, calendar_events()):
            markdown = brief_writer.render_article(build(events=events))
            body = markdown.split("---", 2)[-1]
            self.assertNotIn("\n## ", body)
            self.assertNotIn("|", body)

    def test_กล่องกลยุทธ์ครบสามบรรทัด(self):
        markdown = brief_writer.render_article(build())
        for label in ("กลยุทธ์ : ", "แนวต้าน : ", "แนวรับ : "):
            self.assertIn(label, markdown)

    def test_สไตล์F_จบด้วยเงื่อนไขเดียว(self):
        markdown = brief_writer.render_article(build())
        self.assertNotIn("แต่หาก", markdown)

    def test_สไตล์G_จบด้วยฉากทัศน์คู่และเอ่ยชื่อเหตุการณ์(self):
        brief = build(events=calendar_events())
        markdown = brief_writer.render_article(brief)
        self.assertIn("แต่หาก", markdown)
        self.assertIn("การจ้างงานนอกภาคเกษตร", markdown)
        self.assertIn("กลยุทธ์ : รอลุ้นการจ้างงานนอกภาคเกษตร", markdown)

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

    def test_หัวข้อย่อยที่แอบโผล่ตกทันที(self):
        brief = build()
        markdown = brief_writer.render_article(brief) + "\n## บทสรุป\n"
        result = brief_writer.validate(markdown, brief)
        self.assertIn("subheading_forbidden", [f["rule"] for f in result["findings"]])

    def test_กล่องกลยุทธ์ขาดบรรทัดตกทันที(self):
        brief = build()
        markdown = brief_writer.render_article(brief).replace("แนวรับ : ", "แนวรับ ")
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


class ทศนิยมตามสินทรัพย์(unittest.TestCase):
    """🪤 บั๊กประจำที่กลับมาทุกครั้งที่มีตัวเขียนใหม่เกิดในโลกของทอง (D · E · A/B/C)"""

    def test_คู่เงินต้องไม่ถูกปัดเหลือสองตำแหน่ง(self):
        rows = make_rows(start=1.15, step=1e-5, wave=2e-4, body=2e-5, wick=6e-5)
        brief = build(rows, asset="usdthb")
        markdown = brief_writer.render_article(brief)
        places = brief_writer.money_for(brief)(brief["current"]["close"])
        self.assertIn(places, markdown)
        self.assertGreaterEqual(len(places.split(".")[-1]), 3)


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
        self.assertIn("-brief-range-", brief_writer.image_name(build()))
        self.assertIn("-brief-channel-",
                      brief_writer.image_name(build(events=calendar_events())))

    def test_สายผลิตวางบทคู่ภาพครบ(self):
        rows = make_rows()
        with tempfile.TemporaryDirectory() as root:
            result = brief_pipeline.run(
                asset="xauusd", publish_root=Path(root), cutoff_at="2026-02-24T02:00:00+00:00",
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
                asset="xauusd", publish_root=Path(root), cutoff_at="2026-02-24T02:00:00+00:00",
                fetcher=lambda asset: ({}, rows, "fixture"),
                calendar_source=lambda asset: ({"events": [], "sentences": [],
                                                "local_date": None}, "unavailable: ทดสอบ"))
        self.assertTrue(result["ok"], msg=result["findings"])
        self.assertEqual(result["style"], brief_story.STYLE_F)

    def test_ของรอบก่อนของอีกสไตล์ต้องถูกกวาดทิ้ง(self):
        """กติกา 'ห้ามวางสองสไตล์ของวันเดียวกันขึ้นเว็บ' — ใบหลังทับใบแรกเงียบ ๆ บนเว็บ"""
        rows = make_rows()
        with tempfile.TemporaryDirectory() as root:
            common = {"asset": "xauusd", "publish_root": Path(root),
                      "cutoff_at": "2026-02-24T02:00:00+00:00",
                      "fetcher": lambda asset: ({}, rows, "fixture")}
            brief_pipeline.run(calendar_source=lambda asset: (
                {"events": calendar_events(), "sentences": [], "local_date": TODAY}, "ok"),
                **common)
            stale = Path(root) / "24-022026" / brief_writer.FOLDERS[brief_story.STYLE_G]
            self.assertTrue((stale / "xauusd.md").is_file())
            brief_pipeline.run(calendar_source=lambda asset: (
                {"events": [], "sentences": [], "local_date": TODAY}, "empty"), **common)
            self.assertFalse((stale / "xauusd.md").exists())


if __name__ == "__main__":
    unittest.main()
