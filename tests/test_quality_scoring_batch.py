from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema

from tools import quality_scoring
from tests.test_quality_scoring import payload

ROOT = Path(__file__).resolve().parents[1]


class BatchTests(unittest.TestCase):
    def test_fifty_jobs_are_isolated_complete_and_atomic(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            inputs = []
            for index in range(50):
                value = payload(90)
                value["job_id"] = f"job-{index:02d}"
                value["article_id"] = f"article-{index:02d}"
                source = root / "inputs" / f"{index:02d}.json"
                source.parent.mkdir(exist_ok=True)
                source.write_text(json.dumps(value), encoding="utf-8")
                inputs.append(source)
            summary = quality_scoring.evaluate_batch(inputs, root / "qa")
            self.assertEqual((summary["total"], summary["succeeded"], summary["failed"]),
                             (50, 50, 0))
            outputs = list((root / "qa").rglob("evaluation.json"))
            self.assertEqual(len(outputs), 50)
            identities = {(json.loads(path.read_text())["job_id"],
                           json.loads(path.read_text())["article_id"]) for path in outputs}
            self.assertEqual(len(identities), 50)
            self.assertFalse(list((root / "qa").rglob(".*.tmp")))

    def test_partial_failure_and_duplicate_do_not_erase_good_results(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            good = root / "good.json"
            bad = root / "bad.json"
            good.write_text(json.dumps(payload()), encoding="utf-8")
            bad.write_text("not-json", encoding="utf-8")
            summary = quality_scoring.evaluate_batch([good, bad, good], root / "qa")
            self.assertEqual((summary["succeeded"], summary["failed"]), (1, 2))
            self.assertEqual(len(list((root / "qa").rglob("evaluation.json"))), 1)

    def test_hostile_non_finite_and_timestamp_jobs_are_isolated_in_any_order(self):
        schema = json.loads((ROOT / "schemas" / "quality-evaluation-v1.schema.json")
                            .read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sources = []
            hostile_values = [float("nan"), float("inf"), float("-inf")]
            for index, hostile in enumerate(hostile_values):
                value = payload()
                value["job_id"] = f"bad-number-{index}"
                next(iter(value["criterion_judgments"].values()))["score"] = hostile
                source = root / f"bad-number-{index}.json"
                source.write_text(json.dumps(value), encoding="utf-8")
                sources.append(source)
            for index, timestamp in enumerate(("not-a-date", "2026-09-04T12:30:00")):
                value = payload()
                value["job_id"] = f"bad-time-{index}"
                value["created_at"] = timestamp
                source = root / f"bad-time-{index}.json"
                source.write_text(json.dumps(value), encoding="utf-8")
                sources.append(source)
            good_before = payload()
            good_before["job_id"] = "good-before"
            good_after = payload()
            good_after["job_id"] = "good-after"
            before_path = root / "good-before.json"
            after_path = root / "good-after.json"
            before_path.write_text(json.dumps(good_before), encoding="utf-8")
            after_path.write_text(json.dumps(good_after), encoding="utf-8")
            summary = quality_scoring.evaluate_batch(
                [before_path, *sources, after_path], root / "qa")
            self.assertEqual((summary["succeeded"], summary["failed"]), (2, 5))
            outputs = list((root / "qa").rglob("evaluation.json"))
            self.assertEqual(len(outputs), 2)
            self.assertEqual({json.loads(path.read_text())["job_id"] for path in outputs},
                             {"good-before", "good-after"})
            for path in outputs:
                jsonschema.validate(json.loads(path.read_text(encoding="utf-8")), schema)

    def test_cli_reports_hostile_job_and_preserves_good_sibling(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bad = payload()
            bad["job_id"] = "bad"
            next(iter(bad["criterion_judgments"].values()))["score"] = float("nan")
            good = payload()
            good["job_id"] = "good"
            bad_path, good_path = root / "bad.json", root / "good.json"
            bad_path.write_text(json.dumps(bad), encoding="utf-8")
            good_path.write_text(json.dumps(good), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-m", "tools.quality_scoring", str(bad_path),
                 str(good_path), "--output-root", str(root / "qa")],
                cwd=ROOT, text=True, capture_output=True, check=False, timeout=20)
            self.assertEqual(completed.returncode, 1)
            summary = json.loads(completed.stdout)
            self.assertEqual((summary["succeeded"], summary["failed"]), (1, 1))
            self.assertTrue((root / "qa" / "good" / "article-1" / "attempt-01"
                             / "evaluation.json").is_file())
            self.assertFalse((root / "qa" / "bad").exists())

    def test_unsafe_identity_segments_never_escape_output_root(self):
        unsafe = [".", "..", "../escape", "..\\escape", "/absolute", "C:\\escape",
                  "\\\\server\\share", "%2e%2e", "safe%2fescape", "a/b", "a\\b"]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            qa = root / "qa"
            inputs = []
            for index, identity in enumerate(unsafe):
                value = payload()
                value["job_id"] = identity
                source = root / f"unsafe-{index}.json"
                source.write_text(json.dumps(value), encoding="utf-8")
                inputs.append(source)
            summary = quality_scoring.evaluate_batch(inputs, qa)
            self.assertEqual(summary["succeeded"], 0)
            self.assertEqual(summary["failed"], len(unsafe))
            self.assertFalse(list(qa.rglob("evaluation.json")) if qa.exists() else [])
            self.assertFalse((root / "escape").exists())

    def test_resolved_containment_rejects_symlink_escape_when_supported(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            qa = root / "qa"
            outside = root / "outside"
            qa.mkdir()
            outside.mkdir()
            try:
                (qa / "job-1").symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("directory symlinks unavailable")
            source = root / "input.json"
            source.write_text(json.dumps(payload()), encoding="utf-8")
            summary = quality_scoring.evaluate_batch([source], qa)
            self.assertEqual((summary["succeeded"], summary["failed"]), (0, 1))
            self.assertFalse(list(outside.rglob("evaluation.json")))


if __name__ == "__main__":
    unittest.main()
