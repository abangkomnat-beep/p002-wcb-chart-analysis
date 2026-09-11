"""Read country-first release manifests and report rollout coverage.

This tool is intentionally read-only for ``output``.  The Thai source
selector's 4/4 result is useful, but is not evidence that eight countries
were delivered; this report keeps those two measures separate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

from tools.active_rollout import requested_selection

SCHEMA = "p002-country-delivery-coverage/v1"


def _day_folder(business_date: str) -> str:
    try:
        return date.fromisoformat(business_date).strftime("%d-%m-%Y")
    except (TypeError, ValueError) as exc:
        raise ValueError("date must be YYYY-MM-DD") from exc


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read manifest: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"manifest must be an object: {path}")
    return value


def _verify_country(day_root: Path, row: dict, business_date: str) -> dict:
    folder = day_root / row["output_folder"]
    manifest_path = folder / "manifest.json"
    base = {"country_code": row["country_code"], "output_folder": row["output_folder"],
            "delivery_manifest": str(manifest_path), "delivered": False, "reason": None}
    if not manifest_path.is_file():
        return {**base, "reason": "DELIVERY_MANIFEST_MISSING"}
    try:
        manifest = _read(manifest_path)
    except ValueError as exc:
        return {**base, "reason": "DELIVERY_MANIFEST_INVALID", "detail": str(exc)}
    if manifest.get("schema") not in {"p002-localized-release/v2", "p002-thai-source-release/v1"}:
        return {**base, "reason": "DELIVERY_MANIFEST_SCHEMA_INVALID"}
    if manifest.get("country_code") != row["country_code"] or manifest.get("source_business_date") != business_date:
        return {**base, "reason": "DELIVERY_MANIFEST_IDENTITY_MISMATCH"}
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        return {**base, "reason": "DELIVERY_FILE_INVENTORY_MISSING"}
    for relative, digest in files.items():
        candidate = (folder / relative).resolve()
        try:
            candidate.relative_to(folder.resolve())
        except ValueError:
            return {**base, "reason": "DELIVERY_PATH_UNSAFE"}
        if not isinstance(digest, str) or len(digest) != 64 or not candidate.is_file() or _sha(candidate) != digest:
            return {**base, "reason": "DELIVERY_FILE_HASH_MISMATCH", "file": relative}
    return {**base, "delivered": True, "reason": None,
            "manifest_sha256": _sha(manifest_path), "expected_articles": manifest.get("expected_articles")}


def report(*, output_root: Path, work_root: Path, business_date: str, countries: list[str]) -> dict:
    requested = requested_selection(countries)
    day_root = Path(output_root) / _day_folder(business_date)
    rows = [_verify_country(day_root, row, business_date) for row in requested["countries"]]
    delivered = sum(row["delivered"] for row in rows)
    payload = {"schema": SCHEMA, "source_business_date": business_date, "requested": countries,
               "expected_count": len(rows), "delivered_count": delivered,
               "status": "PASS" if delivered == len(rows) else "HOLD", "countries": rows}
    target = Path(work_root) / "localization" / _day_folder(business_date) / "coverage" / "country-delivery-coverage.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.with_name(f".{target.name}.tmp")
    staged.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    staged.replace(target)
    return {**payload, "report_path": str(target)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="verify country-first delivery coverage")
    parser.add_argument("--date", required=True)
    parser.add_argument("--countries", nargs="+", required=True)
    parser.add_argument("--output-root", type=Path, default=Path("../output"))
    parser.add_argument("--work-root", type=Path, default=Path("../work"))
    args = parser.parse_args(argv)
    result = report(output_root=args.output_root, work_root=args.work_root,
                    business_date=args.date, countries=args.countries)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
