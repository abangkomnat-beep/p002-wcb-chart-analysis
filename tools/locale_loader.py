"""ตัวโหลดแพ็กภาษา — จุดเดียวที่ประกอบกฎภาษาให้ครบก้อนก่อนเอาไปใช้

## ทำไมต้องมีตัวกลาง ไม่อ่านไฟล์ตรง ๆ

1. **กฎกระจายอยู่หลายไฟล์** (baseline · glossary · phrases · patterns) ใครอ่านเองก็ลืมไฟล์ใดไฟล์หนึ่งได้
2. **ทะเบียนคำต้องห้ามมีสองที่โดยเจตนา** — ตัวจริงคือ `voice_rules.VOICE_DENYLIST` ในโค้ด
   ส่วน `avoid-phrases.json` เก็บเฉพาะคำ *เพิ่มเติม* พร้อมเหตุผล การรวมสองอย่างนี้
   ต้องเกิดที่เดียว ไม่งั้นปลายทางแต่ละที่จะรวมไม่เหมือนกัน
3. **locale ที่ไม่มี baseline ต้องหยุด ไม่ใช่ยืมกฎภาษาอื่น** — เป็นกรณีที่พังเงียบที่สุด
   เพราะบทจะออกมาอ่านได้ปกติแต่ใช้มาตรฐานผิดชุด

## สิ่งที่ตัวโหลดนี้ *ไม่* ทำ

ไม่ validate ด้วย jsonschema — รีโปนี้ตั้งใจใช้ stdlib ล้วน (ดูหมายเหตุใน requirements.txt)
สคีมาใน `schemas/language-*.schema.json` เป็นสัญญาที่คนกับเทสอ่าน ส่วนการบังคับตอนรัน
ทำด้วยการตรวจช่องที่จำเป็นตรง ๆ ในไฟล์นี้ — แลกความยืดหยุ่นกับการไม่เพิ่ม dependency
ให้คนที่รับรีโปนี้ไปใช้
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools import baseline_registry as registry  # noqa: E402
from tools.baseline_registry import (  # noqa: E402
    BaselineError, BaselineTamperedError, LocaleBaselineMissing,
)
from tools.voice_rules import VOICE_DENYLIST  # noqa: E402

CORE_PATH = registry.LANGUAGE_DIR / "core" / "financial-editorial-core-v1.json"

PACK_FILES = {
    "baseline": "baseline.json",
    "glossary": "glossary.json",
    "preferred_phrases": "preferred-phrases.json",
    "avoid_phrases": "avoid-phrases.json",
    "sentence_patterns": "sentence-patterns.json",
    "regression_cases": "regression-cases.json",
}

#: ช่องที่ baseline.json ขาดไม่ได้ — ขาดแล้วโหลดไม่ผ่าน ไม่ใช่เติมค่าเริ่มต้นให้เงียบ ๆ
REQUIRED_BASELINE_KEYS = ("baseline_id", "version", "status", "locale", "certainty", "approval")


class LanguagePackError(BaselineError):
    code = "LANGUAGE_PACK_INVALID"


@dataclass(frozen=True)
class LocalePack:
    """แพ็กภาษาหนึ่งเวอร์ชันที่พร้อมใช้ — สร้างจาก `load_locale()` เท่านั้น"""

    locale: str
    version: str
    status: str
    pack_dir: Path
    sha256: str
    core: dict
    baseline: dict
    glossary: dict
    preferred_phrases: dict
    avoid_phrases: dict
    sentence_patterns: dict
    regression_cases: dict
    _avoid_index: list = field(default_factory=list, repr=False)

    # ----------------------------------------------------------- คุณสมบัติที่ใช้บ่อย
    @property
    def is_locked(self) -> bool:
        return self.status in registry.LOCKED_STATUSES

    @property
    def batching(self) -> str:
        """`daily_batch` = รวมข้อเสนอทั้งวันถามครั้งเดียว (มติผู้ใช้ 2026-08-13)"""
        return (self.baseline.get("approval") or {}).get("calibration_question_batching", "daily_batch")

    @property
    def review_categories(self) -> tuple[str, ...]:
        return tuple(self.baseline.get("review_categories") or ())

    def avoid_terms(self) -> list[dict]:
        """คำที่ต้องเลี่ยงทั้งหมด = ทะเบียนในโค้ด + ที่แพ็กเพิ่ม — รวมที่เดียวเท่านั้น

        รายการจากโค้ดได้ `severity: block` เพราะเป็นด่านของ `public_copy_validator` อยู่แล้ว
        ไม่ใช่แค่คำแนะนำเชิงบรรณาธิการ
        """
        return list(self._avoid_index)

    def glossary_avoid_map(self) -> dict[str, str | None]:
        """คำที่เลี่ยง → คำที่ควรใช้แทน (จาก glossary) · None = ไม่มีตัวแทนตายตัว"""
        mapping: dict[str, str | None] = {}
        for term in (self.glossary.get("terms") or {}).values():
            preferred = term.get("preferred")
            for word in term.get("avoid") or []:
                mapping[word] = preferred
        return mapping


def _read_json(path: Path) -> dict:
    if not path.is_file():
        raise LanguagePackError(f"แพ็กไม่ครบ — ไม่พบไฟล์ {path.name} ที่ {path.parent}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LanguagePackError(f"{path.name} อ่านไม่ได้: {exc}") from exc


def _build_avoid_index(avoid_pack: dict) -> list[dict]:
    inherited = avoid_pack.get("inherits_denylist") or {}
    severity = inherited.get("severity", "block")
    index: list[dict] = [
        {
            "phrase": phrase,
            "severity": severity,
            "reason": "อยู่ในทะเบียนคำต้องห้ามของ WCB Voice Spec (tools/voice_rules.VOICE_DENYLIST)",
            "suggest": None,
            "category": "internal_language",
            "source": "voice_rules",
        }
        for phrase in VOICE_DENYLIST
    ]
    known = {item["phrase"] for item in index}
    for entry in avoid_pack.get("phrases") or []:
        phrase = entry.get("phrase")
        if not phrase or phrase in known:
            # ซ้ำกับทะเบียนในโค้ด = ข้าม ไม่ใช่เพิ่มซ้ำ (เทสบังคับว่าไม่ควรมีตั้งแต่ต้น)
            continue
        index.append({
            "phrase": phrase,
            "severity": entry.get("severity", "warning"),
            "reason": entry.get("reason", ""),
            "suggest": entry.get("suggest"),
            "category": entry.get("category", "internal_language"),
            "source": "locale_pack",
        })
    # เรียงจากยาวไปสั้น เพื่อให้ตัวตรวจรายงานคำที่จำเพาะกว่าก่อนคำที่กว้างกว่า
    index.sort(key=lambda item: len(item["phrase"]), reverse=True)
    return index


def load_locale(locale: str = "th-TH", version: str | None = None,
                registry_path: Path | None = None, verify_hash: bool = True) -> LocalePack:
    """โหลดแพ็กที่ทะเบียนชี้

    `verify_hash=True` (ค่าเริ่มต้น) = ตรวจว่าแพ็กบนดิสก์ยังตรงกับ hash ที่บันทึกไว้
    ปิดได้เฉพาะตอนกำลังแก้แพ็กระหว่าง calibration ซึ่งไฟล์ขยับทุกครั้งที่บันทึก
    """
    info = registry.verify(locale, version, registry_path) if verify_hash \
        else registry.resolve(locale, version, registry_path)
    pack_dir = info["pack_dir"]
    if not pack_dir.is_dir():
        raise LocaleBaselineMissing(
            f"ทะเบียนชี้ไปที่ {pack_dir} แต่ไม่มีโฟลเดอร์นั้น — "
            "ห้ามใช้กฎของ locale อื่นแทนโดยเงียบ")

    parts = {key: _read_json(pack_dir / name) for key, name in PACK_FILES.items()}
    baseline = parts["baseline"]

    missing = [key for key in REQUIRED_BASELINE_KEYS if key not in baseline]
    if missing:
        raise LanguagePackError(f"baseline.json ขาดช่องที่จำเป็น: {', '.join(missing)}")
    if baseline["locale"] != locale:
        raise LanguagePackError(
            f"baseline.json บอกว่าเป็น locale {baseline['locale']!r} "
            f"แต่ทะเบียนวางไว้ใต้ {locale!r}")
    if baseline["version"] != info["version"]:
        raise LanguagePackError(
            f"baseline.json เป็นเวอร์ชัน {baseline['version']!r} "
            f"แต่ทะเบียนชี้ว่า {info['version']!r} — สองที่ต้องตรงกันเสมอ")

    approval = baseline.get("approval") or {}
    if approval.get("baseline_changes_require_user_approval") is not True:
        raise LanguagePackError(
            "baseline.approval.baseline_changes_require_user_approval ต้องเป็น true เสมอ — "
            "governance lock ของทั้งระบบตั้งอยู่บนข้อนี้")

    certainty = baseline.get("certainty") or {}
    if not (certainty.get("preserve_modality") and certainty.get("preserve_conditions")):
        raise LanguagePackError(
            "baseline.certainty ต้องรักษาทั้ง modality และ conditions — "
            "ระดับความมั่นใจกับเงื่อนไขเป็น Protected Content")

    return LocalePack(
        locale=locale,
        version=info["version"],
        status=info["status"],
        pack_dir=pack_dir,
        sha256=info.get("actual_sha256") or registry.pack_sha256(pack_dir),
        core=_read_json(CORE_PATH),
        baseline=baseline,
        glossary=parts["glossary"],
        preferred_phrases=parts["preferred_phrases"],
        avoid_phrases=parts["avoid_phrases"],
        sentence_patterns=parts["sentence_patterns"],
        regression_cases=parts["regression_cases"],
        _avoid_index=_build_avoid_index(parts["avoid_phrases"]),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="โหลดแพ็กภาษาและสรุปสิ่งที่โหลดได้")
    parser.add_argument("--locale", default="th-TH")
    parser.add_argument("--version", default=None)
    parser.add_argument("--no-verify-hash", action="store_true")
    args = parser.parse_args(argv)

    try:
        pack = load_locale(args.locale, args.version, verify_hash=not args.no_verify_hash)
    except BaselineError as exc:
        print(f"[{exc.code}] {exc}")
        return 1

    print(f"{pack.locale}@{pack.version} · สถานะ {pack.status} · ล็อกแล้ว={pack.is_locked}")
    print(f"  แพ็ก        : {pack.pack_dir}")
    print(f"  hash        : {pack.sha256}")
    print(f"  ถามอนุมัติ  : {pack.batching}")
    print(f"  หมวดที่ตรวจ : {len(pack.review_categories)} หมวด")
    print(f"  คำที่เลี่ยง  : {len(pack.avoid_terms())} รายการ "
          f"(จากโค้ด {len(VOICE_DENYLIST)} + จากแพ็ก {len(pack.avoid_terms()) - len(VOICE_DENYLIST)})")
    print(f"  ศัพท์กลาง   : {len(pack.glossary.get('terms') or {})} รายการ")
    print(f"  regression  : {len(pack.regression_cases.get('cases') or [])} เคส")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
