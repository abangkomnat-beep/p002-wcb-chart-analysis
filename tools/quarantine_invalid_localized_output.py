"""Quarantine an invalid localized day release with an auditable journal.

The operation is reversible: source files are copied to the remediation area
before the public country folders are removed and the day marker is rewritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _copy_tree(src: Path, dst: Path, records: list[dict]) -> None:
    if not src.exists():
        return
    shutil.copytree(src, dst, dirs_exist_ok=True)
    for f in dst.rglob("*"):
        if f.is_file():
            records.append({"path": str(f), "sha256": _sha(f)})


def quarantine(project_root: Path, business_date: str, countries: list[str], transaction_id: str) -> Path:
    out_day = project_root / "output" / business_date
    work_day = project_root / "work" / "localization" / business_date
    q = work_day / "audit-remediation-r1" / "pre-quarantine"
    q.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    marker = out_day / "manifest.json"
    if marker.exists():
        shutil.copy2(marker, q / "day-manifest.before.json")
        records.append({"path": str(q / "day-manifest.before.json"), "sha256": _sha(q / "day-manifest.before.json")})
    for code in countries:
        matches = [p for p in out_day.iterdir() if p.is_dir() and p.name.startswith(code + "-")]
        for src in matches:
            _copy_tree(src, q / src.name, records)
    tx = work_day / "transactions" / transaction_id
    _copy_tree(tx, q / ("transaction-" + transaction_id), records)
    for run_name in ("es-CL", "es-MX"):
        run = work_day / "expansion-control" / "runs" / run_name
        _copy_tree(run, q / ("run-" + run_name), records)

    data = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else {}
    for code in countries:
        data.get("countries", {}).pop(code, None)
    tmp = marker.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(marker)
    for code in countries:
        for src in list(out_day.iterdir()):
            if src.is_dir() and src.name.startswith(code + "-"):
                shutil.rmtree(src)
    journal = {
        "schema": "p002-audit-remediation/quarantine-v1",
        "business_date": business_date,
        "countries": countries,
        "transaction_id": transaction_id,
        "quarantined_at": datetime.now(timezone.utc).isoformat(),
        "marker_after_sha256": _sha(marker),
        "files": records,
        "recovery": "Restore the country directories from pre-quarantine and replace day-manifest.before.json as manifest.json.",
    }
    (q / "quarantine-journal.json").write_text(json.dumps(journal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return q


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", type=Path, required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--countries", nargs="+", required=True)
    ap.add_argument("--transaction", required=True)
    args = ap.parse_args()
    print(quarantine(args.project_root, args.date, args.countries, args.transaction))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
