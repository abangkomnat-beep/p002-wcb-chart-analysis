from __future__ import annotations

import json
import unittest
from pathlib import Path

import jsonschema

from tools import quality_scoring, quality_summary
from tests.test_quality_scoring import H, payload

ROOT = Path(__file__).resolve().parents[1]


class QualitySchemaTests(unittest.TestCase):
    def schema(self, name):
        return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))

    def test_evaluation_revision_and_history_validate(self):
        evaluation = quality_scoring.evaluate(payload(70))
        jsonschema.validate(evaluation, self.schema("quality-evaluation-v1.schema.json"))
        revision = quality_scoring.make_revision_brief(evaluation, article_hash=H)
        jsonschema.validate(revision, self.schema("revision-brief-v1.schema.json"))
        history = quality_scoring.append_history(None, evaluation)
        jsonschema.validate(history, self.schema("quality-attempt-history-v1.schema.json"))

    def test_schema_rejects_extra_property_bad_hash_and_owner(self):
        evaluation = quality_scoring.evaluate(payload())
        evaluation["extra"] = True
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(evaluation, self.schema("quality-evaluation-v1.schema.json"))
        revision = quality_scoring.make_revision_brief(quality_scoring.evaluate(payload(70)),
                                                       article_hash=H)
        revision["article_hash"] = "bad"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(revision, self.schema("revision-brief-v1.schema.json"))
        revision["article_hash"] = H
        revision["issues"][0]["owner"] = "UNKNOWN"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(revision, self.schema("revision-brief-v1.schema.json"))

    def test_summary_rejects_schema_valid_but_semantically_forged_score(self):
        evaluation = quality_scoring.evaluate(payload())
        evaluation["calculation"]["overall_score"] = 99
        with self.assertRaisesRegex(quality_scoring.QualityScoringError, "semantically"):
            quality_summary.render(evaluation)

    def test_summary_rejects_out_of_range_and_incomplete_envelopes(self):
        evaluation = quality_scoring.evaluate(payload())
        evaluation["calculation"]["overall_score"] = 999
        with self.assertRaisesRegex(quality_scoring.QualityScoringError, "schema"):
            quality_summary.render(evaluation)
        with self.assertRaisesRegex(quality_scoring.QualityScoringError, "schema"):
            quality_summary.render({"schema": "quality-evaluation-v1", "status": "PASS_SCORE"})

    def test_summary_renders_only_calculator_coherent_evaluation(self):
        rendered = quality_summary.render(quality_scoring.evaluate(payload()))
        self.assertIn("Overall: 90.00%", rendered)


if __name__ == "__main__":
    unittest.main()
