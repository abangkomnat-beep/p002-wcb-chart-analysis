"""ด่านของสายสาธารณะ A/B/C — กฎที่พังแล้วบทความหลุดออกไปโดยไม่มีใครเห็น

เทสสำคัญที่สุดในไฟล์นี้คือ `test_เลขทุกตัวในบทความชี้กลับ_snapshot_ได้`
เพราะมันคือกฎเดียวที่กันความผิดพลาดที่เกิดขึ้นจริงเมื่อ 2026-08-05 — บทความชุดแรก
มีตัวเลขที่ไม่มีต้นทางใน snapshot ปนอยู่ห้าตัว และไม่มีใครจับได้จนกว่าจะมีด่านนี้
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools import build_daily_package, license_gate, publish_layout  # noqa: E402
from tools import voice_rules, wcb_copy_validator, wcb_source, wcb_writers, writers  # noqa: E402


FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "wcb-snapshot-xauusd.json"
ALLOWED_TF = ("1h", "4h", "1day", "1week")
NUMBER = re.compile(r"\d[\d,]*\.\d+|\d{1,3}(?:,\d{3})+|\d+")
# เลขเชิงโครงสร้างที่ไม่ใช่ข้อมูลตลาด — ชุดเดียวกับด่าน validate_article.py
STRUCTURAL = (
    re.compile(r"\[\[chart:[^\]]*\]\]"),
    re.compile(r"\d{1,2}:\d{2}"),
    re.compile(r"\(\s*\d+\s*(?:,\s*\d+\s*)*\)"),
    re.compile(r"\d+\s*(?:วัน|ชั่วโมง|นาที|ปี|เดือน|สัปดาห์)(?:ทำการ)?"),
    re.compile(r"ราย\s*\d+"),
    re.compile(r"\b(?:19|20)\d{2}\b"),
)


def evidence_numbers(payload) -> set[float]:
    """กองหลักฐาน — เก็บค่าสัมบูรณ์เพราะบทความเขียน MACD -3.7 เป็น 3.7 พร้อมคำว่าติดลบ"""
    numbers: set[float] = set()

    def walk(node):
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, bool):
            return
        elif isinstance(node, (int, float)):
            numbers.add(abs(float(node)))
        elif isinstance(node, str):
            for token in re.findall(r"\d[\d,]*\.?\d*", node):
                try:
                    numbers.add(abs(float(token.replace(",", ""))))
                except ValueError:
                    pass

    walk(payload)
    return numbers


def strip_structural(line: str) -> str:
    for pattern in STRUCTURAL:
        line = pattern.sub(lambda m: " " * len(m.group(0)), line)
    return line


def split_frontmatter(article: str) -> tuple[dict, str]:
    match = re.match(r"^---\r?\n(.*?)\r?\n---", article, re.S)
    if not match:
        return {}, article
    fields = {}
    for line in match.group(1).splitlines():
        name, sep, value = line.partition(":")
        if sep:
            fields[name.strip()] = value.strip()
    return fields, article[match.end():]


class ฐานสายสาธารณะ(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.evidence = wcb_source.normalize(cls.payload)
        cls.rendered = {writer["id"]: writer["render"](cls.evidence)
                        for writer in wcb_writers.WCB_WRITERS}


class ทะเบียนนักเขียน(ฐานสายสาธารณะ):
    def test_มีสามสไตล์และรหัสไม่ซ้ำกัน(self):
        self.assertEqual(len(wcb_writers.WCB_WRITERS), 3)
        ids = [writer["id"] for writer in wcb_writers.WCB_WRITERS]
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(set(ids), {"a_standard", "b_technical", "c_event"})

    def test_by_id_หาเจอและโยนเมื่อไม่รู้จัก(self):
        self.assertEqual(wcb_writers.by_id("b_technical")["style"], "B — เทคนิคเจาะลึก")
        with self.assertRaises(KeyError):
            wcb_writers.by_id("ไม่มีสไตล์นี้")

    def test_สามสไตล์ให้ข้อความไม่ซ้ำกันเลย(self):
        texts = list(self.rendered.values())
        self.assertEqual(len(set(texts)), 3)


class สัญญาส่งออกของเว็บ(ฐานสายสาธารณะ):
    def test_frontmatter_ครบตามสัญญานำเข้า(self):
        for style, article in self.rendered.items():
            with self.subTest(style=style):
                fields, _ = split_frontmatter(article)
                for key in ("asset", "title", "excerpt", "author_slug", "trend"):
                    self.assertTrue(fields.get(key), f"{style} ขาด {key}")
                self.assertLessEqual(len(fields["title"]), 90)
                self.assertGreaterEqual(len(fields["excerpt"]), 120)
                self.assertLessEqual(len(fields["excerpt"]), 160)

    def test_trend_ต้องเป็นรหัสสามค่าเท่านั้น(self):
        # ระบบนำเข้าของเว็บปฏิเสธค่าอื่นทุกค่า รวมทั้งคำไทยที่อ่านรู้เรื่องกว่า
        for style, article in self.rendered.items():
            with self.subTest(style=style):
                fields, _ = split_frontmatter(article)
                self.assertIn(fields["trend"], ("up", "dn", "fl"))

    def test_มีหัวข้อบังคับครบสามหัว(self):
        for style, article in self.rendered.items():
            with self.subTest(style=style):
                for pattern in (r"##\s*เทคนิค", r"##\s*ปัจจัย", r"##\s*กลยุทธ"):
                    self.assertRegex(article, pattern)

    def test_ห้ามหัวข้อ_h1_ห้าม_bullet_ห้ามตาราง(self):
        for style, article in self.rendered.items():
            with self.subTest(style=style):
                _, body = split_frontmatter(article)
                for line in body.splitlines():
                    self.assertFalse(line.startswith("# "), f"{style} มีหัวข้อ H1")
                    self.assertIsNone(re.match(r"^\s*[-*]\s", line), f"{style} มี bullet")
                    # หมุดกราฟใช้ | คั่นพารามิเตอร์ตามสัญญาของเว็บ ลอกออกก่อนตรวจหาตาราง
                    self.assertNotIn("|", re.sub(r"\[\[chart:[^\]]*\]\]", "", line),
                                     f"{style} มีตาราง")

    def test_ไม่มีเครื่องหมายค้างและยาวพอตามสัญญา(self):
        for style, article in self.rendered.items():
            with self.subTest(style=style):
                self.assertNotIn("<<", article)
                self.assertNotIn(">>", article)
                thai = len(re.findall(r"[฀-๿]", article))
                self.assertGreaterEqual(round(thai / 3.5), 600,
                                        f"{style} สั้นกว่าเพดานขั้นต่ำของสัญญา")

    def test_ทุกสไตล์ยาวถึงเกณฑ์ของสไตล์ตัวเอง(self):
        """ด่านตรวจบังคับขั้นต่ำร่วมที่ 600 คำ แต่สเปกกำหนดของแต่ละสไตล์ไว้สูงกว่านั้น

        สองเลขไม่ตรงกันมาตลอด ⇒ สไตล์ B ออกมา 820 คำ ทั้งที่สเปกเขียนว่า 900–1,600
        แล้วผ่านด่านได้สบาย ไม่มีอะไรฟ้อง (พบ 2026-08-05)
        """
        for writer in wcb_writers.WCB_WRITERS:
            with self.subTest(style=writer["id"]):
                article = self.rendered[writer["id"]]
                words = round(len(re.findall(r"[฀-๿]", article)) / 3.5)
                self.assertGreaterEqual(
                    words, writer["min_words"],
                    f"{writer['style']} ได้ {words} คำ ต่ำกว่าเกณฑ์ {writer['min_words']} ของสเปก")


class ภาษาที่คนอ่านเข้าใจ(ฐานสายสาธารณะ):
    """ด่านกันศัพท์ระบบหลุดขึ้นหน้าเว็บ

    บทชุด 2026-08-05 ขึ้นจริงด้วยข้อความว่า "สัญญาณรายวันรวมเป็น strong_buy" และ
    "ให้สัญญาณneutral" (ไม่มีเว้นวรรค เพราะรหัสถูกต่อท้ายคำไทยตรง ๆ) ทั้งห้าหัวข้อ
    ผ่านด่านตัวเลขได้สบายเพราะรหัสไม่ใช่ตัวเลข ⇒ ต้องมีด่านของตัวเอง
    """

    def _body_only(self, article: str) -> str:
        """ตัดหัวไฟล์และหมุดกราฟออก — สองส่วนนั้นเป็นสัญญากับเว็บ ต้องเป็นรหัสอังกฤษ"""
        _, body = split_frontmatter(article)
        return re.sub(r"\[\[chart:[^\]]*\]\]", "", body)

    def test_ไม่มีรหัสคำตัดสินดิบในเนื้อบท(self):
        for style, article in self.rendered.items():
            with self.subTest(style=style):
                body = self._body_only(article)
                for code in ("strong_buy", "strong_sell"):
                    self.assertNotIn(code, body, f"{style} มีรหัส {code} ในเนื้อบท")
                # คำว่า buy/sell/neutral ปรากฏในพาดหัวข่าวอังกฤษได้ตามปกติ
                # จึงจับเฉพาะรูปที่เป็นการรายงานค่าของระบบ ไม่ใช่แบนคำลอย ๆ ทั้งบท
                self.assertIsNone(
                    re.search(r"(?:อยู่ที่|รวมเป็น|สัญญาณ)\s*(?:buy|sell|neutral)\b", body),
                    f"{style} รายงานค่าสัญญาณเป็นรหัสดิบ")

    def test_ไม่มีรหัสต่อท้ายคำไทยแบบไม่เว้นวรรค(self):
        for style, article in self.rendered.items():
            with self.subTest(style=style):
                self.assertIsNone(re.search(r"สัญญาณ[A-Za-z]", self._body_only(article)),
                                  f"{style} มีรหัสอังกฤษติดกับคำว่า สัญญาณ")

    def test_ชื่อกรอบเวลาในเนื้อบทเป็นภาษาไทย(self):
        for style, article in self.rendered.items():
            with self.subTest(style=style):
                body = self._body_only(article)
                for code in wcb_writers.TF_ORDER:
                    self.assertNotIn(code, body, f"{style} พิมพ์ชื่อกรอบเวลาเป็นรหัส {code}")

    def test_รหัสที่ไม่รู้จักต้องโยน_ไม่ใช่เขียนค่าดิบลงบท(self):
        """ปลายทางเพิ่มรหัสใหม่ = ต้องดัง ไม่ใช่ปล่อยผ่านเงียบ ๆ"""
        for bad in ("mega_buy", "STRONG_BUY", "hold", 1):
            with self.subTest(code=bad):
                with self.assertRaises(ValueError):
                    wcb_writers.verdict_thai(bad)
                with self.assertRaises(ValueError):
                    wcb_writers.signal_thai(bad)

    def test_รหัสใหม่จากปลายทางทำให้บททั้งใบหยุด(self):
        payload = json.loads(json.dumps(self.payload))
        payload["technicals"]["summary"] = "mega_buy"
        broken = wcb_source.normalize(payload)
        for writer in wcb_writers.WCB_WRITERS:
            with self.subTest(style=writer["id"]):
                with self.assertRaises(ValueError):
                    writer["render"](broken)

    def test_ปลายทางไม่ส่งคำตัดสินมา_บทยังต้องได้คำโปรยตามสัญญา(self):
        """ค่าว่างคือ evidence ไม่พอ ⇒ ตัดวลีทิ้งเงียบ แต่ห้ามทำให้คำโปรยสั้นกว่าเกณฑ์"""
        payload = json.loads(json.dumps(self.payload))
        payload["technicals"]["summary"] = None
        thin = wcb_source.normalize(payload)
        for writer in wcb_writers.WCB_WRITERS:
            with self.subTest(style=writer["id"]):
                fields, _ = split_frontmatter(writer["render"](thin))
                self.assertGreaterEqual(len(fields["excerpt"]), 120)
                self.assertLessEqual(len(fields["excerpt"]), 160)
                self.assertNotIn("None", fields["excerpt"])


class ย่อหน้าข่าวพูดกับคนอ่าน(ฐานสายสาธารณะ):
    """ห้ามเล่ากลไกหลังบ้าน แต่ยังต้องบอกตามจริงว่าไม่มีข่าวใหม่

    ฉบับ 2026-08-05 เขียนว่า "ฟีดข่าวที่ระบบดึงมาพร้อมชุดราคามีอยู่รายการเดียว" แล้วยก
    พาดหัวข่าวอายุสิบสามวันขึ้นบทต่อทันที ⇒ คนอ่านผูกข่าวเก่ากับราคาวันนี้เข้าหากันเอง
    """

    # เจาะจงที่ถ้อยคำอธิบายกลไกของเราเท่านั้น — คำว่า API ปรากฏใน**ชื่อรายการปฏิทินจริง**
    # ("ปริมาณน้ำมันดิบคงคลัง (API)") จึงห้ามแบนลอย ๆ ไม่งั้นด่านนี้จะตกเพราะข้อมูลถูกต้อง
    JARGON = ("ฟีดข่าว", "ที่ระบบดึงมา", "พร้อมชุดราคา", "snapshot", "evidence")

    def test_ไม่มีศัพท์กลไกหลังบ้านในบท(self):
        for style, article in self.rendered.items():
            with self.subTest(style=style):
                _, body = split_frontmatter(article)
                for word in self.JARGON:
                    self.assertNotIn(word, body, f"{style} เล่ากลไกหลังบ้านด้วยคำว่า {word}")

    def test_ข่าวเก่าเกินวันข้อมูล_ต้องไม่ยกพาดหัวขึ้นบท(self):
        stale_title = "หัวข่าวเก่าที่ต้องไม่ขึ้นบท"
        payload = json.loads(json.dumps(self.payload))
        payload["news"] = [{"title": stale_title, "published_at": "2020-01-01",
                            "source": "ทดสอบ", "url": "https://example.invalid/x"}]
        old = wcb_source.normalize(payload)
        for writer in wcb_writers.WCB_WRITERS:
            with self.subTest(style=writer["id"]):
                article = writer["render"](old)
                self.assertNotIn(stale_title, article, "พาดหัวข่าวเก่าหลุดขึ้นบท")
                self.assertIn("เก่าเกินกว่าจะใช้อธิบายการเคลื่อนไหวของวันนี้ได้", article)
                thai = len(re.findall(r"[฀-๿]", article))
                self.assertGreaterEqual(round(thai / 3.5), writer["min_words"],
                                        "รอบข่าวเก่าทำให้บทสั้นกว่าเกณฑ์ของสไตล์")


class ไม่ซ้ำย่อหน้าข้ามสไตล์(ฐานสายสาธารณะ):
    def test_บท_b_ไม่ใช้ย่อหน้าไล่ระดับชุดเดียวกับ_a_และ_c(self):
        """คนที่อ่านสองสไตล์ของหัวข้อเดียวกันต้องไม่เจอย่อหน้าซ้ำคำต่อคำ

        `_levels_paragraph` เคยถูกเรียกทั้งสามสไตล์ ⇒ ย่อหน้ายาวย่อหน้าหนึ่งซ้ำเป๊ะ
        สามที่ และในบท B มันยังซ้ำกับย่อหน้าเงื่อนไขที่ตามมาติดกันด้วย (2026-08-05)
        """
        shared = wcb_writers._levels_paragraph(self.evidence)
        self.assertTrue(shared, "fixture นี้ไม่มีระดับราคา เทสนี้จะไม่ได้ตรวจอะไรเลย")
        self.assertNotIn(shared, self.rendered["b_technical"])

    def test_ไม่มีย่อหน้าใดซ้ำกันสองที่ในบทเดียว(self):
        for style, article in self.rendered.items():
            with self.subTest(style=style):
                _, body = split_frontmatter(article)
                paragraphs = [line.strip() for line in body.splitlines()
                              if len(line.strip()) > 80 and not line.startswith("[[chart:")]
                repeated = {p for p in paragraphs if paragraphs.count(p) > 1}
                self.assertFalse(repeated, f"{style} มีย่อหน้าซ้ำ: {repeated}")

    def test_เลขแนวรับด่านแรกไม่ถูกพิมพ์ซ้ำในสองย่อหน้าติดกัน(self):
        below, _ = wcb_writers._sorted_levels(self.evidence)
        self.assertTrue(below, "fixture นี้ไม่มีแนวรับ เทสนี้จะไม่ได้ตรวจอะไรเลย")
        first = wcb_writers.price(below[0], self.evidence)
        _, body = split_frontmatter(self.rendered["b_technical"])
        blocks = [b for b in body.split("\n\n") if first in b and "[[chart:" not in b]
        self.assertLessEqual(len(blocks), 1,
                             f"บท B พิมพ์แนวรับ {first} ซ้ำใน {len(blocks)} ย่อหน้า")


class ระดับราคาต้องไม่ปนกรอบเวลา(ฐานสายสาธารณะ):
    """ด่านของบั๊กที่ผู้ใช้อนุมัติให้แก้ 2026-08-06

    ของเดิมเทจุดหมุนทั้งสี่กรอบรวมกองเดียวแล้วเรียงตามระยะห่างจากราคา ⇒ จุดหมุน
    กรอบ 30 นาทีชนะทุกครั้ง บททองของ 2026-08-05 จึงได้หกด่านที่กินช่วงรวม 0.53%
    ขณะที่ราคาแกว่งจริงวันนั้น 3.48% (ห่างกัน 43 เท่า) ⇒ ใช้วางแผนวันไม่ได้
    """

    def _frames(self, evidence):
        return wcb_writers._levels_by_frame(evidence)

    def test_ด่านฝั่งเดียวกันต้องมาจากกรอบเวลาเดียวกันทั้งชุด(self):
        below, above, source = self._frames(self.evidence)
        for values, side in ((below, "below"), (above, "above")):
            if not values:
                continue
            frame = source[side]
            pool = {round(v, wcb_writers.profile_of(self.evidence)["decimals"])
                    for v in wcb_writers._pivot_group(self.evidence, frame)}
            for value in values:
                self.assertIn(value, pool,
                              f"ฝั่ง {side} มีค่า {value} ที่ไม่ใช่จุดหมุนของกรอบ {frame}")

    def test_เลือกกรอบรายวันก่อนเสมอเมื่อฝั่งนั้นยังมีจุดหมุนเหลือ(self):
        spot = float(self.evidence["quote"]["price"])
        daily = wcb_writers._pivot_group(self.evidence, "1day")
        _, _, source = self._frames(self.evidence)
        if any(v < spot for v in daily):
            self.assertEqual(source.get("below"), "1day")
        if any(v >= spot for v in daily):
            self.assertEqual(source.get("above"), "1day")

    def test_ฝั่งที่รายวันไม่เหลือด่าน_ต้องถอยลงกรอบถัดไป_ไม่ใช่ปล่อยว่าง(self):
        """วันที่ราคาวิ่งแรงจะทะลุจุดหมุนรายวันฝั่งบนหมดทุกชั้น

        เกิดจริงกับทองและ NVDA เมื่อ 2026-08-05 ⇒ ถ้าบังคับรายวันล้วน บทจะไม่มี
        หัวข้อฝั่งบนเลย ซึ่งเป็นวันที่คนอ่านต้องการด่านฝั่งบนมากที่สุด
        """
        # จำลองสภาพจริง: ราคาผ่านจุดหมุน**รายวัน**ฝั่งบนหมดทุกชั้น แต่จุดหมุนกรอบเล็ก
        # ยังอยู่เหนือราคาได้ เพราะคำนวณจากแท่งที่ใหม่กว่า ⇒ ตัดเฉพาะชั้นรายวันที่อยู่เหนือ
        # ราคาออก ไม่ใช่ดันราคาให้พ้นทุกกรอบ (ซึ่งจะไม่ใช่สภาพที่เกิดขึ้นจริง)
        payload = json.loads(json.dumps(self.payload))
        spot = float(payload["quote"]["price"])
        daily = payload["technicals"]["pivots"]
        for key in wcb_source.PIVOT_KEYS:
            if daily.get(key) is not None and float(daily[key]) >= spot:
                daily[key] = None
        broken_out = wcb_source.normalize(payload)

        self.assertEqual([], [v for v in wcb_writers._pivot_group(broken_out, "1day")
                              if v >= float(broken_out["quote"]["price"])],
                         "ชุดทดสอบไม่ได้อยู่ในสภาพที่ต้องการ — รายวันยังมีด่านฝั่งบนเหลือ")

        below, above, source = self._frames(broken_out)
        self.assertEqual(source.get("below"), "1day", "ฝั่งล่างต้องยังใช้รายวันตามเดิม")
        self.assertTrue(above, "ฝั่งบนว่างเปล่า — ไม่ได้ถอยลงกรอบถัดไป")
        self.assertNotEqual(source.get("above"), "1day")
        self.assertIn(source.get("above"), wcb_writers.TF_ORDER)

    def test_ย่อหน้าไล่ระดับต้องกำกับกรอบเวลาของทุกฝั่ง(self):
        below, above, source = self._frames(self.evidence)
        text = wcb_writers._levels_paragraph(self.evidence)
        self.assertTrue(text, "fixture นี้ไม่มีระดับราคา เทสนี้จะไม่ได้ตรวจอะไรเลย")
        for values, side in ((below, "below"), (above, "above")):
            if values:
                self.assertIn(wcb_writers.TF_THAI[source[side]], text,
                              f"ย่อหน้าไม่บอกว่าด่านฝั่ง {side} มาจากกรอบไหน")

    def test_บททุกสไตล์ที่พิมพ์ระดับ_ต้องมีคำกำกับกรอบเวลา(self):
        for style, article in self.rendered.items():
            with self.subTest(style=style):
                if "ด่านแรกฝั่ง" not in article:
                    continue
                self.assertIn("จุดหมุนกรอบ", article,
                              f"{style} พิมพ์ระดับราคาโดยไม่บอกกรอบเวลา")

    def test_หมุดกราฟใช้ระดับชุดเดียวกับที่บทพูดถึง(self):
        """เส้นบนกราฟกับตัวเลขในบทต้องมาจากแหล่งเดียว ไม่ใช่คนละชุดที่ดูคล้ายกัน"""
        below, above = wcb_writers._sorted_levels(self.evidence)
        marker = wcb_writers.chart_marker(self.evidence, "1day")
        for raw in re.findall(r"[sr]=([\d,.]+)", marker):
            for token in raw.split(","):
                value = float(token)
                self.assertTrue(any(abs(v - value) <= 1 for v in below + above),
                                f"หมุดกราฟอ้างเส้น {token} ที่ไม่อยู่ในชุดที่บทพูดถึง")


class หมุดกราฟ(ฐานสายสาธารณะ):
    def test_ใช้กรอบเวลาที่เว็บรองรับเท่านั้น(self):
        for style, article in self.rendered.items():
            with self.subTest(style=style):
                markers = re.findall(r"\[\[chart:([^\]\|]+)", article)
                self.assertTrue(markers, f"{style} ไม่มีหมุดกราฟ")
                for timeframe in markers:
                    self.assertIn(timeframe, ALLOWED_TF)

    def test_เลขเส้นต้องเป็นค่า_pivot_จริง(self):
        pivots = wcb_source.pivot_values(self.evidence)
        for style, article in self.rendered.items():
            with self.subTest(style=style):
                for group in re.findall(r"\[\[chart:[^\]\|]+((?:\|[^\]]*)?)\]\]", article):
                    for raw in re.findall(r"[sr]=([\d,]+)", group):
                        for token in raw.split(","):
                            value = float(token)
                            self.assertTrue(any(abs(p - value) <= 1 for p in pivots),
                                            f"{style} อ้างเส้น {token} ที่ไม่ใช่ pivot")


class ตัวเลขต้องมีต้นทาง(ฐานสายสาธารณะ):
    def test_เลขทุกตัวในบทความชี้กลับ_snapshot_ได้(self):
        """กฎแกนของสายนี้ — เลขที่คิดเองต้องตกด่านนี้เสมอ

        ยอมให้ปัดได้สองระดับตามที่บทความเขียนให้คนอ่าน: ทศนิยมสั้นลง และราคาปัดเป็น
        จำนวนเต็ม (ระยะ 1 ดอลลาร์ กติกาเดียวกับเส้นในหมุดกราฟ)
        """
        pool = evidence_numbers(self.payload)
        for style, article in self.rendered.items():
            with self.subTest(style=style):
                _, body = split_frontmatter(article)
                for line in body.splitlines():
                    for match in NUMBER.finditer(strip_structural(line)):
                        token = match.group(0)
                        value = abs(float(token.replace(",", "")))
                        ok = (any(abs(item - value) < 0.005 for item in pool)
                              or any(abs(item - value) <= 0.05 for item in pool)
                              or ("." not in token and value >= 100
                                  and any(abs(item - value) < 1.0 for item in pool)))
                        self.assertTrue(ok, f"{style} มีเลข {token} ที่ไม่มีต้นทางใน snapshot")

    def test_ไม่มีการแปลงหน่วยของค่าในปฏิทิน(self):
        # ปฏิทินส่ง "98" มา บทความต้องไม่เขียน 98,000 (ความผิดพลาดจริงเมื่อ 2026-08-05)
        previous = {str(event["previous"]) for event in self.evidence["calendar"]
                    if event["previous"] not in (None, "")}
        for style, article in self.rendered.items():
            with self.subTest(style=style):
                for value in previous:
                    digits = re.sub(r"[^\d]", "", value)
                    if digits and len(digits) <= 3:
                        self.assertNotIn(f"{digits},000", article)


class ก้อนข้อมูลที่ใช้ไม่ได้(ฐานสายสาธารณะ):
    def test_ok_false_ต้องหยุด_ไม่ใช่เขียนต่อ(self):
        with self.assertRaises(wcb_source.SnapshotUnusable):
            wcb_source.normalize({**self.payload, "ok": False})

    def test_ไม่มีราคาต้องหยุด(self):
        broken = {**self.payload, "quote": {**self.payload["quote"], "price": None}}
        with self.assertRaises(wcb_source.SnapshotUnusable):
            wcb_source.normalize(broken)

    def test_ฟีดข่าวว่างยังต้องเขียนบทความได้เต็มความยาว(self):
        """โจทย์ผู้ใช้: ถ้าไม่มีข่าวก็ต้องเขียนบทวิเคราะห์ได้"""
        empty = wcb_source.normalize({**self.payload, "news": []})
        for writer in wcb_writers.WCB_WRITERS:
            with self.subTest(style=writer["id"]):
                article = writer["render"](empty)
                thai = len(re.findall(r"[฀-๿]", article))
                self.assertGreaterEqual(round(thai / 3.5), 600)
                self.assertIn("ไม่มีตัวจุดชนวนที่ระบุชื่อได้", article)

    def test_ข้อความไทยที่บันทึกผิด_encoding_ถูกซ่อมตอนอ่าน(self):
        titles = [event["title"] for event in self.evidence["calendar"]]
        self.assertTrue(any("ปฏิทิน" in t or "การจ้างงาน" in t or "อัตรา" in t for t in titles),
                        "ชื่อรายการในปฏิทินยังอ่านไม่ออก — _mend ไม่ทำงาน")


class การเข้าถึงรหัสและความสด(ฐานสายสาธารณะ):
    """ด่านของ adapter ดึงสด — ทุกตัวในคลาสนี้ทำงานโดยไม่แตะเครือข่าย"""

    def setUp(self):
        self._saved = {key: os.environ.pop(key, None)
                       for key in (wcb_source.KEY_ENV, wcb_source.KEY_FILE_ENV)}

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_ไม่มีรหัสต้องโยน_ไม่ใช่ยิงเปล่า(self):
        with self.assertRaises(wcb_source.KeyMissing):
            wcb_source._resolve_key()

    def test_ลำดับการหารหัส_อาร์กิวเมนต์ก่อน_แล้วค่อย_env(self):
        os.environ[wcb_source.KEY_ENV] = "จาก-env"
        self.assertEqual(wcb_source._resolve_key("ส่งตรง"), "ส่งตรง")
        self.assertEqual(wcb_source._resolve_key(), "จาก-env")

    def test_อ่านรหัสจากไฟล์ในเครื่องได้และตัดช่องว่างท้าย(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "key.txt"
            path.write_text("รหัสในไฟล์\n", encoding="utf-8")
            os.environ[wcb_source.KEY_FILE_ENV] = str(path)
            self.assertEqual(wcb_source._resolve_key(), "รหัสในไฟล์")

    def test_ไม่มีรหัสฝังอยู่ในซอร์สของรีโป(self):
        """กันการเผลอใส่ค่าตั้งต้น — รหัสที่ commit ไปแล้วลบทีหลังไม่ได้"""
        # หน้าตาของรหัสจริง: ยาว มีทั้งพิมพ์ใหญ่ พิมพ์เล็ก และตัวเลขคละกัน
        # ชื่อตัวแปรสภาพแวดล้อมเป็นพิมพ์ใหญ่ล้วนจึงไม่เข้าเงื่อนไขนี้
        looks_like_secret = re.compile(r"[\"']([A-Za-z0-9_\-]{24,})[\"']")
        for path in sorted((_REPO_ROOT / "tools").glob("wcb_*.py")):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("&k=", source.replace('f"{base_url}?asset={asset}&k={secret}"', ""),
                             f"{path.name} มี URL ที่ประกอบรหัสไว้ตายตัว")
            for literal in looks_like_secret.findall(source):
                mixed = (any(c.islower() for c in literal) and any(c.isupper() for c in literal)
                         and any(c.isdigit() for c in literal))
                self.assertFalse(mixed, f"{path.name} มีค่าที่หน้าตาเหมือนรหัสฝังอยู่: {literal[:6]}…")

    def test_รหัสต้องถูกลบออกจากข้อความ_error(self):
        # urllib ใส่ URL เต็มลงใน error เอง ถ้าไม่กรอง รหัสจะโผล่ใน traceback
        message = "HTTP Error 500: https://example/api?asset=xauusd&k=ลับมาก"
        self.assertNotIn("ลับมาก", wcb_source.redact(message, "ลับมาก"))
        self.assertIn("***", wcb_source.redact(message, "ลับมาก"))

    def test_ก้อนเก่าเกินเพดานต้องถูกตีตก(self):
        old = datetime.now(timezone.utc) - timedelta(hours=6)
        evidence = wcb_source.normalize(
            {**self.payload, "generatedAt": old.isoformat().replace("+00:00", "Z")})
        self.assertGreater(wcb_source.age_minutes(evidence), wcb_source.MAX_AGE_MINUTES)
        with self.assertRaises(wcb_source.SnapshotStale):
            wcb_source.ensure_fresh(evidence)

    def test_ก้อนที่เก็บไว้ต้องเอากลับมาแปลงซ้ำได้(self):
        """`--save-snapshot` ต้องเก็บก้อนดิบ ไม่ใช่ก้อนที่แปลงแล้ว (บั๊กจริง 2026-08-05)

        ถ้าเก็บก้อนที่แปลงแล้ว จะรันซ้ำไม่ได้และด่านตรวจบทความก็หา pivot ไม่เจอ
        """
        again = wcb_source.normalize(json.loads(json.dumps(self.payload)))
        self.assertEqual(again["quote"]["price"], self.evidence["quote"]["price"])
        with self.assertRaises(wcb_source.SnapshotUnusable):
            wcb_source.normalize(json.loads(json.dumps(self.evidence)))

    def test_คำขอต้องมี_user_agent(self):
        """ไม่มี User-Agent = Cloudflare ตอบ 403 (วัดจริง 2026-08-05) — กันการถอดออก"""
        request = wcb_source.build_request("https://example/api")
        agent = request.get_header("User-agent") or ""
        self.assertTrue(agent, "คำขอไม่มี User-Agent")
        self.assertNotIn("Python-urllib", agent)

    def test_ก้อนสดต้องผ่าน(self):
        now = datetime.now(timezone.utc)
        evidence = wcb_source.normalize(
            {**self.payload, "generatedAt": now.isoformat().replace("+00:00", "Z")})
        self.assertLess(wcb_source.age_minutes(evidence), 1)


class สายท่อสายสาธารณะ(ฐานสายสาธารณะ):
    """`build_daily_package --line public` — ด่านสิทธิ์ข้อมูลต้องกั้นได้จริง"""

    def test_วางลงคลังในเครื่องได้แต่ต้องติดป้ายว่ายังไม่มีสิทธิ์เผยแพร่(self):
        """`output/` คือคลังในเครื่อง ไม่ใช่การเผยแพร่ — README ของโฟลเดอร์นั้นระบุชัด
        ว่า "ไม่ใช่ของที่ส่งมอบ" และ "ห้าม push ขึ้นที่เก็บออนไลน์ใด ๆ"

        เดิมเทสนี้ล็อกไว้ว่าห้ามมีไฟล์เลยเมื่อสิทธิ์ยังไม่ชัด **แต่ค่าคงที่นั้นไม่เคยเป็นจริง
        ในระบบ** — บทของสายภายใน ①②③ นั่งอยู่ใน `output/` มาตลอดด้วยสถานะ
        `approved-internal-only` เท่ากันเป๊ะ ⇒ สองสายใช้เกณฑ์คนละชุดกับโฟลเดอร์เดียวกัน

        อันตรายจริงไม่ใช่การมีไฟล์อยู่ในคลัง แต่คือ README เขียนว่า "หยิบไปอัปได้เลย"
        โดยไม่บอกว่านั่นจริงเฉพาะด่านเนื้อหา ⇒ เกณฑ์ที่ถูกคือ **วางได้ แต่ต้องติดป้าย**
        """
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            snapshot = root / "snap.json"
            snapshot.write_text(json.dumps(self.payload, ensure_ascii=False), encoding="utf-8")
            result = build_daily_package.build_public(
                "xauusd", batch_id="t", output_root=root / "work",
                publish_root=root / "out", snapshot_path=snapshot,
                cutoff_at="2026-08-05T11:34:00+00:00", max_age_minutes=10 ** 9)

            self.assertTrue(result["content_ok"], "ร่างต้องผ่านด่านบทความครบทุกสไตล์")
            self.assertEqual(len(result["drafts"]), 3)
            drafts = root / "work" / "t" / "xauusd" / "internal" / "public-line" / "drafts"
            self.assertEqual(len(list(drafts.glob("*.md"))), 3, "ร่างต้องถูกเก็บไว้ให้ตรวจได้")

            self.assertIsNotNone(result["published"], "บทที่ผ่านด่านเนื้อหาต้องถึงคลังในเครื่อง")
            self.assertEqual(len(list((root / "out").rglob("*.md"))) - 1, 3,
                             "ต้องมีบทครบสามสไตล์ (ไม่นับป้ายสถานะสิทธิ์)")

            # ป้ายต้องมีเสมอและต้องตรงกับคำตัดสินของด่าน ไม่ว่าคำตัดสินจะเป็นค่าไหน
            notice = Path(result["published"]["clearance_notice"])
            self.assertTrue(notice.is_file(), "ไม่มีป้ายบอกสถานะสิทธิ์ในโฟลเดอร์วัน")
            text = notice.read_text(encoding="utf-8")
            self.assertIn(result["clearance"], text, "ป้ายไม่ได้บอกสถานะจริงของรอบนี้")
            self.assertEqual(
                result["published"]["cleared_for_publication"],
                result["clearance"] == license_gate.APPROVED_PUBLIC)
            for reason in result["license_reasons"]:
                self.assertIn(reason, text, "ป้ายต้องบอกด้วยว่าติดตรงไหน")

    def test_ป้ายเมื่อยังไม่มีสิทธิ์ต้องห้ามชัดเจนและบอกเหตุผล(self):
        with tempfile.TemporaryDirectory() as folder:
            notice = publish_layout.write_clearance_notice(
                Path(folder), "2026-08-05T11:34:00+00:00",
                clearance=license_gate.APPROVED_INTERNAL,
                reasons=["ทดสอบ: ยังไม่รู้เจ้าของข้อมูล"])
            text = notice.read_text(encoding="utf-8")
            self.assertIn("ยังนำขึ้นเว็บหรือโซเชียลไม่ได้", text)
            self.assertIn("ทดสอบ: ยังไม่รู้เจ้าของข้อมูล", text)

    def test_ป้ายเมื่อเผยแพร่ได้ต้องบอกฐานของการอนุมัติด้วย(self):
        """ป้ายที่เขียนแค่ "เผยแพร่ได้" ลอย ๆ ปกปิดเรื่องสำคัญ

        ทะเบียนตอนนี้ถูกปลดด้วย**การอนุมัติของเจ้าของงาน** ไม่ใช่ผลการตรวจสัญญา
        คนที่หยิบไฟล์ไปโพสต์ควรรู้ความต่างข้อนี้ เพราะถ้าคำตอบ E1 กลับมาไม่ดี
        ของที่โพสต์ไปแล้วต้องถอนกลับ
        """
        with tempfile.TemporaryDirectory() as folder:
            notice = publish_layout.write_clearance_notice(
                Path(folder), "2026-08-05T11:34:00+00:00",
                clearance=license_gate.APPROVED_PUBLIC, reasons=[])
            text = notice.read_text(encoding="utf-8")
            self.assertIn("เผยแพร่ได้", text)
            self.assertNotIn("ยังนำขึ้นเว็บหรือโซเชียลไม่ได้", text)
            unreviewed = [name for name, entry in publish_layout._provider_entries().items()
                          if entry.get("contract_reviewed") is False]
            for name in unreviewed:
                self.assertIn(name, text,
                              f"{name} ปลดโดยไม่ได้ตรวจสัญญา แต่ป้ายไม่ได้บอก")
                self.assertIn("ไม่ใช่ผลการตรวจสัญญาต้นทาง", text)

    def test_ก้อนดิบที่เก็บไว้ต้องเป็นก้อนดิบจริง(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            snapshot = root / "snap.json"
            snapshot.write_text(json.dumps(self.payload, ensure_ascii=False), encoding="utf-8")
            build_daily_package.build_public(
                "xauusd", batch_id="t", output_root=root / "work",
                publish_root=None, snapshot_path=snapshot,
                cutoff_at="2026-08-05T11:34:00+00:00", max_age_minutes=10 ** 9)
            saved = json.loads((root / "work" / "t" / "xauusd" / "internal" / "public-line"
                                / "raw.snapshot.json").read_text(encoding="utf-8"))
            self.assertIn("technicalsByTf", saved, "ก้อนที่เก็บไม่ใช่ก้อนดิบ")
            wcb_source.normalize(saved)  # ต้องแปลงซ้ำได้โดยไม่โยน

    def test_เมื่อสิทธิ์อนุมัติแล้วไฟล์ต้องลงโฟลเดอร์เผยแพร่ครบสามสไตล์(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"
            published = publish_layout.publish_wcb_asset(
                asset="xauusd", evidence=self.evidence, snapshot=self.payload,
                publish_root=out, cutoff_at="2026-08-05T11:34:00+00:00")
            self.assertEqual(len(published["writers"]), 3)
            for entry in published["writers"]:
                self.assertEqual(entry["status"], "pass")
                self.assertTrue(Path(entry["article"]).is_file())
            # สายนี้ไม่มีไฟล์กราฟ เพราะเว็บวาดเองจากหมุดในบทความ
            self.assertFalse(list(out.rglob("*.png")))

    def test_สไตล์ที่ตกด่านต้องลบไฟล์รอบก่อนของวันเดียวกันทิ้ง(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"
            cutoff = "2026-08-05T11:34:00+00:00"
            publish_layout.publish_wcb_asset(
                asset="xauusd", evidence=self.evidence, snapshot=self.payload,
                publish_root=out, cutoff_at=cutoff)
            stale = Path(publish_layout.publish_wcb_asset(
                asset="xauusd", evidence=self.evidence, snapshot=self.payload,
                publish_root=out, cutoff_at=cutoff)["writers"][0]["article"])
            self.assertTrue(stale.is_file())
            # รอบถัดมาตกด่านเพราะกองหลักฐานว่าง ⇒ ไฟล์รอบก่อนต้องหายไป ไม่ใช่ค้างดูเหมือนของสด
            empty = {"ok": True, "quote": {"price": 1.0}, "generatedAt": "2026-08-05T04:34:07Z"}
            again = publish_layout.publish_wcb_asset(
                asset="xauusd", evidence=self.evidence, snapshot=empty,
                publish_root=out, cutoff_at=cutoff)
            self.assertTrue(all(entry["status"] == "fail" for entry in again["writers"]))
            self.assertFalse(stale.exists(), "ไฟล์ที่ตกด่านรอบนี้ยังค้างจากรอบก่อน")


class บทต้องพูดถึงสินทรัพย์ของตัวเอง(unittest.TestCase):
    """บั๊กจริง 2026-08-05 — สายนี้ถูกเขียนและทดสอบกับทองอย่างเดียว

    ชื่อสินทรัพย์ หน่วย และสายส่งมหภาคถูกฝังเป็นค่าคงที่ ⇒ พอเอาไปรันกับ EUR/USD
    บทที่ได้พาดหัวว่า "ทองคำโลก (XAU/USD) ยืนที่ 1.15" บอกราคา "ดอลลาร์ต่อออนซ์"
    และปิดท้ายว่า "ทองได้ประโยชน์" ทั้งฉบับ

    **ด่านตรวจบทความจับไม่ได้เลย** เพราะมันตรวจว่าเลขมีต้นทางไหม ไม่ได้ตรวจว่า
    บทพูดถึงตัวไหน ⇒ ด่านนั้นทดแทนเทสชุดนี้ไม่ได้
    """

    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(
            (_REPO_ROOT / "tests" / "fixtures" / "wcb-snapshot-eurusd.json")
            .read_text(encoding="utf-8"))
        cls.evidence = wcb_source.normalize(cls.payload)
        cls.rendered = {writer["id"]: writer["render"](cls.evidence)
                        for writer in wcb_writers.WCB_WRITERS}

    def test_ห้ามมีคำของสินทรัพย์อื่นหลุดเข้าบท(self):
        for style, article in self.rendered.items():
            with self.subTest(style=style):
                for word in ("ทองคำ", "XAU", "ต่อออนซ์", "ถือทอง"):
                    self.assertNotIn(word, article,
                                     f"{style} พูดถึง {word} ทั้งที่เป็นบท EUR/USD")

    def test_พาดหัวกับหน่วยต้องเป็นของสินทรัพย์จริง(self):
        for style, article in self.rendered.items():
            with self.subTest(style=style):
                fields, _ = split_frontmatter(article)
                self.assertIn("EUR/USD", fields["title"])
                self.assertEqual(fields["asset"], "eurusd")
        self.assertIn("ดอลลาร์ต่อยูโร", self.rendered["a_standard"])

    def test_ราคาต้องไม่ถูกปัดจนสูงสุดกับต่ำสุดเท่ากัน(self):
        """`:,.2f` ตายตัวทำให้ราคาเปิด/สูงสุด/ต่ำสุด/ปิดของ EUR/USD เป็น 1.15 หมด

        บทเดิมจึงเขียนว่า "ระหว่างวันขึ้นไปสูงสุด 1.15 และลงต่ำสุด 1.15"
        ซึ่งผ่านด่านเลขได้สบายเพราะเลขมีต้นทางจริง แค่ไม่ให้ข้อมูลอะไรเลย
        """
        quote = self.evidence["quote"]
        high = wcb_writers.price(quote["high"], self.evidence)
        low = wcb_writers.price(quote["low"], self.evidence)
        self.assertNotEqual(high, low, "ราคาสูงสุดกับต่ำสุดถูกปัดมาชนกัน")
        self.assertIn(f"สูงสุด {high} และลงต่ำสุด {low}", self.rendered["a_standard"])

    def test_เส้นในหมุดกราฟต้องแยกจากกันได้(self):
        """ปัดเป็นจำนวนเต็มตายตัว ⇒ ทุก pivot ของ EUR/USD กลายเป็น "1" เท่ากันหมด"""
        for style, article in self.rendered.items():
            with self.subTest(style=style):
                for group in re.findall(r"\[\[chart:[^\]\|]+((?:\|[^\]]*)?)\]\]", article):
                    for raw in re.findall(r"[sr]=([\d,\.]+)", group):
                        for token in raw.split(","):
                            self.assertNotEqual(
                                token, "1", f"{style} มีเส้นกราฟที่ถูกปัดจนไร้ความหมาย")

    def test_หาทะเบียนเจอทั้งจากชื่อหัวข้อและจาก_tag(self):
        """ก้อนที่ปลายทางคืนมาสะท้อน tag กลับมา ไม่ใช่ชื่อหัวข้อของสายท่อ

        `btcusd` กลับมาเป็น `btc` ⇒ ถ้าทะเบียนรับแต่ชื่อหัวข้อ สายท่อจริงจะพัง
        เฉพาะหัวข้อที่ชื่อไม่ตรงกับ tag (พบจริงตอนรันสายท่อเต็ม 2026-08-05)
        """
        self.assertIs(wcb_source.profile_for("btc"), wcb_source.profile_for("btcusd"))
        for name, tag in wcb_source.ASSET_TAGS.items():
            with self.subTest(asset=name):
                self.assertIs(wcb_source.profile_for(tag), wcb_source.profile_for(name))

    def test_ก้อนที่ปลายทางปัดหยาบเกินไปต้องถูกติดธง(self):
        """EUR/USD จริงจากปลายทาง — ค่าที่เป็นราคาถูกปัดเป็นทศนิยมสองตำแหน่ง

        เขียนบทต่อได้ (ผู้ใช้สั่ง 2026-08-05) แต่ต้องรู้ตัวว่าก้อนนี้หยาบ
        `strict=True` ยังหยุดได้เหมือนเดิมสำหรับคนที่ต้องการพฤติกรรมนั้น
        """
        flagged = wcb_source.ensure_resolution(self.evidence)
        self.assertTrue(flagged["coarse_prices"])
        self.assertIn("เต็มความละเอียด", flagged["coarse_note"])
        with self.assertRaises(wcb_source.SnapshotTooCoarse):
            wcb_source.ensure_resolution(self.evidence, strict=True)

    def test_ก้อนที่ละเอียดพอต้องไม่ถูกติดธง(self):
        """กันธงใหม่กลายเป็นธงที่ขึ้นกับทุกอย่าง — ทองต้องสะอาด"""
        gold = wcb_source.normalize(json.loads(FIXTURE.read_text(encoding="utf-8")))
        self.assertFalse(wcb_source.ensure_resolution(gold)["coarse_prices"])
        wcb_source.ensure_resolution(gold, strict=True)  # ต้องไม่โยน

    def test_เส้นค่าเฉลี่ยที่ปัดมาชนกันต้องยุบเหลือบรรทัดเดียว(self):
        """"เหนือเส้น SMA20 ที่ 1.14 · เหนือเส้น SMA50 ที่ 1.14" อ่านเหมือนสองด่าน

        ทั้งที่เป็นเลขเดียวกัน — ตัวเลขตรงหลักฐานแต่การนำเสนอทำให้เข้าใจผิด
        """
        stack = wcb_writers._average_stack(
            self.evidence, ("SMA20", "SMA50", "SMA100", "SMA200"))
        joined = " · ".join(stack)
        self.assertIn("SMA20 และ SMA50", joined, "เส้นที่ค่าชนกันไม่ถูกยุบ")
        values = [part.rsplit(" ที่ ", 1)[1] for part in stack]
        self.assertEqual(len(values), len(set(values)), "ยังมีค่าซ้ำโผล่หลายบรรทัด")

    def test_ทองที่เส้นไม่ชนกันต้องไม่ถูกยุบ(self):
        """กันการยุบไปกินเคสปกติ — ทองแต่ละเส้นห่างกันหลายสิบดอลลาร์"""
        gold = wcb_source.normalize(json.loads(FIXTURE.read_text(encoding="utf-8")))
        stack = wcb_writers._average_stack(gold, ("SMA20", "SMA50", "SMA100", "SMA200"))
        for part in stack:
            self.assertNotIn(" และ ", part, "ยุบเส้นทองทั้งที่ค่าไม่ได้ชนกัน")

    def test_สินทรัพย์ที่ยังไม่ลงทะเบียนต้องหยุด_ไม่ใช่ใช้ค่าของทอง(self):
        """ล้มที่ชั้นนักเขียน ไม่ใช่ที่ `normalize()`

        ด่านตรวจบทความเรียก `normalize()` ด้วยเพื่อเอาค่า pivot ถ้าผูกทะเบียนไว้ตรงนั้น
        ก้อนพิการที่ควรได้คำตัดสิน "ตกด่าน" จะกลายเป็น exception กลางสายท่อแทน
        """
        stray = wcb_source.normalize({**self.payload, "asset": "ยังไม่ลงทะเบียน"})
        for writer in wcb_writers.WCB_WRITERS:
            with self.subTest(style=writer["id"]):
                with self.assertRaises(wcb_source.SnapshotUnusable):
                    writer["render"](stray)


class ทางเข้าสายท่อ(unittest.TestCase):
    def test_help_ต้องไม่พังบนคอนโซลโค้ดเพจไทย(self):
        """argparse พิมพ์ข้อความช่วยเหลือก่อนโค้ดใน main() ได้ทำงาน

        ถ้าตั้ง stdout ช้ากว่า `parse_args()` อักขระอย่าง `·` ในข้อความช่วยเหลือ
        จะทำให้ `--help` ตายด้วย UnicodeEncodeError บนเครื่องที่ใช้ cp874 (พบจริง 08-05)
        """
        env = {**os.environ, "PYTHONIOENCODING": "cp874"}
        result = subprocess.run(
            [sys.executable, "-m", "tools.build_daily_package", "--help"],
            cwd=_REPO_ROOT, env=env, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))


class ด่านสิทธิ์ข้อมูลสองสาย(ฐานสายสาธารณะ):
    def test_ระบุ_provider_เองได้เมื่อสินทรัพย์เดียวเดินสองสาย(self):
        """สองสายใช้คนละ endpoint ของ WCB — สายภายในใช้ series · สายสาธารณะใช้ snapshot

        ทะเบียนผูกหัวข้อไว้กับ endpoint ของสายภายใน สายสาธารณะจึงต้องระบุเอง
        ไม่งั้นจะถูกตัดสินด้วยสิทธิ์ของอีก endpoint ซึ่งอาจได้คำตอบคนละอย่างจากทีมเว็บ
        """
        default = license_gate.evaluate("xauusd", content_qa_passed=True, data_quality_passed=True)
        public = license_gate.evaluate("xauusd", providers=["wcb_snapshot_api"],
                                       content_qa_passed=True, data_quality_passed=True)
        self.assertEqual(default["providers"], ["wcb_series_api"])
        self.assertEqual(public["providers"], ["wcb_snapshot_api"])

    def test_ด่านต้องกั้นทันทีถ้าสิทธิ์ของสายสาธารณะกลับไปไม่ชัด(self):
        """ทะเบียนถูกปลดตามคำสั่งผู้ใช้ 2026-08-05 — เทสนี้จึงไม่ล็อกค่าปัจจุบัน

        สิ่งที่ต้องล็อกคือ**กลไก**: วันที่คำตอบจากทีมเว็บกลับมาว่าสิทธิ์ไม่ครอบคลุม
        แก้ทะเบียนกลับแล้วต้องกั้นเองทันทีโดยไม่ต้องแตะโค้ด
        """
        registry = license_gate.load_registry()
        registry["providers"]["wcb_snapshot_api"]["use_case"]["public_display"] = False
        result = license_gate.evaluate("xauusd", registry=registry,
                                       providers=["wcb_snapshot_api"],
                                       content_qa_passed=True, data_quality_passed=True)
        self.assertNotEqual(result["clearance"], license_gate.APPROVED_PUBLIC)
        self.assertTrue(result["license_reasons"])


class หัวข้อแผนในบท_ABC(ฐานสายสาธารณะ):
    """ผู้ใช้สั่งเปิดหัวข้อแผนให้ A/B/C เมื่อ 2026-08-05 (ดึก)

    ของที่ต้องล็อกไม่ใช่ถ้อยคำ แต่คือ **สามด่านที่กันบทที่อันตราย**:
    แผนที่ยังไม่ผ่านด่านความเสี่ยงต้องไม่ขึ้น · แผนที่สร้างจากราคาคนละที่กับบทต้องไม่ขึ้น
    · และแผนที่ชี้คนละทางกับที่บทเล่าต้องไม่ขึ้น
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        sys.path.insert(0, str(_REPO_ROOT / "tests"))
        from test_writers_and_layout import build_branch, no_trade_branch  # noqa: E402
        cls.branch = build_branch()
        cls.no_trade = no_trade_branch()
        cls.plan = writers.plan_for_public(cls.branch)
        # ก้อนที่ "สองแหล่งเห็นตรงกัน" — fixture สองใบนี้มาจากคนละวันโดยธรรมชาติ
        # จึงต้องขยับราคาให้ตรงกับทิศของแผนก่อน ไม่งั้นได้ทดสอบแต่ทางที่ถูกปฏิเสธ
        # (ค่าที่ขยับมีสองช่องเท่านั้น และ evidence คำนวณใหม่จากก้อนเดียวกันจึงยังสอดคล้อง)
        cls.agreed_payload = json.loads(json.dumps(cls.payload))
        cls.agreed_payload["quote"] = {**cls.agreed_payload["quote"],
                                       "price": 4040.0, "low": 4030.0}
        cls.agreed = wcb_source.normalize(cls.agreed_payload)

    def test_ฐานของเทสต้องเป็นแผนจริงที่ผ่านด่านความเสี่ยง(self):
        self.assertIsNotNone(self.plan, "fixture ไม่ให้แผนที่พูดได้ เทสชุดนี้จะไม่ได้ตรวจอะไร")
        self.assertEqual(self.plan["bias"], "down")
        self.assertEqual(wcb_writers.trend_code(self.agreed), "dn",
                         "ก้อนที่จัดให้ตรงกันแล้วต้องอ่านได้เป็นขาลงเหมือนแผน")

    def test_ทั้งสามสไตล์เขียนหัวข้อแผนเมื่อแผนผ่านด่าน(self):
        for writer in wcb_writers.WCB_WRITERS:
            with self.subTest(writer=writer["id"]):
                with_plan = writer["render"](self.agreed, self.plan)
                without = writer["render"](self.agreed, None)
                self.assertIn("จุดตัดขาดทุนของแผน", with_plan)
                self.assertNotIn("จุดตัดขาดทุนของแผน", without)
                self.assertGreater(len(with_plan), len(without))

    def test_เลขในหัวข้อแผนต้องเป็นเลขของแผนจริงทุกตัว(self):
        text = wcb_writers.render_a(self.agreed, self.plan)
        for value in (self.plan["entry"]["edge"], self.plan["stop"]["value"],
                      self.plan["targets"][0]["value"]):
            self.assertIn(f"{float(value):,.2f}", text)
        self.assertIn(voice_rules.format_ratio(self.plan["targets"][0]["rr"]), text)

    def test_ด่านตัวเลขต้องตกถ้าไม่ได้ส่งแผนเข้ากองหลักฐาน(self):
        """พิสูจน์ว่ากองหลักฐานถูกขยาย **เพราะมีแผนจริง** ไม่ใช่เพราะด่านหลวมลง

        ถ้าเทสนี้ผ่านทั้งสองทาง แปลว่าเลขแผนบังเอิญไปตรงกับค่าใน snapshot อยู่แล้ว
        ซึ่งจะทำให้เทสข้างบนไม่ได้พิสูจน์อะไรเลย
        """
        text = wcb_writers.render_a(self.agreed, self.plan)
        with_plan = wcb_copy_validator.validate(text, self.agreed_payload, plan=self.plan)
        without = wcb_copy_validator.validate(text, self.agreed_payload)
        self.assertEqual(with_plan["status"], "pass", with_plan["findings"])
        self.assertTrue(with_plan["plan_evidence_used"])
        self.assertEqual(without["status"], "fail")
        self.assertTrue(any(item["rule"] == "number_unsupported"
                            for item in without["findings"]))

    def test_กองหลักฐานของแผนต้องแคบ_ไม่ยกทั้งแผนเข้ามา(self):
        numbers = wcb_copy_validator.plan_numbers(self.plan)
        self.assertIn(abs(float(self.plan["stop"]["value"])), numbers)
        # คะแนนความเชื่อมั่นกับ invalidation ไม่ใช่เลขที่หัวข้อแผนได้รับอนุญาตให้เขียน
        self.assertNotIn(float(self.plan["confidence"]), numbers)
        invalidation = (self.plan.get("invalidation") or {}).get("value")
        if invalidation is not None and abs(float(invalidation)) != abs(
                float(self.plan["stop"]["value"])):
            self.assertNotIn(abs(float(invalidation)), numbers)

    def test_แผนที่ทิศขัดกับบทต้องไม่ขึ้นบทเด็ดขาด(self):
        """บทที่เล่าขาขึ้นแล้วแนบแผนขาลงอันตรายกว่าบทที่ไม่มีแผนเลย

        ด่านตัวเลขจับเรื่องนี้ไม่ได้และไม่มีวันจับได้ เพราะทุกเลขมีต้นทางครบถ้วน
        """
        self.assertEqual(wcb_writers.trend_code(self.evidence), "up")
        reason = wcb_writers.plan_rejection(self.evidence, self.plan)
        self.assertTrue(reason.startswith("bias_conflicts_with_article"), reason)
        plan, why = build_daily_package.resolve_public_plan(self.evidence, self.branch)
        self.assertIsNone(plan)
        self.assertTrue(why.startswith("bias_conflicts_with_article"))

    def test_แผนที่สร้างจากราคานอกกรอบวันต้องไม่ขึ้นบท(self):
        """แผนที่อ้างราคาที่ตลาดไม่ได้เทรดวันนี้ = สองแหล่งพูดถึงคนละตลาด"""
        stale = {**self.plan, "reference_price": float(self.agreed["quote"]["high"]) + 500}
        self.assertEqual(wcb_writers.plan_rejection(self.agreed, stale),
                         "plan_price_outside_today_range")

    def test_ไม่มีกรอบให้ทานสอบต้องไม่ปล่อยผ่าน(self):
        blind = json.loads(json.dumps(self.agreed_payload))
        blind["quote"] = {k: v for k, v in blind["quote"].items() if k not in ("low", "high")}
        self.assertEqual(
            wcb_writers.plan_rejection(wcb_source.normalize(blind), self.plan),
            "no_reference_range")

    def test_แผนของหัวข้ออื่นต้องไม่หลุดข้ามหัวข้อ(self):
        other = {**self.plan, "asset": "btcusd"}
        self.assertEqual(wcb_writers.plan_rejection(self.agreed, other),
                         "asset_mismatch:btcusd")

    def test_วันที่ไม่มีจังหวะต้องไม่มีหัวข้อแผน(self):
        plan, reason = build_daily_package.resolve_public_plan(self.agreed, self.no_trade)
        self.assertIsNone(plan)
        self.assertEqual(reason, "no_trade")

    def test_แผนที่ด่านความเสี่ยงไม่ให้ผ่านต้องไม่มีหัวข้อแผน(self):
        branch = {**self.branch, "audit": {**self.branch["audit"], "verdict": "revise"}}
        plan, reason = build_daily_package.resolve_public_plan(self.agreed, branch)
        self.assertIsNone(plan)
        self.assertEqual(reason, "risk_audit_verdict:revise")

    def test_รอบที่สายภายในไม่ได้รันต้องบอกเหตุผลนั้นตรง_ๆ(self):
        plan, reason = build_daily_package.resolve_public_plan(self.agreed, None)
        self.assertIsNone(plan)
        self.assertEqual(reason, "no_internal_plan_in_batch")

    def test_แผนอ่านมาจากไฟล์หลักฐานของสายภายในเท่านั้น(self):
        """ตัวเลขแผนต้องมาจาก `internal/trade-plan.json` ตามมติผู้ใช้ข้อ 15

        และแผนที่ถูก veto ซึ่งไปอยู่ `internal/rejected-plan/` ต้องอ่านไม่เจอ
        """
        with tempfile.TemporaryDirectory() as folder:
            asset_dir = Path(folder) / "xauusd"
            internal = asset_dir / "internal"
            self.assertIsNone(build_daily_package.load_trade_branch(asset_dir))

            rejected = internal / "rejected-plan"
            rejected.mkdir(parents=True)
            (rejected / "trade-plan.json").write_text(json.dumps(self.plan), encoding="utf-8")
            (rejected / "risk-audit.json").write_text(
                json.dumps(self.branch["audit"]), encoding="utf-8")
            self.assertIsNone(build_daily_package.load_trade_branch(asset_dir),
                              "แผนที่ถูกตีตกต้องอ่านไม่เจอ")

            (internal / "trade-plan.json").write_text(json.dumps(self.plan), encoding="utf-8")
            (internal / "risk-audit.json").write_text(
                json.dumps(self.branch["audit"]), encoding="utf-8")
            loaded = build_daily_package.load_trade_branch(asset_dir)
            self.assertEqual(loaded["status"], "built")
            self.assertEqual(loaded["plan"]["stop"]["value"], self.plan["stop"]["value"])

    def test_เส้นทางเต็ม_จากไฟล์แผนบนดิสก์ถึงบทที่วางลงคลัง(self):
        """ข้อต่อระหว่างชิ้นส่วนคือที่ที่บั๊กชอบอยู่ — เทสนี้เดินทั้งเส้นจริง

        สายภายในเขียน `internal/trade-plan.json` → สายสาธารณะอ่าน → ตัวเขียนใส่หัวข้อ
        → ด่านตัวเลขรับค่าจากแผน → ไฟล์ที่วางลงคลังต้องมีย่อหน้าแผนจริง
        """
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            snapshot = root / "snap.json"
            snapshot.write_text(json.dumps(self.agreed_payload, ensure_ascii=False),
                                encoding="utf-8")
            internal = root / "work" / "t" / "xauusd" / "internal"
            internal.mkdir(parents=True)
            (internal / "trade-plan.json").write_text(json.dumps(self.plan), encoding="utf-8")
            (internal / "risk-audit.json").write_text(
                json.dumps(self.branch["audit"]), encoding="utf-8")

            result = build_daily_package.build_public(
                "xauusd", batch_id="t", output_root=root / "work",
                publish_root=root / "out", snapshot_path=snapshot,
                cutoff_at="2026-08-05T11:34:00+00:00", max_age_minutes=10 ** 9)

            self.assertTrue(result["content_ok"], result["drafts"])
            self.assertTrue(result["trade_plan_public"]["included"],
                            result["trade_plan_public"]["reason"])
            articles = list((root / "out").rglob("xauusd.md"))
            self.assertEqual(len(articles), 3)
            for path in articles:
                with self.subTest(folder=path.parent.name):
                    text = path.read_text(encoding="utf-8")
                    self.assertIn("จุดตัดขาดทุนของแผน", text)
                    self.assertIn(f"{float(self.plan['stop']['value']):,.2f}", text)
            note = json.loads((internal / "public-line" / "trade-plan-note.json")
                              .read_text(encoding="utf-8"))
            self.assertTrue(note["included"])
            self.assertEqual(note["source"], "internal/trade-plan.json")

    def test_หลักฐานสองสายต้องไม่เขียนทับกัน(self):
        """`run_daily` รันสองสายด้วย batch เดียว — ชื่อไฟล์ชุดเดียวกันจึงเคยทับกัน

        ของสายภายในกลายเป็นหลักฐานล้วน ๆ ตั้งแต่ A/B/C แทนที่ในคลัง (2026-08-05)
        ทับเมื่อไหร่ = วันนั้นไม่เหลืออะไรให้ตรวจย้อนของสายภายในเลย
        """
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            snapshot = root / "snap.json"
            snapshot.write_text(json.dumps(self.payload, ensure_ascii=False), encoding="utf-8")
            internal = root / "work" / "t" / "xauusd" / "internal"
            internal.mkdir(parents=True)
            (internal / "raw.snapshot.json").write_text('{"ของสายภายใน": true}', encoding="utf-8")

            build_daily_package.build_public(
                "xauusd", batch_id="t", output_root=root / "work", publish_root=None,
                snapshot_path=snapshot, cutoff_at="2026-08-05T11:34:00+00:00",
                max_age_minutes=10 ** 9)

            kept = json.loads((internal / "raw.snapshot.json").read_text(encoding="utf-8"))
            self.assertEqual(kept, {"ของสายภายใน": True}, "สายสาธารณะเขียนทับหลักฐานสายภายใน")
            self.assertTrue((internal / "public-line" / "raw.snapshot.json").is_file())


if __name__ == "__main__":
    unittest.main()
