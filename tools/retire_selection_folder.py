"""Retire a verified legacy selection-copy folder without deleting its evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path


SCHEMA = "p002-selection-folder-retirement/v1"
FOLDER = "0-ขึ้นเว็บวันนี้"


class RetirementError(RuntimeError):
    pass


def _day_name(business_date: str) -> str:
    try:
        return datetime.strptime(business_date, "%Y-%m-%d").strftime("%d-%m-%Y")
    except ValueError as exc:
        raise RetirementError("date must be YYYY-MM-DD") from exc


def _tree_hashes(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RetirementError(f"symlink is not allowed: {path}")
        if path.is_file():
            result[str(path.relative_to(root)).replace("\\", "/")] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _verify_copies(day: Path, legacy: Path, hashes: dict[str, str]) -> None:
    """Every copied article/image must match exactly one canonical country file."""
    candidates: dict[str, list[Path]] = {}
    for path in day.rglob("*"):
        if not path.is_file() or legacy in path.parents or path.name == ".delivery.lock":
            continue
        candidates.setdefault(path.name, []).append(path)
    for relative, digest in hashes.items():
        name = Path(relative).name
        if name == "selection-report.json":
            continue
        matches = [path for path in candidates.get(name, [])
                   if hashlib.sha256(path.read_bytes()).hexdigest() == digest]
        if len(matches) != 1:
            raise RetirementError(f"legacy copy does not match one country file: {relative}")


def prepare(*, output_root: Path, work_root: Path, business_date: str) -> dict:
    day = Path(output_root) / _day_name(business_date)
    legacy = day / FOLDER
    transaction = Path(work_root) / "localization" / _day_name(business_date) / "output-country-cutover"
    journal = transaction / "selection-retirement.json"
    target = transaction / "legacy-selection-copy"
    if journal.is_file():
        prior = json.loads(journal.read_text(encoding="utf-8"))
        if prior.get("schema") == SCHEMA and prior.get("state") == "COMMITTED":
            if target.is_dir() and _tree_hashes(target) == prior.get("files"):
                return {**prior, "journal": str(journal), "idempotent": True}
            raise RetirementError("committed selection retirement journal does not match target")
    if not legacy.is_dir():
        raise RetirementError(f"legacy selection folder is missing: {legacy}")
    if target.exists():
        raise RetirementError(f"retirement target already exists: {target}")
    files = _tree_hashes(legacy)
    if not files:
        raise RetirementError("legacy selection folder is empty")
    _verify_copies(day, legacy, files)
    record = {"schema": SCHEMA, "state": "PREPARED", "business_date": business_date,
              "source": str(legacy), "target": str(target), "files": files}
    transaction.mkdir(parents=True, exist_ok=True)
    journal.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**record, "journal": str(journal), "idempotent": False}


def apply(*, output_root: Path, work_root: Path, business_date: str) -> dict:
    record = prepare(output_root=output_root, work_root=work_root, business_date=business_date)
    if record["state"] == "COMMITTED":
        return record
    source, target = Path(record["source"]), Path(record["target"])
    try:
        os.replace(source, target)
        if _tree_hashes(target) != record["files"]:
            raise RetirementError("hash mismatch after selection retirement")
    except Exception:
        if target.exists() and not source.exists():
            os.replace(target, source)
        raise
    committed = {**record, "state": "COMMITTED"}
    try:
        Path(record["journal"]).write_text(json.dumps(committed, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
    except Exception:
        os.replace(target, source)
        raise
    return committed


def recover(*, output_root: Path, work_root: Path, business_date: str) -> dict:
    """Restore a committed move when the cutover must be rolled back.

    Recovery is deliberately narrow: it accepts only this tool's committed
    journal and the exact hash inventory it wrote.  It will never overwrite a
    newly-created selection folder or move an altered archive back to Output.
    """
    day = Path(output_root) / _day_name(business_date)
    transaction = Path(work_root) / "localization" / _day_name(business_date) / "output-country-cutover"
    journal = transaction / "selection-retirement.json"
    if not journal.is_file():
        raise RetirementError(f"retirement journal is missing: {journal}")
    record = json.loads(journal.read_text(encoding="utf-8"))
    if record.get("schema") != SCHEMA or record.get("state") != "COMMITTED":
        raise RetirementError("recovery requires a committed selection retirement journal")
    source, target = Path(record.get("source", "")), Path(record.get("target", ""))
    if source != day / FOLDER or not target.is_dir():
        raise RetirementError("retirement journal paths are not valid for this date")
    if source.exists():
        raise RetirementError(f"cannot recover over an existing selection folder: {source}")
    if _tree_hashes(target) != record.get("files"):
        raise RetirementError("archived selection files changed; recovery is blocked")
    os.replace(target, source)
    recovered = {**record, "state": "RECOVERED"}
    journal.write_text(json.dumps(recovered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return recovered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="retire verified 0-ขึ้นเว็บวันนี้ copy")
    parser.add_argument("--date", required=True)
    parser.add_argument("--output-root", type=Path, default=Path("../output"))
    parser.add_argument("--work-root", type=Path, default=Path("../work"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--recover", action="store_true")
    args = parser.parse_args(argv)
    if args.apply and args.recover:
        parser.error("--apply and --recover cannot be used together")
    action = recover if args.recover else (apply if args.apply else prepare)
    result = action(output_root=args.output_root, work_root=args.work_root,
                    business_date=args.date)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
