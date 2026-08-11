"""เทสกลไกจำโซนข้ามวัน — "ล็อกโซนจนกว่าราคาทะลุ" (ผู้ใช้เคาะ 08-10 ข้อ #18ข)

ขอบเขตที่ผู้ใช้เคาะตอนอนุมัติแผน: ล็อกทั้งโซนรับ + แนวต้าน + กรอบแนวโน้ม
· "ทะลุ" = แท่งรายวัน**ปิด**นอกระดับ (intraday แทงแล้วเด้งกลับไม่นับ — กติกา
เดียวกับแท่งปิด A-1) · state หาย = คำนวณสดต่อได้ ไม่ตกทั้งบท (ความจำเป็น
เรื่องความต่อเนื่อง ไม่ใช่ความจริงของตัวเลข)

ครบ 4 สภาพตามแผน: ยังไม่ทะลุ(ล็อก) · ปิดทะลุ(ปลด+แทน) · state หาย(สด) ·
รันซ้ำวันเดียวกันได้ค่าเดิม (idempotent — กันหลายเซสชันชนกัน)
"""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import chart_story, zone_memory  # noqa: E402

REAL_ROWS = json.loads(
    (REPO_ROOT / "tests" / "fixtures" / "xau_420_sessions_2026-08-07.json")
    .read_text(encoding="utf-8"))


def _next_day(rows: list[dict], *, close: float, spread: float = 6.0) -> list[dict]:
    """ต่อแท่งปิดวันถัดไป (วันปฏิทินถัดจากแท่งสุดท้าย) เพื่อจำลองข้ามวัน"""
    import datetime as dt
    last = dt.date.fromisoformat(rows[-1]["date"])
    day = last + dt.timedelta(days=1)
    return rows + [{
        "date": day.isoformat(), "open": rows[-1]["close"],
        "high": max(rows[-1]["close"], close) + spread,
        "low": min(rows[-1]["close"], close) - spread, "close": close,
    }]


