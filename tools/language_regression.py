"""Deterministic corpus-level language regression gates for the shadow pilot."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

CONNECTORS = ("อย่างไรก็ตาม", "ในขณะเดียวกัน", "โดยสรุป", "ทั้งนี้", "กล่าวโดยสรุป")
ROBOTIC_PHRASES = ("จากข้อมูลดังกล่าว", "ในภาพรวมของตลาด", "สิ่งที่ควรจับตาในระยะถัดไป")


def _prose_lines(text: str) -> list[str]:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "|", "!", "---")):
            continue
        lines.append(re.sub(r"\s+", " ", stripped))
    return lines


def _ngrams(text: str, size: int = 4) -> Counter[str]:
    words = re.findall(r"[\u0E00-\u0E7F\w]+", text.lower())
    return Counter(" ".join(words[i:i + size]) for i in range(max(0, len(words) - size + 1)))


def analyze_corpus(documents: list[dict], *, max_opening_repeat: int = 3,
                   max_connector_rate_per_1000: int = 18,
                   max_cross_article_ngram_repeat: int = 4) -> dict:
    """Return explainable findings; documents have id, text, and optional style_profile."""
    if not isinstance(documents, list) or not documents:
        raise ValueError("documents must be non-empty")
    normalized = []
    for item in documents:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("text"), str):
            raise ValueError("each document needs id/text")
        normalized.append(item)
    findings = []
    openings = Counter()
    connector_count = 0
    total_words = 0
    all_ngrams = Counter()
    for item in normalized:
        lines = _prose_lines(item["text"])
        opening = lines[0] if lines else ""
        if opening:
            openings[opening] += 1
        connector_count += sum(item["text"].count(term) for term in CONNECTORS)
        total_words += len(re.findall(r"[\u0E00-\u0E7F\w]+", item["text"]))
        all_ngrams.update(_ngrams(item["text"]))
        for phrase in ROBOTIC_PHRASES:
            if phrase in item["text"]:
                findings.append({"code": "ROBOTIC_PHRASE", "severity": "warning", "document_id": item["id"], "phrase": phrase})
    for opening, count in openings.items():
        if count > max_opening_repeat:
            findings.append({"code": "OPENING_REPETITION", "severity": "warning", "opening": opening, "count": count})
    rate = (connector_count * 1000 / total_words) if total_words else 0.0
    if rate > max_connector_rate_per_1000:
        findings.append({"code": "CONNECTOR_DENSITY", "severity": "warning", "rate_per_1000_words": round(rate, 2), "count": connector_count})
    repeated = [(gram, count) for gram, count in all_ngrams.items() if count > max_cross_article_ngram_repeat and len(gram) >= 20]
    for gram, count in sorted(repeated, key=lambda x: (-x[1], x[0]))[:25]:
        findings.append({"code": "CROSS_ARTICLE_NGRAM", "severity": "info", "ngram": gram, "count": count})
    return {"schema": "language-regression-v1", "documents": len(normalized), "metrics": {"opening_unique": len(openings), "connector_count": connector_count, "connector_rate_per_1000_words": round(rate, 2), "cross_article_ngrams": len(repeated)}, "findings": findings, "passed": not any(x["severity"] == "warning" for x in findings)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P002 corpus language regression gate")
    parser.add_argument("manifest", help="JSON array or object with documents")
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    payload = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    documents = payload["documents"] if isinstance(payload, dict) else payload
    result = analyze_corpus(documents)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
