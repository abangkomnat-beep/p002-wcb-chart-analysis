import hashlib
import json
import re
import unittest
from pathlib import Path

from tools import locale_loader
from tools.bootstrap_multilingual_locales import (
    CLDR_COMMIT,
    CLDR_VERSION,
    MASTER_LOCALES,
    SOURCE_RANK_BY_CODE,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = REPO_ROOT.parent
LANGUAGE_DIR = REPO_ROOT / "language"
REGISTRY_PATH = LANGUAGE_DIR / "baseline-registry.json"
COUNTRY_REGISTRY_PATH = LANGUAGE_DIR / "country-locale-registry.json"
VENDOR_ROOT = LANGUAGE_DIR / "vendor" / f"unicode-cldr-{CLDR_VERSION}"


class MultilingualRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        cls.country_registry = json.loads(COUNTRY_REGISTRY_PATH.read_text(encoding="utf-8"))
        cls.foreign_locales = {item["locale"] for item in MASTER_LOCALES}

    def test_registry_has_thai_plus_exactly_19_foreign_language_packs(self):
        self.assertEqual(set(self.registry["locales"]), self.foreign_locales | {"th-TH"})
        self.assertEqual(len(self.foreign_locales), 19)

    def test_all_foreign_packs_are_draft_and_load_without_thai_fallback(self):
        for locale in sorted(self.foreign_locales):
            with self.subTest(locale=locale):
                pack = locale_loader.load_locale(locale)
                self.assertEqual(pack.status, "draft")
                self.assertEqual(pack.baseline["translation_scope"]["mode"],
                                 "translation_and_localization_only")
                self.assertFalse(pack.baseline["translation_scope"]["may_add_or_remove_claims"])
                self.assertFalse(pack.baseline["translation_scope"]["may_research_or_add_market_context"])
                self.assertEqual(pack.avoid_terms(), [],
                                 "foreign pack must not inherit Thai VOICE_DENYLIST")

    def test_country_registry_has_33_unique_countries_and_routes_every_pack(self):
        countries = self.country_registry["countries"]
        self.assertEqual(self.country_registry["country_count"], 33)
        self.assertEqual(len(countries), 33)
        self.assertEqual(len({item["country_code"] for item in countries}), 33)
        self.assertEqual(sum(item["country_code"] != "TH" for item in countries), 32)
        for item in countries:
            with self.subTest(country=item["country_code"]):
                self.assertIn(item["language_pack"], self.registry["locales"])
                self.assertTrue(item["economic_city"])
                self.assertIn("/", item["timezone"])
        self.assertEqual(self.country_registry["publish_window_local"],
                         {"start": "06:00", "end": "08:00"})

    def test_country_selection_rank_priority_and_language_are_sheet_grounded(self):
        countries = self.country_registry["countries"]
        self.assertEqual(self.country_registry["source_sheet_id"],
                         "1xLO1Rn3hcxFnnsCqiU1LE9bMJ9_RZNtSkKeql_icROs")
        self.assertEqual(self.country_registry["source_tab"], "ประเทศ ภาษา ความสำคัญ")
        self.assertEqual(self.country_registry["source_gid"], 59868993)
        self.assertEqual([item["source_rank"] for item in countries],
                         sorted(SOURCE_RANK_BY_CODE.values()))
        self.assertTrue(all(item["source_priority"] == "ต้องทำหลัก" for item in countries))
        top_five_packs = {"en-001", "ar-001", "es-419", "sw-KE", "zh-Hant"}
        self.assertEqual(sum(item["language_pack"] in top_five_packs for item in countries), 18)

    def test_job_schema_accepts_all_pack_and_country_locale_tags(self):
        schema = json.loads((REPO_ROOT / "schemas" / "analysis-job-v1.schema.json").read_text(encoding="utf-8"))
        pattern = schema["$defs"]["languageContract"]["properties"]["locale"]["pattern"]
        regex = re.compile(pattern)
        tags = self.foreign_locales | {
            item["content_locale"] for item in self.country_registry["countries"]
        }
        rejected = sorted(tag for tag in tags if not regex.fullmatch(tag))
        self.assertEqual(rejected, [])


class LocaleSkillTests(unittest.TestCase):
    def test_agent_08_registers_the_translation_only_skill(self):
        skill = REPO_ROOT / ".claude" / "skills" / "localize-financial-analysis" / "SKILL.md"
        registry = PROJECT_ROOT / "Agents" / "08-Language-Editorial" / "SKILLS.md"
        self.assertTrue(skill.is_file())
        self.assertIn("localize-financial-analysis", registry.read_text(encoding="utf-8"))
        text = skill.read_text(encoding="utf-8")
        self.assertIn("ไม่ใช่ analysis generation", text)
        self.assertIn("ค้นข่าว ค้นราคา", text)


class CldrVendorTests(unittest.TestCase):
    def test_pinned_cldr_data_and_checksums_are_complete(self):
        manifest = json.loads((VENDOR_ROOT / "source-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["release"], CLDR_VERSION)
        self.assertEqual(manifest["commit"], CLDR_COMMIT)
        self.assertEqual(manifest["license"], "Unicode-3.0")
        self.assertEqual(len(manifest["files"]), 2 + (2 * len(MASTER_LOCALES)))
        for record in manifest["files"]:
            with self.subTest(path=record["path"]):
                path = VENDOR_ROOT / record["path"]
                self.assertTrue(path.is_file())
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record["sha256"])


if __name__ == "__main__":
    unittest.main()
