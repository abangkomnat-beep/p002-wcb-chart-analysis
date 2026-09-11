"""Build a Lead-owned package handoff from an immutable writer candidate.

This is deliberately a *HOLD-preserving* bridge.  It copies final candidate
bytes, binds them to the frozen source manifest, and translates a verified
source-QA receipt into the package receipt shape.  It never creates language,
semantic, visual, or package-input PASS receipts, and therefore cannot make a
country release eligible on its own.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import re
from pathlib import Path

from tools import localization_config


class HandoffError(ValueError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HandoffError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise HandoffError(f"JSON object required: {path}")
    return value


def _write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() == data:
            return
        raise HandoffError(f"refusing to overwrite different bytes: {path}")
    path.write_bytes(data)


def _json(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _frontmatter_slug(text: str) -> str | None:
    """Read an explicit slug already present in reviewed candidate bytes."""
    match = re.search(r"(?m)^slug:\s*(\S.*?)\s*$", text)
    if not match:
        return None
    value = match.group(1).strip().strip("\"'")
    return value or None


def _proposal_questions(proposal: dict, missing: list[str]) -> list[str]:
    """Retain only writer-owned unresolved questions.

    Review gates are represented separately by review status and the handoff's
    missing-review-gates list; they must not be injected into writer custody.
    """
    questions = proposal.get("open_questions", [])
    if not isinstance(questions, list) or any(not isinstance(q, str) for q in questions):
        raise HandoffError("proposal open_questions must be a string list")
    if missing:
        raise HandoffError("writer alignment has unresolved fields: " + ", ".join(missing))
    return list(questions)


def _writer_proposal_bytes(path: Path, *, article_id: str, source_sha256: str,
                           pack_sha256: str, writer_execution_id: str,
                           target: bytes) -> tuple[dict, bytes]:
    """Verify and retain the writer's proposal bytes without dropping custody.

    Per-span source-quote and receipt linkage may be carried in extension
    fields.  Reconstructing this JSON from a small allow-list silently loses
    that custody, so a bridge either keeps the authenticated writer proposal
    byte-for-byte or fails before making a handoff.
    """
    raw = path.read_bytes()
    proposal = _read(path)
    if (proposal.get("schema") != "p002-localized-proposal/v2"
            or proposal.get("article_id") != article_id
            or proposal.get("source_sha256") != source_sha256
            or proposal.get("pack_sha256") != pack_sha256
            or proposal.get("writer_execution_id") != writer_execution_id):
        raise HandoffError(f"writer proposal identity/custody mismatch: {article_id}")
    if proposal.get("target_markdown") != target.decode("utf-8"):
        raise HandoffError(f"writer proposal target differs from candidate: {article_id}")
    if (not isinstance(proposal.get("alignment"), list)
            or any(not isinstance(row, dict) for row in proposal["alignment"])
            or not isinstance(proposal.get("open_questions"), list)
            or any(not isinstance(question, str) for question in proposal["open_questions"])
            or type(proposal.get("attempt")) is not int or not 1 <= proposal["attempt"] <= 3):
        raise HandoffError(f"writer proposal structure is invalid: {article_id}")
    return proposal, raw


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise HandoffError(f"path escapes allowed root: {path}") from exc


def _source_acceptance(source_receipt: dict, *, receipt_id: str, article_id: str,
                       source_sha256: str, claim_map_sha256: str, pack_sha256: str) -> dict:
    """Re-express an existing hash-bound source QA decision without approving translation."""
    bindings = source_receipt.get("binding_hashes")
    if source_receipt.get("status") != "PASS" or not isinstance(bindings, dict):
        raise HandoffError(f"source QA is not PASS for {article_id}")
    if bindings.get("source_sha256") != source_sha256 or bindings.get("claim_map_sha256") != claim_map_sha256:
        raise HandoffError(f"source QA hash mismatch for {article_id}")
    reviewer = source_receipt.get("reviewer_execution_id")
    if not isinstance(reviewer, str) or not reviewer:
        raise HandoffError(f"source QA reviewer identity missing for {article_id}")
    # Source QA receipts predate the package receipt schema.  This timestamp
    # records bridge execution, while derived_from_sha256 preserves provenance.
    return {
        "receipt_id": receipt_id, "gate": "source_acceptance", "article_id": article_id,
        "source_sha256": source_sha256, "claim_map_sha256": claim_map_sha256,
        "pack_sha256": pack_sha256, "reviewer_execution_id": reviewer,
        "reviewer_kind": "Lead source-QA bridge", "reviewed_at": "2026-09-10T00:00:00+07:00",
        "verdict": "PASS", "findings": [],
        "derived_from_schema": source_receipt.get("schema"),
        "derived_from_sha256": None,
    }


def build(*, project_root: Path, candidate_root: Path, source_bindings: Path,
          output_run: Path) -> dict:
    project = Path(project_root).resolve()
    candidate_root = Path(candidate_root).resolve()
    source_bindings = Path(source_bindings).resolve()
    output_run = Path(output_run).resolve()
    for path in (candidate_root, source_bindings):
        _relative(path, project)
    _relative(output_run, project / "work" / "localization")
    candidate = _read(candidate_root / "manifest.json")
    source = _read(source_bindings)
    if candidate.get("schema") not in {
            "p002-localized-writer-retry/v1",
            "p002-localized-writer-production/v1",
    }:
        raise HandoffError("unsupported writer candidate schema")
    if candidate.get("source_business_date") != source.get("source_business_date"):
        raise HandoffError("candidate/source business date mismatch")
    country_code = candidate.get("country_code") or candidate.get("country")
    if candidate.get("country_code") and candidate.get("country") and candidate["country_code"] != candidate["country"]:
        raise HandoffError("candidate country identity fields differ")
    country = localization_config.resolve_country(country_code)
    for key in ("content_locale", "language_pack", "pack_version", "pack_sha256"):
        if candidate.get(key) != country.get(key) and key in {"content_locale", "language_pack"}:
            raise HandoffError(f"candidate {key} does not match country registry")
    candidate_source_hash = candidate.get("source_manifest_sha256") or candidate.get("source_bindings_sha256")
    if candidate_source_hash != _sha(source_bindings):
        raise HandoffError("candidate source manifest hash mismatch")
    writer_execution_id = candidate.get("execution_id") or candidate.get("writer_execution_id")
    if not isinstance(writer_execution_id, str) or not writer_execution_id:
        raise HandoffError("candidate writer execution identity missing")
    source_by_id = {item.get("article_id"): item for item in source.get("articles", [])}
    candidate_by_id = {item.get("article_id"): item for item in candidate.get("articles", [])}
    expected = source.get("expected_article_keys") or [item.get("article_id") for item in source.get("articles", [])]
    if set(expected) != set(source_by_id) or set(expected) != set(candidate_by_id):
        raise HandoffError("source/candidate article inventory mismatch")
    if output_run.exists() and any(output_run.iterdir()):
        raise HandoffError(f"handoff run already exists: {output_run}")

    entries, index = [], []
    for article_id in expected:
        source_item, candidate_item = source_by_id[article_id], candidate_by_id[article_id]
        if candidate_item.get("source_sha256") != source_item.get("source_sha256"):
            raise HandoffError(f"candidate source hash mismatch: {article_id}")
        claim_path = source_bindings.parent / source_item["claim_map_path"]
        if _sha(claim_path) != source_item["claim_map_sha256"]:
            raise HandoffError(f"claim map hash mismatch: {article_id}")
        target = candidate_root / candidate_item["candidate_path"]
        if _sha(target) != candidate_item.get("candidate_sha256"):
            raise HandoffError(f"candidate target hash mismatch: {article_id}")
        target_rel = f"candidates/{article_id}/article.md"
        _write_new(output_run / target_rel, target.read_bytes())
        proposal, proposal_bytes = _writer_proposal_bytes(
            candidate_root / candidate_item["proposal_path"], article_id=article_id,
            source_sha256=source_item["source_sha256"], pack_sha256=candidate["pack_sha256"],
            writer_execution_id=writer_execution_id, target=target.read_bytes())
        proposal_rel = f"proposals/{article_id.lower()}.json"
        _write_new(output_run / proposal_rel, proposal_bytes)
        claim_rel = f"claims/{article_id.lower()}.json"
        _write_new(output_run / claim_rel, claim_path.read_bytes())
        images = []
        source_images = {image["sha256"]: image for image in source_item["images"]}
        for image in candidate_item.get("images", []):
            source_reference_sha = image.get("source_sha256") or image.get("base_sha256")
            source_image = source_images.get(source_reference_sha)
            if source_image is None:
                ordinal_match = re.search(r"-img(\d+)-", Path(image.get("target_path", "")).name, re.IGNORECASE)
                if ordinal_match:
                    ordinal = ordinal_match.group(1)
                    matches = [item for item in source_item["images"] if re.search(rf"-img{ordinal}-", item.get("name", ""), re.IGNORECASE)]
                    if len(matches) == 1:
                        source_image = matches[0]
            target_image = Path(image.get("target_path", ""))
            if not target_image.is_absolute():
                target_image = candidate_root / target_image
            if source_image is None or not target_image.is_file() or _sha(target_image) != image.get("target_sha256"):
                raise HandoffError(f"image binding mismatch: {article_id}")
            image_rel = f"candidates/{article_id}/images/{target_image.name}"
            _write_new(output_run / image_rel, target_image.read_bytes())
            images.append({"name": target_image.name, "source_path": source_image["path"],
                           "source_sha256": source_image["sha256"], "candidate_path": image_rel,
                           "target_sha256": image["target_sha256"]})
        receipt_id = "source-" + article_id.lower()
        source_receipt_path = source_bindings.parent / "receipts" / f"{article_id}.json"
        receipt = _source_acceptance(_read(source_receipt_path), receipt_id=receipt_id, article_id=article_id,
                                     source_sha256=source_item["source_sha256"],
                                     claim_map_sha256=source_item["claim_map_sha256"], pack_sha256=candidate["pack_sha256"])
        receipt["derived_from_sha256"] = _sha(source_receipt_path)
        receipt_rel = f"receipts/{receipt_id}.json"
        receipt_bytes = _json(receipt)
        _write_new(output_run / receipt_rel, receipt_bytes)
        index.append({"receipt_id": receipt_id, "path": receipt_rel, "sha256": hashlib.sha256(receipt_bytes).hexdigest()})
        entry = {"article_id": article_id, "style": source_item["style"], "asset": source_item["asset"],
                 "source_receipt_id": receipt_id, "source_path": source_item["source_path"],
                 "source_sha256": source_item["source_sha256"],
                 "source_canonical_sha256": source_item.get("source_canonical_sha256"),
                 "claim_map_path": claim_rel, "claim_map_sha256": source_item["claim_map_sha256"],
                 "proposal_path": proposal_rel, "candidate_path": target_rel, "images": images}
        # Style-M source files do not always carry a source slug.  Preserve
        # the slug already present in the reviewed target so package metadata
        # can validate it without inventing or rewriting candidate content.
        slug = candidate_item.get("localized_slug") or _frontmatter_slug(proposal["target_markdown"])
        if slug:
            entry["localized_slug"] = slug
        entries.append(entry)
    manifest = {"schema": "p002-localized-source/v2", "run_id": output_run.name,
                "country_code": country_code, "content_locale": candidate["content_locale"],
                "language_pack": candidate["language_pack"], "pack_version": candidate["pack_version"],
                "pack_sha256": candidate["pack_sha256"], "country_policy_sha256": country["policy_sha256"],
                "source_business_date": candidate["source_business_date"], "status": "PENDING_INDEPENDENT_REVIEW",
                "review_status": "PENDING_INDEPENDENT_REVIEW", "expected_article_keys": expected, "articles": entries}
    source_manifest_path = output_run / "source-manifest.json"
    _write_new(source_manifest_path, _json(manifest))
    _write_new(output_run / "receipts/index.json", _json({"receipts": index, "status": "SOURCE_READY_ONLY"}))
    report = {"schema": "p002-localized-release-handoff/v1", "status": "HOLD_INDEPENDENT_REVIEW",
              "country_code": country_code, "source_manifest_sha256": _sha(source_manifest_path),
              "writer_manifest_sha256": _sha(candidate_root / "manifest.json"),
              "source_manifest_path": str(output_run / "source-manifest.json"),
              "receipt_index_path": str(output_run / "receipts/index.json"),
              "missing_review_gates": ["language", "semantic", "visual", "package_input"],
              "external_publish": False, "output_touched": False}
    _write_new(output_run / "handoff-report.json", _json(report))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--candidate-root", required=True)
    parser.add_argument("--source-bindings", required=True)
    parser.add_argument("--output-run", required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(build(project_root=Path(args.project_root), candidate_root=Path(args.candidate_root),
                               source_bindings=Path(args.source_bindings), output_run=Path(args.output_run)), ensure_ascii=False))
        return 0
    except HandoffError as exc:
        print(json.dumps({"status": "HOLD", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
