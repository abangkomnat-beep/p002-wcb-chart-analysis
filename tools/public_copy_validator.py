"""ด่านตรวจบทความก่อนปล่อย — บังคับกฎที่ prompt บังคับไม่ได้

ตรวจ 5 เรื่อง:
1. ศัพท์ระบบหลุดเข้าเนื้อบทความ
2. field ภายในโผล่ใน frontmatter ของบทความสาธารณะ
3. timestamp แบบเครื่องอ่านและ path ในเครื่อง
4. จำนวนทศนิยมเกินที่กำหนดต่อชนิดสินทรัพย์
5. ตัวเลขในบทความที่หาไม่เจอในหลักฐาน (article-data.json)

    python -m tools.public_copy_validator บทความ.md --evidence บทความ.article-data.json

ออกรหัส 1 เมื่อไม่ผ่าน เพื่อให้ขั้นตอน QA ใช้เป็นด่านจริงได้
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


VALIDATOR_VERSION = "1.0.0"

# คำที่เป็นภาษาของระบบ ไม่ใช่ภาษาที่ผู้อ่านควรเห็น
SYSTEM_TERMS = (
    "locked_snapshot", "locked snapshot", "approved_level_sources", "qa_status",
    "publication_clearance", "missing_fields", "unavailable", "data_status",
    "hold-data-license-review", "hold-data-mismatch", "hold-data-quality",
    "hold-content-qa", "provider_only", "insufficient_data", "publication_gate",
    "calculation_owner", "basis_candle_state", "is_expected_session",
    "approved_for_publication", "snapshot.json", "article-data", "source_log",
)

# field ที่บทความสาธารณะต้องมี ตาม input gate ของ Output Contract
REQUIRED_PUBLIC_FRONTMATTER = ("title", "symbol", "instrument_type", "timezone")

# field ที่ต้องอยู่ใน meta.json ไม่ใช่หัวบทความ
INTERNAL_FRONTMATTER_KEYS = (
    "data_status", "qa_status", "publication_clearance", "missing_fields",
    "approved_level_sources", "source_log", "reviewer", "status", "snapshot",
    "baseline_article", "comparison_group",
)

ISO_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?")
LOCAL_PATH = re.compile(r"(?:[A-Za-z]:\\|file://|/Users/|/home/|\\\\)")
NUMBER = re.compile(r"\d[\d,]*\.\d+|\d{1,3}(?:,\d{3})+")

# ทศนิยมสูงสุดที่แสดงต่อผู้อ่านได้ต่อชนิดสินทรัพย์
PUBLIC_PRECISION = {
    "spot": 2,
    "spot_metal": 2,
    "crypto_spot": 2,
    "thai_gold_96_5": 2,
    "forex_spot": 5,
    "futures": 2,
}
PERCENT_PRECISION = 2
DEFAULT_PRECISION = 2


def split_frontmatter(article: str) -> tuple[dict, str, int]:
    """คืน (frontmatter, เนื้อบทความ, เลขบรรทัดที่เนื้อเริ่ม)"""
    if not article.startswith("---"):
        return {}, article, 1
    parts = article.split("---", 2)
    if len(parts) < 3:
        return {}, article, 1
    block, body = parts[1], parts[2]
    frontmatter = {}
    for line in block.splitlines():
        name, separator, value = line.partition(":")
        if separator and not name.startswith(" "):
            frontmatter[name.strip()] = value.strip().strip("\"'")
    offset = len(block.splitlines()) + 2
    return frontmatter, body, offset


def collect_evidence_numbers(payload) -> set[float]:
    numbers: set[float] = set()

    def walk(node):
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, bool):
            return
        elif isinstance(node, (int, float)):
            numbers.add(float(node))
        elif isinstance(node, str):
            for token in NUMBER.findall(node):
                try:
                    numbers.add(float(token.replace(",", "")))
                except ValueError:
                    pass

    walk(payload)
    return numbers


def _finding(rule: str, severity: str, line: int, detail: str) -> dict:
    return {"rule": rule, "severity": severity, "line": line, "detail": detail}


def _decimals(token: str) -> int:
    return len(token.split(".")[1]) if "." in token else 0


def _matches_evidence(value: float, decimals: int, evidence: set[float]) -> bool:
    tolerance = 0.5 * (10 ** -decimals) + 1e-9
    return any(abs(candidate - value) <= tolerance for candidate in evidence)


def validate(article_text: str, *, evidence: dict | None = None, instrument_type: str | None = None,
             check_numbers: bool = True) -> dict:
    frontmatter, body, offset = split_frontmatter(article_text)
    instrument_type = instrument_type or frontmatter.get("instrument_type") or ""
    max_decimals = PUBLIC_PRECISION.get(instrument_type, DEFAULT_PRECISION)
    evidence_numbers = collect_evidence_numbers(evidence) if evidence else set()
    findings: list[dict] = []

    for key in REQUIRED_PUBLIC_FRONTMATTER:
        if not frontmatter.get(key):
            findings.append(_finding(
                "contract_field_missing", "fatal", 1,
                f"หัวบทความขาด `{key}` ซึ่ง input gate ของ contract บังคับไว้",
            ))

    for key in INTERNAL_FRONTMATTER_KEYS:
        if key in frontmatter:
            findings.append(_finding(
                "internal_frontmatter", "fatal", 1,
                f"`{key}` เป็นข้อมูลภายใน ต้องย้ายไปไฟล์ meta.json ไม่ใช่หัวบทความ",
            ))

    for key, value in frontmatter.items():
        if ISO_TIMESTAMP.search(str(value)):
            findings.append(_finding(
                "machine_timestamp_frontmatter", "warning", 1,
                f"`{key}` เก็บเวลาแบบเครื่องอ่าน — ใช้ได้ในระบบหลังบ้าน แต่ห้ามนำไปแสดงในเนื้อบทความ",
            ))

    for index, line in enumerate(body.splitlines(), start=offset):
        lowered = line.lower()
        for term in SYSTEM_TERMS:
            if term in lowered:
                findings.append(_finding(
                    "system_term", "fatal", index,
                    f"พบศัพท์ระบบ \"{term}\" ในเนื้อบทความ",
                ))
        for match in ISO_TIMESTAMP.finditer(line):
            findings.append(_finding(
                "machine_timestamp", "fatal", index,
                f"เวลาแบบเครื่องอ่าน \"{match.group(0)}\" ต้องเปลี่ยนเป็นเวลาที่คนอ่านเข้าใจ",
            ))
        if LOCAL_PATH.search(line):
            findings.append(_finding(
                "local_path", "fatal", index, "พบ path ในเครื่องหรือ URL ระบบไฟล์",
            ))

        for match in NUMBER.finditer(line):
            token = match.group(0)
            decimals = _decimals(token)
            try:
                value = float(token.replace(",", ""))
            except ValueError:
                continue
            is_percent = line[match.end():match.end() + 1] == "%"
            allowed = PERCENT_PRECISION if is_percent else max_decimals
            if decimals > allowed:
                findings.append(_finding(
                    "precision", "fatal", index,
                    f"\"{token}\" มีทศนิยม {decimals} ตำแหน่ง เกินที่กำหนดไว้ {allowed}",
                ))
            if check_numbers and evidence_numbers and not _matches_evidence(value, decimals, evidence_numbers):
                findings.append(_finding(
                    "number_without_evidence", "fatal", index,
                    f"\"{token}\" ไม่ตรงกับค่าใดในหลักฐาน",
                ))

    fatal = [item for item in findings if item["severity"] == "fatal"]
    return {
        "status": "fail" if fatal else "pass",
        "instrument_type": instrument_type or None,
        "max_decimals": max_decimals,
        "findings": findings,
        "fatal_count": len(fatal),
        "validator_version": VALIDATOR_VERSION,
    }


def format_report(result: dict, article_path: Path) -> str:
    lines = [f"{article_path.name}: {result['status'].upper()} ({result['fatal_count']} ข้อร้ายแรง)"]
    for item in result["findings"]:
        lines.append(f"  บรรทัด {item['line']} [{item['rule']}] {item['detail']}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("article", type=Path)
    parser.add_argument("--evidence", type=Path, help="ไฟล์ article-data.json ที่ใช้ตรวจตัวเลข")
    parser.add_argument("--instrument-type", help="ระบุเองเมื่อ frontmatter ไม่มี")
    parser.add_argument("--skip-number-check", action="store_true")
    parser.add_argument("--json", action="store_true", help="พิมพ์ผลเป็น JSON")
    args = parser.parse_args()

    evidence = json.loads(args.evidence.read_text(encoding="utf-8")) if args.evidence else None
    result = validate(
        args.article.read_text(encoding="utf-8"),
        evidence=evidence,
        instrument_type=args.instrument_type,
        check_numbers=not args.skip_number_check,
    )

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json
          else format_report(result, args.article))
    return 1 if result["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
