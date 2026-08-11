"""เทสด่านความสอดคล้อง D-4.5 — บทขัดกันเองต้องตกทั้งใบ ไม่ออกไฟล์

ที่มา: ทีมเว็บเคยตีกลับบทที่ขัดกันเอง (D-4.5) · หลังเส้นแบ่งงานใหม่ 08-09
ไม่มีตาข่ายฝั่งเว็บแล้ว ด่านฝั่งเราต้องจับเอง · ผู้ใช้เคาะ 08-10: ทำทั้งบีบต้นทาง
และด่านท้าย fail-closed

กติกาเทสตามบทเรียน 08-10: ทุกกฎต้องมีเคส "สวมบั๊กกลับต้องแดง" —
เทสที่เขียวโดยไม่เคยจับบั๊กจริงคือเทสที่ยังพิสูจน์ตัวเองไม่ได้
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import consistency_gate as gate  # noqa: E402
from tools import headline_format  # noqa: E402


def _rules(findings: list[dict]) -> set[str]:
    return {item["rule"] for item in findings}


def _story(down: bool = True) -> dict:
    """story จำลองขั้นต่ำ — ด่านนี้อ่านแค่ regime ไม่แตะช่องอื่น"""
    return {"regime": {"down": down}}


FRONTMATTER_DN = """---
asset: xauusd
title: วิเคราะห์ทองคำวันนี้ 10 สิงหาคม 2026 — แนวรับแนวต้านจากกราฟ XAU/USD
excerpt: ทองปิดที่ 4,342.63 ดอลลาร์ อ่านโครงสร้างกราฟรายวัน
author_slug: natthaphon-s
timeframe: Daily
trend: dn
---

# วิเคราะห์ทองคำวันนี้ 10 ส.ค. 2026 — ทองยืน 4,343 จับตาโซนรับ 3,991

