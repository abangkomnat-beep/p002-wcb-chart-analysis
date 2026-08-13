"""ด่านตรวจภาษาเชิงกล — ทำงานก่อน LLM เพื่อให้ LLM เหลือแต่เรื่องที่ต้องใช้วิจารณญาณ

## ทำไมต้องมีชั้นเชิงกลก่อน

ถ้าโยนบททั้งใบให้ LLM ว่า "ช่วยปรับภาษาให้ดีขึ้น" จะได้สามอย่างที่ไม่ต้องการพร้อมกัน:
เปลืองโทเคนทุกวันกับเรื่องเดิม · ผลไม่คงเส้นคงวา (บทเดียวกันรันสองครั้งได้คนละคำตอบ) ·
และที่อันตรายที่สุดคือ LLM มีโอกาสแตะตัวเลขหรือระดับความมั่นใจโดยไม่มีใครเห็น

สิ่งที่**เขียนเป็นกฎได้** (คำต้องห้าม ศัพท์ที่มีคำแทน ย่อหน้ายาวผิดปกติ คำเชื่อมซ้อน ข้อความซ้ำ)
จึงตรวจด้วยโค้ดที่นี่ ได้ผลเท่ากันทุกครั้งและอธิบายที่มาได้ทีละข้อ ส่วนที่เหลือ —
ความเป็นธรรมชาติ โครงประโยคแปล น้ำเสียง — เป็นงานของสกิลที่ใช้วิจารณญาณ

## ผลลัพธ์ผูกกับสอง hash เสมอ

`source_sha256` (ต้นฉบับ) และ `baseline_sha256` (แพ็กภาษา) — เพราะทั้งสองอย่างเปลี่ยนได้
หลังตรวจแต่ก่อน apply ถ้าไม่ตรง `language_patch` จะปฏิเสธด้วย `STALE_REVIEW`
แทนที่จะแก้ข้อความผิดที่เงียบ ๆ

## จังหวะถามผู้ใช้ (มติผู้ใช้ 2026-08-13)

ช่วง calibration **รวมข้อเสนอทุกบทของวันเป็นชุดเดียว ถามครั้งเดียวต่อวัน ห้ามถามทีละข้อ**
`bundle_daily()` คือตัวรวบ และ `render_batch()` คือหน้าตาที่ผู้ใช้เห็น
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.locale_loader import LocalePack, load_locale  # noqa: E402
from tools.voice_rules import count_public_words  # noqa: E402

SCHEMA = "language-review-v1"

SEVERITY_ORDER = {"block": 0, "warning": 1, "info": 2}

#: บรรทัดที่ไม่ใช่เนื้อความสำหรับผู้อ่าน — ไม่ตรวจ (แต่ยังนับเลขบรรทัดตามจริง)
_SKIP_PREFIXES = ("#", "![", "|", "*ข้อมูล ณ ")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def split_body(text: str) -> tuple[int, list[str]]:
    """คืน (เลขบรรทัดที่เนื้อความเริ่ม, บรรทัดของเนื้อความ) — ข้าม frontmatter

    เลขบรรทัดต้องนับจากไฟล์จริง ไม่ใช่จากเนื้อที่ตัดหัวแล้ว ไม่งั้น patch จะไปแก้ผิดบรรทัด
    """
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                return index + 2, lines[index + 1:]
    return 1, lines


def _is_prose(line: str) -> bool:
    """บรรทัดนี้เป็นเนื้อความที่ผู้อ่านอ่านไหม

    เส้นคั่น `---` ต้องถูกคัดออกที่นี่ ไม่ใช่แค่เพราะมันไม่ใช่เนื้อความ แต่เพราะ
    `count_public_words` ถูกออกแบบให้รับ **ทั้งเอกสาร** — มันตัด frontmatter ด้วยการ
    split ที่ `---` ⇒ ส่งเส้นคั่นเดี่ยว ๆ เข้าไปจะได้ IndexError (เจอจริงตอนรันกับคลังบท 244 ใบ)
    """
    stripped = line.strip()
    if not stripped or stripped.startswith(_SKIP_PREFIXES):
        return False
    if set(stripped) <= set("-—_=* "):
        return False
    return True


def _find_phrase(line: str, phrase: str) -> int:
    """หาตำแหน่งของวลี — คำละตินเทียบแบบไม่สนตัวพิมพ์ ให้ตรงกับพฤติกรรมของ voice_rules"""
    if phrase.isascii():
        return line.lower().find(phrase.lower())
    return line.find(phrase)


class _RevisionBuilder:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, *, category: str, severity: str, line: int, original: str,
            proposed: str | None, reason: str, rule_id: str | None) -> None:
        self.items.append({
            "id": "",  # เติมทีหลังหลังเรียงลำดับ เพื่อให้เลขไล่ตามที่ผู้ใช้เห็นจริง
            "category": category,
            "severity": severity,
            "line": line,
            "original": original,
            "proposed": proposed,
            "reason": reason,
            "rule_id": rule_id,
            "auto_applicable": proposed is not None,
        })


def _check_avoid_terms(pack: LocalePack, line_no: int, line: str, out: _RevisionBuilder) -> None:
    matched_spans: list[tuple[int, int]] = []
    for term in pack.avoid_terms():
        phrase = term["phrase"]
        position = _find_phrase(line, phrase)
        if position < 0:
            continue
        span = (position, position + len(phrase))
        # คำที่กว้างกว่าซ้อนอยู่ในคำที่จำเพาะกว่าซึ่งรายงานไปแล้ว = ไม่รายงานซ้ำ
        # (avoid_terms เรียงจากยาวไปสั้นมาแล้ว)
        if any(start <= span[0] and span[1] <= end for start, end in matched_spans):
            continue
        matched_spans.append(span)
        out.add(
            category=term["category"],
            severity=term["severity"],
            line=line_no,
            original=line[span[0]:span[1]],
            proposed=term["suggest"],
            reason=term["reason"],
            rule_id=f"avoid:{phrase}",
        )


def _check_glossary(pack: LocalePack, line_no: int, line: str, out: _RevisionBuilder) -> None:
    already = {item["original"] for item in out.items if item["line"] == line_no}
    for word, preferred in pack.glossary_avoid_map().items():
        if word in already or word not in line:
            continue
        out.add(
            category="technical_term",
            severity="warning",
            line=line_no,
            original=word,
            proposed=preferred,
            reason=f"ศัพท์กลางของ locale นี้ใช้ {preferred!r} แทน {word!r}"
                   if preferred else f"{word!r} ไม่ใช่ศัพท์ที่ locale นี้ใช้",
            rule_id=f"glossary:{word}",
        )


def _check_paragraph(pack: LocalePack, line_no: int, line: str, out: _RevisionBuilder) -> None:
    rules = pack.sentence_patterns
    density = rules.get("paragraph_density") or {}
    limit = density.get("max_words")
    if limit:
        words = count_public_words(line)
        if words > limit:
            out.add(
                category="sentence_density",
                severity=density.get("severity", "warning"),
                line=line_no,
                original=line.strip()[:60],
                proposed=None,  # การแบ่งย่อหน้าต้องใช้วิจารณญาณ เครื่องเสนอแทนไม่ได้
                reason=f"ย่อหน้านี้ยาว {words} คำ (เพดาน {limit}) — "
                       "ย่อหน้าที่ยาวเกินนี้มักรวมหลายตรรกะไว้ก้อนเดียว",
                rule_id="paragraph_density",
            )

    connectors = rules.get("connector_overuse") or {}
    max_connectors = connectors.get("max_per_paragraph")
    if max_connectors:
        found = {word: line.count(word) for word in connectors.get("connectors") or []}
        total = sum(found.values())
        if total > max_connectors:
            top = ", ".join(f"{word}×{n}" for word, n in
                            sorted(found.items(), key=lambda kv: -kv[1]) if n)
            out.add(
                category="connector_overuse",
                severity=connectors.get("severity", "warning"),
                line=line_no,
                original=line.strip()[:60],
                proposed=None,
                reason=f"คำเชื่อม {total} ตัวในย่อหน้าเดียว (เพดาน {max_connectors}) — {top}",
                rule_id="connector_overuse",
            )


def _check_redundancy(pack: LocalePack, start_line: int, lines: list[str],
                      out: _RevisionBuilder) -> None:
    rules = (pack.sentence_patterns.get("redundancy") or {})
    window = rules.get("min_repeat_chars")
    if not window:
        return
    minimum = rules.get("min_occurrences", 2)

    seen: dict[str, int] = {}
    first_line: dict[str, int] = {}
    for offset, line in enumerate(lines):
        if not _is_prose(line):
            continue
        # บรรทัดรายการ (bullet/ลำดับเลข) ไม่เข้าการตรวจซ้ำ — รายการปฏิทินและป้ายแผน
        # ("จุดตัดขาดทุน (Stop Loss):", "ซึ่งจัดเป็นรายการผลกระทบสูง") จงใจใช้โครงขนาน
        # ให้ผู้อ่านกวาดตาเทียบกันได้ ความซ้ำตรงนั้นคือ format ไม่ใช่ความซ้ำซ้อนของร้อยแก้ว
        # (มติผู้ใช้ 2026-08-13 — Calibration ชุดแรก)
        if re.match(r"^\s*(?:[-*•]|\d+[.)])\s", line):
            continue
        compact = re.sub(r"\s+", " ", line.strip())
        for index in range(len(compact) - window + 1):
            chunk = compact[index:index + window]
            seen[chunk] = seen.get(chunk, 0) + 1
            first_line.setdefault(chunk, start_line + offset)

    repeated = [chunk for chunk, count in seen.items() if count >= minimum]
    if not repeated:
        return
    # รายงานตัวเดียวต่อบท — ตัวที่ยาวที่สุดครอบตัวสั้นที่ซ้อนกันอยู่แล้ว
    worst = max(repeated, key=lambda chunk: (seen[chunk], len(chunk)))
    out.add(
        category="redundancy",
        severity=rules.get("severity", "info"),
        line=first_line[worst],
        original=worst,
        proposed=None,
        reason=f"ข้อความยาว {len(worst)} อักขระนี้ปรากฏ {seen[worst]} ครั้งในบทเดียว",
        rule_id="redundancy",
    )


def review_text(text: str, pack: LocalePack, *, review_id: str,
                source_path: str | None = None, generated_at: str | None = None) -> dict:
    """ตรวจบทหนึ่งใบ คืนผลตามสคีมา language-review-v1"""
    start_line, lines = split_body(text)
    out = _RevisionBuilder()

    for offset, line in enumerate(lines):
        if not _is_prose(line):
            continue
        line_no = start_line + offset
        _check_avoid_terms(pack, line_no, line, out)
        _check_glossary(pack, line_no, line, out)
        _check_paragraph(pack, line_no, line, out)

    _check_redundancy(pack, start_line, lines, out)

    revisions = sorted(out.items, key=lambda item: (SEVERITY_ORDER[item["severity"]], item["line"]))
    for number, item in enumerate(revisions, start=1):
        item["id"] = f"L-{number:03d}"

    by_severity: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for item in revisions:
        by_severity[item["severity"]] = by_severity.get(item["severity"], 0) + 1
        by_category[item["category"]] = by_category.get(item["category"], 0) + 1

    return {
        "schema": SCHEMA,
        "review_id": review_id,
        "locale": pack.locale,
        "baseline_version": pack.version,
        "baseline_status": pack.status,
        "source_path": source_path,
        "source_sha256": sha256_text(text),
        "baseline_sha256": pack.sha256,
        "generated_at": generated_at,
        "summary": {"total": len(revisions), "by_severity": by_severity, "by_category": by_category},
        "revisions": revisions,
    }


def review_file(path: Path, pack: LocalePack, *, generated_at: str | None = None) -> dict:
    path = Path(path)
    review_id = f"LANG-{pack.locale}-{path.stem}"
    return review_text(path.read_text(encoding="utf-8"), pack,
                       review_id=review_id, source_path=str(path), generated_at=generated_at)


# ---------------------------------------------------------------- ชุดอนุมัติประจำวัน

def bundle_daily(reviews: list[dict], *, batch_id: str, date: str,
                 locale: str = "th-TH") -> dict:
    """รวมผลตรวจทุกบทของวันเป็นชุดเดียว — ผู้ใช้ตอบครั้งเดียวต่อวัน

    รหัสข้อเสนอในชุดเป็น `<หัวข้อ>/L-0xx` เพื่อไม่ให้เลขชนกันข้ามบท
    (แต่ละบทเริ่มนับ L-001 ใหม่เสมอ ซึ่งถูกแล้วเมื่อดูทีละบท)
    """
    total = 0
    by_severity: dict[str, int] = {}
    entries = []
    for review in reviews:
        key = Path(review.get("source_path") or review["review_id"]).stem
        for item in review["revisions"]:
            total += 1
            by_severity[item["severity"]] = by_severity.get(item["severity"], 0) + 1
        entries.append({"key": key, "review": review})

    return {
        "schema": "language-review-batch-v1",
        "batch_id": batch_id,
        "date": date,
        "locale": locale,
        "batching": "daily_batch",
        "batching_note": "มติผู้ใช้ 2026-08-13 — ถามครั้งเดียวต่อวัน ห้ามถามทีละข้อ",
        "summary": {"articles": len(reviews), "revisions": total, "by_severity": by_severity},
        "reviews": [entry["review"] for entry in entries],
    }


def render_batch(batch: dict, *, max_items: int = 40) -> str:
    """หน้าตาที่ผู้ใช้เห็นตอนอนุมัติ — สั้นพอที่จะอ่านจบในครั้งเดียว"""
    summary = batch["summary"]
    lines = [
        f"Language Review · {batch['locale']} · ชุดประจำวัน {batch['date']} ({batch['batch_id']})",
        f"บท {summary['articles']} ใบ · ข้อเสนอ {summary['revisions']} ข้อ"
        + (" · " + " · ".join(f"{name} {count}"
                              for name, count in sorted(summary["by_severity"].items(),
                                                        key=lambda kv: SEVERITY_ORDER[kv[0]]))
           if summary["by_severity"] else ""),
        "",
    ]
    shown = 0
    for review in batch["reviews"]:
        if not review["revisions"]:
            continue
        key = Path(review.get("source_path") or review["review_id"]).stem
        lines.append(f"── {key} · baseline {review['baseline_version']} ({review['baseline_status']})")
        for item in review["revisions"]:
            if shown >= max_items:
                lines.append(f"   … อีก {summary['revisions'] - shown} ข้อ ดูเต็มใน review.json")
                break
            proposed = item["proposed"] if item["proposed"] is not None else "(ต้องใช้วิจารณญาณ ยังไม่มีคำแทน)"
            lines.append(f"   [{key}/{item['id']}] {item['category']} · {item['severity']} · บรรทัด {item['line']}")
            lines.append(f"      เดิม  : {item['original']}")
            lines.append(f"      เสนอ  : {proposed}")
            lines.append(f"      เหตุผล: {item['reason']}")
            shown += 1
        if shown >= max_items:
            break
        lines.append("")

    lines += [
        "",
        "ตอบได้แบบ: อนุมัติทั้งหมด · อนุมัติเฉพาะ <รหัส> · อนุมัติทั้งหมดยกเว้น <รหัส> · ปฏิเสธทั้งหมด",
        "ไม่ตอบ = บทเดินต่อโดยไม่แก้ภาษา (ไม่ block การผลิต)",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ตรวจภาษาเชิงกลของบทวิเคราะห์")
    parser.add_argument("paths", nargs="+", help="ไฟล์ .md ของบท (ใส่หลายไฟล์ = รวมเป็นชุดวันเดียว)")
    parser.add_argument("--locale", default="th-TH")
    parser.add_argument("--version", default=None)
    parser.add_argument("--batch-id", default=None)
    parser.add_argument("--date", default=None, help="วันที่ของชุด (ไม่ระบุ = ใช้ค่าจาก --batch-id)")
    parser.add_argument("--out", default=None, help="เขียนชุดเป็น JSON ลงไฟล์นี้")
    parser.add_argument("--json", action="store_true", help="พิมพ์ JSON แทนข้อความอ่านง่าย")
    parser.add_argument("--no-verify-hash", action="store_true")
    args = parser.parse_args(argv)

    pack = load_locale(args.locale, args.version, verify_hash=not args.no_verify_hash)
    reviews = [review_file(Path(path), pack) for path in args.paths]
    batch_id = args.batch_id or f"B-{args.locale}"
    batch = bundle_daily(reviews, batch_id=batch_id, date=args.date or "-", locale=args.locale)

    if args.out:
        Path(args.out).write_text(json.dumps(batch, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8")
    print(json.dumps(batch, ensure_ascii=False, indent=2) if args.json else render_batch(batch))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
