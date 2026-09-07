import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.package_localized_country import check_country, commit_country


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PackageCountryTests(unittest.TestCase):
    def make_fixture(self, pack_status="stable_locked"):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        (root / "Repo").mkdir()
        run = root / "work" / "localization" / "2026-09-07" / "za-r1"
        (run / "claims").mkdir(parents=True)
        (run / "candidates").mkdir()
        source = (root / "Repo" / "eurusd.md")
        candidate = run / "candidates" / "eurusd.md"
        source.write_text("ราคา EURUSD อยู่ที่ 1.16141 หากยืนเหนือ 1.16206\n", encoding="utf-8")
        candidate.write_text("EURUSD is at 1.16141. If it holds above 1.16206.\n", encoding="utf-8")
        claim = run / "claims" / "eurusd.json"
        claim.write_text(json.dumps({"source_sha256": sha(source), "claims": [{"id": "C1", "protected": [
            {"value_text": "1.16141"}, {"value_text": "1.16206"}]}]}), encoding="utf-8")
        manifest = run / "source-manifest.json"
        manifest.write_text(json.dumps({
            "schema": "p002-za-source/v1", "country_code": "ZA", "content_locale": "en-ZA",
            "language_pack": "en-001", "pack_version": "0.1.0", "pack_status": pack_status,
            "pack_sha256": "packhash", "source_business_date": "2026-09-07", "output_root": "output",
            "articles": [{"article_id": "eurusd-20260907", "style": "L", "asset": "EURUSD",
                           "source_path": "Repo/eurusd.md", "source_sha256": sha(source),
                           "candidate_path": "candidates/eurusd.md", "claim_map_path": "claims/eurusd.json",
                           "claim_map_sha256": "claimhash", "writer_execution_id": "writer-1",
                           "alignment": [{"claim_id": "C1", "target_quote": "EURUSD is at 1.16141"}]}]
        }), encoding="utf-8")
        receipt = run / "receipts.json"
        receipt.write_text(json.dumps({"receipts": [
            {"gate": "source_acceptance", "article_id": "eurusd-20260907", "source_sha256": sha(source), "verdict": "PASS"},
            {"gate": "language", "article_id": "eurusd-20260907", "target_sha256": sha(candidate),
             "reviewer_execution_id": "review-1", "verdict": "PASS"},
        ]}), encoding="utf-8")
        return temp, root, manifest, receipt

    def test_check_draft_is_read_only_hold(self):
        temp, root, manifest, receipt = self.make_fixture("draft")
        try:
            before = sorted(str(p.relative_to(root)) for p in root.rglob("*"))
            result = check_country(manifest, receipt, root)
            after = sorted(str(p.relative_to(root)) for p in root.rglob("*"))
            self.assertEqual(result["status"], "HOLD")
            self.assertFalse(result["release_eligible"])
            self.assertEqual(before, after)
        finally:
            temp.cleanup()

    def test_stable_pack_can_commit_after_check(self):
        temp, root, manifest, receipt = self.make_fixture("stable_locked")
        try:
            result = check_country(manifest, receipt, root)
            self.assertEqual(result["status"], "PASS")
            committed = commit_country(manifest, receipt, root, "r0001", "b0001")
            self.assertEqual(committed["status"], "PASS")
            release = root / "output" / "134-Localized" / "ZA-South-Africa" / "en-ZA" / "releases" / "r0001"
            self.assertTrue((release / "manifest.json").is_file())
            self.assertTrue((root / "output" / "134-Localized" / "batches" / "b0001.json").is_file())
        finally:
            temp.cleanup()


if __name__ == "__main__":
    unittest.main()
