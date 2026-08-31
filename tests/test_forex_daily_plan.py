from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from tools import forex_daily_plan
from tools.unified_registry import RegistryLoader


class ForexDailyPlanContract(unittest.TestCase):

    def test_style_identity_is_l(self):
        self.assertEqual(forex_daily_plan.STYLE_ID, "l_forex_daily_plan")
        self.assertEqual(forex_daily_plan.STYLE_LETTER, "L")
        self.assertEqual(forex_daily_plan.STYLE_NAME,
                         "Style L — Forex Daily Trade Plan")
        self.assertEqual(forex_daily_plan.STYLE_FOLDER, "L-Forex-Daily")

    def test_weekday_schedule_is_exactly_five_pairs(self):
        self.assertEqual(forex_daily_plan.ASSETS,
                         ("eurusd", "gbpusd", "usdjpy", "audusd", "usdcad"))
        self.assertEqual(
            [forex_daily_plan.scheduled_asset(datetime(2026, 8, day, 5, 0,
                                                        tzinfo=timezone.utc))
             for day in range(24, 29)],
            ["usdjpy", "eurusd", "gbpusd", "audusd", "usdcad"])

    def test_weekend_schedule_skips(self):
        self.assertIsNone(forex_daily_plan.scheduled_asset(
            datetime(2026, 8, 29, 5, 0, tzinfo=timezone.utc)))
        self.assertIsNone(forex_daily_plan.scheduled_asset(
            datetime(2026, 8, 30, 5, 0, tzinfo=timezone.utc)))

    def test_relevant_events_include_aud_and_cad(self):
        events = [
            {"country": "AUD", "title": "RBA", "impact": "High",
             "at": "2026-08-28 08:00"},
            {"country": "CAD", "title": "BoC", "impact": "High",
             "at": "2026-08-28 09:00"},
            {"country": "USD", "title": "CPI", "impact": "High",
             "at": "2026-08-28 10:00"},
            {"country": "JPY", "title": "BoJ", "impact": "High",
             "at": "2026-08-28 11:00"},
        ]
        cutoff = datetime(2026, 8, 28, 5, 0, tzinfo=timezone.utc)
        self.assertEqual([row["title"] for row in forex_daily_plan.relevant_events(
            "audusd", events, cutoff)], ["RBA", "CPI"])
        self.assertEqual([row["title"] for row in forex_daily_plan.relevant_events(
            "usdcad", events, cutoff)], ["BoC", "CPI"])

    def test_style_l_is_registered_for_production(self):
        registry = RegistryLoader().load(
            Path(__file__).resolve().parents[1] / "config" / "article_styles.json")
        entry = registry.styles[forex_daily_plan.STYLE_ID]
        unit = registry.execution_units[entry.execution_unit]

        self.assertEqual(entry.letter, forex_daily_plan.STYLE_LETTER)
        self.assertEqual(entry.adapter, "forex_daily_plan")
        self.assertEqual(entry.assets, forex_daily_plan.ASSETS)
        self.assertEqual(entry.timeframes, forex_daily_plan.TIMEFRAMES)
        self.assertTrue(entry.production)
        self.assertEqual(unit.members, (forex_daily_plan.STYLE_ID,))
        self.assertFalse(unit.execute_once_per_asset)

    def test_h4_inset_is_removed_only_from_usdjpy(self):
        self.assertFalse(forex_daily_plan.h4_inset_enabled("usdjpy"))
        self.assertTrue(forex_daily_plan.h4_inset_enabled("eurusd"))
        self.assertTrue(forex_daily_plan.h4_inset_enabled("gbpusd"))

    def test_news_is_combined_in_one_table(self):
        cutoff = datetime(2026, 8, 21, 5, 0, tzinfo=timezone.utc)
        events = [
            {"country": "JPY", "at": "2026-08-21 07:30", "title": "ข่าวเช้า",
             "actual": "52.0", "previous": "51.0"},
            {"country": "USD", "at": "2026-08-21 21:00", "title": "ข่าวค่ำ",
             "forecast": "1.0", "previous": "0.8"},
        ]
        rows, next_event = forex_daily_plan.event_sections(events, cutoff)
        self.assertEqual(len(rows), 2)
        self.assertIn("ประกาศแล้ว", rows[0])
        self.assertIn("รอติดตาม", rows[1])
        self.assertIn("ข่าวค่ำ", next_event)

    def test_removed_copy_is_detected(self):
        for phrase in forex_daily_plan.DEPRECATED_COPY:
            with self.subTest(phrase=phrase):
                self.assertEqual(forex_daily_plan.deprecated_copy_in(phrase), [phrase])
        self.assertEqual(forex_daily_plan.deprecated_copy_in("เนื้อหาใหม่"), [])

    def test_paragraph_indent_uses_em_space_entity(self):
        self.assertEqual(forex_daily_plan.indent_paragraph("ย่อหน้า"),
                         "&emsp;ย่อหน้า")
        self.assertEqual(forex_daily_plan.indent_paragraph("&emsp;ย่อหน้า"),
                         "&emsp;ย่อหน้า")

    def test_internal_chart_links_use_live_relative_routes(self):
        expected = {
            "usdjpy": "/thailand/asset-usdjpy",
            "eurusd": "/thailand/asset-eurusd",
            "gbpusd": "/thailand/asset-gbpusd",
            "audusd": "/thailand/asset-audusd",
            "usdcad": "/thailand/asset-hub",
        }
        for asset, path in expected.items():
            with self.subTest(asset=asset):
                text = forex_daily_plan.internal_chart_links(asset)
                ticker = forex_daily_plan.wcb_source.profile_for(
                    asset)["symbol"].replace("/", "")
                self.assertTrue(text.startswith("&emsp;"))
                self.assertIn(f"ติดตามราคา {ticker} แบบเรียลไทม์", text)
                self.assertIn(f"]({path})", text)
                if path != forex_daily_plan.ASSET_HUB_PATH:
                    self.assertIn(f"[หน้าราคา {ticker}]({path})", text)
                self.assertIn("](/thailand/analysis)", text)
                self.assertNotIn("http://", text)
                self.assertNotIn("https://", text)

    def test_closed_bar_contract_accepts_wait_and_active_wording(self):
        self.assertTrue(forex_daily_plan.has_closed_bar_confirmation(
            "M30 ต้องผ่านครบก่อน และ M15 ต้องปิดเหนือ trigger"))
        self.assertTrue(forex_daily_plan.has_closed_bar_confirmation(
            "M30 ผ่านกฎฝั่ง BUY แล้ว และ M15 ปิดเบรกกรอบแล้ว"))
        self.assertFalse(forex_daily_plan.has_closed_bar_confirmation(
            "M30 ผ่านกฎฝั่ง BUY แล้ว แต่ M15 แตะ trigger ระหว่างแท่ง"))

    def test_friday_expiry_does_not_carry_to_monday(self):
        friday = datetime(2026, 8, 28, 3, 0, tzinfo=timezone.utc)
        monday = datetime(2026, 8, 31, 3, 0, tzinfo=timezone.utc)
        notice = forex_daily_plan.friday_expiry_notice(friday)
        self.assertIn("ไม่ถือสถานะหรือเงื่อนไขเดิมข้ามไปวันจันทร์", notice)
        self.assertIsNone(forex_daily_plan.friday_expiry_notice(monday))

    def test_frontmatter_contract_has_exact_ten_fields(self):
        article = """---
asset: usdjpy
title: t
slug: s
excerpt: e
author_slug: a
timeframe: Daily
trend: down
status: draft
country: thailand
language: th
---
"""
        self.assertEqual(forex_daily_plan.frontmatter_keys(article), [
            "asset", "title", "slug", "excerpt", "author_slug", "timeframe", "trend",
            "status", "country", "language"])

    def test_usdcad_is_held_out_of_web_import_until_registered(self):
        self.assertFalse(forex_daily_plan.web_import_eligible("usdcad"))
        for asset in ("eurusd", "gbpusd", "usdjpy", "audusd"):
            with self.subTest(asset=asset):
                self.assertTrue(forex_daily_plan.web_import_eligible(asset))

        files = [Path("staging/usdjpy/usdjpy.md"), Path("staging/usdcad/usdcad.md")]
        self.assertEqual(forex_daily_plan.web_import_sources(files), [files[0]])

    def test_calendar_failure_is_fail_closed_before_market_fetch(self):
        cutoff = datetime(2026, 8, 21, 5, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with mock.patch.object(forex_daily_plan, "REPO", root), \
                    mock.patch.object(forex_daily_plan, "STATE", root / "state"), \
                    mock.patch.object(
                        forex_daily_plan, "fetch_events",
                        return_value=([], {"status": "unavailable", "reason": "fixture"})), \
                    mock.patch.object(forex_daily_plan, "closed_intraday") as market:
                result = forex_daily_plan.run_round(
                    assets=["usdjpy"], publish_root=root / "output", cutoff_at=cutoff)
        self.assertFalse(result["ok"])
        self.assertIn("calendar feed unavailable", result["errors"][0])
        market.assert_not_called()

    def test_naive_cutoff_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            forex_daily_plan.parse_cutoff("2026-08-21T12:00:00")


if __name__ == "__main__":
    unittest.main()
