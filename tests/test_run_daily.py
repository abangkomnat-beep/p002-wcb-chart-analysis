"""ล็อกตัวห่อ run_daily — มันต้องส่งค่าตั้งต้นชุดเดียวกับการพิมพ์คำสั่งเต็มเป๊ะ

ตัวห่อไม่มีตรรกะของตัวเอง เทสจึงตรวจอย่างเดียวว่า "ของที่ส่งต่อ" ถูกต้อง:
ไม่ยิงเครือข่าย ไม่เขียนไฟล์ — mock ทั้งสองสายและยาม frontmatter

พฤติกรรมตั้งแต่ 2026-08-24 (คำสั่งผู้ใช้): A/B/C เป็นสายบทความสาธารณะ
ส่วนสายภายในสร้างเฉพาะหลักฐานและแผน ไม่รันตัวเขียน ①②③ อีก
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import brief_story, build_daily_package, run_daily  # noqa: E402


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
        #
        # ต้องมีช่อง `style` ด้วย เพราะ `run_pair` อ่านช่องนี้เพื่อตัดสินว่าวันนี้ต้อง
        # ผลิตใบที่สองหรือไม่ (ค่าตั้งต้น 2026-08-13 = ออกทั้ง F และ G เมื่อได้ G)
        style_fg_patcher = mock.patch.object(
            run_daily.brief_pipeline, "run",
            return_value={"ok": True, "style": brief_story.STYLE_F, "style_name": "F",
                          "asset": "xauusd", "folder": "f", "findings": []})
        self.style_fg = style_fg_patcher.start()
        self.addCleanup(style_fg_patcher.stop)
        # H/I/J เคยหลุดจาก mock ของคลาสนี้ ทำให้ unit test ยิง series จริงและเขียน
        # `../output` ตามสภาวะตลาด ณ เวลารัน ผลคือ full regression ผ่านบ้างตกบ้าง
        # และมี artifact จากเทสปนกับงานพร้อมอัปโหลด จึงล็อกทั้งทะเบียน production
        # และตัวรันรอบไว้ที่ fixture deterministic เช่นเดียวกับสไตล์อื่น
        intraday_assets_patcher = mock.patch.object(
            run_daily.intraday_story, "production_assets",
            return_value={"xauusd"})
        self.intraday_assets = intraday_assets_patcher.start()
        self.addCleanup(intraday_assets_patcher.stop)

        intraday_patcher = mock.patch.object(
            run_daily.intraday_pipeline, "run_round",
            return_value={"ok": True, "skipped": [], "articles": [],
                          "states": {"fixture": "NO_NEW_STORY"}})
        self.intraday = intraday_patcher.start()
        self.addCleanup(intraday_patcher.stop)
        forex_patcher = mock.patch.object(
            run_daily.forex_daily_plan, "run_round",
            return_value={"ok": True, "destination": "fx", "errors": [],
                          "assets": {
                              "eurusd": {"readiness": "WAIT"},
                              "gbpusd": {"readiness": "ACTIVE"},
                              "usdjpy": {"readiness": "WAIT"},
                          }})
        self.forex = forex_patcher.start()
        self.addCleanup(forex_patcher.stop)
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
        """ไม่ใส่ธง = สร้างหลักฐานภายใน · A/B/C เป็นชุดเดียวที่ลง output/"""
        code, internal, public, dispatch, calls = self.run_wrapper([])
        self.assertEqual(code, 0)
        dispatch.assert_not_called()
        self.intraday_assets.assert_called_once_with()
        self.intraday.assert_called_once()
        self.forex.assert_called_once()

        (in_args, in_cutoff), _ = internal.call_args
        self.assertEqual(in_args.line, build_daily_package.LINE_INTERNAL)
        self.assertTrue(in_args.no_publish,
                        "สายภายในต้องไม่วางไฟล์ลง output ตามคำสั่ง 2026-08-05")
        (pub_args, pub_cutoff), _ = public.call_args
        self.assertEqual(pub_args.line, build_daily_package.LINE_PUBLIC)
        self.assertFalse(pub_args.no_publish)
        self.assertEqual(in_cutoff, pub_cutoff)
        _, intraday_kwargs = self.intraday.call_args
        self.assertEqual(intraday_kwargs, {
            "asset": "xauusd",
            "publish_root": Path("../output"),
            "cutoff_at": in_cutoff,
        })
        _, forex_kwargs = self.forex.call_args
        self.assertEqual(forex_kwargs, {
            "assets": ["eurusd", "gbpusd", "usdjpy"],
            "publish_root": Path("../output"),
            "cutoff_at": in_cutoff,
        })

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
        self.assertRegex(day_dir.name, r"^\d{2}-\d{2}-\d{4}$")

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

    def test_ธง_publish_internal_เก่าถูกปิดและไม่วางสายภายใน(self):
        code, internal, public, _, _ = self.run_wrapper(["--publish-internal"])
        self.assertEqual(code, 0)
        (in_args, _), _ = internal.call_args
        self.assertTrue(in_args.no_publish)
        (pub_args, _), _ = public.call_args
        self.assertFalse(pub_args.no_publish)

    def test_explicit_internal_line_is_evidence_only(self):
        """แม้สั่ง --line internal ตรง ๆ ก็ต้องเก็บไว้ใน work และไม่วาง output"""
        code, internal, public, dispatch, _ = self.run_wrapper(
            ["--line", "internal", "--asset", "xauusd",
             "--batch-id", "2026-08-06T07-00Z-daily"])
        self.assertEqual(code, 0)
        internal.assert_not_called()
        public.assert_not_called()
        (args, _), _ = dispatch.call_args
        self.assertEqual(args.line, build_daily_package.LINE_INTERNAL)
        self.assertTrue(args.no_publish)
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

    def test_บทเช้าออกทั้ง_F_และ_G_ในวันที่เงื่อนไขครบ_และถอยกลับได้ด้วยธง(self):
        """ผู้ใช้สั่ง 2026-08-13 — วันที่ระบบตอบ G ต้องได้ F ควบมาด้วย

        ล็อกที่ตัวห่อ ไม่ใช่แค่ที่ pipeline เพราะจุดที่เคยเสียคือ "ของถูกต้องแต่ไม่มี
        ใครเรียก" (เดิม F/G ไม่เข้ารอบผลิตเลยทั้งที่โค้ดครบ)
        """
        # วันที่ระบบตอบ F ⇒ ใบเดียวเหมือนเดิม (F ผลิตได้ทุกวัน G ไม่ใช่)
        self.run_wrapper([])
        self.assertEqual(len(self.style_fg.call_args_list), len(build_daily_package.ASSETS))

        # วันที่ระบบตอบ G ⇒ เรียกซ้ำอีกใบต่อหัวข้อ โดยใบที่สองบังคับ F และห้ามลบใบแรก
        self.style_fg.reset_mock()
        self.style_fg.return_value = {"ok": True, "style": brief_story.STYLE_G,
                                      "style_name": "G", "asset": "xauusd",
                                      "folder": "g", "findings": []}
        self.run_wrapper(["--asset", "xauusd"])
        second = self.style_fg.call_args_list[1][1]
        self.assertEqual(len(self.style_fg.call_args_list), 2)
        self.assertEqual(second["style"], brief_story.STYLE_F)
        self.assertTrue(second["keep_other"],
                        "ใบที่สองห้ามกวาดใบแรกทิ้ง ไม่งั้นได้ใบเดียวเหมือนเดิม")

        # ธงถอยกลับ — สไตล์เดียวต่อวันแบบก่อน 2026-08-13
        self.style_fg.reset_mock()
        self.run_wrapper(["--asset", "xauusd", "--fg-single"])
        self.assertEqual(len(self.style_fg.call_args_list), 1)
        self.assertNotIn("keep_other", self.style_fg.call_args_list[0][1])

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

    def test_forex_daily_plan_จำกัดสามคู่_ข้ามได้_และไม่รันในสายภายใน(self):
        self.run_wrapper(["--asset", "eurusd"])
        self.assertEqual(self.forex.call_args.kwargs["assets"], ["eurusd"])

        self.forex.reset_mock()
        self.run_wrapper(["--skip-forex-daily-plan"])
        self.forex.assert_not_called()

        self.run_wrapper(["--line", "internal"])
        self.forex.assert_not_called()

    def test_style_l_cli_รันเฉพาะ_L_และใช้_assets_จากทะเบียน(self):
        self.forex.return_value = {
            "ok": True, "destination": "../output/24-08-2026/L-Forex-Daily",
            "errors": [], "assets": {"usdjpy": {"readiness": "WAIT"}},
        }
        code, internal, public, dispatch, calls = self.run_wrapper(
            ["--style", "L", "--asset", "usdjpy"])

        self.assertEqual(code, 0)
        internal.assert_not_called()
        public.assert_not_called()
        dispatch.assert_not_called()
        self.style_d.assert_not_called()
        self.style_e.assert_not_called()
        self.style_fg.assert_not_called()
        self.intraday_assets.assert_not_called()
        self.intraday.assert_not_called()
        self.forex.assert_called_once()
        self.assertEqual(self.forex.call_args.kwargs["assets"], ["usdjpy"])
        calls["select"].assert_not_called()
        self.assertEqual(calls["guard"], [["../output/24-08-2026/L-Forex-Daily"]])

    def test_style_l_cli_ปฏิเสธ_asset_นอกทะเบียนก่อนรัน(self):
        with self.assertRaises(SystemExit):
            self.run_wrapper(["--style", "L", "--asset", "xauusd"])
        self.forex.assert_not_called()

    def test_forex_daily_plan_fail_closed_ดัน_exit_code(self):
        self.forex.return_value = {"ok": False, "destination": None,
                                   "assets": {}, "errors": ["calendar unavailable"]}
        code, _, public, _, _ = self.run_wrapper([])
        self.assertNotEqual(code, 0)
        public.assert_called_once()

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