เนื้อบทเริ่มตรงนี้ ราคาปิด 4,342.63 ดอลลาร์ เมื่อ 7 ส.ค. 2026
"""


class TrendRegimeTests(unittest.TestCase):
    """กฎ 1 — `trend:` ใน frontmatter ต้องตรงกับ regime ของ story"""

    def test_trend_dn_กับ_regime_down_ผ่าน(self):
        findings = gate.check(FRONTMATTER_DN, _story(down=True))
        self.assertNotIn("trend_regime_mismatch", _rules(findings))

    def test_สวมบั๊ก_trend_สวนทาง_regime_ต้องแดง(self):
        # บทประกาศขาลงแต่ frontmatter บอกเว็บว่า up — คนอ่านเห็นป้ายเทรนด์ผิดทิศ
        wrong = FRONTMATTER_DN.replace("trend: dn", "trend: up")
        findings = gate.check(wrong, _story(down=True))
        self.assertIn("trend_regime_mismatch", _rules(findings))
        self.assertTrue(all(f["severity"] == "fatal"
                            for f in findings if f["rule"] == "trend_regime_mismatch"))

    def test_ไม่มี_story_ไม่ตรวจกฎนี้(self):
        wrong = FRONTMATTER_DN.replace("trend: dn", "trend: up")
        findings = gate.check(wrong, None)
        self.assertNotIn("trend_regime_mismatch", _rules(findings))


class BuddhistYearTests(unittest.TestCase):
    """กฎ 2 — ปีทั้งใบเป็น ค.ศ. · เจอปี พ.ศ. โดดในเนื้อความ = ตก

    🔄 **กฎนี้กลับขั้วเมื่อ 08-11** (หัวหน้าสั่ง) — เดิมบังคับ พ.ศ. ตอนนี้บังคับ ค.ศ.
    เหตุผล: ทั้งเว็บบังคับ locale ค.ศ. ⇒ วันที่เผยแพร่บนหน้าเป็น 2026 เสมอ
    พาดหัว พ.ศ. ทำให้หน้าเดียวกันมีปีต่างกัน 543 ปี
    """

    def test_บทปี_คศ_ล้วนผ่าน(self):
        findings = gate.check(FRONTMATTER_DN, _story())
        self.assertNotIn("buddhist_year", _rules(findings))

    def test_สวมบั๊ก_ปี_พศ_ในเนื้อความต้องแดง(self):
        bad = FRONTMATTER_DN + "\nโครงสร้างพลิกเป็นขาลงตั้งแต่ 29 ม.ค. 2569 เป็นต้นมา\n"
        findings = gate.check(bad, _story())
        self.assertIn("buddhist_year", _rules(findings))

    def test_สวมบั๊ก_พาดหัวยังเป็น_พศ_ต้องแดง(self):
        """เคสที่จะเกิดจริงที่สุด: แก้เนื้อบทแล้วลืมพาดหัว"""
        bad = FRONTMATTER_DN.replace("10 สิงหาคม 2026", "10 สิงหาคม 2569")
        findings = gate.check(bad, _story())
        self.assertIn("buddhist_year", _rules(findings))

    def test_ราคาหน้าตาเหมือนปี_พศ_ไม่โดนตี(self):
        # ราคาแถว 2,5xx มีจริง — จุดทศนิยมกับลูกน้ำต้องกันกฎปีได้
        ok = FRONTMATTER_DN + "\nแนวรับถัดไปอยู่ที่ 2,569.50 ดอลลาร์ และ 2569.50 ตามลำดับ\n"
        findings = gate.check(ok, _story())
        self.assertNotIn("buddhist_year", _rules(findings))

    def test_ปี_คศ_โดดไม่โดนตี(self):
        ok = FRONTMATTER_DN + "\nจุดสูงสุดของปี 2026 อยู่ที่ 5,597.23 ดอลลาร์\n"
        findings = gate.check(ok, _story())
        self.assertNotIn("buddhist_year", _rules(findings))


class IsoDateTests(unittest.TestCase):
    """กฎ 3 — วันที่ ISO ในเนื้อความ = ตก · บทต้องเขียนวันที่เป็นไทย

    ⚠️ **ตั้งเป็นกฎแยกเมื่อ 08-11** — เดิม ISO ถูกจับโดยบังเอิญเพราะกฎปีจับ ค.ศ.
    พอกลับขั้วเป็นจับ พ.ศ. ISO จะรอดทันที ⇒ ถ้าไม่ตั้งกฎนี้ การกลับขั้วจะกลายเป็น
    การผ่อนด่านแบบไม่ตั้งใจ · เทสชุดนี้คือตัวกันไม่ให้มันเงียบหาย
    """

    def test_สวมบั๊ก_วันที่แบบ_ISO_ในเนื้อความต้องแดง(self):
        bad = FRONTMATTER_DN + "\nข้อมูลถึง 2026-08-07 ตามฐานราคา\n"
        findings = gate.check(bad, _story())
        self.assertIn("iso_date_in_body", _rules(findings))

    def test_ชื่อไฟล์ภาพเป็น_ISO_ไม่โดนตี(self):
        ok = FRONTMATTER_DN + "\n![ภาพที่ 1 — โครงสร้างรอบใหญ่](xauusd-d1-structure-2026-08-07.webp)\n"
        findings = gate.check(ok, _story())
        self.assertNotIn("iso_date_in_body", _rules(findings))

    def test_บทปกติไม่ติดกฎนี้(self):
        findings = gate.check(FRONTMATTER_DN, _story())
        self.assertNotIn("iso_date_in_body", _rules(findings))


class RenderLabelTests(unittest.TestCase):
    """กฎ 4 — ป้ายข้อความที่จะวาดลงภาพ ผ่านกฎปีชุดเดียวกับบท (ตรวจก่อนวาด)"""

    def test_ป้ายปี_คศ_ผ่าน(self):
        findings = gate.check_labels(["XAU/USD · รายวัน (D1)", "ข้อมูลถึง 7 ส.ค. 2026"])
        self.assertEqual(findings, [])

    def test_สวมบั๊ก_หัวกราฟปี_พศ_ต้องแดง(self):
        # อาการ D-4.5 บนภาพ: บทกับหัวกราฟคนละระบบปี
        findings = gate.check_labels(["ข้อมูลถึง 7 ส.ค. 2569"])
        self.assertIn("buddhist_year_label", _rules(findings))

    def test_ป้ายบอกตำแหน่งไฟล์ไม่มีข้อยกเว้น(self):
        # ป้ายบนภาพไม่ใช่ชื่อไฟล์ — วันที่ ISO บนภาพผิดเสมอ ไม่มีเคสยกเว้นแบบในบท
        findings = gate.check_labels(["ภาพจาก xauusd-d1-structure-2026-08-07.webp"])
        self.assertIn("iso_date_label", _rules(findings))


class TitleH1DateTests(unittest.TestCase):
    """กฎ 5 — วันที่ใน Title (เดือนเต็ม) กับ H1 (เดือนย่อ) ต้องเป็นวันเดียวกัน"""

    def _doc(self, title_date: str, h1_date: str) -> str:
        title = headline_format.title("xauusd", title_date)
        h1 = headline_format.h1("xauusd", h1_date, "ทองยืน 4,343 จับตาโซนรับ 3,991")
        return (f"---\nasset: xauusd\ntitle: {title}\ntrend: dn\n---\n\n"
                f"# {h1}\n\nเนื้อบท\n")

    def test_วันเดียวกันผ่าน(self):
        findings = gate.check(self._doc("2026-08-10", "2026-08-10"), _story())
        self.assertNotIn("title_h1_date_mismatch", _rules(findings))

    def test_สวมบั๊ก_คนละวันต้องแดง(self):
        # เคสจริง: A/B/C ลงวันที่ snapshot ส่วน D/E ลงวันแท่งปิด — เคยต่างกันเงียบ ๆ
        findings = gate.check(self._doc("2026-08-10", "2026-08-07"), _story())
        self.assertIn("title_h1_date_mismatch", _rules(findings))

    def test_ไม่มี_H1_ไม่ตรวจกฎนี้(self):
        doc = "---\ntitle: วิเคราะห์ทองคำวันนี้ 10 สิงหาคม 2026 — ทดสอบ\n---\n\nเนื้อบทไม่มีหัว\n"
        findings = gate.check(doc, _story())
        self.assertNotIn("title_h1_date_mismatch", _rules(findings))


class WcbValidatorIntegrationTests(unittest.TestCase):
    """กฎปี ค.ศ. ต้องครอบ A/B/C ผ่าน `wcb_copy_validator` ด้วย (แผนขั้น A4)

    ใช้บทที่ตัวเขียนจริงผลิตจาก snapshot fixture — ไม่ใช่บทประดิษฐ์ เพื่อพิสูจน์
    พร้อมกันว่าบทจริงทุกสไตล์ไม่ติด false positive
    """

    @classmethod
    def setUpClass(cls):
        import json
        from tools import wcb_source, wcb_writers, wcb_copy_validator
        cls.validator = wcb_copy_validator
        fixture = REPO_ROOT / "tests" / "fixtures" / "wcb-snapshot-xauusd.json"
        cls.payload = json.loads(fixture.read_text(encoding="utf-8"))
        evidence = wcb_source.normalize(cls.payload)
        cls.articles = {w["id"]: w["render"](evidence) for w in wcb_writers.WCB_WRITERS}

    def test_บทจริงทุกสไตล์ไม่ติดกฎปี(self):
        for style, article in self.articles.items():
            with self.subTest(style=style):
                report = self.validator.validate(article, self.payload)
                self.assertEqual(
                    [f for f in report["findings"] if f["rule"] == "buddhist_year"], [])

    def test_สวมบั๊ก_ปี_พศ_ในบท_ABC_ต้องแดง(self):
        style, article = next(iter(self.articles.items()))
        bad = article + "\nข้อมูล ณ 3 ส.ค. 2569 เวลา 13:30 น.\n"
        report = self.validator.validate(bad, self.payload)
        rules = {f["rule"] for f in report["findings"]}
        self.assertIn("buddhist_year", rules)


class RendererLabelPathTests(unittest.TestCase):
    """ป้ายภาพเดินผ่านด่านจริง — ระบบปีบนแกนเวลาต้องตรงกับบทเสมอ

    ภาพรวม 320 แท่ง ≈ 15 เดือน กินข้ามปีใหม่เสมอ ⇒ ป้ายปีโผล่ที่รอยต่อเดือนมกราคม
    แทบทุกใบ · ถ้าแกนเวลากับบทคนละระบบปี = อาการ D-4.5 บนภาพ
    """

    def _view(self):
        # ธ.ค. 2025 ข้าม ม.ค. 2026 — รอยต่อปีที่ป้ายปีจะโผล่
        return ([{"date": f"2025-12-{d:02d}"} for d in range(1, 32)]
                + [{"date": f"2026-01-{d:02d}"} for d in range(1, 32)]
                + [{"date": f"2026-02-{d:02d}"} for d in range(1, 28)])

    def test_ป้ายปีบนแกนเวลาเป็น_คศ(self):
        from tools import chart_story_renderer
        _ticks, labels = chart_story_renderer.month_tick_labels(self._view())
        self.assertIn("2026", labels, "รอยต่อมกราคมต้องได้ปี ค.ศ.")
        self.assertNotIn("2569", labels, "ปี พ.ศ. ห้ามโผล่บนแกนเวลา (หัวหน้าสั่ง 08-11)")

    def test_สวมบั๊กกลับ_ป้าย_พศ_ผ่าน_checked_label_ต้องระเบิด(self):
        from tools import chart_story_renderer
        with self.assertRaises(ValueError):
            chart_story_renderer.checked_label("ข้อมูลถึง 7 ส.ค. 2569")

    def test_สวมบั๊ก_ป้าย_ISO_ผ่าน_checked_label_ต้องระเบิด(self):
        from tools import chart_story_renderer
        with self.assertRaises(ValueError):
            chart_story_renderer.checked_label("ข้อมูลถึง 2026-08-07")

    def test_ป้ายปกติผ่าน_checked_label_ได้ค่าเดิม(self):
        from tools import chart_story_renderer
        text = "ข้อมูลถึง 7 ส.ค. 2026 · ปิด 4,342.63"
        self.assertEqual(chart_story_renderer.checked_label(text), text)


class FatalOnlyTests(unittest.TestCase):
    """ด่านนี้ fail-closed — ทุก finding ต้องเป็น fatal ห้ามมีระดับเตือนเฉย ๆ"""

    def test_ทุกกฎให้_fatal(self):
        bad = (FRONTMATTER_DN.replace("trend: dn", "trend: up")
               + "\nพลิกขาลงตั้งแต่ 29 ม.ค. 2569 ข้อมูลถึง 2026-08-07\n")
        findings = gate.check(bad, _story(down=True))
        self.assertTrue(findings)
        self.assertTrue(all(f["severity"] == "fatal" for f in findings))


if __name__ == "__main__":
    unittest.main()
