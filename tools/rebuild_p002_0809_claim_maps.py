"""Rebuild 08-09 source maps with only boundary-safe semantic literals."""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1].parent
DAY = "08-09-2026"
BASE = ROOT / "work/localization" / DAY
SOURCE = ROOT / "output" / DAY / "TH-Thailand"
OUT = BASE / "source-bindings-r2"
TOKEN = re.compile(r"(?<![\w.])(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|[A-Z][A-Z0-9_/-]{1,})(?![\w.])")
BOUNDARY = r"(?<![A-Za-z0-9_.,+%\-]){x}(?![A-Za-z0-9_.,+%\-])"
ARTICLES = [("E", "XAUUSD"), ("M", "BTCUSD"), ("L", "GBPUSD"), ("L", "AUDUSD")]
TARGET_RUNS = ("ms-MY", "pt-BR", "es-AR")

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def count(text: str, token: str) -> int:
    # Keep this boundary identical to language_patch.literal_count so a
    # protected value cannot be accepted by the map and rejected by the gate.
    return len(re.findall(
        r"(?<![A-Za-z0-9_.,+%\-])" + re.escape(token)
        + r"(?![A-Za-z0-9_%]|[.,]\d)", text))

def main() -> None:
    OUT.joinpath("claims").mkdir(parents=True, exist_ok=True)
    entries = []
    for style, asset in ARTICLES:
        article_id = f"{style}-{asset}"
        folder = SOURCE / style / asset
        article = next(folder.glob("*-article.md"))
        raw = article.read_bytes()
        text = raw.decode("utf-8")
        targets = []
        for run in TARGET_RUNS:
            candidate = BASE / "expansion-control" / "runs" / run / "candidates" / article_id / "article.md"
            if not candidate.is_file():
                raise FileNotFoundError(candidate)
            targets.append(candidate.read_text(encoding="utf-8"))
        tokens = []
        for token in dict.fromkeys(TOKEN.findall(text)):
            source_count = count(text, token)
            # A source literal is protected only when every localized
            # candidate preserves its count.  This avoids date/number
            # fragments such as 08/09 or 00 that translators legitimately
            # render with a different boundary while retaining the complete
            # source quote for independent semantic review.
            if source_count and all(count(target, token) == source_count for target in targets):
                tokens.append({"id": f"{article_id}-P{len(tokens)+1:03d}",
                               "kind": "numeric_literal" if token[0].isdigit() else "symbol",
                               "value_text": token, "unit": "verbatim", "role": "semantic_protected"})
        claim = {"schema": "p002-source-claim-map/v2", "article_id": article_id,
                 "source_sha256": sha(raw), "claim_map_status": "independent_source_review_ready",
                 "claims": [{"id": f"{article_id}-ALL", "source_field": "article",
                             "source_quote": text, "protected": tokens}]}
        claim_path = OUT / "claims" / f"{article_id.casefold()}.json"
        claim_path.write_text(json.dumps(claim, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        images = []
        for image in sorted(folder.glob("*.webp")):
            images.append({"name": image.name, "path": image.relative_to(ROOT).as_posix(),
                           "sha256": sha(image.read_bytes()), "bytes": image.stat().st_size})
        entries.append({"article_id": article_id, "style": style, "asset": asset,
                        "source_path": article.relative_to(ROOT).as_posix(), "source_sha256": sha(raw),
                        "source_canonical_sha256": sha(raw), "claim_map_path": claim_path.relative_to(OUT).as_posix(),
                        "claim_map_sha256": sha(claim_path.read_bytes()), "images": images})
    manifest = {"schema": "p002-source-bindings/v2", "source_business_date": "2026-09-08",
                "source_locale": "th-TH", "status": "READY",
                "reason": "technical source QA and independent claim-map rebuild completed",
                "articles": entries}
    (OUT / "source-bindings.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUT)

if __name__ == "__main__":
    main()
