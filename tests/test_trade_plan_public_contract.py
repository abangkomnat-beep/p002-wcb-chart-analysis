import copy
import hashlib
import sys
import unittest
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import trade_plan_public_contract  # noqa: E402


class PublicTradePlanContract(unittest.TestCase):
    def setUp(self):
        self.article = b""
        self.contract = {
            "schema": trade_plan_public_contract.SCHEMA,
            "style_id": "e_indicator",
            "asset": "xauusd",
            "article": "xauusd.md",
            "article_sha256": hashlib.sha256(self.article).hexdigest(),
            "qa_status": "PASS_QA",
            "publishable": True,
            "plan_status": "WAIT_TRIGGER",
            "side": "BUY",
            "current_close": 99.0,
            "cutoff_at": "2026-08-31T23:59:00+07:00",
            "valid_until": "2026-09-01T23:59:00+07:00",
            "evidence_hash": "a" * 64,
            "rr_policy_version": "TPR-RR/v1",
            "plans": [{
                "side": "BUY",
                "trigger": {"condition": "D1 close above resistance", "value": 100.0},
                "entry_zone": {"low": 100.0, "high": 101.0},
                "stop_loss": 99.0,
                "take_profit": [103.0, 105.0],
                "risk_reward": [1.0, 2.0],
                "rr_basis": "gross_pre_cost",
                "invalidation": {"condition": "D1 close below structure", "value": 99.0},
            }],
        }
        from tools import trade_plan_public_adapters
        self.article = ("---\nslug: example\n---\n\n# plan\n\n"
                        + trade_plan_public_adapters.public_plan_block(self.contract)
                        + "\n").encode("utf-8")
        self.contract["article_sha256"] = hashlib.sha256(self.article).hexdigest()

    def validate(self, contract=None, article=None):
        return trade_plan_public_contract.validate(
            contract if contract is not None else self.contract,
            article_name="xauusd.md",
            article_bytes=article if article is not None else self.article,
            style_id="e_indicator", asset="xauusd", publish_date=date(2026, 9, 1))

    def test_complete_single_side_contract_passes(self):
        report = self.validate()
        self.assertEqual(report["status"], "PASS", report["findings"])

    def test_every_required_public_field_is_fail_closed(self):
        required = (
            "schema", "style_id", "asset", "article", "article_sha256", "qa_status",
            "publishable", "plan_status", "side", "current_close", "cutoff_at", "valid_until",
            "evidence_hash", "rr_policy_version", "plans",
        )
        for field in required:
            with self.subTest(field=field):
                broken = copy.deepcopy(self.contract)
                broken.pop(field)
                self.assertEqual(self.validate(broken)["status"], "FAIL")

    def test_data_hold_and_block_qa_never_pass_public_gate(self):
        for status in ("DATA_HOLD", "BLOCK_QA"):
            with self.subTest(status=status):
                broken = copy.deepcopy(self.contract)
                broken["qa_status"] = status
                report = self.validate(broken)
                self.assertEqual(report["status"], "FAIL")
                self.assertIn("HOLD_STATUS_PRESENT",
                              {item["code"] for item in report["findings"]})

    def test_contract_is_bound_to_exact_article_bytes(self):
        report = self.validate(article=self.article + b"changed\n")
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("ARTICLE_HASH_MISMATCH",
                      {item["code"] for item in report["findings"]})

    def test_gross_rr_disclosure_is_required_in_public_copy(self):
        article = b"---\nslug: example\n---\n\n# plan\n"
        broken = copy.deepcopy(self.contract)
        broken["article_sha256"] = hashlib.sha256(article).hexdigest()
        report = self.validate(broken, article=article)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("RR_DISCLOSURE_MISSING",
                      {item["code"] for item in report["findings"]})

    def test_wait_without_complete_plan_is_rejected(self):
        broken = copy.deepcopy(self.contract)
        broken["plans"][0].pop("stop_loss")
        report = self.validate(broken)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("PLAN_FIELD_MISSING",
                      {item["code"] for item in report["findings"]})

    def test_oco_requires_complete_buy_and_sell_legs(self):
        oco = copy.deepcopy(self.contract)
        oco["side"] = "OCO"
        sell = {
            "side": "SELL",
            "trigger": {"condition": "D1 close below support", "value": 98.0},
            "entry_zone": {"low": 97.0, "high": 98.0},
            "stop_loss": 99.0,
            "take_profit": [95.0],
            "risk_reward": [1.0],
            "rr_basis": "gross_pre_cost",
            "invalidation": {"condition": "D1 close above structure", "value": 99.0},
        }
        oco["plans"].append(sell)
        from tools import trade_plan_public_adapters
        self.article = (trade_plan_public_adapters.public_plan_block(oco) + "\n").encode("utf-8")
        oco["article_sha256"] = hashlib.sha256(self.article).hexdigest()
        self.assertEqual(self.validate(oco)["status"], "PASS")
        oco["plans"][1] = copy.deepcopy(oco["plans"][0])
        report = self.validate(oco)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("OCO_LEGS_INVALID",
                      {item["code"] for item in report["findings"]})

    def test_invalid_price_geometry_is_rejected_without_recalculating_it(self):
        broken = copy.deepcopy(self.contract)
        broken["plans"][0]["stop_loss"] = 102.0
        report = self.validate(broken)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("PLAN_GEOMETRY_INVALID",
                      {item["code"] for item in report["findings"]})

    def test_under_minimum_or_wrong_rr_basis_is_rejected(self):
        for mutation, code in (({"risk_reward": [0.99, 4.0]},
                                "RISK_REWARD_BELOW_MINIMUM"),
                               ({"rr_basis": "raw"}, "RR_BASIS_INVALID"),
                               ({"rr_basis": "cost_adjusted"}, "RR_BASIS_INVALID")):
            with self.subTest(code=code):
                broken = copy.deepcopy(self.contract)
                broken["plans"][0].update(mutation)
                report = self.validate(broken)
                self.assertEqual(report["status"], "FAIL")
                self.assertIn(code, {item["code"] for item in report["findings"]})

    def test_wait_trigger_must_be_strictly_untriggered_against_current_close(self):
        broken = copy.deepcopy(self.contract)
        broken["current_close"] = broken["plans"][0]["trigger"]["value"]
        report = self.validate(broken)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("WAIT_TRIGGER_ALREADY_CROSSED",
                      {item["code"] for item in report["findings"]})

    def test_adversarial_unknown_keys_zero_evidence_long_ttl_and_weak_trigger_fail(self):
        mutations = (
            (lambda value: value.update({"unknown": True}), "UNKNOWN_CONTRACT_FIELD"),
            (lambda value: value.update({"evidence_hash": "0" * 64}), "EVIDENCE_HASH_ZERO"),
            (lambda value: value.update({"valid_until": "2026-09-20T00:00:00+07:00"}),
             "TTL_NOT_EXACT"),
            (lambda value: value["plans"][0]["trigger"].update({"condition": "x"}),
             "TRIGGER_CONDITION_TOO_WEAK"),
            (lambda value: value["plans"][0].update({"mystery": 1}),
             "UNKNOWN_PLAN_FIELD"),
        )
        for mutate, code in mutations:
            with self.subTest(code=code):
                broken = copy.deepcopy(self.contract)
                mutate(broken)
                report = self.validate(broken)
                self.assertIn(code, {item["code"] for item in report["findings"]})

    def test_rr_claim_is_recomputed_from_adverse_entry_edge(self):
        broken = copy.deepcopy(self.contract)
        broken["plans"][0]["risk_reward"] = [1.1, 2.0]
        report = self.validate(broken)
        self.assertIn("RISK_REWARD_GEOMETRY_MISMATCH",
                      {item["code"] for item in report["findings"]})

    def test_expected_evidence_hash_is_bound_when_caller_has_canonical_evidence(self):
        report = trade_plan_public_contract.validate(
            self.contract, article_name="xauusd.md", article_bytes=self.article,
            style_id="e_indicator", asset="xauusd", publish_date=date(2026, 9, 1),
            expected_evidence_hash="b" * 64)
        self.assertIn("EVIDENCE_HASH_MISMATCH",
                      {item["code"] for item in report["findings"]})

    def test_visible_plan_value_tamper_fails_even_when_article_hash_is_rebound(self):
        tampered = self.article.replace(b"D1 close above resistance", b"D1 close above 999")
        broken = copy.deepcopy(self.contract)
        broken["article_sha256"] = hashlib.sha256(tampered).hexdigest()
        report = self.validate(broken, article=tampered)
        self.assertIn("ARTICLE_PLAN_VALUE_MISMATCH",
                      {item["code"] for item in report["findings"]})

    def test_duplicate_public_plan_blocks_fail_even_when_article_hash_is_rebound(self):
        block = self.article.decode("utf-8")
        duplicated = (block + "\n" + block).encode("utf-8")
        broken = copy.deepcopy(self.contract)
        broken["article_sha256"] = hashlib.sha256(duplicated).hexdigest()
        report = self.validate(broken, article=duplicated)
        self.assertIn("ARTICLE_PLAN_BLOCK_DUPLICATE",
                      {item["code"] for item in report["findings"]})


if __name__ == "__main__":
    unittest.main()
