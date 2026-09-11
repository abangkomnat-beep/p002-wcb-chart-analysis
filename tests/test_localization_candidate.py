import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.language_patch import validate_localized_candidate


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class LocalizedCandidateTests(unittest.TestCase):
    def setUp(self):
        self.source = "ราคา EURUSD อยู่ที่ 1.16141 หากยืนเหนือ 1.16206 จะยืนยันแนวโน้ม\n".encode()
        self.target = "EURUSD is at 1.16141. If it holds above 1.16206, the direction will be confirmed.\n".encode()
        self.claim_map = {
            "source_sha256": digest(self.source),
            "claims": [{"id": "C1", "source_quote": self.source.decode().strip(), "protected": [
                {"id": "P1", "value_text": "1.16141", "kind": "decimal", "unit": "USD", "role": "price"},
                {"id": "P2", "value_text": "1.16206", "kind": "decimal", "unit": "USD", "role": "level"},
            ]}],
        }
        self.job = {
            "article_id": "eurusd-20260907",
            "country_code": "ZA", "content_locale": "en-ZA",
            "language_pack": "en-001", "pack_version": "0.1.0",
            "pack_sha256": digest(b"pack"), "source_sha256": digest(self.source),
            "claim_map_sha256": digest(json.dumps(self.claim_map).encode()), "target_sha256": digest(self.target),
            "claim_map_actual_sha256": digest(json.dumps(self.claim_map).encode()),
            "source_receipt_id": "source-1", "image_hashes": {},
            "writer_execution_id": "writer-1",
            "alignment": [{"claim_id": "C1", "target_field": "body", "target_quote": self.target.decode().strip()}],
        }
        self.receipts = [{"gate": "source_acceptance", "article_id": self.job["article_id"],
                          "source_sha256": digest(self.source), "verdict": "PASS",
                          "receipt_id": "source-1", "reviewer_execution_id": "source-review",
                          "reviewer_kind": "TEST_ONLY", "reviewed_at": "2026-09-07T12:00:00+07:00",
                          "findings": [], "pack_sha256": self.job["pack_sha256"],
                          "claim_map_sha256": self.job["claim_map_sha256"]}]
        self.receipts.extend({"gate": gate, "article_id": self.job["article_id"],
                              "source_sha256": digest(self.source), "target_sha256": digest(self.target),
                              "pack_sha256": self.job["pack_sha256"], "claim_map_sha256": self.job["claim_map_sha256"],
                              "reviewer_execution_id": "review-1", "findings": [], "image_hashes": {},
                              "receipt_id": "TEST_ONLY-" + gate, "reviewer_kind": "TEST_ONLY",
                              "reviewed_at": "2026-09-07T12:00:00Z", "verdict": "PASS"} for gate in ("language", "semantic", "visual", "package_input"))
        self.pack = {"locale": "en-001", "version": "0.1.0", "status": "stable_locked",
                     "sha256": digest(b"pack"), "recorded_sha256": digest(b"pack"),
                     "verified": True, "approved_by": "TEST_ONLY", "approved_at": "2026-09-07"}

    def check(self, **overrides):
        args = dict(job=self.job, claim_map=self.claim_map, trusted_receipts=self.receipts, pack_info=self.pack)
        args.update(overrides)
        source = args.pop("source", self.source)
        target = args.pop("target", self.target)
        return validate_localized_candidate(source, target, **args)

    def test_each_missing_target_gate_is_pending(self):
        for index in range(1, 5):
            with self.subTest(index=index):
                result = self.check(trusted_receipts=self.receipts[:index] + self.receipts[index + 1:])
                self.assertTrue(result["mechanical_ok"])
                self.assertEqual(result["review_status"], "PENDING")
                self.assertFalse(result["release_eligible"])

    def test_receipt_bindings_and_review_outcomes_fail_closed(self):
        for key, value in [("target_sha256", None), ("pack_sha256", digest(b"other")),
                           ("claim_map_sha256", None), ("reviewer_execution_id", ""),
                           ("verdict", "HOLD"), ("findings", [{"severity": "Major"}])]:
            with self.subTest(key=key):
                receipt = {**self.receipts[1], key: value}
                result = self.check(trusted_receipts=[self.receipts[0], receipt, *self.receipts[2:]])
                self.assertFalse(result["release_eligible"])
                self.assertEqual(result["review_status"], "FAILED")

    def test_other_article_receipts_do_not_contaminate_current_article(self):
        result = self.check(trusted_receipts=[*self.receipts, {"article_id": "other", "gate": "language", "verdict": "FAIL"}])
        self.assertTrue(result["release_eligible"])

    def test_pack_requires_verification_and_approval(self):
        for key, value in [("verified", "true"), ("recorded_sha256", None), ("approved_by", ""), ("approved_at", None)]:
            with self.subTest(key=key):
                self.assertFalse(self.check(pack_info={**self.pack, key: value})["release_eligible"])

    def test_empty_claims_unknown_duplicate_and_ambiguous_alignment(self):
        self.assertFalse(self.check(claim_map={**self.claim_map, "claims": []})["mechanical_ok"])
        for alignment in [[], self.job["alignment"] * 2, [{"claim_id": "unknown", "target_field": "body", "target_quote": "EURUSD"}]]:
            self.assertFalse(self.check(job={**self.job, "alignment": alignment})["mechanical_ok"])

    def test_value_elsewhere_does_not_satisfy_claim_span(self):
        result = self.check(job={**self.job, "alignment": [{"claim_id": "C1", "target_field": "body", "target_quote": "EURUSD is at 1.16141"}]})
        self.assertFalse(result["mechanical_ok"])

    def test_hash_and_source_receipt_id_are_mandatory(self):
        for key in ("claim_map_actual_sha256", "source_receipt_id", "writer_execution_id", "target_sha256", "pack_sha256"):
            with self.subTest(key=key):
                self.assertFalse(self.check(job={**self.job, key: None})["release_eligible"])

    def test_raw_crlf_hash_is_not_normalized(self):
        source = self.source.replace(b"\n", b"\r\n")
        result = validate_localized_candidate(source, self.target, job=self.job, claim_map=self.claim_map,
                                              trusted_receipts=self.receipts, pack_info=self.pack)
        self.assertEqual(result["source_sha256"], digest(source))
        self.assertFalse(result["mechanical_ok"])

    def test_protected_sign_substring_count_and_swapped_spans(self):
        source = b"Support -1.16%. Resistance 2.20%."
        claim_map = {"source_sha256": digest(source), "claims": [
            {"id": "C1", "source_quote": "Support -1.16%.",
             "protected": [{"id": "P1", "value_text": "-1.16%", "kind": "decimal", "unit": "%", "role": "support"}]},
            {"id": "C2", "source_quote": "Resistance 2.20%.",
             "protected": [{"id": "P2", "value_text": "2.20%", "kind": "decimal", "unit": "%", "role": "resistance"}]}]}
        for support, resistance in [("1.16%", "2.20%"), ("-1.160%", "2.20%"),
                                    ("2.20%", "-1.16%"), ("-1.16% -1.16%", "2.20%")]:
            with self.subTest(support=support, resistance=resistance):
                target = f"Support {support}. Resistance {resistance}.".encode()
                claim_hash = digest(json.dumps(claim_map).encode())
                job = {**self.job, "source_sha256": digest(source), "target_sha256": digest(target),
                       "claim_map_sha256": claim_hash, "claim_map_actual_sha256": claim_hash,
                       "alignment": [{"claim_id": "C1", "target_field": "body", "target_quote": f"Support {support}."},
                                     {"claim_id": "C2", "target_field": "body", "target_quote": f"Resistance {resistance}."}]}
                receipts = [{**self.receipts[0], "source_sha256": digest(source)}]
                result = validate_localized_candidate(source, target, job=job, claim_map=claim_map,
                                                      trusted_receipts=receipts, pack_info=self.pack)
                self.assertIn("PROTECTED_VALUE_MISSING", {f["code"] for f in result["findings"]})

    def test_malformed_nested_inputs_return_findings(self):
        for claims in (None, {}, [None], [{"id": [], "protected": []}]):
            with self.subTest(claims=claims):
                self.assertFalse(self.check(claim_map={**self.claim_map, "claims": claims})["release_eligible"])

    def test_visual_hashes_and_duplicate_gates_are_rejected(self):
        receipts = [dict(r) for r in self.receipts]
        receipts[3]["image_hashes"] = {"image.png": digest(b"changed")}
        self.assertFalse(self.check(trusted_receipts=receipts)["release_eligible"])
        self.assertFalse(self.check(trusted_receipts=[*self.receipts, self.receipts[1]])["release_eligible"])

    def test_visual_hashes_may_use_legacy_evidence_container(self):
        receipts = [dict(r) for r in self.receipts]
        hashes = {"chart.webp": digest(b"chart")}
        for index in (3, 4):
            receipts[index] = {key: value for key, value in receipts[index].items()
                               if key != "image_hashes"}
            receipts[index]["evidence"] = {"image_hashes": {"handoff/article/images/chart.webp": hashes["chart.webp"]}}
        result = self.check(job={**self.job, "image_hashes": hashes}, trusted_receipts=receipts)
        self.assertTrue(result["release_eligible"])

    def test_ambiguous_quote_rejected(self):
        target = self.target * 2
        result = validate_localized_candidate(self.source, target, job={**self.job, "target_sha256": digest(target)},
                                              claim_map=self.claim_map, trusted_receipts=self.receipts[:1], pack_info=self.pack)
        self.assertIn("TARGET_ANCHOR_MISSING", {f["code"] for f in result["findings"]})

    def test_valid_candidate_is_release_eligible(self):
        result = validate_localized_candidate(self.source, self.target, job=self.job,
                                              claim_map=self.claim_map,
                                              trusted_receipts=self.receipts,
                                              pack_info=self.pack)
        self.assertTrue(result["mechanical_ok"])
        self.assertEqual(result["review_status"], "VERIFIED")
        self.assertTrue(result["release_eligible"])

    def test_style_d_candidate_requires_first_h2_structure_heading(self):
        target = (b"---\n"
                  b"title: Weekly market review 7-11 September 2026\n"
                  b"---\n\n"
                  b"## Market structure\n\n" + self.target)
        job = {**self.job, "style": "D", "week_start": "2026-09-07",
               "week_end": "2026-09-11", "target_sha256": digest(target),
               "alignment": [{"claim_id": "C1", "target_field": "body",
                              "target_quote": self.target.decode().strip()}]}
        receipts = [{**receipt, "target_sha256": digest(target)}
                    if receipt.get("gate") != "source_acceptance" else receipt
                    for receipt in self.receipts]
        result = self.check(job=job, target=target, trusted_receipts=receipts)
        self.assertTrue(result["release_eligible"])

    def test_style_d_candidate_rejects_legacy_intro_before_first_h2(self):
        target = (b"---\n"
                  b"title: Weekly market review 7-11 September 2026\n"
                  b"---\n\n"
                  b"# Legacy intro\n\n"
                  b"## Market structure\n\n" + self.target)
        job = {**self.job, "style": "D", "week_start": "2026-09-07",
               "week_end": "2026-09-11", "target_sha256": digest(target),
               "alignment": [{"claim_id": "C1", "target_field": "body",
                              "target_quote": self.target.decode().strip()}]}
        receipts = [{**receipt, "target_sha256": digest(target)}
                    if receipt.get("gate") != "source_acceptance" else receipt
                    for receipt in self.receipts]
        result = self.check(job=job, target=target, trusted_receipts=receipts)
        self.assertIn("STYLE_D_BODY_START", {finding["code"] for finding in result["findings"]})

    def test_one_claim_can_span_multiple_distinct_target_sentences(self):
        alignment = [{"claim_id": "C1", "target_field": "body", "target_quote": quote}
                     for quote in ("EURUSD is at 1.16141.",
                                   "If it holds above 1.16206, the direction will be confirmed.")]
        self.assertTrue(self.check(job={**self.job, "alignment": alignment})["release_eligible"])
        # Removing one sentence must not borrow its protected value from outside the spans.
        result = self.check(job={**self.job, "alignment": alignment[:1]})
        self.assertIn("PROTECTED_VALUE_MISSING", {f["code"] for f in result["findings"]})

    def test_overlapping_target_spans_cannot_double_count_protected_values(self):
        for quote in ("EURUSD is at 1.16141.", self.target.decode().strip()):
            alignment = [*self.job["alignment"],
                         {"claim_id": "C1", "target_field": "body", "target_quote": quote}]
            result = self.check(job={**self.job, "alignment": alignment})
            self.assertIn("TARGET_ANCHOR_OVERLAP", {f["code"] for f in result["findings"]})

    def test_self_overlapping_quote_occurrences_are_ambiguous(self):
        target = b"aaa"
        job = {**self.job, "target_sha256": digest(target),
               "alignment": [{"claim_id": "C1", "target_field": "body", "target_quote": "aa"}]}
        result = validate_localized_candidate(self.source, target, job=job, claim_map=self.claim_map,
                                              trusted_receipts=self.receipts[:1], pack_info=self.pack)
        self.assertIn("TARGET_ANCHOR_MISSING", {f["code"] for f in result["findings"]})

    def test_required_review_metadata_applies_to_source_and_target(self):
        for index in range(len(self.receipts)):
            for key, value in (("receipt_id", ""), ("reviewer_kind", None),
                               ("reviewed_at", None), ("reviewed_at", "yesterday"),
                               ("reviewed_at", "2026-09-07T12:00:00"),
                               ("findings", None), ("findings", [{"severity": "critical"}])):
                with self.subTest(index=index, key=key, value=value):
                    receipts = [dict(r) for r in self.receipts]
                    receipts[index][key] = value
                    self.assertFalse(self.check(trusted_receipts=receipts)["release_eligible"])

    def test_source_receipt_must_bind_pack_and_claim_map(self):
        for key in ("pack_sha256", "claim_map_sha256"):
            receipt = {**self.receipts[0], key: digest(b"stale")}
            result = self.check(trusted_receipts=[receipt, *self.receipts[1:]])
            self.assertIn("RECEIPT_MISMATCH", {f["code"] for f in result["findings"]})

    def test_protected_fields_are_required(self):
        for key in ("id", "kind", "value_text", "unit", "role"):
            with self.subTest(key=key):
                claim_map = json.loads(json.dumps(self.claim_map))
                del claim_map["claims"][0]["protected"][0][key]
                result = self.check(claim_map=claim_map)
                self.assertIn("CLAIM_MAP_INVALID", {f["code"] for f in result["findings"]})

    def test_localized_validation_does_not_call_thai_comparison(self):
        from unittest.mock import patch

        with patch("tools.language_patch.compare_fragment", side_effect=AssertionError("Thai path")):
            self.assertTrue(self.check()["release_eligible"])

    def test_draft_pack_stays_candidate_only(self):
        result = validate_localized_candidate(self.source, self.target, job=self.job,
                                              claim_map=self.claim_map,
                                              trusted_receipts=self.receipts,
                                              pack_info={**self.pack, "status": "draft"})
        self.assertTrue(result["mechanical_ok"])
        self.assertFalse(result["pack_ready"])
        self.assertFalse(result["release_eligible"])

    def test_source_change_is_rejected(self):
        result = validate_localized_candidate(self.source + b"changed", self.target, job=self.job,
                                              claim_map=self.claim_map,
                                              trusted_receipts=self.receipts,
                                              pack_info=self.pack)
        self.assertFalse(result["mechanical_ok"])
        self.assertIn("SOURCE_CHANGED", {item["code"] for item in result["findings"]})

    def test_wrong_country_and_missing_protected_value_are_rejected(self):
        job = {**self.job, "country_code": "MY", "content_locale": "ms-MY"}
        target = self.target.replace(b"1.16206", b"1.16207")
        job["alignment"] = [{"claim_id": "C1", "target_field": "body", "target_quote": target.decode().strip()}]
        result = validate_localized_candidate(self.source, target, job=job,
                                              claim_map=self.claim_map,
                                              trusted_receipts=self.receipts,
                                              pack_info=self.pack)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("INPUT_INVALID", codes)
        self.assertIn("PROTECTED_VALUE_MISSING", codes)

    def test_writer_cannot_be_reviewer(self):
        receipts = [*self.receipts]
        receipts[1] = {**receipts[1], "reviewer_execution_id": "writer-1"}
        result = validate_localized_candidate(self.source, self.target, job=self.job,
                                              claim_map=self.claim_map,
                                              trusted_receipts=receipts,
                                              pack_info=self.pack)
        self.assertIn("REVIEW_NOT_INDEPENDENT", {item["code"] for item in result["findings"]})


if __name__ == "__main__":
    unittest.main()
