from __future__ import annotations

import unittest
from datetime import datetime

from tools import style_m_article_contract as contract
from tools import style_m_story


class StyleMArticleContract(unittest.TestCase):
    def story(self, state="NO_PLAN"):
        return {
            "schema": style_m_story.SCHEMA, "asset": "btcusd", "timeframe": "1h",
            "cutoff": "2026-08-29T11:00:00+07:00",
            "latest": {"at": "2026-08-29 10:00:00", "close": 100.0},
            "indicators": {"ema20": 101.0, "ema50": 100.0, "atr14": 2.0},
            "pivots": {"highs": [{"index": 70, "at": "2026-08-28 12:00:00", "price": 110.0},
                                  {"index": 90, "at": "2026-08-29 08:00:00", "price": 108.0}],
                       "lows": [{"index": 60, "at": "2026-08-28 02:00:00", "price": 90.0},
                                {"index": 85, "at": "2026-08-29 03:00:00", "price": 92.0}]},
            "source_sha256": "a" * 64, "state": state, "side": None,
            "reason_code": "STRUCTURE_CONFLICT", "reason": "conflict",
            "show_plan_geometry": False, "plan": None,
        }

    def test_manifest_has_stable_schema_and_occupancy_meaning(self):
        facts = contract.build(self.story(), [])
        self.assertEqual(facts["schema"], "style-m-article-visual-facts/v1")
        self.assertEqual(facts["contract_version"], "M-PROD/v4")
        self.assertFalse(facts["facts"]["occupancy.price_bins"]["source_volume_available"])
        self.assertEqual(facts["facts"]["occupancy.price_bins"]["count"], 72)
        self.assertEqual(facts["web_routes"], {"primary": "/thailand/asset-btc",
                                                "secondary": "/thailand/analysis"})

    def test_no_plan_forbids_trade_geometry(self):
        facts = contract.build(self.story(), [])
        self.assertEqual(facts["facts"]["plan.entry"]["permission"], "forbidden")
        self.assertEqual(facts["facts"]["plan.sl_tp_rr"]["permission"], "forbidden")

    def test_duplicate_no_plan_is_hold(self):
        facts = contract.build(self.story(), [])
        result = contract.index_recommendation(facts, facts["semantic_fingerprint"])
        self.assertEqual(result["recommendation"], "HOLD_DUPLICATE_NO_PLAN")
        self.assertFalse(result["index"])

    def test_verified_news_is_one_public_advisory(self):
        event = {"event_id": "e1", "title": "Fed", "url": "https://example.test/fed",
                 "time_thai": "29/08 20:00 น."}
        facts = contract.build(self.story(), [], events=[event, dict(event, event_id="e2")])
        self.assertTrue(facts["news"]["public_advisory"])
        self.assertEqual(facts["news"]["selected_event_id"], "e1")


if __name__ == "__main__":
    unittest.main()
