"""เทสนักเขียนสามสไตล์ + โครงโฟลเดอร์ที่ผู้ใช้เอาไปอัป (คำสั่งผู้ใช้ 2026-08-04)

สิ่งที่เทสชุดนี้ล็อกไว้:
- **ทั้งสามสไตล์ต้องต่างกันจริง** ไม่ใช่ของเดิมห่อใหม่ — วัดจากโครงสร้างและถ้อยคำ
- **สไตล์ ① ต้องไม่เปลี่ยนแม้แต่ตัวอักษรเดียว** เพราะถูกล็อกด้วย pilot-baseline อยู่
- กฎเนื้อหาบังคับเท่ากันทุกสไตล์: เลขทุกตัวชี้กลับ evidence · ห้ามศัพท์ระบบ · ห้ามตาราง
- **ตัวเลขจุดเข้า/จุดตัดขาดทุน/อัตราส่วน อยู่ในสไตล์ ② คนเดียว** (ผู้ใช้ปลดมติข้อ 14ก
  เมื่อ 2026-08-04) · สไตล์ ① กับ ③ ต้องไม่มีแม้ส่งแผนให้ก็ตาม
- โครงโฟลเดอร์: output/<DD-MMYYYY>/<นักเขียน>/<สินทรัพย์>.md + .png ชื่อคู่กัน
  และ **ไม่มีไฟล์ฝั่ง internal ปนในนั้น**
- fail-closed: สไตล์ไหนไม่ผ่านด่าน = ไม่มีไฟล์ของสไตล์นั้น ไม่ใช่ปล่อยของเสียลงไป
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import article_builder, chart_renderer, integrity  # noqa: E402
from tools import levels as level_engine, license_gate  # noqa: E402
from tools import public_copy_validator, publish_layout, voice_rules, writers  # noqa: E402
from tools import risk_auditor, trade_plan  # noqa: E402


CUTOFF = "2026-08-03T07:00:00+00:00"


def _ระบบไฟล์ต่อร่วมกันได้(root: Path) -> bool:
    """ถามระบบไฟล์ตรง ๆ แทนการเดาจากชื่อระบบปฏิบัติการ

    NTFS/ext4 ต่อไฟล์ร่วมกันได้โดยไม่ต้องขอสิทธิ์พิเศษ แต่ไดรฟ์ FAT32/exFAT
    หรือโฟลเดอร์ที่ sync ขึ้นคลาวด์บางตัวทำไม่ได้ — เทสจึงต้องถามที่เดียวกับที่จะเขียนจริง
    """
    probe = root / "_probe-link"
    target = root / "_probe-target"
    try:
        target.write_bytes(b"x")
        os.link(target, probe)
        return True
    except (OSError, NotImplementedError, AttributeError):
        return False
    finally:
        for path in (probe, target):
            try:
                path.unlink()
            except OSError:
                pass

# ข่าวปลอมที่ผ่านชั้นคัดกรองมาแล้ว — ใส่เพื่อให้ทั้งสามสไตล์ได้เดินเส้นทางที่มีข่าวจริง
# (สไตล์ ② ใช้ข่าวเปิดเรื่อง · สไตล์ ③ ใช้ปิดท้าย · ถ้าไม่ใส่จะเทสไม่ถึงโค้ดส่วนนั้น)
SAMPLE_NEWS = [
    {"event": "ทิศทางนโยบายดอกเบี้ยของธนาคารกลางสหรัฐ",
     "signal": "ต้นทุนการถือครองสินทรัพย์ที่ไม่ให้ผลตอบแทน",
     "source": "Reuters", "theme_id": "fed_policy"},
    {"event": "การเข้าซื้อทองคำของธนาคารกลาง", "signal": "ความต้องการซื้อระยะยาว",
     "source": "CNBC", "theme_id": "central_bank_gold"},
]


def build_sample(tmp: Path) -> tuple[dict, dict]:
    """ประกอบ evidence pack ด้วยเส้นทางเดียวกับสายท่อจริง — ไม่แต่งตัวเลขเอง

    ต้องประกอบเองแทนการอ่านไฟล์ผลลัพธ์เก่า เพราะเลขในบทความกับเลขใน evidence
    ต้องมาจากรอบคำนวณเดียวกัน ไม่งั้นด่านตรวจตัวเลขจะจับว่าไม่ตรงทั้งที่โค้ดถูก
    """
    rows = json.loads(
        (FIXTURES / "xau_valid_120_sessions.json").read_text(encoding="utf-8"))["rows"]
    report = integrity.assess(rows, "xauusd", calculated_at=CUTOFF)
    level_map = level_engine.build_level_map(report)
    chart_levels, _ = article_builder.public_level_views(
        level_map["zones"], float(report["candles"][-1]["close"]))
    chart_metadata = chart_renderer.render_daily_chart(
        candles=report["candles"], output_path=tmp / "chart-daily.png",
        symbol="XAU/USD", cutoff_at=CUTOFF, levels=chart_levels,
        indicator_series={"sma20": chart_renderer.rolling_mean_series(report["candles"], 20)},
        decimals=2,
        price_text=lambda value: voice_rules.format_price(value, "spot_metal"),
    )
    data = article_builder.build_article_data(
        report=report, level_map=level_map, chart_metadata=chart_metadata,
        license_result=license_gate.evaluate("xauusd"), symbol="XAU/USD",
        instrument_type="spot_metal", unit="ดอลลาร์ต่อออนซ์", decimals=2,
        cutoff_at=CUTOFF, batch_id="2026-08-03T07-00Z-daily-market",
        verified_news=SAMPLE_NEWS,
    )
    technical = {
        "indicators": report["indicators"], "pivots": report["pivots"],
        "valid_completed_bars": report["valid_completed_bars"],
        **article_builder.change_summary(report),
        "context": data["context"],
    }
    return data, technical


def build_branch(report_rows_cutoff: str = CUTOFF) -> dict:
    """สาขาแผนการเทรดจากข้อมูลชุดเดียวกับ `build_sample` — เดินผ่านโมดูลจริงทั้งสองตัว

    ห้ามแต่งแผนขึ้นเองในเทส เพราะจุดที่ต้องพิสูจน์คือ "เลขในบทความ = เลขในแผนจริง"
    แผนที่แต่งมือจะพิสูจน์ได้แค่ว่าเทมเพลตวางตัวอักษรถูกที่
    """
    rows = json.loads(
        (FIXTURES / "xau_valid_120_sessions.json").read_text(encoding="utf-8"))["rows"]
    report = integrity.assess(rows, "xauusd", calculated_at=report_rows_cutoff)
    level_map = level_engine.build_level_map(report)
    news = {"items": []}
    plan = trade_plan.build(
        report=report, level_map=level_map, symbol="XAU/USD", instrument_type="spot_metal",
        cutoff_at=report_rows_cutoff, batch_id="2026-08-03T07-00Z-daily-market",
        asset="xauusd", news=news)
    audit = risk_auditor.audit(plan, level_map=level_map, news=news)
    return {"status": "built", "classification": plan["classification"],
            "verdict": audit["verdict"], "plan": plan, "audit": audit}


def approved_branch() -> dict:
    """สาขาเดียวกับ `build_branch()` แต่ผลตรวจเป็น `pass` — ใช้ทดสอบตัวเขียนเท่านั้น

    ตั้งแต่ 2026-08-05 ด่านปล่อยแผนรับเฉพาะ `pass` และข้อมูลจริง**ยังไม่เคยให้ `pass` เลย**
    (วัดย้อนหลัง 484 วัน ได้ 0 วัน — ดูผลวัดระยะ 4) ถ้าเทสตัวเขียนพึ่งแผนจริงล้วน ๆ
    หัวข้อแผนจะไม่มีวันถูกเรนเดอร์ในเทสอีกเลย และเราจะไม่รู้ตัวว่าตัวเขียนพังเมื่อไหร่

    **ที่แทนคือ *ผลตรวจ* ไม่ใช่ตัวแผน** — ทุกตัวเลขยังมาจาก `trade_plan.build` จริง
    ห้ามใช้ตัวช่วยนี้ในเทสที่พิสูจน์ตัวด่านเอง (เทสพวกนั้นต้องใช้ `build_branch()` ตรง ๆ)
    """
    branch = build_branch()
    audit = {**branch["audit"], "verdict": risk_auditor.VERDICT_PASS, "findings": []}
    return {**branch, "verdict": risk_auditor.VERDICT_PASS, "audit": audit}


class WriterRegistry(unittest.TestCase):
    def test_มีนักเขียนสามคนและรหัสไม่ซ้ำกัน(self):
        self.assertEqual(len(writers.WRITERS), 3)
        ids = [writer["id"] for writer in writers.WRITERS]
        self.assertEqual(len(set(ids)), 3)

    def test_ชื่อโฟลเดอร์ไม่ซ้ำและไม่มีอักขระที่ตั้งชื่อโฟลเดอร์ไม่ได้(self):
        folders = [writer["folder"] for writer in writers.WRITERS]
        self.assertEqual(len(set(folders)), 3)
        for folder in folders:
            for bad in '\\/:*?"<>|':
                self.assertNotIn(bad, folder, f"ชื่อโฟลเดอร์ '{folder}' มีอักขระต้องห้าม {bad}")

    def test_by_id_หานักเขียนเจอและโยนเมื่อไม่รู้จัก(self):
        self.assertEqual(writers.by_id("market_tempo")["pen_name"], "ปุณณ์")
        with self.assertRaises(KeyError):
            writers.by_id("ไม่มีคนนี้")


class StylesAreDistinct(unittest.TestCase):
    """หัวใจของงานนี้ — ผู้ใช้ทักว่า "ตัวเขียนสามเทคนิคแต่ผลออกมาสไตล์เดียว" """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.article, cls.technical = build_sample(Path(cls.tmp.name))
        cls.rendered = {writer["id"]: writer["render"](cls.article, chart_name="a.png")
                        for writer in writers.WRITERS}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_สามสไตล์ให้ข้อความไม่ซ้ำกันเลย(self):
        texts = list(self.rendered.values())
        self.assertEqual(len(set(texts)), 3, "มีอย่างน้อยสองสไตล์ที่ให้ผลเหมือนกันเป๊ะ")

    def test_เนื้อความต่างกันจริงไม่ใช่แค่สลับหัวข้อ(self):
        """เทียบเฉพาะเนื้อร้อยแก้ว — ถ้าซ้ำกันเกินครึ่ง แปลว่าเป็นของเดิมห่อใหม่"""
        prose = {key: set(article_builder.prose_only(text).split())
                 for key, text in self.rendered.items()}
        keys = list(prose)
        for first in range(len(keys)):
            for second in range(first + 1, len(keys)):
                left, right = prose[keys[first]], prose[keys[second]]
                overlap = len(left & right) / max(1, min(len(left), len(right)))
                self.assertLess(overlap, 0.75,
                                f"{keys[first]} กับ {keys[second]} ใช้ถ้อยคำซ้ำกัน "
                                f"{overlap:.0%} — ยังเป็นสไตล์เดียวกันอยู่")

    def test_สไตล์โครงสร้างราคามีหัวข้อย่อยและรายการโซน(self):
        text = self.rendered["price_structure"]
        self.assertIn("\n## ", text)
        self.assertIn("**โซนแนวรับที่ต้องเฝ้า:**", text)
        self.assertRegex(text, r"\n- ")

    def test_สไตล์จังหวะตลาดไม่มีหัวข้อย่อยและสั้นกว่าอีกสองสไตล์(self):
        tempo = self.rendered["market_tempo"]
        self.assertNotIn("\n## ", tempo)
        words = {key: voice_rules.count_public_words(text)
                 for key, text in self.rendered.items()}
        self.assertLess(words["market_tempo"], words["market_report"])
        self.assertLess(words["market_tempo"], words["price_structure"])

    def test_สไตล์รายงานตลาดยังเป็นของเดิมทุกตัวอักษร(self):
        """สไตล์ ① ถูกล็อกด้วย pilot-baseline — เปลี่ยนถ้อยคำคือทำ baseline พังทั้งชุด"""
        self.assertEqual(self.rendered["market_report"],
                         article_builder.render_markdown(self.article, chart_name="a.png"))

    def test_ทุกสไตล์อ้างชื่อไฟล์กราฟที่ส่งเข้าไป(self):
        for key, text in self.rendered.items():
            self.assertIn("](a.png)", text, f"สไตล์ {key} ไม่ได้ใช้ชื่อไฟล์กราฟที่ส่งให้")


class EveryStyleObeysContentRules(unittest.TestCase):
    """โครงสร้างต่างกันได้ แต่กฎเนื้อหาห้ามผ่อนให้สไตล์ไหนเป็นพิเศษ"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.article, cls.technical = build_sample(Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_ทุกสไตล์ผ่านด่านตรวจของตัวเอง(self):
        for writer in writers.WRITERS:
            with self.subTest(writer=writer["id"]):
                markdown = writer["render"](self.article, chart_name="a.png")
                result = public_copy_validator.validate(
                    markdown,
                    evidence={"article": self.article, "technical": self.technical},
                    instrument_type=self.article["instrument"]["instrument_type"],
                    profile=writer["profile"])
                self.assertEqual(result["status"], "pass",
                                 f"{writer['id']} ตกด่าน: {result['findings']}")

    def test_ทุกสไตล์ห้ามมีตาราง_ห้ามศัพท์ระบบ_และมีหัวเรื่องหัวเดียว(self):
        for writer in writers.WRITERS:
            with self.subTest(writer=writer["id"]):
                markdown = writer["render"](self.article, chart_name="a.png")
                _, body, _ = public_copy_validator.split_frontmatter(markdown)
                self.assertNotIn("|", body)
                lowered = body.lower()
                for term in public_copy_validator.SYSTEM_TERMS:
                    self.assertNotIn(term, lowered)
                for term in voice_rules.VOICE_DENYLIST:
                    self.assertNotIn(term, lowered)
                h1 = [line for line in body.splitlines()
                      if line.startswith("#") and not line.startswith("##")]
                self.assertEqual(len(h1), 1)

    def test_ไม่ส่งแผนมาก็ต้องไม่มีตัวเลขแผนสักสไตล์(self):
        """วันที่ไม่มีจังหวะ หัวข้อแผนต้องหายไปทั้งอัน ไม่ใช่เขียนว่า "วันนี้ไม่มีแผน" """
        banned = ("จุดเข้า", "entry", "stop loss", "จุดตัดขาดทุน", "take profit",
                  "ทำกำไรที่", "r:r", "risk to reward")
        for writer in writers.WRITERS:
            with self.subTest(writer=writer["id"]):
                lowered = writer["render"](self.article, chart_name="a.png").lower()
                for term in banned:
                    self.assertNotIn(term, lowered,
                                     f"{writer['id']} มีภาษาแผนการเทรด '{term}' "
                                     "ทั้งที่รอบนี้ไม่มีแผนให้เขียน")

    def test_ส่งแผนมาแล้วมีแค่สไตล์_2_ที่เขียนถึง(self):
        """ผู้ใช้ปลดล็อกให้ "สไตล์ที่ 2" คนเดียว — อีกสองคนต้องไม่ขยับแม้แต่ตัวอักษรเดียว"""
        plan = writers.plan_for_public(approved_branch())
        self.assertIsNotNone(plan, "ข้อมูลตัวอย่างควรให้แผนที่พูดได้ ไม่งั้นเทสนี้ไม่ได้ตรวจอะไร")
        for writer in writers.WRITERS:
            with self.subTest(writer=writer["id"]):
                plain = writer["render"](self.article, chart_name="a.png")
                with_plan = writer["render"](self.article, chart_name="a.png", plan=plan)
                if writer["uses_trade_plan"]:
                    self.assertIn("**จุดเข้า:**", with_plan)
                    self.assertIn("**จุดตัดขาดทุน:**", with_plan)
                    self.assertNotEqual(plain, with_plan)
                else:
                    self.assertEqual(plain, with_plan,
                                     f"{writer['id']} ไม่ควรเปลี่ยนเมื่อมีแผน")
                    self.assertNotIn("จุดเข้า", with_plan)

    def test_ไม่มีภาษาชี้จังหวะเข้าแบบระหว่างวัน(self):
        """ระบบมีข้อมูลรายวันเท่านั้น — พูดถึงไทม์เฟรมย่อยคือพูดถึงของที่ไม่มี"""
        banned = ("1h", "15m", "4h", "m15", "h1", "h4", "ระหว่างวันให้เข้า", "รายชั่วโมง")
        for writer in writers.WRITERS:
            with self.subTest(writer=writer["id"]):
                lowered = writer["render"](self.article, chart_name="a.png").lower()
                for term in banned:
                    self.assertNotIn(term, lowered)


