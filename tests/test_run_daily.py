"""ล็อกตัวห่อ run_daily — มันต้องส่งค่าตั้งต้นชุดเดียวกับการพิมพ์คำสั่งเต็มเป๊ะ

ตัวห่อไม่มีตรรกะของตัวเอง เทสจึงตรวจอย่างเดียวว่า "ของที่ส่งต่อ" ถูกต้อง:
ไม่ยิงเครือข่าย ไม่เขียนไฟล์ — mock ทั้งสองสายและยาม frontmatter

พฤติกรรมตั้งแต่ 2026-08-05 ดึก (คำสั่งผู้ใช้): ค่าตั้งต้น = A/B/C เป็นชุดเดียว
ที่วางลง output/ · สายภายใน ①②③ รันครบทุกด่านแต่ no_publish เว้นแต่สั่ง
--publish-internal หรือเรียก --line internal ตรง ๆ
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import build_daily_package, run_daily  # noqa: E402


class DefaultInvocation(unittest.TestCase):

    def setUp(self):
        """**ชั้นเลือกใบขึ้นเว็บต้องถูก mock ในทุกเทสของคลาสนี้ ไม่ใช่เฉพาะที่นึกออก**

        ของจริงเขียนไฟล์ลง `../output` ซึ่งเป็นผลผลิตจริงของผู้ใช้ · เกิดขึ้นแล้วจริง
        ตอนต่อชั้นนี้เข้ามา 2026-08-06: เทสที่ mock ไม่ครบเพียงตัวเดียว (ตัวที่ตรวจ
        exit code) ก็พอให้มีโฟลเดอร์โผล่ในโฟลเดอร์ส่งของ ⇒ ผูกไว้ที่ setUp แทน
        """
        patcher = mock.patch.object(
            run_daily.publish_selection, "select",
            return_value={"status": "ready", "asset": "xauusd",
                          "article": "x", "directory": "d"})
        self.select = patcher.start()
        self.addCleanup(patcher.stop)
        # สไตล์ D ก็เขียนไฟล์จริง (บท + ภาพ 2 ใบ) — mock ทั้งคลาสด้วยเหตุผลเดียวกัน
        style_d_patcher = mock.patch.object(
            run_daily.chart_story_pipeline, "run",
            return_value={"status": "pass", "asset": "xauusd",
                          "directory": "d", "findings": []})
        self.style_d = style_d_patcher.start()
        self.addCleanup(style_d_patcher.stop)
        # สไตล์ E เขียนไฟล์จริงเช่นกัน (บท + ภาพรวมใบเดียว)
        style_e_patcher = mock.patch.object(
            run_daily.chart_indicator_pipeline, "run",
            return_value={"status": "pass", "asset": "xauusd", "char_count": 3800,
                          "directory": "e", "findings": []})
        self.style_e = style_e_patcher.start()
        self.addCleanup(style_e_patcher.stop)
        # สไตล์ F/G เขียนไฟล์จริงเช่นกัน (บทเช้า + ภาพกรอบราคา) — เข้ารอบ 2026-08-11
        style_fg_patcher = mock.patch.object(
            run_daily.brief_pipeline, "run",
            return_value={"ok": True, "style_name": "F", "asset": "xauusd",
                          "folder": "f", "findings": []})
        self.style_fg = style_fg_patcher.start()
        self.addCleanup(style_fg_patcher.stop)

    def run_wrapper(self, argv):
        calls = {"guard": [], "select": self.select}
        with mock.patch.object(build_daily_package, "run_internal_line",
                               return_value=0) as internal, \
                mock.patch.object(build_daily_package, "run_public_line",
                                  return_value=0) as public, \
                mock.patch.object(build_daily_package, "dispatch",
                                  return_value=0) as dispatch, \
                mock.patch.object(run_daily.frontmatter_guard, "main",
                                  side_effect=lambda a: calls["guard"].append(a) or 0):
            code = run_daily.main(argv)
        return code, internal, public, dispatch, calls

    def test_default_public_replaces_internal_in_output(self):
        """ไม่ใส่ธง = ①②③ รันแบบ no_publish · A/B/C เป็นชุดเดียวที่ลง output/"""
        code, internal, public, dispatch, calls = self.run_wrapper([])
        self.assertEqual(code, 0)
        dispatch.assert_not_called()

        (in_args, in_cutoff), _ = internal.call_args
        self.assertEqual(in_args.line, build_daily_package.LINE_INTERNAL)
        self.assertTrue(in_args.no_publish,
                        "สายภายในต้องไม่วางไฟล์ลง output ตามคำสั่ง 2026-08-05")
        (pub_args, pub_cutoff), _ = public.call_args
        self.assertEqual(pub_args.line, build_daily_package.LINE_PUBLIC)
        self.assertFalse(pub_args.no_publish)
        self.assertEqual(in_cutoff, pub_cutoff)

        # ค่าตั้งต้นที่เหลือต้องตรง parser ของ build_daily_package ทั้งสองสาย
        for args in (in_args, pub_args):
            self.assertEqual(args.asset, sorted(build_daily_package.ASSETS))
            self.assertEqual(args.output_root, Path("../work/build"))
            self.assertEqual(args.publish_root, Path("../output"))
            self.assertIsNone(args.snapshot)
            self.assertIsNone(args.source)
            self.assertEqual(args.max_bar_age_days,
                             build_daily_package.wcb_series_source.MAX_BAR_AGE_DAYS)
            self.assertFalse(args.no_news)
            self.assertFalse(args.no_trade_plan)
            self.assertEqual(args.cutoff_at, in_cutoff)
            self.assertEqual(args.batch_id, in_args.batch_id)
        # ยามต้องถูกเรียกสองที่เหมือนขั้นตอนเดิมก่อนส่งของ
        self.assertEqual(calls["guard"], [["."], ["../output"]])
        # ใบขึ้นเว็บต้องถูกเลือกจากโฟลเดอร์วันของรอบนี้ ไม่ใช่ path ที่พิมพ์ไว้ตายตัว
        (day_dir,), _ = calls["select"].call_args
        self.assertEqual(day_dir.parent, Path("../output"))
        self.assertRegex(day_dir.name, r"^\d{2}-\d{6}$")

    def test_เลือกใบขึ้นเว็บก่อนยาม_frontmatter(self):
        """สำเนาที่วางไว้ต้องโดนยามกวาดด้วย — basic-memory แทรก permalink: ให้ไฟล์ .md เอง

        ถ้าเลือกทีหลัง ใบที่ก๊อปจะรอดยามไปขึ้นเว็บพร้อม frontmatter แปลกปลอม
        """
        order = []
        self.select.side_effect = lambda d: order.append("select") or {
            "status": "ready", "article": "x", "directory": "d"}
        with mock.patch.object(build_daily_package, "run_internal_line", return_value=0), \
                mock.patch.object(build_daily_package, "run_public_line", return_value=0), \
                mock.patch.object(run_daily.frontmatter_guard, "main",
                                  side_effect=lambda a: order.append("guard") or 0):
            run_daily.main([])
        self.assertEqual(order, ["select", "guard", "guard"])

    def test_ธงข้ามการเลือกใบและสายภายในล้วนต้องไม่แตะโฟลเดอร์ขึ้นเว็บ(self):
        """`--line internal` ไม่ได้ผลิตบทสายเว็บ ⇒ ไปเลือกใบขึ้นเว็บไม่ได้"""
        _, _, _, _, calls = self.run_wrapper(["--skip-selection"])
        calls["select"].assert_not_called()
        _, _, _, _, calls = self.run_wrapper(["--line", "internal"])
        calls["select"].assert_not_called()

    def test_publish_internal_restores_old_behavior(self):
        code, internal, public, _, _ = self.run_wrapper(["--publish-internal"])
        self.assertEqual(code, 0)
        (in_args, _), _ = internal.call_args
        self.assertFalse(in_args.no_publish)
        (pub_args, _), _ = public.call_args
        self.assertFalse(pub_args.no_publish)

    def test_explicit_single_line_publishes_normally(self):
        """สั่ง --line internal ตรง ๆ = คำสั่งชัดเจน วางไฟล์ปกติผ่าน dispatch"""
        code, internal, public, dispatch, _ = self.run_wrapper(
            ["--line", "internal", "--asset", "xauusd",
             "--batch-id", "2026-08-06T07-00Z-daily"])
        self.assertEqual(code, 0)
        internal.assert_not_called()
        public.assert_not_called()
        (args, _), _ = dispatch.call_args
        self.assertEqual(args.line, build_daily_package.LINE_INTERNAL)
        self.assertFalse(args.no_publish)
        self.assertEqual(args.asset, ["xauusd"])
        self.assertEqual(args.batch_id, "2026-08-06T07-00Z-daily")

    def test_สไตล์เสริม_D_E_FG_รันครบทุกหัวข้อ_ข้ามได้_และไม่รันในสายภายใน(self):
        """ผู้ใช้สั่ง 2026-08-11: A–G เข้าสายหลัก**ครบทุกหัวข้อ** — เดิม D/E ผูกกับ
        ทองตัวเดียวและ F/G ไม่เข้ารอบเลย (นโยบาย "วันละ 1 บทเฉพาะทอง" เป็นเรื่อง
        ใบขึ้นเว็บใน publishing_policy.json ไม่ใช่เรื่องการผลิต)"""
        everything = sorted(build_daily_package.ASSETS)
        self.run_wrapper([])
        for style in (self.style_d, self.style_e, self.style_fg):
            self.assertEqual([kwargs["asset"] for _, kwargs in style.call_args_list],
                             everything, "สายเสริมต้องวนครบทุกหัวข้อตามลำดับเดียวกับสายหลัก")

        for style in (self.style_d, self.style_e, self.style_fg):
            style.reset_mock()
        self.run_wrapper(["--skip-style-d", "--skip-style-e", "--skip-style-fg"])
        self.style_d.assert_not_called()
        self.style_e.assert_not_called()
        self.style_fg.assert_not_called()

        self.run_wrapper(["--line", "internal"])
        self.style_d.assert_not_called()
        self.style_e.assert_not_called()
        self.style_fg.assert_not_called()

        # จำกัดหัวข้อ = สายเสริมวนเฉพาะหัวข้อนั้น (เดิมผูกทองแล้วเงียบทั้งสาย)
        self.run_wrapper(["--asset", "eurusd"])
        for style in (self.style_d, self.style_e, self.style_fg):
            self.assertEqual([kwargs["asset"] for _, kwargs in style.call_args_list],
                             ["eurusd"])

    def test_สไตล์เสริมตกด่านต้องดัน_exit_code_ไม่เป็นศูนย์(self):
        """สายเสริมล้มห้ามกลืนเงียบ — แต่ก็ห้ามพาสายหลักล้มตาม (ยังรันครบ)"""
        self.style_e.return_value = {"status": "fail", "asset": "xauusd",
                                     "char_count": 0, "directory": "e",
                                     "findings": [{"rule": "x"}]}
        code, _, public, _, _ = self.run_wrapper([])
        self.assertNotEqual(code, 0)
        public.assert_called_once()

        self.style_e.side_effect = RuntimeError("แหล่งข้อมูลล่ม")
        code, _, public, _, _ = self.run_wrapper([])
        self.assertNotEqual(code, 0)
        public.assert_called_once()

    def test_skip_guard(self):
        code, _, _, _, calls = self.run_wrapper(["--skip-guard"])
        self.assertEqual(code, 0)
        self.assertEqual(calls["guard"], [])

    def test_failure_codes_surface(self):
        """สายไหนตกหรือยามตกต้องดันให้ exit code ไม่เป็นศูนย์ — ห้ามกลืนเงียบ"""
        with mock.patch.object(build_daily_package, "run_internal_line", return_value=1), \
                mock.patch.object(build_daily_package, "run_public_line", return_value=0), \
                mock.patch.object(run_daily.frontmatter_guard, "main", return_value=0):
            self.assertNotEqual(run_daily.main([]), 0)
        with mock.patch.object(build_daily_package, "run_internal_line", return_value=0), \
                mock.patch.object(build_daily_package, "run_public_line", return_value=1), \
                mock.patch.object(run_daily.frontmatter_guard, "main", return_value=0):
            self.assertNotEqual(run_daily.main([]), 0)
        with mock.patch.object(build_daily_package, "run_internal_line", return_value=0), \
                mock.patch.object(build_daily_package, "run_public_line", return_value=0), \
                mock.patch.object(run_daily.frontmatter_guard, "main", return_value=1):
            self.assertNotEqual(run_daily.main([]), 0)

    def test_batch_id_is_folder_safe(self):
        stamp = run_daily.default_batch_id(
            datetime(2026, 8, 6, 7, 5, tzinfo=timezone.utc))
        self.assertEqual(stamp, "2026-08-06T07-05Z-daily")
        self.assertNotIn(":", stamp)


if __name__ == "__main__":
    unittest.main()