class StateIOTests(unittest.TestCase):
    def test_roundtrip_และ_atomic(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = {"schema": zone_memory.SCHEMA, "asset": "xauusd",
                     "as_of": "2026-08-10", "zones": [], "resistance": [], "channel": None}
            zone_memory.save("xauusd", state, state_dir=Path(tmp))
            loaded = zone_memory.load("xauusd", state_dir=Path(tmp))
            self.assertEqual(loaded, state)
            # ไม่มีไฟล์ tmp ค้าง (เขียนแบบ temp+rename)
            leftovers = [p for p in Path(tmp).iterdir() if p.suffix != ".json"]
            self.assertEqual(leftovers, [])

    def test_state_หายหรือพัง_คืน_None_ไม่ระเบิด(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(zone_memory.load("xauusd", state_dir=Path(tmp)))
            (Path(tmp) / "zones-xauusd.json").write_text("{พังครึ่งไฟล์", encoding="utf-8")
            self.assertIsNone(zone_memory.load("xauusd", state_dir=Path(tmp)))


class LockAcrossDaysTests(unittest.TestCase):
    """หัวใจของกลไก — วันสองต้องได้ระดับชุดเดิมเป๊ะเมื่อยังไม่มีการทะลุ"""

    @classmethod
    def setUpClass(cls):
        cls.day1 = chart_story.build_story(list(REAL_ROWS), asset="xauusd")
        cls.state1 = zone_memory.build_state(cls.day1)

    def test_state_เก็บครบสามชนิดพร้อมวันล็อก(self):
        self.assertEqual(self.state1["as_of"], self.day1["current"]["date"])
        self.assertEqual(len(self.state1["zones"]), len(self.day1["zones"]))
        self.assertEqual(len(self.state1["resistance"]), len(self.day1["resistance"]))
        for zone in self.state1["zones"]:
            self.assertEqual(zone["locked_since"], self.day1["current"]["date"])
        if self.day1["channel"]:
            self.assertIsNotNone(self.state1["channel"])
            self.assertEqual(self.state1["channel"]["locked_since"],
                             self.day1["current"]["date"])

    def test_วันสองยังไม่ทะลุ_ระดับล็อกเดิมเป๊ะ(self):
        # ปิดวันถัดไปกลางช่วงเดิม — ไม่ทะลุอะไร
        rows2 = _next_day(list(REAL_ROWS), close=self.day1["current"]["close"] + 5)
        day2 = chart_story.build_story(rows2, asset="xauusd", locked=self.state1)
        self.assertEqual([z["mean"] for z in day2["zones"]],
                         [z["mean"] for z in self.day1["zones"]],
                         "โซนรับต้องเป็นชุดที่ล็อกไว้ ไม่ใช่คำนวณใหม่")
        self.assertEqual([r["mean"] for r in day2["resistance"]],
                         [r["mean"] for r in self.day1["resistance"]])
        for zone in day2["zones"]:
            self.assertEqual(zone["locked_since"], self.day1["current"]["date"])
        self.assertTrue(day2["zone_memory"]["used"])

    def test_สวมบั๊กกลับ_ค่าล็อกต้องชนะค่าคำนวณสดจริง(self):
        # พิสูจน์ว่าการล็อกไม่ได้ "เขียวเพราะคำนวณสดบังเอิญได้เท่าเดิม" —
        # ขยับค่าใน state ให้ต่างจากของจริงเล็กน้อย ถ้า build_story เมิน locked
        # ผลจะเท่าคำนวณสด ไม่ใช่ค่าที่ขยับ (0.5 ดอลลาร์ไม่ทะลุ ไม่ชนตัวกรองไหน)
        shifted = copy.deepcopy(self.state1)
        for zone in shifted["zones"]:
            zone["mean"] += 0.5
            zone["low"] += 0.5
            zone["high"] += 0.5
        rows2 = _next_day(list(REAL_ROWS), close=self.day1["current"]["close"] + 5)
        story = chart_story.build_story(rows2, asset="xauusd", locked=shifted)
        self.assertEqual([z["mean"] for z in story["zones"]],
                         [z["mean"] for z in shifted["zones"]],
                         "ระดับในบทต้องเป็นค่าที่ล็อก ไม่ใช่ค่าคำนวณสด")
        fresh = chart_story.build_story(rows2, asset="xauusd")
        self.assertNotEqual([z["mean"] for z in story["zones"]],
                            [z["mean"] for z in fresh["zones"]])

    def test_วันสองรันซ้ำสองรอบได้ค่าเดิม_idempotent(self):
        rows2 = _next_day(list(REAL_ROWS), close=self.day1["current"]["close"] + 5)
        run1 = chart_story.build_story(rows2, asset="xauusd", locked=self.state1)
        state2 = zone_memory.build_state(run1, previous=self.state1)
        run2 = chart_story.build_story(rows2, asset="xauusd", locked=state2)
        self.assertEqual([z["mean"] for z in run1["zones"]],
                         [z["mean"] for z in run2["zones"]])
        # วันล็อกเดิมต้องไม่ถูกรีเซ็ตเป็นวันนี้
        for z1, z2 in zip(run1["zones"], run2["zones"]):
            self.assertEqual(z1["locked_since"], z2["locked_since"])

    def test_ปิดทะลุโซนรับ_โซนนั้นถูกปลด(self):
        deepest = min(z["low"] for z in self.day1["zones"])
        rows2 = _next_day(list(REAL_ROWS), close=deepest - 30)   # ปิดใต้ทุกโซน
        day2 = chart_story.build_story(rows2, asset="xauusd", locked=self.state1)
        locked_means = {z["mean"] for z in self.state1["zones"]}
        surviving_locked = [z for z in day2["zones"]
                            if z.get("locked_since") == self.day1["current"]["date"]
                            and z["mean"] in locked_means]
        self.assertEqual(surviving_locked, [],
                         "ปิดใต้โซนแล้วโซนล็อกเดิมต้องหลุดจากกระดาน")
        self.assertTrue(day2["zone_memory"]["broken"],
                        "ต้องบันทึกว่ารอบนี้มีระดับถูกปลดเพราะทะลุ")

    def test_ปิดเหนือแนวต้าน_เส้นนั้นถูกปลด_เส้นอื่นคงเดิม(self):
        first = self.day1["resistance"][0]["mean"]
        others = [r["mean"] for r in self.day1["resistance"][1:]]
        # ปิดเหนือเส้นแรกนิดเดียว แต่ยังใต้เส้นถัดไป
        target = first + 1.0
        if others:
            self.assertLess(target, min(others), "เคสนี้ต้องทะลุแค่เส้นเดียว")
        rows2 = _next_day(list(REAL_ROWS), close=target)
        day2 = chart_story.build_story(rows2, asset="xauusd", locked=self.state1)
        surviving = [r["mean"] for r in day2["resistance"]
                     if r.get("locked_since") == self.day1["current"]["date"]]
        self.assertNotIn(first, surviving, "เส้นที่ถูกปิดทะลุต้องหลุด")
        for value in others:
            self.assertIn(value, surviving, "เส้นที่ยังไม่ทะลุต้องอยู่ครบ")

    def test_กรอบแนวโน้มล็อกข้ามวัน_จุดตั้งต้นกับความชันเดิม(self):
        # ⚠️ ข้อมูลจริง 08-07 ราคา**ปิดเหนือขอบบนของกรอบอยู่แล้ว** (บทเล่าเอง
        # ว่า "ปิดทะลุขึ้นเหนือแนวขอบบน") — แท่งถัดไปจึงต้องปิด**ในกรอบ**เท่านั้น
        # กรอบล็อกถึงจะอยู่รอด: คำนวณจุดกึ่งกลางกรอบ ณ แท่งถัดไปจากเส้นตรึง
        ch = self.day1["channel"]
        main_next = ch["main_at_last"] + ch["slope"]
        inside = main_next + ch["offset"] / 2      # กึ่งกลางระหว่างเส้นหลักกับเส้นขนาน
        rows2 = _next_day(list(REAL_ROWS), close=inside)
        day2 = chart_story.build_story(rows2, asset="xauusd", locked=self.state1)
        self.assertIsNotNone(day2["channel"])
        self.assertEqual(day2["channel"]["start_date"], ch["start_date"])
        self.assertAlmostEqual(day2["channel"]["slope"], ch["slope"])
        self.assertAlmostEqual(day2["channel"]["intercept"], ch["intercept"])
        self.assertEqual(day2["channel"]["locked_since"], self.day1["current"]["date"])

    def test_ปิดนอกกรอบ_กรอบถูกปลดแล้ว_fit_ใหม่(self):
        ch = self.day1["channel"]
        # เส้นหลักคือขอบบน (ตลาดขาลง) — ปิดเหนือเส้นหลัก ณ แท่งถัดไปหลายช่วง ATR
        last = ch["main_at_last"]
        rows2 = _next_day(list(REAL_ROWS), close=last + self.day1["atr14"] * 2)
        day2 = chart_story.build_story(rows2, asset="xauusd", locked=self.state1)
        self.assertTrue(day2["zone_memory"]["broken"])
        if day2["channel"] is not None:
            self.assertNotIn("locked_since", day2["channel"],
                             "กรอบที่ fit ใหม่ต้องไม่แบกวันล็อกเก่า")

    def test_ไม่ส่ง_locked_พฤติกรรมเดิมทุกช่อง(self):
        # ทางเดินเดิม (เทส/สคริปต์เรียกตรง) ต้องไม่เปลี่ยน — ไม่มีช่อง memory โผล่
        story = chart_story.build_story(list(REAL_ROWS), asset="xauusd")
        self.assertNotIn("zone_memory", story)
        for zone in story["zones"]:
            self.assertNotIn("locked_since", zone)


class ArticleAgePhraseTests(unittest.TestCase):
    """B3 — บทวันที่โซนล็อกข้ามวันต้องกำกับอายุ และเลขวันล็อกต้องไม่ตกด่านเอง"""

    def test_บทกำกับโซนเดิม_และผ่านด่านครบทุกชั้น(self):
        from tools import chart_story_writer
        day1 = chart_story.build_story(list(REAL_ROWS), asset="xauusd")
        state1 = zone_memory.build_state(day1)
        ch = day1["channel"]
        inside = ch["main_at_last"] + ch["slope"] + ch["offset"] / 2
        rows2 = _next_day(list(REAL_ROWS), close=inside)
        day2 = chart_story.build_story(rows2, asset="xauusd", locked=state1)

        markdown = chart_story_writer.render_article(day2)
        self.assertIn("เดิมที่ใช้อ้างอิงมาตั้งแต่ 7 ส.ค. 2026", markdown,
                      "บทต้องบอกคนอ่านว่าระดับเป็นชุดเดิมจากวันไหน")
        validation = chart_story_writer.validate(markdown, day2)
        self.assertEqual(validation["status"], "pass",
                         [f["rule"] for f in validation["findings"]])

    def test_วันแรกที่เพิ่งล็อก_ไม่มีวลีเดิม(self):
        from tools import chart_story_writer
        day1 = chart_story.build_story(list(REAL_ROWS), asset="xauusd")
        markdown = chart_story_writer.render_article(day1)
        self.assertNotIn("เดิมที่ใช้อ้างอิงมาตั้งแต่", markdown,
                         "วันแรกยังไม่ใช่ 'ชุดเดิม' ห้ามกำกับ")


if __name__ == "__main__":
    unittest.main()
