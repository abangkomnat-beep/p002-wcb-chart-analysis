"""แก้ภาษาแบบเจาะจุด + ด่านตรวจว่าความหมายไม่เปลี่ยน

## กฎเดียวที่เครื่องมือนี้บังคับ

    อนุมัติ 3 จุด = แก้ 3 จุด
    ไม่ใช่ "อนุมัติ 3 จุด แล้วเขียนบทใหม่ทั้งใบ"

การเขียนใหม่ทั้งบทหลังผู้ใช้อนุมัติบางข้อ เป็นวิธีที่ทำให้ตัวเลขหรือระดับความมั่นใจ
เปลี่ยนไปโดยไม่มีใครเห็น เพราะ diff ใหญ่จนไม่มีใครอ่านจริง ที่นี่จึงแทนที่เฉพาะ
ข้อความที่ผู้ใช้อนุมัติ ที่บรรทัดที่ระบุ ครั้งเดียว — หา anchor ไม่เจอก็หยุด ไม่เดา

## ด่านสามชั้นก่อนปล่อยผ่าน

1. **สอง hash** — ต้นฉบับและแพ็กภาษาต้องเป็นตัวเดียวกับตอนที่ตรวจ ไม่งั้น `STALE_REVIEW`
   (ทั้งสองอย่างเปลี่ยนได้ในช่วงระหว่างตรวจกับอนุมัติ ซึ่งกินเวลาเป็นวันในโหมดถามเป็นชุด)
2. **ต่อจุดที่แก้** — ตัวเลข ระดับความมั่นใจ และเงื่อนไข ในข้อความเดิมกับข้อความใหม่
   ต้องเท่ากันทุกตัว เทียบกันเป็นคู่ ตรงจุดที่แก้ ซึ่งแม่นกว่าเทียบทั้งบท
3. **ทั้งบท** — ชุดตัวเลขก่อนแก้กับหลังแก้ต้องเท่ากันเป๊ะ เป็นตาข่ายชั้นสุดท้าย
   เผื่อกรณีที่ชั้น 2 มองไม่เห็น (เช่น patch ไปทับข้อความอื่นโดยบังเอิญ)

## ข้อจำกัดที่รู้ตัว

คำบอกระดับความมั่นใจตรวจด้วยรายการคำ ซึ่งเป็นตัวแทนหยาบของความหมายจริง —
ภาษาไทยไม่มีตัวตัดคำในเครื่องนี้ จึงเทียบแบบนับคำที่ปรากฏ (เลือกคำที่ยาวที่สุดก่อน
เพื่อไม่ให้ "อาจ" ถูกนับซ้ำจาก "อาจจะ") ด่านนี้จับ *การหายไปหรือเพิ่มขึ้น* ของคำได้แน่นอน
แต่จับการเปลี่ยนความหมายที่ไม่ผ่านคำเหล่านี้ไม่ได้ — จึงเป็นหนึ่งในสามชั้น ไม่ใช่ชั้นเดียว
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from collections import Counter
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.language_review import sha256_text  # noqa: E402
from tools.locale_loader import load_locale  # noqa: E402
from tools.style_d_weekly_title import validate_localized_title  # noqa: E402
from tools.localization_config import LocalizationConfigError, resolve_country  # noqa: E402
from tools.wcb_writers import TITLE_MAX  # noqa: E402

#: ตัวเลขทุกรูปที่ผู้อ่านเห็น รวมเครื่องหมาย % และตัวคั่นหลักพัน
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?%?")

#: คำบอกระดับความมั่นใจ แยกตามระดับ — เรียงจากยาวไปสั้นตอนสร้าง pattern
CERTAINTY_MARKERS = {
    "possibility": ("อาจจะ", "อาจ", "น่าจะ", "มีโอกาส", "มีแนวโน้ม"),
    "assertion": ("รับประกัน", "ยืนยัน", "แน่นอน"),
    "conditional": ("ต่อเมื่อ", "จนกว่า", "หาก", "ถ้า", "เมื่อ"),
    "watch": ("ยังไม่", "จับตา", "ติดตาม", "เฝ้าดู", "รอสัญญาณ"),
}

#: คำที่ห้าม *เพิ่มเข้ามา* — สัญญาเว็บห้ามคำสั่งซื้อขายตรง ๆ ในบท
FORBIDDEN_TO_INTRODUCE = ("แนะนำซื้อ", "แนะนำขาย", "ควรซื้อ", "ควรขาย", "สั่งซื้อ", "เข้าซื้อทันที")

_MARKER_PATTERN = re.compile("|".join(
    re.escape(word) for word in sorted(
        (word for words in CERTAINTY_MARKERS.values() for word in words),
        key=len, reverse=True)))

_MARKER_LEVEL = {word: level for level, words in CERTAINTY_MARKERS.items() for word in words}


class PatchError(Exception):
    code = "PATCH_ERROR"


class StaleReviewError(PatchError):
    code = "STALE_REVIEW"


class PatchAnchorError(PatchError):
    code = "PATCH_ANCHOR_LOST"


class IntegrityError(PatchError):
    code = "INTEGRITY_FAILED"


# ---------------------------------------------------------------- ตัวสกัดของที่ห้ามเปลี่ยน

def numbers_of(text: str) -> Counter:
    return Counter(NUMBER.findall(text))


def certainty_of(text: str) -> Counter:
    """นับคำบอกความมั่นใจแบบเลือกคำยาวที่สุดก่อน — "อาจจะ" ไม่ถูกนับซ้ำเป็น "อาจ" + "จะ" """
    markers = []
    for match in _MARKER_PATTERN.finditer(text):
        word = match.group(0)
        # "เมื่อดู..." เป็นคำจัดลำดับการอ่าน ไม่ใช่เงื่อนไขตลาด/แผนเทรด
        # จับเฉพาะรูปที่พิสูจน์จาก L-102 เพื่อไม่เปิดข้อยกเว้นกว้างเกินจำเป็น
        if word == "เมื่อ" and text[match.end():].startswith("ดู"):
            continue
        markers.append(_MARKER_LEVEL[word] + ":" + word)
    return Counter(markers)


def compare_fragment(original: str, proposed: str) -> list[dict]:
    """เทียบข้อความเดิมกับข้อความใหม่ตรงจุดที่แก้ — คืนรายการที่ผิด (ว่าง = ผ่าน)"""
    problems: list[dict] = []

    before, after = numbers_of(original), numbers_of(proposed)
    if before != after:
        problems.append({
            "kind": "number_changed",
            "detail": f"ตัวเลขไม่ตรง เดิม {sorted(before.elements())} ใหม่ {sorted(after.elements())}",
        })

    before_certainty, after_certainty = certainty_of(original), certainty_of(proposed)
    if before_certainty != after_certainty:
        lost = sorted((before_certainty - after_certainty).elements())
        gained = sorted((after_certainty - before_certainty).elements())
        problems.append({
            "kind": "certainty_changed",
            "detail": f"ระดับความมั่นใจ/เงื่อนไขเปลี่ยน หาย {lost} เพิ่ม {gained}",
        })

    introduced = [word for word in FORBIDDEN_TO_INTRODUCE
                  if word in proposed and word not in original]
    if introduced:
        problems.append({
            "kind": "forbidden_introduced",
            "detail": f"เพิ่มคำที่ห้ามอยู่ในบท: {introduced}",
        })

    return problems


def integrity_report(before: str, after: str) -> dict:
    """ตาข่ายชั้นสุดท้ายระดับทั้งบท — ชุดตัวเลขต้องเท่ากันเป๊ะ"""
    before_numbers, after_numbers = numbers_of(before), numbers_of(after)
    problems: list[dict] = []
    if before_numbers != after_numbers:
        problems.append({
            "kind": "document_numbers_changed",
            "detail": f"หาย {sorted((before_numbers - after_numbers).elements())} "
                      f"เพิ่ม {sorted((after_numbers - before_numbers).elements())}",
        })
    return {"ok": not problems, "problems": problems,
            "numbers_before": sum(before_numbers.values()),
            "numbers_after": sum(after_numbers.values())}


# ---------------------------------------------------------------- ตัวตรวจ candidate ข้ามภาษา

def validate_localized_candidate(
    source_bytes: bytes,
    target_bytes: bytes,
    *,
    job: dict,
    claim_map: dict,
    trusted_receipts: list[dict],
    pack_info: dict,
) -> dict:
    """ตรวจ binding เชิงกลของ candidate ต่างภาษาโดยไม่เขียนไฟล์หรืออนุมัติภาษา

    รับ bytes ที่ caller อ่านมาแล้วเพื่อให้ hash ตรงกับไฟล์จริง และไม่ใช้
    ``compare_fragment`` ซึ่งมีตัวตรวจ certainty ภาษาไทย อำนาจยืนยัน source/
    reviewer เป็นของ caller ที่โหลด trusted receipt จาก Lead-controlled store
    """
    findings: list[dict] = []

    def problem(code: str, detail: str, *, claim_id: str | None = None) -> None:
        item = {"code": code, "detail": detail}
        if claim_id is not None:
            item["claim_id"] = claim_id
        findings.append(item)

    import hashlib

    def nonempty(value):
        return isinstance(value, str) and bool(value.strip())

    def valid_hash(value):
        return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None

    def unique_quote(text, quote):
        if not nonempty(quote):
            return False
        start = text.find(quote)
        return start >= 0 and text.find(quote, start + 1) < 0

    def check_review_metadata(receipt):
        from datetime import datetime

        for key in ("receipt_id", "reviewer_kind"):
            if not nonempty(receipt.get(key)):
                problem("RECEIPT_MISMATCH", f"receipt {key} is missing")
        try:
            reviewed_at = receipt.get("reviewed_at")
            if not nonempty(reviewed_at):
                raise ValueError("missing timestamp")
            timestamp = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
            if timestamp.utcoffset() is None:
                raise ValueError("timestamp needs a timezone")
        except ValueError:
            problem("RECEIPT_MISMATCH", "reviewed_at must be an ISO-8601 timestamp with timezone")
        receipt_findings = receipt.get("findings")
        if not isinstance(receipt_findings, list) or any(not isinstance(f, dict) for f in receipt_findings):
            problem("RECEIPT_MISMATCH", "receipt findings must be an object list")
        elif any(str(f.get("severity", "")).lower() in {"critical", "major"}
                 and f.get("resolved") is not True for f in receipt_findings):
            problem("REVIEW_FAILED", "unresolved Critical/Major findings")

    job = job if isinstance(job, dict) else {}
    claim_map = claim_map if isinstance(claim_map, dict) else {}
    pack_info = pack_info if isinstance(pack_info, dict) else {}
    if not isinstance(trusted_receipts, list) or any(not isinstance(r, dict) for r in trusted_receipts):
        problem("INPUT_INVALID", "trusted_receipts must be a list of objects")
        trusted_receipts = []
    required = ("article_id", "country_code", "content_locale", "language_pack",
                "pack_version", "source_receipt_id", "writer_execution_id")
    missing = [key for key in required if not nonempty(job.get(key))]
    if missing:
        problem("INPUT_INVALID", f"job ขาดช่องบังคับ: {', '.join(missing)}")
    try:
        country = resolve_country(job.get("country_code"))
    except LocalizationConfigError as exc:
        country = None
        problem("INPUT_INVALID", f"country configuration invalid: {exc}")
    if country:
        if job.get("content_locale") != country["content_locale"]:
            problem("INPUT_INVALID", "content_locale does not match country configuration")
        if job.get("language_pack") != country["language_pack"] or pack_info.get("locale") != country["language_pack"]:
            problem("INPUT_INVALID", "language_pack does not match country configuration")
        policy_hash = job.get("country_policy_sha256")
        if policy_hash is not None and policy_hash != country["policy_sha256"]:
            problem("INPUT_INVALID", "country policy changed after job preparation")
    for key in ("source_sha256", "target_sha256", "pack_sha256", "claim_map_sha256", "claim_map_actual_sha256"):
        if not valid_hash(job.get(key)):
            problem("INPUT_INVALID", f"{key} must be a SHA-256 digest")
    if job.get("claim_map_sha256") != job.get("claim_map_actual_sha256"):
        problem("CLAIM_MAP_STALE", "claim map bytes do not match the approved digest")

    source_hash = target_hash = None
    source_text = target_text = ""
    try:
        if not isinstance(source_bytes, bytes) or not isinstance(target_bytes, bytes):
            raise ValueError("source and target must be bytes")
        source_hash = hashlib.sha256(source_bytes).hexdigest()
        target_hash = hashlib.sha256(target_bytes).hexdigest()
        source_text = source_bytes.decode("utf-8")
        target_text = target_bytes.decode("utf-8")
        if not source_text.strip() or not target_text.strip():
            problem("INPUT_INVALID", "source and target must not be empty")
    except (UnicodeDecodeError, ValueError) as exc:
        problem("UTF8_INVALID", str(exc))

    if source_hash != job.get("source_sha256"):
        problem("SOURCE_CHANGED", "source_sha256 ไม่ตรง bytes ที่ส่งเข้ามา")
    if not valid_hash(claim_map.get("source_sha256")) or claim_map.get("source_sha256") != source_hash:
        problem("CLAIM_MAP_STALE", "claim map ผูกกับ source คนละ hash")
    if job.get("target_sha256") != target_hash:
        problem("TARGET_CHANGED", "target_sha256 ไม่ตรง bytes candidate")

    # Style D is the only localized article whose title carries a weekly
    # period.  The source manifest supplies one canonical ISO pair; a
    # translator may change wording/order/punctuation but cannot move dates or
    # silently turn the article back into a daily title.
    if str(job.get("style") or "").upper() == "D":
        week_start, week_end = job.get("week_start"), job.get("week_end")
        if not week_start or not week_end:
            problem("STYLE_D_WEEK_MISSING", "Style D localization requires week_start/week_end")
        else:
            title_match = re.search(r"(?m)^title:\s*(.*?)\s*$", target_text)
            if not title_match:
                problem("STYLE_D_TITLE_MISSING", "localized Style D candidate has no title")
            else:
                title = title_match.group(1).strip().strip("\"'")
                if len(title) > TITLE_MAX:
                    problem("TITLE_TOO_LONG",
                            f"localized title is {len(title)} characters (maximum {TITLE_MAX})")
                for detail in validate_localized_title(
                    title,
                    week_start, week_end,
                    locale=str(job.get("content_locale") or "")):
                    problem("STYLE_D_WEEK_TITLE", detail)
        # Localized Style D follows the same body contract as the source.  The
        # exact first heading text is locale-owned, so validate its level and
        # position while rejecting any legacy H1/teaser/rule intro.
        body_parts = target_text.split("---", 2)
        localized_body = body_parts[2] if len(body_parts) == 3 else ""
        first_nonempty = next((line.strip() for line in localized_body.splitlines()
                               if line.strip()), "")
        if not first_nonempty.startswith("## "):
            problem("STYLE_D_BODY_START",
                    "localized Style D body must begin with its first H2 structure heading")

    pack_hash = pack_info.get("sha256")
    if not valid_hash(pack_hash) or job.get("pack_sha256") != pack_hash:
        problem("PACK_CHANGED", "pack_sha256 ไม่ตรง pack ที่ตรวจ")
    if pack_info.get("version") != job.get("pack_version"):
        problem("PACK_CHANGED", "pack_version ไม่ตรง pack ที่ตรวจ")

    source_acceptance = [item for item in trusted_receipts
                         if item.get("gate") == "source_acceptance"
                         and item.get("article_id") == job.get("article_id")
                         and item.get("receipt_id") == job.get("source_receipt_id")]
    if len(source_acceptance) != 1:
        problem("SOURCE_RECEIPT_MISSING", "ไม่มี source acceptance receipt ใน trusted store")
    else:
        for receipt in source_acceptance:
            check_review_metadata(receipt)
            if receipt.get("source_sha256") != source_hash:
                problem("RECEIPT_MISMATCH", "source receipt ผูกกับ source คนละ hash")
            for key in ("pack_sha256", "claim_map_sha256"):
                if not valid_hash(receipt.get(key)) or receipt.get(key) != job.get(key):
                    problem("RECEIPT_MISMATCH", f"source receipt {key} differs")
            if receipt.get("verdict") != "PASS":
                problem("SOURCE_NOT_ACCEPTED", "source receipt ยังไม่ PASS")
            if not nonempty(receipt.get("reviewer_execution_id")):
                problem("RECEIPT_MISMATCH", "source reviewer identity is missing")

    claims = claim_map.get("claims")
    if not isinstance(claims, list) or not claims or any(not isinstance(c, dict) for c in claims):
        problem("CLAIM_MAP_INVALID", "claims must be a nonempty object list")
        claims = []
    claim_ids = [item.get("id") for item in claims]
    if any(not nonempty(c) for c in claim_ids) or len(claim_ids) != len(set(str(c) for c in claim_ids)):
        problem("CLAIM_MAP_INVALID", "claim IDs ต้องมีค่าและไม่ซ้ำ")
    alignment = job.get("alignment")
    if not isinstance(alignment, list) or any(not isinstance(a, dict) for a in alignment):
        problem("INPUT_INVALID", "alignment must be an object list")
        alignment = []
    alignment_ids = [a.get("claim_id") for a in alignment]
    if any(not nonempty(c) for c in alignment_ids):
        problem("CLAIM_MAP_INVALID", "alignment IDs must be nonempty")
    if any(c not in claim_ids for c in alignment_ids):
        problem("CLAIM_MAP_INVALID", "unknown alignment claim ID")
    by_claim: dict[str, list[str]] = {}
    target_spans: list[tuple[int, int]] = []
    for item in alignment:
        claim_id = item.get("claim_id")
        if not nonempty(claim_id):
            continue
        if not nonempty(item.get("target_field")):
            problem("CLAIM_MAP_INVALID", "target_field is missing", claim_id=claim_id)
        quote = item.get("target_quote")
        if not unique_quote(target_text, quote):
            problem("TARGET_ANCHOR_MISSING", "target quote missing or ambiguous", claim_id=claim_id)
            continue
        start = target_text.index(quote)
        end = start + len(quote)
        if any(start < prior_end and prior_start < end for prior_start, prior_end in target_spans):
            problem("TARGET_ANCHOR_OVERLAP", "target spans overlap or repeat", claim_id=claim_id)
            continue
        target_spans.append((start, end))
        by_claim.setdefault(claim_id, []).append(quote)

    def literal_count(text, literal):
        # Prevent matching 1.16 inside 11.16, -1.16, or 1.160; preserve signs/units.
        return len(re.findall(r"(?<![A-Za-z0-9_.,+%\-])" + re.escape(literal)
                              + r"(?![A-Za-z0-9_%]|[.,]\d)", text))

    for claim in claims:
        claim_id = claim.get("id")
        quotes = by_claim.get(claim_id) if nonempty(claim_id) else None
        if not quotes:
            problem("CLAIM_MISSING", "ไม่มี target alignment", claim_id=claim_id)
            continue
        source_quote = claim.get("source_quote")
        if not unique_quote(source_text, source_quote):
            problem("CLAIM_MAP_INVALID", "source quote missing or ambiguous", claim_id=claim_id)
            source_quote = ""
        protected_values = claim.get("protected")
        if not isinstance(protected_values, list) or any(not isinstance(p, dict) for p in protected_values):
            problem("CLAIM_MAP_INVALID", "protected must be an object list", claim_id=claim_id)
            continue
        seen_protected = set()
        for protected in protected_values:
            value = protected.get("value_text")
            pid = protected.get("id")
            if any(not nonempty(protected.get(key)) for key in ("id", "kind", "value_text", "unit", "role")) or pid in seen_protected:
                problem("CLAIM_MAP_INVALID", "protected id/kind/value_text/unit/role invalid", claim_id=claim_id)
                continue
            seen_protected.add(pid)
            source_count = literal_count(source_quote, value)
            if not source_count or sum(literal_count(quote, value) for quote in quotes) != source_count:
                problem("PROTECTED_VALUE_MISSING", f"protected literal count differs: {value!r}", claim_id=claim_id)

    writer_id = job.get("writer_execution_id")
    required_gates = {"language", "semantic", "visual", "package_input"}
    review_receipts = [item for item in trusted_receipts
                       if item.get("article_id") == job.get("article_id")
                       and item.get("gate") in required_gates]
    for receipt in review_receipts:
        check_review_metadata(receipt)
        reviewer = receipt.get("reviewer_execution_id")
        if not nonempty(reviewer) or reviewer == writer_id:
            problem("REVIEW_NOT_INDEPENDENT", "reviewer must be present and distinct from writer")
        for key, expected in (("source_sha256", source_hash), ("target_sha256", target_hash),
                              ("pack_sha256", pack_hash), ("claim_map_sha256", job.get("claim_map_sha256"))):
            if not valid_hash(receipt.get(key)) or receipt.get(key) != expected:
                problem("RECEIPT_MISMATCH", f"receipt {key} differs")
        if receipt.get("gate") in {"visual", "package_input"}:
            hashes = job.get("image_hashes")
            if not isinstance(hashes, dict) or any(not nonempty(k) or not valid_hash(v) for k, v in hashes.items()) or receipt.get("image_hashes") != hashes:
                problem("RECEIPT_MISMATCH", "image hashes differ or are absent")
        if receipt.get("verdict") != "PASS":
            problem("REVIEW_FAILED", "target review is not PASS")
    gates = [r.get("gate") for r in review_receipts]
    if len(gates) != len(set(gates)):
        problem("RECEIPT_MISMATCH", "duplicate review gate")
    has_failed = any(item.get("verdict") != "PASS" for item in review_receipts)
    review_status = "FAILED" if findings or has_failed else (
        "VERIFIED" if set(gates) == required_gates
        else "PENDING")
    pack_ready = (pack_info.get("status") == "stable_locked"
                  and pack_info.get("verified") is True and valid_hash(pack_hash)
                  and pack_info.get("recorded_sha256") == pack_hash
                  and nonempty(pack_info.get("approved_by")) and nonempty(pack_info.get("approved_at")))
    mechanical_ok = not findings
    release_eligible = mechanical_ok and review_status == "VERIFIED" and pack_ready
    return {
        "mechanical_ok": mechanical_ok,
        "review_status": review_status,
        "pack_ready": pack_ready,
        "release_eligible": release_eligible,
        "source_sha256": source_hash,
        "target_sha256": target_hash,
        "findings": findings,
    }


# ---------------------------------------------------------------- ตัว apply

def apply_approved(source_text: str, review: dict, approved_ids, *,
                   pack_sha256: str | None = None, strict: bool = True) -> dict:
    """แทนที่เฉพาะข้อเสนอที่อนุมัติ ทีละจุด ที่บรรทัดที่ระบุ

    `strict=True` = เจอปัญหาใด ๆ แล้วโยนทันที · `False` = คืนรายงานให้ปลายทางตัดสิน
    (ใช้ตอนอยากเห็นภาพรวมว่าติดกี่จุดก่อนแก้จริง)
    """
    approved = list(approved_ids)

    if sha256_text(source_text) != review.get("source_sha256"):
        raise StaleReviewError(
            "ต้นฉบับเปลี่ยนไปหลังจากตรวจ — ต้องตรวจใหม่ก่อน apply "
            "(นี่คือกรณีปกติเมื่อถามอนุมัติเป็นชุดข้ามวัน ไม่ใช่ความผิดพลาด)")
    if pack_sha256 is not None and pack_sha256 != review.get("baseline_sha256"):
        raise StaleReviewError(
            "แพ็กภาษาเปลี่ยนไปหลังจากตรวจ — กฎที่ใช้ตรวจกับกฎปัจจุบันคนละชุดแล้ว ต้องตรวจใหม่")

    by_id = {item["id"]: item for item in review["revisions"]}
    unknown = [rid for rid in approved if rid not in by_id]
    if unknown:
        raise PatchError(f"ไม่มีข้อเสนอรหัสนี้ในผลตรวจ: {unknown}")

    lines = source_text.splitlines(keepends=True)
    applied: list[dict] = []
    skipped: list[dict] = []

    # เรียงจากบรรทัดท้ายขึ้นหน้า เพื่อให้การแก้บรรทัดหลังไม่ขยับ anchor ของบรรทัดก่อน
    for rid in sorted(approved, key=lambda r: by_id[r]["line"], reverse=True):
        item = by_id[rid]
        if item.get("proposed") is None:
            skipped.append({"id": rid, "why": "ไม่มีข้อความแทนที่ — ข้อนี้ต้องใช้วิจารณญาณของคน"})
            continue

        index = item["line"] - 1
        if not 0 <= index < len(lines):
            message = f"บรรทัด {item['line']} อยู่นอกไฟล์ (ไฟล์มี {len(lines)} บรรทัด)"
            if strict:
                raise PatchAnchorError(f"[{rid}] {message}")
            skipped.append({"id": rid, "why": message})
            continue

        line = lines[index]
        if item["original"] not in line:
            message = f"ไม่พบข้อความเดิม {item['original']!r} ที่บรรทัด {item['line']}"
            if strict:
                raise PatchAnchorError(f"[{rid}] {message}")
            skipped.append({"id": rid, "why": message})
            continue

        problems = compare_fragment(item["original"], item["proposed"])
        if problems:
            message = "; ".join(problem["detail"] for problem in problems)
            if strict:
                raise IntegrityError(f"[{rid}] {message}")
            skipped.append({"id": rid, "why": message, "problems": problems})
            continue

        lines[index] = line.replace(item["original"], item["proposed"], 1)
        applied.append({"id": rid, "line": item["line"],
                        "original": item["original"], "proposed": item["proposed"]})

    patched = "".join(lines)
    integrity = integrity_report(source_text, patched)
    if strict and not integrity["ok"]:
        raise IntegrityError("; ".join(problem["detail"] for problem in integrity["problems"]))

    return {
        "ok": integrity["ok"] and not skipped,
        "review_id": review.get("review_id"),
        "applied": list(reversed(applied)),  # คืนตามลำดับบรรทัดจากบนลงล่างให้คนอ่าน
        "skipped": skipped,
        "integrity": integrity,
        "text": patched,
        "source_sha256_before": review["source_sha256"],
        "source_sha256_after": sha256_text(patched),
        "diff": diff_text(source_text, patched, review.get("source_path") or "article.md"),
    }


def diff_text(before: str, after: str, name: str = "article.md") -> str:
    return "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=f"a/{name}", tofile=f"b/{name}", n=1))


# ---------------------------------------------------------------- CLI

def _parse_approval(value: str, review: dict) -> list[str]:
    """รับรูปแบบที่ผู้ใช้ตอบจริงในชุดประจำวัน"""
    all_ids = [item["id"] for item in review["revisions"]]
    text = value.strip()
    if text in {"all", "ทั้งหมด"}:
        return all_ids
    if text in {"none", "ปฏิเสธทั้งหมด"}:
        return []
    if text.startswith("except:"):
        excluded = {part.strip() for part in text[len("except:"):].split(",") if part.strip()}
        return [rid for rid in all_ids if rid not in excluded]
    return [part.strip() for part in text.split(",") if part.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="apply ข้อเสนอภาษาที่ผู้ใช้อนุมัติ แบบเจาะจุด")
    parser.add_argument("article", help="ไฟล์บทต้นฉบับ")
    parser.add_argument("--review", required=True, help="ไฟล์ผลตรวจ (review.json ของบทนี้)")
    parser.add_argument("--approve", required=True,
                        help="'all' · 'none' · 'L-001,L-003' · 'except:L-004'")
    parser.add_argument("--out", default=None, help="เขียนผลลัพธ์ลงไฟล์นี้ (ไม่ระบุ = ไม่เขียนทับ)")
    parser.add_argument("--locale", default="th-TH")
    parser.add_argument("--check-baseline", action="store_true",
                        help="ตรวจด้วยว่าแพ็กภาษายังเป็นตัวเดิมกับตอนตรวจ")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    article_path = Path(args.article)
    source = article_path.read_text(encoding="utf-8")
    review = json.loads(Path(args.review).read_text(encoding="utf-8"))
    if review.get("schema") == "language-review-batch-v1":
        matches = [item for item in review["reviews"]
                   if Path(item.get("source_path") or "").name == article_path.name]
        if not matches:
            print(f"[PATCH_ERROR] ชุดนี้ไม่มีผลตรวจของ {article_path.name}")
            return 1
        review = matches[0]

    pack_sha = load_locale(args.locale, verify_hash=False).sha256 if args.check_baseline else None

    try:
        result = apply_approved(source, review, _parse_approval(args.approve, review),
                                pack_sha256=pack_sha, strict=False)
    except PatchError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "error": str(exc)},
                         ensure_ascii=False, indent=2) if args.json else f"[{exc.code}] {exc}")
        return 1

    if args.out and result["integrity"]["ok"]:
        Path(args.out).write_text(result["text"], encoding="utf-8")

    if args.json:
        payload = {key: value for key, value in result.items() if key != "text"}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"apply {len(result['applied'])} จุด · ข้าม {len(result['skipped'])} จุด · "
              f"integrity {'ผ่าน' if result['integrity']['ok'] else 'ไม่ผ่าน'}")
        for item in result["skipped"]:
            print(f"  ข้าม [{item['id']}] {item['why']}")
        for problem in result["integrity"]["problems"]:
            print(f"  ⛔ {problem['detail']}")
        if result["diff"]:
            print("\n" + result["diff"])
    return 0 if result["integrity"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
