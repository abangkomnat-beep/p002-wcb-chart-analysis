"""Move a Thai daily source set into the country-first delivery layout.

This tool is deliberately separate from localized-country release packaging:
Thailand's files are the frozen source for translation, so this migration
never claims language QA or creates a release marker.  It creates a durable
journal and byte-checked backup before replacing the four legacy top-level
style folders.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

from tools.localization_config import delivery_article_path
from tools.delivery_file_naming import image_name
from tools.daily_source_selector import legacy_lanes_for_date

# Backwards-compatible name for callers that explicitly mean the Monday set.
LAYOUT = legacy_lanes_for_date("2026-09-07")


class MigrationError(RuntimeError):
    pass


_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_PLACEHOLDER_FILES = {"STATUS.md", "README.md"}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _write_journal(path: Path, journal: dict) -> None:
    """Write the recovery record before advancing a filesystem operation."""
    path.write_bytes(_json(journal))


def _day_folder(day: str) -> str:
    try:
        year, month, date = day.split("-")
        if len(year) != 4 or len(month) != 2 or len(date) != 2:
            raise ValueError
    except ValueError as exc:
        raise MigrationError("date must be YYYY-MM-DD") from exc
    return f"{date}-{month}-{year}"


def layout_for_date(source_business_date: str):
    """Return the approved D/E/M/L source set for a Bangkok business date."""
    layout = legacy_lanes_for_date(source_business_date)
    if not layout:
        raise MigrationError("weekend has no Thai source delivery layout")
    return layout


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise MigrationError(f"cannot read {path}") from exc


def _replace_links(markdown: str, names: dict[str, str]) -> str:
    def rewrite(match: re.Match) -> str:
        target = match.group(1)
        if target not in names:
            raise MigrationError(f"article references an untracked image: {target}")
        return match.group(0).replace(target, names[target])
    return _IMAGE.sub(rewrite, markdown)


def build_inventory(project_root: Path, source_business_date: str) -> dict:
    """Read the approved daily source set and every referenced image without writes."""
    root = Path(project_root).resolve()
    day = root / "output" / _day_folder(source_business_date)
    if not day.is_dir():
        raise MigrationError(f"missing output day: {day}")
    layout = layout_for_date(source_business_date)
    entries, assigned = [], set()
    for style, asset, legacy_folder, article_template in layout:
        article_name = article_template.format(date=source_business_date)
        article = day / legacy_folder / article_name
        raw = _read(article)
        try:
            markdown = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MigrationError(f"article is not UTF-8: {article.name}") from exc
        images = []
        names = {match.group(1) for match in _IMAGE.finditer(markdown)}
        if not names:
            raise MigrationError(f"article has no image references: {article.name}")
        for name in sorted(names):
            if Path(name).name != name or not name.lower().endswith(".webp"):
                raise MigrationError(f"unsafe image reference in {article.name}: {name}")
            path = article.parent / name
            data = _read(path)
            images.append({"old_path": path.relative_to(root).as_posix(), "name": name,
                           "sha256": _sha(data), "bytes": len(data)})
            assigned.add(path.relative_to(day).as_posix())
        assigned.add(article.relative_to(day).as_posix())
        entries.append({"article_id": f"{style}-{asset}", "style": style, "asset": asset,
                        "old_path": article.relative_to(root).as_posix(),
                        "new_path": f"output/{_day_folder(source_business_date)}/TH-Thailand/" +
                                    delivery_article_path(source_business_date, "TH", style, asset),
                        # source_sha256 remains the immutable pre-rewrite bytes;
                        # the explicit names prevent consumers confusing it
                        # with the localized candidate or post-link bytes.
                        "source_original_sha256": _sha(raw),
                        # Set during prepare after image links have their final names.
                        "source_canonical_sha256": None,
                        "source_sha256": _sha(raw), "source_bytes": len(raw), "images": images})
    all_legacy = set()
    for _, _, legacy_folder, _ in layout:
        for path in (day / legacy_folder).rglob("*"):
            if path.is_file():
                all_legacy.add(path.relative_to(day).as_posix())
    extra = sorted(all_legacy - assigned)
    if extra:
        raise MigrationError("unmapped legacy files: " + ", ".join(extra))
    return {"schema": "p002-thai-layout-migration/v1", "source_business_date": source_business_date,
            "day_folder": _day_folder(source_business_date), "articles": entries,
            "legacy_folders": sorted({item[2] for item in layout})}


def prepare(project_root: Path, source_business_date: str, migration_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9-]+", migration_id or ""):
        raise MigrationError("migration id must be lowercase letters, digits and hyphens")
    root = Path(project_root).resolve()
    inventory = build_inventory(root, source_business_date)
    tx = root / "work" / "localization" / inventory["day_folder"] / "migrations" / migration_id
    if tx.exists():
        raise MigrationError("migration id already exists")
    prepared = tx / "prepared" / "TH-Thailand"
    prepared.mkdir(parents=True)
    for entry in inventory["articles"]:
        source = root / entry["old_path"]
        original = _read(source).decode("utf-8")
        names = {image["name"]: image_name(source_business_date, "TH", entry["style"], entry["asset"], ordinal, image["name"])
                 for ordinal, image in enumerate(entry["images"], start=1)}
        target = prepared / delivery_article_path(source_business_date, "TH", entry["style"], entry["asset"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_replace_links(original, names), encoding="utf-8", newline="\n")
        entry["source_canonical_sha256"] = _sha(_read(target))
        for ordinal, image in enumerate(entry["images"], start=1):
            data = _read(root / image["old_path"])
            if _sha(data) != image["sha256"]:
                raise MigrationError(f"image changed while preparing: {image['old_path']}")
            (target.parent / names[image["name"]]).write_bytes(data)
    prepared_files = {path.relative_to(prepared).as_posix(): _sha(_read(path))
                      for path in prepared.rglob("*") if path.is_file()}
    journal = {**inventory, "migration_id": migration_id, "state": "PREPARED",
               "prepared_files": prepared_files}
    _write_journal(tx / "journal.json", journal)
    return tx


def _load_journal(root: Path, source_business_date: str, migration_id: str) -> tuple[Path, Path, dict]:
    root = Path(root).resolve()
    tx = root / "work" / "localization" / _day_folder(source_business_date) / "migrations" / migration_id
    journal_path = tx / "journal.json"
    try:
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationError("missing or invalid migration journal") from exc
    if journal.get("source_business_date") != source_business_date:
        raise MigrationError("migration is not prepared for this date")
    return tx, journal_path, journal


def _result(journal: dict, tx: Path, target: Path, status: str) -> dict:
    return {"status": status, "target": str(target), "backup": str(tx / "backup"),
            "articles": len(journal["articles"]),
            "images": sum(len(article["images"]) for article in journal["articles"])}


def _source_identity(entries: list[dict]) -> list[dict]:
    """Compare immutable legacy bytes without confusing them with rewritten links."""
    return [{key: value for key, value in entry.items() if key != "source_canonical_sha256"}
            for entry in entries]


def _rollback(day: Path, tx: Path, journal_path: Path, journal: dict) -> None:
    """Restore the pre-apply tree from durable operation intent in the journal."""
    target = day / "TH-Thailand"
    displaced = tx / "displaced" / "TH-Thailand"
    if displaced.exists():
        if target.exists():
            actual = {path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file()}
            owned = set(journal.get("installed_files", [])) | {"source-layout-manifest.json"} | _PLACEHOLDER_FILES
            foreign = actual - owned
            if foreign:
                raise MigrationError("cannot recover: Thailand target has foreign files: " + ", ".join(sorted(foreign)))
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(displaced, target)
    else:
        # No previous target existed.  Only remove files the migration owns;
        # do not erase a foreign file created concurrently.
        for relative in reversed(journal.get("installed_files", [])):
            candidate = target / relative
            if candidate.exists():
                candidate.unlink()
        manifest = target / "source-layout-manifest.json"
        if manifest.exists():
            manifest.unlink()
        for directory in sorted((path for path in target.rglob("*") if path.is_dir()), key=lambda path: len(path.parts), reverse=True):
            if directory != target and not any(directory.iterdir()):
                directory.rmdir()
    for operation in reversed(journal.get("legacy_moves", [])):
        source = day / operation["legacy"]
        backup = tx / "backup" / operation["legacy"]
        if backup.exists() and not source.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            os.replace(backup, source)
    journal["state"] = "ROLLED_BACK"
    _write_journal(journal_path, journal)


def recover(project_root: Path, source_business_date: str, migration_id: str) -> dict:
    """Recover an interrupted migration without inspecting or changing other countries."""
    root = Path(project_root).resolve()
    tx, journal_path, journal = _load_journal(root, source_business_date, migration_id)
    day = root / "output" / journal["day_folder"]
    target = day / "TH-Thailand"
    state = journal.get("state")
    if state == "APPLYING":
        _rollback(day, tx, journal_path, journal)
        return _result(journal, tx, target, "ROLLED_BACK")
    if state in {"PREPARED", "ROLLED_BACK", "COMMITTED"}:
        return _result(journal, tx, target, state)
    raise MigrationError("migration journal has an unknown state")


def apply(project_root: Path, source_business_date: str, migration_id: str) -> dict:
    root = Path(project_root).resolve()
    tx, journal_path, journal = _load_journal(root, source_business_date, migration_id)
    if journal.get("state") == "COMMITTED":
        return _result(journal, tx, root / "output" / journal["day_folder"] / "TH-Thailand", "COMMITTED")
    if journal.get("state") != "PREPARED":
        raise MigrationError("migration is not prepared; recover it before applying again")
    if _source_identity(build_inventory(root, source_business_date)["articles"]) != _source_identity(journal["articles"]):
        raise MigrationError("source files changed after prepare; create a new migration")
    prepared = tx / "prepared" / "TH-Thailand"
    actual_prepared = {path.relative_to(prepared).as_posix(): _sha(_read(path))
                       for path in prepared.rglob("*") if path.is_file()}
    if actual_prepared != journal.get("prepared_files"):
        raise MigrationError("prepared tree changed")
    for entry in journal["articles"]:
        relative = delivery_article_path(source_business_date, "TH", entry["style"], entry["asset"])
        if _sha(_read(prepared / relative)) != entry.get("source_canonical_sha256"):
            raise MigrationError(f"prepared canonical source hash mismatch: {entry['article_id']}")
    day = root / "output" / journal["day_folder"]
    target = day / "TH-Thailand"
    existing = {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()} if target.exists() else set()
    journal["legacy_moves"] = [{"legacy": legacy, "state": "PLANNED"}
                               for legacy in journal["legacy_folders"]]
    journal["installed_files"] = []
    journal["target_displacement"] = "PLANNED" if existing - _PLACEHOLDER_FILES else "NONE"
    try:
        journal["state"] = "APPLYING"; _write_journal(journal_path, journal)
        if journal["target_displacement"] == "PLANNED":
            displaced = tx / "displaced" / "TH-Thailand"
            if displaced.exists():
                raise MigrationError("displaced Thailand backup already exists")
            displaced.parent.mkdir(parents=True, exist_ok=True)
            os.replace(target, displaced)
            journal["target_displacement"] = "DONE"; _write_journal(journal_path, journal)
        for operation in journal["legacy_moves"]:
            legacy = operation["legacy"]
            source, backup = day / legacy, tx / "backup" / legacy
            if backup.exists():
                raise MigrationError(f"backup already exists: {legacy}")
            backup.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, backup)
            operation["state"] = "DONE"; _write_journal(journal_path, journal)
        for source in prepared.rglob("*"):
            if not source.is_file():
                continue
            destination = target / source.relative_to(prepared)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise MigrationError(f"destination already exists: {destination.relative_to(target)}")
            shutil.copy2(source, destination)
            journal["installed_files"].append(destination.relative_to(target).as_posix())
            _write_journal(journal_path, journal)
        manifest = {"schema": "p002-thai-source-layout/v1", "source_business_date": source_business_date,
                    "migration_id": migration_id, "articles": journal["articles"],
                    "files": {path.relative_to(target).as_posix(): _sha(_read(path))
                              for path in target.rglob("*") if path.is_file() and path.name != "STATUS.md"}}
        (target / "source-layout-manifest.json").write_bytes(_json(manifest))
        journal["state"] = "COMMITTED"; journal["target_manifest_sha256"] = _sha(_json(manifest))
        _write_journal(journal_path, journal)
        return _result(journal, tx, target, "COMMITTED")
    except Exception:
        _rollback(day, tx, journal_path, journal)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--date", required=True)
    parser.add_argument("--migration-id", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inventory", action="store_true")
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--recover", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = (build_inventory(args.project_root, args.date) if args.inventory else
                  {"prepared": str(prepare(args.project_root, args.date, args.migration_id))} if args.prepare else
                  apply(args.project_root, args.date, args.migration_id) if args.apply else
                  recover(args.project_root, args.date, args.migration_id))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except MigrationError as exc:
        print(json.dumps({"status": "HOLD", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
