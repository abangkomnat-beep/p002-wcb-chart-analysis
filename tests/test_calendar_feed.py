"""เทสของ `/api/calendar/feed` ตัวใหม่ — ตัวแปลงข้อมูลและกติกาหน่วย

เทสสำคัญที่สุดในไฟล์นี้คือ `test_scale_unknown_ต้องข้ามทั้งค่า` เพราะมันคือกฎ
เดียวที่กันบทความพูดตัวเลขผิดไปเป็นพันล้านเท่า (ดุลการค้าจีน "$107" ที่จริงคือ
107 พันล้านดอลลาร์ — ทีมเว็บเจอกับดักนี้ตอนทดสอบเอง 2026-08-07)
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools import calendar_feed, chart_story_pipeline, wcb_copy_validator, wcb_source, wcb_writers  # noqa: E402

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

    def test_เปอร์เซ็นต์จากทะเบียนเติมสัญลักษณ์เมื่อrawยังไม่มี(self):
        field = {"raw": "6.77", "value": 6.77, "unit": "%", "unit_th": "เปอร์เซ็นต์",
                 "kind": "percent", "unit_source": "dict"}
        self.assertEqual(calendar_feed.format_value(field), "6.77%")

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

    def test_ทะเบียนหน่วยกลางกู้ค่าดัชนีที่ฟีดไม่ระบุชนิด(self):
        unknown = {"raw": "11", "value": 11, "unit": None, "unit_th": None,
                   "kind": None, "unit_source": None}
        raw = {"events": [{
            "id": "398376", "title_th": "ดัชนีภาคการผลิตรัฐนิวยอร์ก (Empire State)",
            "title_en": "NY Empire State Manufacturing Index", "country": "USD",
            "impact": "Medium", "at_th": "2026-08-17 19:30",
            "forecast": unknown, "previous": None, "actual": None,
        }]}
        self.assertEqual(calendar_feed.to_calendar_events(raw)[0]["forecast"], "11 จุด")

    def test_ทะเบียนใช้ชื่ออังกฤษที่อนุมัติเป็นทางสำรองเมื่อรหัสเปลี่ยน(self):
        unknown = {"raw": "33", "value": 33, "unit": None, "unit_th": None,
                   "kind": None, "unit_source": None}
        raw = {"events": [{
            "id": "new-id", "title_th": "ดัชนีตลาดที่อยู่อาศัย (NAHB)",
            "title_en": "NAHB Housing Market Index", "country": "USD",
            "impact": "Medium", "at_th": "2026-08-17 21:00",
            "forecast": unknown, "previous": None, "actual": None,
        }]}
        self.assertEqual(calendar_feed.to_calendar_events(raw)[0]["forecast"], "33 จุด")

    def test_ทะเบียนเติมมาตราส่วนให้ยอดบ้านและอัตราดอกเบี้ย(self):
        unknown = lambda raw: {"raw": raw, "value": float(raw), "unit": None,
                               "unit_th": None, "kind": None, "unit_source": None}
        raw = {"events": [
            {"id": "398326", "title_th": "ยอดเริ่มสร้างบ้าน", "title_en": "Housing Starts",
             "country": "USD", "impact": "High", "at_th": "2026-08-18 19:30",
             "forecast": unknown("1.35"), "previous": None, "actual": None},
            {"id": "398809", "title_th": "ใบอนุญาตก่อสร้าง (เบื้องต้น)",
             "title_en": "Building Permits Prel", "country": "USD", "impact": "High",
             "at_th": "2026-08-18 19:30", "forecast": unknown("1.37"),
             "previous": None, "actual": None},
            {"id": "396571", "title_th": "อัตราดอกเบี้ยบ้าน 30 ปี (MBA)",
             "title_en": "MBA 30-Year Mortgage Rate", "country": "USD", "impact": "Medium",
             "at_th": "2026-08-19 18:00", "forecast": None,
             "previous": unknown("6.77"), "actual": None},
        ]}
        converted = calendar_feed.to_calendar_events(raw)
        self.assertEqual(converted[0]["forecast"], "1.35 ล้านยูนิต")
        self.assertEqual(converted[1]["forecast"], "1.37 ล้านยูนิต")
        self.assertIn("อัตรารายปีปรับฤดูกาล", converted[0]["title"])
        self.assertIn("อัตรารายปีปรับฤดูกาล", converted[1]["title"])
        self.assertEqual(converted[2]["previous"], "6.77%")

    def test_ชื่อรายเดือนกับตัวเลขรวมไม่ถูกตัดซ้ำเป็นเหตุการณ์เดียว(self):
        percent = {"raw": "-2.6%", "value": -2.6, "unit": "%",
                   "unit_th": "เปอร์เซ็นต์", "kind": "percent", "unit_source": "feed"}
        level = {"raw": "1.37", "value": 1.37, "unit": None,
                 "unit_th": None, "kind": None, "unit_source": None}
        raw = {"events": [
            {"id": "398964", "title_th": "ใบอนุญาตก่อสร้าง (เบื้องต้น)",
             "title_en": "Building Permits MoM Prel", "country": "USD", "impact": "Medium",
             "at_th": "2026-08-18 19:30", "forecast": None,
             "previous": percent, "actual": None},
            {"id": "398809", "title_th": "ใบอนุญาตก่อสร้าง (เบื้องต้น)",
             "title_en": "Building Permits Prel", "country": "USD", "impact": "High",
             "at_th": "2026-08-18 19:30", "forecast": level,
             "previous": None, "actual": None},
        ]}
        converted = calendar_feed.to_calendar_events(raw)
        self.assertNotEqual(converted[0]["title"], converted[1]["title"])
        selected = chart_story_pipeline.weekly_calendar_events(
            converted, asset="xauusd", local_date="2026-08-18", limit=10)
        self.assertEqual(len(selected), 2)
        monthly = next(event for event in selected if "รายเดือน" in event["title"])
        level_event = next(event for event in selected if "รายเดือน" not in event["title"])
        self.assertEqual(monthly["previous"], "-2.6%")
        self.assertEqual(level_event["forecast"], "1.37 ล้านยูนิต")

    def test_ค่าที่ไม่อยู่ในทะเบียนยังถูกตัดแบบเดิม(self):
        raw = {"events": [{
            "id": "unknown", "title_th": "ยอดขายบ้านมือสอง",
            "title_en": "Existing Home Sales", "country": "USD", "impact": "High",
            "at_th": "2026-08-18 21:00", "forecast": UNKNOWN_UNIT,
            "previous": None, "actual": None,
        }]}
        self.assertIsNone(calendar_feed.to_calendar_events(raw)[0]["forecast"])


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

    กติกาใหม่รอบสี่ (2026-08-10 ข้อ A-3 ครึ่งหลัง): **ทุกทางเดินต้องผ่านด่านหน่วย**
    · มีฟีด = `format_value` ตัดสินรายค่า · ไม่มีฟีด (ปิดสวิตช์/ล่ม) = ตัดตัวเลข
    snapshot ทั้งหมดเพราะไม่รู้หน่วยสักตัว — เลขเปล่า "4.09" ห้ามหลุดขึ้นบทอีก
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

    def _build(self, root: Path, fetcher=None):
        from tools import build_daily_package
        snapshot = root / "snap.json"
        snapshot.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
        result = build_daily_package.build_public(
            "xauusd", batch_id="t", output_root=root / "work",
            publish_root=None, snapshot_path=snapshot,
            cutoff_at="2026-08-05T11:34:00+00:00", max_age_minutes=10 ** 9,
            calendar_feed_fetcher=fetcher)
        draft = (root / "work" / "t" / "xauusd" / "internal" / "public-line"
                / "drafts" / "a_standard.md").read_text(encoding="utf-8")
        return result, draft

    def test_ไม่ส่ง_fetcher_เลขปฏิทิน_snapshot_ต้องถูกตัดทั้งหมด(self):
        """ช่อง calendar เดิมไม่มีข้อมูลหน่วย ⇒ เลขทุกตัวคือ "ไม่รู้หน่วย" ห้ามเขียน
        และประโยคที่เหลือชื่อ+เวลาต้องจบในตัวเอง (คู่เทสที่ทีมเว็บขอ 08-10)"""
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            result, draft = self._build(Path(folder))
            self.assertTrue(result["content_ok"], msg=str(
                {k: v["validation"]["findings"] for k, v in result["drafts"].items()}))
            self.assertNotIn("ครั้งก่อนอยู่ที่", draft, "เลขไม่รู้หน่วยหลุดขึ้นบทอีกแล้ว")
            self.assertNotIn("คาดไว้ที่", draft)
            self.assertIn("จึงระบุได้แค่วันและเวลา", draft,
                          "ตัดค่าแล้วประโยคต้องปิดตัวเอง ไม่ใช่หายไปเฉย ๆ")

    def test_ฟีดล่มต้อง_fallback_แบบตัดเลข_ไม่ใช่ปล่อยเลขเปล่า(self):
        """ทางเดินที่อันตรายที่สุดคือ fallback อัตโนมัติตอนไม่มีใครดู — ต้องตัดเลขเสมอ"""
        import tempfile

        def broken(_asset=None):
            raise calendar_feed.CalendarFeedUnusable("ทดสอบ: ฟีดล่ม")

        with tempfile.TemporaryDirectory() as folder:
            result, draft = self._build(Path(folder), fetcher=broken)
            self.assertTrue(result["content_ok"])
            self.assertNotIn("ครั้งก่อนอยู่ที่", draft, "ฟีดล่มแล้วเลขเปล่ากลับมา")
            self.assertIn("จึงระบุได้แค่วันและเวลา", draft)

    def test_ฟีดให้ค่าที่ไม่รู้หน่วย_ประโยคต้องจบเองและไม่มีเลขเปล่า(self):
        """เทสคู่ที่ทีมเว็บขอตรงตัว (รอบสี่ ข้อ 2): "ประโยคจบสมบูรณ์ + ค่าไม่รู้หน่วย"
        ต้องได้พร้อมกัน — เคสจริงคือยอดขายบ้านมือสอง 4.09 (`unit_source: null`)"""
        import tempfile

        def feed_unknown_unit(_asset=None):
            return {"events": [{
                "id": "351", "title_th": "ยอดขายบ้านมือสอง", "title_en": "Existing Home Sales",
                "country": "USD", "impact": "High", "at_th": "2026-08-05 21:00",
                "previous": {"raw": "4.09", "value": 4.09, "unit": None, "unit_th": None,
                            "kind": None, "unit_source": None},
                "forecast": {"raw": "4.07", "value": 4.07, "unit": None, "unit_th": None,
                            "kind": None, "unit_source": None},
                "actual": None,
            }]}

        with tempfile.TemporaryDirectory() as folder:
            result, draft = self._build(Path(folder), fetcher=feed_unknown_unit)
            self.assertTrue(result["content_ok"])
            self.assertNotIn("4.09", draft, "ค่าไม่รู้หน่วยต้องถูกตัดทั้งค่า")
            self.assertNotIn("4.07", draft)
            self.assertIn("ยอดขายบ้านมือสอง", draft, "ชื่อรายการต้องยังอยู่")
            self.assertIn("จึงระบุได้แค่วันและเวลา", draft)

    def test_ส่ง_fetcher_บทความได้หน่วยกำกับและยังผ่านด่าน(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            result, draft = self._build(Path(folder), fetcher=self._fake_feed)
            self.assertTrue(result["content_ok"], msg=str(
                {k: v["validation"]["findings"] for k, v in result["drafts"].items()}))
            self.assertIn("80 พันตำแหน่ง", draft)


class ตัวคัดปฏิทินรายสัปดาห์ของสไตล์D(unittest.TestCase):

    EVENTS = [
        {"at": "2026-08-17 19:30", "country": "USD", "impact": "Medium", "title": "A"},
        {"at": "2026-08-18 13:00", "country": "GBP", "impact": "High", "title": "B"},
        {"at": "2026-08-19 15:00", "country": "USD", "impact": "Low", "title": "C"},
        {"at": "2026-08-21 20:45", "country": "USD", "impact": "High", "title": "D"},
        {"at": "2026-08-22 09:00", "country": "USD", "impact": "High", "title": "E"},
    ]

    def test_ช่วงสัปดาห์ยึดจันทร์ถึงศุกร์(self):
        self.assertEqual(chart_story_pipeline.week_bounds("2026-08-19"),
                         ("2026-08-17", "2026-08-21"))

    def test_ทองคัดเฉพาะUSDในวันทำการและไม่เอาข่าวผลกระทบต่ำ(self):
        selected = chart_story_pipeline.weekly_calendar_events(
            self.EVENTS, asset="xauusd", local_date="2026-08-19")
        self.assertEqual([event["title"] for event in selected], ["A", "D"])

    def test_คู่เงินคัดข่าวของทั้งสองฝั่ง(self):
        selected = chart_story_pipeline.weekly_calendar_events(
            self.EVENTS, asset="gbpusd", local_date="2026-08-19")
        self.assertEqual([event["title"] for event in selected], ["A", "B", "D"])

    def test_เมื่อที่นั่งจำกัดข่าวผลกระทบสูงมาก่อน(self):
        selected = chart_story_pipeline.weekly_calendar_events(
            self.EVENTS, asset="xauusd", local_date="2026-08-19", limit=1)
        self.assertEqual([event["title"] for event in selected], ["D"])


class รวมเข้าสไตล์D(unittest.TestCase):
    """`chart_story_pipeline.calendar_block_from_feed` — D ไม่มีด่านเทียบก้อนดิบ

    (`allowed_numbers()` เชื่อประโยคที่ `_calendar_sentences` สร้างโดยตรง)
    จึงพิสูจน์แค่ว่าประโยคที่ได้มีหน่วยกำกับจริง ไม่ต้องพ่วงก้อนดิบเพิ่ม
    """

    def test_ได้ประโยคปฏิทินพร้อมหน่วยจากฟีดปลอม(self):
        """🐞 เคยตายเงียบเพราะวันที่ตายตัว — `calendar_block_from_feed` อ่าน "วันนี้"
        จากนาฬิกาจริง พอเลย 2026-08-07 รายการในฟีดปลอมกลายเป็นอดีต `upcoming()`
        กรองทิ้ง สถานะจึงเป็น "empty" · เทสที่ผูกกับวันที่ต้อง**นับจากวันนี้เสมอ**
        """
        today = datetime.now(tz=wcb_source.BANGKOK).date()
        upcoming_day = (today if today.weekday() < 5
                        else today + timedelta(days=7 - today.weekday())).isoformat()

        def fake_fetcher():
            return {"events": [{
                "id": "1", "title_th": "รายการทดสอบ", "title_en": "Test",
                "country": "USD", "impact": "High", "at_th": f"{upcoming_day} 19:30",
                "forecast": {"raw": "80", "value": 80, "unit": "K",
                            "unit_th": "พันตำแหน่ง", "kind": "count", "unit_source": "dict"},
                "previous": None, "actual": None,
            }]}

        calendar, status = chart_story_pipeline.calendar_block_from_feed(
            "xauusd", fetcher=fake_fetcher)
        self.assertEqual(status, "ok")
        self.assertIn("80 พันตำแหน่ง", calendar["sentences"][0])
        self.assertIn("week_start", calendar)
        self.assertIn("week_end", calendar)

    def test_ฟีดล่มต้องไม่พาบทล้ม(self):
        def broken_fetcher():
            raise RuntimeError("เครือข่ายสะดุด")

        calendar, status = chart_story_pipeline.calendar_block_from_feed(
            "xauusd", fetcher=broken_fetcher)
        self.assertIsNone(calendar)
        self.assertIn("unavailable", status)

    def test_สายเก่าของD_ต้องตัดเลขปฏิทินเช่นกัน(self):
        """`_calendar_block` (สายสำรอง `--no-calendar-feed`) อ่าน snapshot ที่ไม่มี
        ข้อมูลหน่วย — ต้องตัดตัวเลขทั้งหมดแบบเดียวกับ A/B/C ไม่ใช่ช่องโหว่ที่เหลืออยู่"""
        from unittest import mock
        today = datetime.now(tz=wcb_source.BANGKOK).date()
        upcoming_day = (today if today.weekday() < 5
                        else today + timedelta(days=7 - today.weekday())).isoformat()
        fake_evidence = {
            "calendar": [{"at": f"{upcoming_day} 21:00", "country": "USD",
                          "impact": "High", "title": "ยอดขายบ้านมือสอง",
                          "previous": "4.09", "forecast": "4.07", "actual": None}],
            "local_date": datetime.now(tz=wcb_source.BANGKOK).strftime("%Y-%m-%d"),
        }
        with mock.patch.object(wcb_source, "fetch", return_value=fake_evidence):
            calendar, status = chart_story_pipeline._calendar_block("xauusd")
        self.assertEqual(status, "ok")
        joined = " ".join(calendar["sentences"])
        self.assertNotIn("4.09", joined, "สาย D เก่ายังปล่อยเลขเปล่า")
        self.assertNotIn("4.07", joined)
        self.assertIn("จึงระบุได้แค่วันและเวลา", joined)


if __name__ == "__main__":
    unittest.main()
