"""Prepare unreviewed, paragraph-bound source claim maps for localized delivery.

These are source-QA drafts, never receipts. Re-running with unchanged source
bytes is a no-op; changed source bytes create a new revision beside the old
draft so a reviewer can still audit what they read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from tools.daily_source_selector import lanes_for_date

ROOT = Path(__file__).resolve().parents[1]
PARSER_VERSION = "claims-v4-image-aware-semantic-markers"
_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+\.webp)\)", re.IGNORECASE)
_TOKEN = re.compile(r"(?<![\w.])(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|[A-Z][A-Z0-9_/-]{1,})(?![\w.])")
_BOUNDARY = r"(?<![A-Za-z0-9_.,+%\-]){x}(?![A-Za-z0-9_%]|[.,]\d)"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _tokens(text: str) -> list[str]:
    # Keep exactly the same boundary as language_patch.literal_count.  Date
    # fragments (09, 2026) and signed/decimal substrings are not claims.
    values = []
    for token in _TOKEN.findall(text):
        if re.search(_BOUNDARY.format(x=re.escape(token)), text):
            values.append(token)
    return list(dict.fromkeys(values))


def _markers(text: str) -> dict[str, list[str]]:
    lower = text.casefold()
    matches = lambda words: [word for word in words if word.casefold() in lower]
    return {"direction": matches(("ขึ้น", "ลง", "เหนือ", "ต่ำกว่า", "ซื้อ", "ขาย", "up", "down", "above", "below")),
            "condition": matches(("ถ้า", "หาก", "เมื่อ", "ก่อน", "หลัง", "รอ", "เงื่อนไข", "จนกว่า", "ยังไม่", "if", "unless", "when")),
            "certainty": matches(("จะ", "อาจ", "คาด", "น่าจะ", "ยังคง", "จึง", "ต้อง", "ควร", "ห้าม", "ไม่ใช่", "will", "may", "could", "likely"))}


def _blocks(markdown: str) -> list[tuple[str, str]]:
    """Keep textual paragraphs, tables, and each visual reference independently."""
    result: list[tuple[str, str]] = []
    for block in re.split(r"\n\s*\n", markdown.strip()):
        stripped = block.strip()
        if not stripped or stripped == "---" or stripped.startswith("---\n"):
            continue
        images = _IMAGE.findall(stripped)
        image_lines = [line.strip() for line in stripped.splitlines() if _IMAGE.search(line)]
        remaining = _IMAGE.sub("", stripped).strip()
        if remaining:
            kind = "table" if all(line.lstrip().startswith("|") for line in remaining.splitlines()) else "paragraph"
            result.append((kind, remaining))
        result.extend(("image", line) for line in image_lines)
    return result


def _protected(key: str, text: str) -> list[dict]:
    return [{"id": f"{key}-P{ordinal:03d}", "kind": "numeric_literal" if token[0].isdigit() else "symbol",
             "value_text": token, "unit": "verbatim", "role": "source_literal"}
            for ordinal, token in enumerate(_tokens(text), 1)]


def _source_articles(source_business_date: str) -> list[tuple[str, str, Path, bytes]]:
    day_folder = f"{source_business_date[8:10]}-{source_business_date[5:7]}-{source_business_date[:4]}"
    entries = []
    for style, asset, *_ in lanes_for_date(source_business_date):
        directory = ROOT.parent / "output" / day_folder / "TH-Thailand" / style / asset
        candidates = sorted(directory.glob("*-article.md"))
        if len(candidates) != 1:
            raise RuntimeError(f"expected one migrated article for {style}-{asset}: {directory}")
        article = candidates[0]
        entries.append((style, asset, article, article.read_bytes()))
    return entries


def _image_fingerprint(article: Path) -> str:
    images = sorted(article.parent.glob("*.webp"))
    payload = "\n".join(f"{image.name}:{_sha(image.read_bytes())}" for image in images).encode("utf-8")
    return _sha(payload)


def _choose_run(base: Path, articles: list[tuple[str, str, Path, bytes]]) -> tuple[Path, bool]:
    hashes = {f"{style}-{asset}": {"article": _sha(raw),
                                  "images": _image_fingerprint(article)}
              for style, asset, article, raw in articles}
    existing = base / "source-bindings.json"
    if existing.is_file():
        try:
            prior = json.loads(existing.read_text(encoding="utf-8"))
            prior_hashes = {entry["article_id"]: {
                "article": entry.get("source_sha256"),
                "images": entry.get("source_images_sha256"),
            } for entry in prior.get("articles", [])}
            if (prior.get("schema") == "p002-source-bindings/v2"
                    and prior.get("parser_version") == PARSER_VERSION
                    and prior_hashes == hashes):
                return base, True
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            pass
    revision = 2
    while (base.parent / f"{base.name}-r{revision:04d}").exists():
        revision += 1
    return (base if not existing.exists() else base.parent / f"{base.name}-r{revision:04d}"), False


def prepare(source_business_date: str) -> Path:
    day_folder = f"{source_business_date[8:10]}-{source_business_date[5:7]}-{source_business_date[:4]}"
    articles = _source_articles(source_business_date)
    base = ROOT.parent / "work" / "localization" / day_folder / "source-bindings"
    run, unchanged = _choose_run(base, articles)
    if unchanged:
        return run
    claims_dir = run / "claims"
    entries = []
    for style, asset, article, raw in articles:
        text = raw.decode("utf-8")
        key = f"{style}-{asset}"
        referenced = [Path(name).name for name in _IMAGE.findall(text)]
        inventory = sorted(article.parent.glob("*.webp"))
        inventory_names = [image.name for image in inventory]
        if len(referenced) != len(set(referenced)) or sorted(referenced) != inventory_names:
            raise RuntimeError(f"image inventory does not match Markdown references: {key}")
        claims = []
        for ordinal, (kind, quote) in enumerate(_blocks(text), 1):
            claim_id = f"{key}-C{ordinal:03d}"
            claims.append({"id": claim_id, "source_field": kind, "source_quote": quote,
                           "protected": _protected(claim_id, quote), "semantic_markers": _markers(quote)})
        if not claims:
            raise RuntimeError(f"no claim blocks found in {key}")
        claim = {"schema": "p002-source-claim-map/v2", "article_id": key, "source_sha256": _sha(raw),
                 "claim_map_status": "lead_prepared_for_independent_review", "claims": claims}
        claim_path = claims_dir / f"{key.casefold()}.json"
        _write(claim_path, claim)
        images = [{"name": image.name, "path": image.relative_to(ROOT.parent).as_posix(),
                   "sha256": _sha(image.read_bytes()), "bytes": image.stat().st_size} for image in inventory]
        entries.append({"article_id": key, "style": style, "asset": asset,
                        "source_path": article.relative_to(ROOT.parent).as_posix(), "source_sha256": _sha(raw),
                        "source_images_sha256": _image_fingerprint(article),
                        "source_canonical_sha256": _sha(raw), "claim_map_path": claim_path.relative_to(run).as_posix(),
                        "claim_map_sha256": _sha(claim_path.read_bytes()), "images": images})
    manifest = {"schema": "p002-source-bindings/v2", "parser_version": PARSER_VERSION,
                "source_business_date": source_business_date,
                "source_locale": "th-TH", "status": "HOLD",
                "reason": "claim maps require independent source acceptance review", "articles": entries}
    _write(run / "source-bindings.json", manifest)
    return run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    print(prepare(args.date))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
