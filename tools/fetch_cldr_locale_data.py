"""ดึงเฉพาะ CLDR JSON ที่ P002 ต้องใช้จาก commit ที่ pin แล้ว.

ไม่ clone และไม่รันโค้ดภายนอก ดึงเฉพาะ LICENSE, likelySubtags, numbers และ
Gregorian date formats สำหรับ 19 language-master locales.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import urllib.request
from pathlib import Path

try:
    # เมื่อเรียกจากราก Repo: python -m tools.fetch_cldr_locale_data
    from tools.bootstrap_multilingual_locales import CLDR_COMMIT, CLDR_VERSION, MASTER_LOCALES
except ModuleNotFoundError:
    # เมื่อเรียกไฟล์โดยตรง: python tools/fetch_cldr_locale_data.py
    from bootstrap_multilingual_locales import CLDR_COMMIT, CLDR_VERSION, MASTER_LOCALES


REPO_ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = REPO_ROOT / "language" / "vendor" / f"unicode-cldr-{CLDR_VERSION}"
RAW_ROOT = f"https://raw.githubusercontent.com/unicode-org/cldr-json/{CLDR_COMMIT}"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fetch(relative_source: str) -> bytes:
    url = f"{RAW_ROOT}/{relative_source}"
    request = urllib.request.Request(url, headers={"User-Agent": "P002-locale-bootstrap/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}: {url}")
        return response.read()


def _sources() -> list[tuple[str, str, bool]]:
    items: list[tuple[str, str, bool]] = [
        ("LICENSE", "LICENSE", False),
        (
            "cldr-json/cldr-core/supplemental/likelySubtags.json",
            "supplemental/likelySubtags.json",
            True,
        ),
    ]
    for item in MASTER_LOCALES:
        cldr_locale = item["cldr"]
        pack_locale = item["locale"]
        items.extend([
            (
                f"cldr-json/cldr-numbers-full/main/{cldr_locale}/numbers.json",
                f"locales/{pack_locale}/numbers.json",
                True,
            ),
            (
                f"cldr-json/cldr-dates-full/main/{cldr_locale}/ca-gregorian.json",
                f"locales/{pack_locale}/ca-gregorian.json",
                True,
            ),
        ])
    return items


def fetch() -> None:
    if VENDOR_ROOT.exists():
        raise RuntimeError(f"มี vendor data แล้ว ห้ามเขียนทับ: {VENDOR_ROOT}")

    VENDOR_ROOT.parent.mkdir(parents=True, exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory(prefix="p002-cldr-") as tmp:
        temp_root = Path(tmp) / VENDOR_ROOT.name
        for source, target, is_json in _sources():
            data = _fetch(source)
            if is_json:
                json.loads(data.decode("utf-8"))
            target_path = temp_root / target
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(data)
            records.append({
                "path": target,
                "source": f"{RAW_ROOT}/{source}",
                "sha256": _sha256(data),
                "bytes": len(data),
            })

        manifest = {
            "provider": "Unicode CLDR JSON",
            "repository": "https://github.com/unicode-org/cldr-json",
            "release": CLDR_VERSION,
            "commit": CLDR_COMMIT,
            "license": "Unicode-3.0",
            "license_file": "LICENSE",
            "purpose": "locale identifiers, numbers and date formatting; not translation prose",
            "execution_policy": "data_only_no_external_code_execution",
            "files": records,
        }
        (temp_root / "source-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        shutil.copytree(temp_root, VENDOR_ROOT)


def check() -> None:
    manifest_path = VENDOR_ROOT / "source-manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"ไม่พบ {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("commit") != CLDR_COMMIT or manifest.get("release") != CLDR_VERSION:
        raise RuntimeError("CLDR version/commit ไม่ตรงกับตัวที่ pin")
    for record in manifest.get("files") or []:
        path = VENDOR_ROOT / record["path"]
        if not path.is_file():
            raise RuntimeError(f"vendor file หาย: {record['path']}")
        if _sha256(path.read_bytes()) != record["sha256"]:
            raise RuntimeError(f"checksum ไม่ตรง: {record['path']}")
    expected = 2 + (2 * len(MASTER_LOCALES))
    if len(manifest.get("files") or []) != expected:
        raise RuntimeError(f"manifest ต้องมี {expected} files")
    print(f"CLDR READY: {CLDR_VERSION}@{CLDR_COMMIT[:12]} | {expected} verified files")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        check()
    else:
        fetch()
        check()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
