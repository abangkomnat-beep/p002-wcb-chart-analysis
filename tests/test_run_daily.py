"""ล็อกตัวห่อ run_daily — มันต้องส่งค่าตั้งต้นชุดเดียวกับการพิมพ์คำสั่งเต็มเป๊ะ

ตัวห่อไม่มีตรรกะของตัวเอง เทสจึงตรวจอย่างเดียวว่า "ของที่ส่งต่อ" ถูกต้อง:
ไม่ยิงเครือข่าย ไม่เขียนไฟล์ — mock ทั้งสองสายและยาม frontmatter

พฤติกรรมปัจจุบัน: daily route ปิด legacy public line A/B/C ทั้งชุด
ส่วนสายภายในสร้างเฉพาะหลักฐานและแผน ไม่รันตัวเขียน A/B/C หรือ ①②③
"""

from __future__ import annotations

import sys
import tempfile
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
        clock_patch = mock.patch.object(run_daily, "datetime", wraps=datetime)
        clock_mock = clock_patch.start()
        clock_mock.now.return_value = datetime(2026, 9, 9, 3, tzinfo=timezone.utc)
        self.addCleanup(clock_patch.stop)
        patcher = mock.patch.object(
            run_daily.publish_selection, "select",
            return_value={"status": "ready", "asset": "xauusd",
                          "article": "x", "directory": "d"})
        self.select = patcher.start()
        self.addCleanup(patcher.stop)
        purge_patcher = mock.patch.object(
            run_daily.publish_selection, "purge_forbidden_output_files",
            return_value=[])
        self.purge_output = purge_patcher.start()
        self.addCleanup(purge_patcher.stop)
        # The wrapper now normalizes legacy/country-first files on every
        # entrypoint. Keep these unit tests hermetic; integration coverage for
        # the migration helper uses its own tmp_path fixtures.
        migrate_patcher = mock.patch.object(
            run_daily.country_first_output, "migrate_day",
            return_value={"records": [], "migrated": 0})
        migrate_patcher.start()
        self.addCleanup(migrate_patcher.stop)
        repair_patcher = mock.patch.object(
            run_daily.country_first_output, "repair_canonical_day",
            return_value={"records": [], "repaired": 0})
        repair_patcher.start()
        self.addCleanup(repair_patcher.stop)
        queue_patcher = mock.patch.object(
            run_daily.localization_queue, "write_receipt",
            return_value={"selected": [], "held": []})
        queue_patcher.start()
        self.addCleanup(queue_patcher.stop)
        queue_dry_patcher = mock.patch.object(
            run_daily.localization_queue, "select",
            return_value={"selected": [], "held": []})
        queue_dry_patcher.start()
        self.addCleanup(queue_dry_patcher.stop)
        dispatch_patcher = mock.patch.object(
            run_daily.normal_localization_orchestrator, "run",
            return_value={"status": "ALREADY_DELIVERED"})
        dispatch_patcher.start()
        self.addCleanup(dispatch_patcher.stop)
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
        style_e_plus_patcher = mock.patch(
            "tools.e_unified_adapter.style_e_plus_daily.run",
            return_value={"status": "pass", "asset": "btcusd", "char_count": 3900,
                          "directory": "eplus", "findings": [],
                          "variant": "e_plus_h1_m15", "images": ["h1", "m15"]})
        self.style_e_plus = style_e_plus_patcher.start()
        self.addCleanup(style_e_plus_patcher.stop)
        # Style M replaces E+ only in the default BTCUSD daily route. Mock the
        # adapter so wrapper tests never fetch market/news data or write files.
        self.style_m = mock.Mock()
        self.style_m.assets = ("btcusd",)
        self.style_m.production = True
        self.style_m.run_round.return_value = {
            "status": "pass", "state": "NO_PLAN", "published": True,
            "directory": "m", "lane": "m-lane",
        }
        style_m_patcher = mock.patch.object(
            run_daily.MProductionRoute, "load", return_value=self.style_m)
        style_m_patcher.start()
        self.addCleanup(style_m_patcher.stop)
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
        schedule_patcher = mock.patch.object(
            run_daily.forex_daily_plan, "scheduled_assets",
            return_value=["gbpusd", "usdcad"])
        self.schedule = schedule_patcher.start()
        self.addCleanup(schedule_patcher.stop)
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

    def test_default_disables_legacy_abc_public_line(self):
        """ไม่ใส่ธง = สร้างหลักฐานภายในและสาย D/E/M/L แต่ไม่เรียก A/B/C"""
        code, internal, public, dispatch, calls = self.run_wrapper([])
        self.assertEqual(code, 0)
        dispatch.assert_not_called()
        public.assert_not_called()
        self.intraday_assets.assert_not_called()
        self.intraday.assert_not_called()
        self.forex.assert_called_once()

        (in_args, in_cutoff), _ = internal.call_args
        self.assertEqual(in_args.line, build_daily_package.LINE_INTERNAL)
        self.assertTrue(in_args.no_publish,
                        "สายภายในต้องไม่วางไฟล์ลง output ตามคำสั่ง 2026-08-05")
        _, forex_kwargs = self.forex.call_args
        self.assertEqual(forex_kwargs, {
            "assets": ["eurusd", "usdjpy"],
            "publish_root": Path("../output"),
            "cutoff_at": in_cutoff,
        })

        # ค่าตั้งต้นสายหลักฐานต้องตรง parser ของ build_daily_package
        self.assertEqual(in_args.asset, ["xauusd", "btcusd"])
        self.assertEqual(in_args.output_root, Path("../work/build"))
        self.assertEqual(in_args.publish_root, Path("../output"))
        self.assertIsNone(in_args.snapshot)
        self.assertIsNone(in_args.source)
        self.assertEqual(in_args.max_bar_age_days,
                         build_daily_package.wcb_series_source.MAX_BAR_AGE_DAYS)
        self.assertFalse(in_args.no_news)
        self.assertFalse(in_args.no_trade_plan)
        self.assertEqual(in_args.cutoff_at, in_cutoff)
        # ยังตรวจทั้งตัวรีโปและ output แต่ไม่มี legacy public line ให้เรียก
        self.assertEqual(calls["guard"], [["."], ["../output"]])
        # ใบขึ้นเว็บต้องถูกเลือกจากโฟลเดอร์วันของรอบนี้ ไม่ใช่ path ที่พิมพ์ไว้ตายตัว
        (day_dir,), _ = calls["select"].call_args
        self.assertEqual(day_dir.parent, Path("../output"))
        self.assertRegex(day_dir.name, r"^\d{2}-\d{2}-\d{4}$")
        self.purge_output.assert_called_once_with(day_dir)

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
        public.assert_not_called()
        (in_args, _), _ = internal.call_args
        self.assertTrue(in_args.no_publish)

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

    def test_default_uses_only_scheduled_production_lanes(self):
        """วันพุธปล่อย E/M/L ที่กำหนด และไม่เรียก D/F/G/H/I/J."""
        with mock.patch.object(run_daily.DProductionRoute, "load") as d_load, \
                mock.patch.object(run_daily.FProductionRoute, "load") as f_load, \
                mock.patch.object(run_daily.GProductionRoute, "load") as g_load, \
                mock.patch.object(run_daily.HIJProductionRoute, "load") as hij_load:
            self.run_wrapper([])
        d_load.assert_not_called()
        f_load.assert_not_called()
        g_load.assert_not_called()
        hij_load.assert_not_called()
        self.style_d.assert_not_called()
        self.style_fg.assert_not_called()
        self.intraday.assert_not_called()
        self.assertEqual([kwargs["asset"] for _, kwargs in self.style_e.call_args_list],
                         ["xauusd"])
        self.style_e_plus.assert_not_called()
        self.style_m.run_round.assert_called_once()
        self.assertEqual(self.style_m.run_round.call_args.kwargs["asset"], "btcusd")

    def test_dry_run_has_no_pipeline_side_effects(self):
        code, internal, public, dispatch, calls = self.run_wrapper(["--dry-run"])
        self.assertEqual(code, 0)
        internal.assert_not_called()
        public.assert_not_called()
        dispatch.assert_not_called()
        self.style_d.assert_not_called()
        self.style_e.assert_not_called()
        self.style_m.run_round.assert_not_called()
        self.forex.assert_not_called()
        calls["select"].assert_not_called()

        for style in (self.style_d, self.style_e, self.style_e_plus, self.style_fg):
            style.reset_mock()
        self.style_m.run_round.reset_mock()
        self.run_wrapper(["--skip-style-d", "--skip-style-e", "--skip-style-fg"])
        self.style_d.assert_not_called()
        self.style_e.assert_not_called()
        self.style_e_plus.assert_not_called()
        self.style_fg.assert_not_called()
        self.style_m.run_round.assert_called_once()

        self.style_m.run_round.reset_mock()
        self.run_wrapper(["--line", "internal"])
        self.style_d.assert_not_called()
        self.style_e.assert_not_called()
        self.style_e_plus.assert_not_called()
        self.style_fg.assert_not_called()
        self.style_m.run_round.assert_not_called()

        # จำกัดหัวข้อ Forex = สายอื่นไม่ถูกเรียกตาม L-only contract
        self.forex.reset_mock()
        self.run_wrapper(["--asset", "eurusd"])
        self.style_d.assert_not_called()
        self.style_fg.assert_not_called()
        self.forex.assert_called_once()
        self.assertEqual(self.forex.call_args.kwargs["assets"], ["eurusd"])
        self.style_e.assert_not_called()
        self.style_e_plus.assert_not_called()
        self.style_m.run_round.assert_not_called()

    def test_บทเช้าออกทั้ง_F_และ_G_เมื่อเปิด_experimental_ชัดเจน(self):
        """ผู้ใช้สั่ง 2026-08-13 — วันที่ระบบตอบ G ต้องได้ F ควบมาด้วย

        ล็อกที่ตัวห่อ ไม่ใช่แค่ที่ pipeline เพราะจุดที่เคยเสียคือ "ของถูกต้องแต่ไม่มี
        ใครเรียก" (เดิม F/G ไม่เข้ารอบผลิตเลยทั้งที่โค้ดครบ)
        """
        # วันที่ระบบตอบ F ⇒ ใบเดียวเหมือนเดิม (F ผลิตได้ทุกวัน G ไม่ใช่)
        self.run_wrapper(["--include-experimental", "--asset", "xauusd"])
        self.assertEqual(len(self.style_fg.call_args_list), 1)

        # วันที่ระบบตอบ G ⇒ เรียกซ้ำอีกใบต่อหัวข้อ โดยใบที่สองบังคับ F และห้ามลบใบแรก
        self.style_fg.reset_mock()
        self.style_fg.return_value = {"ok": True, "style": brief_story.STYLE_G,
                                      "style_name": "G", "asset": "xauusd",
                                      "folder": "g", "findings": []}
        self.run_wrapper(["--include-experimental", "--asset", "xauusd"])
        second = self.style_fg.call_args_list[1][1]
        self.assertEqual(len(self.style_fg.call_args_list), 2)
        self.assertEqual(second["style"], brief_story.STYLE_F)
        self.assertTrue(second["keep_other"],
                        "ใบที่สองห้ามกวาดใบแรกทิ้ง ไม่งั้นได้ใบเดียวเหมือนเดิม")

        # ธงถอยกลับ — สไตล์เดียวต่อวันแบบก่อน 2026-08-13
        self.style_fg.reset_mock()
        self.run_wrapper(["--include-experimental", "--asset", "xauusd", "--fg-single"])
        self.assertEqual(len(self.style_fg.call_args_list), 1)
        self.assertNotIn("keep_other", self.style_fg.call_args_list[0][1])

    def test_สไตล์เสริมตกด่านต้องดัน_exit_code_ไม่เป็นศูนย์(self):
        """สายเสริมล้มห้ามกลืนเงียบ — แต่ก็ห้ามพาสายหลักล้มตาม (ยังรันครบ)"""
        self.style_e.return_value = {"status": "fail", "asset": "xauusd",
                                     "char_count": 0, "directory": "e",
                                     "findings": [{"rule": "x"}]}
        code, _, public, _, _ = self.run_wrapper([])
        self.assertNotEqual(code, 0)
        public.assert_not_called()

        self.style_e.side_effect = RuntimeError("แหล่งข้อมูลล่ม")
        code, _, public, _, _ = self.run_wrapper([])
        self.assertNotEqual(code, 0)
        public.assert_not_called()

    def test_explicit_public_line_also_disables_legacy_abc(self):
        code, internal, public, dispatch, _ = self.run_wrapper(["--line", "public"])
        self.assertEqual(code, 0)
        internal.assert_not_called()
        public.assert_not_called()
        dispatch.assert_not_called()

    def test_skip_guard(self):
        code, _, _, _, calls = self.run_wrapper(["--skip-guard"])
        self.assertEqual(code, 0)
        self.assertEqual(calls["guard"], [])

    def test_skip_guard_never_finalizes_continuity(self):
        with mock.patch.object(run_daily.publish_selection, "finalize_continuity") as finalize:
            code, _, _, _, _ = self.run_wrapper(["--skip-guard"])
        self.assertEqual(code, 0)
        finalize.assert_not_called()

    def test_build_failure_never_finalizes_continuity(self):
        self.style_e.return_value = {"status": "fail", "asset": "xauusd",
                                     "char_count": 0, "directory": "e", "findings": []}
        with mock.patch.object(run_daily.publish_selection, "finalize_continuity") as finalize:
            code, _, _, _, _ = self.run_wrapper([])
        self.assertNotEqual(code, 0)
        finalize.assert_not_called()

    def test_partial_selection_fails_closed_without_baseline(self):
        self.select.return_value = {"status": "partial", "reason": "missing lane",
                                     "expected": "fixture"}
        with mock.patch.object(run_daily.publish_selection, "finalize_continuity") as finalize:
            code, _, _, _, _ = self.run_wrapper([])
        self.assertNotEqual(code, 0)
        finalize.assert_not_called()

    def test_ready_selection_finalizes_once_after_all_gates(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "selection.json"
            report.write_text("{}", encoding="utf-8")
            self.select.return_value = {
                "status": "ready", "article": "fixture", "directory": temporary,
                "selection_report": str(report), "lanes": [{"id": "fixture"}],
            }
            with mock.patch.object(run_daily.publish_selection, "finalize_continuity",
                                   return_value={"status": "recorded"}) as finalize:
                code, _, _, _, _ = self.run_wrapper([])
        self.assertEqual(code, 0)
        finalize.assert_called_once()

    def test_forex_daily_plan_ตามตาราง_ข้ามได้_และไม่รันในสายภายใน(self):
        self.run_wrapper(["--asset", "eurusd"])
        self.assertEqual(self.forex.call_args.kwargs["assets"], ["eurusd"])

        self.forex.reset_mock()
        self.run_wrapper([])
        self.forex.assert_called_once()
        self.assertEqual(self.forex.call_args.kwargs["assets"],
                         ["eurusd", "usdjpy"])

        self.forex.reset_mock()
        self.run_wrapper(["--skip-forex-daily-plan"])
        self.forex.assert_not_called()

        self.run_wrapper(["--line", "internal"])
        self.forex.assert_not_called()

    def test_schedule_contract_เสีย_หยุดก่อนรันสายข้อมูลและ_style_l(self):
        with mock.patch.object(run_daily, "scheduled_lane_plan",
                               side_effect=run_daily.SourceSelectorError("fixture malformed schedule")):
            code, internal, public, dispatch, _ = self.run_wrapper([])

        self.assertNotEqual(code, 0)
        internal.assert_not_called()
        public.assert_not_called()
        dispatch.assert_not_called()
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

    def test_style_l_cli_ไม่ระบุ_asset_ส่งสองคู่เป็น_batch_เดียว(self):
        self.forex.return_value = {
            "ok": True, "destination": "../output/27-08-2026/L-Forex-Daily",
            "errors": [],
            "assets": {
                "gbpusd": {"readiness": "WAIT"},
                "usdcad": {"readiness": "WAIT",
                            "web_import_status": "HOLD_UNREGISTERED_ASSET"},
            },
        }
        code, internal, public, dispatch, _ = self.run_wrapper(["--style", "L"])

        self.assertEqual(code, 0)
        internal.assert_not_called()
        public.assert_not_called()
        dispatch.assert_not_called()
        self.schedule.assert_not_called()
        self.forex.assert_called_once()
        self.assertEqual(self.forex.call_args.kwargs["assets"],
                         ["eurusd", "usdjpy"])

    def test_style_l_cli_วันหยุดข้ามโดยไม่เรียก_batch(self):
        with mock.patch.object(run_daily, "scheduled_lane_plan", return_value={}):
            code, internal, public, dispatch, _ = self.run_wrapper(["--style", "L"])

        self.assertEqual(code, 0)
        internal.assert_not_called()
        public.assert_not_called()
        dispatch.assert_not_called()
        self.forex.assert_not_called()

    def test_style_l_cli_usdcad_hold_ไม่ส่ง_none_เข้ายาม_frontmatter(self):
        self.forex.return_value = {
            "ok": True, "destination": None, "errors": [],
            "assets": {"usdcad": {"readiness": "WAIT",
                                      "web_import_status": "HOLD_UNREGISTERED_ASSET"}},
        }
        code, _, _, _, calls = self.run_wrapper(
            ["--style", "L", "--asset", "usdcad", "--include-experimental"])

        self.assertEqual(code, 0)
        self.forex.assert_called_once()
        self.assertEqual(calls["guard"], [])

    def test_style_e_cli_ปิด_Eplus_สำหรับ_btcusd(self):
        with self.assertRaises(SystemExit):
            self.run_wrapper(["--style", "E", "--asset", "btcusd"])
        self.style_e_plus.assert_not_called()
        self.style_e.assert_not_called()

    def test_style_m_cli_รันเฉพาะ_M_และไม่เรียก_Eplus(self):
        code, internal, public, dispatch, calls = self.run_wrapper(
            ["--style", "M", "--asset", "btcusd"])
        self.assertEqual(code, 0)
        internal.assert_not_called()
        public.assert_not_called()
        dispatch.assert_not_called()
        self.style_m.run_round.assert_called_once()
        self.style_e_plus.assert_not_called()
        self.style_e.assert_not_called()
        self.style_d.assert_not_called()
        self.style_fg.assert_not_called()
        self.intraday.assert_not_called()
        self.forex.assert_not_called()
        calls["select"].assert_not_called()
        self.assertEqual(calls["guard"], [["m"]])

    def test_style_m_cli_ปฏิเสธ_internal_ก่อนโหลด_route(self):
        with self.assertRaises(SystemExit):
            self.run_wrapper(["--style", "M", "--line", "internal"])
        self.style_m.run_round.assert_not_called()

    def test_style_l_cli_ปฏิเสธ_asset_นอกทะเบียนก่อนรัน(self):
        with self.assertRaises(SystemExit):
            self.run_wrapper(["--style", "L", "--asset", "xauusd"])
        self.forex.assert_not_called()

    def test_forex_daily_plan_fail_closed_ดัน_exit_code(self):
        self.forex.return_value = {"ok": False, "destination": None,
                                   "assets": {}, "errors": ["calendar unavailable"]}
        code, _, public, _, _ = self.run_wrapper([])
        self.assertNotEqual(code, 0)
        public.assert_not_called()

    def test_failure_codes_surface(self):
        """สายไหนตกหรือยามตกต้องดันให้ exit code ไม่เป็นศูนย์ — ห้ามกลืนเงียบ"""
        with mock.patch.object(build_daily_package, "run_internal_line", return_value=1), \
                mock.patch.object(build_daily_package, "run_public_line", return_value=0), \
                mock.patch.object(run_daily.frontmatter_guard, "main", return_value=0):
            self.assertNotEqual(run_daily.main([]), 0)
        with mock.patch.object(build_daily_package, "run_internal_line", return_value=0), \
                mock.patch.object(build_daily_package, "run_public_line", return_value=1), \
                mock.patch.object(run_daily.frontmatter_guard, "main", return_value=0):
            # legacy public A/B/C ถูกปิด จึงไม่มี exit code จาก mock ที่ไม่ถูกเรียก
            self.assertEqual(run_daily.main([]), 0)
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
