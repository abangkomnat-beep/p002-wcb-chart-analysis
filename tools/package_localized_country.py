"""ตรวจและจัดชุด localized country edition แบบ path-safe สำหรับ P002.

รุ่นแรกตั้งใจรองรับ South Africa (ZA) เท่านั้น และแยก ``--check`` ซึ่งอ่านอย่างเดียว
ออกจาก ``--commit`` ที่ต้องตรวจ hash ใหม่ก่อนเขียน release marker.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

from tools.language_patch import validate_localized_candidate


class PackageError(Exception):
    code = "PACKAGE_ERROR"


class InputError(PackageError):
    code = "INPUT_ERROR"


class OutputConflict(PackageError):
    code = "OUTPUT_CONFLICT"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"อ่าน JSON ไม่ได้: {path}: {exc}") from exc


def resolve_scoped_file(root: Path, relative_path: str) -> Path:
    """resolve ไฟล์ที่ต้องอยู่ใต้ root และไม่ตาม symlink/junction."""
    if not relative_path or Path(relative_path).is_absolute():
        raise InputError(f"path ต้องเป็น relative: {relative_path!r}")
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise InputError(f"path หลุด root: {relative_path!r}") from exc
    current = root.resolve()
    for part in Path(relative_path).parts:
        current = current / part
        if current.is_symlink() or (current.exists() and current.is_dir() and getattr(current.stat(), "st_file_attributes", 0) & 0x400):
            raise InputError(f"ห้ามใช้ symlink/junction: {relative_path!r}")
    return candidate


def load_trusted_receipts(index_path: Path, run_root: Path) -> list[dict]:
    payload = _read_json(index_path)
    records = payload.get("receipts")
    if not isinstance(records, list):
        raise InputError("receipt index ต้องมี receipts เป็น list")
    result: list[dict] = []
    for item in records:
        if not isinstance(item, dict):
            raise InputError("receipt ต้องเป็น object")
        record = dict(item)
        receipt_path = record.get("path")
        if receipt_path:
            path = resolve_scoped_file(run_root, receipt_path)
            record = {**_read_json(path), **{k: v for k, v in record.items() if k != "path"}}
        result.append(record)
    return result


def load_job(manifest_path: Path, project_root: Path) -> tuple[dict, Path, Path]:
    manifest = _read_json(manifest_path)
    if manifest.get("schema") != "p002-za-source/v1":
        raise InputError("manifest ต้องใช้ schema p002-za-source/v1")
    if manifest.get("country_code") != "ZA" or manifest.get("content_locale") != "en-ZA":
        raise InputError("รุ่นนี้รองรับ ZA/en-ZA เท่านั้น")
    run_root = manifest_path.parent.resolve()
    output_root = resolve_scoped_file(project_root, manifest.get("output_root", "output"))
    articles = manifest.get("articles")
    if not isinstance(articles, list) or not articles:
        raise InputError("manifest ต้องมี articles อย่างน้อยหนึ่งรายการ")
    for item in articles:
        for key in ("article_id", "style", "asset", "source_path", "candidate_path", "claim_map_path"):
            if not item.get(key):
                raise InputError(f"article ขาด {key}")
        resolve_scoped_file(project_root, item["source_path"])
        resolve_scoped_file(run_root, item["candidate_path"])
        resolve_scoped_file(run_root, item["claim_map_path"])
    return manifest, run_root, output_root


def _article_result(manifest: dict, article: dict, project_root: Path, run_root: Path,
                    receipts: list[dict]) -> dict:
    source_path = resolve_scoped_file(project_root, article["source_path"])
    candidate_path = resolve_scoped_file(run_root, article["candidate_path"])
    claim_path = resolve_scoped_file(run_root, article["claim_map_path"])
    if not source_path.is_file() or not candidate_path.is_file() or not claim_path.is_file():
        return {"article_id": article["article_id"], "status": "HOLD",
                "findings": [{"code": "FILE_MISSING", "detail": "source/candidate/claim map หาย"}]}
    source_bytes = source_path.read_bytes()
    target_bytes = candidate_path.read_bytes()
    claim_map = _read_json(claim_path)
    job = {
        **article,
        "country_code": manifest["country_code"],
        "content_locale": manifest["content_locale"],
        "language_pack": manifest["language_pack"],
        "pack_version": manifest["pack_version"],
        "pack_sha256": manifest.get("pack_sha256"),
        "target_sha256": sha256_bytes(target_bytes),
    }
    pack_info = {
        "locale": manifest["language_pack"],
        "version": manifest["pack_version"],
        "status": manifest.get("pack_status", "draft"),
        "sha256": manifest.get("pack_sha256"),
    }
    result = validate_localized_candidate(source_bytes, target_bytes, job=job,
                                          claim_map=claim_map,
                                          trusted_receipts=receipts,
                                          pack_info=pack_info)
    result.update({"article_id": article["article_id"], "candidate_path": article["candidate_path"],
                   "target_sha256": sha256_bytes(target_bytes)})
    result["status"] = "READY" if result["release_eligible"] else "HOLD"
    return result


def check_country(manifest_path: Path, receipt_index: Path, project_root: Path) -> dict:
    manifest, run_root, _ = load_job(manifest_path, project_root)
    receipts = load_trusted_receipts(receipt_index, run_root)
    results = [_article_result(manifest, item, project_root, run_root, receipts)
               for item in manifest["articles"]]
    ready = sum(item["status"] == "READY" for item in results)
    status = "PASS" if ready == len(results) and results else "HOLD"
    return {"mode": "check", "status": status, "release_eligible": status == "PASS",
            "expected_articles": len(results), "ready_articles": ready,
            "country_code": manifest["country_code"], "content_locale": manifest["content_locale"],
            "articles": results}


def _safe_output_path(output_root: Path, relative_path: str) -> Path:
    return resolve_scoped_file(output_root, relative_path)


def commit_country(manifest_path: Path, receipt_index: Path, project_root: Path,
                   release_id: str, batch_id: str) -> dict:
    # ตรวจทุกอย่างใน invocation นี้เอง ไม่ใช้ผล --check เก่า
    report = check_country(manifest_path, receipt_index, project_root)
    if not report["release_eligible"]:
        raise PackageError("country ยังไม่พร้อม commit")
    manifest, run_root, output_root = load_job(manifest_path, project_root)
    release_root = _safe_output_path(output_root,
                                     f"134-Localized/ZA-South-Africa/en-ZA/releases/{release_id}")
    staging = _safe_output_path(run_root, f"staging/{release_id}")
    if release_root.exists():
        raise OutputConflict(f"release มีอยู่แล้ว: {release_root}")
    staging.mkdir(parents=True, exist_ok=False)
    try:
        for item in manifest["articles"]:
            result = next(row for row in report["articles"] if row["article_id"] == item["article_id"])
            source_candidate = resolve_scoped_file(run_root, result["candidate_path"])
            target = staging / f"{item['style']}-{item['asset']}"
            target.mkdir(parents=True, exist_ok=False)
            shutil.copy2(source_candidate, target / "article.md")
            image_dir = target / "images"
            image_dir.mkdir()
            for image in item.get("images", []):
                src = resolve_scoped_file(run_root, image["candidate_path"])
                shutil.copy2(src, image_dir / Path(image["candidate_path"]).name)
            copied = [target / "article.md", *image_dir.iterdir()]
            if any(not path.is_file() for path in copied):
                raise PackageError("ไฟล์ใน staging ไม่ครบ")
        public_manifest = {"schema": "p002-za-release/v1", "release_id": release_id,
                           "batch_id": batch_id, "country_code": "ZA", "content_locale": "en-ZA",
                           "source_business_date": manifest.get("source_business_date"),
                           "articles": [{"article_id": item["article_id"],
                                         "path": f"{item['style']}-{item['asset']}/article.md",
                                         "sha256": sha256_bytes((staging / f"{item['style']}-{item['asset']}" / "article.md").read_bytes())}
                                        for item in manifest["articles"]]}
        (staging / "manifest.json").write_text(json.dumps(public_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # ตรวจ staging ก่อนเปิดเผย release directory
        release_root.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, release_root)
        batch_root = _safe_output_path(output_root, "134-Localized/batches")
        batch_root.mkdir(parents=True, exist_ok=True)
        batch_marker = batch_root / f"{batch_id}.json"
        if batch_marker.exists():
            raise OutputConflict(f"batch marker มีอยู่แล้ว: {batch_marker}")
        batch_marker.write_text(json.dumps({"schema": "p002-za-batch/v1", "batch_id": batch_id,
                                            "country": "ZA-South-Africa", "release_id": release_id},
                                           ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return {"mode": "commit", "status": "PASS", "release_eligible": True,
            "release_root": str(release_root), "batch_id": batch_id, "release_id": release_id}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--receipt-index", required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--commit", action="store_true")
    parser.add_argument("--release-id")
    parser.add_argument("--batch-id")
    args = parser.parse_args(argv)
    try:
        project_root = Path(args.project_root).resolve()
        manifest = Path(args.manifest).resolve()
        receipt_index = Path(args.receipt_index).resolve()
        if args.commit and (not args.release_id or not args.batch_id):
            raise InputError("--commit ต้องมี --release-id และ --batch-id")
        result = (check_country(manifest, receipt_index, project_root) if args.check else
                  commit_country(manifest, receipt_index, project_root, args.release_id, args.batch_id))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status") == "PASS" else 1
    except PackageError as exc:
        print(json.dumps({"status": "HOLD", "code": exc.code, "error": str(exc)},
                         ensure_ascii=False, indent=2))
        return 2 if exc.code == "INPUT_ERROR" else 1


if __name__ == "__main__":
    raise SystemExit(main())
