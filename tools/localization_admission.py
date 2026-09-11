"""Validate a human-issued admission record for one localized country release.

Admission is a separate decision from packaging.  This module authenticates
the current country release, locked language pack and independent review
receipt, but it never creates an ADMITTED record itself.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tools import baseline_registry
from tools.active_rollout import requested_selection
from tools.country_delivery_coverage import _day_folder, _verify_country

SCHEMA = "p002-localization-admission/v1"


class AdmissionError(ValueError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdmissionError(f"cannot read admission evidence: {path}") from exc
    if not isinstance(value, dict):
        raise AdmissionError("admission evidence must be an object")
    return value


def _inside(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise AdmissionError("evidence path is required")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise AdmissionError("evidence path escapes the project") from exc
    return candidate


def validate(record_path: Path, *, project_root: Path, output_root: Path) -> dict[str, Any]:
    record_path = Path(record_path)
    record = _read(record_path)
    if record.get("schema") != SCHEMA or record.get("status") != "ADMITTED":
        raise AdmissionError("admission record is not an ADMITTED p002 record")
    required = ("country_code", "source_business_date", "admitter_identity", "admitter_execution_id",
                "writer_execution_id", "review_receipt_path", "review_receipt_sha256")
    missing = [key for key in required if not isinstance(record.get(key), str) or not record[key].strip()]
    if missing:
        raise AdmissionError("admission record missing: " + ", ".join(missing))
    if record["admitter_execution_id"] == record["writer_execution_id"]:
        raise AdmissionError("writer cannot admit its own release")
    country = record["country_code"]
    selection = requested_selection([country])
    row = selection["countries"][0]
    if not row["eligible"]:
        raise AdmissionError("country localization is disabled")
    day_root = Path(output_root) / _day_folder(record["source_business_date"])
    delivery = _verify_country(day_root, row, record["source_business_date"])
    if not delivery["delivered"]:
        raise AdmissionError("delivery is not verified: " + str(delivery["reason"]))
    manifest = _read(Path(delivery["delivery_manifest"]))
    for key in ("language_pack", "pack_version", "pack_sha256"):
        if record.get(key) != manifest.get(key):
            raise AdmissionError(f"admission {key} does not match delivery manifest")
    pack = baseline_registry.verify(manifest["language_pack"], manifest["pack_version"])
    if pack["status"] != "stable_locked" or pack["actual_sha256"] != manifest["pack_sha256"]:
        raise AdmissionError("delivery language pack is not the current locked bytes")
    review_path = _inside(Path(project_root), record["review_receipt_path"])
    if not review_path.is_file() or _sha(review_path) != record["review_receipt_sha256"]:
        raise AdmissionError("independent review receipt is missing or changed")
    review = _read(review_path)
    if review.get("status") == "PASS" and isinstance(review.get("reviewer_execution_id"), str):
        reviewer_execution_id = review["reviewer_execution_id"]
    elif (review.get("status") == "PASS_INDEPENDENT_REVIEW"
          and isinstance(review.get("review_execution_id"), str)
          and review.get("independent_from_writer") is True
          and review.get("writer_execution_id") == record["writer_execution_id"]):
        # Canonical multi-gate reviewer receipts use the aggregate review
        # schema.  Admission accepts it only when every required gate is an
        # explicit PASS; this is validation of existing evidence, not a new
        # PASS derived from a fixture or schema conversion.
        gates = review.get("gates")
        required_gates = {"language", "semantic", "visual", "package_input"}
        if (not isinstance(gates, dict) or set(gates) != required_gates
                or any(not isinstance(gates[gate], dict) or gates[gate].get("status") != "PASS"
                       for gate in required_gates)):
            raise AdmissionError("aggregate review gates are not all PASS")
        reviewer_execution_id = review["review_execution_id"]
    else:
        raise AdmissionError("review receipt is not a passing independent review")
    if reviewer_execution_id == record["writer_execution_id"]:
        raise AdmissionError("writer review cannot support admission")
    return {"status": "PASS", "country_code": country,
            "delivery_manifest_sha256": delivery["manifest_sha256"],
            "language_pack": manifest["language_pack"], "pack_version": manifest["pack_version"],
            "pack_sha256": manifest["pack_sha256"], "admission_path": str(record_path)}
