"""ด่านของสายสาธารณะ A/B/C — กฎที่พังแล้วบทความหลุดออกไปโดยไม่มีใครเห็น

เทสสำคัญที่สุดในไฟล์นี้คือ `test_เลขทุกตัวในบทความชี้กลับ_snapshot_ได้`
เพราะมันคือกฎเดียวที่กันความผิดพลาดที่เกิดขึ้นจริงเมื่อ 2026-08-05 — บทความชุดแรก
มีตัวเลขที่ไม่มีต้นทางใน snapshot ปนอยู่ห้าตัว และไม่มีใครจับได้จนกว่าจะมีด่านนี้
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools import (build_daily_package, calendar_feed, chart_public_renderer,  # noqa: E402
                   license_gate, publish_layout, wcb_series_source)
from tools import voice_rules, wcb_copy_validator, wcb_source, wcb_writers, writers  # noqa: E402
from tools import web_features  # noqa: E402

FIXTURES = _REPO_ROOT / "tests" / "fixtures"


class สวิตช์bullet:
    """context manager สลับค่า `web_bullets_enabled` ชั่วคราวโดยไม่แตะแฟ้มนโยบายจริง

    เขียนแฟ้มชั่วคราวแล้วชี้ `web_features.POLICY_PATH` ไปที่นั่น — ไม่ patch ตัวฟังก์ชัน
    เพราะอยากให้เทสเดินผ่านทางเดียวกับของจริง (อ่านไฟล์ → ตีความค่า) ไม่ใช่ทางลัด
    """

    def __init__(self, enabled: bool, *, tables: bool | None = None):
        # `tables=None` = ไม่เขียนช่องตารางลงแฟ้มชั่วคราว ⇒ ด่าน fail-closed ปิดตาราง
        # (พฤติกรรมเดิมของเทสทุกตัวก่อน 08-11 ค่ำ — ไม่ต้องไล่แก้จุดเรียกเก่า)
        self.enabled = enabled
        self.tables = tables

    def __enter__(self):
        self._tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                                encoding="utf-8")
        data = {"web_bullets_enabled": self.enabled}
        if self.tables is not None:
            data["web_tables_enabled"] = self.tables
        json.dump(data, self._tmp)
        self._tmp.close()
        self._saved = web_features.POLICY_PATH
        web_features.POLICY_PATH = Path(self._tmp.name)
        return self

    def __exit__(self, *exc):
        web_features.POLICY_PATH = self._saved
        os.unlink(self._tmp.name)
        return False


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
    """กองหลักฐาน — เก็บค่าสัมบูรณ์เพราะบทความเขียน MACD -3.7 เป็น 3.7 พร้อมคำว่าติดลบ

    ใช้ตัวจริงของด่าน (`wcb_copy_validator.collect_evidence`) แทนการเดินก้อนซ้ำเอง —
    เดินคนละตัวเมื่อไหร่ เทสกับด่านจะเห็นกองหลักฐานคนละกอง แล้วเทสจะผ่าน/ตกคนละแบบ
    กับของจริง (เจอตอนเปลี่ยนระบบปี 08-10/08-11: ด่านรู้จักปีแบบหนึ่ง เทสรู้จักอีกแบบ)
    """
    return wcb_copy_validator.collect_evidence(payload)


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

    def test_หัวข้อกลยุทธ์ท้ายบทเป็นบูลเลตตามคำสั่งผู้ใช้_08_11(self):
        """ผู้ใช้เคาะ "ทำทั้ง 3 ข้อ" 08-11 บ่าย — หัวข้อกลยุทธ์/ฉากทัศน์ของ A/B/C
        แยกจากย่อหน้าแน่นเป็น bullet ป้ายชัด (โครงเดียวกับที่ทำใน D/E/G ไปแล้ว)
        · fixture นี้มีทั้งแนวรับและแนวต้าน จึงต้องได้โครงเต็มทุกสไตล์"""
        wanted = {
            # 🔄 08-11 ค่ำ: A เปลี่ยนจากป้ายเงื่อนไข 🟢🔴 เป็นสี่ป้ายแผนตรง
            # (ผู้ใช้ตีกลับฉบับบรรยาย — ดู `_a_plan_block`) · B/C ยังชุดเดิม
            "a_standard": tuple(f"**{label}**" for label in wcb_writers.A_PLAN_LABELS),
            "b_technical": ("**ต้องดูอะไร:**", "**ทำไมต้องดูราคาปิด:**",
                            "**ทำอย่างไร:**", "**แล้วจะเป็นอย่างไรต่อ:**"),
            "c_event": ("**ฉากทัศน์ตลาดตอบรับเชิงบวกต่อทอง:**",
                        "**ฉากทัศน์ตลาดตอบรับเชิงลบต่อทอง:**",
                        "**การบริหารความเสี่ยงช่วงข่าว:**"),
        }
        for style, labels in wanted.items():
            article = self.rendered[style]
            for label in labels:
                with self.subTest(style=style, label=label):
                    self.assertIn(label, article, f"{style} ขาดป้าย {label}")


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
        """เทียบกับ **ทะเบียนตัวจริงของด่าน** ไม่ใช่รูปแบบที่เทสคิดขึ้นเอง

        🔄 08-11: เดิมเทสนี้พิมพ์ `##\\s*เทคนิค` ฯลฯ ซ้ำกับด่านอีกชุดหนึ่ง ⇒ ตอนผู้ใช้
        สั่งเปลี่ยนชื่อหัวข้อตามใบตัวอย่าง ต้องไล่แก้สองที่และมีสิทธิ์แก้ไม่ตรงกัน
        (บทเรียนเดียวกับ `author_slug_for` ที่รวมทางเดียวไว้ที่เดียว) — อ่านทะเบียน
        เดียวกับที่ `wcb_copy_validator` ใช้จริง ⇒ ชื่อใหม่ที่ลืมขึ้นทะเบียนจะตกที่นี่ทันที
        """
        for style, article in self.rendered.items():
            with self.subTest(style=style):
                for name, pattern in wcb_copy_validator.REQUIRED_HEADINGS:
                    self.assertRegex(article, pattern, f"{style} ขาด{name}")

    def test_H1_ได้ตัวเดียวบรรทัดแรก_ห้าม_bullet_ห้ามตาราง(self):
        """🔄 **กลับด้าน 2026-08-10** — เดิมห้าม H1 ทั้งหมด (เว็บสร้าง H1 จาก `title` ให้เอง)
        · ผู้ใช้สั่งให้ทุกสไตล์มีทั้ง title และ H1 ⇒ ได้ **ตัวเดียว ที่บรรทัดแรกของเนื้อบท**
        · H1 กลางบทยังผิดเสมอไม่ว่าหลังบ้านจะรองรับช่องแยกหรือไม่

        ข้อ bullet ยืนตามค่าปัจจุบันของ `web_bullets_enabled` ซึ่งตอนนี้ปิดอยู่ —
        ชุดเทส `สวิตช์บทตามความสามารถของเว็บ` ด้านล่างคุมพฤติกรรมของทั้งสองโหมด
        """
        for style, article in self.rendered.items():
            with self.subTest(style=style):
                _, body = split_frontmatter(article)
                lines = body.splitlines()
                h1_lines = [i for i, line in enumerate(lines) if line.startswith("# ")]
                self.assertEqual(len(h1_lines), 1, f"{style} ต้องมี H1 ตัวเดียว")
                first = next(i for i, line in enumerate(lines) if line.strip())
                self.assertEqual(h1_lines[0], first, f"{style} H1 ต้องอยู่บรรทัดแรกของเนื้อบท")
                for line in lines:
                    if not web_features.bullets_enabled():
                        self.assertIsNone(re.match(r"^\s*[-*]\s", line), f"{style} มี bullet")
                    # หมุดกราฟใช้ | คั่นพารามิเตอร์ตามสัญญาของเว็บ ลอกออกก่อนตรวจหาตาราง
                    # · แถวตารางจริง (ขึ้นต้น |) อนุญาตเมื่อสวิตช์ตารางเปิด (08-11 ค่ำ)
                    if web_features.tables_enabled() and line.lstrip().startswith("|"):
                        continue
                    self.assertNotIn("|", re.sub(r"\[\[chart:[^\]]*\]\]", "", line),
                                     f"{style} มี | นอกแถวตาราง")

    def test_แฟ้มนโยบายจริงให้สไตล์A_ออกมาเป็น_bullet(self):
        """🔒 **ผู้ใช้เลือกฉบับ bullet เมื่อ 2026-08-10 หลังดูใบตัวอย่างสองโหมด**

        ล็อกที่ **ผลลัพธ์** ไม่ใช่ที่ค่าในไฟล์ — สิ่งที่ตกลงกันไว้คือ "บท A ขึ้นเว็บเป็นลิสต์"
        ถ้าวันหนึ่งสวิตช์ยังเปิดแต่ชั้นนักเขียนเลิกใส่ bullet (เช่นมีคนรื้อ `listing()`)
        เทสที่ดูแค่ค่า `true` จะยังผ่านทั้งที่ของจริงพังไปแล้ว

        **ถ้าเปิดหน้าเว็บจริงแล้วลิสต์ไม่มีจุดนำ** (CSS `.an-body ul` ยังไม่มา — ดู E23)
        ให้กลับ `web_bullets_enabled` เป็น false **แล้วลบเทสนี้ทิ้ง** ไม่ใช่ดัดให้ผ่าน
        """
        self.assertTrue(web_features.bullets_enabled(),
                        "web_bullets_enabled ถูกปิดกลับ — ตั้งใจหรือเปล่า")
        บท = self.rendered["a_standard"].splitlines()
        self.assertTrue([line for line in บท if line.startswith("- ")],
                        "สวิตช์เปิดอยู่แต่สไตล์ A ไม่มี bullet สักบรรทัด")

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


class สวิตช์บทตามความสามารถของเว็บ(ฐานสายสาธารณะ):
    """bullet เปิด/ปิดจากแฟ้มนโยบายที่เดียว — ชั้นนักเขียนกับด่านตรวจต้องขยับพร้อมกัน

    ที่ต้องมีเทสชุดนี้ เพราะโหมดที่ **ไม่ได้ใช้ในรอบผลิตจริง** คือโหมดที่พังเงียบได้
    ง่ายที่สุด · วันที่ทีมเว็บเพิ่ม CSS แล้วเราพลิกสวิตช์ ต้องได้บทที่ผ่านด่านทันที
    ไม่ใช่วันที่เพิ่งมาค้นพบว่าชั้นใดชั้นหนึ่งไม่รู้จักสวิตช์
    """

    THAI = re.compile(r"[฀-๿]")

    def _render_a(self, enabled: bool) -> str:
        with สวิตช์bullet(enabled):
            return wcb_writers.render_a(self.evidence)

    def test_เปิดสวิตช์แล้วสไตล์A_มี_bullet_ปิดแล้วไม่มี(self):
        มี = self._render_a(True).splitlines()
        ไม่มี = self._render_a(False).splitlines()
        self.assertTrue([line for line in มี if line.startswith("- ")],
                        "เปิดสวิตช์แล้วยังไม่มี bullet เลย")
        self.assertFalse([line for line in ไม่มี if line.startswith("- ")],
                         "ปิดสวิตช์แล้วยังมี bullet หลุดมา")

    def test_สองโหมดให้เนื้อความและตัวเลขชุดเดียวกัน(self):
        """สวิตช์เปลี่ยน**การจัดวาง** ไม่ใช่เนื้อหา

        ถ้าสองโหมดพูดคนละเรื่อง สิ่งที่หัวหน้าตรวจผ่านจะไม่ใช่สิ่งที่ขึ้นเว็บ และด่าน
        ตัวเลขที่รันกับโหมดหนึ่งจะไม่ได้รับประกันอะไรให้อีกโหมดเลย
        """
        เปิด, ปิด = self._render_a(True), self._render_a(False)
        # ลอกเลขเชิงโครงสร้างออกก่อนเทียบ ด้วยนิยามเดียวกับด่านจริง — เลขลำดับลิสต์
        # ("  1. **4,366.37**…" ของแนวรับ/แนวต้านแบบลำดับ 08-11) มีเฉพาะโหมด bullet
        # โดยเจตนา เหมือนที่ขีด `- ` มีเฉพาะโหมดนั้น · เลขตลาดจริงยังต้องตรงกันทุกตัว
        เลข = [sum((NUMBER.findall(wcb_copy_validator.strip_structural(line))
                    for line in text.splitlines()), [])
               for text in (เปิด, ปิด)]
        self.assertEqual(เลข[0], เลข[1],
                         "ตัวเลขที่ปรากฏในบทไม่ตรงกันระหว่างสองโหมด")
        คำ = [round(len(self.THAI.findall(text)) / 3.5) for text in (เปิด, ปิด)]
        self.assertEqual(คำ[0], คำ[1], "ความยาวสองโหมดไม่เท่ากัน")

    def test_ด่านตรวจปล่อย_bullet_เมื่อเปิดสวิตช์และตีตกเมื่อปิด(self):
        บท = self._render_a(True)
        for enabled, ต้องเจอ in ((True, False), (False, True)):
            with self.subTest(สวิตช์=enabled), สวิตช์bullet(enabled):
                ผล = wcb_copy_validator.validate(บท, self.payload)
                รหัส = [item["rule"] for item in ผล["findings"]]
                self.assertEqual("bullet_forbidden" in รหัส, ต้องเจอ,
                                 f"สวิตช์={enabled} แต่ผลของด่านเป็น {รหัส}")

    def test_ตารางถูกตีตกเมื่อสวิตช์ตารางปิดหรือไม่รู้ค่า(self):
        """🔄 08-11 ค่ำ: ตารางเปลี่ยนจาก "ห้ามทุกกรณี" เป็นสวิตช์ `web_tables_enabled`
        — แฟ้มนโยบายที่ไม่มีช่องนี้ต้อง fail-closed เป็นห้าม เหมือน bullet"""
        # ต่อท้ายบทตรง ๆ ไม่ผูกกับชื่อหัวข้อ — ชื่อหัวข้อเปลี่ยนได้ตามสไตล์การเขียน
        # (เกิดจริง 08-11) แล้ว `replace` ที่ไม่เจอจะเงียบ ทำให้เทสผ่านโดยไม่ได้ตรวจอะไร
        บท = self._render_a(True) + "\n\n| ก | ข |\n"
        with สวิตช์bullet(True):
            ผล = wcb_copy_validator.validate(บท, self.payload)
        self.assertIn("table_forbidden", [item["rule"] for item in ผล["findings"]])

    def test_เปิดสวิตช์ตารางแล้วแถวตารางผ่านแต่ขีดกลางประโยคยังตก(self):
        """อนุญาตเฉพาะบรรทัดที่เป็นแถวตารางจริง — | หลุดกลางประโยคคือข้อความเสียรูป
        ไม่ใช่ตาราง ต้องตกเหมือนเดิมไม่ว่าสวิตช์จะเปิดไหม"""
        with สวิตช์bullet(True, tables=True):
            สะอาด = wcb_writers.render_a(self.evidence)
            ผลสะอาด = wcb_copy_validator.validate(สะอาด, self.payload)
            เสีย = สะอาด + "\n\nประโยคที่มี | หลุดมากลางทาง\n"
            ผลเสีย = wcb_copy_validator.validate(เสีย, self.payload)
        self.assertIn("| อินดิเคเตอร์ | ค่า | สัญญาณ |", สะอาด,
                      "เปิดสวิตช์ตารางแล้วสไตล์ A ต้องมีตารางอินดิเคเตอร์")
        self.assertNotIn("table_forbidden",
                         [item["rule"] for item in ผลสะอาด["findings"]])
        self.assertIn("table_forbidden", [item["rule"] for item in ผลเสีย["findings"]])


class ด่านห้ามVolumeสายเว็บ(ฐานสายสาธารณะ):
    """ใบแจ้งหัวหน้า 2026-08-13 ข้อ 3: volume มีจริงเฉพาะหุ้น — บททอง (OTC) ห้ามพูดถึง

    fixture ของฐานเป็นทองคำ (spot_metal) ซึ่งปลายทางส่ง volume เป็น null ทุกแท่ง
    ⇒ ประโยค volume ในบทนี้มีทางเดียวคือแต่งขึ้น ต้องตกที่ระดับคำ
    """

    def test_บททองพูดถึงปริมาณการซื้อขายต้องตก(self):
        with สวิตช์bullet(True):
            สะอาด = wcb_writers.render_a(self.evidence)
            เสีย = สะอาด + "\n\nปริมาณการซื้อขายเบาบางระหว่างรอตัวเลขสำคัญ\n"
            ผลสะอาด = wcb_copy_validator.validate(สะอาด, self.payload)
            ผลเสีย = wcb_copy_validator.validate(เสีย, self.payload)
        self.assertNotIn("volume_forbidden",
                         [item["rule"] for item in ผลสะอาด["findings"]])
        self.assertIn("volume_forbidden", [item["rule"] for item in ผลเสีย["findings"]])

    def test_คำละตินตระกูลvolumeตกทั้งชุดแบบไม่สนตัวพิมพ์(self):
        with สวิตช์bullet(True):
            สะอาด = wcb_writers.render_a(self.evidence)
            for คำ in ("Volume", "VWAP", "OBV"):
                with self.subTest(คำ=คำ):
                    ผล = wcb_copy_validator.validate(
                        สะอาด + f"\n\nสัญญาณจาก {คำ} ยังไม่ยืนยันทิศ\n", self.payload)
                    self.assertIn("volume_forbidden",
                                  [item["rule"] for item in ผล["findings"]])


class สไตล์A_รอบรีวิวผู้ใช้_08_11_บ่าย(ฐานสายสาธารณะ):
    """🔒 คำสั่งผู้ใช้รอบรีวิว A: ตัดวงเล็บอธิบายทั้งหมด + แนวรับ/แนวต้านเป็นลำดับ

    ① bullet อินดิเคเตอร์รายตัว — วงเล็บอธิบายท้าย ("(วัดน้ำหนักแรงซื้อขายสะสม)" ฯลฯ)
      ต้องหายทั้งชุด ② หัวฝั่งเหลือ "**แนวต้าน**:"/"**แนวรับ**:" ไม่มีวงเล็บขยาย
    ③ ระดับใต้แต่ละฝั่งเป็นลำดับเลข `1.` ทีละด่าน และยังผ่านด่านตัวเลขจริง
    """

    ที่ถูกตัด = ("วัดน้ำหนักแรงซื้อขายสะสม", "วัดว่าราคาปิดอยู่ตรงไหนของกรอบสั้น",
                "วัดระยะห่างจากค่าเฉลี่ย", "วัดการตัดกันของโมเมนตัม",
                "ด่านทดสอบด้านบน", "จุดรองรับด้านล่าง")

    def test_วงเล็บอธิบายถูกตัดออกทั้งชุด(self):
        article = self.rendered["a_standard"]
        for text in self.ที่ถูกตัด:
            self.assertNotIn(text, article,
                             f"ผู้ใช้สั่งตัดวงเล็บอธิบาย 08-11 แต่ \"{text}\" ยังอยู่ในบท A")

    def test_แนวรับแนวต้านเป็นลำดับเลขล้วน(self):
        """🔄 08-11 ค่ำ (ชุดสอง): "(ด่านแรก · จุดหมุนกรอบรายวัน)" ถูกสั่งตัดตามไปด้วย
        — รายการเหลือเลขกับหน่วยล้วน · คำกำกับกรอบย้ายไปเป็นประโยคท้ายก้อน
        เฉพาะวันที่ฝั่งใดไม่ใช่กรอบรายวัน (กันบั๊ก NVDA 08-05 แบบไม่รกวันปกติ)"""
        with สวิตช์bullet(True):
            article = wcb_writers.render_a(self.evidence)
            ผล = wcb_copy_validator.validate(article, self.payload)
        # ดูเฉพาะหัวข้อเทคนิค — บันไดแผนท้ายบท (08-11 ค่ำ) ก็เป็นลำดับเลขเหมือนกัน
        เทคนิค = article.split("## ปัจจัยข่าว", 1)[0]
        lines = เทคนิค.splitlines()
        self.assertIn("- **แนวต้าน**:", lines, "หัวฝั่งบนต้องเหลือชื่อล้วนไม่มีวงเล็บ")
        self.assertIn("- **แนวรับ**:", lines, "หัวฝั่งล่างต้องเหลือชื่อล้วนไม่มีวงเล็บ")
        ordered = [line for line in lines if re.match(r"^\s+\d+\.\s", line)]
        self.assertTrue(ordered, "ระดับราคาต้องเรียงเป็นลำดับเลขตามคำสั่งผู้ใช้")
        for line in ordered:
            self.assertNotIn("(", line, "รายการระดับราคาต้องไม่มีวงเล็บกำกับแล้ว")
        self.assertNotIn("(ด่านแรก", article)
        # เลขลำดับเป็นเครื่องหมายโครงสร้าง — ด่านตัวเลขต้องไม่ตีตกมันเป็นเลขไร้ต้นทาง
        ตก = [item for item in ผล["findings"] if item["rule"] == "number_unsupported"]
        self.assertEqual(ตก, [], "เลขลำดับลิสต์ต้องไม่ตกด่าน number_unsupported")

    def test_โหมดร้อยแก้วไม่มีเลขลำดับหลุดไปปน(self):
        """สวิตช์ปิด = เลขลำดับหายไปพร้อมขีด ไม่ใช่กลายเป็นเลขลอยในย่อหน้า"""
        with สวิตช์bullet(False):
            article = wcb_writers.render_a(self.evidence)
        ค้าง = [line for line in article.splitlines() if re.match(r"\s*\d+\.\s", line)]
        self.assertEqual(ค้าง, [], "โหมดร้อยแก้วมีเลขลำดับค้าง")
        self.assertIn("**แนวต้าน**:", article)


class สไตล์A_แผนตรง_08_11_ค่ำ(ฐานสายสาธารณะ):
    """🔒 คำสั่งผู้ใช้ 08-11 ค่ำ: หัวข้อกลยุทธ์ของ A "ให้แผนไปเลย ไม่เอาเชิงบรรยาย"

    ตัวอย่างที่ผู้ใช้ให้: "รอเข้าจังหวะ 1 2 3 ถ้าหลุด cut loss หรือ เข้าได้ตั้งแต่
    4300-4305 Tp ที่เท่าไร" ⇒ สี่ป้ายตายตัว (`A_PLAN_LABELS`) ทุกเส้นทาง
    และก้อนบรรยายของรอบบ่าย (ย่อหน้าตำแหน่งราคา + 🟢🔴) ต้องหายทั้งชุด
    """

    ที่ถูกตัด = ("เงื่อนไขยืนยันฝั่งซื้อ", "เงื่อนไขภาพเสีย", "ระหว่างนั้นทำอย่างไร",
                "ซึ่งไม่ใช่จุดที่ได้เปรียบทั้งสองทาง")

    def test_ป้ายแผนครบสี่และก้อนบรรยายเดิมหายทั้งชุด(self):
        article = self.rendered["a_standard"]
        for label in wcb_writers.A_PLAN_LABELS:
            self.assertIn(f"**{label}**", article, f"ป้ายแผน {label!r} หาย")
        for text in self.ที่ถูกตัด:
            self.assertNotIn(text, article,
                             f"ผู้ใช้สั่งตัดก้อนบรรยาย แต่ \"{text}\" ยังอยู่ในบท A")
        self.assertIn(wcb_writers.A_PLAN_CAVEAT, article)

    def _แผนของ(self, evidence: dict) -> str:
        with สวิตช์bullet(True):
            article = wcb_writers.render_a(evidence)
        return article.split("## วางแผนและกลยุทธ์การเทรดวันนี้", 1)[1]

    def test_ไม่มีแผนระบบ_บันไดรอเข้าเป็นลำดับเลขและไม่มีวงเล็บกรอบ(self):
        """🔄 08-11 ค่ำชุดสี่: ผู้ใช้สั่งตัด "(จุดหมุนกรอบรายวัน)" ออกจากหัวข้อแผน
        — วันปกติ (สองฝั่งมาจากกรอบรายวัน) จึงต้องไม่มีคำกำกับกรอบเลย"""
        แผน = self._แผนของ(self.evidence)
        self.assertTrue(re.search(rf"\n  1\. {wcb_writers.VISUAL_INDENT}\*\*[\d,\.]+\*\*", แผน),
                        "บันไดแผนต้องเป็นลำดับเลขทีละด่าน (พร้อม NBSP เยื้องชุดสาม)")
        _, _, source = wcb_writers._levels_by_frame(self.evidence)
        self.assertEqual({source.get("below"), source.get("above")}, {"1day"},
                         "ชุดทดสอบนี้ต้องเป็นวันที่สองฝั่งมาจากกรอบรายวัน")
        self.assertNotIn("จุดหมุนกรอบ", แผน,
                         "วันปกติต้องไม่มีคำกำกับกรอบค้างอยู่ในหัวข้อแผน")

    def test_ฝั่งที่ไม่ใช่กรอบรายวันยังต้องมีคำกำกับท้ายก้อน(self):
        """กติกา "คำกำกับกรอบเวลาห้ามหาย" ยังอยู่ — ย้ายที่ ไม่ได้ยกเลิก

        บั๊ก NVDA 2026-08-05: ด่านฝั่งบนทั้งชุดเป็นจุดหมุนกรอบ 30 นาที แต่บทเสนอ
        ปนกับด่านรายวัน ⇒ คนอ่านเอาด่านของกราฟ 30 นาทีไปวางกรอบทั้งวัน
        """
        payload = json.loads(json.dumps(self.payload))
        # ทำให้ฝั่งบนไม่เหลือจุดหมุนรายวัน: ดันจุดหมุนรายวันทุกตัวลงใต้ราคาปัจจุบัน
        # (เท่ากับวันที่ราคาทะลุชั้นรายวันฝั่งบนไปหมดแล้ว ซึ่งเกิดจริงกับ NVDA)
        spot = float(payload["quote"]["price"])
        กองรายวัน = [payload["technicals"].get("pivots") or {},
                    (payload["technicalsByTf"].get("1day") or {}).get("pivots") or {}]
        for pivots in กองรายวัน:
            for key, value in list(pivots.items()):
                if value is not None and float(value) >= spot:
                    pivots[key] = round(spot * 0.9, 5)
        evidence = wcb_source.normalize(payload)
        _, _, source = wcb_writers._levels_by_frame(evidence)
        self.assertNotEqual(source.get("above"), "1day",
                            "ชุดทดสอบต้องบังคับให้ฝั่งบนมาจากกรอบเล็กจริง")
        แผน = self._แผนของ(evidence)
        self.assertIn("จุดหมุนกรอบ", แผน,
                      "ฝั่งที่ไม่ใช่กรอบรายวันต้องมีคำกำกับท้ายก้อนเสมอ")
        self.assertIn(wcb_writers.TF_THAI[source["above"]], แผน,
                      "คำกำกับต้องบอกกรอบเวลาจริงของฝั่งนั้น")

    def test_มีแผนระบบ_เขียนโซนเข้า_CutLoss_TP_ตรงตามแผน(self):
        """เส้นทางมีแผนจากชั้นวางแผน — เลขทุกตัวยกจากก้อนแผน ไม่คิดใหม่

        ก้อนแผนในเทสนี้เป็นรูปเดียวกับ `internal/trade-plan.json` (ดู
        `plan_paragraphs`) · เทสนี้ตรวจการจัดวาง ไม่ได้ตรวจด่านตัวเลข
        เพราะเลขแผนมีต้นทางอยู่ที่ไฟล์แผน ไม่ใช่ snapshot ที่ด่านถืออยู่
        """
        plan = {"asset": self.evidence["asset"], "bias": "up",
                "bias_reason": "price_above_rising_stack",
                "entry": {"edge": 4310.0, "zone": [4300.0, 4305.0]},
                "stop": {"value": 4280.0},
                "targets": [{"value": 4360.0, "rr": 1.6},
                            {"value": 4400.0, "rr": 2.4}]}
        with สวิตช์bullet(True):
            article = wcb_writers.render_a(self.evidence, plan)
        แผนบท = article.split("## วางแผนและกลยุทธ์การเทรดวันนี้", 1)[1]
        self.assertIn("พิจารณาบริเวณ **4,300.00** ถึง **4,305.00**", แผนบท)
        self.assertIn("**จุดตัดขาดทุน (Stop Loss):** **4,280.00**", แผนบท)
        self.assertRegex(แผนบท, rf"  1\. {wcb_writers.VISUAL_INDENT}\*\*4,360\.00\*\*")
        self.assertRegex(แผนบท, rf"  2\. {wcb_writers.VISUAL_INDENT}\*\*4,400\.00\*\*")
        self.assertIn("เท่าของระยะที่เสี่ยง", แผนบท)
        # แผนระบบมาแล้ว บันไดรอเข้าต้องไม่โผล่ซ้อน — แผนเดียวต่อวัน
        self.assertNotIn("รอราคาย่อลงมาแตะแนวรับ", แผนบท)


class สไตล์A_รอบรีวิว_08_11_ค่ำ_ชุดสอง(ฐานสายสาธารณะ):
    """🔒 คำสั่งผู้ใช้ 08-11 ค่ำ (ชุดสอง หลังเห็นบทจริง):

    ① ตัด "(ด่านแรก · จุดหมุนกรอบรายวัน)" ออกจากรายการแนวรับ/แนวต้าน
    ② ภาพตีเส้นครบ 3 ต่อฝั่งตามที่บทไล่ (หมุด `chart_marker` 3/3 — ภาพวาดตามหมุด)
    ③ อินดิเคเตอร์รายวันเป็น**ตารางครบทุกตัว** แทน bullet 4 ตัวเดิม
       (สวิตช์ `web_tables_enabled` — เหตุผลเดียวกับ bullet ตอน 08-10)
    """

    def test_ภาษาสไตล์A_ฉบับผู้ใช้ตรวจผ่าน_08_14(self):
        article = self.rendered["a_standard"]
        required = (
            "จำนวนสัญญาณบอกเพียงว่ามีเครื่องมือกี่ตัวชี้ไปแต่ละฝั่ง",
            "ไม่ได้หมายความว่าทุกสัญญาณมีน้ำหนักเท่ากัน",
            "ค่าของอินดิเคเตอร์ทั้งหมดที่นำมารวมสัญญาณมีดังนี้",
            "ข้อมูลชุดนี้ช่วยบอกตำแหน่งของราคาในรอบใหญ่",
            "การบริหารความเสี่ยงยังเป็นส่วนสำคัญของแผน",
        )
        for phrase in required:
            self.assertIn(phrase, article)
        forbidden = ("ซึ่งเป็นการนับหัว", "ยังไม่ได้เล่าเรื่องเดียวกัน",
                     "ปิดท้ายด้วยเรื่อง", "สายส่งจากตัวเลขเหล่านี้ถึงราคาทองเดินผ่านทางเดียว")
        for phrase in forbidden:
            self.assertNotIn(phrase, article)

    def test_ภาษาและการตีความสไตล์B_ฉบับAgent8(self):
        article = self.rendered["b_technical"]
        required = ("ADX(14) อยู่ที่", "ค่า RSI ในกรอบเล็กสูงกว่ากรอบรายวัน",
                    "จุดหมุนเป็นระดับอ้างอิงที่คำนวณจากแท่งก่อนหน้า",
                    "จุดตัดขาดทุนควรอิงระดับที่ทำให้เหตุผลของแผนหมดลง")
        for phrase in required:
            self.assertIn(phrase, article)
        self.assertNotRegex(article, r"ADX\(14\) อยู่ที่ [^·\n]+สัญญาณฝั่ง")
        for phrase in ("แรงซื้อกระจุกอยู่ในระยะสั้น", "เอาหางไปกระดิกหมา",
                       "ถอยจุดตัดขาดทุนให้พ้นโซน", "ผู้เล่นจำนวนมากเห็นตรงกัน"):
            self.assertNotIn(phrase, article)

    def test_ภาษาและฉากทัศน์สไตล์C_เมื่อไม่มีค่าคาด(self):
        article = self.rendered["c_event"]
        self.assertIn("ฉากทัศน์ตลาดตอบรับเชิงบวกต่อทอง", article)
        self.assertIn("ฉากทัศน์ตลาดตอบรับเชิงลบต่อทอง", article)
        self.assertNotIn("อ่อนกว่าครั้งก่อน", article)
        self.assertNotIn("แข็งกว่าครั้งก่อน", article)
        self.assertNotIn("ไม่มีเทรนด์แข็งพอ", article)

    def test_สไตล์C_ใช้ค่าคาดเมื่อปฏิทินมีหลักฐาน(self):
        payload = json.loads(json.dumps(self.payload))
        payload["calendar"]["events"][0]["forecast"] = "1"
        article = wcb_writers.render_c(wcb_source.normalize(payload))
        self.assertIn("ตัวเลขเศรษฐกิจออกมาต่ำกว่าคาด", article)
        self.assertIn("ตัวเลขเศรษฐกิจออกมาสูงกว่าคาด", article)
        self.assertNotIn("อ่อนกว่าครั้งก่อน", article)

    def test_หมุดกราฟให้เส้นครบสามต่อฝั่งตามที่มีจริง(self):
        article = self.rendered["a_standard"]
        below, above = wcb_writers._sorted_levels(self.evidence)
        markers = re.findall(r"\[\[chart:[^|\]]+\|s=([\d.,]+)\|r=([\d.,]+)\]\]", article)
        self.assertTrue(markers, "สไตล์ A ต้องมีหมุดกราฟพร้อมเส้นสองฝั่ง")
        for s_text, r_text in markers:
            self.assertEqual(s_text.split(","),
                             wcb_writers._distinct_lines(below, 3, self.evidence),
                             "เส้นฝั่งรับบนหมุดต้องครบ 3 ด่านตามบท (เท่าที่ evidence มี)")
            self.assertEqual(r_text.split(","),
                             wcb_writers._distinct_lines(above, 3, self.evidence),
                             "เส้นฝั่งต้านบนหมุดต้องครบ 3 ด่านตามบท (เท่าที่ evidence มี)")

    def test_ตารางอินดิเคเตอร์ครบทุกตัวและ_bullet_สี่ตัวเดิมหาย(self):
        article = self.rendered["a_standard"]     # แฟ้มนโยบายจริง — สวิตช์ตารางเปิด
        self.assertIn("| อินดิเคเตอร์ | ค่า | สัญญาณ |", article)
        expected = [name for name, item in self.evidence["daily"]["indicators"].items()
                    if item.get("value") is not None]
        for name in expected:
            self.assertIn(f"| {name} |", article, f"ตารางขาด {name}")
        rows = [line for line in article.splitlines()
                if line.startswith("| ") and "---" not in line
                and not line.startswith("| อินดิเคเตอร์")]
        self.assertEqual(len(rows), len(expected),
                         "จำนวนแถวตารางต้องเท่ากับอินดิเคเตอร์ที่มีค่าจริง")
        self.assertNotIn("ไล่ดูรายตัวจะเห็นเหลี่ยม", article,
                         "bullet รายตัว 4 ตัวเดิมต้องถูกแทนด้วยตาราง")

    def test_สวิตช์ตารางปิดถอยเป็นร้อยแก้วเนื้อครบทุกตัว(self):
        with สวิตช์bullet(True):                  # แฟ้มชั่วคราวไม่มีช่องตาราง = ปิด
            article = wcb_writers.render_a(self.evidence)
        _, body = split_frontmatter(article)
        แถวตาราง = [line for line in body.splitlines() if line.lstrip().startswith("|")]
        self.assertEqual(แถวตาราง, [], "สวิตช์ปิดแล้วต้องไม่มีแถวตารางหลุดมา")
        for name, item in self.evidence["daily"]["indicators"].items():
            if item.get("value") is not None:
                self.assertIn(f"{name} อยู่ที่", article,
                              f"โหมดร้อยแก้วต้องยังไล่ {name} ครบ ไม่ใช่ตัดเนื้อทิ้ง")


class สไตล์A_รอบรีวิว_08_11_ค่ำ_ชุดสาม(ฐานสายสาธารณะ):
    """🔒 คำสั่งผู้ใช้ 08-11 ค่ำ (ชุดสาม จากภาพหน้าเว็บจริงรอบสอง):

    ① การเยื้องยังไม่ขึ้นบนหน้าเว็บ — CSS ปลายทางตัด padding ลิสต์ซ้อน
      ⇒ ชั้นลึกต้องมี NBSP นำเนื้อความ (`VISUAL_INDENT`) ควบกับการซ้อนลิสต์จริง
    ② ช่องสัญญาณในตารางให้สีแยกฝั่ง (ซื้อเขียว · กลางเหลือง · ขายแดง)
    ③ ช่องสัญญาณใช้คำสั้น "ซื้อ/ขาย/กลาง" ไม่เติมคำอื่น
    """

    def _แถวตาราง(self) -> list[str]:
        article = self.rendered["a_standard"]
        return [line for line in article.splitlines()
                if line.startswith("| ") and "---" not in line
                and not line.startswith("| อินดิเคเตอร์")]

    def test_ชั้นลึกของลิสต์มี_NBSP_นำเนื้อความ(self):
        nbsp = wcb_writers.VISUAL_INDENT
        article = self.rendered["a_standard"]
        # ลูกลำดับเลขของแนวรับ/แนวต้านและบันไดแผน — ทุกบรรทัดต้องเยื้อง 1 ชั้น
        ordered = [line for line in article.splitlines()
                   if re.match(r"^\s{0,8}\d{1,2}\.\s", line)]
        self.assertTrue(ordered, "บทต้องมีลูกลำดับเลขให้ตรวจ")
        for line in ordered:
            self.assertRegex(line, rf"^\s*\d{{1,2}}\. {nbsp}\S",
                             f"ลูกลำดับเลขไม่มี NBSP เยื้อง: {line!r}")
        # ระดับชั้นต้องไล่ตามลึก — หัวชั้น 0 ห้ามมี NBSP (ไม่ใช่เยื้องมั่วทุกบรรทัด)
        self.assertIn("\n- ไล่ปฏิทินที่รออยู่ตามลำดับเวลา\n", article)
        self.assertNotRegex(article, rf"\n- {nbsp}",
                            "หัวชั้นบนสุดต้องชิดซ้าย ไม่ใช่ติด NBSP ไปด้วย")

    def test_ช่องสัญญาณเป็นคำสั้นพร้อมจุดสี(self):
        แถว = self._แถวตาราง()
        self.assertTrue(แถว, "ตารางอินดิเคเตอร์ต้องมีแถวข้อมูล")
        อนุญาต = set(wcb_writers.TABLE_SIGNAL_THAI.values()) | {"—"}
        for line in แถว:
            ช่องสัญญาณ = line.strip().strip("|").split("|")[-1].strip()
            self.assertIn(ช่องสัญญาณ, อนุญาต,
                          f"ช่องสัญญาณนอกทะเบียนคำสั้น+สี: {line!r}")

    def test_คำยาวแบบเดิมไม่หลุดเข้าตาราง(self):
        for line in self._แถวตาราง():
            for คำยาว in ("ฝั่งซื้อ", "ฝั่งขาย", "เป็นกลาง", "ให้สัญญาณ"):
                self.assertNotIn(คำยาว, line,
                                 f"ตารางต้องใช้คำสั้น ซื้อ/ขาย/กลาง เท่านั้น: {line!r}")

    def test_สีครบสามฝั่งตามทะเบียน(self):
        """ทะเบียน `TABLE_SIGNAL_THAI` คือสัญญากับผู้ใช้ — ล็อกทั้งสีและคำทีละฝั่ง"""
        self.assertEqual(wcb_writers.TABLE_SIGNAL_THAI,
                         {"buy": "ซื้อ", "sell": "ขาย", "neutral": "กลาง"})

    def test_โหมดร้อยแก้วยังใช้คำเต็มอ่านเป็นประโยคได้(self):
        with สวิตช์bullet(True):                  # แฟ้มชั่วคราวไม่มีช่องตาราง = ปิด
            article = wcb_writers.render_a(self.evidence)
        self.assertIn("ให้สัญญาณ", article,
                      "ร้อยแก้วต้องยังรายงานสัญญาณด้วยคำเต็ม ไม่ใช่คำสั้นของตาราง")
        self.assertNotIn("🟢", article, "จุดสีเป็นของตารางเท่านั้น")


class สไตล์A_รอบรีวิว_08_11_ค่ำ_ชุดสี่(ฐานสายสาธารณะ):
    """🔒 คำสั่งผู้ใช้ 08-11 ค่ำ (ชุดสี่): ตัด "ต่อออนซ์" และ "(จุดหมุนกรอบรายวัน)"
    ออกจากหัวข้อแผน — พ่วงปิดบั๊กหน่วยผิดของ USD/THB ที่เจอตอนแก้
    """

    def test_รายการราคาใช้หน่วยรูปสั้นไม่ใช่หน่วยเต็ม(self):
        """🔄 08-11 ค่ำชุดสี่: ผู้ใช้สั่งตัด "ต่อออนซ์" ออกจากรายการแผน

        หน่วยเต็มยังต้องอยู่ในประโยคเปิดบท — ที่นั่นมันบอกข้อมูลจริง (และเป็นที่ที่
        NVDA ต้องประกาศว่าเป็นสัญญาส่วนต่าง) ส่วนในรายการมันแค่ซ้ำทุกบรรทัด
        """
        article = self.rendered["a_standard"]
        profile = wcb_source.profile_for(self.evidence["asset"])
        self.assertNotEqual(profile["unit_phrase"], profile["unit_short"],
                            "ชุดทดสอบนี้ต้องใช้สินทรัพย์ที่หน่วยเต็มยาวกว่ารูปสั้น")
        รายการ = [line for line in article.splitlines()
                  if re.match(r"^\s{0,8}\d{1,2}\.\s", line)]
        self.assertTrue(รายการ, "บทต้องมีรายการราคาให้ตรวจ")
        for line in รายการ:
            self.assertIn(profile["unit_short"], line, f"รายการไม่มีหน่วย: {line!r}")
            self.assertNotIn(profile["unit_phrase"], line,
                             f"รายการยังใช้หน่วยเต็ม: {line!r}")
        self.assertIn(profile["unit_phrase"], article,
                      "หน่วยเต็มต้องยังอยู่ในประโยคเปิดบท")

    def test_ทุกสินทรัพย์มีหน่วยรูปสั้นที่สอดคล้องกับหน่วยเต็ม(self):
        """🐞 บั๊กที่เจอ 08-11: จุดที่เขียน "ดอลลาร์" ตายตัวทำให้ USD/THB ผิดหน่วย

        (ราคากับส่วนต่างของคู่นี้เป็นบาท) ⇒ ทะเบียนต้องมีรูปสั้นครบทุกตัว และรูปสั้น
        ต้องเป็นคำขึ้นต้นของหน่วยเต็มเสมอ ไม่ใช่คำที่คิดขึ้นใหม่คนละสกุล
        """
        for asset, profile in wcb_source.ASSET_PROFILES.items():
            with self.subTest(asset=asset):
                self.assertIn("unit_short", profile, "ทะเบียนขาดหน่วยรูปสั้น")
                self.assertTrue(profile["unit_short"], "หน่วยรูปสั้นว่าง")
                self.assertTrue(profile["unit_phrase"].startswith(profile["unit_short"]),
                                "หน่วยรูปสั้นต้องเป็นคำขึ้นต้นของหน่วยเต็ม")

    def test_คู่เงินบาทรายงานหน่วยเป็นบาทไม่ใช่ดอลลาร์(self):
        """ตัวที่เปิดโปงบั๊ก — ล็อกไว้ตรง ๆ ไม่ผ่านทะเบียนอย่างเดียว"""
        self.assertEqual(wcb_source.ASSET_PROFILES["usdthb"]["unit_short"], "บาท")


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
                stale_phrase = ("เก่าเกินกว่าจะนำมาอธิบายการเคลื่อนไหวของวันนี้โดยตรง"
                                if writer["id"] == "a_standard" else
                                "ไม่ควรนำมาอธิบายการเคลื่อนไหวของวันนี้โดยตรง")
                self.assertIn(stale_phrase, article)
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

    def test_เลขแนวรับด่านแรกไม่ถูกพิมพ์ซ้ำในหัวข้อเดียวกัน(self):
        """🔄 **ผ่อนขอบเขตจาก "ทั้งบท" เป็น "ต่อหัวข้อ" เมื่อ 2026-08-11 — ตั้งใจ**

        เดิมห้าม B พิมพ์เลขแนวรับด่านแรกเกินหนึ่งย่อหน้า**ทั้งบท** · ใบตัวอย่างที่ผู้ใช้
        ส่งมา 08-11 พิมพ์เลขนั้นทั้งในหัวข้อ "ด่านราคาสำคัญ" และหัวข้อ "สรุปกลยุทธ์"
        โดยเจตนา (ใบตัวอย่าง B บรรทัด 46/68/70) — ซึ่งอ่านแล้วไม่ซ้ำซากเพราะอยู่คนละ
        หัวข้อและทำหน้าที่คนละอย่าง: ที่หนึ่งคือ "ด่านอยู่ตรงไหน" อีกที่คือ "แล้วยังไงต่อ"

        **บั๊กเดิมที่ยังต้องกันอยู่คือย่อหน้าซ้ำติด ๆ กันในหัวข้อเดียว** (2026-08-05)
        ⇒ ย้ายมาตรวจรายหัวข้อแทน · ย่อหน้าที่ซ้ำกันคำต่อคำยังถูกจับที่
        `test_ไม่มีย่อหน้าใดซ้ำกันสองที่ในบทเดียว` อีกชั้นหนึ่ง
        """
        below, _ = wcb_writers._sorted_levels(self.evidence)
        self.assertTrue(below, "fixture นี้ไม่มีแนวรับ เทสนี้จะไม่ได้ตรวจอะไรเลย")
        first = wcb_writers.price(below[0], self.evidence)
        _, body = split_frontmatter(self.rendered["b_technical"])
        for section in re.split(r"(?m)^## ", body)[1:]:
            head = section.splitlines()[0].strip()
            with self.subTest(section=head):
                blocks = [b for b in section.split("\n\n")
                          if first in b and "[[chart:" not in b]
                self.assertLessEqual(len(blocks), 1,
                                     f"หัวข้อ '{head}' พิมพ์แนวรับ {first} ซ้ำ {len(blocks)} ย่อหน้า")


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


class เพดานคลาดเคลื่อนของหมุดกราฟ(unittest.TestCase):
    """เพดานของด่านต้องกว้างพอกับการปัดเศษที่ชั้นนักเขียนทำจริง — ไม่กว้างกว่านั้น

    บั๊กจริงที่เจอในรอบผลิต 2026-08-11: SOL ตกด่าน `chart_line` ทั้งสามสไตล์ ⇒
    ไม่ได้วางลง `output/` เลยทั้งวัน · **ไม่ใช่ข้อมูลเสีย** แต่เป็นเลขสองตัวใน
    ระบบเราที่ไม่สอดคล้องกันเอง —

        `_distinct_lines()`   ปั้นค่าด้วย `f"{value:.{levels}f}"` (SOL = 1 ตำแหน่ง)
                              ⇒ ปัดแล้วคลาดได้ถึง **0.05**
        `_line_tolerance()`   ให้เพดาน `pivot × 0.05%` ⇒ ที่ราคา 74.66 ได้ **0.0373**

    pivot S2 = 74.66 ปัดขึ้นเป็น 74.7 คลาด 0.04 ⇒ เกินเพดานไป 0.003 (อีกสามค่า
    บังเอิญปัดลงเลยรอด) · เงื่อนไขทั่วไป: ชนเมื่อ `10^-levels ÷ 2 > ราคา × 0.0005`
    ⇒ **สินทรัพย์ที่ตั้งไว้ 1 ตำแหน่งและราคาต่ำกว่า ~100 จะสุ่มตกทุกครั้งที่ pivot ปัดขึ้น**

    ⚠️ เทสคู่นี้ต้องอ่านคู่กันเสมอ — ตัวแรกพิสูจน์ว่าด่านไม่ตีของที่ถูกต้อง
    ตัวที่สองพิสูจน์ว่า**ด่านไม่ได้ถูกผ่อน** ค่าที่คลาดเกินการปัดเศษยังตกเหมือนเดิม
    (ผู้ใช้เคาะทางนี้ 2026-08-11 บนเงื่อนไขว่าเป็นการทำให้สองชั้นพูดภาษาเดียวกัน
    ไม่ใช่การขยับเกณฑ์ให้ผลออกบ่อยขึ้น ซึ่งยังเป็นข้อห้ามอยู่)
    """

    # ค่าจริงของ SOL จากรอบผลิต 2026-08-11 — S2 = 74.66 คือตัวที่ทำให้ทั้งวันตกด่าน
    PIVOTS = {"p": 75.79, "r1": 76.25, "r2": 76.91, "r3": 77.84,
              "s1": 75.32, "s2": 74.66, "s3": 73.73}

    def _payload(self) -> dict:
        """ก้อน SOL ขนาดเท่าของจริง — ทาบ pivot ลงบนก้อนทองที่มีโครงครบอยู่แล้ว

        ไม่มี fixture ของ SOL ในรีโป และการสร้างใหม่ทั้งก้อนจะกลายเป็นการทดสอบ
        fixture ที่เราแต่งเอง ⇒ ยืมโครงของก้อนจริงมา เปลี่ยนเฉพาะสองอย่างที่
        ด่านนี้อ่าน คือชื่อสินทรัพย์กับค่า pivot

        **ราคาต้องย้ายมาสเกลเดียวกับ pivot ด้วย** — `_sorted_levels()` แยกแนวรับ
        แนวต้านด้วยราคาปัจจุบัน ถ้าทิ้งราคาทองไว้ที่สี่พัน pivot ทั้งเจ็ดจะตกฝั่ง
        "ใต้ราคา" หมด แล้วหมุดจะได้ 77.8/76.9 แทนที่จะเป็นคู่ที่เกิดปัญหาจริง
        """
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["asset"] = "solusd"
        payload["technicals"]["pivots"] = dict(self.PIVOTS)
        for frame in payload.get("technicalsByTf", {}).values():
            if isinstance(frame, dict) and "pivots" in frame:
                frame["pivots"] = dict(self.PIVOTS)
        payload["quote"].update({"price": 75.80, "prevClose": 75.45, "open": 75.50,
                                 "high": 76.10, "low": 75.20})
        return payload

    @staticmethod
    def _article(marker: str) -> str:
        return ("---\nasset: solusd\ntitle: ทดสอบ\nexcerpt: " + "ก" * 130 + "\n"
                "author_slug: x\n---\n\n## เทคนิคและระดับราคาสำคัญ\n\n"
                f"ข้อความ {marker}\n\n"
                "## ปัจจัยพื้นฐานที่ต้องดู\n\nข้อความ\n\n## กลยุทธ์วันนี้\n\nข้อความ\n")

    def _chart_line_findings(self, marker: str) -> list[dict]:
        report = wcb_copy_validator.validate(self._article(marker), self._payload())
        return [f for f in report["findings"] if f["rule"] == "chart_line"]

    def test_ค่าที่นักเขียนปั้นเองต้องผ่านด่านของตัวเองเสมอ(self):
        """หมุดที่ `_distinct_lines()` ปั้นออกมาจริง ต้องไม่ถูกด่านตีตกสักตัว

        เดินผ่านตัวปั้นจริง ไม่ใช่พิมพ์ค่าที่รู้คำตอบแล้วลงไปเอง — ผูกสองชั้นไว้
        ด้วยกันแบบนี้ ใครแก้ความละเอียดในทะเบียนแล้วลืมเพดาน เทสตกทันที
        """
        evidence = wcb_source.normalize(self._payload())
        # ขอแนวรับสามชั้นเพื่อให้ S2 = 74.66 (ตัวที่ทำให้ตกด่านจริง) อยู่ในหมุดแน่ ๆ
        # — ของจริงได้มันมาเพราะ pivot ไหลข้ามกรอบเวลา ซึ่งไม่ใช่ประเด็นของเทสนี้
        marker = wcb_writers.chart_marker(evidence, "1day", supports=3)
        self.assertIn("74.7", marker, "ค่าที่เคยทำให้ตกด่านต้องยังอยู่ในหมุด")
        self.assertEqual([], self._chart_line_findings(marker),
                         f"หมุดที่ระบบปั้นเอง {marker} ถูกด่านของตัวเองตีตก")

    def test_ค่าที่คลาดเกินการปัดเศษต้องยังตกด่าน_fail_closed(self):
        """กันการเข้าใจผิดว่า "ขยับเพดานแล้ว = ด่านหลวมลง"

        74.9 ไม่ใช่ผลของการปัด pivot ตัวใดเลย (ใกล้สุดคือ 75.32 ห่าง 0.42
        และ 74.66 ห่าง 0.24 — ทั้งคู่เกินครึ่งหลักที่ปัด 0.05 หลายเท่า)
        """
        findings = self._chart_line_findings("[[chart:1day|s=75.3,74.9]]")
        self.assertTrue(findings, "เส้นที่ไม่ได้มาจากการปัด pivot ต้องยังตกด่าน")
        self.assertIn("74.9", findings[0]["detail"])

    def test_เพดานไม่แคบกว่าครึ่งหลักที่ปัดและไม่กว้างเกินจำเป็น(self):
        """ผูกตัวเลขของเพดานไว้ตรง ๆ — กันการปรับค่าโดยไม่มีใครเห็น

        ทอง (`levels` 0) ปัดเป็นจำนวนเต็ม ⇒ ต้องได้อย่างน้อย 0.5
        SOL (`levels` 1) ปัดหนึ่งตำแหน่ง ⇒ ต้องได้อย่างน้อย 0.05
        และทองต้องไม่ถูกหั่นให้แคบลงกว่าเพดานเดิมที่ผ่านการตรวจมาแล้ว
        """
        self.assertGreaterEqual(wcb_copy_validator._line_tolerance(74.66, levels=1), 0.05)
        self.assertGreaterEqual(wcb_copy_validator._line_tolerance(4366.37, levels=0), 0.5)
        # ทองที่ระดับสี่พัน เปอร์เซ็นต์ (2.18) กว้างกว่าครึ่งหลัก (0.5) อยู่แล้ว
        # ⇒ การเพิ่มพื้นครั้งนี้ต้องไม่ไปเปลี่ยนพฤติกรรมของทองแม้แต่นิดเดียว
        self.assertEqual(wcb_copy_validator._line_tolerance(4366.37, levels=0),
                         wcb_copy_validator._line_tolerance(4366.37))

    def test_ก้อนที่ยังไม่ลงทะเบียนต้องตกด่าน_ไม่ใช่ระเบิดกลางสายท่อ(self):
        """เหตุผลเดียวกับที่ `normalize()` จงใจไม่เรียก `profile_for()`

        ด่านตรวจต้องคืนคำตัดสินได้เสมอ ก้อนของหัวข้อที่ยังไม่ลงทะเบียนต้องได้
        "ตกด่าน" ไม่ใช่ exception ที่ทำให้ทั้งรอบผลิตล้มโดยไม่รู้ว่าบทไหนผิด
        """
        payload = self._payload()
        payload["asset"] = "หัวข้อที่ยังไม่ลงทะเบียน"
        report = wcb_copy_validator.validate(self._article("[[chart:1day|s=75.3]]"), payload)
        self.assertIsInstance(report["findings"], list)


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
                expected = ("ยังไม่มีข่าวที่เกี่ยวข้องโดยตรงกับวันวิเคราะห์"
                            if writer["id"] == "a_standard" else
                            "ไม่ควรระบุสาเหตุของการเคลื่อนไหวจากข้อมูลที่ไม่มีแหล่งยืนยัน")
                self.assertIn(expected, article)

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
        # ค่าทดสอบเป็น ASCII เพราะรหัสจริงไปอยู่ใน query string ⇒ อักขระไทยใช้ไม่ได้
        # อยู่แล้วตั้งแต่ต้น (เดิมชุดทดสอบใช้คำไทย ซึ่งเป็นสภาพที่เกิดขึ้นจริงไม่ได้)
        os.environ[wcb_source.KEY_ENV] = "from-env-1234"
        self.assertEqual(wcb_source._resolve_key("direct-5678"), "direct-5678")
        self.assertEqual(wcb_source._resolve_key(), "from-env-1234")

    def test_อ่านรหัสจากไฟล์ในเครื่องได้และตัดช่องว่างท้าย(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "key.txt"
            path.write_text("key-in-file-9999\n", encoding="utf-8")
            os.environ[wcb_source.KEY_FILE_ENV] = str(path)
            self.assertEqual(wcb_source._resolve_key(), "key-in-file-9999")

    def test_ไฟล์รหัสที่มี_BOM_ต้องใช้งานได้(self):
        """กับดักของเครื่อง Windows — เกิดจริง 2026-08-06

        PowerShell 5.1 เขียน `Set-Content -Encoding utf8` แล้วได้ UTF-8 **พร้อม BOM**
        อักขระ `\\ufeff` กลายเป็นตัวแรกของรหัส แล้ว urllib โยน UnicodeEncodeError ลึก
        อยู่ใน http.client โดยไม่มีคำว่า "รหัส" ในข้อความเลย ⇒ ไล่จาก traceback ไม่เจอ
        """
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "key.txt"
            path.write_text("key-with-bom-42", encoding="utf-8-sig")  # utf-8-sig = ใส่ BOM
            self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"), "ชุดทดสอบไม่มี BOM")
            os.environ[wcb_source.KEY_FILE_ENV] = str(path)
            resolved = wcb_source._resolve_key()
            self.assertEqual(resolved, "key-with-bom-42")
            self.assertTrue(resolved.isascii(), "รหัสที่ได้ยังมีอักขระนอก ASCII")

    def test_รหัสที่มีอักขระใช้ใน_URL_ไม่ได้_ต้องโยนพร้อมบอกวิธีแก้(self):
        """ไม่กลืนเงียบ — ข้อความต้องพูดถึงรหัสและ BOM ไม่ใช่ปล่อยไปตายที่ชั้น http"""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "key.txt"
            path.write_text("รหัสภาษาไทยใช้ใน URL ไม่ได้", encoding="utf-8")
            os.environ[wcb_source.KEY_FILE_ENV] = str(path)
            with self.assertRaises(wcb_source.KeyMissing) as caught:
                wcb_source._resolve_key()
            self.assertIn("BOM", str(caught.exception))

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

    def test_ไม่มีรหัสหรือ_URL_ที่ประกอบรหัสอยู่ที่ใดในรีโปเลย(self):
        """กวาด**ทั้งรีโป** ไม่ใช่แค่ `tools/wcb_*.py`

        ตั้งแต่ 2026-08-06 ไฟล์รหัสถูกย้ายมาอยู่ที่ `.secrets/` ของโฟลเดอร์ P002
        (คำสั่งผู้ใช้) ซึ่งอยู่**นอก**รีโปนี้และนอกรีโป `output/` ⇒ git มองไม่เห็น
        แต่มันอยู่ใกล้รีโปกว่าเดิมมาก การเผลอคัดลอกไฟล์เข้ามาจึงง่ายขึ้น
        ⇒ ด่านเดิมที่ดูแค่สองไฟล์ไม่พออีกแล้ว ต้องกวาดทุกไฟล์ที่ commit ได้

        รหัสจริงยาว 32 ตัวอักษร คละพิมพ์ใหญ่-เล็ก-ตัวเลข ⇒ จับรูปนั้นเป็นหลัก
        """
        secret_shape = re.compile(r"[A-Za-z0-9]{28,64}")
        url_with_key = re.compile(r"[?&]k=[A-Za-z0-9_\-]{8,}")
        tracked = subprocess.run(["git", "ls-files"], cwd=_REPO_ROOT, capture_output=True,
                                 text=True, encoding="utf-8")
        self.assertEqual(0, tracked.returncode, "เรียก git ls-files ไม่สำเร็จ")
        files = [line for line in tracked.stdout.splitlines() if line.strip()]
        self.assertGreater(len(files), 20, "ไม่ได้รายชื่อไฟล์ในรีโป — ด่านนี้จะไม่ตรวจอะไรเลย")

        for name in files:
            path = _REPO_ROOT / name
            if not path.is_file() or path.suffix.lower() in {".png", ".jpg", ".ico", ".woff2"}:
                continue
            try:
                source = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            with self.subTest(file=name):
                # บรรทัดที่ประกอบ URL จากตัวแปรเป็นของถูกต้อง — จับเฉพาะค่าที่ฝังจริง
                self.assertIsNone(url_with_key.search(source),
                                  f"{name} มี URL ที่ฝังรหัสไว้ตายตัว")
                for literal in re.findall(r"[\"']([^\"'\s]{28,64})[\"']", source):
                    if not secret_shape.fullmatch(literal):
                        continue
                    mixed = (any(c.islower() for c in literal)
                             and any(c.isupper() for c in literal)
                             and any(c.isdigit() for c in literal))
                    self.assertFalse(mixed, f"{name} มีค่าที่หน้าตาเหมือนรหัส: {literal[:6]}…")

    def test_ไฟล์รหัสต้องอยู่นอกรีโปเสมอ(self):
        """ถ้าวันหนึ่งมีใครวางไฟล์รหัสไว้ในรีโป ด่านนี้ต้องดังก่อน push"""
        suspicious = [p for p in _REPO_ROOT.rglob("*")
                      if p.is_file() and ".git" not in p.parts
                      and re.search(r"(wcb[-_]?key|\.secrets|snapshot[-_]?key)", p.name, re.I)]
        self.assertEqual([], [str(p.relative_to(_REPO_ROOT)) for p in suspicious],
                         "พบไฟล์ที่หน้าตาเหมือนไฟล์รหัสอยู่ในรีโป — ต้องเก็บไว้นอกรีโปเท่านั้น")

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
            # ภาพซูมแนบ (08-10) ดึงแท่ง series ตอน publish — เทสต้องปิดทางเน็ต
            # ด้วย fixture เดียวกับที่ใช้ทั้งไฟล์ ไม่งั้นผลเทสขึ้นกับเน็ต ณ วินาทีรัน
            rows_420 = json.loads((_REPO_ROOT / "tests" / "fixtures" /
                                   "xau_420_sessions_2026-08-07.json")
                                  .read_text(encoding="utf-8"))
            real_indicator_renderer = chart_public_renderer.render_daily_indicator_lines

            def render_fixture_indicator(rows, evidence, output_path, **kwargs):
                # fixture แท่งจบ 7 ส.ค. แต่ snapshot ของเทสจบ 5 ส.ค. จึงทดสอบ layout
                # โดยปิดเฉพาะด่านปลายเส้น; ด่านนั้นมี unit test แยกที่ใช้ค่าตรง/ไม่ตรง
                kwargs["verify_endpoints"] = False
                return real_indicator_renderer(rows, evidence, output_path, **kwargs)

            with mock.patch.object(wcb_series_source, "fetch_asset_rows",
                                   return_value=({}, rows_420, "fixture")), \
                    mock.patch.object(wcb_series_source, "fetch_series_rows",
                                      return_value=({}, rows_420, "fixture-public")), \
                    mock.patch.object(chart_public_renderer,
                                      "render_daily_indicator_lines",
                                      side_effect=render_fixture_indicator):
                result = build_daily_package.build_public(
                    "xauusd", batch_id="t", output_root=root / "work",
                    publish_root=root / "out", snapshot_path=snapshot,
                    cutoff_at="2026-08-05T11:34:00+00:00", max_age_minutes=10 ** 9)

            self.assertTrue(result["content_ok"], "ร่างต้องผ่านด่านบทความครบทุกสไตล์")
            self.assertEqual(len(result["drafts"]), 3)
            drafts = root / "work" / "t" / "xauusd" / "internal" / "public-line" / "drafts"
            self.assertEqual(len(list(drafts.glob("*.md"))), 3, "ร่างต้องถูกเก็บไว้ให้ตรวจได้")

            self.assertIsNotNone(result["published"], "บทที่ผ่านด่านเนื้อหาต้องถึงคลังในเครื่อง")
            # 3 สไตล์ + ใบหมุดสำรอง**เฉพาะสไตล์ที่ยังเปิดธง `pin_fallback`** — ผู้ใช้
            # สั่งเลิกครบทั้ง A/B/C เมื่อ 08-11 บ่าย (ตอนนี้ = 0 ใบ) · นับจากทะเบียน
            # แทนเลขตายตัว เพื่อให้วันที่ธงถูกเปิดคืน เทสนี้ยังพูดความจริงเอง
            with_pin = sum(1 for item in wcb_writers.WCB_WRITERS
                           if item.get("pin_fallback", True))
            self.assertEqual(len(list((root / "out").rglob("*.md"))),
                             len(wcb_writers.WCB_WRITERS) + with_pin,
                             "จำนวนไฟล์บท+ใบหมุดไม่ตรงทะเบียน")
            # 🆕 08-11 (ผู้ใช้สั่ง): ใบหลักของแต่ละสไตล์คือ**ฉบับแนบภาพ** ไม่ใช่ใบหมุด
            # ⇒ ชื่อยุคก่อนหน้า (`-แนบภาพ.md`) ต้องไม่เหลืออยู่ในโฟลเดอร์สไตล์อีก
            self.assertEqual(list((root / "out").rglob("xauusd-แนบภาพ.md")), [])
            attach = list((root / "out").rglob("xauusd.md"))
            self.assertEqual(len(attach), 3)
            for variant in attach:
                self.assertNotIn("[[chart", variant.read_text(encoding="utf-8"),
                                 "ใบหลักต้องไม่เหลือหมุด — เว็บจะวาดกราฟซ้ำ")
            fallbacks = list((root / "out").rglob("xauusd-หมุดกราฟ.md"))
            no_pin = {item["folder"] for item in wcb_writers.WCB_WRITERS
                      if not item.get("pin_fallback", True)}
            self.assertEqual(len(fallbacks), len(wcb_writers.WCB_WRITERS) - len(no_pin),
                             "ใบหมุดต้องอยู่ครบเฉพาะสไตล์ที่ยังประกาศใช้")
            for pins in fallbacks:
                self.assertIn("[[chart", pins.read_text(encoding="utf-8"))
                self.assertNotIn(pins.parent.name, no_pin,
                                 "สไตล์ที่เลิกใช้ใบหมุดต้องไม่มีไฟล์นี้เหลืออยู่")
            # ภาพ D1 สร้างแยกตามสไตล์ (A = indicator, B/C = ซูมเดิม) และแต่ละสไตล์
            # ได้เท่าที่บทตัวเองอ้างถึงจริง (C ไม่มีหมุด 4 ชั่วโมง)
            daily = list((root / "out").rglob("xauusd-web-d1-*.webp"))
            h4 = list((root / "out").rglob("xauusd-web-4h-*.webp"))
            self.assertEqual(len(daily), 3, "ภาพซูมรายวันต้องอยู่ครบทั้งสามสไตล์")
            self.assertEqual(len(h4), 2, "ภาพราย 4 ชั่วโมงต้องมีเฉพาะสไตล์ที่มีหมุดของมัน")
            for image in daily + h4:
                folder = image.parent
                self.assertIn(f"({image.name})",
                              (folder / "xauusd.md").read_text(encoding="utf-8"),
                              f"{folder.name}: มีภาพที่บทไม่ได้อ้างถึง (ภาพกำพร้า)")

            # สถานะสิทธิ์ยังอยู่ในผลลัพธ์/รายงานภายใน แต่ไม่แนบไฟล์ป้ายลง output
            self.assertNotIn("clearance_notice", result["published"])
            self.assertEqual(
                result["published"]["cleared_for_publication"],
                result["clearance"] == license_gate.APPROVED_PUBLIC)

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

    def test_ใบสำรองหมุดของรอบก่อนต้องไม่สวมทับบทสดของรอบใหม่(self):
        """🐞 เกิดจริง 2026-08-11 เที่ยง — "ของเก่าสวมรุ่นเก่าของตัวเอง" ฉบับใบสำรอง

        `_attach_images` อ่านใบสำรอง (`-หมุดกราฟ.md`) เป็นต้นทางเมื่อมันมีอยู่
        (จำเป็น — กันอ่านฉบับแนบภาพวนกลับ) ⇒ ใบสำรอง**ของรอบก่อน**ที่ยังนอนอยู่
        ทำให้บทสดที่เพิ่งผ่านด่านถูกเขียนทับด้วยเนื้อทั้งใบของรอบเช้า (พ.ศ. เก่า
        slug เก่า หัวข้อเก่า) แล้วไหลตามไปถึงโฟลเดอร์ขึ้นเว็บโดยไม่มีด่านไหนฟ้อง
        ⇒ การเขียนใบสดที่ผ่านด่านต้องฆ่าใบสำรองทุกยุคของหัวข้อนั้นทันที
        """
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"
            cutoff = "2026-08-05T11:34:00+00:00"
            day = out / publish_layout.day_folder(cutoff)
            stale_text = "---\ntitle: บทรอบเช้า พ.ศ. 2569\n---\n\n# ของเก่า\n"
            for writer in wcb_writers.WCB_WRITERS:
                target = day / writer["folder"]
                target.mkdir(parents=True)
                (target / "xauusd-หมุดกราฟ.md").write_text(stale_text, encoding="utf-8")
                (target / "xauusd-แนบภาพ.md").write_text(stale_text, encoding="utf-8")
            published = publish_layout.publish_wcb_asset(
                asset="xauusd", evidence=self.evidence, snapshot=self.payload,
                publish_root=out, cutoff_at=cutoff)
            # ใบสำรองที่ *สด* เกิดใหม่ได้จาก `_attach_images` ของรอบนี้เอง — สิ่งที่ห้าม
            # คือ**เนื้อของรอบก่อน**โผล่ในไฟล์ใดก็ตามของหัวข้อนี้หลังรอบที่ผ่านด่าน
            for entry in published["writers"]:
                with self.subTest(style=entry["style"]):
                    self.assertEqual(entry["status"], "pass")
                    target = day / entry["folder"]
                    for name in ("xauusd.md", "xauusd-หมุดกราฟ.md", "xauusd-แนบภาพ.md"):
                        path = target / name
                        if path.exists():
                            self.assertNotIn(
                                "บทรอบเช้า", path.read_text(encoding="utf-8"),
                                f"{name} ยังถือเนื้อของรอบก่อน — ใบสำรองเก่าสวมทับบทสด")


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
        """EUR/USD ก้อน**ก่อน** ทีมเว็บแก้ E7 — ค่าที่เป็นราคาถูกปัดเป็นทศนิยมสองตำแหน่ง

        เขียนบทต่อได้ (ผู้ใช้สั่ง 2026-08-05) แต่ต้องรู้ตัวว่าก้อนนี้หยาบ
        `strict=True` ยังหยุดได้เหมือนเดิมสำหรับคนที่ต้องการพฤติกรรมนั้น

        **ก้อนนี้จงใจเก็บไว้แม้ E7 ปิดแล้ว** — มันคือหน้าตาของอาการตอนปลายทางถอยกลับ
        ซึ่งเกิดมาแล้วสองครั้งกับฟีดคริปโท (E6 → E8 ห่างกันวันเดียว)
        """
        flagged = wcb_source.ensure_resolution(self.evidence)
        self.assertTrue(flagged["coarse_prices"])
        self.assertIn("2 ตำแหน่ง", flagged["coarse_note"])
        with self.assertRaises(wcb_source.SnapshotTooCoarse):
            wcb_source.ensure_resolution(self.evidence, strict=True)

    def test_ก้อนที่ละเอียดพอต้องไม่ถูกติดธง(self):
        """กันธงใหม่กลายเป็นธงที่ขึ้นกับทุกอย่าง — ทองต้องสะอาด"""
        gold = wcb_source.normalize(json.loads(FIXTURE.read_text(encoding="utf-8")))
        self.assertFalse(wcb_source.ensure_resolution(gold)["coarse_prices"])
        wcb_source.ensure_resolution(gold, strict=True)  # ต้องไม่โยน

    def test_คู่เงินที่ได้ทศนิยมครบแล้วต้องไม่ถูกติดธง(self):
        """ก้อน EUR/USD จริงหลังทีมเว็บแก้ E7 (เก็บ 2026-08-06) — ห้ามติดธงอีก

        ก่อนแก้ ด่านนี้ใช้ค่าคงที่ 0.01 เป็นขั้นการปัด ⇒ EUR/USD จะติดธง
        `coarse_prices` **ตลอดกาล** ต่อให้ปลายทางส่งห้าตำแหน่งมาให้แล้ว
        เพราะตัวเลขที่ป้อนเข้าสูตรไม่ได้มาจากก้อน แต่มาจากสิ่งที่โค้ดเดาไว้
        """
        fixed = wcb_source.normalize(json.loads(
            (_REPO_ROOT / "tests" / "fixtures" / "wcb-snapshot-eurusd-e7-fixed.json")
            .read_text(encoding="utf-8")))
        checked = wcb_source.ensure_resolution(fixed)
        self.assertFalse(checked["coarse_prices"], checked.get("coarse_note"))
        self.assertAlmostEqual(checked["provider_step"], 1e-5)
        wcb_source.ensure_resolution(fixed, strict=True)  # ต้องไม่โยน

    def test_ขั้นการปัดต้องวัดจากก้อน_ไม่ใช่เชื่อทะเบียนอย่างเดียว(self):
        """ปลายทาง**ถอยกลับ**ได้ — ด่านต้องจับได้เองโดยไม่ต้องมีคนไปแก้ทะเบียน

        นี่คือเหตุผลทั้งหมดที่ `provider_step()` วัดทศนิยมจากค่าจริงในก้อน
        ถ้าเชื่อ `ASSET_PROFILES[...]["decimals"]` อย่างเดียว วันที่ปลายทางถอยกลับ
        ไปปัด 2 ตำแหน่ง ด่านจะเงียบสนิทและบทจะออกโดยมีเส้นค่าเฉลี่ยชนกัน
        """
        step, how = wcb_source.provider_step(self.evidence)
        self.assertAlmostEqual(step, 0.01)
        self.assertIn("ทะเบียน", how)
        gold = wcb_source.normalize(json.loads(FIXTURE.read_text(encoding="utf-8")))
        self.assertAlmostEqual(wcb_source.provider_step(gold)[0], 0.01)

    def test_ค่าประหลาดค่าเดียวต้องไม่ทำให้ก้อนหยาบดูละเอียด(self):
        """ค่าที่ผ่านการคำนวณด้วย float มาก่อน (0.1 + 0.2) มีทศนิยม 17 ตำแหน่งจริง ๆ

        ถ้า `provider_step()` ใช้ `max()` ค่าเดียวแบบนั้นจะกลบทั้งก้อนที่ปัดหยาบ
        แล้วด่านจะเงียบผิด ⇒ ต้องมีอย่างน้อยสองค่าที่ละเอียดถึงระดับนั้น
        """
        self.assertEqual(wcb_source._decimal_places(1.15), 2)
        self.assertEqual(wcb_source._decimal_places(1.15467), 5)
        self.assertEqual(wcb_source._decimal_places(4262.0), 0)
        self.assertGreater(wcb_source._decimal_places(0.1 + 0.2), 10)

        polluted = wcb_source.normalize(json.loads(
            (_REPO_ROOT / "tests" / "fixtures" / "wcb-snapshot-eurusd.json")
            .read_text(encoding="utf-8")))
        polluted["daily"]["indicators"]["SMA10"] = {"signal": "buy", "value": 0.1 + 0.2}
        self.assertAlmostEqual(wcb_source.provider_step(polluted)[0], 0.01)
        self.assertTrue(wcb_source.ensure_resolution(polluted)["coarse_prices"])

    def test_รายการผลกระทบสูงต้องได้ที่นั่งก่อนเสมอ(self):
        """บั๊กจริง 2026-08-06 — NFP ของวันรุ่งขึ้นไม่ขึ้นบทเลยแม้แต่สไตล์เดียว

        เพราะโควตาถูกตัดจากรายการทุกประเทศก่อน แล้วค่อยกรองเหลือสหรัฐทีหลัง
        ⇒ ออสเตรเลีย/จีนกินโควตาไปก่อน · **เพิ่มโควตาไม่ช่วย** limit 4/6/8 ได้ผลเท่ากัน
        """
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["calendar"] = {"events": [
            {"at": "2026-08-06 08:30", "country": "AUD", "impact": "High",
             "title": "ดุลการค้าออสเตรเลีย", "previous": "-3.0", "forecast": None, "actual": None},
            {"at": "2026-08-06 19:30", "country": "USD", "impact": "Medium",
             "title": "ตัวเลขกลางหนึ่ง", "previous": "1.8", "forecast": None, "actual": None},
            {"at": "2026-08-06 19:30", "country": "USD", "impact": "Medium",
             "title": "ตัวเลขกลางสอง", "previous": "2.1", "forecast": None, "actual": None},
            {"at": "2026-08-07 10:00", "country": "CNY", "impact": "High",
             "title": "การส่งออกจีน", "previous": "27", "forecast": None, "actual": None},
            {"at": "2026-08-07 19:30", "country": "USD", "impact": "High",
             "title": "Non Farm Payrolls", "previous": "57", "forecast": None, "actual": None},
        ]}
        evidence = wcb_source.normalize(payload)
        evidence["local_date"] = "2026-08-06"

        chosen = wcb_writers._calendar_events(evidence, 3)
        titles = [event["title"] for event in chosen]
        self.assertIn("Non Farm Payrolls", titles, "รายการผลกระทบสูงของสหรัฐต้องได้ที่นั่งก่อน")
        self.assertIn("ตัวเลขกลางหนึ่ง", titles,
                      "รายการที่ใกล้ที่สุดต้องมีที่นั่งจองเสมอ — บทเผยแพร่เช้าแล้วเงียบเรื่องคืนนี้ไม่ได้")
        self.assertEqual([event["country"] for event in chosen], ["USD"] * 3,
                         "ปฏิทินในบทต้องเป็นของสหรัฐเท่านั้น — ย่อหน้าสายส่งมหภาคอ่านได้เฉพาะฝั่งนั้น")
        # นำเสนอตามเวลาเสมอ เพราะบทเขียนว่า "ไล่ปฏิทินที่รออยู่ตามลำดับเวลา"
        self.assertEqual(titles, sorted(titles, key=lambda t: str(
            next(e["at"] for e in chosen if e["title"] == t))))
        self.assertEqual(titles[-1], "Non Farm Payrolls")

        # จำนวนที่ขึ้นบทต้องไม่เพิ่ม — เปลี่ยนแค่ว่าที่นั่งเท่าเดิมตกกับใคร
        self.assertEqual(len(wcb_writers._calendar_events(evidence, 2)), 2)
        for style, article in {w["id"]: w["render"](evidence)
                               for w in wcb_writers.WCB_WRITERS}.items():
            with self.subTest(style=style):
                self.assertIn("Non Farm Payrolls", article)
                self.assertNotIn("ออสเตรเลีย", article)

    def test_ค่าคาดการณ์ในปฏิทินขึ้นบทได้และรายการที่ไม่มีค่าต้องไม่เดาแทน(self):
        """E4 ปิด 2026-08-07 — ช่อง `forecast` มาถึงปลายทางของเราแล้วจริง

        ก่อนหน้านี้ค่ามาเป็น `null` ทุกรายการ บทจึงเขียนได้แค่ครั้งก่อน
        เทสนี้ล็อกสองเรื่องพร้อมกัน: **มีค่าต้องเขียน** และ
        **ไม่มีค่าห้ามเดาแทน** (ค่าที่หายกลับไป = ปลายทางถอยกลับ ต้องแจ้งทีมเว็บ)
        """
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["calendar"] = {"events": [
            {"at": "2026-08-07 19:30", "country": "USD", "impact": "High",
             "title": "Non Farm Payrolls", "previous": "57", "forecast": "80",
             "actual": None},
            {"at": "2026-08-07 21:00", "country": "USD", "impact": "Medium",
             "title": "รายการไม่มีค่าคาด", "previous": "1.8", "forecast": None,
             "actual": None},
            {"at": "2026-08-07 22:00", "country": "USD", "impact": "Medium",
             "title": "รายการมีแต่ค่าคาด", "previous": None, "forecast": "2.4",
             "actual": None},
        ]}
        evidence = wcb_source.normalize(payload)
        evidence["local_date"] = "2026-08-07"

        lines = wcb_writers._calendar_sentences(evidence, limit=3)
        joined = " | ".join(lines)
        self.assertIn("ครั้งก่อนอยู่ที่ 57 และรอบนี้ตลาดคาดไว้ที่ 80", joined)
        # ไม่มีค่าคาด = เขียนเท่าที่มี ประโยคยังสมบูรณ์ ห้ามเติมคำว่าคาดโดยไม่มีเลข
        no_forecast = next(l for l in lines if "รายการไม่มีค่าคาด" in l)
        self.assertIn("ครั้งก่อนอยู่ที่ 1.8", no_forecast)
        self.assertNotIn("คาดไว้", no_forecast)
        # มีแต่ค่าคาด ไม่มีครั้งก่อน = ยังเขียนได้ ไม่ต้องมีคู่ครบถึงจะพูดถึง
        only_forecast = next(l for l in lines if "รายการมีแต่ค่าคาด" in l)
        self.assertIn("รอบนี้ตลาดคาดไว้ที่ 2.4", only_forecast)
        self.assertNotIn("ครั้งก่อน", only_forecast)

        # เลขค่าคาดต้องผ่านด่านเลขชี้กลับหลักฐานของทุกสไตล์ (ไม่ใช่แค่ประโยคดิบ)
        for writer in wcb_writers.WCB_WRITERS:
            with self.subTest(style=writer["id"]):
                article = writer["render"](evidence)
                self.assertIn("ตลาดคาดไว้ที่ 80", article)
                report = wcb_copy_validator.validate(article, payload)
                unsupported = [f for f in report["findings"]
                               if f["rule"] == "number_unsupported"]
                self.assertEqual(unsupported, [],
                                 "ค่าคาดการณ์ต้องนับเป็นเลขที่มีต้นทางในก้อน snapshot")

    def test_คำกำกับค่าคาดการณ์ต้องพูดตามก้อนจริง_ไม่ขัดกับประโยคของตัวเอง(self):
        """บั๊กจริง 2026-08-07 — บท C ของ eurusd ขัดกันเองในย่อหน้าเดียว

        ย่อหน้าไล่ปฏิทินเขียนว่า *"ครั้งก่อนอยู่ที่ 57 และรอบนี้ตลาดคาดไว้ที่ 80"*
        แล้วปิดท้ายด้วย *"ทุกรายการในชุดนี้ยังไม่มีตัวเลขคาดการณ์ในระบบ"*
        เพราะคำกำกับถูกเขียนตายตัวไว้ตอน E4 ยังปิด (ตอนนั้นค่าเป็น `null` จริงทุกตัว)
        แล้วไม่ได้ถูกถอดตอน E4 ปิดและค่าคาดการณ์มาถึงในวันเดียวกัน

        ล็อกสามสภาพ — และสภาพที่สามสำคัญเท่าสองอันแรก เพราะค่าคาดการณ์
        **ถอยกลับไปเป็น `null` ได้** ประโยคเดิมต้องกลับมาเองโดยไม่ต้องแก้โค้ด
        """
        def article_with(forecasts):
            payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
            payload["calendar"] = {"events": [
                {"at": f"2026-08-07 {hour}:30", "country": "USD", "impact": "High",
                 "title": f"รายการที่ {i + 1}", "previous": f"{i + 1}.5",
                 "forecast": cast, "actual": None}
                for i, (hour, cast) in enumerate(zip(("19", "20", "21"), forecasts))]}
            evidence = wcb_source.normalize(payload)
            evidence["local_date"] = "2026-08-07"
            # ล็อกที่ **รหัสสไตล์** ไม่ใช่ถ้อยคำในบท — เดิมค้นด้วยประโยค
            # "ด่านถัดไปเรียงกันมาแบบนี้" แล้วพอสไตล์การเขียนเปลี่ยน (08-11)
            # `next()` โยน StopIteration ทั้งที่เรื่องที่เทสนี้ตรวจไม่ได้เปลี่ยนเลย
            writer = wcb_writers.by_id("c_event")
            return writer["render"](evidence), payload

        # 1) ค่าคาดการณ์มาครบ (สภาพหลัง E4 ปิด) — ห้ามมีคำกำกับเลย
        article, payload = article_with(("80", "4.2", "2.4"))
        self.assertIn("ตลาดคาดไว้ที่ 4.2", article)
        self.assertNotIn("ยังไม่มีตัวเลขคาดการณ์ในระบบ", article,
                         "มีค่าคาดการณ์อยู่ในย่อหน้าแล้ว จะปิดท้ายว่าไม่มีไม่ได้")
        self.assertEqual([f for f in wcb_copy_validator.validate(article, payload)["findings"]
                          if f["rule"] == "number_unsupported"], [])

        # 2) มาบางรายการ — ต้องบอกว่า "บาง" ไม่ใช่ "ทุก"
        article, _ = article_with(("80", "4.2", None))
        self.assertIn("บางรายการในชุดนี้ยังไม่มีตัวเลขคาดการณ์ในระบบ", article)
        self.assertNotIn("ทุกรายการในชุดนี้ยังไม่มีตัวเลขคาดการณ์", article)

        # 3) ถอยกลับเป็น null ทั้งชุด — ประโยคเดิมต้องกลับมาเอง
        article, _ = article_with((None, None, None))
        self.assertIn("ทุกรายการในชุดนี้ยังไม่มีตัวเลขคาดการณ์ในระบบ", article)
        self.assertIn("การเดาตัวเลขคาดการณ์ขึ้นมาเองคือการสร้างข้อมูลที่ไม่มีต้นทาง", article)

        # รายการแรกอยู่คนละย่อหน้า จึงต้องไม่ถูกนับรวมในคำกำกับ
        article, _ = article_with((None, "4.2", "2.4"))
        self.assertNotIn("ยังไม่มีตัวเลขคาดการณ์ในระบบ", article)

    def test_ช่องข่าวมหภาคต้องต่อท้ายข่าวปกติและยุบซ้ำ(self):
        """`macroNews` ขึ้นจริง 2026-08-06 — ช่องนี้คัดจากตัวขับมหภาค คนละเกณฑ์กับ `news`

        ลำดับสำคัญ: `news` ติดป้ายสินทรัพย์ตรง ๆ จึงเกี่ยวข้องกว่า
        **ห้ามสลับลำดับเพื่อให้บทมีข่าวเยอะขึ้น**
        """
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["news"] = [{"title": "ตรงป้าย", "slug": "a", "published_at": "2026-08-06"}]
        payload["macroNews"] = [
            {"title": "ตรงป้าย", "slug": "a", "published_at": "2026-08-06"},
            {"title": "ตัวขับมหภาค", "slug": "b", "published_at": "2026-08-06",
             "category": "macro", "url": "/thailand/news/b"},
        ]
        evidence = wcb_source.normalize(payload)
        self.assertEqual([item["title"] for item in evidence["headlines"]],
                         ["ตรงป้าย", "ตัวขับมหภาค"])
        self.assertEqual(evidence["headlines"][1]["url"], "/thailand/news/b")
        self.assertEqual(evidence["headlines"][0]["channel"], "news")
        self.assertEqual(evidence["headlines"][1]["channel"], "macro")

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

    # วลีที่พิสูจน์ว่าเลขแผนขึ้นบทจริง — A เปลี่ยนเป็นแผนตรงตั้งแต่ 08-11 ค่ำ
    # (`_a_plan_block`) ส่วน B/C ยังใช้ร้อยแก้วของ `plan_paragraphs` ตามเดิม
    วลีแผนของสไตล์ = {"a_standard": "**จุดตัดขาดทุน (Stop Loss):**",
                     "b_technical": "จุดตัดขาดทุน (Stop Loss) อยู่ที่",
                     "c_event": "จุดตัดขาดทุน (Stop Loss) อยู่ที่"}

    def test_ทั้งสามสไตล์เขียนหัวข้อแผนเมื่อแผนผ่านด่าน(self):
        for writer in wcb_writers.WCB_WRITERS:
            with self.subTest(writer=writer["id"]):
                with_plan = writer["render"](self.agreed, self.plan)
                without = writer["render"](self.agreed, None)
                วลี = self.วลีแผนของสไตล์[writer["id"]]
                self.assertIn(วลี, with_plan)
                if writer["id"] == "a_standard":
                    # A ไม่มีแผนระบบก็ยังให้แผน (บันไดรอเข้า) — สิ่งที่ต้องต่างคือ
                    # เลขของแผนระบบต้องไม่โผล่ในฉบับไม่มีแผน
                    self.assertNotIn(f"{float(self.plan['stop']['value']):,.2f}", without)
                else:
                    self.assertNotIn(วลี, without)
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
                    # A ใช้ป้ายแผนตรง (08-11 ค่ำ) · B/C ใช้ร้อยแก้วแผนเดิม —
                    # ทุกสไตล์ต้องเรียกชื่อเดียวกัน "จุดตัดขาดทุน (Stop Loss)" (ผู้ใช้เขียนคำใหม่ 08-14
                    # — กลับไปใช้คำก่อน 08-13 ทั้งระบบ ไม่ใช่เฉพาะสไตล์ D ที่ผู้ใช้ยกมา)
                    self.assertTrue("จุดตัดขาดทุน (Stop Loss) อยู่ที่" in text
                                    or "**จุดตัดขาดทุน (Stop Loss):**" in text,
                                    f"{path.parent.name} ไม่มีร่องรอยแผนในบท")
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


class ประโยคปฏิทินต้องจบในตัวเองและอ้างวันที่จริง(unittest.TestCase):
    """ทีมเว็บข้อ A-3 (2026-08-09) — สองอาการที่มาจากย่อหน้าปฏิทินเดียวกัน

    (1) **ประโยคขาดกลางคัน** — หลักฐานของจริงคือ
        `output/_ส่งหัวหน้า3/D-โครงสร้างกราฟ/xauusd.md` บรรทัด 46 ซึ่งจบย่อหน้าว่า
        *"…ต่อด้วย วันอังคารนี้เวลา 21:00 น. ยอดขายบ้านมือสอง ซึ่งจัดเป็นรายการผลกระทบสูง "*
        เกิดเมื่อค่า `previous`/`forecast` ถูกตัดทั้งคู่ตามกติกาหน่วยของ `calendar_feed`
        แล้วเหลือประโยคจบที่ส่วนขยาย · โผล่ชัดในสไตล์ D เพราะย่อหน้านั้นจบด้วยประโยค
        ปฏิทินตัวสุดท้ายพอดี ไม่มีวลี "(ที่มา: …)" ตามมาปิดเหมือน A/B/C

    (2) **คำเวลาสัมพัทธ์** — "คืนนี้"/"วันอังคารนี้" ผิดตั้งแต่วันรุ่งขึ้นเมื่อบทถูกอ่านย้อนหลัง
    """

    @staticmethod
    def _evidence(events):
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["calendar"] = {"events": events}
        evidence = wcb_source.normalize(payload)
        evidence["local_date"] = "2026-08-07"
        return evidence, payload

    def test_ค่าถูกตัดทั้งคู่แล้วประโยคต้องยังจบในตัวเอง(self):
        """เล่นซ้ำอาการของจริง: รายการผลกระทบสูงที่ไม่เหลือค่าให้เขียนเลย"""
        evidence, _ = self._evidence([
            {"at": "2026-08-11 21:00", "country": "USD", "impact": "High",
             "title": "ยอดขายบ้านมือสอง", "previous": None, "forecast": None, "actual": None},
        ])
        sentence = wcb_writers._calendar_sentences(evidence, limit=3)[0]
        self.assertTrue(sentence.endswith("จึงระบุได้แค่วันและเวลา"),
                        f"ประโยคค้างกลางอากาศอีกแล้ว: {sentence!r}")
        self.assertNotIn("ครั้งก่อนอยู่ที่", sentence, "ไม่มีค่าแล้วห้ามมีวลีที่รอค่า")
        self.assertNotIn("คาดไว้ที่", sentence)

    def test_ทุกสไตล์ต้องไม่จบย่อหน้าปฏิทินคาวลีขยาย(self):
        """ล็อกที่ปลายทางจริง ไม่ใช่แค่ประโยคดิบ — ผู้เรียกแต่ละสไตล์ต่อคำเชื่อมคนละคำ"""
        evidence, _ = self._evidence([
            {"at": "2026-08-07 19:30", "country": "USD", "impact": "High",
             "title": "การจ้างงานนอกภาคเกษตร", "previous": "57", "forecast": "80", "actual": None},
            {"at": "2026-08-11 21:00", "country": "USD", "impact": "High",
             "title": "ยอดขายบ้านมือสอง", "previous": None, "forecast": None, "actual": None},
        ])
        for writer in wcb_writers.WCB_WRITERS:
            with self.subTest(style=writer["id"]):
                article = writer["render"](evidence)
                self.assertNotIn("ผลกระทบสูง ต่อด้วย", article)
                for line in article.splitlines():
                    self.assertFalse(line.rstrip().endswith("ซึ่งจัดเป็นรายการผลกระทบสูง"),
                                     f"{writer['id']} จบย่อหน้าคาวลีขยาย: {line[-90:]!r}")

    def test_มีค่าครบต้องไม่มีคำกำกับว่าไม่มีค่า(self):
        evidence, _ = self._evidence([
            {"at": "2026-08-07 19:30", "country": "USD", "impact": "High",
             "title": "การจ้างงานนอกภาคเกษตร", "previous": "57", "forecast": "80", "actual": None},
        ])
        sentence = wcb_writers._calendar_sentences(evidence, limit=3)[0]
        self.assertIn("ครั้งก่อนอยู่ที่ 57 และรอบนี้ตลาดคาดไว้ที่ 80", sentence)
        self.assertNotIn("จึงระบุได้แค่วันและเวลา", sentence)

    def test_ขาดค่าบางช่องยังเขียนเท่าที่มีและไม่ใส่คำกำกับ(self):
        evidence, _ = self._evidence([
            {"at": "2026-08-07 19:30", "country": "USD", "impact": "Medium",
             "title": "มีแต่ครั้งก่อน", "previous": "1.8", "forecast": None, "actual": None},
            {"at": "2026-08-07 22:00", "country": "USD", "impact": "Medium",
             "title": "มีแต่ค่าคาด", "previous": None, "forecast": "2.4", "actual": None},
        ])
        lines = wcb_writers._calendar_sentences(evidence, limit=3)
        only_previous = next(l for l in lines if "มีแต่ครั้งก่อน" in l)
        only_forecast = next(l for l in lines if "มีแต่ค่าคาด" in l)
        self.assertTrue(only_previous.endswith("ครั้งก่อนอยู่ที่ 1.8"))
        self.assertTrue(only_forecast.endswith("รอบนี้ตลาดคาดไว้ที่ 2.4"))
        for line in (only_previous, only_forecast):
            self.assertNotIn("จึงระบุได้แค่วันและเวลา", line)

    def test_at_ที่อ่านไม่ออกต้องตัดทั้งวลีวันเวลา_ไม่พิมพ์โครงเปล่า(self):
        # `at` ที่ผ่านด่านคัดของ `upcoming()` ได้ (สตริงยาวพอและเรียงหลัง cutoff)
        # แต่ถอดเป็นวันที่/เวลาไม่ได้ — สภาพที่ปลายทางส่งรูปแบบใหม่ที่เรายังไม่รู้จัก
        evidence, _ = self._evidence([
            {"at": "2026-08-99", "country": "USD", "impact": "Medium",
             "title": "รายการไม่มีเวลา", "previous": "1.8", "forecast": None, "actual": None},
        ])
        sentence = wcb_writers._calendar_sentences(evidence, limit=3)[0]
        self.assertNotIn("เวลา  น.", sentence, "clock ว่างต้องตัดทั้งวลี ไม่ใช่พิมพ์โครงเปล่า")
        self.assertTrue(sentence.startswith("ช่วงถัดไป รายการไม่มีเวลา"), sentence)

    def test_ห้ามมีคำเวลาสัมพัทธ์เหลือในบททุกสไตล์(self):
        """บทค้างบนเว็บถาวร — คำพวกนี้ผิดตั้งแต่วันถัดไปที่มีคนเปิดอ่าน"""
        evidence, _ = self._evidence([
            {"at": "2026-08-07 19:30", "country": "USD", "impact": "High",
             "title": "การจ้างงานนอกภาคเกษตร", "previous": "57", "forecast": "80", "actual": None},
            {"at": "2026-08-08 19:30", "country": "USD", "impact": "High",
             "title": "ดัชนีราคาผู้ผลิต", "previous": "0.2", "forecast": "0.1", "actual": None},
            {"at": "2026-08-11 21:00", "country": "USD", "impact": "High",
             "title": "ยอดขายบ้านมือสอง", "previous": "4.09", "forecast": "4.07", "actual": None},
        ])
        for word in ("คืนนี้", "คืนพรุ่งนี้", "วันอังคารนี้", "วันอังคารถัดไป", "วันพุธถัดไป"):
            self.assertNotIn(word, " ".join(wcb_writers._calendar_sentences(evidence, limit=8)))
        for writer in wcb_writers.WCB_WRITERS:
            with self.subTest(style=writer["id"]):
                article = writer["render"](evidence)
                # ปฏิทินจัดกลุ่มตามวันตั้งแต่ 08-11 ⇒ วันกับเวลาอยู่คนละบรรทัด
                # เจตนาเดิมคงอยู่: ต้องมีวันที่แน่นอนและเวลาแน่นอน ไม่ใช่คำสัมพัทธ์
                self.assertIn("ศุกร์ 7 ส.ค.", article)
                self.assertIn("19:30 น.", article)
                self.assertIn("อังคาร 11 ส.ค.", article)
                for word in ("คืนนี้", "คืนพรุ่งนี้", "ถัดไปเวลา", "นี้เวลา"):
                    self.assertNotIn(word, article, f"{writer['id']} ยังมีคำเวลาสัมพัทธ์")

    def test_เลขวันที่ต้องมีต้นทางจริงในก้อน_ไม่ใช่การผ่อนด่าน(self):
        """หัวใจของข้อ (2): เขียนวันที่ได้ **โดยไม่แตะเกณฑ์ของด่านเลย**

        เลขวันที่คือวันของเดือนที่ถอดจากฟิลด์ `at` ของรายการนั้น และ
        `collect_evidence()` เดินสตริง `at` อยู่แล้ว ⇒ 7 กับ 11 อยู่ในกองหลักฐานจริง
        เทสนี้พิสูจน์ทั้งสองชั้น: กองหลักฐานมีเลขนั้น **และ** บททุกสไตล์ผ่านด่าน
        """
        evidence, payload = self._evidence([
            {"at": "2026-08-07 19:30", "country": "USD", "impact": "High",
             "title": "การจ้างงานนอกภาคเกษตร", "previous": "57", "forecast": "80", "actual": None},
            {"at": "2026-08-11 21:00", "country": "USD", "impact": "High",
             "title": "ยอดขายบ้านมือสอง", "previous": "4.09", "forecast": "4.07", "actual": None},
        ])
        pool = wcb_copy_validator.collect_evidence(payload)
        for day in (7.0, 11.0):
            self.assertIn(day, pool, "วันของเดือนต้องมาจากฟิลด์ `at` ในก้อนจริง")
        for writer in wcb_writers.WCB_WRITERS:
            with self.subTest(style=writer["id"]):
                report = wcb_copy_validator.validate(writer["render"](evidence), payload)
                self.assertEqual([f for f in report["findings"]
                                  if f["rule"] == "number_unsupported"], [],
                                 "วันที่ต้องผ่านด่านด้วยต้นทางจริง ไม่ใช่ด้วยข้อยกเว้น")

    def test_วันที่ที่ไม่มีต้นทางต้องยังตกด่านตามเดิม_fail_closed(self):
        """กันการเข้าใจผิดว่า "ด่านยอมเลขวันที่ทุกตัวแล้ว" — ด่านไม่ได้ถูกผ่อน"""
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        payload["calendar"] = {"events": []}
        pivot = sorted(wcb_source.pivot_values(wcb_source.normalize(payload)))[0]
        article = ("---\nasset: xauusd\ntitle: ทดสอบ\nexcerpt: " + "ก" * 130 + "\n"
                   "author_slug: x\n---\n\n## เทคนิคและระดับราคาสำคัญ\n\n"
                   "เลขที่ไม่มีต้นทางในก้อนนี้เลย 913257 หน่วย "
                   f"[[chart:1day|s={pivot}]]\n\n"
                   "## ปัจจัยพื้นฐานที่ต้องดู\n\nข้อความ\n\n## กลยุทธ์วันนี้\n\nข้อความ\n")
        report = wcb_copy_validator.validate(article, payload)
        self.assertTrue(any(f["rule"] == "number_unsupported" for f in report["findings"]))


class สไตล์การเขียนตามใบตัวอย่าง(unittest.TestCase):
    """ชั้นการนำเสนอที่ผู้ใช้สั่งปรับ 2026-08-11 (`01-CC/Input/ภาษาการเขียน/`)

    ล็อกไว้เพราะของพวกนี้ "หายแล้วบทยังอ่านได้" ⇒ ไม่มีอะไรเตือนเลยถ้าใครรีแฟกเตอร์
    แล้วเส้นคั่น/กล่อง/ตัวหนาหลุดหายไปทีละอย่าง
    """

    @classmethod
    def setUpClass(cls):
        payload = json.loads((FIXTURES / "wcb-snapshot-xauusd.json").read_text(encoding="utf-8"))
        cls.payload = payload
        evidence = wcb_source.normalize(payload)
        cls.articles = {w["id"]: w["render"](evidence) for w in wcb_writers.WCB_WRITERS}

    def test_ทุกสไตล์มีเส้นคั่นระหว่างหัวข้อ(self):
        for style, article in self.articles.items():
            with self.subTest(style=style):
                self.assertGreaterEqual(article.count("\n---\n"), 3,
                                        "ต้องมีเส้นคั่นอย่างน้อยหนึ่งเส้นต่อหัวข้อใหญ่")

    def test_ทุกสไตล์มีกล่องคำแนะนำอย่างน้อยหนึ่งกล่อง(self):
        for style, article in self.articles.items():
            with self.subTest(style=style):
                self.assertIn("\n> ", article)

    def test_ทุกสไตล์มีตัวหนาเน้นคำสำคัญ(self):
        for style, article in self.articles.items():
            with self.subTest(style=style):
                self.assertGreaterEqual(article.count("**"), 6)

    # ชื่อหัวข้อของแต่ละสไตล์ตามใบตัวอย่าง — คัดลอกจาก `01-CC/Input/ภาษาการเขียน/`
    # **เรียงตามลำดับที่ต้องปรากฏจริง** · A ตัวแรกมีท่อนท้ายเป็นคำตัดสินของวัน
    # ซึ่งเปลี่ยนตามข้อมูล ⇒ ล็อกเฉพาะส่วนคงที่ด้วย `startswith`
    หัวข้อตามใบตัวอย่าง = {
        "a_standard": ["ภาพรวมทางเทคนิค:",
                       "ปัจจัยข่าวและตัวเลขเศรษฐกิจที่ต้องจับตา",
                       "วางแผนและกลยุทธ์การเทรดวันนี้"],
        "b_technical": ["1. เจาะโครงสร้างราคา & เทคนิคอล (Multi-Timeframe)",
                        "2. ด่านราคาสำคัญที่ต้องจับตา",
                        "3. ปัจจัยข่าวและตารางเศรษฐกิจที่ต้องระวัง",
                        "4. สรุปกลยุทธ์การเทรดวันนี้"],
        "c_event": ["1. แนวรับ-แนวต้านสำคัญประจำวัน",
                    "2. ปฏิทินข่าวเศรษฐกิจและตารางประกาศตัวเลข",
                    "3. ฉากทัศน์ & แผนการเทรด (Trade Scenarios)"],
    }

    def test_ชื่อหัวข้อตรงใบตัวอย่างทั้งชุดและลำดับ(self):
        """🔄 **กลับด้านจากเทสเดิม 2026-08-11 ตามคำสั่งผู้ใช้**

        ของเดิมบังคับให้ทุกสไตล์ตั้งชื่อหัวข้อ**ขึ้นต้น**ด้วย เทคนิค/ปัจจัย/กลยุทธ์
        เพราะด่านจับด้วยคำนำหน้า ⇒ ชื่อในใบตัวอย่างสองในสามใบใช้ไม่ได้เลย
        ผู้ใช้ตีกลับ: ยึดใบตัวอย่างเป็นหลัก ด่านต้องขยับตาม (ดู `REQUIRED_HEADINGS`)

        เทียบ **ทั้งชุดและลำดับ** ไม่ใช่แค่ "มีคำนี้อยู่ที่ไหนสักที่" — ลำดับหัวข้อคือ
        โครงบท ถ้าสลับกันแล้วยังผ่าน เทสนี้ก็ไม่ได้ล็อกอะไร
        """
        for style, article in self.articles.items():
            with self.subTest(style=style):
                heads = [line[3:].strip() for line in article.splitlines()
                         if line.startswith("## ")]
                want = self.หัวข้อตามใบตัวอย่าง[style]
                self.assertEqual(len(heads), len(want), f"จำนวนหัวข้อไม่ตรง — {heads}")
                for actual, expected in zip(heads, want):
                    self.assertTrue(actual.startswith(expected),
                                    f"หัวข้อ {actual!r} ไม่ตรงใบตัวอย่าง {expected!r}")

    def test_สไตล์B_มีหัวข้อย่อยสามชั้นตามใบตัวอย่าง(self):
        """หัวข้อย่อยเป็นตัวแยกสไตล์ B ออกจาก A/C — ใบตัวอย่างมีสามอัน

        ⚠️ ไม่บังคับ "ต้องมีครบทุกรอบ" เพราะหัวข้อย่อยผูกกับเนื้อที่มีจริง
        (กติกาแกน: evidence ไม่พอ = ตัดเงียบ ไม่มีหัวข้อว่าง) — สิ่งที่ล็อกคือ
        **หัวข้อย่อยที่โผล่ต้องเป็นชื่อในทะเบียนนี้เท่านั้น และ B ต้องมีอย่างน้อยสองอัน**
        """
        allowed = ("### โครงสร้างแท่งเทียน (Price Structure)",
                   "### สัญญาณอินดิเคเตอร์:",
                   "### จุดหมุนราคา (Pivot Points) ของแต่ละกรอบ")
        subheads = [line.strip() for line in self.articles["b_technical"].splitlines()
                    if line.startswith("### ")]
        self.assertGreaterEqual(len(subheads), 2, subheads)
        for head in subheads:
            self.assertTrue(head.startswith(allowed), f"หัวข้อย่อยนอกทะเบียน: {head!r}")
        for style in ("a_standard", "c_event"):
            self.assertNotIn("\n### ", self.articles[style],
                             f"{style} ไม่มีหัวข้อย่อยในใบตัวอย่าง")

    def test_ปฏิทินจัดกลุ่มตามวันและเวลาเป็นตัวหนา(self):
        """🔄 08-11 ค่ำ: ผู้ใช้สั่งเยื้องเพิ่มหนึ่งชั้นจากภาพหน้าเว็บจริง —
        ประโยคนำกลายเป็น bullet แม่ · หัววันเยื้อง 1 ชั้น · เวลาเยื้อง 2 ชั้น

        🔄 ชุดสาม: ภาพหน้าเว็บรอบสองยืนยันว่า CSS ปลายทางตัด padding ลิสต์ซ้อน
        ⇒ แต่ละชั้นต้องมี NBSP นำเนื้อความด้วย (`VISUAL_INDENT` ชั้นละ 4 ตัว)
        ไม่งั้นตาเห็นชิดซ้ายเหมือนเดิมทั้งที่โครงซ้อนถูก"""
        article = self.articles["a_standard"]
        nbsp = wcb_writers.VISUAL_INDENT
        self.assertIn("\n- ไล่ปฏิทินที่รออยู่ตามลำดับเวลา\n", article)
        self.assertRegex(article, rf"\n  - {nbsp}\*\*(จันทร์|อังคาร|พุธ|พฤหัสบดี|ศุกร์|เสาร์|อาทิตย์) \d+")
        self.assertRegex(article, rf"\n    - {nbsp}{nbsp}\*\*\d{{2}}:\d{{2}} น\.\*\*")
        # ชั้นเดิม (หัววันชิดซ้าย) ต้องไม่เหลือ — กันรีแฟกเตอร์ที่เยื้องบางกลุ่มไม่ครบ
        self.assertNotRegex(article, r"\n- \*\*(จันทร์|อังคาร|พุธ|พฤหัสบดี|ศุกร์|เสาร์|อาทิตย์) ")

    def test_บทยังผ่านด่านของตัวเองทุกสไตล์(self):
        """เปลี่ยนหน้าตาแล้วต้องไม่ทำให้ด่านเลข/ด่านโครงตกแม้แต่สไตล์เดียว"""
        for style, article in self.articles.items():
            with self.subTest(style=style):
                report = wcb_copy_validator.validate(article, self.payload)
                fatal = [f for f in report["findings"] if f["severity"] == "fatal"]
                self.assertEqual(fatal, [], msg=str(fatal))


class ผู้เขียนแยกตามสินทรัพย์(unittest.TestCase):
    """คำสั่งผู้ใช้ 2026-08-11 — ทองเป็นคนเขียนจริง สินทรัพย์อื่นเป็นทีม

    ล็อกไว้เพราะกฎนี้มองไม่เห็นจากหน้าบท (อยู่ใน frontmatter) ⇒ ถ้าเพี้ยนจะเงียบ
    จนกว่าจะมีคนเปิดหน้าเว็บแล้วเห็นกล่องผู้เขียนผิดคน
    """

    def test_ทองใช้คนเขียนจริง(self):
        self.assertEqual(wcb_writers.author_slug_for("xauusd"), "natthaphon-s")

    def test_สินทรัพย์อื่นใช้ทีมทั้งหมด(self):
        """ครอบทุกตัวในทะเบียน — เพิ่มสินทรัพย์ใหม่แล้วลืมคิดเรื่องผู้เขียนจะตกที่นี่"""
        for asset in wcb_source.ASSET_PROFILES:
            if asset == "xauusd":
                continue
            with self.subTest(asset=asset):
                self.assertEqual(wcb_writers.author_slug_for(asset),
                                 "world-class-broker-team")

    def test_สินทรัพย์ที่ยังไม่มีในทะเบียนก็ต้องได้ทีมไม่ใช่พัง(self):
        """fail-safe: ค่าตั้งต้นต้องเป็นทีม ไม่ใช่ยกเครดิตให้คนเขียนจริงโดยบังเอิญ"""
        self.assertEqual(wcb_writers.author_slug_for("xagusd"),
                         "world-class-broker-team")


class ห้ามมีบรรทัดชื่อผู้เขียนในเนื้อบท(unittest.TestCase):
    """คำสั่งผู้ใช้ 2026-08-11 + สเปกไฟล์ของทีมเว็บ ("⛔ ห้ามใส่บรรทัดชื่อผู้เขียน")

    หน้าเว็บมีกล่องผู้เขียนของตัวเองที่อ่านจาก `author_slug` ⇒ เขียนชื่อในเนื้อบทอีกที
    จะกลายเป็นชื่อซ้ำสองที่บนหน้าเดียว
    """

    def test_ทุกสไตล์ของสาย_ABC_ไม่มี_byline(self):
        payload = json.loads((FIXTURES / "wcb-snapshot-xauusd.json").read_text(encoding="utf-8"))
        evidence = wcb_source.normalize(payload)
        for writer in wcb_writers.WCB_WRITERS:
            with self.subTest(style=writer["id"]):
                self.assertNotIn("*โดย ", writer["render"](evidence))

    def test_frontmatter_ยังมี_author_slug_ครบ(self):
        """ตัดชื่อออกจากเนื้อได้ แต่ห้ามตัดช่องที่เว็บใช้เปิดกล่องผู้เขียน"""
        payload = json.loads((FIXTURES / "wcb-snapshot-xauusd.json").read_text(encoding="utf-8"))
        evidence = wcb_source.normalize(payload)
        for writer in wcb_writers.WCB_WRITERS:
            with self.subTest(style=writer["id"]):
                self.assertIn("author_slug: natthaphon-s", writer["render"](evidence))


class ด่านเดียวกันต้องเห็นหลักฐานกองเดียวกัน(ฐานสายสาธารณะ):
    """🐞 เกิดจริง 2026-08-13 — สไตล์ C ของทองหายทั้งใบทั้งที่รอบผลิตรายงานว่าผ่าน

    `wcb_copy_validator.validate()` ถูกเรียกสองครั้งต่อรอบ: ชั้นร่างใน
    `build_daily_package.build_public` (พ่วง `calendar_feed=`) และชั้นวางไฟล์ใน
    `publish_layout.publish_wcb_asset` (เดิม**ไม่พ่วง**) ⇒ เลขที่มาจากฟีดปฏิทิน
    ซึ่งเป็นคนละ endpoint จาก snapshot ตก `number_unsupported` เฉพาะชั้นหลัง
    แล้วบทถูก fail-closed ทิ้งเงียบ · จอพิมพ์ `ผ่านครบสามสไตล์` + `✓ C` + exit 0

    ของจริงที่ตกคือเลข `26` ในบรรทัด "พุธ 26 ส.ค." (วันของรายการ PCE จากฟีด)
    วันก่อนหน้ารอดเพราะเลขวันที่บังเอิญมีอยู่ใน snapshot ด้วย ⇒ **สุ่มตกตาม
    ปฏิทินของแต่ละวัน** ไม่ใช่ผิดตายตัวที่จับได้ตั้งแต่รอบแรก
    """

    FEED_ONLY_NUMBER = "913257"

    def เตรียมหลักฐานที่ปฏิทินมาจากฟีด(self):
        """คืนคู่ (evidence, ก้อนดิบของฟีด) ที่มีเลขซึ่ง **ไม่มีใน snapshot เลย**

        ยืนยันแล้วว่า `913257` ไม่ปรากฏใน fixture — เลขนี้จึงมีต้นทางเดียวคือฟีด
        เหมือนเลขวันที่ของรายการปฏิทินในของจริง
        """
        raw = {"events": [{
            "id": "pce-test", "title_th": "ดัชนีราคา PCE พื้นฐาน", "title_en": "Core PCE",
            "country": "USD", "impact": "High", "at_th": "2026-08-05 19:30",
            "previous": {"raw": self.FEED_ONLY_NUMBER, "value": 913257, "unit": "K",
                         "unit_th": "พันตำแหน่ง", "kind": "count", "unit_source": "dict"},
            "forecast": None, "actual": None}]}
        self.assertNotIn(self.FEED_ONLY_NUMBER, json.dumps(self.payload),
                         "เลขที่ใช้พิสูจน์ดันมีอยู่ใน snapshot — เทสนี้จะพิสูจน์อะไรไม่ได้เลย")
        evidence = dict(self.evidence)
        evidence["calendar"] = calendar_feed.to_calendar_events(raw)
        self.assertIn(self.FEED_ONLY_NUMBER,
                      wcb_writers.by_id("c_event")["render"](evidence, None),
                      "บท C ไม่ได้พูดเลขจากฟีด — ข้อมูลตั้งต้นของเทสไม่ตรงกับของจริง")
        return evidence, raw

    def หา(self, published, writer_id):
        return next(item for item in published["writers"] if item["writer_id"] == writer_id)

    def test_ชั้นวางไฟล์ไม่รับก้อนดิบของฟีด_บทที่อ้างเลขจากปฏิทินต้องหาย(self):
        """พิสูจน์ขาแรก — ถ้าไม่พ่วง ของจริงพังแบบไหน (กันเข้าใจผิดว่าไม่ต้องพ่วงก็ได้)"""
        evidence, _ = self.เตรียมหลักฐานที่ปฏิทินมาจากฟีด()
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"
            published = publish_layout.publish_wcb_asset(
                asset="xauusd", evidence=evidence, snapshot=self.payload,
                publish_root=out, cutoff_at="2026-08-05T11:34:00+00:00")
            entry = self.หา(published, "c_event")
            self.assertEqual(entry["status"], "fail")
            self.assertTrue(
                any(finding["rule"] == "number_unsupported"
                    and self.FEED_ONLY_NUMBER in (finding.get("detail") or "")
                    for finding in entry["findings"]),
                "ตกด้วยเหตุอื่น — เทสไม่ได้จับกับดักที่ตั้งใจจับ")
            self.assertFalse((out / publish_layout.day_folder("2026-08-05T11:34:00+00:00")
                              / entry["folder"] / "xauusd.md").exists())

    def test_ชั้นวางไฟล์รับก้อนดิบของฟีดแล้วบทเดิมต้องผ่านและมีไฟล์จริง(self):
        """พิสูจน์ขาสอง — พ่วงแล้วผ่าน **ไม่ใช่การผ่อนด่าน**

        เลขยังต้องชี้กลับต้นทางจริงได้เหมือนเดิมทุกประการ เปลี่ยนแค่ว่ากองหลักฐาน
        ที่ชั้นนี้เดินอยู่ครบเท่าที่ชั้นร่างเห็น — เลขที่ไม่มีต้นทางยังตกเหมือนเดิม
        (ล็อกไว้ด้วย `test_เลขมั่วยังตกเหมือนเดิมแม้พ่วงก้อนดิบของฟีด`)
        """
        evidence, raw = self.เตรียมหลักฐานที่ปฏิทินมาจากฟีด()
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"
            published = publish_layout.publish_wcb_asset(
                asset="xauusd", evidence=evidence, snapshot=self.payload,
                publish_root=out, cutoff_at="2026-08-05T11:34:00+00:00",
                calendar_feed=raw)
            entry = self.หา(published, "c_event")
            self.assertEqual(entry["status"], "pass", entry["findings"])
            self.assertFalse([finding for finding in entry["findings"]
                              if finding["rule"] == "number_unsupported"])
            self.assertTrue(Path(entry["article"]).is_file())

    def test_เลขมั่วยังตกเหมือนเดิมแม้พ่วงก้อนดิบของฟีด(self):
        """fail-closed ต้องไม่หลวมลง — เลขที่ไม่มีต้นทางทั้งใน snapshot และในฟีดต้องตก"""
        evidence, raw = self.เตรียมหลักฐานที่ปฏิทินมาจากฟีด()
        โกง = dict(evidence)
        โกง["calendar"] = [dict(evidence["calendar"][0],
                                previous="482913 พันตำแหน่ง")]
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"
            published = publish_layout.publish_wcb_asset(
                asset="xauusd", evidence=โกง, snapshot=self.payload,
                publish_root=out, cutoff_at="2026-08-05T11:34:00+00:00",
                calendar_feed=raw)
            entry = self.หา(published, "c_event")
            self.assertEqual(entry["status"], "fail",
                             "เลขที่ไม่มีต้นทางเล็ดลอดได้ = ด่านหลวมลงจริง")

    def test_build_public_ต้องส่งก้อนดิบของฟีดต่อให้ชั้นวางไฟล์(self):
        """ล็อกสายไฟเส้นที่ขาด — พ่วงที่ชั้นร่างอย่างเดียวไม่พอ ต้องส่งต่อด้วย"""
        raw = {"events": []}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            snapshot = root / "snap.json"
            snapshot.write_text(json.dumps(self.payload, ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(build_daily_package.publish_layout, "publish_wcb_asset",
                                   wraps=publish_layout.publish_wcb_asset) as spy:
                build_daily_package.build_public(
                    "xauusd", batch_id="t", output_root=root / "work",
                    publish_root=root / "out", snapshot_path=snapshot,
                    cutoff_at="2026-08-05T11:34:00+00:00", max_age_minutes=10 ** 9,
                    calendar_feed_fetcher=lambda _asset: raw)
            self.assertEqual(spy.call_args.kwargs.get("calendar_feed"), raw,
                             "ชั้นร่างเห็นก้อนดิบของฟีดแต่ชั้นวางไฟล์ไม่เห็น — บั๊กเดิมกลับมาแล้ว")


class สไตล์ที่หายหลังชั้นร่างว่าผ่านต้องฟ้องดัง(ฐานสายสาธารณะ):
    """② ของทางแก้ที่ผู้ใช้เคาะ 2026-08-13 — กันอาการ "จอบอกผ่าน แต่ไฟล์ไม่เกิด" ทั้งตระกูล

    ไม่ได้ผูกกับเรื่องปฏิทินเรื่องเดียว: `style_word_floor` ก็มีเฉพาะชั้นวางไฟล์
    เหมือนกัน ⇒ สไตล์ B ที่ได้ 820 คำจะตกที่ชั้นนั้นที่เดียวโดยชั้นร่างว่าผ่าน
    ด่านนี้จับทุกเหตุที่ทำให้สองชั้นไม่ตรงกัน ไม่ใช่แค่เหตุที่รู้จักแล้ว
    """

    def บังคับให้สไตล์สุดท้ายตกที่ชั้นวางไฟล์(self):
        """ปล่อยให้ด่านจริงทำงานทุกใบ แล้วพลิกผลของใบสุดท้าย **เฉพาะที่ชั้นวางไฟล์**

        ⚠️ ต้องสวมที่ชื่อ `publish_layout.wcb_copy_validator` (ตัวอ้างถึงโมดูล)
        ไม่ใช่ `.validate` ข้างใน — สองชั้นถือโมดูลก้อนเดียวกัน สวมที่ตัวฟังก์ชัน
        จะโดนชั้นร่างไปด้วย แล้ว `content_ok` กลายเป็นเท็จ ⇒ เทสไม่ได้ทดสอบ
        "สองชั้นไม่ตรงกัน" อีกต่อไป (พลาดมาแล้วตอนเขียนเทสนี้)

        ใช้ลำดับการเรียกแทนการดูเนื้อบท เพราะ `publish_wcb_asset` เดิน
        `WCB_WRITERS` ตามลำดับตายตัว — ผูกกับลำดับจึงแน่นอนกว่าผูกกับข้อความ
        """
        จริง = wcb_copy_validator.validate
        ลำดับ = {"n": 0}

        def ปลอม(*args, **kwargs):
            ลำดับ["n"] += 1
            result = จริง(*args, **kwargs)
            if ลำดับ["n"] == len(wcb_writers.WCB_WRITERS):
                result = dict(result, status="fail", fatal_count=result["fatal_count"] + 1,
                              findings=[*result["findings"],
                                        {"rule": "number_unsupported", "severity": "fatal",
                                         "line": 46, "detail": "บังคับให้ตกในเทส"}])
            return result

        return mock.patch.object(publish_layout, "wcb_copy_validator",
                                 types.SimpleNamespace(validate=ปลอม))

    def test_build_public_ต้องรายงานสไตล์ที่หายไว้ใน_silent_drops(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            snapshot = root / "snap.json"
            snapshot.write_text(json.dumps(self.payload, ensure_ascii=False), encoding="utf-8")
            with self.บังคับให้สไตล์สุดท้ายตกที่ชั้นวางไฟล์():
                result = build_daily_package.build_public(
                    "xauusd", batch_id="t", output_root=root / "work",
                    publish_root=root / "out", snapshot_path=snapshot,
                    cutoff_at="2026-08-05T11:34:00+00:00", max_age_minutes=10 ** 9)
            # ชั้นร่างว่าผ่านครบ (ด่านจริงไม่ถูกแตะ) แต่ชั้นวางไฟล์ตีตกใบสุดท้าย
            self.assertTrue(result["content_ok"])
            drops = result["published"]["silent_drops"]
            self.assertEqual([item["writer_id"] for item in drops],
                             [wcb_writers.WCB_WRITERS[-1]["id"]])
            self.assertTrue(drops[0]["findings"], "ต้องแนบเหตุผลไปด้วย ไม่ใช่บอกแค่ว่าหาย")

    def test_รอบที่มีสไตล์หายต้องไม่จบด้วย_exit_0_และต้องบอกว่าไฟล์ไม่เกิด(self):
        """exit 0 ทั้งที่ผลออกไม่ครบ = ตารางเวลาและสคริปต์เข้าใจว่าเรียบร้อย"""
        drop = {"writer_id": "c_event", "style": "C — อิงเหตุการณ์",
                "folder": "C-อิงเหตุการณ์", "word_count": 1222,
                "findings": [{"rule": "number_unsupported", "severity": "fatal",
                              "line": 46, "detail": '"26" ไม่มีอยู่ใน snapshot'}]}
        canned = {
            "asset": "xauusd", "line": build_daily_package.LINE_PUBLIC, "status": "built",
            "content_ok": True, "clearance": "approved-internal-only",
            "license_reasons": [], "directory": "d",
            "drafts": {"c_event": {"style": "C — อิงเหตุการณ์",
                                   "validation": {"status": "pass", "word_count": 1222,
                                                  "chart_markers": 1, "findings": []}}},
            "published": {"directory": "out", "cleared_for_publication": False,
                          "web_images": {"status": "ready", "images": []},
                          "silent_drops": [drop]},
            "trade_plan_public": {"included": False, "reason": "no_trade",
                                  "bias": None, "rr_first_target": None},
        }
        args = argparse.Namespace(asset=["xauusd"], batch_id="t", output_root=Path("w"),
                                  publish_root=Path("o"), no_publish=False, snapshot=None,
                                  calendar_feed=True)
        buffer = io.StringIO()
        with mock.patch.object(build_daily_package, "build_public", return_value=canned), \
                contextlib.redirect_stdout(buffer):
            code = build_daily_package.run_public_line(args, "2026-08-05T11:34:00+00:00")
        printed = buffer.getvalue()
        self.assertEqual(code, 1, "สไตล์หายแล้วยังจบด้วย exit 0 — ไม่มีใครรู้ว่าผลออกไม่ครบ")
        self.assertIn("C-อิงเหตุการณ์/", printed)
        self.assertIn("ไม่มีไฟล์ใน", printed)
        self.assertNotIn("ผ่านครบสามสไตล์", printed)
        self.assertIn("✗ C — อิงเหตุการณ์", printed,
                      "จอยังติ๊กถูกให้สไตล์ที่ไฟล์ไม่เกิด")


if __name__ == "__main__":
    unittest.main()
