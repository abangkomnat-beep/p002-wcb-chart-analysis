"""ด่านของบทรายเหตุการณ์ (ระยะ 1) — บทที่เล่าว่า "ตัวเลขออกมาที่เท่าไหร่เทียบคาด"

เทสสำคัญที่สุดสองตัวในไฟล์นี้:

    test_บทต้องไม่ชี้ทิศราคา         การชี้ทิศคือระยะ 3b ที่ผู้ใช้ยังไม่เคาะกติกา
                                     บทที่หลุดไปชี้ทิศเองคือการข้ามด่านอนุมัติ
    test_เลขทุกตัวชี้กลับก้อนได้      กฎ YMYL เดียวกับสายรายวัน ไม่มีข้อยกเว้น
                                     ให้บทต้นแบบ
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools import event_impact, event_report, wcb_copy_validator, wcb_source  # noqa: E402

FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "wcb-snapshot-eurusd.json"

# รายการจริงจากตาราง 2026-08-07 — เก็บรูปแบบค่าที่ต้นทางส่งมาจริงไว้ทั้งสามแบบ
# (เลขเปล่า · เลขติด % · เลขติดสัญลักษณ์เงิน) เพราะตัวอ่านเลขต้องรับได้ทุกแบบ
NFP = {"at": "2026-08-07 19:30", "country": "USD", "impact": "High",
       "title": "การจ้างงานนอกภาคเกษตร (NFP)",
       "actual": "92", "forecast": "80", "previous": "57"}
EURO_TRADE = {"at": "2026-08-07 13:00", "country": "EUR", "impact": "High",
              "title": "ดุลการค้า", "actual": "€15.4", "forecast": "€17.4", "previous": "€19.3"}
CHINA_TRADE = {"at": "2026-08-07 10:00", "country": "CNY", "impact": "High",
               "title": "การส่งออก", "actual": "23.9%", "forecast": "22.2%", "previous": "27%"}
FED_TALK = {"at": "2026-08-07 21:00", "country": "USD", "impact": "Medium",
            "title": "สุนทรพจน์ของ Fed Barkin",
            "actual": None, "forecast": None, "previous": None}
NOT_OUT_YET = {"at": "2026-08-11 21:00", "country": "USD", "impact": "High",
               "title": "ยอดขายบ้านมือสอง", "actual": None, "forecast": "4.07", "previous": "4.09"}

CALENDAR = [NOT_OUT_YET, FED_TALK, NFP, EURO_TRADE, CHINA_TRADE]


class ทะเบียนผลกระทบ(unittest.TestCase):
    def setUp(self):
        self.settings = event_impact.load()

    def test_ทะเบียนจับคู่ด้วยสกุลเงินไม่ใช่ชื่อรายการ(self):
        """ชื่อรายการเป็นข้อความอิสระที่ต้นทางแก้คำได้ทุกเมื่อ

        ถ้าวันหนึ่งมีคนเพิ่มการจับคู่ด้วยชื่อรายการเข้ามา เทสนี้จะตกทันที —
        เจตนาคือกันการอนุมานเศรษฐกิจรายตัว ("ยอดขายบ้านกระทบทองไหม")
        ซึ่งเราตรวจย้อนกลับไม่ได้ เข้ามาปนกับการจับคู่ที่เป็นข้อเท็จจริง
        """
        self.assertIn("currency_assets", self.settings)
        self.assertNotIn("title_assets", self.settings)
        for code in ("USD", "EUR", "GBP"):
            self.assertIn(code, self.settings["currency_assets"])

    def test_หุ้นสหรัฐอยู่ในทะเบียนแต่ยังไม่เปิดผลิต(self):
        """แยก "เกี่ยวข้อง" ออกจาก "ผลิตอยู่" — หัวหน้าตอบ 08-06 ว่าหุ้นสหรัฐยังไม่ใช่ตอนนี้

        ถ้าจะเปิด `nvda` ต้องเป็นคำสั่งของผู้ใช้ ไม่ใช่ผลข้างเคียงของการแก้โค้ด
        """
        self.assertIn("nvda", self.settings["currency_assets"]["USD"])
        self.assertNotIn("nvda", self.settings["assets_enabled_now"])
        self.assertEqual(self.settings["assets_enabled_now"][0], "xauusd",
                         "ลำดับที่หัวหน้าสั่งคือทองก่อน")

    def test_คัดเฉพาะรายการที่ประกาศแล้วและสำคัญพอ(self):
        events = event_impact.released_events(CALENDAR, self.settings)
        titles = [e["title"] for e in events]
        self.assertEqual(titles, ["การส่งออก", "ดุลการค้า", "การจ้างงานนอกภาคเกษตร (NFP)"],
                         "ต้องเรียงตามเวลา และเหลือเฉพาะตัวที่มีค่าประกาศแล้ว")
        self.assertNotIn("ยอดขายบ้านมือสอง", titles, "ยังไม่ประกาศ = ยังไม่มีบท")
        self.assertNotIn("สุนทรพจน์ของ Fed Barkin", titles, "Medium ยังไม่เปิด")

    def test_จับคู่สินทรัพย์ตามสกุลเงินและตัดด้วยตัวที่เปิดผลิต(self):
        self.assertEqual(event_impact.assets_for(NFP, self.settings),
                         ["xauusd", "eurusd", "gbpusd", "usdjpy", "btcusd"])
        self.assertEqual(event_impact.assets_for(EURO_TRADE, self.settings), ["eurusd"])
        self.assertEqual(event_impact.assets_for(CHINA_TRADE, self.settings), [],
                         "จีนยังไม่ลงทะเบียน = ยังไม่ตัดสิน ไม่ใช่ไม่มีผล")

    def test_รายการที่ตกไปต้องยังเห็นในใบสั่งงาน_ไม่หายเงียบ(self):
        """กติกา no silent caps — ของที่ถูกตัดต้องรายงานได้ว่าตัดเพราะอะไร"""
        rows = event_impact.plan(CALENDAR, self.settings)
        china = next(r for r in rows if r["event"]["country"] == "CNY")
        self.assertEqual(china["assets"], [])
        self.assertEqual(len(rows), 3)

    def test_ทะเบียนหายต้องระเบิดไม่ใช่เดาต่อ(self):
        with self.assertRaises(Exception):
            event_impact.load(Path("ไม่มีไฟล์นี้.json"))


class อ่านค่าปฏิทิน(unittest.TestCase):
    def test_อ่านได้ทุกรูปแบบที่ต้นทางส่งมาจริง(self):
        for raw, expected in (("80", 80.0), ("4.2%", 4.2), ("-0.4%", -0.4),
                              ("€15.4", 15.4), ("$112.5", 112.5), ("1,234", 1234.0)):
            with self.subTest(raw=raw):
                self.assertEqual(event_report.as_number(raw), expected)

    def test_อ่านไม่ออกต้องเงียบไม่ใช่เดา(self):
        for raw in (None, "", "ไม่ระบุ", "n/a", "—"):
            with self.subTest(raw=raw):
                self.assertIsNone(event_report.as_number(raw))
                self.assertEqual(event_report.comparison("80", raw), "")
                self.assertEqual(event_report.comparison(raw, "80"), "")

    def test_คำเปรียบเทียบตรงทั้งสามทาง(self):
        self.assertEqual(event_report.comparison("92", "80"), "สูงกว่า")
        self.assertEqual(event_report.comparison("€15.4", "€17.4"), "ต่ำกว่า")
        self.assertEqual(event_report.comparison("4.2%", "4.2%"), "เท่ากับ")
        # ติดลบต้องเทียบตามค่าจริง ไม่ใช่ค่าสัมบูรณ์
        self.assertEqual(event_report.comparison("-0.4%", "0.1%"), "ต่ำกว่า")

    def test_รู้ว่าค่าไหนมีหน่วยติดมา(self):
        self.assertTrue(event_report.has_unit("4.2%"))
        self.assertTrue(event_report.has_unit("€15.4"))
        self.assertFalse(event_report.has_unit("80"))


class บทรายเหตุการณ์(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.payload["calendar"] = {"events": CALENDAR}
        cls.evidence = wcb_source.normalize(cls.payload)
        cls.evidence["local_date"] = "2026-08-07"
        cls.article = event_report.render(NFP, cls.evidence)

    def test_ยังไม่ประกาศต้องเขียนไม่ได้(self):
        with self.assertRaises(ValueError):
            event_report.render(NOT_OUT_YET, self.evidence)

    def test_ค่าทั้งสามตัวต้องอยู่ในบทครบ(self):
        self.assertIn("ประกาศออกมาที่ 92", self.article)
        self.assertIn("สูงกว่าที่ตลาดคาดไว้ที่ 80", self.article)
        self.assertIn("สูงกว่าครั้งก่อนที่อยู่ที่ 57", self.article)
        self.assertIn("ปฏิทินเศรษฐกิจ WorldClassBroker", self.article)

    def test_บทต้องไม่ชี้ทิศราคา(self):
        """ระยะ 3b (`RL-006`) ยังไม่เปิด — ผู้ใช้ยังไม่เคาะกติกาการอนุมานทิศ

        บทนี้รายงานตัวเลขกับสภาพราคาเท่านั้น ถ้าวันหนึ่งมีคนเติมคำชี้ทิศเข้ามา
        เทสนี้ต้องตกก่อนบทจะหลุดออกไป
        """
        for banned in ("บวกต่อ", "ลบต่อ", "หนุนราคา", "กดราคา", "น่าจะขึ้น", "น่าจะลง",
                       "แนะนำ", "เข้าซื้อ", "ขายทำกำไร", "เป้าหมายราคา"):
            with self.subTest(คำ=banned):
                self.assertNotIn(banned, self.article)
        self.assertIn("ยังไม่สรุปว่าตัวเลขนี้จะพาราคาไปทางไหน", self.article)

    def test_คำกำกับหน่วยขึ้นเฉพาะตอนค่าไม่มีหน่วย(self):
        """ผูกกับ E9 — ค่าที่ติดหน่วยมาเองแล้วต้องไม่มีคำแก้ตัวโผล่มารก

        และเมื่อ E9 ปิด ประโยคนี้ต้องหายไปเองโดยไม่ต้องแก้โค้ด
        (บทเรียนจากบั๊กคำกำกับค่าคาดการณ์ 2026-08-07)
        """
        self.assertIn("ไม่มีช่องบอกหน่วย", self.article)          # NFP = เลขเปล่า
        with_unit = event_report.render(EURO_TRADE, self.evidence)
        self.assertNotIn("ไม่มีช่องบอกหน่วย", with_unit)
        self.assertIn("€15.4", with_unit)

    def test_ไม่พิมพ์ผลลบที่คำนวณเอง(self):
        """กติกาเดิมของทุกสไตล์ — บอกว่าสูงกว่าได้ แต่ห้ามบอกว่าสูงกว่าเท่าไร

        92 กับ 80 ต่างกัน 12 · เลข 12 ไม่มีอยู่ในก้อน snapshot
        """
        self.assertNotIn("12", self.article.split("---", 2)[-1])

    def test_พาดหัวไม่เกินเพดานของสายเว็บ(self):
        long_event = dict(NFP, title="รายการชื่อยาวมาก " * 12)
        self.assertLessEqual(len(event_report.headline(long_event)), 90)

    def test_ชื่อประเทศต้องเป็นภาษาคน_รหัสที่ไม่รู้จักต้องหยุดให้เห็น(self):
        """บั๊กจริงในบทใบแรกที่ผลิต 08-07 — บทเขียนว่า "ดุลการค้า ของEUR"

        รหัสดิบหลุดขึ้นบทเพราะไม่มีทะเบียนชื่อไทย · หลักเดียวกับ `_thai_code`
        ของสายรายวัน: **ห้ามมีค่าตั้งต้น** รหัสใหม่ต้องระเบิดก่อนบทออกไป
        """
        self.assertIn("ของยูโรโซน", event_report.render(EURO_TRADE, self.evidence))
        self.assertIn("ของสหรัฐ", self.article)
        with self.assertRaises(ValueError):
            event_report.render(dict(NFP, country="XYZ"), self.evidence)

    def test_เลขทุกตัวชี้กลับก้อนได้(self):
        """ด่าน YMYL เดียวกับสายรายวัน — บทต้นแบบก็ไม่มีข้อยกเว้น

        ตรวจเฉพาะกฎ `number_unsupported` โดยตั้งใจ กฎอื่นของสัญญาส่งออกเว็บ
        (ความยาว excerpt · หมุดกราฟ) ไม่ผูกกับบทชนิดนี้เพราะยังไม่ขึ้นเว็บ
        """
        for event in (NFP, EURO_TRADE):
            with self.subTest(รายการ=event["title"]):
                article = event_report.render(event, self.evidence)
                report = wcb_copy_validator.validate(article, self.payload)
                self.assertEqual([f for f in report["findings"]
                                  if f["rule"] == "number_unsupported"], [])

    def test_ต้องบอกวันที่จริงไม่ใช่เวลาลอย(self):
        """ทีมเว็บข้อ A-3 — บทถูกเก็บถาวร "เวลา 19:30 น." เฉย ๆ อ่านย้อนหลังไม่รู้วันไหน

        วันที่มาจากฟิลด์ `at` ของรายการเดียวกับเวลา จึงมีต้นทางเท่ากัน และเลข 7
        อยู่ในกองหลักฐานอยู่แล้ว (เทสเลขชี้กลับก้อนด้านบนครอบอยู่)
        """
        article = event_report.render(NFP, self.evidence)
        self.assertIn("เมื่อวันศุกร์ 7 ส.ค. เวลา 19:30 น. ตามเวลาไทย", article)
        for word in ("คืนนี้", "คืนพรุ่งนี้", "เมื่อเวลา 19:30"):
            self.assertNotIn(word, article)

    def test_at_ที่ถอดไม่ได้ต้องตัดทั้งวลี_ไม่พิมพ์โครงเปล่า(self):
        broken = dict(NFP, at="รูปแบบใหม่ที่ยังไม่รู้จัก")
        article = event_report.render(broken, self.evidence)
        self.assertNotIn("เมื่อวัน ", article)
        self.assertNotIn("เวลา  น.", article)
        self.assertIn("\nการจ้างงานนอกภาคเกษตร (NFP)ของสหรัฐ ซึ่งจัดเป็นรายการผลกระทบสูง "
                      "ประกาศออกมาที่ 92", article,
                      "อ่านวันเวลาไม่ออก = ตัดทั้งวลี แล้วประโยคขึ้นต้นด้วยชื่อรายการเลย")


if __name__ == "__main__":
    unittest.main()
