"""Durable CC-controlled workflow state for one localized source day.

The scaffold deliberately records gates and hashes only. Translation, review,
and release remain separate real executions; no state transition creates a
public Output tree or promotes a language pack.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from tools.daily_source_selector import source_keys_for_date

STATES = ("SOURCE_PENDING", "SOURCE_READY", "PACK_PENDING", "CANDIDATES_READY", "REVIEW_PENDING", "READY_TO_PACKAGE", "DELIVERED")
COUNTRY_TRANSITIONS = {
    "PACK_PENDING": {"CANDIDATES_READY"},
    "CANDIDATES_READY": {"REVIEW_PENDING"},
    "REVIEW_PENDING": {"READY_TO_PACKAGE"},
    "READY_TO_PACKAGE": {"DELIVERED"},
    "DELIVERED": set(),
}


class WorkflowError(ValueError):
    pass


def _sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _resolve_source_bindings_path(project_root: Path, source_business_date: str,
                                  *, source_bindings_path: str | Path | None = None,
                                  source_bindings_revision_dir: str | Path | None = None,
                                  revision_dir: str | Path | None = None) -> tuple[Path, bool]:
    """Resolve a frozen source manifest while keeping the legacy default."""
    candidates = [item for item in (
        source_bindings_path, source_bindings_revision_dir, revision_dir) if item is not None]
    if len(candidates) > 1:
        raise WorkflowError("provide only one explicit source bindings path or revision directory")
    explicit = bool(candidates)
    if candidates:
        candidate = Path(candidates[0]).expanduser()
        path = candidate / "source-bindings.json" if candidate.is_dir() else candidate
    else:
        path = (Path(project_root).resolve() / "work" / "localization"
                / _day_folder(source_business_date) / "source-bindings"
                / "source-bindings.json")
    return path.resolve(), explicit


def _binding_identity(project_root: Path, source_business_date: str, *,
                      source_bindings_path: str | Path | None = None,
                      source_bindings_revision_dir: str | Path | None = None,
                      revision_dir: str | Path | None = None,
                      source_bindings_sha256: str | None = None) -> tuple[Path, str | None, bool]:
    path, explicit = _resolve_source_bindings_path(
        project_root, source_business_date,
        source_bindings_path=source_bindings_path,
        source_bindings_revision_dir=source_bindings_revision_dir,
        revision_dir=revision_dir)
    digest = _sha(path)
    if explicit and digest is None:
        raise WorkflowError("explicit source bindings manifest is missing")
    if source_bindings_sha256 is not None:
        if (len(source_bindings_sha256) != 64
                or any(char not in "0123456789abcdef" for char in source_bindings_sha256)):
            raise WorkflowError("source_bindings_sha256 must be a SHA-256 hex digest")
        if digest != source_bindings_sha256:
            raise WorkflowError("source bindings manifest hash mismatch")
    return path, digest, explicit or source_bindings_sha256 is not None


def _verify_bound_source(data: dict, *, project_root: Path,
                         source_business_date: str,
                         source_bindings_path: str | Path | None = None,
                         source_bindings_revision_dir: str | Path | None = None,
                         revision_dir: str | Path | None = None,
                         source_bindings_sha256: str | None = None) -> None:
    stored_path = data.get("source_bindings_path")
    stored_hash = data.get("source_bindings_sha256")
    explicit = any(item is not None for item in (
        source_bindings_path, source_bindings_revision_dir, revision_dir,
        source_bindings_sha256))
    if explicit:
        path, digest, _ = _binding_identity(
            project_root, source_business_date,
            source_bindings_path=source_bindings_path,
            source_bindings_revision_dir=source_bindings_revision_dir,
            revision_dir=revision_dir,
            source_bindings_sha256=source_bindings_sha256)
        if not isinstance(stored_path, str) or not isinstance(stored_hash, str):
            raise WorkflowError("workflow has no explicit source bindings identity")
        if Path(stored_path).resolve() != path or stored_hash != digest:
            raise WorkflowError("workflow source bindings identity drifted")
        return
    if isinstance(stored_path, str) and isinstance(stored_hash, str):
        if _sha(Path(stored_path)) != stored_hash:
            raise WorkflowError("workflow source bindings manifest is stale or mismatched")


def _verify_evidence(path: str | Path | None, digest: str | None, label: str) -> None:
    if not isinstance(path, (str, Path)) or not isinstance(digest, str):
        raise WorkflowError(f"{label} requires an evidence path and SHA-256")
    candidate = Path(path)
    if not candidate.is_file() or _sha(candidate) != digest:
        raise WorkflowError(f"{label} evidence is missing, stale or mismatched")


def _day_folder(day: str) -> str:
    try:
        return date.fromisoformat(day).strftime("%d-%m-%Y")
    except (TypeError, ValueError) as exc:
        raise WorkflowError("source date must be YYYY-MM-DD") from exc


def state_path(project_root: Path, source_business_date: str, workflow_id: str) -> Path:
    if not workflow_id or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in workflow_id):
        raise WorkflowError("workflow id must use lowercase letters, digits, and hyphens")
    return Path(project_root).resolve() / "work" / "localization" / _day_folder(source_business_date) / "workflows" / workflow_id / "state.json"


def start(project_root: Path, source_business_date: str, workflow_id: str, countries: list[str], *,
          source_bindings_path: str | Path | None = None,
          source_bindings_revision_dir: str | Path | None = None,
          revision_dir: str | Path | None = None,
          source_bindings_sha256: str | None = None) -> Path:
    expected = source_keys_for_date(source_business_date)
    if not expected:
        raise WorkflowError("weekend has no localization workflow")
    if not countries or len(countries) != len(set(countries)) or any(not code.isalpha() or len(code) != 2 for code in countries):
        raise WorkflowError("countries must be unique two-letter country codes")
    path = state_path(project_root, source_business_date, workflow_id)
    if path.exists():
        data = load(project_root, source_business_date, workflow_id)
        _verify_bound_source(
            data, project_root=project_root, source_business_date=source_business_date,
            source_bindings_path=source_bindings_path,
            source_bindings_revision_dir=source_bindings_revision_dir,
            revision_dir=revision_dir, source_bindings_sha256=source_bindings_sha256)
        return path
    bindings, bindings_hash, _ = _binding_identity(
        project_root, source_business_date,
        source_bindings_path=source_bindings_path,
        source_bindings_revision_dir=source_bindings_revision_dir,
        revision_dir=revision_dir, source_bindings_sha256=source_bindings_sha256)
    data = {"schema": "p002-localization-workflow/v1", "workflow_id": workflow_id,
            "source_business_date": source_business_date, "state": "SOURCE_PENDING",
            "expected_articles": [f"{style}-{asset}" for style, asset in expected],
            "source_bindings_path": str(bindings), "source_bindings_sha256": bindings_hash,
            "countries": {code.upper(): {"state": "PACK_PENDING", "pack_sha256": None,
                                           "source_receipt_sha256": None, "candidate_manifest_sha256": None,
                                           "review_receipt_sha256": None, "delivery_manifest_sha256": None}
                          for code in countries}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


def load(project_root: Path, source_business_date: str, workflow_id: str) -> dict:
    path = state_path(project_root, source_business_date, workflow_id)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError("workflow state is missing or invalid") from exc


def resume(project_root: Path, source_business_date: str, workflow_id: str, *,
           source_bindings_path: str | Path | None = None,
           source_bindings_revision_dir: str | Path | None = None,
           revision_dir: str | Path | None = None,
           source_bindings_sha256: str | None = None) -> dict:
    """Load a workflow only after its frozen source manifest still matches."""
    data = load(project_root, source_business_date, workflow_id)
    _verify_bound_source(
        data, project_root=project_root, source_business_date=source_business_date,
        source_bindings_path=source_bindings_path,
        source_bindings_revision_dir=source_bindings_revision_dir,
        revision_dir=revision_dir, source_bindings_sha256=source_bindings_sha256)
    return data


def record_country_gate(project_root: Path, source_business_date: str, workflow_id: str,
                        country: str, state: str, *, pack_sha256: str | None = None,
                        source_receipt_sha256: str | None = None,
                        candidate_manifest_sha256: str | None = None,
                        review_receipt_sha256: str | None = None,
                        delivery_manifest_sha256: str | None = None,
                        source_bindings_path: str | Path | None = None,
                        source_bindings_revision_dir: str | Path | None = None,
                        revision_dir: str | Path | None = None,
                        source_bindings_sha256: str | None = None,
                        source_receipt_path: str | Path | None = None,
                        candidate_manifest_path: str | Path | None = None,
                        review_receipt_path: str | Path | None = None,
                        delivery_manifest_path: str | Path | None = None) -> dict:
    if state not in STATES:
        raise WorkflowError("unknown workflow state")
    data = load(project_root, source_business_date, workflow_id)
    _verify_bound_source(
        data, project_root=project_root, source_business_date=source_business_date,
        source_bindings_path=source_bindings_path,
        source_bindings_revision_dir=source_bindings_revision_dir,
        revision_dir=revision_dir, source_bindings_sha256=source_bindings_sha256)
    entry = (data.get("countries") or {}).get(country.upper())
    if not isinstance(entry, dict):
        raise WorkflowError("country is not in this workflow")
    current = entry.get("state")
    if state == current:
        return data
    allowed = COUNTRY_TRANSITIONS.get(current, set())
    if state not in allowed:
        raise WorkflowError(f"invalid country workflow transition: {current} -> {state}")
    for key, value in (("pack_sha256", pack_sha256), ("source_receipt_sha256", source_receipt_sha256),
                       ("candidate_manifest_sha256", candidate_manifest_sha256),
                       ("review_receipt_sha256", review_receipt_sha256),
                       ("delivery_manifest_sha256", delivery_manifest_sha256)):
        if value is not None:
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise WorkflowError(f"{key} must be a SHA-256 hex digest")
            entry[key] = value
    if state == "CANDIDATES_READY":
        if not (entry.get("pack_sha256") and entry.get("source_receipt_sha256") and entry.get("candidate_manifest_sha256")):
            raise WorkflowError("CANDIDATES_READY requires pack, source receipt and candidate manifest hashes")
        _verify_evidence(source_receipt_path, entry["source_receipt_sha256"], "source receipt")
        _verify_evidence(candidate_manifest_path, entry["candidate_manifest_sha256"], "candidate manifest")
    if state == "READY_TO_PACKAGE":
        if not entry.get("review_receipt_sha256"):
            raise WorkflowError("READY_TO_PACKAGE requires an independent review receipt hash")
        _verify_evidence(review_receipt_path, entry["review_receipt_sha256"], "review receipt")
    if state == "DELIVERED":
        if not entry.get("delivery_manifest_sha256"):
            raise WorkflowError("DELIVERED requires a delivery manifest hash")
        _verify_evidence(delivery_manifest_path, entry["delivery_manifest_sha256"], "delivery manifest")
    entry["state"] = state
    path = state_path(project_root, source_business_date, workflow_id)
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return data