class TradePlanInStyleTwo(unittest.TestCase):
    """ผู้ใช้ปลดมติข้อ 14ก เมื่อ 2026-08-04 — ตัวเลขแผนขึ้นบทความสไตล์ ② ได้แล้ว

    สิ่งที่ยังไม่ปลดและเทสชุดนี้เฝ้าไว้: ทุกเลขต้องเป็นค่าจากแผนจริง · ภาษาต้องเป็น
    เงื่อนไขระดับวัน · ป้ายระดับฝั่ง internal ห้ามหลุด · และข้อสรุปของบทความต้องไม่
    สวนทางกับทิศของแผนในบทความเดียวกัน
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.article, cls.technical = build_sample(Path(cls.tmp.name))
        cls.branch = approved_branch()
        cls.plan = writers.plan_for_public(cls.branch)
        cls.rendered = writers.render_price_structure(
            cls.article, chart_name="a.png", plan=cls.plan)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_เกณฑ์ปล่อยแผน_ไม่มีจังหวะต้องไม่ปล่อย(self):
        branch = {**self.branch, "plan": {**self.branch["plan"], "classification": "no_trade"}}
        self.assertIsNone(writers.plan_for_public(branch))

    def test_เกณฑ์ปล่อยแผน_ด่านความเสี่ยงต้องตัดสิน_pass_เท่านั้น(self):
        """แก้เมื่อ 2026-08-05 — เดิมกั้นเฉพาะ `block` ตอนนี้ `revise` ก็ไม่ผ่าน"""
        for verdict in (risk_auditor.VERDICT_BLOCK, risk_auditor.VERDICT_REVISE, None, "อะไรก็ไม่รู้"):
            with self.subTest(verdict=verdict):
                audit = {**self.branch["audit"], "verdict": verdict}
                self.assertIsNone(writers.plan_for_public({**self.branch, "audit": audit}))
        self.assertIsNone(writers.plan_for_public({**self.branch, "audit": {}}),
                          "ไม่มีผลตรวจเลยต้องถือว่าไม่ผ่าน ไม่ใช่ปล่อยผ่าน")
        self.assertIsNotNone(writers.plan_for_public(self.branch))

    def test_เกณฑ์ปล่อยแผน_สาขาที่ไม่ได้สร้างสำเร็จต้องไม่ปล่อย(self):
        for status in ("error", "blocked", "disabled_by_flag"):
            with self.subTest(status=status):
                self.assertIsNone(writers.plan_for_public({**self.branch, "status": status}))
        self.assertIsNone(writers.plan_for_public(None))

    def test_ข้อ_required_กั้นแล้วตั้งแต่ระยะ_4_วัดเสร็จ(self):
        """กลับด้านจากเทสเดิมเมื่อ 2026-08-05 (ผู้ใช้เลือกทาง ข)

        เดิมข้อ `required` ไม่กั้น เพราะเกณฑ์ยังไม่ผ่านการวัด · วัดแล้ว 484 วัน
        พบว่าเกณฑ์กับตัวสร้างแผนขัดกันเอง จึงถอนตัวเลขแผนออกจากบทความก่อน
        """
        real = build_branch()
        self.assertEqual(real["verdict"], risk_auditor.VERDICT_REVISE,
                         "ข้อมูลตัวอย่างควรได้ revise ไม่งั้นเทสนี้ไม่ได้ตรวจอะไร")
        self.assertIsNone(writers.plan_for_public(real))

    def test_เลขทุกตัวในหัวข้อแผนตรงกับแผนจริง(self):
        section = self.rendered.split("## 4.")[1].split("## สรุป")[0]
        expected = [voice_rules.format_price(self.plan["entry"]["edge"], "spot_metal"),
                    voice_rules.format_price(self.plan["stop"]["value"], "spot_metal")]
        expected += [voice_rules.format_price(target["value"], "spot_metal")
                     for target in self.plan["targets"][:2]]
        expected += [voice_rules.format_ratio(target["rr"])
                     for target in self.plan["targets"][:2]]
        for token in expected:
            self.assertIn(token, section, f"ค่า {token} ของแผนหายไปจากบทความ")

    def test_หัวข้อแผนผ่านด่านตรวจพร้อมหลักฐานของแผน(self):
        result = public_copy_validator.validate(
            self.rendered,
            evidence={"article": self.article, "technical": self.technical,
                      "trade_plan": writers.plan_evidence(self.plan)},
            instrument_type="spot_metal", profile=writers.PRICE_STRUCTURE_PROFILE,
            ratio_values=writers.plan_ratio_values(self.plan))
        self.assertEqual(result["status"], "pass", result["findings"])

    def test_ไม่ส่งค่าอัตราส่วนไปให้ด่าน_แล้วเลขอัตราส่วนต้องตก(self):
        """พิสูจน์ว่าเลขอัตราส่วนถูกตรวจจริง ไม่ได้รอดเพราะบังเอิญตรงค่าอื่นในกอง"""
        result = public_copy_validator.validate(
            self.rendered,
            evidence={"article": self.article, "technical": self.technical,
                      "trade_plan": writers.plan_evidence(self.plan)},
            instrument_type="spot_metal", profile=writers.PRICE_STRUCTURE_PROFILE)
        self.assertEqual(result["status"], "fail")
        self.assertIn("number_rounding", {item["rule"] for item in result["findings"]})

    def test_ภาษาต้องเป็นเงื่อนไขระดับวันไม่ใช่คำสั่งเข้าระหว่างวัน(self):
        lowered = self.rendered.lower()
        for phrase in ("เข้า buy ตรงนี้", "เข้า sell ตรงนี้", "entry confirmed",
                       "intraday trigger"):
            self.assertNotIn(phrase, lowered)
        self.assertIn("แท่งรายวันปิด", self.rendered)

    def test_ป้ายระดับฝั่ง_internal_ห้ามหลุดมากับแผน(self):
        """แผนถือป้ายอย่าง "Pivot S1 + SMA20" ไว้ — เขียนลงบทความคือหลุดศัพท์ระบบทันที"""
        lowered = self.rendered.lower()
        for term in ("pivot", "sma", "atr", "swing"):
            self.assertNotIn(term, lowered)

    def test_ข้อสรุปของบทความต้องไม่สวนทิศของแผนในฉบับเดียวกัน(self):
        bullish = self.plan["bias"] == "up"
        summary = self.rendered.split("## สรุป")[1]
        if bullish:
            self.assertIn("ฝั่งซื้อยังได้เปรียบ", summary)
            self.assertNotIn("ฝั่งขายยังได้เปรียบ", summary)
        else:
            self.assertIn("ฝั่งขายยังได้เปรียบ", summary)
            self.assertNotIn("ฝั่งซื้อยังได้เปรียบ", summary)

    def test_ราคาใต้เส้นค่าเฉลี่ยทั้งสองเส้นคือฝั่งขายแม้_rsi_จะแตะ_50(self):
        """บั๊กจริงของทองคำ 2026-08-04 — RSI ดิบ 50.4 เคยพลิกข้อสรุปเป็นฝั่งซื้อ

        ทั้งที่ราคาอยู่ใต้ทั้งสองเส้น และย่อหน้าก่อนหน้าเพิ่งเขียนว่าเรียงตัวฝั่งขาลง
        """
        data = {"snapshot": {"price": 4048.95},
                "technical": {"ma20": 4061.282, "ma50": 4174.4474, "rsi14": 50.4}}
        self.assertFalse(writers._bullish(data))
        above = {"snapshot": {"price": 4200.0},
                 "technical": {"ma20": 4061.282, "ma50": 4174.4474, "rsi14": 50.4}}
        self.assertTrue(writers._bullish(above))


class RatioNumbersAreNarrow(unittest.TestCase):
    """ช่องอัตราส่วนต้องไม่กลายเป็นประตูหลังให้ราคาทศนิยม 2 ตำแหน่งผ่านด่านไปด้วย"""

    HEAD = ("---\ntitle: a\nsymbol: X\ninstrument_type: forex_spot\n"
            "timezone: Asia/Bangkok\n---\n\n# หัว\n\n")

    def _check(self, body: str, evidence: dict, ratio_values=None):
        return public_copy_validator.validate(
            self.HEAD + body, evidence=evidence, check_completeness=False,
            profile={"require_technical_heading": False}, ratio_values=ratio_values)

    def test_อัตราส่วนที่ส่งมาให้ผ่านได้(self):
        result = self._check("ผลตอบแทน 2.35 เท่า", {"rr": 2.3456}, ratio_values=[2.3456])
        self.assertEqual(result["status"], "pass", result["findings"])

    def test_อัตราส่วนที่ไม่ได้ส่งมาต้องตก(self):
        result = self._check("ผลตอบแทน 2.35 เท่า", {"rr": 2.3456}, ratio_values=[1.5])
        self.assertEqual(result["status"], "fail")

    def test_ราคาคู่เงินที่พิมพ์ตกทศนิยมยังต้องตกเหมือนเดิม(self):
        """ต่อให้รอบนั้นมีอัตราส่วนอยู่ในบทความ ราคาก็ยังต้องครบตำแหน่งตามชนิดสินทรัพย์"""
        result = self._check("ราคาอยู่ที่ 1.16 ดอลลาร์", {"price": 1.16234},
                             ratio_values=[2.3456])
        self.assertEqual(result["status"], "fail")
        self.assertIn("number_rounding", {item["rule"] for item in result["findings"]})


class ValidatorProfiles(unittest.TestCase):
    def test_ค่าเริ่มต้นของด่านตรวจไม่เปลี่ยนเมื่อไม่ส่ง_profile(self):
        """เพิ่มสไตล์ใหม่ต้องไม่ทำให้ของเดิมหลวมลง"""
        text = "---\ntitle: a\nsymbol: X\ninstrument_type: forex_spot\ntimezone: Asia/Bangkok\n---\n\n# หัว\n\n## หัวย่อย\n"
        result = public_copy_validator.validate(text, check_numbers=False,
                                                check_completeness=False)
        rules = {item["rule"] for item in result["findings"]}
        self.assertIn("heading_forbidden", rules)

    def test_profile_ที่อนุญาตหัวข้อย่อยไม่ตีหัวข้อย่อยตก(self):
        text = "---\ntitle: a\nsymbol: X\ninstrument_type: forex_spot\ntimezone: Asia/Bangkok\n---\n\n# หัว\n\n## หัวย่อย\n"
        result = public_copy_validator.validate(
            text, check_numbers=False, check_completeness=False,
            profile={"allow_subheadings": True})
        rules = {item["rule"] for item in result["findings"]}
        self.assertNotIn("heading_forbidden", rules)

    def test_profile_ผ่อนได้แค่โครงสร้าง_ผ่อนกฎเนื้อหาไม่ได้(self):
        """ต่อให้ส่ง profile ที่พยายามปิดกฎเนื้อหา ตารางกับศัพท์ระบบก็ยังต้องถูกจับ"""
        text = ("---\ntitle: a\nsymbol: X\ninstrument_type: forex_spot\n"
                "timezone: Asia/Bangkok\n---\n\n# หัว\n\nคอลัมน์ | คอลัมน์\n\nqa_status ของงาน\n")
        result = public_copy_validator.validate(
            text, check_numbers=False, check_completeness=False,
            profile={"allow_subheadings": True, "require_technical_heading": False})
        rules = {item["rule"] for item in result["findings"]}
        self.assertIn("table_forbidden", rules)
        self.assertIn("system_term", rules)

    def test_เลขลำดับหัวข้อไม่ถูกนับเป็นตัวเลขข้อมูลตลาด(self):
        stripped = voice_rules.strip_structural_numbers("## 2. โครงสร้างกราฟ")
        self.assertNotIn("2", stripped)

    def test_เลขในเนื้อยังถูกตรวจตามเดิมแม้บรรทัดขึ้นต้นด้วยข้อความอื่น(self):
        stripped = voice_rules.strip_structural_numbers("ราคาอยู่ที่ 1.2345 ดอลลาร์")
        self.assertIn("1.2345", stripped)


class DayFolderName(unittest.TestCase):
    def test_รูปแบบวันตรงตามที่ผู้ใช้สั่ง(self):
        self.assertEqual(publish_layout.day_folder("2026-08-04T09:00:00+00:00"), "04-082026")

    def test_ยึดเวลาไทยไม่ใช่_utc(self):
        """สามทุ่มไทยของวันที่ 4 ยังเป็นบ่ายสองแบบ UTC ของวันที่ 4 — แต่ตีหนึ่งไทยไม่ใช่"""
        self.assertEqual(publish_layout.day_folder("2026-08-04T18:00:00+00:00"), "05-082026")

    def test_เวลาที่อ่านไม่ออกต้องโยนไม่ใช่เดาวัน(self):
        with self.assertRaises(ValueError):
            publish_layout.day_folder("เมื่อวานนี้")


class PublishLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.article, cls.technical = build_sample(Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _publish(self, root: Path, trade_branch: dict | None = None):
        chart = root / "source-chart.png"
        chart.write_bytes(b"\x89PNG\r\n\x1a\n")
        return publish_layout.publish_asset(
            asset="xauusd", article_data=self.article, technical_evidence=self.technical,
            chart_source=chart, publish_root=root / "out",
            cutoff_at="2026-08-04T09:00:00+00:00",
            instrument_type=self.article["instrument"]["instrument_type"],
            trade_branch=trade_branch)

    def test_ได้โครงวันแล้วนักเขียนแล้วไฟล์คู่ชื่อเดียวกัน(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = self._publish(root)
            day = root / "out" / "04-082026"
            self.assertTrue(day.is_dir())
            for writer in writers.WRITERS:
                folder = day / writer["folder"]
                self.assertTrue((folder / "xauusd.md").exists(), f"ขาดบทความของ {writer['id']}")
                self.assertTrue((folder / "xauusd.png").exists(), f"ขาดกราฟของ {writer['id']}")
            self.assertEqual(len(report["writers"]), 3)

    def test_ในโฟลเดอร์ที่ผู้ใช้เปิดมีแค่_md_กับ_png(self):
        """คำสั่งผู้ใช้ — ตัดเรื่อง internal ออกจากสายตา"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._publish(root)
            found = list((root / "out").rglob("*"))
            files = [path for path in found if path.is_file()]
            self.assertTrue(files)
            for path in files:
                self.assertIn(path.suffix, (".md", ".png"),
                              f"มีไฟล์แปลกปลอมในโฟลเดอร์ที่ผู้ใช้เปิด: {path.name}")
            for path in found:
                self.assertNotIn("internal", path.name.lower())

    def test_สไตล์ที่ตกด่านต้องไม่มีไฟล์วางอยู่(self):
        """fail-closed — ไฟล์ที่วางอยู่ในโฟลเดอร์นี้แปลว่าหยิบไปอัปได้เลย"""
        original = writers.WRITERS[1]["profile"]
        try:
            # บีบเพดานความยาวให้สไตล์ที่ 2 ตกด่านแน่นอน
            writers.WRITERS[1]["profile"] = {**original, "word_max": 1}
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                report = self._publish(root)
                failed = [item for item in report["writers"] if item["status"] != "pass"]
                self.assertEqual(len(failed), 1)
                folder = root / "out" / "04-082026" / failed[0]["folder"]
                self.assertFalse((folder / "xauusd.md").exists(),
                                 "สไตล์ที่ตกด่านไม่ควรมีไฟล์วางอยู่")
                # สไตล์อื่นต้องไม่โดนหางเลข
                self.assertEqual(
                    len([item for item in report["writers"] if item["status"] == "pass"]), 2)
        finally:
            writers.WRITERS[1]["profile"] = original

    def test_รันซ้ำวันเดิมแล้วตกด่านต้องลบไฟล์ของรอบก่อนทิ้ง(self):
        """เทสข้างบนตรวจบนโฟลเดอร์เปล่าเสมอ จึงไม่เคยเห็นเคสนี้ (พบ 2026-08-05)

        รอบแรกผ่าน ไฟล์ลงโฟลเดอร์ · รอบสองของ**วันเดียวกัน**ตกด่าน — ถ้าไม่ลบของเดิม
        ไฟล์รอบแรกจะนอนอยู่ที่เดิมโดยหน้าตาเหมือนของรอบล่าสุดทุกประการ
        ผู้ใช้หยิบไปอัปโดยไม่มีอะไรบอกว่ามันเป็นของที่ถูกตีตกไปแล้ว
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._publish(root)  # รอบแรก — ผ่านครบสามสไตล์
            folder = root / "out" / "04-082026" / writers.WRITERS[1]["folder"]
            self.assertTrue((folder / "xauusd.md").exists(), "รอบแรกควรผ่าน")

            original = writers.WRITERS[1]["profile"]
            try:
                writers.WRITERS[1]["profile"] = {**original, "word_max": 1}
                report = self._publish(root)  # รอบสอง วันเดียวกัน — สไตล์ ② ตกด่าน
            finally:
                writers.WRITERS[1]["profile"] = original

            failed = [item for item in report["writers"] if item["status"] != "pass"]
            self.assertEqual([item["folder"] for item in failed], [writers.WRITERS[1]["folder"]])
            self.assertFalse((folder / "xauusd.md").exists(),
                             "ไฟล์ของรอบก่อนต้องถูกลบ ไม่ใช่ค้างไว้ให้เข้าใจผิดว่าเป็นของสด")
            self.assertFalse((folder / "xauusd.png").exists(),
                             "กราฟก็ต้องหายไปด้วย ไม่งั้นเหลือกราฟลอยที่ไม่มีบทความคู่")
            self.assertTrue(failed[0]["removed_stale"],
                            "ต้องบันทึกไว้ด้วยว่ารอบนี้ไปลบของเดิมทิ้ง")
            # สไตล์อื่นที่ยังผ่านต้องไม่โดนหางเลข
            for writer in (writers.WRITERS[0], writers.WRITERS[2]):
                kept = root / "out" / "04-082026" / writer["folder"]
                self.assertTrue((kept / "xauusd.md").exists(), f"{writer['id']} ไม่ควรโดนลบ")
                self.assertTrue((kept / "xauusd.png").exists())

    def test_ไฟล์ของสินทรัพย์อื่นในโฟลเดอร์เดียวกันต้องไม่โดนลบตาม(self):
        """ลบเฉพาะคู่ของสินทรัพย์ที่กำลังทำ — ไม่ใช่ล้างทั้งโฟลเดอร์"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._publish(root)
            folder = root / "out" / "04-082026" / writers.WRITERS[1]["folder"]
            (folder / "eurusd.md").write_text("บทความของอีกหัวข้อ", encoding="utf-8")

            original = writers.WRITERS[1]["profile"]
            try:
                writers.WRITERS[1]["profile"] = {**original, "word_max": 1}
                self._publish(root)
            finally:
                writers.WRITERS[1]["profile"] = original

            self.assertTrue((folder / "eurusd.md").exists(),
                            "xauusd ตกด่านต้องไม่ลาก eurusd ที่ผ่านไปแล้วตายตาม")

    def test_กราฟชุดเดียวไม่ก๊อปซ้ำสามชุด(self):
        """กราฟผูกกับหัวข้อ ไม่ได้ผูกกับสไตล์การเขียน — สามโฟลเดอร์ได้ไฟล์เดียวกันเป๊ะ

        รูปคือ 95% ของขนาดโฟลเดอร์ผลผลิต (วัด 08-05: 1.41 MB จาก 1.49 MB ต่อวัน)
        ผู้ใช้ยังต้องเห็น `.png` ครบทุกโฟลเดอร์เหมือนเดิม — เปิดได้ ลากไปอัปได้ตามปกติ
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._publish(root)
            day = root / "out" / "04-082026"
            charts = [day / writer["folder"] / "xauusd.png" for writer in writers.WRITERS]
            for path in charts:
                self.assertTrue(path.is_file(), f"ต้องยังเห็นเป็นไฟล์ปกติ: {path}")
            self.assertEqual(len({path.read_bytes() for path in charts}), 1,
                             "เนื้อไฟล์ต้องตรงกันทั้งสามชุด")
            if not _ระบบไฟล์ต่อร่วมกันได้(root):
                self.skipTest("ระบบไฟล์นี้ต่อไฟล์ร่วมกันไม่ได้ — ชั้นตีพิมพ์ถอยไปก๊อปจริงตามที่ออกแบบไว้")
            self.assertEqual(len({path.stat().st_ino for path in charts}), 1,
                             "สามโฟลเดอร์ต้องชี้ไฟล์เดียวกัน ไม่ใช่ก๊อปสามชุดกินที่สามเท่า")

    def test_กราฟที่ต่อร่วมกันต้องไม่ผูกกลับไปที่ไฟล์ต้นทางในกองงาน(self):
        """ถ้าไปต่อร่วมกับไฟล์ใน `work/` รอบถัดไปที่เขียนทับต้นทางจะลากของที่อัปไปแล้วเปลี่ยนตาม"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chart = root / "source-chart.png"
            chart.write_bytes(b"\x89PNG\r\n\x1a\n" + "เดิม".encode())
            publish_layout.publish_asset(
                asset="xauusd", article_data=self.article, technical_evidence=self.technical,
                chart_source=chart, publish_root=root / "out",
                cutoff_at="2026-08-04T09:00:00+00:00",
                instrument_type=self.article["instrument"]["instrument_type"], trade_branch=None)
            published = root / "out" / "04-082026" / writers.WRITERS[0]["folder"] / "xauusd.png"
            before = published.read_bytes()
            chart.write_bytes(b"\x89PNG\r\n\x1a\n" + "รอบใหม่ทับต้นทาง".encode())
            self.assertEqual(published.read_bytes(), before,
                             "ไฟล์ที่ตีพิมพ์แล้วต้องไม่เปลี่ยนตามต้นทางในกองงาน")

    def test_แผนลงเฉพาะโฟลเดอร์ของสไตล์ที่_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = self._publish(root, trade_branch=approved_branch())
            self.assertTrue(report["trade_plan_public"]["included"])
            included = {item["writer_id"]: item["trade_plan_included"]
                        for item in report["writers"]}
            self.assertEqual(included, {"market_report": False, "price_structure": True,
                                        "market_tempo": False})
            day = root / "out" / "04-082026"
            for writer in writers.WRITERS:
                text = (day / writer["folder"] / "xauusd.md").read_text(encoding="utf-8")
                with self.subTest(writer=writer["id"]):
                    self.assertEqual("**จุดเข้า:**" in text, writer["uses_trade_plan"])

    def test_ไม่มีแผนต้องบันทึกเหตุผลไว้ให้แยกออกจากระบบพัง(self):
        branch = build_branch()
        branch = {**branch, "plan": {**branch["plan"], "classification": "no_trade",
                                     "detail": "ยังไม่มีทิศที่วัดได้จากเส้นค่าเฉลี่ย"}}
        with tempfile.TemporaryDirectory() as tmp:
            report = self._publish(Path(tmp), trade_branch=branch)
            note = report["trade_plan_public"]
            self.assertFalse(note["included"])
            self.assertEqual(note["reason"], "no_trade")
            self.assertTrue(note["detail"])

    def test_แผนที่ผู้ตรวจสั่งแก้ต้องบันทึกคำตัดสินและรหัสข้อที่ยิง(self):
        """วันที่หัวข้อหายเพราะ `revise` ต้องแยกออกจากวันที่ไม่มีจังหวะและวันที่ระบบพัง

        ทั้งสามกรณีหน้าตาเหมือนกันหมดคือหัวข้อหายไปเฉย ๆ ถ้าไม่บันทึกเหตุผลไว้
        """
        with tempfile.TemporaryDirectory() as tmp:
            report = self._publish(Path(tmp), trade_branch=build_branch())
            note = report["trade_plan_public"]
            self.assertFalse(note["included"])
            self.assertEqual(note["reason"], "risk_audit_verdict:revise")
            self.assertTrue(note["detail"], "ต้องบอกด้วยว่ายิงข้อไหน ไม่ใช่บอกแค่ว่าไม่ผ่าน")
            self.assertFalse(any(item["trade_plan_included"] for item in report["writers"]))

    def test_ไม่ส่งสาขาแผนมาเลยก็ยังตีพิมพ์ครบสามสไตล์(self):
        """สาขาแผนเป็นสาขาข้าง — ล้มแล้วห้ามลากบทความล้มตาม"""
        with tempfile.TemporaryDirectory() as tmp:
            report = self._publish(Path(tmp))
            self.assertFalse(report["trade_plan_public"]["included"])
            self.assertEqual([item["status"] for item in report["writers"]],
                             ["pass", "pass", "pass"])


if __name__ == "__main__":
    unittest.main()
