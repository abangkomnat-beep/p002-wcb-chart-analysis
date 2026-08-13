"""ด่านตรวจบทความก่อนปล่อย — บังคับกฎที่ prompt บังคับไม่ได้

ยกเครื่องตาม WCB Voice Spec v1 (2026-08-03) ตรวจ 8 เรื่อง:
1. ศัพท์ระบบหลุดเข้าเนื้อบทความ (system_term)
2. field ภายในโผล่ใน frontmatter ของบทความสาธารณะ (internal_frontmatter)
3. timestamp แบบเครื่องอ่านและ path ในเครื่อง (machine_timestamp / local_path)
4. คำ robot ตาม denylist 20 รายการของ spec ข้อ 3 (voice_denylist)
5. โครงสร้าง: ห้ามตาราง ห้าม heading อื่นนอกจาก H1 + "ข้อมูลเทคนิค (Technical Analysis)"
   (table_forbidden / heading_forbidden / technical_heading)
6. เลขทุกตัวต้องเท่ากับ round_half_up(ค่าใน evidence ตามกติกาชนิดข้อมูล spec ข้อ 4)
   — ปัดผิด ปัดซ้อน หรือเลขที่ evidence ไม่มี = fail (number_rounding)
7. เพดานความยาว 350-560 คำ (v1.1) ด้วยตัวนับ deterministic ใน voice_rules (word_count)
   — ต่ำกว่าพื้น = fail เช่นกัน เพราะผู้ใช้สั่งให้บทความมีเนื้อหามากกว่าฉบับ v1
8. ครบเครื่องบทความจริง: มี H1 เดียว มีหัวข้อเทคนิคครั้งเดียว (เมื่อ check_completeness)

    python -m tools.public_copy_validator บทความ.md --evidence บทความ.article-data.json

ออกรหัส 1 เมื่อไม่ผ่าน เพื่อให้ขั้นตอน QA ใช้เป็นด่านจริงได้
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import voice_rules  # noqa: E402


VALIDATOR_VERSION = "2.0.0"

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

# ช่องที่ **สัญญากำหนดไว้เองว่าเป็นเวลาแบบเครื่องอ่าน** — เตือนไปก็ไม่มีอะไรให้แก้
#
# กฎ `machine_timestamp_frontmatter` มีไว้จับ "เวลาแบบเครื่องหลุดเข้ามาในช่องที่
# คนอ่านเห็น" แต่ `cutoff_at` เป็นช่องบังคับที่ต้องเป็น ISO อยู่แล้ว ⇒ คำเตือนจึงดัง
# ครบทุกหัวข้อทุกรอบที่รัน · **คำเตือนที่ดังตลอดเวลาเท่ากับไม่ได้เตือน** วันที่มีช่อง
# แปลกปลอมโผล่มาจริงมันจะกลืนหายไปในกองเดิม (พบจากการตรวจกระบวนการ 2026-08-05)
#
# ยกเว้นตามรายชื่อ ไม่ใช่ปิดกฎทั้งข้อ — ช่องอื่นที่มีเวลาแบบเครื่องยังต้องดังเหมือนเดิม
TIMESTAMP_FIELDS_BY_CONTRACT = frozenset({"cutoff_at"})
LOCAL_PATH = re.compile(r"(?:[A-Za-z]:\\|file://|/Users/|/home/|\\\\)")
# จับทั้งทศนิยม เลขมี comma และจำนวนเต็มเปล่า (RSI ฯลฯ) — ตรวจหลังลอกเลขโครงสร้างออกแล้ว
NUMBER = re.compile(r"\d[\d,]*\.\d+|\d{1,3}(?:,\d{3})+|\d+")


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
            # จาก string เก็บเฉพาะรูปทศนิยม/มี comma — ไม่เก็บจำนวนเต็มเปล่า
            # กันเลขใน id/วันที่ (เช่น batch_id) กลายเป็นค่าอ้างอิงราคาโดยไม่ตั้งใจ
            for token in re.findall(r"\d[\d,]*\.\d+|\d{1,3}(?:,\d{3})+", node):
                try:
                    numbers.add(float(token.replace(",", "")))
                except ValueError:
                    pass

    walk(payload)
    return numbers


def _finding(rule: str, severity: str, line: int, detail: str) -> dict:
    return {"rule": rule, "severity": severity, "line": line, "detail": detail}


def _token_matches_evidence(token: str, *, is_percent: bool, instrument_type: str | None,
                            evidence: set[float], ratio_texts: frozenset[str] = frozenset()) -> bool:
    """เลขในบทความถูกต้องก็ต่อเมื่อ "เท่ากับข้อความที่ได้จากการปัดค่าดิบสักค่าใน evidence"

    เทียบเป็น "ข้อความ" ไม่ใช่ตัวเลข เพื่อบังคับรูปแบบไปด้วยในตัว:
    forex ต้อง 4 ตำแหน่ง · BTC ต้องหลักร้อย+comma · % ต้อง 2 ตำแหน่ง · RSI จำนวนเต็ม
    ข้อจำกัดที่รู้: จำนวนเต็มเปล่าเทียบผ่าน format_int กับค่า evidence ใดก็ได้
    จึงหลวมกว่าราคา — แต่ทุกเลขยังต้องชี้กลับค่าจริงใน evidence เสมอ

    `ratio_texts` คือรายการข้อความอัตราส่วนที่ผู้เรียก **ระบุมาทีละค่า** (ผลตอบแทน
    ต่อความเสี่ยงของแผน) — จงใจไม่ให้เป็นกฎรูปแบบทั่วไป เพราะถ้าเปิดให้เลขทศนิยม
    2 ตำแหน่งใดก็ได้ผ่าน ราคาคู่เงินที่พิมพ์ตกทศนิยมจะรอดด่านไปด้วย
    """
    if is_percent:
        return any(voice_rules.format_percent(value) == token for value in evidence)
    if token in ratio_texts:
        return True
    plain_integer = "." not in token and "," not in token
    for value in evidence:
        if voice_rules.format_price(value, instrument_type) == token:
            return True
        if plain_integer and voice_rules.format_int(value) == token:
            return True
    return False


# โปรไฟล์โครงสร้างของสไตล์ตั้งต้น — ใช้เมื่อผู้เรียกไม่ส่ง profile มา
# ทำให้พฤติกรรมเดิมของด่านตรวจไม่เปลี่ยนแม้แต่นิดเดียวเมื่อเพิ่มสไตล์ใหม่เข้ามา
#
# **สิ่งที่ profile เปลี่ยนได้มีแค่โครงสร้าง** คือหัวข้อย่อยกับความยาว
# กฎเนื้อหาทั้งหมด (ตัวเลขต้องตรง evidence · ห้ามศัพท์ระบบ · ห้ามคำ denylist ·
# ห้ามตาราง · ห้ามเวลาแบบเครื่องอ่าน · H1 หัวเดียว) บังคับเท่ากันทุกสไตล์ ไม่มีข้อยกเว้น
DEFAULT_PROFILE = {
    "allow_subheadings": False,
    "require_technical_heading": True,
    "word_min": voice_rules.WORD_MIN,
    "word_max": voice_rules.WORD_MAX,
}


def validate(article_text: str, *, evidence: dict | None = None, instrument_type: str | None = None,
             check_numbers: bool = True, check_completeness: bool = True,
             profile: dict | None = None, ratio_values=None) -> dict:
    profile = {**DEFAULT_PROFILE, **(profile or {})}
    frontmatter, body, offset = split_frontmatter(article_text)
    instrument_type = instrument_type or frontmatter.get("instrument_type") or ""
    evidence_numbers = collect_evidence_numbers(evidence) if evidence else set()
    # อัตราส่วนผลตอบแทนต่อความเสี่ยงเป็น "จำนวนเท่า" ไม่ใช่ราคา จึงปัดคนละกติกา
    # ผู้เรียกต้องส่งค่าที่อนุญาตมาเอง — ด่านนี้ไม่คิดค่าอัตราส่วนขึ้นเองเด็ดขาด
    ratio_texts = frozenset(voice_rules.format_ratio(value) for value in (ratio_values or ()))
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
        if key in TIMESTAMP_FIELDS_BY_CONTRACT:
            continue
        if ISO_TIMESTAMP.search(str(value)):
            findings.append(_finding(
                "machine_timestamp_frontmatter", "warning", 1,
                f"`{key}` เก็บเวลาแบบเครื่องอ่าน — ใช้ได้ในระบบหลังบ้าน แต่ห้ามนำไปแสดงในเนื้อบทความ",
            ))

    h1_count = 0
    technical_heading_count = 0
    for index, line in enumerate(body.splitlines(), start=offset):
        lowered = line.lower()
        stripped_line = line.strip()

        for term in SYSTEM_TERMS:
            if term in lowered:
                findings.append(_finding(
                    "system_term", "fatal", index,
                    f"พบศัพท์ระบบ \"{term}\" ในเนื้อบทความ",
                ))
        # denylist คำ robot 20 รายการ (spec ข้อ 3) — ตรวจแบบ substring
        for term in voice_rules.VOICE_DENYLIST:
            if term in lowered:
                findings.append(_finding(
                    "voice_denylist", "fatal", index,
                    f"พบคำต้องห้ามตาม Voice Spec \"{term}\" ในเนื้อบทความ",
                ))
        # volume มีจริงเฉพาะหุ้น (ใบแจ้งหัวหน้า 2026-08-13) — ชนิดอื่นปลายทางส่ง null
        # ทุกแท่ง จึงไม่มีตัวเลขจริงให้อ้าง · ไม่รู้ชนิด = ห้ามไว้ก่อน (fail-closed)
        if instrument_type not in voice_rules.VOLUME_ALLOWED_INSTRUMENT_TYPES:
            volume_term = voice_rules.volume_term_in(line)
            if volume_term:
                findings.append(_finding(
                    "volume_forbidden", "fatal", index,
                    f"พบคำตระกูล volume \"{volume_term}\" ในบทของชนิด "
                    f"{instrument_type or 'ไม่ระบุ'} — ข้อมูล volume มีจริงเฉพาะหุ้น "
                    "ตลาด OTC ไม่มีตัวเลขให้อ้าง",
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

        # กติกาโครงสร้างของ spec: ห้ามตาราง markdown ทุกกรณี
        if "|" in line:
            findings.append(_finding(
                "table_forbidden", "fatal", index,
                "พบอักขระ | — บทความโครงเล่าเรื่องห้ามมีตาราง markdown",
            ))
        # heading อนุญาตเฉพาะ H1 หัวเดียว + บรรทัด "ข้อมูลเทคนิค (Technical Analysis)"
        if stripped_line.startswith("#"):
            if stripped_line.startswith("##"):
                if not profile["allow_subheadings"]:
                    findings.append(_finding(
                        "heading_forbidden", "fatal", index,
                        f"พบหัวข้อย่อย \"{stripped_line[:40]}\" — โครงเล่าเรื่องไม่มีหัวข้อย่อย",
                    ))
            else:
                h1_count += 1
                if h1_count > 1:
                    findings.append(_finding(
                        "heading_forbidden", "fatal", index,
                        "พบ H1 มากกว่าหนึ่งหัว — บทความมีหัวเรื่องเดียว",
                    ))
        if stripped_line == voice_rules.TECHNICAL_HEADING:
            technical_heading_count += 1

        if check_numbers and evidence_numbers:
            # ลอกเลขเชิงโครงสร้าง (เวลา วันที่ไทย "N วัน") ออกก่อน — เหลือแต่เลขข้อมูลตลาด
            scannable = voice_rules.strip_structural_numbers(line)
            for match in NUMBER.finditer(scannable):
                token = match.group(0)
                is_percent = scannable[match.end():match.end() + 1] == "%"
                if not _token_matches_evidence(
                        token, is_percent=is_percent, instrument_type=instrument_type,
                        evidence=evidence_numbers, ratio_texts=ratio_texts):
                    findings.append(_finding(
                        "number_rounding", "fatal", index,
                        f"\"{token}\" ไม่เท่ากับค่าใดใน evidence เมื่อปัดตามกติกา "
                        f"{instrument_type or 'ไม่ระบุชนิด'} (spec ข้อ 4)",
                    ))

    if check_completeness:
        words = voice_rules.count_public_words(article_text)
        word_min, word_max = profile["word_min"], profile["word_max"]
        if not word_min <= words <= word_max:
            findings.append(_finding(
                "word_count", "fatal", 1,
                f"ความยาว {words} คำ อยู่นอกเพดาน {word_min}-{word_max} "
                f"คำของ spec (ตัวนับ deterministic ใน voice_rules)",
            ))
        if profile["require_technical_heading"] and technical_heading_count != 1:
            findings.append(_finding(
                "technical_heading", "fatal", 1,
                f"หัวข้อ \"{voice_rules.TECHNICAL_HEADING}\" ต้องมีครั้งเดียว "
                f"(พบ {technical_heading_count} ครั้ง)",
            ))
        if h1_count != 1:
            findings.append(_finding(
                "technical_heading", "fatal", 1,
                f"บทความต้องมี H1 หนึ่งหัว (พบ {h1_count})",
            ))

    fatal = [item for item in findings if item["severity"] == "fatal"]
    return {
        "status": "fail" if fatal else "pass",
        "instrument_type": instrument_type or None,
        "findings": findings,
        "fatal_count": len(fatal),
        "word_count": voice_rules.count_public_words(article_text),
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
