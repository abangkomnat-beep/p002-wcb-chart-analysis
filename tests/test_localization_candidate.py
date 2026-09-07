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
            "claims": [{"id": "C1", "protected": [
                {"id": "P1", "value_text": "1.16141", "role": "price"},
                {"id": "P2", "value_text": "1.16206", "role": "level"},
            ]}],
        }
        self.job = {
            "article_id": "eurusd-20260907",
            "country_code": "ZA", "content_locale": "en-ZA",
            "language_pack": "en-001", "pack_version": "0.1.0",
            "pack_sha256": "packhash", "source_sha256": digest(self.source),
            "claim_map_sha256": "claimhash", "target_sha256": digest(self.target),
            "writer_execution_id": "writer-1",
            "alignment": [{"claim_id": "C1", "target_quote": "EURUSD is at 1.16141"}],
        }
        self.receipts = [{"gate": "source_acceptance", "article_id": self.job["article_id"],
                          "source_sha256": digest(self.source), "verdict": "PASS"},
                         {"gate": "language", "article_id": self.job["article_id"],
                          "target_sha256": digest(self.target), "reviewer_execution_id": "review-1",
                          "verdict": "PASS"}]
        self.pack = {"locale": "en-001", "version": "0.1.0", "status": "stable_locked",
                     "sha256": "packhash"}

    def test_valid_candidate_is_release_eligible(self):
        result = validate_localized_candidate(self.source, self.target, job=self.job,
                                              claim_map=self.claim_map,
                                              trusted_receipts=self.receipts,
                                              pack_info=self.pack)
        self.assertTrue(result["mechanical_ok"])
        self.assertEqual(result["review_status"], "VERIFIED")
        self.assertTrue(result["release_eligible"])

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
