"""Recoverably flatten final P002 country delivery folders.

This migration moves only final Output.  Candidate files and their immutable
review receipts stay in work.  The journal records every old/new final path,
and the prior country trees are retained in backup before the public marker is
written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

from tools.delivery_file_naming import article_name, image_name


class FlatMigrationError(RuntimeError):
    pass


_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_COUNTRY = re.compile(r"[A-Z]{2}")
_FOLDER = re.compile(r"[A-Z]{2}-[A-Za-z0-9-]+")
_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _day(day: str) -> str:
    if not isinstance(day, str) or not _DAY.fullmatch(day):
        raise FlatMigrationError("date must be YYYY-MM-DD")
    return f"{day[8:10]}-{day[5:7]}-{day[:4]}"


def _files(root: Path) -> dict[str, bytes]:
    if not root.is_dir():
        raise FlatMigrationError(f"missing folder: {root}")
    result = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise FlatMigrationError(f"links are forbidden: {path}")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = path.read_bytes()
    return result


def _article_parts(path: Path, country: str) -> tuple[str, str]:
    try:
        style, asset = path.relative_to(path.parents[2]).parts[:2]
    except ValueError as exc:
        raise FlatMigrationError(f"invalid article path: {path}") from exc
    if not re.fullmatch(r"[A-Z]", style) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", asset):
        raise FlatMigrationError(f"invalid style/asset path: {path}")
    return style, asset


def _prepare_country(source: Path, prepared: Path, day: str, country: str) -> dict:
    articles = sorted(source.glob("*/*/article.md"))
    if not articles:
        raise FlatMigrationError(f"{source.name} has no legacy article.md files")
    mappings, article_records = [], []
    readme = source / "README.md"
    if readme.is_file():
        prepared.mkdir(parents=True, exist_ok=True)
        shutil.copy2(readme, prepared / "README.md")
    for article in articles:
        style, asset = article.relative_to(source).parts[:2]
        body = article.read_text(encoding="utf-8")
        image_dir = article.parent / "images"
        images = sorted(image_dir.glob("*.webp"))
        refs = [match.group(1) for match in _IMAGE.finditer(body)]
        expected = {f"images/{image.name}" for image in images}
        if set(refs) != expected or len(refs) != len(set(refs)):
            raise FlatMigrationError(f"image links do not match inventory: {article}")
        names = {f"images/{image.name}": image_name(day, country, style, asset, ordinal, image.name)
                 for ordinal, image in enumerate(images, start=1)}
        for old, new in names.items():
            body = body.replace(old, new)
        new_article = article_name(day, country, style, asset)
        target_dir = prepared / style / asset
        target_dir.mkdir(parents=True, exist_ok=True)
        target_article = target_dir / new_article
        target_article.write_text(body, encoding="utf-8", newline="\n")
        mappings.append({"old_path": article.relative_to(source).as_posix(),
                         "new_path": target_article.relative_to(prepared).as_posix(),
                         "old_sha256": _sha(article.read_bytes()), "new_sha256": _sha(target_article.read_bytes())})
        mapped_images = []
        for image in images:
            new_name = names[f"images/{image.name}"]
            target_image = target_dir / new_name
            shutil.copy2(image, target_image)
            if _sha(image.read_bytes()) != _sha(target_image.read_bytes()):
                raise FlatMigrationError(f"image copy changed bytes: {image}")
            mappings.append({"old_path": image.relative_to(source).as_posix(),
                             "new_path": target_image.relative_to(prepared).as_posix(),
                             "old_sha256": _sha(image.read_bytes()), "new_sha256": _sha(target_image.read_bytes())})
            mapped_images.append({"old_name": image.name, "new_name": new_name, "sha256": _sha(image.read_bytes())})
        article_records.append({"style": style, "asset": asset, "article": target_article.relative_to(prepared).as_posix(),
                                "images": mapped_images})
    return {"country_code": country, "folder": source.name, "articles": article_records, "mappings": mappings}


def prepare(project_root: Path, source_business_date: str, migration_id: str) -> Path:
    root = Path(project_root).resolve()
    day_folder = _day(source_business_date)
    output = root / "output" / day_folder
    if not re.fullmatch(r"[a-z0-9-]+", migration_id or ""):
        raise FlatMigrationError("migration id must be lowercase letters, digits and hyphens")
    tx = root / "work" / "output-layout-migration" / day_folder / migration_id
    if tx.exists():
        raise FlatMigrationError("migration id already exists")
    marker_path = output / "manifest.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8")) if marker_path.exists() else None
    countries = [("TH", "TH-Thailand"), ("ZA", "ZA-South-Africa")]
    journal_countries = []
    for country, folder in countries:
        source = output / folder
        if not source.is_dir():
            raise FlatMigrationError(f"country output missing: {folder}")
        record = _prepare_country(source, tx / "prepared" / folder, source_business_date, country)
        journal_countries.append(record)
    # Produce new metadata from prepared files.  The original manifests remain
    # byte-for-byte in backup as immutable provenance.
    for record in journal_countries:
        prepared = tx / "prepared" / record["folder"]
        source_folder = output / record["folder"]
        manifest_name = "source-layout-manifest.json" if record["country_code"] == "TH" else "manifest.json"
        manifest_path = prepared / manifest_name
        existing = json.loads((source_folder / manifest_name).read_text(encoding="utf-8"))
        inventory = {path: _sha(data) for path, data in _files(prepared).items()
                     if path not in {"manifest.json", "source-layout-manifest.json", "README.md"}}
        existing["layout_version"] = "p002-final-flat/v1"
        existing["layout_migration"] = {"migration_id": migration_id, "source_business_date": source_business_date,
                                        "path_mappings": record["mappings"]}
        existing["files"] = inventory
        if record["country_code"] == "TH":
            by_id = {f"{item['style']}-{item['asset']}": item for item in record["articles"]}
            for article in existing.get("articles", []):
                current = by_id.get(article.get("article_id"))
                if current:
                    article["new_path"] = f"output/{_day(source_business_date)}/{record['folder']}/{current['article']}"
                    article["source_sha256"] = _sha((prepared / current["article"]).read_bytes())
        manifest_path.write_bytes(_json(existing))
    if marker is not None:
        marker = dict(marker)
        countries_data = dict(marker.get("countries") or {})
        for record in journal_countries:
            code = record["country_code"]
            if code in countries_data:
                entry = dict(countries_data[code])
                entry["manifest_sha256"] = _sha((tx / "prepared" / record["folder"] / "manifest.json").read_bytes())
                countries_data[code] = entry
        marker["countries"] = countries_data
        (tx / "prepared-marker.json").write_bytes(_json(marker))
    journal = {"schema": "p002-final-flat-migration/v1", "migration_id": migration_id,
               "source_business_date": source_business_date, "state": "PREPARED", "countries": journal_countries,
               "marker_before_sha256": _sha(marker_path.read_bytes()) if marker_path.exists() else None}
    (tx / "journal.json").write_bytes(_json(journal))
    return tx


def apply(project_root: Path, source_business_date: str, migration_id: str) -> dict:
    root = Path(project_root).resolve()
    folder = _day(source_business_date)
    tx = root / "work" / "output-layout-migration" / folder / migration_id
    journal_path = tx / "journal.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    if journal.get("state") != "PREPARED" or journal.get("source_business_date") != source_business_date:
        raise FlatMigrationError("migration is not prepared for this date")
    output = root / "output" / folder
    marker_path = output / "manifest.json"
    marker_before = marker_path.read_bytes() if marker_path.exists() else None
    copied = []
    try:
        journal["state"] = "APPLYING"; journal_path.write_bytes(_json(journal))
        for record in journal["countries"]:
            original, backup, prepared = output / record["folder"], tx / "backup" / record["folder"], tx / "prepared" / record["folder"]
            if not prepared.is_dir() or backup.exists():
                raise FlatMigrationError("prepared/backup tree is invalid")
            backup.parent.mkdir(parents=True, exist_ok=True)
            # Explorer/indexers can keep a directory handle open on Windows,
            # making an otherwise safe directory rename fail with WinError 5.
            # Copy the verified backup first, then install individual files.
            shutil.copytree(original, backup)
            if _files(original) != _files(backup):
                raise FlatMigrationError("backup checksum mismatch")
            copied.append((original, backup))
            for relative, data in _files(prepared).items():
                destination = original / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            for legacy in list(original.glob("*/*/article.md")):
                legacy.unlink()
            for image_folder in list(original.glob("*/*/images")):
                shutil.rmtree(image_folder)
            installed = {key: value for key, value in _files(original).items() if key != "STATUS.md"}
            if installed != _files(prepared):
                raise FlatMigrationError("installed output differs from prepared tree")
        new_marker = tx / "prepared-marker.json"
        if new_marker.exists():
            temp = output / ".flat-layout-marker.tmp"
            temp.write_bytes(new_marker.read_bytes())
            os.replace(temp, marker_path)
        journal["state"] = "COMMITTED"; journal_path.write_bytes(_json(journal))
        return {"status": "COMMITTED", "migration_id": migration_id, "countries": [r["country_code"] for r in journal["countries"]]}
    except Exception:
        for original, backup in reversed(copied):
            # Restore individual files from the byte-checked backup.  This
            # avoids the same directory-rename restriction during recovery.
            if backup.exists():
                for path in original.rglob("*"):
                    if path.is_file():
                        path.unlink()
                for path in backup.rglob("*"):
                    if path.is_file():
                        destination = original / path.relative_to(backup)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(path, destination)
        if marker_before is not None:
            marker_path.write_bytes(marker_before)
        journal["state"] = "ROLLED_BACK"; journal_path.write_bytes(_json(journal))
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--date", required=True)
    parser.add_argument("--migration-id", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = {"prepared": str(prepare(args.project_root, args.date, args.migration_id))} if args.prepare else apply(args.project_root, args.date, args.migration_id)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (FlatMigrationError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "HOLD", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
