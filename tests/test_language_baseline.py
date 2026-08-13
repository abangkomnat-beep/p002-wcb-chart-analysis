"""ทะเบียนมาตรฐานภาษาและ governance lock

เทสชุดนี้เฝ้าสองอย่างที่พังเงียบที่สุดของระบบภาษา:
1. Agent หยิบเวอร์ชันผิดเพราะเดาจากชื่อไฟล์
2. Agent แก้ baseline ที่ล็อกแล้วเอง แล้วไม่มีร่องรอยว่าใครเปลี่ยนอะไร
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import baseline_registry as registry  # noqa: E402
from tools import locale_loader  # noqa: E402
from tools.voice_rules import VOICE_DENYLIST  # noqa: E402

LANGUAGE_DIR = Path(__file__).resolve().parents[1] / "language"
TH_PACK = LANGUAGE_DIR / "locales" / "th-TH"


def _outside_code_fences(text: str) -> list[str]:
    """บรรทัดที่อยู่นอกรั้ว ``` — ตัวอย่างรูปแบบในรั้วไม่ใช่เนื้อหาจริงของไฟล์"""
    lines, inside = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            inside = not inside
            continue
        if not inside:
            lines.append(line)
    return lines


class RegistryTests(unittest.TestCase):
    def test_default_version_resolves_and_pack_exists(self):
        info = registry.resolve("th-TH")
        self.assertTrue(info["pack_dir"].is_dir())
        self.assertIn(info["status"], registry.LIFECYCLE)

    def test_unknown_locale_is_missing_not_silent_fallback(self):
        """locale ที่ไม่มีต้องหยุด ไม่ใช่ยืมกฎของภาษาอื่นมาใช้เงียบ ๆ"""
        with self.assertRaises(registry.LocaleBaselineMissing) as ctx:
            registry.resolve("en-US")
        self.assertEqual(ctx.exception.code, "LOCALE_BASELINE_MISSING")

    def test_pack_hash_covers_every_file_and_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack"
            pack.mkdir()
            (pack / "a.json").write_text("{}", encoding="utf-8")
            (pack / "b.json").write_text("[]", encoding="utf-8")
            base = registry.pack_sha256(pack)

            (pack / "b.json").write_text("[1]", encoding="utf-8")
            self.assertNotEqual(base, registry.pack_sha256(pack),
                                "แก้ไฟล์ใดในแพ็กก็ต้องทำให้ hash เปลี่ยน")

            (pack / "b.json").write_text("[]", encoding="utf-8")
            self.assertEqual(base, registry.pack_sha256(pack))

            # สลับ *ชื่อ* ไฟล์โดยเนื้อเท่าเดิม ก็ต้องเป็นคนละแพ็ก
            (pack / "a.json").write_text("[]", encoding="utf-8")
            (pack / "b.json").write_text("{}", encoding="utf-8")
            self.assertNotEqual(base, registry.pack_sha256(pack))

    def test_line_ending_style_does_not_change_the_hash(self):
        """git แปลง LF ↔ CRLF ตอน checkout ตามค่าของแต่ละเครื่อง

        ถ้าแฮชนับ byte ดิบ แพ็กเดียวกันจะได้คนละแฮชระหว่าง Windows กับ Linux
        แล้ว `verify()` จะฟ้อง BASELINE_TAMPERED ทั้งที่ไม่มีใครแก้อะไร
        """
        with tempfile.TemporaryDirectory() as tmp:
            unix, windows = Path(tmp) / "unix", Path(tmp) / "windows"
            for folder, newline in ((unix, "\n"), (windows, "\r\n")):
                folder.mkdir()
                (folder / "baseline.json").write_bytes(
                    newline.join(['{', '  "a": 1', '}']).encode("utf-8"))
            self.assertEqual(registry.pack_sha256(unix), registry.pack_sha256(windows))

    def test_real_content_change_still_changes_the_hash(self):
        """ตาข่ายคู่กับเทสบน — ตัดเรื่องขึ้นบรรทัดทิ้งแล้วต้องไม่กลายเป็นตัดเนื้อหาทิ้งด้วย"""
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack"
            pack.mkdir()
            target = pack / "baseline.json"
            target.write_text('{"a": 1}', encoding="utf-8")
            before = registry.pack_sha256(pack)
            target.write_text('{"a": 2}', encoding="utf-8")
            self.assertNotEqual(before, registry.pack_sha256(pack))


class GovernanceLockTests(unittest.TestCase):
    """สำเนาทะเบียนจริงมาไว้ใน temp — เทสห้ามแตะทะเบียนของจริง"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.language = Path(self.tmp) / "language"
        shutil.copytree(LANGUAGE_DIR, self.language)
        self.registry_path = self.language / "baseline-registry.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _set_status(self, status: str, **extra):
        data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        record = data["locales"]["th-TH"]["versions"]["0.1.0"]
        record["status"] = status
        record.update(extra)
        self.registry_path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                      encoding="utf-8")

    def test_promote_to_stable_requires_approver(self):
        with self.assertRaises(registry.BaselineError):
            registry.promote("th-TH", "0.1.0", "stable_locked",
                             approved_by="", approved_at="", registry_path=self.registry_path)

    def test_locked_version_cannot_be_repromoted(self):
        registry.promote("th-TH", "0.1.0", "stable_locked", approved_by="user",
                         approved_at="2026-08-13", registry_path=self.registry_path)
        with self.assertRaises(registry.BaselineLockedError) as ctx:
            registry.promote("th-TH", "0.1.0", "candidate", approved_by="agent",
                             approved_at="2026-08-14", registry_path=self.registry_path)
        self.assertEqual(ctx.exception.code, "BASELINE_LOCKED")

    def test_locked_version_cannot_have_hash_refreshed(self):
        """ช่องโหว่ที่ต้องปิด: แก้ไฟล์แล้ว refresh hash = ทำให้การแก้ที่ไม่ได้อนุมัติถูกต้องย้อนหลัง"""
        registry.promote("th-TH", "0.1.0", "stable_locked", approved_by="user",
                         approved_at="2026-08-13", registry_path=self.registry_path)
        with self.assertRaises(registry.BaselineLockedError):
            registry.refresh_hash("th-TH", "0.1.0", registry_path=self.registry_path)

    def test_editing_locked_pack_is_detected(self):
        registry.promote("th-TH", "0.1.0", "stable_locked", approved_by="user",
                         approved_at="2026-08-13", registry_path=self.registry_path)
        glossary = self.language / "locales" / "th-TH" / "glossary.json"
        data = json.loads(glossary.read_text(encoding="utf-8"))
        data["terms"]["support"]["preferred"] = "แนวรับใหม่"
        glossary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        with self.assertRaises(registry.BaselineTamperedError) as ctx:
            registry.verify("th-TH", "0.1.0", registry_path=self.registry_path)
        self.assertEqual(ctx.exception.code, "BASELINE_TAMPERED")

    def test_candidate_without_hash_is_rejected(self):
        self._set_status("candidate", sha256=None)
        with self.assertRaises(registry.BaselineTamperedError):
            registry.verify("th-TH", "0.1.0", registry_path=self.registry_path)

    def test_calibrating_without_hash_is_allowed(self):
        """ช่วงปรับจูนแพ็กขยับทุกวัน การบังคับ hash ตอนนี้จะทำให้ทำงานไม่ได้"""
        self._set_status("calibrating", sha256=None)
        info = registry.verify("th-TH", "0.1.0", registry_path=self.registry_path)
        self.assertEqual(info["status"], "calibrating")


class PackContentTests(unittest.TestCase):
    def setUp(self):
        self.pack = locale_loader.load_locale("th-TH")

    def test_avoid_phrases_do_not_duplicate_the_code_denylist(self):
        """ทะเบียนคำต้องห้ามมีที่เดียว — คัดลอกซ้ำแล้วสองที่จะขัดกันเงียบ ๆ"""
        own = {entry["phrase"] for entry in self.pack.avoid_phrases.get("phrases") or []}
        duplicated = own & set(VOICE_DENYLIST)
        self.assertFalse(duplicated,
                         f"คำเหล่านี้อยู่ใน VOICE_DENYLIST อยู่แล้ว ห้ามเขียนซ้ำในแพ็ก: {duplicated}")

    def test_avoid_index_merges_both_sources(self):
        """รวมสองทะเบียน — คำที่หายไปจากการสืบทอดได้ ต้องเป็นข้อยกเว้นที่มี reason เท่านั้น"""
        merged = {entry["phrase"] for entry in self.pack.avoid_terms()}
        inherited = self.pack.avoid_phrases.get("inherits_denylist") or {}
        excepted = {entry["phrase"] for entry in inherited.get("exceptions") or []}
        for entry in inherited.get("exceptions") or []:
            self.assertTrue(entry.get("reason"),
                            f"ข้อยกเว้น {entry.get('phrase')!r} ไม่มีเหตุผล/มติกำกับ — "
                            "ช่องนี้ไม่ใช่ที่ปิดคำที่รำคาญเงียบ ๆ")
        self.assertTrue(set(VOICE_DENYLIST) - excepted <= merged)
        self.assertFalse(excepted & merged,
                         "คำที่ยกเว้นแล้วต้องไม่โผล่ในทะเบียนรวมอีก")
        self.assertIn("การนับหัว", merged)

    def test_glossary_preferred_terms_are_not_forbidden_words(self):
        """กันกฎที่ขัดกันเอง: แนะนำให้ใช้คำที่อีกด่านหนึ่งห้าม"""
        for name, term in (self.pack.glossary.get("terms") or {}).items():
            for candidate in [term.get("preferred"), *(term.get("allowed") or [])]:
                if not candidate:
                    continue
                for banned in VOICE_DENYLIST:
                    hit = banned in candidate.lower() if banned.isascii() else banned in candidate
                    self.assertFalse(hit, f"ศัพท์ {name}: {candidate!r} มีคำต้องห้าม {banned!r}")

    def test_certainty_and_approval_flags_cannot_be_switched_off(self):
        self.assertTrue(self.pack.baseline["certainty"]["preserve_modality"])
        self.assertTrue(self.pack.baseline["certainty"]["preserve_conditions"])
        self.assertTrue(self.pack.baseline["approval"]["baseline_changes_require_user_approval"])

    def test_calibration_asks_once_per_day(self):
        """มติผู้ใช้ 2026-08-13 — ห้ามถามทีละข้อ"""
        self.assertEqual(self.pack.batching, "daily_batch")

    def test_pack_declares_same_version_as_registry(self):
        self.assertEqual(self.pack.baseline["version"], self.pack.version)
        self.assertEqual(self.pack.baseline["status"], self.pack.status)

    def test_every_pack_file_is_present(self):
        for name in locale_loader.PACK_FILES.values():
            self.assertTrue((TH_PACK / name).is_file(), f"แพ็กขาดไฟล์ {name}")
        for name in ("approved-examples.md", "rejected-examples.md", "CHANGELOG.md"):
            self.assertTrue((TH_PACK / name).is_file(), f"แพ็กขาดไฟล์ {name}")

    def test_approved_examples_stay_empty_until_a_real_approval(self):
        """กันการเติมตัวอย่างที่ผู้ใช้ยังไม่ได้อนุมัติ — ทั้งแฟ้มจะใช้อ้างอิงไม่ได้ทันทีที่ปนของแต่ง

        นับเฉพาะหัวข้อนอกบล็อกโค้ด เพราะไฟล์มีตัวอย่าง *รูปแบบ* อยู่ในรั้ว ``` ซึ่งไม่ใช่รายการจริง
        """
        entries = [line for line in _outside_code_fences(
            (TH_PACK / "approved-examples.md").read_text(encoding="utf-8"))
            if line.startswith("### TH-EX-")]
        self.assertFalse(entries,
                         f"มีรายการตัวอย่างโผล่มา {entries} — ต้องมาจากการอนุมัติจริงเท่านั้น "
                         "ถ้าอนุมัติจริงแล้วให้แก้เทสนี้พร้อมอ้าง batch_id")


class SchemaFileTests(unittest.TestCase):
    """สคีมาเป็นสัญญาที่คนอ่าน — อย่างน้อยต้องเป็น JSON ที่ถูกต้องและมีช่องบังคับครบ"""

    def test_schemas_parse_and_lock_the_non_negotiable_fields(self):
        schemas = Path(__file__).resolve().parents[1] / "schemas"
        baseline = json.loads((schemas / "language-baseline-v1.schema.json").read_text(encoding="utf-8"))
        review = json.loads((schemas / "language-review-v1.schema.json").read_text(encoding="utf-8"))

        certainty = baseline["properties"]["certainty"]["properties"]
        self.assertEqual(certainty["preserve_modality"]["const"], True)
        self.assertEqual(certainty["preserve_conditions"]["const"], True)
        approval = baseline["properties"]["approval"]["properties"]
        self.assertEqual(approval["baseline_changes_require_user_approval"]["const"], True)

        for field in ("source_sha256", "baseline_sha256"):
            self.assertIn(field, review["required"],
                          "ผลตรวจต้องผูกกับทั้งต้นฉบับและแพ็ก ไม่งั้น apply ของเก่าทับของใหม่ได้")


if __name__ == "__main__":
    unittest.main()
