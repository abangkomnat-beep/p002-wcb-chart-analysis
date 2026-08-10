"""เทสสเปกพาดหัว SEO — คำสั่งหัวหน้าผ่านผู้ใช้ 2026-08-10

ตัวอย่างที่ให้มาเป็น**สัญญา** ไม่ใช่แนวทาง:

    Title : วิเคราะห์ทองคำวันนี้ 6 สิงหาคม 2569 — แนวโน้มราคาทอง XAU/USD
    H1    : วิเคราะห์ทองคำวันนี้ 6 ส.ค. 2569 — ทองยืน 4,262 รอ Fed ชี้ทาง

ไฟล์นี้คุมสเปกข้ามทุกสไตล์ (A/B/C ผ่าน `wcb_writers` · D/E ผ่านตัวเขียนของตัวเอง)
ส่วนเทสเฉพาะสไตล์อยู่ในไฟล์ของสไตล์นั้น
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import headline_format, wcb_source, wcb_writers  # noqa: E402

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "wcb-snapshot-xauusd.json"


class รูปแบบวันที่ไทย(unittest.TestCase):

    def test_ปีเป็น_พศ_ทั้งเดือนย่อและเดือนเต็ม(self):
        self.assertEqual(headline_format.thai_date("2026-08-06"), "6 ส.ค. 2569")
        self.assertEqual(headline_format.thai_date("2026-08-06", full_month=True),
                         "6 สิงหาคม 2569")

    def test_ตรงกับตัวอย่างที่หัวหน้าให้มาเป๊ะ(self):
        self.assertEqual(headline_format.title("xauusd", "2026-08-06"),
                         "วิเคราะห์ทองคำวันนี้ 6 สิงหาคม 2569 — แนวโน้มราคาทอง XAU/USD")
        self.assertEqual(headline_format.h1("xauusd", "2026-08-06", "ทองยืน 4,262 รอ Fed ชี้ทาง"),
                         "วิเคราะห์ทองคำวันนี้ 6 ส.ค. 2569 — ทองยืน 4,262 รอ Fed ชี้ทาง")

    def test_เดือนครบสิบสองทั้งสองแบบ(self):
        self.assertEqual(len(headline_format.MONTH_ABBR), 12)
        self.assertEqual(len(headline_format.MONTH_FULL), 12)
        # ห้ามมีเดือนซ้ำ — ซ้ำแล้ววันที่บนบทจะผิดเงียบ ๆ ทั้งเดือน
        self.assertEqual(len(set(headline_format.MONTH_FULL)), 12)

    def test_ปีข้ามศตวรรษยังบวกถูก(self):
        self.assertEqual(headline_format.buddhist_year("1999"), 2542)
        self.assertEqual(headline_format.buddhist_year(2000), 2543)


class ทะเบียนคำค้นต่อสินทรัพย์(unittest.TestCase):
    """ทุกสินทรัพย์ที่ลงทะเบียนต้องพาดหัวได้ — ไม่ใช่แค่ทองที่หัวหน้ายกตัวอย่าง"""

    def test_ทุกสินทรัพย์มีชื่อและหางของตัวเอง(self):
        for asset in wcb_source.ASSET_PROFILES:
            with self.subTest(asset=asset):
                profile = wcb_source.ASSET_PROFILES[asset]
                self.assertIn("seo_name", profile, "ลืมลงทะเบียน seo_name")
                self.assertIn("seo_tail", profile, "ลืมลงทะเบียน seo_tail")

    def test_ชื่อในพาดหัวต้องไม่ใช่ชื่อยาวที่ใช้ในเนื้อบท(self):
        """ทองเป็นเคสที่ชัดที่สุด: เนื้อบทเรียก "ทองคำโลก" แต่คนไทยค้น "ทองคำ" """
        self.assertEqual(headline_format.seo_name("xauusd"), "ทองคำ")
        self.assertEqual(headline_format.seo_name("usdthb"), "ค่าเงินบาท")

    def test_title_ทุกตัวอยู่ในงบความยาว(self):
        """เกินงบ = Google ตัดกลางคัน คำท้ายที่ตั้งใจใส่หายไป"""
        for asset in wcb_source.ASSET_PROFILES:
            with self.subTest(asset=asset):
                text = headline_format.title(asset, "2026-12-31")
                self.assertLessEqual(len(text), headline_format.SEO_TITLE_BUDGET, text)

    def test_หางของ_title_ไม่ซ้ำกันข้ามสินทรัพย์(self):
        tails = [headline_format.seo_tail(a) for a in wcb_source.ASSET_PROFILES]
        self.assertEqual(len(tails), len(set(tails)), "หางซ้ำ = สองสินทรัพย์พาดหัวเหมือนกัน")


class เทียบพาดหัวว่าซ้ำกันไหม(unittest.TestCase):

    def test_ช่องว่างส่วนเกินไม่ทำให้หลุดด่าน(self):
        self.assertTrue(headline_format.same_headline("ก ข  ค", " ก  ข ค "))
        self.assertFalse(headline_format.same_headline("ก ข ค", "ก ข ง"))


class พาดหัวสาย_ABC(unittest.TestCase):
    """A/B/C ไม่มี H1 (กฎ `heading_h1` ห้าม `#` ในเนื้อบทตามสัญญาไฟล์กับเว็บ)
    ⇒ สเปกมีผลกับช่อง `title:` ใน frontmatter เท่านั้น"""

    @classmethod
    def setUpClass(cls):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.evidence = wcb_source.normalize(payload)
        cls.titles = {}
        for writer in wcb_writers.WCB_WRITERS:
            article = writer["render"](cls.evidence)
            found = re.search(r"(?m)^title:\s*(.+?)\s*$", article)
            cls.titles[writer["id"]] = found.group(1)

    def test_ทุกสไตล์ขึ้นต้นตามสเปกและใช้เดือนเต็มกับ_พศ(self):
        prefix = headline_format.prefix("xauusd", self.evidence["local_date"],
                                        full_month=True)
        for style, title in self.titles.items():
            with self.subTest(style=style):
                self.assertTrue(title.startswith(prefix), f"{title!r} ไม่ขึ้นต้นด้วย {prefix!r}")
                self.assertIn("2569", title)
                self.assertNotIn("2026", title)

    def test_สามสไตล์ต้องพาดหัวไม่ซ้ำกัน(self):
        """เว็บตั้งชื่อบทจากสินทรัพย์+วันที่ — พาดหัวซ้ำแปลว่าแยกใบไม่ออก"""
        values = list(self.titles.values())
        self.assertEqual(len(values), 3)
        self.assertEqual(len(values), len(set(values)), values)

    def test_ไม่มี_H1_หลุดเข้าเนื้อบท(self):
        for writer in wcb_writers.WCB_WRITERS:
            with self.subTest(style=writer["id"]):
                body = writer["render"](self.evidence).split("---", 2)[-1]
                self.assertFalse(any(line.startswith("# ") for line in body.splitlines()),
                                 "สาย A/B/C ห้ามมี H1 ตามสัญญาไฟล์กับเว็บ")


if __name__ == "__main__":
    unittest.main()
