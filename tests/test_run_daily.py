"""ล็อกตัวห่อ run_daily — มันต้องส่งค่าตั้งต้นชุดเดียวกับการพิมพ์คำสั่งเต็มเป๊ะ

ตัวห่อไม่มีตรรกะของตัวเอง เทสจึงตรวจอย่างเดียวว่า "ของที่ส่งต่อ" ถูกต้อง:
ไม่ยิงเครือข่าย ไม่เขียนไฟล์ — mock ทั้ง dispatch และยาม frontmatter
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
    def run_wrapper(self, argv):
        calls = {"guard": []}
        with mock.patch.object(build_daily_package, "dispatch", return_value=0) as dispatch, \
                mock.patch.object(run_daily.frontmatter_guard, "main",
                                  side_effect=lambda a: calls["guard"].append(a) or 0):
            code = run_daily.main(argv)
        return code, dispatch, calls

    def test_default_run_matches_full_command(self):
        """ไม่ใส่ธงอะไรเลย = --line both ครบสี่หัวข้อ + ค่าตั้งต้นเดิมทุกช่อง"""
        code, dispatch, calls = self.run_wrapper([])
        self.assertEqual(code, 0)
        (args, cutoff), _ = dispatch.call_args
        self.assertEqual(args.line, build_daily_package.LINE_BOTH)
        self.assertEqual(args.asset, sorted(build_daily_package.ASSETS))
        # ค่าตั้งต้นต้องตรงกับ parser ของ build_daily_package — เปลี่ยนที่โน่นต้องเปลี่ยนที่นี่
        self.assertEqual(args.output_root, Path("../work/build"))
        self.assertEqual(args.publish_root, Path("../output"))
        self.assertFalse(args.no_publish)
        self.assertIsNone(args.snapshot)
        self.assertIsNone(args.source)
        self.assertEqual(args.max_bar_age_days,
                         build_daily_package.wcb_series_source.MAX_BAR_AGE_DAYS)
        self.assertFalse(args.no_news)
        self.assertFalse(args.no_trade_plan)
        self.assertEqual(args.cutoff_at, cutoff)
        # ยามต้องถูกเรียกสองที่เหมือนขั้นตอนเดิมก่อนส่งของ
        self.assertEqual(calls["guard"], [["."], ["../output"]])

    def test_flags_pass_through(self):
        code, dispatch, calls = self.run_wrapper(
            ["--asset", "xauusd", "--line", "internal",
             "--batch-id", "2026-08-06T07-00Z-daily", "--skip-guard"])
        self.assertEqual(code, 0)
        (args, _), _ = dispatch.call_args
        self.assertEqual(args.asset, ["xauusd"])
        self.assertEqual(args.line, build_daily_package.LINE_INTERNAL)
        self.assertEqual(args.batch_id, "2026-08-06T07-00Z-daily")
        self.assertEqual(calls["guard"], [])

    def test_failure_codes_surface(self):
        """สายท่อหรือยามตกต้องดันให้ exit code ไม่เป็นศูนย์ — ห้ามกลืนเงียบ"""
        with mock.patch.object(build_daily_package, "dispatch", return_value=1), \
                mock.patch.object(run_daily.frontmatter_guard, "main", return_value=0):
            self.assertNotEqual(run_daily.main([]), 0)
        with mock.patch.object(build_daily_package, "dispatch", return_value=0), \
                mock.patch.object(run_daily.frontmatter_guard, "main", return_value=1):
            self.assertNotEqual(run_daily.main([]), 0)

    def test_batch_id_is_folder_safe(self):
        stamp = run_daily.default_batch_id(
            datetime(2026, 8, 6, 7, 5, tzinfo=timezone.utc))
        self.assertEqual(stamp, "2026-08-06T07-05Z-daily")
        self.assertNotIn(":", stamp)


if __name__ == "__main__":
    unittest.main()
