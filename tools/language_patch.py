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

#: คำบอกทิศ — เทียบแบบ "มี/ไม่มี" ไม่ใช่จำนวนครั้ง เพราะการเรียบเรียงใหม่
#: ทำให้จำนวนครั้งเปลี่ยนได้โดยความหมายเท่าเดิม แต่การหายไปทั้งคำคือความหมายเปลี่ยน
DIRECTION_TERMS = ("ซื้อ", "ขาย", "ขึ้น", "ลง", "บวก", "ลบ")

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
    return Counter(_MARKER_LEVEL[match.group(0)] + ":" + match.group(0)
                   for match in _MARKER_PATTERN.finditer(text))


def directions_of(text: str) -> set:
    return {word for word in DIRECTION_TERMS if word in text}


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

    lost_direction = directions_of(original) - directions_of(proposed)
    if lost_direction:
        problems.append({
            "kind": "direction_lost",
            "detail": f"คำบอกทิศหายไป: {sorted(lost_direction)}",
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
