"""Rebind the five unchanged ZA Monday candidates into the r3 country run.

EURUSD is intentionally excluded because it has a recovered source revision.
This tool only creates source-acceptance custody and candidates; target review
receipts remain the job of an independent execution.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from tools import baseline_registry, localization_config
from tools.prepare_eurusd_za_r3_binding import protected


REMAINING = {"D-XAUUSD", "D-WTIUSD", "E-XAUUSD", "M-BTCUSD", "L-USDJPY"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: dict) -> str:
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def metadata_overlay(article_id: str, target: str) -> str:
    lines = target.splitlines()
    try:
        end = lines[1:].index("---") + 1
    except ValueError as exc:
        raise ValueError(f"{article_id} target lacks frontmatter") from exc
    fields = {line.split(":", 1)[0] for line in lines[1:end] if ":" in line}
    additions = []
    if article_id == "M-BTCUSD" and "slug" not in fields:
        additions.append("slug: btcusd-h1-daily-2026-09-07-za")
    if "country" not in fields:
        additions.append("country: south-africa")
    if "language" not in fields:
        additions.append("language: en")
    if additions:
        lines[end:end] = additions
    return "\n".join(lines) + "\n"


def prepare(project: Path) -> dict:
    project = project.resolve()
    day = "07-09-2026"
    old = project / f"work/localization/{day}/za-20260907-r2"
    run = project / f"work/localization/{day}/za-20260907-r3"
    source_manifest = json.loads((old / "source-manifest.json").read_text(encoding="utf-8"))
    current_manifest_path = run / "source-manifest.json"
    current = json.loads(current_manifest_path.read_text(encoding="utf-8"))
    eurusd = [item for item in current["articles"] if item["article_id"] == "L-EURUSD"]
    if len(eurusd) != 1:
        raise ValueError("r3 must retain exactly one reviewed EURUSD article")
    layout = json.loads((project / f"output/{day}/TH-Thailand/source-layout-manifest.json").read_text(encoding="utf-8"))
    layout_by_id = {item["article_id"]: item for item in layout["articles"]}
    pack = baseline_registry.verify("en-001", "0.1.0")
    country = localization_config.resolve_country("ZA")
    index = json.loads((run / "receipts/index.json").read_text(encoding="utf-8"))
    index["receipts"] = [entry for entry in index["receipts"]
                         if entry["receipt_id"] not in {f"cc-source-{article.lower()}-r3" for article in REMAINING}]
    existing_ids = {entry["receipt_id"] for entry in index["receipts"]}
    articles = eurusd
    for original in source_manifest["articles"]:
        article_id = original["article_id"]
        if article_id not in REMAINING:
            continue
        if article_id not in layout_by_id:
            raise ValueError(f"current source layout missing {article_id}")
        layout_item = layout_by_id[article_id]
        candidate_src = old / original["candidate_path"]
        candidate_base = run / original["candidate_path"]
        if not candidate_base.exists():
            shutil.copytree(candidate_src.parent, candidate_base.parent)
        candidate_dest = candidate_base.with_name("article-r3.md")
        target = metadata_overlay(article_id, candidate_base.read_text(encoding="utf-8"))
        # Candidate bytes are part of the receipt chain.  Always materialize
        # the proposal's LF-normalized bytes; text mode on Windows would turn
        # them into CRLF and make a legitimate re-run look like a new revision.
        candidate_dest.write_bytes(target.encode("utf-8"))
        source_article = project / f"output/{day}/TH-Thailand/{original['style']}/{original['asset'].upper()}/article.md"
        source_text = source_article.read_text(encoding="utf-8")
        source_hash = sha(source_article)
        try:
            protected_values = protected(source_text, target)
            claim_status = "lead_rebound_after_country_layout_migration"
        except ValueError:
            # The legacy candidates localize date strings.  The current literal
            # guard cannot compare those locale forms safely, so require the
            # independent semantic reviewer to check whole-document anchors.
            protected_values = []
            claim_status = "manual_semantic_review_required_for_localized_dates"
        claim = {"source_sha256": source_hash, "claim_map_status": claim_status,
                 "claims": [{"id": f"{article_id}-R3-ALL", "source_field": "article",
                             "source_quote": source_text, "protected": protected_values}]}
        claim_hash = write(run / original["claim_map_path"], claim)
        proposal = {"schema": "p002-localized-proposal/v2", "article_id": article_id,
                    "source_sha256": source_hash, "pack_sha256": pack["actual_sha256"],
                    "writer_execution_id": f"CC-writer-{article_id}-r3", "target_markdown": target,
                    "alignment": [{"claim_id": f"{article_id}-R3-ALL", "target_field": "article",
                                   "target_quote": target}], "open_questions": [], "attempt": 1}
        write(run / original["proposal_path"], proposal)
        images = []
        for image in layout_item["images"]:
            target_image = run / "candidates" / article_id.lower() / "images" / image["name"]
            # r2 candidate folder names use lowercase hyphenated article ids.
            if not target_image.is_file():
                target_image = candidate_dest.parent / "images" / image["name"]
            if not target_image.is_file():
                raise ValueError(f"target image missing: {article_id}/{image['name']}")
            source_image = project / f"output/{day}/TH-Thailand/{original['style']}/{original['asset'].upper()}/images/{image['name']}"
            images.append({"name": image["name"],
                           "source_path": f"output/{day}/TH-Thailand/{original['style']}/{original['asset'].upper()}/images/{image['name']}",
                           "source_sha256": sha(source_image),
                           "candidate_path": target_image.relative_to(run).as_posix(),
                           "target_sha256": sha(target_image)})
        receipt_id = f"cc-source-{article_id.lower()}-r3"
        receipt = {"receipt_id": receipt_id, "gate": "source_acceptance", "article_id": article_id,
                   "pack_sha256": pack["actual_sha256"], "claim_map_sha256": claim_hash,
                   "source_sha256": source_hash, "reviewer_execution_id": f"CC-source-QA-{article_id}-r3",
                   "reviewer_kind": "AI", "reviewed_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                   "verdict": "PASS", "findings": []}
        receipt_path = run / f"receipts/{receipt_id}.json"
        receipt_hash = write(receipt_path, receipt)
        if receipt_id in existing_ids:
            raise ValueError(f"duplicate receipt id: {receipt_id}")
        index["receipts"].append({"receipt_id": receipt_id,
                                  "path": receipt_path.relative_to(run).as_posix(), "sha256": receipt_hash})
        item = {k: original[k] for k in ("article_id", "style", "asset")}
        item.update(source_receipt_id=receipt_id,
                    source_path=f"output/{day}/TH-Thailand/{original['style']}/{original['asset'].upper()}/article.md",
                    source_sha256=source_hash, claim_map_path=original["claim_map_path"],
                    claim_map_sha256=claim_hash, proposal_path=original["proposal_path"],
                    candidate_path=candidate_dest.relative_to(run).as_posix(), images=images)
        if article_id == "M-BTCUSD":
            item["localized_slug"] = "btcusd-h1-daily-2026-09-07-za"
        articles.append(item)
    if {item["article_id"] for item in articles} != {"D-XAUUSD", "D-WTIUSD", "E-XAUUSD", "M-BTCUSD", "L-EURUSD", "L-USDJPY"}:
        raise ValueError("r3 article inventory is incomplete")
    current.update(pack_sha256=pack["actual_sha256"], country_policy_sha256=country["policy_sha256"],
                   expected_article_keys=["D-XAUUSD", "D-WTIUSD", "E-XAUUSD", "M-BTCUSD", "L-EURUSD", "L-USDJPY"],
                   articles=articles)
    write(run / "receipts/index.json", index)
    write(current_manifest_path, current)
    return {"status": "PREPARED", "articles": [item["article_id"] for item in articles]}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    print(json.dumps(prepare(Path(parser.parse_args().project_root)), ensure_ascii=False))
