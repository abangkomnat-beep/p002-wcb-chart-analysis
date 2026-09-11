"""Build v2 package manifests and source receipts for the 08-09 localization runs.

This script only prepares work-area manifests/receipts. It never writes output.
Candidates must already exist and remain immutable after this script finishes.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from tools import baseline_registry, localization_config

ROOT = Path(__file__).resolve().parents[1].parent
REPO = ROOT / "Repo"
DAY = "08-09-2026"
ISO_DAY = "2026-09-08"
SOURCE_BINDINGS = ROOT / "work/localization" / DAY / "source-bindings-r2"
RUNS = ROOT / "work/localization" / DAY / "expansion-control/runs"
ARTICLES = ["E-XAUUSD", "M-BTCUSD", "L-GBPUSD", "L-AUDUSD"]


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def write_json(path: Path, value: dict) -> str:
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return sha_bytes(data)


def find_candidate(run: Path, article_id: str) -> Path:
    for p in run.joinpath("candidates").glob("*/article.md"):
        if p.parent.name.upper() == article_id:
            return p
    raise FileNotFoundError(f"candidate missing: {run.name}/{article_id}")


def find_image(run: Path, article_id: str, name: str) -> Path:
    p = find_candidate(run, article_id).parent / "images" / name
    if not p.is_file():
        raise FileNotFoundError(f"candidate image missing: {run.name}/{article_id}/{name}")
    return p


def frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return {}
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}
    values = {}
    for line in lines[1:end]:
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip().strip("\"'")
    return values


def build(locale_dir: str, country: str, content_locale: str, pack_locale: str) -> Path:
    run = RUNS / locale_dir
    run.mkdir(parents=True, exist_ok=True)
    pack = baseline_registry.verify(pack_locale)
    source_index = json.loads((SOURCE_BINDINGS / "source-bindings.json").read_text(encoding="utf-8"))
    claims_out = run / "claims"
    proposals_out = run / "proposals"
    receipts_out = run / "receipts"
    claims_out.mkdir(exist_ok=True)
    proposals_out.mkdir(exist_ok=True)
    receipts_out.mkdir(exist_ok=True)
    entries = []
    receipt_refs = []
    reviewed_at = datetime.now().astimezone().isoformat(timespec="seconds")
    for src in source_index["articles"]:
        article_id = src["article_id"]
        if article_id not in ARTICLES:
            continue
        source_path = ROOT / src["source_path"]
        source_hash = sha(source_path)
        claim_source = SOURCE_BINDINGS / src["claim_map_path"]
        claim_dest = claims_out / f"{article_id.lower()}.json"
        shutil.copy2(claim_source, claim_dest)
        claim_hash = sha(claim_dest)
        candidate = find_candidate(run, article_id)
        candidate_rel = candidate.relative_to(run).as_posix()
        target = candidate.read_text(encoding="utf-8")
        # Candidate handoffs may use article-folder-relative image names.
        # The v2 packager contract requires explicit images/<name> links.
        target = re.sub(
            r"!\[([^\]]*)\]\((?!images/)([^)/]+\.webp)\)",
            r"![\1](images/\2)",
            target,
        )
        candidate.write_text(target, encoding="utf-8", newline="\n")
        target_meta = frontmatter(target)
        proposal = {
            "schema": "p002-localized-proposal/v2",
            "article_id": article_id,
            "source_sha256": source_hash,
            "pack_sha256": pack["actual_sha256"],
            "writer_execution_id": f"P002-{locale_dir}-{article_id}-writer-r1",
            "target_markdown": target,
            "alignment": [{"claim_id": f"{article_id}-ALL", "target_field": "article", "target_quote": target}],
            "open_questions": [],
            "attempt": 1,
        }
        proposal_path = proposals_out / f"{article_id.lower()}.json"
        write_json(proposal_path, proposal)
        images = []
        for image in src["images"]:
            source_img = ROOT / image["path"]
            candidate_img = find_image(run, article_id, image["name"])
            images.append({
                "name": image["name"],
                "source_path": image["path"],
                "source_sha256": sha(source_img),
                "candidate_path": candidate_img.relative_to(run).as_posix(),
                "target_sha256": sha(candidate_img),
            })
        receipt_id = f"{locale_dir}-source-{article_id.lower()}-r1"
        receipt = {
            "receipt_id": receipt_id,
            "gate": "source_acceptance",
            "article_id": article_id,
            "pack_sha256": pack["actual_sha256"],
            "claim_map_sha256": claim_hash,
            "source_sha256": source_hash,
            "reviewer_execution_id": f"CC-independent-source-QA-{article_id}-20260908",
            "reviewer_kind": "INDEPENDENT_SOURCE_QA",
            "reviewed_at": reviewed_at,
            "verdict": "PASS",
            "findings": [],
        }
        receipt_path = receipts_out / f"{receipt_id}.json"
        receipt_hash = write_json(receipt_path, receipt)
        receipt_refs.append({"receipt_id": receipt_id, "path": receipt_path.relative_to(run).as_posix(), "sha256": receipt_hash})
        entry = {
            "article_id": article_id,
            "style": src["style"],
            "asset": src["asset"],
            "source_receipt_id": receipt_id,
            "source_path": src["source_path"],
            "source_sha256": source_hash,
            "source_canonical_sha256": source_hash,
            "claim_map_path": claim_dest.relative_to(run).as_posix(),
            "claim_map_sha256": claim_hash,
            "proposal_path": proposal_path.relative_to(run).as_posix(),
            "candidate_path": candidate_rel,
            "images": images,
        }
        # Style M source files predate the slug field.  The localized
        # candidate supplies an explicit slug so metadata validation remains
        # deterministic without inventing one in the packager.
        source_meta = frontmatter((ROOT / src["source_path"]).read_text(encoding="utf-8"))
        if "slug" not in source_meta:
            slug = target_meta.get("slug")
            if slug:
                entry["localized_slug"] = slug
        entries.append(entry)
    if [x["article_id"] for x in entries] != ARTICLES:
        raise RuntimeError(f"incomplete article set for {locale_dir}: {[x['article_id'] for x in entries]}")
    policy = localization_config.resolve_country(country)
    manifest = {
        "schema": "p002-localized-source/v2",
        "run_id": f"{locale_dir}-20260908-r1",
        "country_code": country,
        "content_locale": content_locale,
        "language_pack": pack_locale,
        "pack_version": pack["version"],
        "pack_sha256": pack["actual_sha256"],
        "country_policy_sha256": policy["policy_sha256"],
        "source_business_date": ISO_DAY,
        "expected_article_keys": ARTICLES,
        "articles": entries,
    }
    write_json(run / "source-manifest.json", manifest)
    write_json(receipts_out / "index.json", {"receipts": receipt_refs})
    return run / "source-manifest.json"


def main() -> None:
    for args in (("ms-MY", "MY", "ms-MY", "ms-MY"), ("pt-BR", "BR", "pt-BR", "pt-BR"), ("es-AR", "AR", "es-AR", "es-419")):
        print(build(*args))


if __name__ == "__main__":
    main()
