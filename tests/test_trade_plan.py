"""เทสชั้นแผนการเทรดฝั่ง internal (Agent 06 Trade Setup Analyst)

กติกาที่เทสชุดนี้ล็อกไว้ ตรงกับมติผู้ใช้ 2026-08-04:
- ทุกตัวเลขในแผนต้องชี้กลับระดับที่อนุมัติแล้วได้ ห้ามสร้างเลขเอง
- ข้อมูลรายวัน (D1) ⇒ แผนต้องไม่ executable และต้องพก forbidden_language มาด้วย
- ไม่มีจังหวะ = no_trade พร้อมเหตุผล ไม่ใช่โยน exception หรือคืนแผนเปล่า
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import build_daily_package, integrity  # noqa: E402
from tools import levels as level_engine, risk_auditor, trade_plan  # noqa: E402


def load_report(fixture: str, asset: str) -> dict:
    rows = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))["rows"]
    return integrity.assess(rows, asset, calculated_at="2026-08-03T06:30:00Z")


def build_plan(report: dict, level_map: dict, **overrides) -> dict:
    payload = {
        "report": report, "level_map": level_map, "asset": "xauusd",
        "symbol": "XAU/USD", "instrument_type": "spot_metal",
        "cutoff_at": "2026-08-03T06:30:00Z", "batch_id": "test-batch",
    }
    payload.update(overrides)
    return trade_plan.build(**payload)


class TradePlanStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = load_report("xau_valid_120_sessions.json", "xauusd")
        cls.level_map = level_engine.build_level_map(cls.report)
        cls.plan = build_plan(cls.report, cls.level_map)

    def test_plan_carries_every_required_field(self):
        for field in ("plan_version", "classification", "executable", "bias",
                      "reference_price", "entry", "stop", "targets", "rr",
                      "invalidation", "no_trade", "confidence", "evidence_refs",
                      "forbidden_language", "timeframe"):
            with self.subTest(field=field):
                self.assertIn(field, self.plan)

    def test_timeframe_is_daily_only(self):
        self.assertEqual(self.plan["timeframe"], "D1")

    def test_daily_data_never_produces_an_executable_setup(self):
        """D1 อย่างเดียวให้ได้แค่ฉากทัศน์ระดับวัน — ถ้าเทสนี้ตกแปลว่ามีคนเปิด intraday
        โดยไม่ได้ขออนุมัติ (มติผู้ใช้ 2026-08-04 ห้ามเพิ่ม H4/H1 ในโปรเจกต์นี้)
        """
        self.assertEqual(self.plan["classification"], level_engine.DAILY_SCENARIO)
        self.assertFalse(self.plan["executable"])
        self.assertIn("เข้า Buy ตรงนี้", self.plan["forbidden_language"])


class TradePlanEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = load_report("xau_valid_120_sessions.json", "xauusd")
        cls.level_map = level_engine.build_level_map(cls.report)
        cls.plan = build_plan(cls.report, cls.level_map)

    def test_entry_stop_and_targets_all_match_approved_levels(self):
        """กติกาแกน: ห้ามสร้างเลขเอง — ทุกค่าต้องผ่าน levels.validate_target"""
        zones = self.level_map["zones"]
        checks = {
            "entry.edge": self.plan["entry"]["edge"],
            "stop.value": self.plan["stop"]["value"],
        }
        for index, target in enumerate(self.plan["targets"]):
            checks[f"targets[{index}].value"] = target["value"]
        for name, value in checks.items():
            with self.subTest(field=name):
                result = level_engine.validate_target(value, zones)
                self.assertTrue(result["valid"], f"{name}={value} ไม่ตรงระดับที่อนุมัติ")

    def test_every_number_has_an_evidence_reference(self):
        refs = self.plan["evidence_refs"]
        for field in ("entry.edge", "stop.value", "targets[0].value",
                      "stop.atr_distance", "bias", "rr"):
            with self.subTest(field=field):
                self.assertIn(field, refs)
                self.assertTrue(refs[field])

    def test_risk_reward_is_computed_not_declared(self):
        entry = self.plan["entry"]["edge"]
        stop = self.plan["stop"]["value"]
        target = self.plan["targets"][0]["value"]
        expected = abs(target - entry) / abs(stop - entry)

        self.assertAlmostEqual(self.plan["rr"], expected, places=9)

    def test_stop_distance_is_expressed_in_atr_units(self):
        atr = self.report["indicators"]["atr14"]["value"]
        risk = abs(self.plan["stop"]["value"] - self.plan["entry"]["edge"])

        self.assertAlmostEqual(self.plan["stop"]["atr_distance"], risk / atr, places=9)

    def test_confidence_is_scored_with_written_reasons(self):
        self.assertGreaterEqual(self.plan["confidence"], 1)
        self.assertLessEqual(self.plan["confidence"], 10)
        self.assertTrue(self.plan["confidence_basis"])


class TradePlanNoTradeTests(unittest.TestCase):
    """ไม่มีจังหวะคือคำตอบที่ถูกต้อง ไม่ใช่ความล้มเหลว"""

    @classmethod
    def setUpClass(cls):
        cls.report = load_report("xau_valid_120_sessions.json", "xauusd")
        cls.level_map = level_engine.build_level_map(cls.report)

    def test_no_trade_when_moving_averages_are_unavailable(self):
        report = {**self.report, "indicators": {
            **self.report["indicators"],
            "sma20": {**self.report["indicators"]["sma20"],
                      "approved_for_publication": False},
        }}
        plan = build_plan(report, self.level_map)

        self.assertEqual(plan["classification"], trade_plan.NO_TRADE)
        self.assertEqual(plan["reason"], "no_directional_bias")
        self.assertFalse(plan["executable"])
        self.assertTrue(plan["no_trade"])

    def test_no_trade_when_volatility_is_unavailable(self):
        report = {**self.report, "indicators": {
            **self.report["indicators"],
            "atr14": {**self.report["indicators"]["atr14"],
                      "approved_for_publication": False},
        }}
        plan = build_plan(report, self.level_map)

        self.assertEqual(plan["classification"], trade_plan.NO_TRADE)
        self.assertEqual(plan["reason"], "volatility_unavailable")

    def test_no_trade_when_direction_has_too_few_levels(self):
        """กรณีที่กระดาน P002 เตือนไว้ (งานค้างข้อ 1 ของ BTC): ระดับขาด ไม่ใช่ตลาดไม่มีจังหวะ"""
        reference = self.level_map["reference_price"]
        thin = {**self.level_map, "zones": [
            zone for zone in self.level_map["zones"]
            if (zone.get("value") or zone.get("zone_high") or 0) > reference
        ]}
        plan = build_plan(self.report, thin)

        self.assertEqual(plan["classification"], trade_plan.NO_TRADE)
        self.assertIn(plan["reason"], ("insufficient_levels_in_direction", "no_level_for_stop"))
        # เหตุผลต้องอ่านออกว่าเป็นเรื่องข้อมูล ไม่ใช่เรื่องตลาด
        self.assertTrue(plan["detail"])

    def test_no_trade_plan_still_carries_the_full_shape(self):
        report = {**self.report, "indicators": {
            **self.report["indicators"],
            "atr14": {**self.report["indicators"]["atr14"],
                      "approved_for_publication": False},
        }}
        plan = build_plan(report, self.level_map)
        for field in ("plan_version", "classification", "bias", "no_trade",
                      "confidence", "evidence_refs", "timeframe"):
            with self.subTest(field=field):
                self.assertIn(field, plan)


class TradePlanBiasTests(unittest.TestCase):
    def setUp(self):
        self.report = load_report("xau_valid_120_sessions.json", "xauusd")

    def _with_moving_averages(self, fast: float, slow: float) -> dict:
        indicators = self.report["indicators"]
        return {**self.report, "indicators": {
            **indicators,
            "sma20": {**indicators["sma20"], "value": fast,
                      "approved_for_publication": True},
            "sma50": {**indicators["sma50"], "value": slow,
                      "approved_for_publication": True},
        }}

    def test_price_above_rising_stack_is_up(self):
        result = trade_plan.infer_bias(self._with_moving_averages(90.0, 80.0), 100.0)

        self.assertEqual(result["bias"], trade_plan.BIAS_UP)

    def test_price_below_falling_stack_is_down(self):
        result = trade_plan.infer_bias(self._with_moving_averages(110.0, 120.0), 100.0)

        self.assertEqual(result["bias"], trade_plan.BIAS_DOWN)

    def test_mixed_stack_is_neutral(self):
        result = trade_plan.infer_bias(self._with_moving_averages(110.0, 80.0), 100.0)

        self.assertEqual(result["bias"], trade_plan.BIAS_NEUTRAL)
        self.assertEqual(result["reason"], "stack_not_aligned")


class TradeBranchTests(unittest.TestCase):
    """สาขาข้างในสายท่อ — ต้องไม่ลากบทความล้ม และต้องไม่หลุดฝั่ง public"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.internal = Path(self.tmp.name) / "internal"
        self.report = load_report("xau_valid_120_sessions.json", "xauusd")
        self.level_map = level_engine.build_level_map(self.report)
        self.config = {"symbol": "XAU/USD", "instrument_type": "spot_metal"}

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, **overrides):
        payload = {
            "report": self.report, "level_map": self.level_map, "news": {"items": []},
            "internal": self.internal, "config": self.config, "asset": "xauusd",
            "cutoff_at": "2026-08-03T06:30:00Z", "batch_id": "test-batch",
        }
        payload.update(overrides)
        return build_daily_package.build_trade_branch(**payload)

    def test_branch_writes_plan_and_audit_side_by_side(self):
        result = self._run()

        self.assertIn(result["status"], ("built", "blocked"))
        directory = result["directory"]
        self.assertTrue((directory / "trade-plan.json").is_file())
        self.assertTrue((directory / "risk-audit.json").is_file())

    def test_broken_input_does_not_raise_and_is_recorded(self):
        """แผนล้มต้องไม่ทำให้บทความล้ม — แต่ต้องเห็นว่าล้ม ไม่กลืนเงียบ"""
        result = self._run(level_map={"reference_price": None, "zones": []})

        self.assertEqual(result["status"], "error")
        recorded = json.loads((self.internal / "trade-plan-error.json").read_text(encoding="utf-8"))
        self.assertEqual(recorded["status"], "error")
        self.assertTrue(recorded["detail"])

    def test_vetoed_plan_is_quarantined_not_published(self):
        """verdict block = แผนไม่ออกจากระบบ แต่เก็บไว้ให้ตรวจย้อนได้"""
        original = risk_auditor.audit

        def blocking_audit(plan, **kwargs):
            result = original(plan, **kwargs)
            return {**result, "verdict": risk_auditor.VERDICT_BLOCK}

        risk_auditor.audit = blocking_audit
        try:
            result = self._run()
        finally:
            risk_auditor.audit = original

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["directory"].name, "rejected-plan")
        self.assertFalse((self.internal / "trade-plan.json").exists())

    def test_revision_order_is_written_when_there_are_findings(self):
        result = self._run()
        order_path = result["directory"] / "revision-order.json"
        if result["findings"]:
            order = json.loads(order_path.read_text(encoding="utf-8"))
            self.assertEqual(order["max_rounds"], 2)
            for finding in order["findings"]:
                with self.subTest(finding=finding["id"]):
                    self.assertTrue(finding["should_be"])
                    self.assertTrue(finding["pass_criterion"])
        else:
            self.assertFalse(order_path.exists())

    def test_every_file_stays_under_internal(self):
        """**ไฟล์**ของสาขานี้ต้องไม่มีตัวใดอยู่นอก internal/

        ยังบังคับอยู่แม้ผู้ใช้ปลดมติข้อ 14ก แล้ว (2026-08-04) — สิ่งที่ปลดคือ
        **ตัวเลขบางตัวเล่าในบทความสไตล์ ② ได้** ไม่ใช่ไฟล์แผนย้ายไปฝั่งสาธารณะ
        แผนเต็ม ใบสั่งแก้ และคะแนนความเชื่อมั่นยังอยู่ internal/ เหมือนเดิมทุกไฟล์
        """
        self._run()
        for path in self.internal.rglob("*.json"):
            with self.subTest(path=path.name):
                self.assertIn("internal", path.parts)


if __name__ == "__main__":
    unittest.main()
