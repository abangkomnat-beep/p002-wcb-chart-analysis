"""เทส level engine กติกา target และด่านสิทธิ์ข้อมูล"""

import json
import sys
import unittest
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import integrity, levels as level_engine, license_gate  # noqa: E402


def load_report(fixture: str, asset: str) -> dict:
    rows = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))["rows"]
    return integrity.assess(rows, asset, calculated_at="2026-08-03T06:30:00Z")


class LevelEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = load_report("xau_valid_120_sessions.json", "xauusd")
        cls.level_map = level_engine.build_level_map(cls.report)

    def test_pivot_is_not_the_only_source(self):
        kinds = {level["type"] for level in self.level_map["levels"]}

        self.assertIn("pivot", kinds)
        self.assertIn("previous_day", kinds)
        self.assertIn("previous_week", kinds)
        self.assertIn("moving_average", kinds)
        self.assertIn("atr_projection", kinds)

    def test_every_level_carries_its_source(self):
        for level in self.level_map["levels"]:
            with self.subTest(level=level["id"]):
                self.assertTrue(level["source_field"])
                self.assertTrue(level["calculation_method"])
                self.assertIsNotNone(level["basis_timestamp"])

    def test_close_levels_are_merged_into_a_zone(self):
        zones = [item for item in self.level_map["zones"] if item["type"] == "zone"]

        self.assertTrue(zones, "ควรมีอย่างน้อยหนึ่งโซนจากระดับ Pivot ที่ชิดกัน")
        for zone in zones:
            self.assertLess(zone["zone_low"], zone["zone_high"])
            self.assertGreaterEqual(len(zone["members"]), 2)

    def test_moving_average_level_appears_only_when_approved(self):
        short = load_report("xau_5_points_with_weekend.json", "xauusd")
        level_map = level_engine.build_level_map(short)
        kinds = {level["type"] for level in level_map["levels"]}

        self.assertNotIn("moving_average", kinds)
        self.assertNotIn("atr_projection", kinds)


class TargetRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = load_report("xau_valid_120_sessions.json", "xauusd")
        cls.level_map = level_engine.build_level_map(cls.report)
        cls.zones = cls.level_map["zones"]

    def test_text_target_is_rejected(self):
        result = level_engine.validate_target("follow-through above R3", self.zones)

        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "no_numeric_target")

    def test_target_on_an_approved_level_passes(self):
        approved = self.level_map["approved_values"][0]
        result = level_engine.validate_target(approved, self.zones)

        self.assertTrue(result["valid"])
        self.assertTrue(result["matched_level"])

    def test_invented_target_is_rejected(self):
        result = level_engine.validate_target(999999.0, self.zones)

        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "target_not_in_approved_levels")

    def test_no_target_becomes_watchlist(self):
        scenario = level_engine.classify_scenario(
            target=None, invalidation=4000.0, levels=self.zones, has_intraday=True
        )

        self.assertEqual(scenario["classification"], level_engine.WATCHLIST)
        self.assertFalse(scenario["executable"])
        self.assertEqual(scenario["reason"], "no_approved_target")

    def test_without_intraday_data_it_stays_a_daily_scenario(self):
        approved = self.level_map["approved_values"][0]
        scenario = level_engine.classify_scenario(
            target=approved, invalidation=3900.0, levels=self.zones, has_intraday=False
        )

        self.assertEqual(scenario["classification"], level_engine.DAILY_SCENARIO)
        self.assertFalse(scenario["executable"])
        self.assertIn("เข้า Buy ตรงนี้", scenario["forbidden_language"])

    def test_complete_setup_with_intraday_is_executable(self):
        approved = self.level_map["approved_values"][0]
        scenario = level_engine.classify_scenario(
            target=approved, invalidation=3900.0, levels=self.zones,
            has_h4=True, has_intraday=True,
        )

        self.assertEqual(scenario["classification"], level_engine.TRADE_SETUP)
        self.assertTrue(scenario["executable"])

    def test_missing_invalidation_becomes_watchlist(self):
        approved = self.level_map["approved_values"][0]
        scenario = level_engine.classify_scenario(
            target=approved, invalidation=None, levels=self.zones, has_intraday=True
        )

        self.assertEqual(scenario["classification"], level_engine.WATCHLIST)
        self.assertEqual(scenario["reason"], "no_invalidation")


