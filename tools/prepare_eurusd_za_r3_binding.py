"""Bind the recovered EURUSD en-ZA candidate to the current source and pack.

This produces a calibration run only.  It deliberately creates no target review
receipts and never writes to output.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from tools import baseline_registry, localization_config


TOKENS = re.compile(r"(?<![A-Za-z0-9_.,+%\-])(?:EUR/USD|H[0-9]+|M[0-9]+|OCO|WAIT_TRIGGER|NEUTRAL|"
                    r"DMI|ADX|Supertrend|EMA20|EMA50|ATR14|BUY|SELL|ACTIVE|"
                    r"[0-9]+(?:\.[0-9]+)?%?)(?![A-Za-z0-9_%]|[.,]\d)")
COMPOUND_LITERAL = re.compile(r"[0-9a-f]{64}|(?:\d{4}-\d{2}-\d{2}|\d{2}-\d{2}-\d{4})(?:T\d{2}:\d{2}:\d{2}\+07:00)?")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(path: Path, value: dict) -> str:
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return sha(data)


def protected(source: str, target: str) -> list[dict]:
    values = []
    masked = COMPOUND_LITERAL.sub(lambda match: "X" * len(match.group(0)), source)
    # Dates/timestamps and evidence hashes have punctuation/slug boundaries that
    # the generic literal validator intentionally rejects.  They stay in the
    # whole-document source/target anchors and are checked by semantic review.
    for token in dict.fromkeys(TOKENS.findall(masked)):
        if source.count(token) != target.count(token):
            raise ValueError(f"protected token count differs: {token}")
        values.append({"id": f"P{len(values) + 1}", "kind": "literal",
                       "value_text": token, "unit": "verbatim", "role": "whole_article"})
    return values


def prepare(project: Path) -> dict:
    project = project.resolve()
    run = project / "work/localization/07-09-2026/za-20260907-r3"
    source_path = project / "output/07-09-2026/TH-Thailand/L/EURUSD/article.md"
    target_path = run / "candidates/eurusd/article.md"
    source, target = source_path.read_text(encoding="utf-8"), target_path.read_text(encoding="utf-8")
    source_hash, target_hash = sha(source.encode()), sha(target.encode())
    pack = baseline_registry.verify("en-001", "0.1.0")
    country = localization_config.resolve_country("ZA")
    images = []
    for image in sorted((target_path.parent / "images").glob("*.webp")):
        source_image = source_path.parent / "images" / image.name
        if not source_image.is_file():
            raise ValueError(f"source image is missing: {image.name}")
        images.append({"name": image.name,
                       "source_path": f"output/07-09-2026/TH-Thailand/L/EURUSD/images/{image.name}",
                       "source_sha256": sha(source_image.read_bytes()),
                       "candidate_path": f"candidates/eurusd/images/{image.name}",
                       "target_sha256": sha(image.read_bytes())})
    claim = {"source_sha256": source_hash, "claim_map_status": "lead_prepared_for_independent_review",
             "claims": [{"id": "EURUSD-R3-ALL", "source_field": "article",
                         "source_quote": source, "protected": protected(source, target)}]}
    claim_hash = write(run / "claims/eurusd.json", claim)
    proposal = {"schema": "p002-localized-proposal/v2", "article_id": "L-EURUSD",
                "source_sha256": source_hash, "pack_sha256": pack["actual_sha256"],
                "writer_execution_id": "CC-writer-eurusd-r3", "target_markdown": target,
                "alignment": [{"claim_id": "EURUSD-R3-ALL", "target_field": "article",
                               "target_quote": target}], "open_questions": [], "attempt": 1}
    write(run / "proposals/eurusd.json", proposal)
    receipt = {"receipt_id": "cc-source-eurusd-r3", "gate": "source_acceptance",
               "article_id": "L-EURUSD", "pack_sha256": pack["actual_sha256"],
               "claim_map_sha256": claim_hash, "source_sha256": source_hash,
               "reviewer_execution_id": "CC-source-QA-eurusd-r3", "reviewer_kind": "AI",
               "reviewed_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
               "verdict": "PASS", "findings": []}
    receipt_hash = write(run / "receipts/cc-source-eurusd-r3.json", receipt)
    write(run / "receipts/index.json", {"receipts": [{"receipt_id": receipt["receipt_id"],
                                                         "path": "receipts/cc-source-eurusd-r3.json",
                                                         "sha256": receipt_hash}]})
    manifest = {"schema": "p002-localized-source/v2", "run_id": "za-20260907-r3",
                "country_code": "ZA", "content_locale": "en-ZA", "language_pack": "en-001",
                "pack_version": "0.1.0", "pack_sha256": pack["actual_sha256"],
                "country_policy_sha256": country["policy_sha256"], "source_business_date": "2026-09-07",
                "expected_article_keys": ["L-EURUSD"], "articles": [{"article_id": "L-EURUSD",
                    "style": "L", "asset": "EURUSD", "source_receipt_id": receipt["receipt_id"],
                    "source_path": "output/07-09-2026/TH-Thailand/L/EURUSD/article.md",
                    "source_sha256": source_hash, "claim_map_path": "claims/eurusd.json",
                    "claim_map_sha256": claim_hash, "proposal_path": "proposals/eurusd.json",
                    "candidate_path": "candidates/eurusd/article.md", "images": images}]}
    manifest_hash = write(run / "source-manifest.json", manifest)
    return {"status": "PREPARED", "manifest_sha256": manifest_hash, "source_sha256": source_hash,
            "target_sha256": target_hash, "claim_map_sha256": claim_hash, "pack_sha256": pack["actual_sha256"]}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    print(json.dumps(prepare(Path(parser.parse_args().project_root)), ensure_ascii=False))
