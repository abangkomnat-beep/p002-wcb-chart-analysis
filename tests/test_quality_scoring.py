from __future__ import annotations

import copy
import unittest

from tools import quality_scoring

H = "a" * 64


def payload(score=90, visual="content_only", attempt=1):
    config = quality_scoring.load_config()
    criteria = {key: {"score": score, "evidence": f"evidence for {key}"}
                for key in config["content_weights"]}
    if visual != "content_only":
        criteria.update({key: {"score": score, "evidence": f"evidence for {key}"}
                         for key in config["visual_weights"]})
    findings = []
    if score < 85:
        findings = [{"priority": "HIGH", "criterion": key, "location": "section 1",
                     "issue": "unsupported conclusion", "evidence": "line 2",
                     "why_it_matters": "may mislead", "how_to_fix": "bind to evidence",
                     "owner": "AGENT_09"} for key in criteria]
    return {"job_id": "job-1", "article_id": "article-1", "attempt": attempt,
            "producer": "agent-05-article-qa",
            "input_hashes": {"article": H, "brief": "b" * 64, "evidence": "c" * 64},
            "hard_gates": {"passed": True, "failures": []},
            "brief_compliance": {"passed": True, "missing": []},
            "visual_applicability": visual, "criterion_judgments": criteria,
            "findings": findings, "created_at": "2026-09-04T00:00:00+00:00"}


