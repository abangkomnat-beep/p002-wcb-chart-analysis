"""เทสสเปกพาดหัว SEO — คำสั่งหัวหน้าผ่านผู้ใช้ 2026-08-10

ตัวอย่างที่ให้มาเป็น**สัญญา** ไม่ใช่แนวทาง:

    Title : วิเคราะห์ทองคำวันนี้ 6 สิงหาคม 2026 — แนวโน้มราคาทอง XAU/USD
    H1    : วิเคราะห์ทองคำวันนี้ 6 ส.ค. 2026 — ทองยืน 4,262 รอ Fed ชี้ทาง

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

# เดือนที่สะกดยาวที่สุด = กรณีแย่สุดของงบความยาว · ธันวาคมที่เคยใช้ไม่ใช่ตัวที่ยาวสุด
LONGEST_MONTH_DATE = "2026-02-28"


def _real_style_tails() -> dict[str, str]:
    """ดึงหางจริงของทั้งห้าสไตล์จาก**ตัวผลิตตัวจริง** ไม่ใช่พิมพ์ซ้ำไว้ในเทส

    บทเรียนที่แลกมาแล้ว: ด่านที่เดินจากรายชื่อที่พิมพ์ไว้เองจะไม่รู้เรื่องเมื่อของจริง
    เปลี่ยน · ที่นี่จึง render บททองของทุกสไตล์แล้วแกะหางออกมา ⇒ ใครแก้ถ้อยคำหาง
    ในตัวเขียน งบความยาวถูกวัดใหม่ให้อัตโนมัติ ไม่ต้องมาแก้เทสให้ตรงกันสองที่
    """
    evidence = wcb_source.normalize(json.loads(FIXTURE.read_text(encoding="utf-8")))
    rows = json.loads(ROWS_FIXTURE.read_text(encoding="utf-8"))
    titles = {w["id"]: re.search(r"(?m)^title:\s*(.+?)\s*$", w["render"](evidence)).group(1)
              for w in wcb_writers.WCB_WRITERS}
    titles["d_structure"] = chart_story_writer.seo_title(
        chart_story.build_story(rows, asset="xauusd"))
    titles["e_indicator"] = chart_indicator_writer.seo_title(
        chart_indicator.build_indicators(rows, asset="xauusd"))
    return {style: title.split(headline_format.SEPARATOR, 1)[-1].strip()
            for style, title in titles.items()}


def STYLE_TAILS(profile: dict) -> dict[str, str]:
    """หางของทุกสไตล์สำหรับสินทรัพย์หนึ่งตัว — สลับสัญลักษณ์ของทองเป็นของตัวนั้น

    หางของ B/C/D/E เป็น f-string ที่ต่อ `profile['symbol']` ท้ายข้อความคงที่
    จึงแทนที่สัญลักษณ์ได้ตรง ๆ · สไตล์ A ใช้หางคงที่จากทะเบียนของสินทรัพย์นั้นเอง
    """
    gold = wcb_source.ASSET_PROFILES["xauusd"]["symbol"]
    tails = {style: tail.replace(gold, profile["symbol"])
             for style, tail in _real_style_tails().items()}
    tails["a_standard"] = None      # None = ให้ `title()` หยิบหางทะเบียนของตัวเอง
    return tails


class รูปแบบวันที่ไทย(unittest.TestCase):

    def test_ปีเป็น_คศ_ทั้งเดือนย่อและเดือนเต็ม(self):
        self.assertEqual(headline_format.thai_date("2026-08-06"), "6 ส.ค. 2026")
        self.assertEqual(headline_format.thai_date("2026-08-06", full_month=True),
                         "6 สิงหาคม 2026")

    def test_ตรงกับตัวอย่างที่หัวหน้าให้มาเป๊ะ(self):
        self.assertEqual(headline_format.title("xauusd", "2026-08-06"),
                         "วิเคราะห์ทองคำวันนี้ 6 สิงหาคม 2026 — แนวโน้มราคาทอง XAU/USD")
        self.assertEqual(headline_format.h1("xauusd", "2026-08-06", "ทองยืน 4,262 รอ Fed ชี้ทาง"),
                         "วิเคราะห์ทองคำวันนี้ 6 ส.ค. 2026 — ทองยืน 4,262 รอ Fed ชี้ทาง")

    def test_เดือนครบสิบสองทั้งสองแบบ(self):
        self.assertEqual(len(headline_format.MONTH_ABBR), 12)
        self.assertEqual(len(headline_format.MONTH_FULL), 12)
        # ห้ามมีเดือนซ้ำ — ซ้ำแล้ววันที่บนบทจะผิดเงียบ ๆ ทั้งเดือน
        self.assertEqual(len(set(headline_format.MONTH_FULL)), 12)

    def test_ไม่มีการแปลงปีหลงเหลือในระบบ(self):
        """🔄 08-11: ถอด `buddhist_year()` ออกพร้อมการกลับไปใช้ ค.ศ.

        เทสนี้กันของกลับมาแบบเงียบ ๆ — ถ้าใครเติมตัวแปลงปีกลับเข้ามา แปลว่ามีสองระบบปี
        เดินอยู่พร้อมกันอีกครั้ง ซึ่งเป็นต้นตอของอาการ D-4.5 ที่โดนตีกลับมาแล้ว
        ⇒ จะกลับไป พ.ศ. ต้องกลับทั้งชุด (ตัวพิมพ์ + สองด่าน) ไม่ใช่แอบเติมตัวแปลง
        """
        self.assertFalse(hasattr(headline_format, "buddhist_year"))
        self.assertFalse(hasattr(headline_format, "BUDDHIST_OFFSET"))
        # ปีที่พิมพ์ออกต้องเท่ากับปีในทะเบียนเป๊ะ ไม่มีการบวกลบ
        for date_text in ("1999-01-01", "2026-08-06", "2035-12-31"):
            with self.subTest(date=date_text):
                self.assertIn(date_text[:4], headline_format.thai_date(date_text))


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

    def test_ทะเบียนตรงกับสเปกของหัวหน้าทีละตัวอักษร(self):
        """ที่มา: `01-Lead/Input/10-08-2026/` — ลอกมา ไม่ได้แต่งเอง

        ล็อกไว้เพราะสองช่องนี้หน้าตาเหมือน "ถ้อยคำที่ปรับได้ตามใจ" ทั้งที่เป็นสัญญา
        ที่มีตัวเลขวอลุ่มรองรับอยู่เบื้องหลัง · แก้เมื่อไหร่เทสตกก่อนถึงเว็บ
        """
        spec = {
            "xauusd": ("ทองคำ", "แนวโน้มราคาทอง XAU/USD"),         # โภคภัณฑ์ §2
            "eurusd": ("EUR/USD", "แนวโน้มยูโรต่อดอลลาร์"),          # Forex §1 + กฎ 8–9
            "gbpusd": ("ค่าเงินปอนด์", "แนวโน้ม GBP/USD"),           # Forex §1
            "usdthb": ("ค่าเงินบาท", "แนวโน้ม USD/THB"),             # Forex §1
            "btcusd": ("บิทคอยน์", "แนวโน้มราคาบิทคอยน์ BTC"),       # คริปโต §1 + กฎ 8
            "solusd": ("SOL", "แนวโน้มราคา SOL"),                    # คริปโต §1 กลุ่มไม่มีวอลุ่ม
            "nvda": ("หุ้น NVIDIA", "แนวโน้มหุ้น NVDA"),             # หุ้น §1 + กฎ 7–9
        }
        self.assertEqual(set(spec), set(wcb_source.ASSET_PROFILES),
                         "เพิ่ม/ลบสินทรัพย์แล้วยังไม่ได้เปิดสเปกหาพาดหัวของตัวนั้น")
        for asset, (name, tail) in spec.items():
            with self.subTest(asset=asset):
                self.assertEqual(headline_format.seo_name(asset), name)
                self.assertEqual(headline_format.seo_tail(asset), tail)

    def test_เว้นวรรครอบชื่อเฉพาะฝั่งที่เป็นอักษรละติน(self):
        """สเปกเขียนไว้ทั้งสามแบบ — ถ้าประกอบผิดจะได้ 'วิเคราะห์EUR/USDวันนี้'"""
        cases = {
            "xauusd": "วิเคราะห์ทองคำวันนี้ ",        # ไทยล้วน ติดกันหมด
            "eurusd": "วิเคราะห์ EUR/USD วันนี้ ",     # ละตินล้วน เว้นสองข้าง
            "nvda": "วิเคราะห์หุ้น NVIDIA วันนี้ ",     # ไทยนำ ละตินท้าย เว้นข้างเดียว
        }
        for asset, want in cases.items():
            with self.subTest(asset=asset):
                got = headline_format.prefix(asset, "2026-08-10", full_month=True)
                self.assertTrue(got.startswith(want), f"{got!r} ไม่ขึ้นต้นด้วย {want!r}")

    def test_ชื่อที่ใช้ในเนื้อบทต้องเป็นอักษรไทยหัวท้าย(self):
        """`thai_name`/`short_name` ถูกต่อกับคำไทยตรง ๆ ไม่มีตัวเว้นวรรคคั่นให้

        ตัวเขียนต่อแบบนี้อยู่ 13 จุด เช่น `f"{short_name}อยู่ที่ ..."` และ
        `f"ราคา{short_name}แบบเรียลไทม์"` ⇒ ใส่ ticker ละตินลงช่องนี้เมื่อไหร่
        บทจะอ่านว่า "NVIDIAอยู่ที่" ติดกันทันที **โดยไม่มีเทสไหนตกให้เห็น**
        (เกือบพลาดจริงตอนรับสเปกหุ้น 2026-08-10 — กฎ "ชื่อบริษัทเป็นอังกฤษ" ของสเปก
        มีขอบเขตแค่พาดหัว ส่วนช่องนี้เป็นร้อยแก้ว)

        ช่องพาดหัว `seo_name` ไม่ต้องอยู่ใต้กฎนี้ เพราะ `_pad()` เว้นวรรคให้เอง
        """
        for asset, profile in wcb_source.ASSET_PROFILES.items():
            for field in ("thai_name", "short_name"):
                with self.subTest(asset=asset, field=field):
                    value = profile[field]
                    for ch in (value[0], value[-1]):
                        self.assertTrue(headline_format._thai_letter(ch),
                                        f"{asset}.{field} = {value!r} "
                                        "จะไปติดกับคำไทยในบทโดยไม่มีเว้นวรรค")

    def test_หุ้นสหรัฐต้องบอกชนิดเครื่องมือในบท(self):
        """พาดหัวเรียก "หุ้น" ตามสเปกได้ แต่บทต้องบอกว่าจริง ๆ เป็น CFD

        สเปกหุ้น กฎ 7–8 สั่งให้ใส่คำว่า `หุ้น` นำหน้าเพราะวอลุ่มต่างกัน 37 เท่า
        (`หุ้น nvidia` 22,200 vs `วิเคราะห์หุ้น nvda` 170) — ทำตามแล้ว แต่สินค้าเรา
        เป็นสัญญาซื้อขายส่วนต่าง ไม่ใช่หุ้นบนกระดาน · การเรียกผิดชนิดสินค้าเป็นเรื่อง
        YMYL ⇒ ข้อความกำกับต้องอยู่ในบทเสมอ ห้ามหายไปเงียบ ๆ ตอนใครมาแก้ถ้อยคำ
        """
        profile = wcb_source.ASSET_PROFILES["nvda"]
        self.assertIn("สัญญาส่วนต่าง", profile["unit_phrase"])
        self.assertIn("หุ้น", headline_format.seo_name("nvda"))

    def test_title_ทุกตัวอยู่ในงบความยาว(self):
        """เกินงบ = Google ตัดกลางคัน คำท้ายที่ตั้งใจใส่หายไป

        ⚠️ **วัด "หางครบทุกสไตล์" ไม่ใช่แค่หางทะเบียน** — ของเดิมเรียก `title()`
        โดยไม่ส่งหาง จึงวัดแต่หางของสไตล์ A · หาง B/C/D/E ยาวกว่าทุกตัวและไม่เคย
        ถูกวัดเลย (ข้อผูกพันที่กระดานบันทึกไว้ว่าต้องปิดก่อนเปิดสินทรัพย์ตัวที่สอง)

        เดือนที่ยาวที่สุดคือกุมภาพันธ์ ไม่ใช่ธันวาคม — ของเดิมวัดด้วย 2026-12-31
        ซึ่งไม่ใช่กรณีแย่สุด
        """
        for asset, profile in wcb_source.ASSET_PROFILES.items():
            for style, tail in STYLE_TAILS(profile).items():
                with self.subTest(asset=asset, style=style):
                    text = headline_format.title(asset, LONGEST_MONTH_DATE, tail)
                    self.assertLessEqual(headline_format.display_width(text),
                                         headline_format.SEO_TITLE_BUDGET, text)

    def test_งบความยาววัดด้วยความกว้างจริงไม่ใช่จำนวนจุดรหัส(self):
        """สระบน/ล่างกินความกว้างศูนย์ — `len()` นับเกินจริงเสมอกับภาษาไทย

        ตัวเลขในเทสนี้คือของจริงที่วัดได้ ถ้าใครเปลี่ยนกลับไปใช้ `len()` จะตกทันที
        """
        gold = headline_format.title("xauusd", "2026-02-28")
        self.assertEqual(len(gold), 64)
        self.assertEqual(headline_format.display_width(gold), 55)
        # ตัวอักษรที่ไม่มีสระซ้อนต้องนับเท่ากันทั้งสองวิธี — กันสูตรพังแบบเงียบ ๆ
        self.assertEqual(headline_format.display_width("XAU/USD 2026"), 12)

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

    def test_ทุกสไตล์ขึ้นต้นตามสเปกและใช้เดือนเต็มกับ_คศ(self):
        prefix = headline_format.prefix("xauusd", self.evidence["local_date"],
                                        full_month=True)
        year = self.evidence["local_date"][:4]
        for style, title in self.titles.items():
            with self.subTest(style=style):
                self.assertTrue(title.startswith(prefix), f"{title!r} ไม่ขึ้นต้นด้วย {prefix!r}")
                self.assertIn(year, title)
                self.assertNotIn(str(int(year) + 543), title)

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
