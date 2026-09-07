"""Explicit coordination commands for localized delivery updates.

These commands intentionally do not invoke an LLM.  They produce the impact
plan that Lead uses to dispatch Writer/Reviewers, then apply only a transaction
whose prepared trees have already passed the country/package checks.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools import localization_dependencies, localization_transaction


def _work_root(project_root: Path, source_business_date: str) -> Path:
    year, month, day = source_business_date.split("-")
    return Path(project_root) / "work" / "localization" / f"{day}-{month}-{year}"


def write_impact_plan(project_root: Path, source_business_date: str,
                      changed_sources: list[str] | None = None) -> tuple[dict, Path]:
    plan = localization_dependencies.plan_update(project_root, source_business_date,
                                                 changed_sources=changed_sources)
    target = _work_root(project_root, source_business_date) / "index" / "impact-plan.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if target.exists() and target.read_bytes() != data:
        raise ValueError("existing impact plan differs; use a new work revision after source changes")
    if not target.exists():
        target.write_bytes(data)
    return plan, target


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
            payload = {**payload, "impact_plan_path": str(path), "next": "dispatch queued country/article work; this command does not translate"}
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
