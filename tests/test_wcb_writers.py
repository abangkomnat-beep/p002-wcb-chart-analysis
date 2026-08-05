"""ด่านของสายสาธารณะ A/B/C — กฎที่พังแล้วบทความหลุดออกไปโดยไม่มีใครเห็น

เทสสำคัญที่สุดในไฟล์นี้คือ `test_เลขทุกตัวในบทความชี้กลับ_snapshot_ได้`
เพราะมันคือกฎเดียวที่กันความผิดพลาดที่เกิดขึ้นจริงเมื่อ 2026-08-05 — บทความชุดแรก
มีตัวเลขที่ไม่มีต้นทางใน snapshot ปนอยู่ห้าตัว และไม่มีใครจับได้จนกว่าจะมีด่านนี้
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools import wcb_source, wcb_writers  # noqa: E402


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
        age = wcb_source.age_minutes(evidence)
        self.assertGreater(age, wcb_source.MAX_AGE_MINUTES)

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


if __name__ == "__main__":
    unittest.main()
