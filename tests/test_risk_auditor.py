"""เทสด่านตรวจความเสี่ยงและตรรกะ (Agent 07 Risk & Logic Auditor)

กติกาที่เทสชุดนี้ล็อกไว้ ตรงกับมติผู้ใช้ 2026-08-04:
- ผู้ตรวจสั่งแก้อย่างเดียว ⇒ **ทุก finding ต้องมี should_be และ pass_criterion**
  ไม่งั้นผู้เขียนแผนที่แก้เองไม่ได้จะวนหลายรอบโดยเปล่าประโยชน์
- กฎที่ตรวจไม่ได้ต้องประกาศไว้ใน unavailable_checks ไม่ใช่เงียบแล้วให้เข้าใจว่าตรวจครบ
- แผนที่รายงาน no_trade ถือว่าผ่าน ไม่ใช่ข้อบกพร่อง
"""

import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import integrity, levels as level_engine, risk_auditor, trade_plan  # noqa: E402


def load_report(fixture: str, asset: str) -> dict:
    rows = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))["rows"]
    return integrity.assess(rows, asset, calculated_at="2026-08-03T06:30:00Z")


class AuditContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = load_report("xau_valid_120_sessions.json", "xauusd")
        cls.level_map = level_engine.build_level_map(cls.report)
        cls.plan = trade_plan.build(
            report=cls.report, level_map=cls.level_map, asset="xauusd",
            symbol="XAU/USD", instrument_type="spot_metal",
            cutoff_at="2026-08-03T06:30:00Z", batch_id="test-batch")
        cls.result = risk_auditor.audit(cls.plan, level_map=cls.level_map)

    def test_report_carries_every_required_field(self):
        for field in ("auditor_version", "verdict", "confidence_score", "round",
                      "max_rounds", "thresholds_used", "findings", "checked",
                      "unavailable_checks"):
            with self.subTest(field=field):
                self.assertIn(field, self.result)

    def test_every_finding_says_what_the_value_should_be(self):
        """หัวใจของมติ 'สั่งแก้อย่างเดียว' — ใบสั่งที่บอกแค่ว่าผิดตรงไหนใช้ไม่ได้"""
        self.assertTrue(self.result["findings"], "แผนตัวอย่างควรมีอย่างน้อยหนึ่งข้อให้แก้")
        for finding in self.result["findings"]:
            with self.subTest(finding=finding["id"]):
                self.assertTrue(finding["should_be"].strip())
                self.assertTrue(finding["pass_criterion"].strip())
                self.assertIn(finding["severity"],
                              (risk_auditor.BLOCKING, risk_auditor.REQUIRED,
                               risk_auditor.SUGGESTION))
                self.assertIn(finding["target"], ("trade_plan", "article"))
                self.assertIsNone(finding["resolution"])

    def test_auditor_never_returns_a_modified_plan(self):
        """ผู้ตรวจห้ามแก้เอง — ผลตรวจต้องไม่มีแผนติดมาด้วย"""
        for key in ("plan", "trade_plan", "fixed_plan", "entry", "stop", "targets"):
            with self.subTest(key=key):
                self.assertNotIn(key, self.result)

    def test_unavailable_rule_is_declared_not_hidden(self):
        names = {item["name"] for item in self.result["unavailable_checks"]}
        self.assertIn("news_direction_conflict", names)
        for item in self.result["unavailable_checks"]:
            with self.subTest(rule=item["rule"]):
                self.assertTrue(item["reason"])
                self.assertTrue(item["unblocked_by"])

    def test_confidence_score_is_within_range(self):
        self.assertGreaterEqual(self.result["confidence_score"], 1)
        self.assertLessEqual(self.result["confidence_score"], 10)

    def test_round_cap_matches_project_escalation_rule(self):
        self.assertEqual(self.result["max_rounds"], 2)


class RuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = load_report("xau_valid_120_sessions.json", "xauusd")
        cls.level_map = level_engine.build_level_map(cls.report)
        cls.base = trade_plan.build(
            report=cls.report, level_map=cls.level_map, asset="xauusd",
            symbol="XAU/USD", instrument_type="spot_metal",
            cutoff_at="2026-08-03T06:30:00Z", batch_id="test-batch")

    def _audit(self, plan: dict, **kwargs) -> dict:
        return risk_auditor.audit(plan, level_map=self.level_map, **kwargs)

    def _ids(self, result: dict) -> set:
        return {item["id"] for item in result["findings"]}

    def test_invented_target_is_blocking(self):
        plan = {**self.base, "targets": [{**self.base["targets"][0], "value": 999999.0}]}
        result = self._audit(plan)

        self.assertIn("RL-001", self._ids(result))
        self.assertEqual(result["verdict"], risk_auditor.VERDICT_BLOCK)

    def test_low_risk_reward_is_required_fix_with_a_concrete_alternative(self):
        plan = {**self.base, "rr": 0.5}
        result = self._audit(plan)
        finding = next(item for item in result["findings"] if item["id"] == "RL-003")

        self.assertEqual(finding["severity"], risk_auditor.REQUIRED)
        # ต้องเสนอทางออกที่เป็นค่าจริงหรือสั่งให้เปลี่ยนเป็น no_trade
        self.assertTrue("no_trade" in finding["should_be"]
                        or "เป้าหมายชั้นถัดไป" in finding["should_be"])

    def test_high_risk_reward_passes_the_rule(self):
        plan = {**self.base, "rr": 3.0, "stop": {**self.base["stop"], "atr_distance": 1.5}}
        result = self._audit(plan)

        self.assertNotIn("RL-003", self._ids(result))
        self.assertNotIn("RL-004", self._ids(result))

    def test_tight_stop_is_flagged_with_a_named_level(self):
        plan = {**self.base, "stop": {**self.base["stop"], "atr_distance": 0.3}}
        result = self._audit(plan)
        finding = next(item for item in result["findings"] if item["id"] == "RL-004")

        self.assertEqual(finding["severity"], risk_auditor.REQUIRED)
        self.assertTrue(finding["should_be"])

    def test_missing_evidence_reference_is_blocking(self):
        plan = {**self.base, "evidence_refs": {}}
        result = self._audit(plan)

        self.assertIn("RL-008", self._ids(result))
        self.assertEqual(result["verdict"], risk_auditor.VERDICT_BLOCK)

    def test_neutral_bias_with_an_entry_is_blocking(self):
        plan = {**self.base, "bias": trade_plan.BIAS_NEUTRAL}
        result = self._audit(plan)

        self.assertIn("RL-007", self._ids(result))
        self.assertEqual(result["verdict"], risk_auditor.VERDICT_BLOCK)

    def test_news_in_the_round_asks_for_an_event_risk_line(self):
        news = {"items": [{"event": "ตัวเลขการจ้างงานนอกภาคเกษตรของสหรัฐ"}]}
        result = self._audit(self.base, news=news)
        finding = next(item for item in result["findings"] if item["id"] == "RL-009")

        self.assertEqual(finding["severity"], risk_auditor.SUGGESTION)
        self.assertIn("ตัวเลขการจ้างงาน", finding["should_be"])

    def test_plan_that_already_notes_event_risk_passes(self):
        plan = {**self.base, "no_trade": [*self.base["no_trade"], "งดเข้าเมื่อใกล้เวลาประกาศข่าว"]}
        result = self._audit(plan, news={"items": [{"event": "อะไรก็ได้"}]})

        self.assertNotIn("RL-009", self._ids(result))

    def test_suggestion_alone_still_passes(self):
        plan = {**self.base, "rr": 3.0, "stop": {**self.base["stop"], "atr_distance": 1.5}}
        result = self._audit(plan, news={"items": [{"event": "ข่าวหนึ่ง"}]})

        self.assertEqual(self._ids(result), {"RL-009"})
        self.assertEqual(result["verdict"], risk_auditor.VERDICT_PASS)


class NoTradeAuditTests(unittest.TestCase):
    def test_no_trade_plan_is_a_pass_not_a_failure(self):
        report = load_report("xau_valid_120_sessions.json", "xauusd")
        level_map = level_engine.build_level_map(report)
        blind = {**report, "indicators": {
            **report["indicators"],
            "atr14": {**report["indicators"]["atr14"], "approved_for_publication": False},
        }}
        plan = trade_plan.build(
            report=blind, level_map=level_map, asset="xauusd", symbol="XAU/USD",
            instrument_type="spot_metal", cutoff_at="2026-08-03T06:30:00Z",
            batch_id="test-batch")
        result = risk_auditor.audit(plan, level_map=level_map)

        self.assertEqual(result["verdict"], risk_auditor.VERDICT_PASS)
        self.assertEqual(result["findings"], [])
        self.assertIn("ไม่ใช่ข้อบกพร่อง", result["note"])


if __name__ == "__main__":
    unittest.main()
