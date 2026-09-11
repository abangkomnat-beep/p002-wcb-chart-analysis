import hashlib
import json
from pathlib import Path

import pytest

from tools.source_qa_acceptance import SourceAcceptanceError, validate_source_acceptance


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path):
    project = tmp_path / "P002"
    article_path = project / "output/09-09-2026/TH-Thailand/E/XAUUSD/article.md"
    image_path = article_path.parent / "chart.webp"
    claim_path = project / "work/localization/09-09-2026/source-bindings/claims/e-xauusd.json"
    for path, content in ((article_path, b"price 4436.46"), (image_path, b"image"), (claim_path, b"{}")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    image = {"name": "chart.webp", "path": image_path.relative_to(project).as_posix(), "sha256": _sha(image_path)}
    image_fingerprint = hashlib.sha256(b"chart.webp:" + image["sha256"].encode()).hexdigest()
    article = {
        "article_id": "E-XAUUSD", "source_path": article_path.relative_to(project).as_posix(),
        "source_sha256": _sha(article_path), "images": [image],
        "source_images_sha256": image_fingerprint,
        "claim_map_path": "claims/e-xauusd.json", "claim_map_sha256": _sha(claim_path),
    }
    hashes = {key: article[key] for key in ("source_sha256", "source_images_sha256", "claim_map_sha256")}
    evidence = []
    for kind in ("calendar", "snapshot"):
        evidence_path = project / f"work/evidence/{kind}.json"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(json.dumps({"kind": kind}), encoding="utf-8")
        evidence.append({"kind": kind, "path": evidence_path.relative_to(project).as_posix(),
                         "sha256": _sha(evidence_path)})
    receipt = {
        "schema": "p002-source-qa-receipt/v1", "status": "PASS", "article_id": "E-XAUUSD",
        "source_business_date": "2026-09-09", "reviewer_identity": "reviewer-1",
        "reviewer_execution_id": "review-001", "binding_hashes": hashes,
        "evidence": evidence,
    }
    receipt_path = project / "work/receipts/e-xauusd.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return project, article, receipt_path, claim_path


def test_acceptance_receipt_requires_current_article_image_claims_and_evidence(tmp_path):
    project, article, receipt_path, _ = _fixture(tmp_path)
    receipt = validate_source_acceptance(
        receipt_path, article, source_business_date="2026-09-09",
        bindings_dir=project / "work/localization/09-09-2026/source-bindings", project_root=project,
    )
    assert receipt["reviewer_execution_id"] == "review-001"


@pytest.mark.parametrize("target", ("article", "image", "claim"))
def test_acceptance_rejects_changed_source_evidence(tmp_path, target):
    project, article, receipt_path, claim_path = _fixture(tmp_path)
    if target == "article":
        (project / article["source_path"]).write_text("changed", encoding="utf-8")
    elif target == "image":
        (project / article["images"][0]["path"]).write_bytes(b"changed")
    else:
        claim_path.write_text('{"changed": true}', encoding="utf-8")
    with pytest.raises(SourceAcceptanceError, match="changed"):
        validate_source_acceptance(receipt_path, article, source_business_date="2026-09-09",
                                   bindings_dir=project / "work/localization/09-09-2026/source-bindings",
                                   project_root=project)


def test_acceptance_rejects_revoked_or_self_review_receipt(tmp_path):
    project, article, receipt_path, _ = _fixture(tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["writer_execution_id"] = receipt["reviewer_execution_id"]
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(SourceAcceptanceError, match="writer"):
        validate_source_acceptance(receipt_path, article, source_business_date="2026-09-09",
                                   bindings_dir=project / "work/localization/09-09-2026/source-bindings",
                                   project_root=project)


def test_acceptance_rejects_missing_or_changed_reviewer_evidence(tmp_path):
    project, article, receipt_path, _ = _fixture(tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    evidence_path = project / receipt["evidence"][0]["path"]
    evidence_path.write_text('{"changed": true}', encoding="utf-8")
    with pytest.raises(SourceAcceptanceError, match="evidence changed"):
        validate_source_acceptance(receipt_path, article, source_business_date="2026-09-09",
                                   bindings_dir=project / "work/localization/09-09-2026/source-bindings",
                                   project_root=project)


@pytest.mark.parametrize("failure", [None, "missing_attestation", "blank_reason", "wrong_report_hash", "changed_report", "missing_applicability", "missing_snapshot", "unknown_status"])
def test_calendar_not_applicable_requires_explicit_hash_bound_review(tmp_path, failure):
    project, article, receipt_path, _ = _fixture(tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["evidence"] = [item for item in receipt["evidence"] if item["kind"] == "snapshot"]
    report = project / "work/evidence/review.md"
    report.write_text("Reviewer inspected the bound article and all images; no calendar claims.", encoding="utf-8")
    report_hash = _sha(report)
    receipt["evidence"].append({"kind": "source_review", "path": "work/evidence/review.md", "sha256": report_hash})
    receipt["calendar_applicability"] = {
        "status": "not_applicable", "reviewer_attests_no_calendar_claims": True,
        "reason": "Article and chart claims concern technical prices only.",
        "review_report_sha256": report_hash,
    }
    if failure == "missing_attestation":
        del receipt["calendar_applicability"]["reviewer_attests_no_calendar_claims"]
    elif failure == "blank_reason":
        receipt["calendar_applicability"]["reason"] = " "
    elif failure == "wrong_report_hash":
        receipt["calendar_applicability"]["review_report_sha256"] = "0" * 64
    elif failure == "changed_report":
        report.write_text("changed", encoding="utf-8")
    elif failure == "missing_applicability":
        del receipt["calendar_applicability"]
    elif failure == "missing_snapshot":
        receipt["evidence"] = [item for item in receipt["evidence"] if item["kind"] != "snapshot"]
    elif failure == "unknown_status":
        receipt["calendar_applicability"]["status"] = "skip"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    args = dict(source_business_date="2026-09-09", bindings_dir=project / "work/localization/09-09-2026/source-bindings", project_root=project)
    if failure:
        with pytest.raises(SourceAcceptanceError):
            validate_source_acceptance(receipt_path, article, **args)
    else:
        assert validate_source_acceptance(receipt_path, article, **args)["status"] == "PASS"
