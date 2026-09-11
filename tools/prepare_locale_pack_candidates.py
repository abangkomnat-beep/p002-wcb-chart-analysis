"""Snapshot draft locale packs for review without touching production registry."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from tools.active_rollout import ACTIVE_COUNTRIES, country_record
from tools.baseline_registry import pack_sha256, verify

ROOT = Path(__file__).resolve().parents[1]

def target_pack_locales() -> tuple[str, ...]:
    """Read the exact foreign pack families from the approved rollout.

    Country provenance remains the source for locale/pack selection; this
    avoids accidentally preparing a retired language from the larger sheet.
    """
    return tuple(dict.fromkeys(
        country_record(country)["language_pack"]
        for country in ACTIVE_COUNTRIES if country != "TH"
    ))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _validated_day_folder(day_folder: str) -> str:
    if not isinstance(day_folder, str):
        raise ValueError("day folder must be DD-MM-YYYY")
    try:
        parsed = datetime.strptime(day_folder, "%d-%m-%Y")
    except ValueError as exc:
        raise ValueError("day folder must be DD-MM-YYYY") from exc
    if parsed.strftime("%d-%m-%Y") != day_folder:
        raise ValueError("day folder must be DD-MM-YYYY")
    return day_folder


def _revision_for(locale_root: Path, source: Path, pack_version: str) -> tuple[str, Path, bool]:
    """Return a preserved matching revision, or the next empty revision.

    A reviewer may be reading an earlier proposed revision.  This helper never
    replaces that tree: unchanged source bytes are a no-op, changed bytes make
    a new revision.
    """
    source_hash = pack_sha256(source)
    version_root = locale_root / pack_version
    revisions = [path for path in version_root.iterdir() if path.is_dir()] if version_root.is_dir() else []
    for path in sorted(revisions, key=lambda item: item.name):
        if pack_sha256(path) == source_hash:
            return path.name, path, True
    numbers = [0]
    for path in revisions:
        match = re.fullmatch(r"r(\d{4})", path.name)
        if match:
            numbers.append(int(match.group(1)))
    revision = f"r{max(numbers) + 1:04d}"
    return revision, version_root / revision, False


def prepare(day_folder: str) -> Path:
    day_folder = _validated_day_folder(day_folder)
    work_root = (ROOT.parent / "work" / "localization").resolve()
    work = (work_root / day_folder / "expansion-control" / "proposed-packs").resolve()
    if work_root not in work.parents:
        raise ValueError("proposal path escapes localization work root")
    work.mkdir(parents=True, exist_ok=True)
    proposals = []
    for locale in target_pack_locales():
        info = verify(locale)
        source = info["pack_dir"]
        pack_version = info["version"]
        locale_root = work / locale
        if info["status"] == "stable_locked":
            proposals.append({
                "locale": locale, "pack_version": pack_version,
                "status": "reuse_locked", "pack_sha256": info["actual_sha256"],
                "recorded_sha256": info["recorded_sha256"],
                "pack_path": str(source), "proposal_path": None,
                "unchanged": True,
            })
            continue
        revision, target, unchanged = _revision_for(locale_root, source, pack_version)
        if not unchanged:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target)
        files = {}
        for path in sorted(p for p in target.rglob("*") if p.is_file()):
            files[path.relative_to(target).as_posix()] = _sha(path.read_bytes())
        proposal = {"schema": "p002-locale-pack-proposal/v2", "locale": locale,
                    "pack_version": pack_version, "proposal_revision": revision,
                    "status": "candidate_pending_review",
                    "production_registry_unchanged": True,
                    "pack_sha256": pack_sha256(target), "files": files,
                    "required_review": ["complete translation corpus", "D-XAUUSD and D-WTIUSD certainty",
                                        "protected numeric literals", "independent reviewer receipt"],
                    "delivery_allowed": False}
        proposal_path = target.parent / f"{revision}.proposal.json"
        _write(proposal_path, proposal)
        proposals.append({"locale": locale, "pack_version": pack_version,
                          "proposal_revision": revision, "status": proposal["status"],
                          "pack_sha256": proposal["pack_sha256"],
                          "proposal_path": proposal_path.relative_to(work).as_posix(),
                          "unchanged": unchanged})
    _write(work / "index.json", {"schema": "p002-locale-pack-proposals/v2", "status": "HOLD",
                                  "locales": proposals,
                                  "reason": "draft snapshots require language calibration and independent review"})
    return work


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day-folder", required=True)
    args = parser.parse_args()
    print(prepare(args.day_folder))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