class QualityScoringTests(unittest.TestCase):
    def test_content_only_is_one_hundred_percent_content(self):
        result = quality_scoring.evaluate(payload(87))
        self.assertEqual(result["calculation"], {"content_score": 87.0,
                                                 "visual_score": None,
                                                 "overall_score": 87.0})
        self.assertEqual(result["status"], "PASS_SCORE")

    def test_attached_visual_uses_70_30_and_half_up_rounding(self):
        value = payload(90, "required_attached")
        for key in quality_scoring.load_config()["visual_weights"]:
            value["criterion_judgments"][key]["score"] = 85.05
        result = quality_scoring.evaluate(value)
        self.assertEqual(result["calculation"]["overall_score"], 88.52)

    def test_hard_gate_and_compliance_precede_high_scores(self):
        hard = payload(100)
        hard["hard_gates"] = {"passed": False, "failures": ["unsupported_number"]}
        self.assertEqual(quality_scoring.evaluate(hard)["status"], "BLOCK_HARD_GATE")
        self.assertIsNone(quality_scoring.evaluate(hard)["calculation"])
        brief = payload(100)
        brief["brief_compliance"] = {"passed": False, "missing": ["scenario"]}
        self.assertEqual(quality_scoring.evaluate(brief)["status"], "BRIEF_INCOMPLETE")
        self.assertIsNone(quality_scoring.evaluate(brief)["calculation"])

    def test_required_visual_missing_is_never_scored(self):
        value = payload(100)
        value["visual_applicability"] = "required_missing"
        self.assertEqual(quality_scoring.evaluate(value)["status"], "BRIEF_INCOMPLETE")

    def test_optional_attached_requires_visual_judgments(self):
        value = payload(90)
        value["visual_applicability"] = "optional_attached"
        with self.assertRaisesRegex(quality_scoring.QualityScoringError, "criterion set"):
            quality_scoring.evaluate(value)

    def test_low_criterion_requires_complete_finding(self):
        value = payload(84)
        value["findings"].pop()
        with self.assertRaisesRegex(quality_scoring.QualityScoringError, "requires finding"):
            quality_scoring.evaluate(value)
        value = payload(84)
        del value["findings"][0]["location"]
        with self.assertRaisesRegex(quality_scoring.QualityScoringError, "eight"):
            quality_scoring.evaluate(value)

    def test_unknown_owner_and_score_range_fail_closed(self):
        value = payload(84)
        value["findings"][0]["owner"] = "WRITER_AGENT"
        with self.assertRaisesRegex(quality_scoring.QualityScoringError, "owner"):
            quality_scoring.evaluate(value)
        value = payload(90)
        next(iter(value["criterion_judgments"].values()))["score"] = 101
        with self.assertRaisesRegex(quality_scoring.QualityScoringError, "range"):
            quality_scoring.evaluate(value)

    def test_non_finite_scores_are_normalized_to_quality_error(self):
        for hostile in (float("nan"), float("inf"), float("-inf"),
                        "NaN", "Infinity", "-Infinity"):
            value = payload(90)
            next(iter(value["criterion_judgments"].values()))["score"] = hostile
            with self.subTest(hostile=hostile), self.assertRaisesRegex(
                    quality_scoring.QualityScoringError, "finite number"):
                quality_scoring.evaluate(value)

    def test_evaluate_rejects_current_malformed_and_naive_timestamp_before_envelope(self):
        for timestamp, message in (("not-a-date", "ISO 8601"),
                                   ("2026-09-04T12:30:00", "timezone"),
                                   ("", "invalid")):
            value = payload()
            value["created_at"] = timestamp
            with self.subTest(timestamp=timestamp), self.assertRaisesRegex(
                    quality_scoring.QualityScoringError, message):
                quality_scoring.evaluate(value)

    def test_evaluate_accepts_aware_current_timestamp_forms(self):
        for timestamp in ("2026-09-04T12:30:00Z", "2026-09-04T19:30:00+07:00",
                          "2026-09-04T05:30:00-07:00"):
            value = payload()
            value["created_at"] = timestamp
            with self.subTest(timestamp=timestamp):
                self.assertEqual(quality_scoring.evaluate(value)["created_at"], timestamp)

    def test_stale_hash_self_review_and_attempt_four_rejected(self):
        with self.assertRaisesRegex(quality_scoring.QualityScoringError, "stale"):
            quality_scoring.evaluate(payload(), expected_hashes={"article": "d" * 64})
        value = payload()
        value["producer"] = "writer-agent"
        with self.assertRaisesRegex(quality_scoring.QualityScoringError, "self-review"):
            quality_scoring.evaluate(value)
        value = payload(attempt=1)
        value["attempt"] = 4
        with self.assertRaisesRegex(quality_scoring.QualityScoringError, "attempt"):
            quality_scoring.evaluate(value)

    def test_third_failed_attempt_escalates_and_history_is_append_only(self):
        result = quality_scoring.evaluate(payload(70, attempt=3))
        self.assertEqual(result["status"], "ESCALATE_FOR_REVIEW")
        first = quality_scoring.evaluate(payload(70))
        history = quality_scoring.append_history(None, first)
        second_input = payload(70, attempt=2)
        second_input["input_hashes"]["article"] = "d" * 64
        second = quality_scoring.evaluate(second_input)
        updated = quality_scoring.append_history(history, second)
        self.assertEqual([item["attempt"] for item in updated["attempts"]], [1, 2])
        self.assertEqual(len(history["attempts"]), 1)
        with self.assertRaisesRegex(quality_scoring.QualityScoringError, "new article hash"):
            quality_scoring.append_history(history, quality_scoring.evaluate(payload(70, attempt=2)))

    def test_history_rejects_identity_rebind_and_malformed_prior_shape(self):
        first = quality_scoring.evaluate(payload(70))
        history = quality_scoring.append_history(None, first)
        second_input = payload(70, attempt=2)
        second_input["job_id"] = "other-job"
        second_input["article_id"] = "other-article"
        second_input["input_hashes"]["article"] = "d" * 64
        with self.assertRaisesRegex(quality_scoring.QualityScoringError, "identity"):
            quality_scoring.append_history(history, quality_scoring.evaluate(second_input))
        malformed = copy.deepcopy(history)
        malformed["unexpected"] = True
        with self.assertRaisesRegex(quality_scoring.QualityScoringError, "canonical"):
            quality_scoring.append_history(malformed, quality_scoring.evaluate(payload(70, attempt=2)))
        malformed = copy.deepcopy(history)
        malformed["attempts"][0]["attempt"] = 2
        with self.assertRaisesRegex(quality_scoring.QualityScoringError, "contiguous"):
            quality_scoring.append_history(malformed, quality_scoring.evaluate(payload(70, attempt=2)))

    def test_history_rejects_invalid_or_naive_prior_datetime(self):
        first = quality_scoring.evaluate(payload(70))
        history = quality_scoring.append_history(None, first)
        second_input = payload(70, attempt=2)
        second_input["input_hashes"]["article"] = "d" * 64
        second = quality_scoring.evaluate(second_input)
        for timestamp, message in (("not-a-date", "ISO 8601"),
                                   ("2026-09-04T12:30:00", "timezone")):
            malformed = copy.deepcopy(history)
            malformed["attempts"][0]["created_at"] = timestamp
            with self.subTest(timestamp=timestamp), self.assertRaisesRegex(
                    quality_scoring.QualityScoringError, message):
                quality_scoring.append_history(malformed, second)

    def test_history_rejects_duplicate_hashes_already_in_prior_attempts(self):
        first = quality_scoring.evaluate(payload(70))
        history = quality_scoring.append_history(None, first)
        second_input = payload(70, attempt=2)
        second_input["input_hashes"]["article"] = "d" * 64
        history = quality_scoring.append_history(history,
                                                  quality_scoring.evaluate(second_input))
        malformed = copy.deepcopy(history)
        malformed["attempts"][1]["article_hash"] = malformed["attempts"][0]["article_hash"]
        third_input = payload(70, attempt=3)
        third_input["input_hashes"]["article"] = "e" * 64
        with self.assertRaisesRegex(quality_scoring.QualityScoringError, "reuses"):
            quality_scoring.append_history(malformed, quality_scoring.evaluate(third_input))

    def test_history_accepts_aware_iso_timezone_forms(self):
        first = quality_scoring.evaluate(payload(70))
        history = quality_scoring.append_history(None, first)
        second_input = payload(70, attempt=2)
        second_input["input_hashes"]["article"] = "d" * 64
        second = quality_scoring.evaluate(second_input)
        for timestamp in ("2026-09-04T12:30:00Z", "2026-09-04T19:30:00+07:00",
                          "2026-09-04T05:30:00-07:00"):
            valid = copy.deepcopy(history)
            valid["attempts"][0]["created_at"] = timestamp
            with self.subTest(timestamp=timestamp):
                updated = quality_scoring.append_history(valid, second)
                self.assertEqual(len(updated["attempts"]), 2)

    def test_first_attempt_rejects_invalid_or_naive_current_datetime(self):
        for timestamp, message in (("not-a-date", "ISO 8601"),
                                   ("2026-09-04T12:30:00", "timezone")):
            evaluation = quality_scoring.evaluate(payload(70))
            evaluation["created_at"] = timestamp
            with self.subTest(timestamp=timestamp), self.assertRaisesRegex(
                    quality_scoring.QualityScoringError, message):
                quality_scoring.append_history(None, evaluation)

    def test_first_attempt_accepts_aware_current_timezone_forms(self):
        for timestamp in ("2026-09-04T12:30:00Z", "2026-09-04T19:30:00+07:00",
                          "2026-09-04T05:30:00-07:00"):
            evaluation = quality_scoring.evaluate(payload(70))
            evaluation["created_at"] = timestamp
            with self.subTest(timestamp=timestamp):
                history = quality_scoring.append_history(None, evaluation)
                self.assertEqual(history["attempts"][0]["created_at"], timestamp)

    def test_input_hash_keys_must_be_exact(self):
        for mutation in ("extra", "missing"):
            value = payload()
            if mutation == "extra":
                value["input_hashes"]["images"] = "e" * 64
            else:
                del value["input_hashes"]["brief"]
            with self.subTest(mutation=mutation), self.assertRaisesRegex(
                    quality_scoring.QualityScoringError, "exactly"):
                quality_scoring.evaluate(value)

    def test_revision_brief_is_hash_bound(self):
        result = quality_scoring.evaluate(payload(70))
        brief = quality_scoring.make_revision_brief(result, article_hash=H)
        self.assertEqual(brief["issues"], result["findings"])
        with self.assertRaisesRegex(quality_scoring.QualityScoringError, "stale"):
            quality_scoring.make_revision_brief(result, article_hash="d" * 64)


if __name__ == "__main__":
    unittest.main()
