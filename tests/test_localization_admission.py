import hashlib
import json

import pytest

from tools import baseline_registry
from tools import localization_admission as admission


def _setup_release(tmp_path):
    output = tmp_path / "output"
    folder = output / "09-09-2026/MY-Malaysia"
    article = folder / "E-XAUUSD/article.md"
    article.parent.mkdir(parents=True)
    article.write_text("localized", encoding="utf-8")
    pack = baseline_registry.verify("ms-MY")
    manifest = {"schema": "p002-localized-release/v2", "country_code": "MY",
                "source_business_date": "2026-09-09", "expected_articles": 4,
                "language_pack": "ms-MY", "pack_version": pack["version"],
                "pack_sha256": pack["actual_sha256"],
                "files": {"E-XAUUSD/article.md": hashlib.sha256(article.read_bytes()).hexdigest()}}
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    review = tmp_path / "work/review.json"
    review.parent.mkdir(parents=True)
    review.write_text(json.dumps({"status": "PASS", "reviewer_execution_id": "reviewer-1"}), encoding="utf-8")
    record = tmp_path / "work/admission.json"
    record.write_text(json.dumps({"schema": admission.SCHEMA, "status": "ADMITTED", "country_code": "MY",
        "source_business_date": "2026-09-09", "admitter_identity": "lead", "admitter_execution_id": "lead-1",
        "writer_execution_id": "writer-1", "review_receipt_path": "work/review.json",
        "review_receipt_sha256": hashlib.sha256(review.read_bytes()).hexdigest(),
        "language_pack": manifest["language_pack"], "pack_version": manifest["pack_version"],
        "pack_sha256": manifest["pack_sha256"]}), encoding="utf-8")
    return output, record


def test_admission_requires_current_delivery_pack_and_independent_review(tmp_path):
    output, record = _setup_release(tmp_path)
    result = admission.validate(record, project_root=tmp_path, output_root=output)
    assert result["status"] == "PASS"


def test_admission_rejects_writer_review(tmp_path):
    output, record = _setup_release(tmp_path)
    review = tmp_path / "work/review.json"
    review.write_text(json.dumps({"status": "PASS", "reviewer_execution_id": "writer-1"}), encoding="utf-8")
    body = json.loads(record.read_text(encoding="utf-8"))
    body["review_receipt_sha256"] = hashlib.sha256(review.read_bytes()).hexdigest()
    record.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(admission.AdmissionError, match="writer review"):
        admission.validate(record, project_root=tmp_path, output_root=output)


def test_admission_accepts_complete_canonical_aggregate_review(tmp_path):
    output, record = _setup_release(tmp_path)
    review = tmp_path / "work/review.json"
    aggregate = {
        "schema": "p002-independent-review/v1",
        "status": "PASS_INDEPENDENT_REVIEW",
        "review_execution_id": "reviewer-aggregate-1",
        "writer_execution_id": "writer-1",
        "independent_from_writer": True,
        "gates": {gate: {"status": "PASS"}
                  for gate in ("language", "semantic", "visual", "package_input")},
    }
    review.write_text(json.dumps(aggregate), encoding="utf-8")
    body = json.loads(record.read_text(encoding="utf-8"))
    body["review_receipt_sha256"] = hashlib.sha256(review.read_bytes()).hexdigest()
    record.write_text(json.dumps(body), encoding="utf-8")
    assert admission.validate(record, project_root=tmp_path, output_root=output)["status"] == "PASS"
