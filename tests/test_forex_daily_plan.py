from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from tools import forex_daily_plan


class ForexDailyPlanContract(unittest.TestCase):

    def test_style_identity_is_l(self):
        self.assertEqual(forex_daily_plan.STYLE_ID, "l_forex_daily_plan")
        self.assertEqual(forex_daily_plan.STYLE_LETTER, "L")
        self.assertEqual(forex_daily_plan.STYLE_NAME,
                         "Style L — Forex Daily Trade Plan")
        self.assertEqual(forex_daily_plan.STYLE_FOLDER, "L-Forex-Daily")

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

    def test_frontmatter_contract_has_exact_seven_fields(self):
        article = """---
asset: usdjpy
title: t
slug: s
excerpt: e
author_slug: a
timeframe: Daily
trend: down
---
"""
        self.assertEqual(forex_daily_plan.frontmatter_keys(article), [
            "asset", "title", "slug", "excerpt", "author_slug", "timeframe", "trend"])

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
