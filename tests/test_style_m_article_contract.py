from __future__ import annotations

import unittest
from copy import deepcopy
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

    def test_four_state_permission_matrix(self):
        for state in ("NO_PLAN", "INVALIDATED", "WAIT_H1_CONFIRM", "PLAN_VALID"):
            with self.subTest(state=state):
                story = self.story(state)
                if state in ("WAIT_H1_CONFIRM", "PLAN_VALID"):
                    story.update({"side": "BUY", "show_plan_geometry": True,
                                  "plan": {"entry_low": 92.0, "entry_high": 92.5,
                                            "sl": 90.0, "tp1": 100.0, "tp2": 108.0,
                                            "rr1": 2.0, "rr2": 4.0}})
                facts = contract.build(story, [])
                self.assertEqual(facts["facts"]["plan.state"]["value"], state)
                if state in ("NO_PLAN", "INVALIDATED"):
                    self.assertEqual(facts["facts"]["plan.sl_tp_rr"]["permission"], "forbidden")
                    self.assertEqual(facts["facts"]["plan.side"]["permission"], "forbidden")
                else:
                    self.assertIn("plan.entry_low", facts["facts"])
                    self.assertIn("plan.tp2", facts["facts"])
                    self.assertEqual(facts["facts"]["plan.side"]["value"], "BUY")
                    self.assertEqual(facts["facts"]["plan.side"]["permission"],
                                     "conditional" if state == "WAIT_H1_CONFIRM" else "allowed")

    def test_duplicate_no_plan_is_hold(self):
        facts = contract.build(self.story(), [])
        result = contract.index_recommendation(facts, facts["semantic_fingerprint"])
        self.assertEqual(result["recommendation"], "HOLD_DUPLICATE_NO_PLAN")
        self.assertFalse(result["index"])

    def test_duplicate_tolerance_is_atr_normalized(self):
        facts = contract.build(self.story(), [])
        inside = deepcopy(facts)
        inside["fingerprint_basis"]["support"]["low"] += 0.20  # exactly 0.10 ATR14
        self.assertEqual(contract.index_recommendation(facts, inside)["recommendation"],
                         "HOLD_DUPLICATE_NO_PLAN")
        outside = deepcopy(facts)
        outside["fingerprint_basis"]["support"]["low"] += 0.21
        self.assertEqual(contract.index_recommendation(facts, outside)["recommendation"], "NEW_DRAFT")

    def test_parity_mutation_blocks_numeric_level(self):
        facts = contract.build(self.story(), [])
        report = contract.parity_report(
            facts, markdown="91.00", render_report={"displayed_fact_ids": ["zone.support.primary"]})
        self.assertEqual(report["status"], "BLOCK")
        self.assertTrue(report["numeric_mismatches"])

    def test_verified_news_is_one_public_advisory(self):
        event = {"event_id": "e1", "title": "Fed", "url": "https://example.test/fed",
                 "time_thai": "29/08 20:00 น."}
        facts = contract.build(self.story(), [], events=[event, dict(event, event_id="e2")])
        self.assertTrue(facts["news"]["public_advisory"])
        self.assertEqual(facts["news"]["selected_event_id"], "e1")


if __name__ == "__main__":
    unittest.main()
