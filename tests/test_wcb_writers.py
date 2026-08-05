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
            drafts = root / "work" / "t" / "xauusd" / "internal" / "drafts"
            self.assertEqual(len(list(drafts.glob("*.md"))), 3, "ร่างต้องถูกเก็บไว้ให้ตรวจได้")

            self.assertIsNotNone(result["published"], "บทที่ผ่านด่านเนื้อหาต้องถึงคลังในเครื่อง")
            self.assertEqual(len(list((root / "out").rglob("*.md"))) - 1, 3,
                             "ต้องมีบทครบสามสไตล์ (ไม่นับป้ายสถานะสิทธิ์)")

            # สถานะสิทธิ์ต้องไม่ถูกปลดโดยการวางไฟล์ — คนละชั้นกัน
            self.assertFalse(result["published"]["cleared_for_publication"])
            self.assertEqual(result["clearance"], "approved-internal-only")
            self.assertTrue(result["license_reasons"])

            notice = Path(result["published"]["clearance_notice"])
            self.assertTrue(notice.is_file(), "ไม่มีป้ายบอกสถานะสิทธิ์ในโฟลเดอร์วัน")
            text = notice.read_text(encoding="utf-8")
            self.assertIn("ยังนำขึ้นเว็บหรือโซเชียลไม่ได้", text)
            for reason in result["license_reasons"]:
                self.assertIn(reason, text, "ป้ายต้องบอกด้วยว่าติดตรงไหน")

    def test_ป้ายสถานะต้องเปลี่ยนตามเมื่อสิทธิ์ผ่านแล้ว(self):
        """กันป้ายที่เขียนคำเตือนตายตัวจนบอกว่า "ห้ามเผยแพร่" แม้วันที่เผยแพร่ได้จริง"""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            notice = publish_layout.write_clearance_notice(
                root, "2026-08-05T11:34:00+00:00",
                clearance=license_gate.APPROVED_PUBLIC, reasons=[])
            text = notice.read_text(encoding="utf-8")
            self.assertIn("ผ่านด่านสิทธิ์แล้ว", text)
            self.assertNotIn("ยังนำขึ้นเว็บหรือโซเชียลไม่ได้", text)

    def test_ก้อนดิบที่เก็บไว้ต้องเป็นก้อนดิบจริง(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            snapshot = root / "snap.json"
            snapshot.write_text(json.dumps(self.payload, ensure_ascii=False), encoding="utf-8")
            build_daily_package.build_public(
                "xauusd", batch_id="t", output_root=root / "work",
                publish_root=None, snapshot_path=snapshot,
                cutoff_at="2026-08-05T11:34:00+00:00", max_age_minutes=10 ** 9)
            saved = json.loads((root / "work" / "t" / "xauusd" / "internal"
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

    def test_ก้อนที่ปลายทางปัดหยาบเกินไปต้องถูกหยุด(self):
        """EUR/USD จริงจากปลายทาง — ค่าเทคนิคถูกปัดเป็นทศนิยมสองตำแหน่ง

        ขั้นละ 0.01 ใหญ่กว่ากรอบราคาทั้งวันของคู่นี้หลายเท่า ⇒ SMA20 กับ SMA50
        ออกมาเป็น 1.14 เท่ากัน และแนวรับทั้งสามชั้นเป็น 1.15 เท่ากันหมด
        บทที่เขียนจากก้อนนี้ผ่านด่านเลขได้ทุกตัวแต่ไม่บอกอะไรคนอ่านเลย
        """
        with self.assertRaises(wcb_source.SnapshotTooCoarse):
            wcb_source.ensure_resolution(self.evidence)

    def test_ก้อนที่ละเอียดพอต้องผ่านด่านนี้(self):
        """กันด่านใหม่กลายเป็นด่านที่ตีตกทุกอย่าง — ทองผ่านต้องผ่านจริง"""
        gold = wcb_source.normalize(json.loads(FIXTURE.read_text(encoding="utf-8")))
        self.assertIs(wcb_source.ensure_resolution(gold), gold)

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

    def test_provider_ของสายสาธารณะยังเป็น_unknown_และต้องกั้นการเผยแพร่(self):
        # เปลี่ยนเป็นอนุมัติได้เมื่อได้คำตอบเรื่องสิทธิ์จากทีมเว็บแล้วเท่านั้น
        result = license_gate.evaluate("xauusd", providers=["wcb_snapshot_api"],
                                       content_qa_passed=True, data_quality_passed=True)
        self.assertNotEqual(result["clearance"], license_gate.APPROVED_PUBLIC)
        self.assertTrue(result["license_reasons"])


if __name__ == "__main__":
    unittest.main()
