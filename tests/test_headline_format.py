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

from tools import chart_indicator, chart_indicator_writer  # noqa: E402
from tools import chart_story, chart_story_writer  # noqa: E402
from tools import headline_format, wcb_source, wcb_writers  # noqa: E402

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "wcb-snapshot-xauusd.json"
ROWS_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "xau_420_sessions_2026-08-07.json"


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
    """A/B/C มีทั้ง `title:` และ H1 ตั้งแต่ 2026-08-10 (คำสั่งผู้ใช้: ทุกสไตล์ต้องมีทั้งคู่)

    ⚠️ **ข้อเท็จจริงที่ค้างอยู่:** ทีมเว็บระบุ 08-09 ว่า `title` เป็นทั้ง Title tag และ H1
    บนหน้าบท (ช่องเดียวกัน) ⇒ การมี `#` ในไฟล์ทำให้หน้าเว็บมี H1 สองอัน · ทำตามคำสั่ง
    ผู้ใช้ที่ยืนยันแล้ว และตั้งคำถามกลับไปที่ทีมเว็บว่าจะเปิดช่อง H1 แยกให้ไหม
    """

    @classmethod
    def setUpClass(cls):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.evidence = wcb_source.normalize(payload)
        cls.titles = {}
        cls.h1s = {}
        for writer in wcb_writers.WCB_WRITERS:
            article = writer["render"](cls.evidence)
            found = re.search(r"(?m)^title:\s*(.+?)\s*$", article)
            cls.titles[writer["id"]] = found.group(1)
            cls.h1s[writer["id"]] = next(line[2:] for line in article.splitlines()
                                         if line.startswith("# "))

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

    def test_ทุกสไตล์มีทั้ง_title_และ_H1_และต้องไม่เหมือนกัน(self):
        for style in self.titles:
            with self.subTest(style=style):
                self.assertTrue(self.titles[style], "ไม่มี title")
                self.assertTrue(self.h1s[style], "ไม่มี H1")
                self.assertFalse(headline_format.same_headline(self.titles[style],
                                                               self.h1s[style]),
                                 "title กับ H1 เหมือนกัน")

    def test_H1_ใช้เดือนย่อ_และผูกกับราคาของวัน(self):
        for style, h1 in self.h1s.items():
            with self.subTest(style=style):
                self.assertIn(headline_format.thai_date(self.evidence["local_date"]), h1)
                self.assertIn(wcb_writers.price(self.evidence["quote"]["price"],
                                                self.evidence), h1)

    def test_H1_มีตัวเดียวและอยู่บรรทัดแรกของเนื้อบท(self):
        for writer in wcb_writers.WCB_WRITERS:
            with self.subTest(style=writer["id"]):
                body = writer["render"](self.evidence).split("---", 2)[-1]
                lines = [line for line in body.splitlines() if line.strip()]
                self.assertTrue(lines[0].startswith("# "), "H1 ต้องเป็นบรรทัดแรกของเนื้อบท")
                self.assertEqual(sum(1 for line in lines if line.startswith("# ")), 1)


