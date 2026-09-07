"""Read-only impact planning for localized delivery trees.

The day manifest is a delivery marker, while each country manifest carries the
source paths and hashes used to decide whether that country must be refreshed.
This module never translates, writes output, or treats a missing index as a
reason to ignore a changed source.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


class DependencyError(ValueError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DependencyError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DependencyError(f"{path} must contain an object")
    return value


def delivery_root(project_root: Path, source_business_date: str) -> Path:
    try:
        year, month, day = source_business_date.split("-")
        if len(year) != 4 or len(month) != 2 or len(day) != 2:
            raise ValueError
    except ValueError as exc:
        raise DependencyError("source_business_date must be YYYY-MM-DD") from exc
    return Path(project_root) / "output" / f"{day}-{month}-{year}"


def rebuild_index(project_root: Path, source_business_date: str) -> dict:
    """Rebuild a dependency index from committed country manifests only."""
    project_root = Path(project_root).resolve()
    root = delivery_root(project_root, source_business_date)
    marker_path = root / "manifest.json"
    # An initial country release has no committed dependency graph yet.  This
    # is distinct from a broken graph: callers must route it to the initial
    # packaging flow instead of pretending that there is nothing to update.
    if not marker_path.exists():
        return {"schema": "p002-localization-dependencies/v1",
                "source_business_date": source_business_date,
                "day_manifest_sha256": None,
                "records": [],
                "state": "NO_COMMITTED_COUNTRIES"}
    marker = _read(marker_path)
    if marker.get("source_business_date") != source_business_date:
        raise DependencyError("day manifest date mismatch")
    countries = marker.get("countries")
    if not isinstance(countries, dict) or not countries:
        raise DependencyError("day manifest has no committed countries")
    records = []
    for code, item in countries.items():
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise DependencyError("invalid country entry in day manifest")
        country_root = root / item["path"]
        try:
            country_root.resolve().relative_to(root.resolve())
        except ValueError as exc:
            raise DependencyError("country path escapes delivery root") from exc
        manifest_path = country_root / "manifest.json"
        manifest = _read(manifest_path)
        if manifest.get("country_code") != code:
            raise DependencyError("country manifest identity mismatch")
        for source in manifest.get("sources") or []:
            if not isinstance(source, dict) or not isinstance(source.get("source_path"), str):
                raise DependencyError("country manifest lacks source_path; migrate before impact planning")
            records.append({
                "country_code": code,
                "content_locale": manifest.get("content_locale"),
                "country_manifest_path": str(manifest_path.relative_to(project_root).as_posix()),
                "generation_id": manifest.get("generation_id"),
                "article_id": source.get("article_id"),
                "source_path": source["source_path"],
                "source_sha256": source.get("source_sha256"),
                "source_image_hashes": {image["source_path"]: image["source_sha256"]
                                        for image in source.get("images", [])
                                        if isinstance(image, dict) and image.get("source_path")},
                "pack_sha256": manifest.get("pack_sha256"),
                "country_policy_sha256": manifest.get("country_policy_sha256"),
            })
    return {"schema": "p002-localization-dependencies/v1", "source_business_date": source_business_date,
            "day_manifest_sha256": _sha(marker_path), "records": records, "state": "COMMITTED"}


def detect_changes(project_root: Path, index: dict, *, changed_sources: list[str] | None = None) -> list[dict]:
    """Return NEW/MODIFIED/UNCHANGED/MISSING per committed article.

    ``changed_sources`` narrows a user-requested update, but paths outside the
    index are not fabricated into work.  A missing canonical input stays HOLD.
    """
    project_root = Path(project_root).resolve()
    requested = set(changed_sources or [])
    results = []
    for record in index.get("records") or []:
        source_rel = record["source_path"]
        image_paths = set(record.get("source_image_hashes", {}))
        if requested and source_rel not in requested and not (requested & image_paths):
            continue
        path = project_root / source_rel
        if not path.is_file():
            status, actual = "MISSING", None
        else:
            actual = _sha(path)
            status = "UNCHANGED" if actual == record.get("source_sha256") else "MODIFIED"
        image_changes = []
        for image_rel, expected in record.get("source_image_hashes", {}).items():
            image = project_root / image_rel
            actual_image = _sha(image) if image.is_file() else None
            if actual_image != expected:
                image_changes.append({"source_path": image_rel, "status": "MISSING" if actual_image is None else "MODIFIED"})
        if any(change["status"] == "MISSING" for change in image_changes):
            status = "MISSING"
        elif status == "UNCHANGED" and image_changes:
            status = "MODIFIED"
        results.append({**record, "status": status, "actual_source_sha256": actual,
                        "image_changes": image_changes})
    return results


def plan_update(project_root: Path, source_business_date: str, *, changed_sources: list[str] | None = None) -> dict:
    index = rebuild_index(project_root, source_business_date)
    changes = detect_changes(project_root, index, changed_sources=changed_sources)
    if index.get("state") == "NO_COMMITTED_COUNTRIES":
        status = "NO_COMMITTED_COUNTRIES"
    else:
        status = "HOLD" if any(item["status"] == "MISSING" for item in changes) else "READY"
    return {"schema": "p002-localization-impact-plan/v1", "source_business_date": source_business_date,
            "dependency_index_sha256": hashlib.sha256(json.dumps(index, sort_keys=True).encode()).hexdigest(),
            "changes": changes, "dependency_state": index.get("state"), "status": status}