class LicenseGateTests(unittest.TestCase):
    def setUp(self):
        self.registry = license_gate.load_registry()
        self.today = date(2026, 8, 3)

    def test_current_registry_holds_every_asset(self):
        for asset in ("xauusd", "eurusd", "btcusd"):
            with self.subTest(asset=asset):
                result = license_gate.evaluate(
                    asset, registry=self.registry, today=self.today,
                    content_qa_passed=True, data_quality_passed=True,
                )
                self.assertEqual(result["clearance"], license_gate.APPROVED_INTERNAL)
                self.assertFalse(license_gate.is_publishable(result))
                self.assertTrue(result["license_reasons"])

    def test_unknown_rights_hold_before_quality_is_known(self):
        result = license_gate.evaluate("xauusd", registry=self.registry, today=self.today)

        self.assertEqual(result["clearance"], license_gate.HOLD_LICENSE)

    def test_full_rights_plus_passing_gates_approve_publication(self):
        registry = json.loads(json.dumps(self.registry))
        # ผูกกับ provider ที่สินทรัพย์ใช้จริงตามทะเบียน (ตั้งแต่ 2026-08-04 คือ MT5)
        registry["providers"]["mt5_raw_trading"] = {
            "plan": "venture",
            "use_case": {"internal_analysis": True, "public_display": True,
                         "commercial_use": True, "redistribution": True},
            "attribution_required": True,
            "verified_at": "2026-07-01",
            "expiry_at": "2027-07-01",
            "notes": "ตัวอย่างสำหรับเทสเท่านั้น",
        }
        result = license_gate.evaluate(
            "xauusd", registry=registry, today=self.today,
            content_qa_passed=True, data_quality_passed=True,
        )

        self.assertEqual(result["clearance"], license_gate.APPROVED_PUBLIC)
        self.assertEqual(result["attribution_required"], ["mt5_raw_trading"])

    def test_expired_review_holds_again(self):
        registry = json.loads(json.dumps(self.registry))
        registry["providers"]["mt5_raw_trading"] = {
            "plan": "venture",
            "use_case": {"internal_analysis": True, "public_display": True,
                         "commercial_use": True, "redistribution": True},
            "attribution_required": True,
            "verified_at": "2025-01-01",
            "expiry_at": None,
            "notes": "ตัวอย่างสำหรับเทสเท่านั้น",
        }
        result = license_gate.evaluate(
            "xauusd", registry=registry, today=self.today,
            content_qa_passed=True, data_quality_passed=True,
        )

        self.assertNotEqual(result["clearance"], license_gate.APPROVED_PUBLIC)
        self.assertTrue(any("เกิน" in reason for reason in result["license_reasons"]))

    def test_content_and_license_gates_are_independent(self):
        registry = json.loads(json.dumps(self.registry))
        registry["providers"]["mt5_raw_trading"] = {
            "plan": "business",
            "use_case": {"internal_analysis": True, "public_display": True,
                         "commercial_use": True, "redistribution": True},
            "attribution_required": False,
            "verified_at": "2026-07-15",
            "expiry_at": None,
            "notes": "ตัวอย่างสำหรับเทสเท่านั้น",
        }
        result = license_gate.evaluate(
            "eurusd", registry=registry, today=self.today,
            content_qa_passed=False, data_quality_passed=True,
        )

        self.assertEqual(result["clearance"], license_gate.HOLD_CONTENT)
        self.assertEqual(result["license_reasons"], [])


if __name__ == "__main__":
    unittest.main()
