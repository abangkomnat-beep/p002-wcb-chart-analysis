"""Validate a human source-QA receipt against a frozen source binding.

This module verifies evidence identity only.  It never decides whether market
claims are correct and never creates a PASS receipt.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = REPO_ROOT.parent
RECEIPT_SCHEMA = "p002-source-qa-receipt/v1"


class SourceAcceptanceError(ValueError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceAcceptanceError(f"cannot read JSON evidence: {path}") from exc
    if not isinstance(data, dict):
        raise SourceAcceptanceError(f"evidence must be an object: {path}")
    return data


def _inside(root: Path, relative_path: str) -> Path:
    candidate = (root / relative_path).resolve()
    if root.resolve() not in candidate.parents:
        raise SourceAcceptanceError(f"evidence path escapes project: {relative_path}")
    return candidate


def _image_fingerprint(images: list[Mapping[str, Any]]) -> str:
    payload = "\n".join(f"{item['name']}:{item['sha256']}" for item in images).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_evidence(evidence: Any, project_root: Path, calendar_applicability: Any = None) -> list[dict[str, Any]]:
    if not isinstance(evidence, list) or not evidence:
        raise SourceAcceptanceError("receipt must contain reviewer evidence")
    checked: list[dict[str, Any]] = []
    for item in evidence:
        if not isinstance(item, Mapping):
            raise SourceAcceptanceError("reviewer evidence must be an object")
        kind = item.get("kind")
        relative_path = item.get("path")
        expected_hash = item.get("sha256")
        if not all(isinstance(value, str) and value for value in (kind, relative_path, expected_hash)):
            raise SourceAcceptanceError("reviewer evidence requires kind, path and sha256")
        if len(expected_hash) != 64 or any(char not in "0123456789abcdef" for char in expected_hash):
            raise SourceAcceptanceError("reviewer evidence sha256 is invalid")
        path = _inside(project_root, relative_path)
        if not path.is_file() or _sha(path) != expected_hash:
            raise SourceAcceptanceError("reviewer evidence changed or is missing")
        checked.append({"kind": kind, "path": relative_path, "sha256": expected_hash})
    required_kinds = {"calendar", "snapshot"}
    if calendar_applicability is not None:
        if not isinstance(calendar_applicability, Mapping):
            raise SourceAcceptanceError("calendar applicability must be an object")
        status = calendar_applicability.get("status")
        if status == "not_applicable":
            reason = calendar_applicability.get("reason")
            report_hash = calendar_applicability.get("review_report_sha256")
            if (calendar_applicability.get("reviewer_attests_no_calendar_claims") is not True
                    or not isinstance(reason, str) or not reason.strip()
                    or not isinstance(report_hash, str) or not report_hash
                    or not any(item["kind"] == "source_review" and item["sha256"] == report_hash
                               for item in checked)):
                raise SourceAcceptanceError("calendar N/A requires reviewer attestation, reason and hash-bound source review")
            required_kinds = {"snapshot", "source_review"}
        elif status != "required":
            raise SourceAcceptanceError("unknown calendar applicability status")
    if not {item["kind"] for item in checked}.issuperset(required_kinds):
        raise SourceAcceptanceError("receipt requires calendar and snapshot evidence")
    return checked


def validate_source_acceptance(
    receipt_path: Path,
    article: Mapping[str, Any],
    *,
    source_business_date: str,
    bindings_dir: Path,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    """Return a verified receipt or raise if its source evidence is stale.

    ``article`` must be one entry from a p002-source-bindings/v2 manifest.
    ``bindings_dir`` is used for the claim-map path stored in that manifest.
    """
    receipt = _read_json(Path(receipt_path))
    if receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("status") != "PASS":
        raise SourceAcceptanceError("receipt is not a passing source-QA receipt")
    required = ("article_id", "source_business_date", "reviewer_identity", "reviewer_execution_id")
    missing = [key for key in required if not isinstance(receipt.get(key), str) or not receipt[key].strip()]
    if missing:
        raise SourceAcceptanceError("receipt missing required fields: " + ", ".join(missing))
    if receipt["article_id"] != article.get("article_id"):
        raise SourceAcceptanceError("receipt article does not match source binding")
    if receipt["source_business_date"] != source_business_date:
        raise SourceAcceptanceError("receipt business date does not match source binding")
    if receipt.get("revoked") is True:
        raise SourceAcceptanceError("receipt has been revoked")
    if receipt.get("writer_execution_id") == receipt["reviewer_execution_id"]:
        raise SourceAcceptanceError("source writer cannot review the same source execution")

    source_path = _inside(Path(project_root), str(article["source_path"]))
    if not source_path.is_file() or _sha(source_path) != article.get("source_sha256"):
        raise SourceAcceptanceError("source article changed after binding")
    images = list(article.get("images") or [])
    for image in images:
        image_path = _inside(Path(project_root), str(image["path"]))
        if not image_path.is_file() or _sha(image_path) != image.get("sha256"):
            raise SourceAcceptanceError("source image changed after binding")
    if _image_fingerprint(images) != article.get("source_images_sha256"):
        raise SourceAcceptanceError("source image inventory does not match binding")

    claim_path = _inside(Path(bindings_dir), str(article["claim_map_path"]))
    if not claim_path.is_file() or _sha(claim_path) != article.get("claim_map_sha256"):
        raise SourceAcceptanceError("claim map changed after binding")
    receipt_hashes = receipt.get("binding_hashes") or {}
    expected_hashes = {
        "source_sha256": article["source_sha256"],
        "source_images_sha256": article["source_images_sha256"],
        "claim_map_sha256": article["claim_map_sha256"],
    }
    if receipt_hashes != expected_hashes:
        raise SourceAcceptanceError("receipt binding hashes do not match frozen source")
    _validate_evidence(receipt.get("evidence"), Path(project_root), receipt.get("calendar_applicability"))
    return receipt
