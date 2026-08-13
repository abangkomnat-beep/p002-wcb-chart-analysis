"""ตัวโหลดแพ็กภาษา — จุดที่ "พังเงียบ" ได้ง่ายที่สุดของทั้งระบบ

ความผิดพลาดที่อันตรายที่สุดของชั้นนี้ไม่ใช่การ crash แต่คือการ **โหลดกฎผิดชุดแล้วเดินต่อ**
เพราะบทที่ออกมาอ่านได้ปกติทุกอย่าง ไม่มีใครเห็นว่ามาตรฐานที่ใช้เป็นคนละตัว
เทสทุกข้อในไฟล์นี้จึงยืนยันว่า "ผิด = หยุด" ไม่ใช่ "ผิด = เตือนแล้วไปต่อ"
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

LANGUAGE_DIR = Path(__file__).resolve().parents[1] / "language"


class LoadRealPackTests(unittest.TestCase):
    def test_loads_the_version_the_registry_points_at(self):
        pack = locale_loader.load_locale("th-TH")
        info = registry.resolve("th-TH")
        self.assertEqual(pack.version, info["version"])
        self.assertEqual(pack.status, info["status"])

    def test_missing_locale_stops_instead_of_borrowing_another_language(self):
        with self.assertRaises(registry.LocaleBaselineMissing) as ctx:
            locale_loader.load_locale("es-LATAM")
        self.assertEqual(ctx.exception.code, "LOCALE_BASELINE_MISSING")

    def test_core_rules_are_language_neutral(self):
        """ไฟล์ core ห้ามมีคำของภาษาใดภาษาหนึ่ง ไม่งั้นการเพิ่มภาษาที่สองจะลากกฎไทยไปด้วย"""
        text = (LANGUAGE_DIR / "core" / "financial-editorial-core-v1.json").read_text(encoding="utf-8")
        core = json.loads(text)
        for key in ("principles", "protected_content", "rule_precedence", "lifecycle"):
            for value in core[key]:
                self.assertTrue(value.isascii(),
                                f"ค่าใน core.{key} ต้องเป็นรหัสที่ไม่ผูกภาษา แต่พบ {value!r}")

    def test_pack_exposes_merged_avoid_list_and_glossary_map(self):
        pack = locale_loader.load_locale("th-TH")
        self.assertGreater(len(pack.avoid_terms()), 0)
        self.assertEqual(pack.glossary_avoid_map().get("การนับหัว"), "จำนวนสัญญาณ")

    def test_longer_phrases_are_reported_before_shorter_ones(self):
        """เรียงยาวไปสั้น เพื่อให้ผู้ใช้เห็นคำที่จำเพาะกว่า ไม่ใช่ชิ้นส่วนของมัน"""
        lengths = [len(item["phrase"]) for item in locale_loader.load_locale("th-TH").avoid_terms()]
        self.assertEqual(lengths, sorted(lengths, reverse=True))


class BrokenPackTests(unittest.TestCase):
    """ทุกเคสทำกับสำเนาใน temp — ห้ามแตะแพ็กจริง"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.language = Path(self.tmp) / "language"
        shutil.copytree(LANGUAGE_DIR, self.language)
        self.registry_path = self.language / "baseline-registry.json"
        self.pack_dir = self.language / "locales" / "th-TH"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _edit_baseline(self, **changes):
        path = self.pack_dir / "baseline.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data.update(changes)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load(self):
        return locale_loader.load_locale("th-TH", registry_path=self.registry_path,
                                         verify_hash=False)

    def test_version_mismatch_between_pack_and_registry_is_refused(self):
        self._edit_baseline(version="9.9.9")
        with self.assertRaises(locale_loader.LanguagePackError):
            self._load()

    def test_locale_mismatch_is_refused(self):
        self._edit_baseline(locale="en-US")
        with self.assertRaises(locale_loader.LanguagePackError):
            self._load()

    def test_turning_off_user_approval_is_refused(self):
        """governance lock ทั้งระบบตั้งอยู่บนธงนี้ — ปิดได้เมื่อไหร่ก็ไม่เหลืออะไรให้ล็อก"""
        self._edit_baseline(approval={"baseline_changes_require_user_approval": False})
        with self.assertRaises(locale_loader.LanguagePackError):
            self._load()

    def test_turning_off_certainty_guard_is_refused(self):
        self._edit_baseline(certainty={"preserve_modality": False, "preserve_conditions": True})
        with self.assertRaises(locale_loader.LanguagePackError):
            self._load()

    def test_missing_pack_file_is_refused(self):
        (self.pack_dir / "glossary.json").unlink()
        with self.assertRaises(locale_loader.LanguagePackError):
            self._load()

    def test_missing_required_baseline_key_is_refused(self):
        path = self.pack_dir / "baseline.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        del data["reader_profile"]
        del data["certainty"]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        with self.assertRaises(locale_loader.LanguagePackError):
            self._load()

    def test_registry_pointing_at_a_missing_folder_is_refused(self):
        shutil.rmtree(self.pack_dir)
        with self.assertRaises(registry.LocaleBaselineMissing):
            self._load()


if __name__ == "__main__":
    unittest.main()
