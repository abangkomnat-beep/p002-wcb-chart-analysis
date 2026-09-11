"""Move historical Thai legacy folders out of a daily final Output tree safely.

The daily runner now prevents new unscheduled output.  This tool repairs a
day that was produced before that guard existed.  It moves only known legacy
style folders under ``TH-Thailand`` into ``work/build`` and records hashes so
the move can be audited or reversed; it never deletes a source folder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path


LEGACY_STYLE_FOLDERS = (
    "D-โครงสร้างกราฟ", "F-กรอบราคา", "G-รอเหตุการณ์",
    "H-แรงเทรนด์-M30", "I-เบรกเอาต์-M15", "J-ย่อแล้วไปต่อ",
)


class QuarantineError(RuntimeError):
    pass


def _day_folder(business_date: str) -> str:
    try:
        return datetime.strptime(business_date, "%Y-%m-%d").strftime("%d-%m-%Y")
    except ValueError as exc:
        raise QuarantineError("date must be YYYY-MM-DD") from exc


def _hashes(folder: Path) -> dict[str, str]:
    return {
        str(path.relative_to(folder)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.rglob("*")) if path.is_file()
    }


def prepare(*, output_root: Path, work_root: Path, business_date: str) -> dict:
    day = _day_folder(business_date)
    source_root = Path(output_root) / day / "TH-Thailand"
    destination_root = Path(work_root) / "build" / day / "TH-Thailand"
    journal = Path(work_root) / "localization" / day / "unscheduled-output-quarantine.json"
    if journal.is_file():
        try:
            prior = json.loads(journal.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise QuarantineError(f"invalid quarantine journal: {journal}") from exc
        if (prior.get("schema") == "p002-unscheduled-output-quarantine/v1"
                and prior.get("business_date") == business_date
                and prior.get("state") == "COMMITTED"):
            return {**prior, "journal": str(journal)}
    records = []
    for name in LEGACY_STYLE_FOLDERS:
        source = source_root / name
        target = destination_root / name
        if not source.exists():
            continue
        if not source.is_dir():
            raise QuarantineError(f"legacy source is not a directory: {source}")
        if target.exists():
            raise QuarantineError(f"quarantine target already exists: {target}")
        hashes = _hashes(source)
        if not hashes:
            raise QuarantineError(f"legacy source is empty: {source}")
        records.append({"folder": name, "source": str(source), "target": str(target),
                        "files": hashes})
    document = {"schema": "p002-unscheduled-output-quarantine/v1",
                "business_date": business_date, "state": "PREPARED", "records": records}
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**document, "journal": str(journal)}


def apply(*, output_root: Path, work_root: Path, business_date: str) -> dict:
    prepared = prepare(output_root=output_root, work_root=work_root, business_date=business_date)
    if prepared.get("state") == "COMMITTED":
        return prepared
    journal = Path(prepared["journal"])
    moved = []
    try:
        for record in prepared["records"]:
            source, target = Path(record["source"]), Path(record["target"])
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, target)
            # Record the completed rename before verifying its bytes.  A hash
            # failure must still be rolled back; appending afterwards leaves
            # this moved folder outside the rollback list.
            moved.append(record)
            if _hashes(target) != record["files"]:
                raise QuarantineError(f"hash mismatch after moving {record['folder']}")
    except Exception:
        for record in reversed(moved):
            source, target = Path(record["source"]), Path(record["target"])
            if target.exists() and not source.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, source)
        raise
    document = {**prepared, "state": "COMMITTED"}
    try:
        journal.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception:
        for record in reversed(moved):
            source, target = Path(record["source"]), Path(record["target"])
            if target.exists() and not source.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, source)
        raise
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="quarantine unscheduled Thai output folders")
    parser.add_argument("--date", required=True)
    parser.add_argument("--output-root", type=Path, default=Path("../output"))
    parser.add_argument("--work-root", type=Path, default=Path("../work"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    result = (apply if args.apply else prepare)(output_root=args.output_root,
                                                 work_root=args.work_root,
                                                 business_date=args.date)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
