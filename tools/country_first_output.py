"""Move daily source artifacts into the country-first P002 output layout.

The legacy writers still emit their files into style-root folders.  This module
is the single, reversible handoff used after a successful source run: it copies
and renames a complete lane, rewrites local image references, records a journal,
then removes the legacy duplicates.  A backup is kept under ``work`` so a
failed migration can be restored without touching the source data.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from tools.daily_source_selector import lanes_for_date
from tools.delivery_file_naming import image_name


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_final_image(name: str, business_date: str, style: str, asset: str, ordinal: int) -> bool:
    prefix = f"P002-{business_date.replace('-', '')}-TH-{style}-{asset}-img{ordinal:02d}-"
    return name.startswith(prefix) and name.lower().endswith(".webp")


def migrate_day(*, output_root: Path, work_root: Path, business_date: str,
                styles: set[str] | None = None) -> dict:
    """Migrate present legacy lanes for one Bangkok business date.

    Missing lanes are reported and left untouched.  A lane is promoted only
    when its article and every sibling image can be copied successfully.
    """
    day_name = datetime.strptime(business_date, "%Y-%m-%d").strftime("%d-%m-%Y")
    day = Path(output_root) / day_name
    backup = Path(work_root) / "localization" / day_name / "country-first-migration"
    records: list[dict] = []
    for style, asset, canonical_rel, canonical_name in lanes_for_date(business_date):
        if styles and style not in styles:
            continue
        legacy = day / {"E": "E-อินดิเคเตอร์", "L": "L-Forex-Daily", "D": "D-โครงสร้างกราฟ"}.get(style, "")
        source_article = legacy / f"{asset.lower()}.md"
        if not source_article.is_file():
            records.append({"style": style, "asset": asset, "status": "missing",
                            "legacy": str(source_article)})
            continue
        files = [source_article] + sorted(
            p for p in legacy.glob(f"{asset.lower()}*")
            if p.is_file() and p != source_article)
        target = day / canonical_rel
        target.mkdir(parents=True, exist_ok=True)
        lane_backup = backup / style / asset
        lane_backup.mkdir(parents=True, exist_ok=True)
        mapping: dict[str, str] = {}
        image_no = 0
        for src in files:
            suffix = "article.md" if src == source_article else re.sub(
                rf"^{re.escape(asset.lower())}-?", "", src.stem, flags=re.I) + src.suffix
            if src == source_article:
                name = canonical_name
            else:
                image_no += 1
                name = image_name(business_date, "TH", style, asset, image_no, src.name)
            mapping[src.name] = name
            shutil.copy2(src, lane_backup / src.name)
        article = source_article.read_text(encoding="utf-8")
        for old, new in mapping.items():
            article = article.replace(old, new)
        staged = target / f".{canonical_name}.stage"
        staged.write_text(article, encoding="utf-8", newline="\n")
        shutil.copy2(staged, target / canonical_name)
        staged.unlink(missing_ok=True)
        for src in files:
            if src == source_article:
                continue
            shutil.copy2(src, target / mapping[src.name])
        for src in files:
            src.unlink()
        if legacy.exists() and not any(legacy.iterdir()):
            legacy.rmdir()
        records.append({"style": style, "asset": asset, "status": "migrated",
                        "source": str(source_article), "target": str(target / canonical_name),
                        "files": {name: _sha(target / new) for name, new in mapping.items()}})
    journal = backup / "migration-journal.json"
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(json.dumps({"schema": "p002-country-first-migration/v1",
                                   "business_date": business_date,
                                   "records": records}, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    return {"day": day_name, "journal": str(journal), "records": records,
            "migrated": sum(r["status"] == "migrated" for r in records)}


def repair_canonical_day(*, output_root: Path, work_root: Path, business_date: str,
                         styles: set[str] | None = None) -> dict:
    """Normalize image names in already country-first lanes.

    Older writers emitted role-only names.  Repair happens in place with a
    backup and deterministic ``imgNN`` names so selector and future reruns
    observe one contract.
    """
    day_name = datetime.strptime(business_date, "%Y-%m-%d").strftime("%d-%m-%Y")
    day = Path(output_root) / day_name
    backup = Path(work_root) / "localization" / day_name / "country-first-migration" / "canonical-repair"
    records = []
    for style, asset, canonical_rel, canonical_name in lanes_for_date(business_date):
        if styles and style not in styles:
            continue
        lane = day / canonical_rel
        article = lane / canonical_name
        if not article.is_file():
            continue
        images = sorted(lane.glob("*.webp"))
        if not images:
            continue
        backup_lane = backup / style / asset
        backup_lane.mkdir(parents=True, exist_ok=True)
        mapping = {}
        for i, p in enumerate(images, 1):
            # A canonical final name is already stable. Feeding it back into
            # image_name would hash its own prefix and change the name on each
            # repair run, invalidating bindings and receipts.
            mapping[p.name] = (p.name if _is_final_image(p.name, business_date, style, asset, i)
                               else image_name(business_date, "TH", style, asset, i, p.name))
        if all(old == new for old, new in mapping.items()):
            continue
        shutil.copy2(article, backup_lane / article.name)
        for p in images:
            shutil.copy2(p, backup_lane / p.name)
        text = article.read_text(encoding="utf-8")
        for old, new in mapping.items():
            text = text.replace(old, new)
        article.write_text(text, encoding="utf-8", newline="\n")
        staged = []
        for old, new in mapping.items():
            tmp = lane / ("." + old + ".repair")
            (lane / old).replace(tmp)
            staged.append((tmp, lane / new))
        for tmp, dest in staged:
            tmp.replace(dest)
        records.append({"style": style, "asset": asset, "status": "repaired",
                        "target": str(article), "mapping": mapping})
    journal = backup / "repair-journal.json"
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(json.dumps({"schema": "p002-country-first-repair/v1",
                                   "business_date": business_date,
                                   "records": records}, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    return {"day": day_name, "journal": str(journal), "records": records,
            "repaired": len(records)}


__all__ = ["migrate_day", "repair_canonical_day"]
