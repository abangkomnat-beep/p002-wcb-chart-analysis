"""ZA file workflow. Receipt custody belongs to Lead, not writer JSON."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
import re
import stat
import uuid
from datetime import date
from pathlib import Path, PureWindowsPath
from PIL import Image
from tools import baseline_registry, locale_loader
from tools.language_patch import validate_localized_candidate


class PackageError(Exception):
    code = "PACKAGE_ERROR"


class InputError(PackageError):
    code = "INPUT_ERROR"


class OutputConflict(PackageError):
    code = "OUTPUT_CONFLICT"


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _object(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key: {key}")
            result[key] = value
        return result
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=unique)
    except (ValueError, UnicodeError) as exc:
        raise InputError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise InputError("JSON root must be object")
    return value


def _bytes(path):
    try:
        return path.read_bytes()
    except OSError as exc:
        raise InputError(f"cannot read {path.name}: {exc}") from exc


def _read_json(path):
    return _object(_bytes(path))


def _id(value, field):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise InputError(f"invalid {field}")
    if re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", value, re.I):
        raise InputError(f"reserved {field}")
    return value


def _hash(value, field):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise InputError(f"invalid {field}")
    return value


def _no_links(path):
    for part in [*reversed(path.parents), path]:
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise InputError(f"link/reparse point forbidden: {part}")


def resolve_scoped_file(root, relative_path):
    if not isinstance(relative_path, str) or not relative_path:
        raise InputError("relative path required")
    parts = relative_path.replace("\\", "/").split("/")
    win = PureWindowsPath(relative_path)
    if win.drive or win.root or any(p in {"", ".", ".."} or ":" in p or p.endswith((" ", ".")) for p in parts):
        raise InputError(f"unsafe relative path: {relative_path}")
    root = Path(os.path.abspath(root))
    candidate = root.joinpath(*parts)
    _no_links(candidate)
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise InputError("path outside root") from exc
    return candidate


def _inside(root, path):
    root, path = Path(os.path.abspath(root)), Path(os.path.abspath(path))
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise InputError("path outside permitted root") from exc
    return resolve_scoped_file(root, relative)


def load_job(manifest_path, project_root):
    project_root = Path(os.path.abspath(project_root))
    manifest_path = _inside(project_root / "work/localization", manifest_path)
    manifest = _read_json(manifest_path)
    if manifest.get("schema") != "p002-za-source/v1":
        raise InputError("source schema must be p002-za-source/v1")
    if (manifest.get("country_code"), manifest.get("content_locale"), manifest.get("language_pack")) != ("ZA", "en-ZA", "en-001"):
        raise InputError("only ZA/en-ZA/en-001 supported")
    _id(manifest.get("run_id"), "run_id")
    _hash(manifest.get("pack_sha256"), "pack_sha256")
    if not isinstance(manifest.get("pack_version"), str) or not manifest["pack_version"]:
        raise InputError("pack_version required")
    try:
        day = date.fromisoformat(manifest["source_business_date"])
    except (ValueError, TypeError, KeyError) as exc:
        raise InputError("source_business_date must be YYYY-MM-DD") from exc
    if day.isoformat() != manifest["source_business_date"] or "output_root" in manifest:
        raise InputError("noncanonical date or output_root override")
    output_root = resolve_scoped_file(project_root, f"output/{day:%d-%m-%Y}")
    run_root = manifest_path.parent
    articles = manifest.get("articles")
    if not isinstance(articles, list) or not articles:
        raise InputError("nonempty articles required")
    seen, folders, candidates = set(), set(), set()
    for item in articles:
        if not isinstance(item, dict):
            raise InputError("article must be object")
        for key in ("article_id", "style", "asset", "source_receipt_id"):
            _id(item.get(key), key)
        key, folder = item["article_id"].casefold(), f"{item['style']}-{item['asset']}".casefold()
        if key in seen or folder in folders:
            raise InputError("duplicate article/destination")
        seen.add(key)
        folders.add(folder)
        for key in ("source_sha256", "claim_map_sha256"):
            _hash(item.get(key), key)
        _inside(project_root / "output", resolve_scoped_file(project_root, item.get("source_path")))
        for key, area in (("candidate_path", "candidates"), ("proposal_path", "proposals"), ("claim_map_path", "claims")):
            path = resolve_scoped_file(run_root, item.get(key))
            _inside(run_root / area, path)
            if key == "candidate_path":
                if str(path).casefold() in candidates:
                    raise InputError("duplicate candidate path")
                candidates.add(str(path).casefold())
        images = item.get("images")
        if not isinstance(images, list) or not images:
            raise InputError("image inventory required for chart pilot")
        names = set()
        for image in images:
            if not isinstance(image, dict):
                raise InputError("image must be object")
            name = image.get("name")
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+\.webp", name) or name.casefold() in names:
                raise InputError("invalid/duplicate image name")
            names.add(name.casefold())
            for key in ("source_sha256", "target_sha256"):
                _hash(image.get(key), key)
            _inside(project_root / "output", resolve_scoped_file(project_root, image.get("source_path")))
            _inside(run_root / "candidates", resolve_scoped_file(run_root, image.get("candidate_path")))
    return manifest, run_root, output_root


def load_trusted_receipts(index_path, run_root):
    index_path = _inside(run_root / "receipts", index_path)
    records = _read_json(index_path).get("receipts")
    if not isinstance(records, list):
        raise InputError("receipt index requires list")
    result, seen = [], set()
    for entry in records:
        if not isinstance(entry, dict) or set(entry) != {"receipt_id", "path", "sha256"}:
            raise InputError("only id/path/hash references allowed in receipt index")
        rid = _id(entry["receipt_id"], "receipt_id")
        if rid in seen:
            raise InputError("duplicate receipt id")
        seen.add(rid)
        path = _inside(run_root / "receipts", resolve_scoped_file(run_root, entry["path"]))
        data = _bytes(path)
        if sha256_bytes(data) != _hash(entry["sha256"], "receipt sha256"):
            raise InputError("receipt checksum mismatch")
        record = _object(data)
        if record.get("receipt_id") != rid:
            raise InputError("receipt id mismatch")
        result.append(record)
    return result


def _load_pack(manifest):
    try:
        info = baseline_registry.verify("en-001", manifest["pack_version"])
        pack = locale_loader.load_locale("en-001", manifest["pack_version"])
    except (baseline_registry.BaselineError, locale_loader.LanguagePackError, OSError, ValueError) as exc:
        raise InputError(f"pack verification failed: {exc}") from exc
    if pack.baseline.get("status") != info["status"]:
        raise InputError("registry/baseline status mismatch")
    return {**info, "locale": pack.locale, "version": pack.version, "sha256": pack.sha256, "verified": True}


def _proposal(article, manifest, run_root):
    proposal = _read_json(resolve_scoped_file(run_root, article["proposal_path"]))
    if proposal.get("schema") != "p002-za-proposal/v1" or proposal.get("article_id") != article["article_id"]:
        raise InputError("proposal identity/schema mismatch")
    for field, expected in (("source_sha256", article["source_sha256"]), ("pack_sha256", manifest["pack_sha256"])):
        if proposal.get(field) != expected:
            raise InputError(f"proposal {field} mismatch")
    _id(proposal.get("writer_execution_id"), "writer_execution_id")
    if type(proposal.get("attempt")) is not int or not 1 <= proposal["attempt"] <= 3:
        raise InputError("attempt must be 1..3")
    if not isinstance(proposal.get("open_questions"), list) or not isinstance(proposal.get("alignment"), list):
        raise InputError("proposal lists missing")
    text = proposal.get("target_markdown")
    if not isinstance(text, str) or not text.strip():
        raise InputError("target_markdown required")
    target = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    if target.startswith(b"\xef\xbb\xbf"):
        raise InputError("BOM not supported")
    return proposal, target


def _metadata(body):
    lines = body.splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        raise InputError("frontmatter required")
    pairs = {}
    for line in lines[1:lines[1:].index("---") + 1]:
        if ":" not in line:
            raise InputError("pilot requires simple scalar frontmatter")
        key, value = line.split(":", 1)
        if key in pairs:
            raise InputError("duplicate metadata key")
        pairs[key] = value.strip().strip("\"'")
    return pairs


def _article_result(manifest, article, project_root, run_root, receipts, pack, *, staging=False):
    source = _bytes(resolve_scoped_file(project_root, article["source_path"]))
    claim_bytes = _bytes(resolve_scoped_file(run_root, article["claim_map_path"]))
    proposal, target = _proposal(article, manifest, run_root)
    if not staging and _bytes(resolve_scoped_file(run_root, article["candidate_path"])) != target:
        raise InputError("candidate differs from proposal")
    job = {**article, **{k: manifest[k] for k in ("country_code", "content_locale", "language_pack", "pack_version", "pack_sha256")},
           "writer_execution_id": proposal["writer_execution_id"], "alignment": proposal["alignment"],
           "claim_map_actual_sha256": sha256_bytes(claim_bytes), "target_sha256": sha256_bytes(target),
           "image_hashes": {x["name"]: x["target_sha256"] for x in article["images"]}}
    result = validate_localized_candidate(source, target, job=job, claim_map=_object(claim_bytes), trusted_receipts=receipts, pack_info=pack)
    files = {f"{article['style']}-{article['asset']}/article.md": target}
    findings = result["findings"]
    if proposal["open_questions"]:
        findings.append({"code": "OPEN_QUESTIONS", "detail": "writer questions unresolved"})
    if not staging:
        text = target.decode("utf-8")
        before, after = _metadata(source.decode("utf-8")), _metadata(text)
        for key in ("asset", "style"):
            if key in before and before[key].casefold() != article[key].casefold():
                findings.append({"code": "SOURCE_IDENTITY_MISMATCH", "detail": key})
        if not before.get("slug") or after.get("slug") != before["slug"] + "-za" or after.get("country") != "south-africa" or after.get("language") != "en":
            findings.append({"code": "METADATA_MISMATCH", "detail": "country/language/slug"})
        for key in set(before) | set(after):
            if key not in {"title", "excerpt", "country", "language", "slug"} and before.get(key) != after.get(key):
                findings.append({"code": "METADATA_MISMATCH", "detail": key})
        references = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
        if set(references) != {f"images/{x['name']}" for x in article["images"]} or "<img" in text.casefold() or re.search(r"!\[[^\]]*\]\[", text):
            findings.append({"code": "IMAGE_LINK_MISMATCH", "detail": "use inventoried relative image links"})
        for image in article["images"]:
            src_data = _bytes(resolve_scoped_file(project_root, image["source_path"]))
            data = _bytes(resolve_scoped_file(run_root, image["candidate_path"]))
            if sha256_bytes(src_data) != image["source_sha256"] or sha256_bytes(data) != image["target_sha256"]:
                findings.append({"code": "IMAGE_CHANGED", "detail": image["name"]})
            try:
                with Image.open(io.BytesIO(data)) as decoded:
                    if decoded.format != "WEBP":
                        raise ValueError("expected WebP")
                    decoded.load()
            except (OSError, ValueError, Image.DecompressionBombError):
                findings.append({"code": "IMAGE_INVALID", "detail": image["name"]})
            files[f"{article['style']}-{article['asset']}/images/{image['name']}"] = data
    result["release_eligible"] = result["release_eligible"] and not findings and not staging
    result.update(article_id=article["article_id"], status="READY" if result["release_eligible"] else "HOLD")
    if staging and result["mechanical_ok"]:
        result["status"] = "CANDIDATE"
    return result, target, files


def _evaluate(manifest_path, receipt_index, project_root, *, staging=False):
    manifest, run_root, output_root = load_job(manifest_path, project_root)
    receipts = load_trusted_receipts(receipt_index, run_root)
    pack = _load_pack(manifest)
    results, files, candidates = [], {}, {}
    for article in manifest["articles"]:
        try:
            result, target, article_files = _article_result(manifest, article, project_root, run_root, receipts, pack, staging=staging)
            files.update(article_files)
            candidates[article["candidate_path"]] = target
        except (InputError, UnicodeError) as exc:
            result = {"article_id": article["article_id"], "status": "HOLD", "mechanical_ok": False, "release_eligible": False,
                      "findings": [{"code": "INPUT_INVALID", "detail": str(exc)}]}
        results.append(result)
    ready = sum(bool(r.get("release_eligible")) for r in results)
    passed = all(r.get("mechanical_ok") for r in results) if staging else ready == len(results)
    report = {"mode": "stage-candidates" if staging else "check", "status": "PASS" if passed else "HOLD",
              "release_eligible": ready == len(results), "expected_articles": len(results), "ready_articles": ready, "articles": results}
    return report, manifest, run_root, output_root, files, candidates


def check_country(manifest_path, receipt_index, project_root):
    return _evaluate(manifest_path, receipt_index, project_root)[0]


def _write_new(path, data):
    _no_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if _bytes(path) == data:
            return
        raise OutputConflict(f"different bytes exist: {path.name}")
    try:
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise OutputConflict("concurrent output creation") from exc


def stage_candidates(manifest_path, receipt_index, project_root):
    report, _, run_root, _, _, candidates = _evaluate(manifest_path, receipt_index, project_root, staging=True)
    # Staging is materialization only; image and final receipt checks run later.
    report["release_eligible"] = False
    if report["status"] != "PASS":
        return report
    for rel, data in candidates.items():
        path = resolve_scoped_file(run_root, rel)
        if path.exists() and _bytes(path) != data:
            raise OutputConflict("new revision needs a new candidate path")
    for rel, data in candidates.items():
        _write_new(resolve_scoped_file(run_root, rel), data)
    return report


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _tree(root):
    result = {}
    for current, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            _no_links(Path(current) / name)
        for name in files:
            path = Path(current) / name
            result[path.relative_to(root).as_posix()] = _bytes(path)
    return result


def commit_country(manifest_path, receipt_index, project_root, release_id, batch_id):
    _id(release_id, "release_id")
    _id(batch_id, "batch_id")
    manifest_path = _inside(Path(project_root) / "work/localization", manifest_path)
    receipt_index = _inside(manifest_path.parent / "receipts", receipt_index)
    original_manifest, original_index = _bytes(manifest_path), _bytes(receipt_index)
    report, manifest, run_root, output_root, files, _ = _evaluate(manifest_path, receipt_index, project_root)
    if original_manifest != _bytes(manifest_path) or original_index != _bytes(receipt_index):
        raise PackageError("job changed during evaluation")
    if not report["release_eligible"]:
        raise PackageError("country HOLD; run --check for findings")
    public = {"schema": "p002-za-release/v1", "country_code": "ZA", "content_locale": "en-ZA",
              "source_business_date": manifest["source_business_date"], "run_id": manifest["run_id"], "release_id": release_id,
              "expected_articles": len(manifest["articles"]),
              "source_manifest_sha256": sha256_bytes(original_manifest),
              "receipt_index_sha256": sha256_bytes(original_index),
              "language_pack": manifest["language_pack"], "pack_version": manifest["pack_version"],
              "pack_sha256": manifest["pack_sha256"],
              "sources": [{"article_id": a["article_id"], "source_sha256": a["source_sha256"],
                           "source_receipt_id": a["source_receipt_id"], "claim_map_sha256": a["claim_map_sha256"],
                           "images": [{k: img[k] for k in ("name", "source_sha256", "target_sha256")} for img in a["images"]]}
                          for a in manifest["articles"]],
              "files": {path: sha256_bytes(data) for path, data in files.items()}}
    files["manifest.json"] = _json_bytes(public)
    files["README.md"] = b"# South Africa\nUse the country release selected in the batch manifest.\n"
    release_rel = f"134-Localized/ZA-South-Africa/en-ZA/releases/{release_id}"
    release = resolve_scoped_file(output_root, release_rel)
    marker = resolve_scoped_file(output_root, f"134-Localized/batches/{batch_id}/manifest.json")
    marker_data = _json_bytes({"schema": "p002-za-batch/v1", "batch_id": batch_id,
                               "source_business_date": manifest["source_business_date"],
                               "countries": {"ZA": {"path": release_rel, "release_id": release_id,
                                                    "manifest_sha256": sha256_bytes(files["manifest.json"])}}})
    if marker.exists() and (_bytes(marker) != marker_data or not release.exists()):
        raise OutputConflict("batch differs or references missing release")
    if release.exists() and _tree(release) != files:
        raise OutputConflict("release differs; use new revision")
    snapshot = _tree(run_root)
    stage = resolve_scoped_file(run_root, f"staging/{release_id}-{uuid.uuid4().hex}")
    if not release.exists():
        for rel, data in files.items():
            _write_new(resolve_scoped_file(stage, rel), data)
        if _tree(stage) != files:
            raise PackageError("staging checksum mismatch")
    second, _, _, _, second_files, _ = _evaluate(manifest_path, receipt_index, project_root)
    now = _tree(run_root)
    prefix = stage.relative_to(run_root).as_posix() + "/"
    now = {k: v for k, v in now.items() if not k.startswith(prefix)}
    if (not second["release_eligible"] or snapshot != now
            or original_manifest != _bytes(manifest_path) or original_index != _bytes(receipt_index)
            or second_files != {k: v for k, v in files.items() if k not in {"manifest.json", "README.md"}}):
        raise PackageError("inputs changed during commit; staging retained")
    if not release.exists():
        _no_links(release)
        release.parent.mkdir(parents=True, exist_ok=True)
        if release.exists():
            raise OutputConflict("concurrent release creation")
        os.rename(stage, release)
    if _tree(release) != files:
        raise PackageError("release checksum mismatch")
    if not marker.exists():
        temp = resolve_scoped_file(run_root, "staging/manifest-" + uuid.uuid4().hex + ".tmp")
        _write_new(temp, marker_data)
        _no_links(marker)
        marker.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(temp, marker)  # atomic visibility, no overwrite
        except FileExistsError:
            if _bytes(marker) != marker_data:
                raise OutputConflict("concurrent batch creation")
        # Remove only the unique file created by this invocation after success;
        # keeping a writable hardlink in work would alias the public marker.
        temp.unlink()
    return {"mode": "commit", "status": "PASS", "release_eligible": True,
            "expected_articles": len(manifest["articles"]), "ready_articles": len(manifest["articles"]),
            "release_root": str(release), "batch_manifest": str(marker)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("project-root", "manifest", "receipt-index"):
        parser.add_argument("--" + name, required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    for name in ("stage-candidates", "check", "commit"):
        modes.add_argument("--" + name, action="store_true")
    parser.add_argument("--release-id")
    parser.add_argument("--batch-id")
    args = parser.parse_args(argv)
    mode = "commit" if args.commit else "stage-candidates" if args.stage_candidates else "check"
    try:
        inputs = (Path(args.manifest), Path(args.receipt_index), Path(args.project_root))
        report = commit_country(*inputs, args.release_id, args.batch_id) if args.commit else stage_candidates(*inputs) if args.stage_candidates else check_country(*inputs)
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["status"] == "PASS" else 1
    except (PackageError, OSError) as exc:
        print(json.dumps({"mode": mode, "status": "HOLD", "release_eligible": False, "code": getattr(exc, "code", "IO_ERROR"), "error": str(exc)}, ensure_ascii=False))
        return 2 if isinstance(exc, InputError) else 1


if __name__ == "__main__":
    raise SystemExit(main())
