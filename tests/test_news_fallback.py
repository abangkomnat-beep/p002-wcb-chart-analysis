"""ล็อกชั้นข่าวสำรองของสายเว็บ — **สวิตช์ต้องปิดอยู่จนกว่าหัวหน้าตอบ E11**

เทสชุดนี้ยืนยันสามเรื่องที่พังแล้วแพงที่สุด:
1. **ปิดอยู่จริง** และปิดแล้ว **ไม่ยิงเครือข่ายเลย** (ไม่ใช่ยิงแล้วทิ้งผล)
2. **ลำดับ 1 ชนะเสมอ** — มีข่าวเว็บ WCB ที่ใช้ได้ ชั้นสำรองต้องไม่แตะ (มติผู้ใช้ข้อ 10)
3. **พาดหัวที่มีตัวเลขถูกทิ้ง** — ไม่งั้นบททั้งใบตกด่าน `number_unsupported`
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from tools import news_fallback  # noqa: E402

NOW = datetime(2026, 8, 7, 2, 0, tzinfo=timezone.utc)
CONFIG = _REPO_ROOT / "config" / "news_sources.json"


def evidence(headlines, *, local_date="2026-08-07"):
    return {"headlines": list(headlines), "local_date": local_date}


def collected(*titles):
    return {"provider_used": "direct_rss",
            "items": [{"title": t, "source": "FXStreet", "source_tier": 2,
                       "link": f"https://example.test/{i}", "theme_id": "us_jobs",
                       "published_at": "2026-08-07T01:35:01+00:00"}
                      for i, t in enumerate(titles)]}


class สวิตช์(unittest.TestCase):

    def test_ทะเบียนจริงต้องยังปิดอยู่(self):
        """ถ้าเทสนี้ตก แปลว่ามีคนเปิดสวิตช์ — ต้องมีคำตอบ E11 ก่อนเท่านั้น

        เปิดโดยไม่มีคำตอบ = เอาชื่อสำนักข่าวอื่นขึ้นเว็บของ WCB โดยไม่ได้รับอนุญาต
        """
        settings = news_fallback.load_settings()
        self.assertFalse(settings["enabled"],
                         "สวิตช์ชั้นข่าวสำรองถูกเปิด — ต้องได้คำตอบ E11 จากหัวหน้าก่อน")

    def test_ทะเบียนจริงจำกัดแหล่งเป็นทางการเท่านั้น(self):
        settings = news_fallback.load_settings()
        self.assertEqual(settings["official_direct_feed_ids"], ["fed_press"])
        self.assertEqual(settings["official_sources"], ["Federal Reserve"])
        self.assertEqual(settings["official_domains"], ["federalreserve.gov"])

    def test_ปิดแล้วต้องไม่เรียกฟีดเลย(self):
        """ปิดสวิตช์ต้องแปลว่า 'ไม่ทำงาน' ไม่ใช่ 'ทำงานแล้วทิ้งผล'"""
        calls = []

        def collector(asset, now=None):
            calls.append(asset)
            return collected("ไม่ควรถูกเรียก")

        ev = evidence([])                       # ไม่มีข่าวเลย = เข้าเงื่อนไขทุกอย่าง
        log = news_fallback.apply(ev, asset="xauusd", collector=collector, now=NOW)
        self.assertEqual(calls, [], "ปิดสวิตช์แล้วยังเรียกฟีด — เสียเวลาและยิงเครือข่ายฟรี")
        self.assertFalse(log["used"])
        self.assertEqual(ev["headlines"], [], "ปิดสวิตช์แล้ว evidence ต้องไม่ถูกแตะ")
        self.assertIn("E11", log["reason"])

    def test_ทะเบียนหายถือว่าปิด(self):
        settings = news_fallback.load_settings(Path("ไม่มีไฟล์นี้.json"))
        self.assertFalse(settings["enabled"])


class เงื่อนไขการทำงาน(unittest.TestCase):
    """ทดสอบพฤติกรรมตอนเปิดสวิตช์ โดยไม่ต้องเปิดของจริง"""

    def setUp(self):
        self.on = {"enabled": True}
        self.original = news_fallback.load_settings
        news_fallback.load_settings = lambda *a, **k: self.on
        self.addCleanup(setattr, news_fallback, "load_settings", self.original)

    def test_ข่าวเว็บ_WCB_ที่ใช้ได้ต้องชนะเสมอ(self):
        """มติผู้ใช้ข้อ 10 — ห้ามให้ชั้นสำรองแทรกตอนลำดับ 1 มีของ"""
        calls = []
        ev = evidence([{"title": "ข่าวของเว็บวันนี้", "published_at": "2026-08-07"}])
        log = news_fallback.apply(ev, asset="xauusd", now=NOW,
                                  collector=lambda a, now=None: calls.append(a) or collected("ใหม่"))
        self.assertEqual(calls, [])
        self.assertFalse(log["used"])
        self.assertEqual(ev["headlines"][0]["title"], "ข่าวของเว็บวันนี้")

    def test_ข่าวเว็บเก่ากว่าวันข้อมูลจึงใช้ชั้นสำรอง(self):
        ev = evidence([{"title": "ข่าวเก่าสิบห้าวัน", "published_at": "2026-07-23"}])
        log = news_fallback.apply(
            ev, asset="xauusd", now=NOW,
            collector=lambda a, now=None: collected("Gold steady as Fed outlook clouds"))
        self.assertTrue(log["used"])
        self.assertEqual(ev["headlines"][0]["title"], "Gold steady as Fed outlook clouds")
        self.assertEqual(ev["headlines"][0]["channel"], news_fallback.CHANNEL)
        self.assertEqual(ev["headlines"][0]["source"], "FXStreet")
        self.assertEqual(ev["headlines"][0]["published_at"], "2026-08-07",
                         "ต้องเก็บเป็นวันที่ล้วน — ตัวเขียนเทียบกับ local_date แบบสตริง")

    def test_พาดหัวที่มีตัวเลขต้องถูกทิ้ง(self):
        """เลขในพาดหัวไม่มีทางอยู่ในก้อน snapshot ⇒ บททั้งใบจะตกด่านเลข"""
        ev = evidence([])
        log = news_fallback.apply(
            ev, asset="nvda", now=NOW,
            collector=lambda a, now=None: collected(
                "Nvidia shares Are Up Over 1,000% Since the AI Boom",
                "AI Data Center Group Draws Funding From Coatue"))
        self.assertEqual(log["dropped_with_digits"], 1)
        self.assertEqual([h["title"] for h in ev["headlines"]],
                         ["AI Data Center Group Draws Funding From Coatue"])

    def test_ทิ้งหมดแล้วต้องไม่แตะ_evidence(self):
        ev = evidence([])
        log = news_fallback.apply(
            ev, asset="nvda", now=NOW,
            collector=lambda a, now=None: collected("Nvidia up 1,000%"))
        self.assertFalse(log["used"])
        self.assertEqual(ev["headlines"], [])
        self.assertIn("ตัวเลข", log["reason"])

    def test_ชั้นสำรองล้มต้องไม่ลากสายท่อล้ม(self):
        """ข่าวล้มไม่หยุดสายท่อ — กติกาเดิมของระบบ ต่างจากราคาที่ล้มแล้วหยุด"""
        def boom(asset, now=None):
            raise RuntimeError("ฟีดล่ม")

        ev = evidence([])
        log = news_fallback.apply(ev, asset="xauusd", collector=boom, now=NOW)
        self.assertFalse(log["used"])
        self.assertIn("ฟีดล่ม", log["reason"])
        self.assertEqual(ev["headlines"], [])


class รูปแบบข้อมูล(unittest.TestCase):

    def test_แปลงแล้วต้องมีช่องครบเท่าพาดหัวของก้อน_snapshot(self):
        """ตัวเขียนอ่านช่องไหนก็ต้องเจอ ไม่งั้นจะพังตอนเปิดสวิตช์ ไม่ใช่ตอนนี้"""
        item = collected("Gold steady ahead of payrolls")["items"][0]
        headline = news_fallback.to_headline(item)
        for field in ("title", "published_at", "slug", "url", "category",
                      "subcat", "channel"):
            self.assertIn(field, headline)

    def test_ทะเบียนบอกวิธีเปิดไว้ในไฟล์เอง(self):
        """คนที่มาเปิดทีหลังต้องอ่านจากไฟล์เดียวจบ ไม่ต้องไปไล่หาในกระดาน"""
        config = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
        block = config["web_line_fallback"]
        joined = " ".join(str(v) for v in block.values())
        self.assertIn("E11", joined)


if __name__ == "__main__":
    unittest.main()