class พาดหัวข้ามทุกสไตล์(unittest.TestCase):
    """ที่เดียวที่เห็น Title ของทั้งห้าสไตล์พร้อมกัน — ตัวที่ควรมีตั้งแต่แรกแต่ไม่มี

    **บั๊กที่ทำให้ต้องมีไฟล์นี้ (ผู้ใช้จับได้ 2026-08-10):** สไตล์ D เรียก
    `headline_format.title()` โดยไม่ส่งหางของตัวเอง จึงตกไปใช้หางคงที่ของทะเบียน
    ซึ่งเป็นหางของสไตล์ A ⇒ **A กับ D ได้ Title เหมือนกันเป๊ะทั้งบรรทัด**

    ของที่มีอยู่ตอนนั้นจับไม่ได้เลยสักตัว:
    - `พาดหัวสาย_ABC.test_สามสไตล์ต้องพาดหัวไม่ซ้ำกัน` เดินจาก `wcb_writers.WCB_WRITERS`
      ซึ่งมีแค่ A/B/C — D/E อยู่คนละโมดูล จึงไม่เคยถูกเอามาเทียบกับใคร
    - เทสของ D กับของ E ต่างคนต่างตรวจบทของตัวเอง ไม่มีใครเห็นของอีกฝั่ง

    ⇒ บทเรียน: **ด่านที่ตรวจแค่สมาชิกในทะเบียนเดียว จับการชนข้ามทะเบียนไม่ได้**
    ตัวนี้จึงประกอบรายชื่อจากตัวผลิต Title ตัวจริงของแต่ละสไตล์ ไม่ใช่จากทะเบียนใดทะเบียนหนึ่ง

    ⚠️ **เทียบที่ "หาง" ไม่ใช่พาดหัวเต็มบรรทัด** — เทสฉบับร่างแรกเทียบเต็มบรรทัดแล้ว
    เขียวทั้งที่สวมบั๊กกลับเข้าไปแล้ว เพราะ A/B/C ลงวันที่ของ snapshot ส่วน D/E ลงวันที่
    ของแท่งปิดล่าสุด — คนละวันกัน พาดหัวจึงไม่ซ้ำ "โดยบังเอิญ" ทั้งที่หางเหมือนกันเป๊ะ
    วันไหนสองฝั่งบังเอิญตรงวันกันถึงจะระเบิด ⇒ เทียบหางคือเทียบสิ่งที่เป็นสัญญาจริง
    """

    @classmethod
    def setUpClass(cls):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        evidence = wcb_source.normalize(payload)
        rows = json.loads(ROWS_FIXTURE.read_text(encoding="utf-8"))

        cls.titles = {}
        for writer in wcb_writers.WCB_WRITERS:
            article = writer["render"](evidence)
            cls.titles[writer["id"]] = re.search(r"(?m)^title:\s*(.+?)\s*$",
                                                 article).group(1)
        cls.titles["d_structure"] = chart_story_writer.seo_title(
            chart_story.build_story(rows, asset="xauusd"))
        cls.titles["e_indicator"] = chart_indicator_writer.seo_title(
            chart_indicator.build_indicators(rows, asset="xauusd"))
        cls.tails = {style: title.split(headline_format.SEPARATOR, 1)[-1].strip()
                     for style, title in cls.titles.items()}

    def test_ครบทั้งห้าสไตล์(self):
        """กันไม่ให้ใครเพิ่มสไตล์ที่หกแล้วลืมพามาเทียบด้วย"""
        self.assertEqual(len(self.titles), 5, sorted(self.titles))

    def test_ไม่มีสองสไตล์ไหนใช้หางเดียวกัน(self):
        """เว็บตั้งชื่อบทจากสินทรัพย์+วันที่ — สองใบพาดหัวเดียวกันแยกไม่ออกว่าใบไหนเป็นใบไหน

        และในมุม SEO คือหน้าสองหน้าแย่งคำค้นเดียวกันเอง
        """
        seen = {}
        for style, tail in sorted(self.tails.items()):
            self.assertNotIn(tail, seen,
                             f"'{style}' ใช้หางเดียวกับ '{seen.get(tail)}': {tail}")
            seen[tail] = style

    def test_ทุกสไตล์ส่งหางของตัวเองมาจริง(self):
        """หางทะเบียนเป็นของสไตล์ A ตัวเดียว — ตัวอื่นตกมาใช้เมื่อไหร่คือลืมส่งหาง

        เขียนแยกจากตัวข้างบนเพราะอาการต่างกัน: ตัวข้างบนบอกว่า "ชนกัน"
        ตัวนี้บอกว่า **"ชนเพราะลืมส่งหาง"** ซึ่งเป็นสาเหตุที่เกิดจริงและจะเกิดซ้ำได้ง่ายสุด
        """
        registry_tail = headline_format.seo_tail("xauusd")
        for style, tail in self.tails.items():
            with self.subTest(style=style):
                if style == "a_standard":
                    self.assertEqual(tail, registry_tail)
                else:
                    self.assertNotEqual(tail, registry_tail,
                                        f"'{style}' ตกไปใช้หางทะเบียนของ A")

    def test_ทุกสไตล์ยังขึ้นต้นตามสเปกและมีสัญลักษณ์สินทรัพย์(self):
        """หางเปลี่ยนได้ แต่ส่วนหน้ากับสัญลักษณ์เป็นสัญญา ไม่ใช่รสนิยม

        สัญลักษณ์ในพาดหัวมีไว้กันบทของคู่เงินขึ้นหัวเป็นทอง (เคยเกิดจริง)
        """
        for style, title in self.titles.items():
            with self.subTest(style=style):
                self.assertTrue(title.startswith("วิเคราะห์ทองคำวันนี้ "), title)
                self.assertIn(headline_format.SEPARATOR.strip(), title)
                self.assertIn("XAU/USD", title)


if __name__ == "__main__":
    unittest.main()
