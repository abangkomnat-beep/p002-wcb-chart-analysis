"""Attach already-issued independent receipts to a package handoff.

This command copies immutable reviewer receipt bytes into a temporary handoff;
it never derives a PASS, edits a receipt, or changes candidate bytes.  The
reviewer index must contain exactly one PASS receipt for each of the four
package gates and each source article.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path


class AttachError(ValueError):
    pass


GATES = ("language", "semantic", "visual", "package_input")


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AttachError(f"cannot read JSON: {path}") from exc
    if not isinstance(value, dict):
        raise AttachError(f"JSON object required: {path}")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inside(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value:
        raise AttachError("receipt path is required")
    path = (root / value).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise AttachError("receipt path escapes reviewer root") from exc
    return path


def attach(*, handoff_root: Path, reviewer_root: Path) -> dict:
    handoff, reviewer = Path(handoff_root).resolve(), Path(reviewer_root).resolve()
    manifest = _read(handoff / "source-manifest.json")
    reviewer_index = reviewer / "receipts/index.json"
    if not reviewer_index.is_file():
        # Independent reviewers may publish the canonical index at their
        # review root while keeping receipt paths under receipts/.
        reviewer_index = reviewer / "index.json"
    index = _read(reviewer_index)
    articles = manifest.get("articles")
    entries = index.get("receipts")
    if not isinstance(articles, list) or not articles or not isinstance(entries, list):
        raise AttachError("handoff/articles or reviewer receipts index is invalid")
    expected_articles = {item.get("article_id") for item in articles}
    expected_writer = {item.get("article_id"): _read(handoff / item["proposal_path"])["writer_execution_id"] for item in articles}
    seen: set[tuple[str, str]] = set()
    copied = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) not in ({"receipt_id", "path", "sha256"}, {"path", "sha256"}):
            raise AttachError("reviewer index entry is invalid")
        receipt_path = _inside(reviewer, entry["path"])
        if not receipt_path.is_file():
            receipt_path = _inside(reviewer / "receipts", entry["path"])
        if not receipt_path.is_file() or _sha(receipt_path) != entry["sha256"]:
            raise AttachError("reviewer receipt is missing or changed")
        receipt = _read(receipt_path)
        receipt_id = entry.get("receipt_id", receipt.get("receipt_id"))
        if not isinstance(receipt_id, str) or not receipt_id or receipt.get("receipt_id") != receipt_id:
            raise AttachError("reviewer receipt id is missing or differs from index")
        article_id, gate = receipt.get("article_id"), receipt.get("gate")
        if article_id not in expected_articles or gate not in GATES:
            raise AttachError("review receipt article/gate is outside handoff")
        if receipt.get("status") != "PASS" or receipt.get("verdict") != "PASS":
            raise AttachError("review receipt is not an issued PASS receipt")
        if receipt.get("writer_execution_id") != expected_writer[article_id]:
            raise AttachError("review receipt writer identity does not match handoff")
        reviewer_id = receipt.get("reviewer_execution_id")
        if not isinstance(reviewer_id, str) or not reviewer_id or reviewer_id == receipt.get("writer_execution_id"):
            raise AttachError("reviewer identity is missing or not independent")
        key = (article_id, gate)
        if key in seen:
            raise AttachError("duplicate article/gate receipt")
        seen.add(key)
        target = handoff / "receipts" / "independent" / (re.sub(r"[^A-Za-z0-9_.-]", "_", receipt_id) + ".json")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != receipt_path.read_bytes():
            raise AttachError("handoff receipt already has different bytes")
        if not target.exists():
            shutil.copyfile(receipt_path, target)
        # package_localized_country resolves index paths from handoff root;
        # retain the explicit receipts/ prefix in the immutable reference.
        copied.append({"receipt_id": receipt_id, "path": target.relative_to(handoff).as_posix(), "sha256": _sha(target)})
    required = {(article, gate) for article in expected_articles for gate in GATES}
    if seen != required:
        missing = sorted(required - seen)
        raise AttachError("review receipt coverage incomplete: " + ", ".join(f"{a}/{g}" for a, g in missing))
    original = _read(handoff / "receipts/index.json")
    source_entries = original.get("receipts")
    if not isinstance(source_entries, list):
        raise AttachError("handoff receipt index is invalid")
    combined = {item["receipt_id"]: item for item in source_entries}
    for item in copied:
        if item["receipt_id"] in combined and combined[item["receipt_id"]] != item:
            raise AttachError("receipt id collision")
        combined[item["receipt_id"]] = item
    data = {"receipts": list(combined.values()), "status": "READY_FOR_PACKAGE_INPUT_REVIEW"}
    encoded = (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    index_path = handoff / "receipts/index.json"
    if index_path.exists():
        existing = _read(index_path)
        if existing.get("status") == "READY_FOR_PACKAGE_INPUT_REVIEW" and index_path.read_bytes() == encoded:
            return {"status": "ATTACHED", "articles": len(expected_articles), "review_receipts": len(copied), "receipt_index": str(index_path), "receipt_index_sha256": _sha(index_path)}
        if existing.get("status") not in {None, "SOURCE_READY_ONLY"}:
            raise AttachError("handoff receipt index already differs")
    if not index_path.exists() or _read(index_path).get("status") in {None, "SOURCE_READY_ONLY"}:
        index_path.write_bytes(encoded)
    return {"status": "ATTACHED", "articles": len(expected_articles), "review_receipts": len(copied), "receipt_index": str(index_path), "receipt_index_sha256": _sha(index_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff-root", required=True)
    parser.add_argument("--reviewer-root", required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(attach(handoff_root=Path(args.handoff_root), reviewer_root=Path(args.reviewer_root)), ensure_ascii=False))
        return 0
    except AttachError as exc:
        print(json.dumps({"status": "HOLD", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
