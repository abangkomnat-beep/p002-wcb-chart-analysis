"""Explicit coordination commands for localized delivery updates.

These commands intentionally do not invoke an LLM.  They produce the impact
plan that Lead uses to dispatch Writer/Reviewers, then apply only a transaction
whose prepared trees have already passed the country/package checks.
"""
from __future__ import annotations

import argparse
import json
import hashlib
from pathlib import Path

from tools import localization_dependencies, localization_transaction, package_localized_country


def _work_root(project_root: Path, source_business_date: str) -> Path:
    year, month, day = source_business_date.split("-")
    return Path(project_root) / "work" / "localization" / f"{day}-{month}-{year}"


def write_impact_plan(project_root: Path, source_business_date: str,
                      changed_sources: list[str] | None = None) -> tuple[dict, Path]:
    plan = localization_dependencies.plan_update(project_root, source_business_date,
                                                 changed_sources=changed_sources)
    index = _work_root(project_root, source_business_date) / "index"
    data = (json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    target = index / "impact-plans" / (hashlib.sha256(data).hexdigest()[:16] + ".json")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(data)
    (index / "latest.json").write_bytes(data)
    return plan, target


def prepare_countries_for_delivery(project_root: Path, source_business_date: str,
                                   transaction_id: str, jobs: list[dict]) -> dict:
    """Prepare checked countries and bind one merged marker; never apply it."""
    project = Path(project_root).resolve()
    if not jobs:
        raise ValueError("at least one country job is required")
    root = localization_dependencies.delivery_root(project, source_business_date)
    marker_path = root / "manifest.json"
    if marker_path.exists():
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        localization_transaction.validate_delivery_marker(marker, source_business_date, complete=True)
        countries = dict(marker["countries"])
    else:
        countries = {}
    requested, intents = {}, []
    for job in jobs:
        for key in ("manifest", "receipt_index", "release_id"):
            if not isinstance(job.get(key), str) or not job[key]:
                raise ValueError(f"country job requires {key}")
        manifest = json.loads(Path(job["manifest"]).read_text(encoding="utf-8"))
        country = package_localized_country.require_manifest_country(manifest)
        code, folder = country["country_code"], country["output_folder"]
        if code in requested:
            raise ValueError("country appears twice in transaction")
        requested[code] = folder
        countries[code] = {"path": folder}
        intents.append((code, folder, job))
    marker = {"schema": "p002-localized-day/v2", "source_business_date": source_business_date,
              "countries": countries}
    tx = localization_transaction.prepare_transaction(project, source_business_date, transaction_id,
                                                      requested, marker)
    for code, folder, job in intents:
        package_localized_country.prepare_country(job["manifest"], job["receipt_index"], project,
                                                  tx, job["release_id"])
        release_manifest = tx / "prepared" / folder / "manifest.json"
        digest = hashlib.sha256(release_manifest.read_bytes()).hexdigest()
        countries[code] = {"path": folder, "release_id": job["release_id"], "manifest_sha256": digest}
    final = {"schema": "p002-localized-day/v2", "source_business_date": source_business_date,
             "countries": countries}
    localization_transaction.attest_transaction_marker(project, source_business_date, transaction_id, final)
    return {"status": "PREPARED", "transaction_id": transaction_id, "marker": final,
            "transaction_root": str(tx)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--date", required=True, help="source date YYYY-MM-DD")
    parser.add_argument("--changed-source", action="append", default=[])
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--plan-update", action="store_true")
    modes.add_argument("--prepare-update", action="store_true")
    modes.add_argument("--apply-update", action="store_true")
    modes.add_argument("--recover", action="store_true")
    parser.add_argument("--transaction-id")
    args = parser.parse_args(argv)
    project = Path(args.project_root).resolve()
    try:
        if args.plan_update:
            payload = localization_dependencies.plan_update(project, args.date,
                                                            changed_sources=args.changed_source)
        elif args.prepare_update:
            # This remains a planning operation.  The transaction is prepared
            # only after writers and independent reviewers have produced a
            # complete, checked country tree.
            payload, path = write_impact_plan(project, args.date, args.changed_source)
            next_step = ("use initial country packaging; no committed country can be overwritten"
                         if payload["status"] == "NO_COMMITTED_COUNTRIES"
                         else "dispatch queued country/article work; this command does not translate")
            payload = {**payload, "impact_plan_path": str(path), "next": next_step}
        elif args.apply_update:
            if not args.transaction_id:
                raise ValueError("--transaction-id is required for --apply-update")
            payload = localization_transaction.apply_transaction(project, args.date, args.transaction_id)
        else:
            if not args.transaction_id:
                raise ValueError("--transaction-id is required for --recover")
            payload = localization_transaction.recover_transaction(project, args.date, args.transaction_id)
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except (ValueError, localization_dependencies.DependencyError,
            localization_transaction.TransactionError) as exc:
        print(json.dumps({"status": "HOLD", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
