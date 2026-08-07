"""เทสของ `/api/calendar/feed` ตัวใหม่ — ตัวแปลงข้อมูลและกติกาหน่วย

เทสสำคัญที่สุดในไฟล์นี้คือ `test_scale_unknown_ต้องข้ามทั้งค่า` เพราะมันคือกฎ
เดียวที่กันบทความพูดตัวเลขผิดไปเป็นพันล้านเท่า (ดุลการค้าจีน "$107" ที่จริงคือ
107 พันล้านดอลลาร์ — ทีมเว็บเจอกับดักนี้ตอนทดสอบเอง 2026-08-07)
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools import calendar_feed, wcb_copy_validator, wcb_writers  # noqa: E402

FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "wcb-snapshot-xauusd.json"

# ตัวอย่างค่าจริงจากการทดสอบยิง API 2026-08-07 — เก็บรูปแบบไว้ทั้งสามชนิด
NFP_FORECAST = {"raw": "80", "value": 80, "unit": "K", "unit_th": "พันตำแหน่ง",
                "kind": "count", "unit_source": "dict"}
PERCENT_ACTUAL = {"raw": "23.9%", "value": 23.9, "unit": "%", "unit_th": "เปอร์เซ็นต์",
                  "kind": "percent", "unit_source": "feed"}
UNKNOWN_UNIT = {"raw": "4.296", "value": 4.296, "unit": None, "unit_th": None,
               "kind": None, "unit_source": None}
SCALE_UNKNOWN = {"raw": "$107", "value": 107, "unit": "$", "unit_th": None,
                 "kind": "currency", "unit_source": "feed", "scale_unknown": True}
INDEX_KIND = {"raw": "54.1", "value": 54.1, "unit": None, "unit_th": "จุด",
             "kind": "index", "unit_source": "dict"}


class กติกาหน่วย(unittest.TestCase):
    def test_unit_source_dict_เขียนหน่วยได้(self):
        self.assertEqual(calendar_feed.format_value(NFP_FORECAST), "80 พันตำแหน่ง")

    def test_เปอร์เซ็นต์ไม่เติมคำซ้ำเพราะสัญลักษณ์ติดมาแล้ว(self):
        self.assertEqual(calendar_feed.format_value(PERCENT_ACTUAL), "23.9%")
        self.assertNotIn("เปอร์เซ็นต์", calendar_feed.format_value(PERCENT_ACTUAL))

    def test_unit_source_null_ต้องข้ามทั้งค่า(self):
        """🪤 ข้อ D-2 ที่ทีมเว็บตีกลับ — เลขเปล่าไม่ใช่ทางออกที่ปลอดภัยกว่า

        ของจริงที่เจอในฟีด 2026-08-07: "ยอดขายบ้านมือสอง ครั้งก่อนอยู่ที่ 4.09"
        (ของจริงคือ 4.09 ล้านหลัง) — คนอ่านไม่มีทางรู้ว่า 4.09 คืออะไร
        คำสั่งตรงตัวคือ "ค่าที่ไม่มีหน่วย ให้ตัดออกจากบท ... ดีกว่าเขียนแล้วคนอ่านงง"
        """
        self.assertIsNone(calendar_feed.format_value(UNKNOWN_UNIT))

    def test_ดัชนีที่unit_source_null_ยังเขียนเลขเปล่าได้(self):
        """เส้นแบ่งที่ทีมเว็บย้ำเอง: "ไม่มีหน่วยเพราะเป็นดัชนี" ≠ "ไม่รู้หน่วย"

        ถ้าตัดทิ้งเหมาเข่งด้วย `unit_source is None` อย่างเดียว ดัชนีที่ไม่มีหน่วย
        โดยธรรมชาติจะหายไปจากบททั้งที่เลขเปล่าคือคำตอบที่ถูกต้องอยู่แล้ว
        """
        index_no_source = dict(INDEX_KIND, unit_th=None, unit_source=None)
        self.assertEqual(calendar_feed.format_value(index_no_source), "54.1")

    def test_scale_unknown_ต้องข้ามทั้งค่า(self):
        """🪤 กับดักที่ทำให้บทผิดไปพันล้านเท่า — ทีมเว็บเจอเอง 2026-08-07

        "$107" ความจริงคือ 107 พันล้านดอลลาร์ ถ้าเขียนแค่ "107" (ตัดหน่วยทิ้ง)
        ก็ยังผิดเพราะดูเหมือนเป็นหน่วยเดิม (ดอลลาร์เฉย ๆ) ⇒ ต้องข้ามทั้งค่า
        ไม่ใช่แค่ไม่เติมหน่วย
        """
        self.assertIsNone(calendar_feed.format_value(SCALE_UNKNOWN))

    def test_ดัชนีไม่มีหน่วยโดยธรรมชาติยังเขียนได้(self):
        self.assertEqual(calendar_feed.format_value(INDEX_KIND), "54.1 จุด")

    def test_ค่าว่างหรือไม่มีเลยคืนNone(self):
        self.assertIsNone(calendar_feed.format_value(None))
        self.assertIsNone(calendar_feed.format_value({}))
        self.assertIsNone(calendar_feed.format_value({"raw": None, "unit_source": "feed"}))


class แปลงรูปเหตุการณ์(unittest.TestCase):
    def test_แปลงให้ตรงช่องกับ_evidence_calendar_เดิมทุกประการ(self):
        raw = {"events": [{
            "id": "396495", "title_th": "การจ้างงานนอกภาคเกษตร (NFP)",
            "title_en": "Non Farm Payrolls", "country": "USD", "impact": "High",
            "at_th": "2026-08-07 19:30", "at_utc": "2026-08-07T12:30:00.000Z",
            "forecast": NFP_FORECAST,
            "previous": {"raw": "57", "value": 57, "unit": "K", "unit_th": "พันตำแหน่ง",
                        "kind": "count", "unit_source": "dict"},
            "actual": None,
        }]}
        events = calendar_feed.to_calendar_events(raw)
        self.assertEqual(events, [{
            "at": "2026-08-07 19:30", "country": "USD", "impact": "High",
            "title": "การจ้างงานนอกภาคเกษตร (NFP)",
            "previous": "57 พันตำแหน่ง", "forecast": "80 พันตำแหน่ง", "actual": None,
        }])

    def test_title_th_เป็นnull_ใช้title_en_แทน(self):
        raw = {"events": [{"id": "1", "title_th": None, "title_en": "Something",
                           "country": "USD", "impact": "Medium", "at_th": "2026-08-07 21:00",
                           "forecast": None, "previous": None, "actual": None}]}
        self.assertEqual(calendar_feed.to_calendar_events(raw)[0]["title"], "Something")

    def test_ก้อนที่แปลงแล้วยังใช้กับ_wcb_writers_ได้ตรง(self):
        """ปิด D-2 ถาวร: ตัวคัด/ตัวเรียงประโยคเดิมของ wcb_writers ต้องใช้ได้
        โดยไม่ต้องแก้ตัวมันเองแม้แต่บรรทัดเดียว — พิสูจน์ด้วยการเรียกจริง"""
        raw = {"events": [
            {"id": "1", "title_th": "รายการที่มีหน่วย", "title_en": "x",
             "country": "USD", "impact": "High", "at_th": "2026-08-07 19:30",
             "forecast": NFP_FORECAST, "previous": None, "actual": None},
        ]}
        evidence = {"calendar": calendar_feed.to_calendar_events(raw),
                   "local_date": "2026-08-07"}
        sentences = wcb_writers._calendar_sentences(evidence, limit=3)
        self.assertIn("80 พันตำแหน่ง", sentences[0])


class รวมเข้าด่านตรวจ(unittest.TestCase):
    def test_เลขจากฟีดใหม่ต้องพ่วง_calendar_feed_เข้าด่านตรวจถึงจะผ่าน(self):
        """ถ้าไม่ส่ง calendar_feed= เลขที่มาจากฟีดนี้ (ไม่อยู่ใน snapshot) ต้องตกด่าน
        — พิสูจน์ทั้งสองทางเพื่อกันการเข้าใจผิดว่า "ส่งไปเฉย ๆ ก็ได้ไม่ต้องพ่วงจริง"

        ใช้ fixture จริงเป็นฐาน (ยืนยันแล้วว่าไม่มี "913257" อยู่ในนั้นเลย) เพื่อให้
        `wcb_source.normalize()`/`pivot_values()` ที่ด่านเรียกใช้ทำงานได้จริง
        แยกจากประเด็นที่กำลังพิสูจน์ (เลขจากปฏิทินใหม่)
        """
        snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
        pivot = wcb_source_first_pivot()
        article = ("---\nasset: xauusd\ntitle: ทดสอบ\nexcerpt: " + "ก" * 130 + "\n"
                  "author_slug: x\n---\n\n## เทคนิคและระดับราคาสำคัญ\n\n"
                  "ทดสอบเลขที่มาจากปฏิทินใหม่เท่านั้น 913257 หน่วย "
                  f"[[chart:1day|s={pivot}]]\n\n"
                  "## ปัจจัยพื้นฐานที่ต้องดู\n\nข้อความ\n\n## กลยุทธ์วันนี้\n\nข้อความ\n")
        calendar_raw = {"events": [{"id": "1", "title_th": "x", "title_en": "x",
                                    "country": "USD", "impact": "High",
                                    "at_th": "2026-08-07 19:30",
                                    "forecast": {"raw": "913257", "value": 913257,
                                                "unit": None, "unit_th": None,
                                                "kind": "count", "unit_source": "dict"},
                                    "previous": None, "actual": None}]}

        without = wcb_copy_validator.validate(article, snapshot)
        self.assertTrue(any(f["rule"] == "number_unsupported" for f in without["findings"]),
                        "ไม่พ่วงก้อนดิบ = เลขที่ปฏิทินใหม่ให้มาต้องตกด่าน")

        with_feed = wcb_copy_validator.validate(article, snapshot, calendar_feed=calendar_raw)
        self.assertFalse(any(f["rule"] == "number_unsupported" for f in with_feed["findings"]),
                         "พ่วงก้อนดิบแล้วต้องผ่าน เพราะเลขมีต้นทางจริงในฟีดใหม่")


def wcb_source_first_pivot() -> str:
    """pivot ตัวแรกของ fixture — ใช้ผูกหมุดกราฟในเทสให้ผ่านด่าน chart_line ไปได้
    (ประเด็นที่เทสนี้พิสูจน์คือด่านตัวเลขของปฏิทิน ไม่ใช่ด่านหมุดกราฟ)"""
    from tools import wcb_source
    snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pivots = wcb_source.pivot_values(wcb_source.normalize(snapshot))
    return f"{pivots[0]:.2f}"


class รวมเข้าสายผลิตจริง(unittest.TestCase):
    """`build_daily_package.build_public(calendar_feed_fetcher=...)` — ปิด D-2 ถาวร

    ยืนยันสองทาง: ไม่ส่ง fetcher (ค่าตั้งต้น) = พฤติกรรมเดิมเป๊ะ ไม่แตะปฏิทิน ·
    ส่ง fetcher = บทความได้หน่วยกำกับตัวเลขปฏิทินจริง และยังผ่านด่านครบ
    """

    def _fake_feed(self, _asset=None):
        return {"events": [{
            "id": "999", "title_th": "รายการทดสอบผลกระทบสูง", "title_en": "Test High",
            "country": "USD", "impact": "High", "at_th": "2026-08-05 19:30",
            "forecast": {"raw": "80", "value": 80, "unit": "K", "unit_th": "พันตำแหน่ง",
                        "kind": "count", "unit_source": "dict"},
            "previous": {"raw": "57", "value": 57, "unit": "K", "unit_th": "พันตำแหน่ง",
                        "kind": "count", "unit_source": "dict"},
            "actual": None,
        }]}

    def test_ไม่ส่ง_fetcher_ปฏิทินเดิมใน_snapshot_ไม่ถูกแตะ(self):
        from tools import build_daily_package
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            snapshot = root / "snap.json"
            snapshot.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
            result = build_daily_package.build_public(
                "xauusd", batch_id="t", output_root=root / "work",
                publish_root=None, snapshot_path=snapshot,
                cutoff_at="2026-08-05T11:34:00+00:00", max_age_minutes=10 ** 9)
            self.assertTrue(result["content_ok"])

    def test_ส่ง_fetcher_บทความได้หน่วยกำกับและยังผ่านด่าน(self):
        from tools import build_daily_package
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            snapshot = root / "snap.json"
            snapshot.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
            result = build_daily_package.build_public(
                "xauusd", batch_id="t", output_root=root / "work",
                publish_root=None, snapshot_path=snapshot,
                cutoff_at="2026-08-05T11:34:00+00:00", max_age_minutes=10 ** 9,
                calendar_feed_fetcher=self._fake_feed)
            self.assertTrue(result["content_ok"], msg=str(
                {k: v["validation"]["findings"] for k, v in result["drafts"].items()}))
            draft = (root / "work" / "t" / "xauusd" / "internal" / "public-line"
                    / "drafts" / "a_standard.md").read_text(encoding="utf-8")
            self.assertIn("80 พันตำแหน่ง", draft)


class รวมเข้าสไตล์D(unittest.TestCase):
    """`chart_story_pipeline.calendar_block_from_feed` — D ไม่มีด่านเทียบก้อนดิบ

    (`allowed_numbers()` เชื่อประโยคที่ `_calendar_sentences` สร้างโดยตรง)
    จึงพิสูจน์แค่ว่าประโยคที่ได้มีหน่วยกำกับจริง ไม่ต้องพ่วงก้อนดิบเพิ่ม
    """

    def test_ได้ประโยคปฏิทินพร้อมหน่วยจากฟีดปลอม(self):
        from tools import chart_story_pipeline

        def fake_fetcher():
            return {"events": [{
                "id": "1", "title_th": "รายการทดสอบ", "title_en": "Test",
                "country": "USD", "impact": "High", "at_th": "2026-08-07 19:30",
                "forecast": {"raw": "80", "value": 80, "unit": "K",
                            "unit_th": "พันตำแหน่ง", "kind": "count", "unit_source": "dict"},
                "previous": None, "actual": None,
            }]}

        calendar, status = chart_story_pipeline.calendar_block_from_feed(
            "xauusd", fetcher=fake_fetcher)
        self.assertEqual(status, "ok")
        self.assertIn("80 พันตำแหน่ง", calendar["sentences"][0])

    def test_ฟีดล่มต้องไม่พาบทล้ม(self):
        from tools import chart_story_pipeline

        def broken_fetcher():
            raise RuntimeError("เครือข่ายสะดุด")

        calendar, status = chart_story_pipeline.calendar_block_from_feed(
            "xauusd", fetcher=broken_fetcher)
        self.assertIsNone(calendar)
        self.assertIn("unavailable", status)


if __name__ == "__main__":
    unittest.main()
