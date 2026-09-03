"""สร้าง Locale Pack draft 19 ภาษาและทะเบียน 33 ประเทศแบบ deterministic.

สคริปต์นี้เตรียมโครงและ routing เท่านั้น ไม่แปลบท ไม่สร้างศัพท์การเงินที่ยังไม่ผ่าน
calibration และไม่เลื่อนสถานะเป็น candidate/stable_locked.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LANGUAGE_DIR = REPO_ROOT / "language"
REGISTRY_PATH = LANGUAGE_DIR / "baseline-registry.json"
COUNTRY_REGISTRY_PATH = LANGUAGE_DIR / "country-locale-registry.json"
PACK_VERSION = "0.1.0"
CLDR_VERSION = "48.2.0"
CLDR_COMMIT = "bb334e8d6250c9363e957e131bf7e6d08ec72f91"


MASTER_LOCALES = (
    {"locale": "en-001", "cldr": "en", "language": "English", "native": "English", "script": "Latn", "direction": "ltr", "countries": ["ZA", "NG", "SG", "GH", "BW"]},
    {"locale": "ar-001", "cldr": "ar", "language": "Arabic", "native": "العربية", "script": "Arab", "direction": "rtl", "countries": ["AE", "EG", "SA", "DZ", "MA"]},
    {"locale": "es-419", "cldr": "es-419", "language": "Spanish", "native": "Español", "script": "Latn", "direction": "ltr", "countries": ["MX", "CO", "CL"]},
    {"locale": "sw-KE", "cldr": "sw", "language": "Swahili", "native": "Kiswahili", "script": "Latn", "direction": "ltr", "countries": ["KE", "TZ", "UG"]},
    {"locale": "zh-Hant", "cldr": "zh-Hant", "language": "Traditional Chinese", "native": "繁體中文", "script": "Hant", "direction": "ltr", "countries": ["TW", "HK"]},
    {"locale": "zh-Hans", "cldr": "zh", "language": "Simplified Chinese", "native": "简体中文", "script": "Hans", "direction": "ltr", "countries": ["CN"]},
    {"locale": "hi-IN", "cldr": "hi", "language": "Hindi", "native": "हिन्दी", "script": "Deva", "direction": "ltr", "countries": ["IN"]},
    {"locale": "id-ID", "cldr": "id", "language": "Indonesian", "native": "Bahasa Indonesia", "script": "Latn", "direction": "ltr", "countries": ["ID"]},
    {"locale": "ja-JP", "cldr": "ja", "language": "Japanese", "native": "日本語", "script": "Jpan", "direction": "ltr", "countries": ["JP"]},
    {"locale": "pt-BR", "cldr": "pt", "language": "Portuguese", "native": "Português (Brasil)", "script": "Latn", "direction": "ltr", "countries": ["BR"]},
    {"locale": "ur-PK", "cldr": "ur", "language": "Urdu", "native": "اردو", "script": "Arab", "direction": "rtl", "countries": ["PK"]},
    {"locale": "ru-RU", "cldr": "ru", "language": "Russian", "native": "Русский", "script": "Cyrl", "direction": "ltr", "countries": ["RU"]},
    {"locale": "bn-BD", "cldr": "bn", "language": "Bengali", "native": "বাংলা", "script": "Beng", "direction": "ltr", "countries": ["BD"]},
    {"locale": "tr-TR", "cldr": "tr", "language": "Turkish", "native": "Türkçe", "script": "Latn", "direction": "ltr", "countries": ["TR"]},
    {"locale": "fil-PH", "cldr": "fil", "language": "Filipino / Tagalog", "native": "Filipino", "script": "Latn", "direction": "ltr", "countries": ["PH"]},
    {"locale": "ko-KR", "cldr": "ko", "language": "Korean", "native": "한국어", "script": "Kore", "direction": "ltr", "countries": ["KR"]},
    {"locale": "am-ET", "cldr": "am", "language": "Amharic", "native": "አማርኛ", "script": "Ethi", "direction": "ltr", "countries": ["ET"]},
    {"locale": "ms-MY", "cldr": "ms", "language": "Malay", "native": "Bahasa Melayu", "script": "Latn", "direction": "ltr", "countries": ["MY"]},
    {"locale": "si-LK", "cldr": "si", "language": "Sinhala", "native": "සිංහල", "script": "Sinh", "direction": "ltr", "countries": ["LK"]},
)


COUNTRIES = (
    ("TH", "Thailand", "ไทย", "th-TH", "th-TH", "Bangkok", "Asia/Bangkok", "source"),
    ("ZA", "South Africa", "แอฟริกาใต้", "en-ZA", "en-001", "Johannesburg", "Africa/Johannesburg", "A"),
    ("NG", "Nigeria", "ไนจีเรีย", "en-NG", "en-001", "Lagos", "Africa/Lagos", "A"),
    ("SG", "Singapore", "สิงคโปร์", "en-SG", "en-001", "Singapore", "Asia/Singapore", "A"),
    ("GH", "Ghana", "กานา", "en-GH", "en-001", "Accra", "Africa/Accra", "A"),
    ("BW", "Botswana", "บอตสวานา", "en-BW", "en-001", "Gaborone", "Africa/Gaborone", "A"),
    ("AE", "United Arab Emirates", "สหรัฐอาหรับเอมิเรตส์", "ar-AE", "ar-001", "Dubai", "Asia/Dubai", "A"),
    ("EG", "Egypt", "อียิปต์", "ar-EG", "ar-001", "Cairo", "Africa/Cairo", "A"),
    ("SA", "Saudi Arabia", "ซาอุดีอาระเบีย", "ar-SA", "ar-001", "Riyadh", "Asia/Riyadh", "A"),
    ("DZ", "Algeria", "แอลจีเรีย", "ar-DZ", "ar-001", "Algiers", "Africa/Algiers", "A"),
    ("MA", "Morocco", "โมร็อกโก", "ar-MA", "ar-001", "Casablanca", "Africa/Casablanca", "A"),
    ("MX", "Mexico", "เม็กซิโก", "es-MX", "es-419", "Mexico City", "America/Mexico_City", "B"),
    ("CO", "Colombia", "โคลอมเบีย", "es-CO", "es-419", "Bogotá", "America/Bogota", "B"),
    ("CL", "Chile", "ชิลี", "es-CL", "es-419", "Santiago", "America/Santiago", "B"),
    ("KE", "Kenya", "เคนยา", "sw-KE", "sw-KE", "Nairobi", "Africa/Nairobi", "B"),
    ("TZ", "Tanzania", "แทนซาเนีย", "sw-TZ", "sw-KE", "Dar es Salaam", "Africa/Dar_es_Salaam", "B"),
    ("UG", "Uganda", "ยูกันดา", "sw-UG", "sw-KE", "Kampala", "Africa/Kampala", "B"),
    ("TW", "Taiwan", "ไต้หวัน", "zh-Hant-TW", "zh-Hant", "Taipei", "Asia/Taipei", "B"),
    ("HK", "Hong Kong", "ฮ่องกง", "zh-Hant-HK", "zh-Hant", "Hong Kong", "Asia/Hong_Kong", "B"),
    ("CN", "China", "จีน", "zh-Hans-CN", "zh-Hans", "Shanghai", "Asia/Shanghai", "C"),
    ("IN", "India", "อินเดีย", "hi-IN", "hi-IN", "Mumbai", "Asia/Kolkata", "C"),
    ("ID", "Indonesia", "อินโดนีเซีย", "id-ID", "id-ID", "Jakarta", "Asia/Jakarta", "C"),
    ("JP", "Japan", "ญี่ปุ่น", "ja-JP", "ja-JP", "Tokyo", "Asia/Tokyo", "C"),
    ("BR", "Brazil", "บราซิล", "pt-BR", "pt-BR", "São Paulo", "America/Sao_Paulo", "C"),
    ("PK", "Pakistan", "ปากีสถาน", "ur-PK", "ur-PK", "Karachi", "Asia/Karachi", "C"),
    ("RU", "Russia", "รัสเซีย", "ru-RU", "ru-RU", "Moscow", "Europe/Moscow", "C"),
    ("BD", "Bangladesh", "บังกลาเทศ", "bn-BD", "bn-BD", "Dhaka", "Asia/Dhaka", "D"),
    ("TR", "Türkiye", "ตุรกี", "tr-TR", "tr-TR", "Istanbul", "Europe/Istanbul", "D"),
    ("PH", "Philippines", "ฟิลิปปินส์", "fil-PH", "fil-PH", "Manila", "Asia/Manila", "D"),
    ("KR", "South Korea", "เกาหลีใต้", "ko-KR", "ko-KR", "Seoul", "Asia/Seoul", "D"),
    ("ET", "Ethiopia", "เอธิโอเปีย", "am-ET", "am-ET", "Addis Ababa", "Africa/Addis_Ababa", "D"),
    ("MY", "Malaysia", "มาเลเซีย", "ms-MY", "ms-MY", "Kuala Lumpur", "Asia/Kuala_Lumpur", "D"),
    ("LK", "Sri Lanka", "ศรีลังกา", "si-LK", "si-LK", "Colombo", "Asia/Colombo", "D"),
)

# ลำดับจากแท็บ "ประเทศ ภาษา ความสำคัญ" โดยตรง ห้ามเรียงจากแหล่งออนไลน์
SOURCE_RANK_BY_CODE = {
    "ZA": 1, "CN": 2, "IN": 3, "ID": 4, "NG": 5, "JP": 6, "BR": 7,
    "PK": 8, "RU": 9, "MX": 10, "BD": 11, "TR": 12, "PH": 13,
    "KR": 14, "KE": 15, "TH": 16, "AE": 17, "ET": 18, "MY": 19,
    "EG": 20, "CO": 21, "SA": 22, "SG": 23, "TZ": 24, "TW": 25,
    "GH": 27, "UG": 28, "DZ": 29, "MA": 32, "CL": 34, "HK": 36,
    "LK": 42, "BW": 66,
}


PROTECTED_GLOSSARY = {
    "XAUUSD": {"preferred": "XAUUSD", "protected": True},
    "BTCUSD": {"preferred": "BTCUSD", "protected": True},
    "WTI": {"preferred": "WTI", "protected": True},
    "EURUSD": {"preferred": "EURUSD", "protected": True},
    "GBPUSD": {"preferred": "GBPUSD", "protected": True},
    "USDJPY": {"preferred": "USDJPY", "protected": True},
    "AUDUSD": {"preferred": "AUDUSD", "protected": True},
    "USDCAD": {"preferred": "USDCAD", "protected": True},
    "D1": {"preferred": "D1", "protected": True},
    "H1": {"preferred": "H1", "protected": True},
}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _pack_files(item: dict) -> dict[str, str | dict]:
    locale = item["locale"]
    source = {
        "provider": "Unicode CLDR JSON",
        "version": CLDR_VERSION,
        "commit": CLDR_COMMIT,
        "cldr_locale": item["cldr"],
        "scope": "locale identifiers, dates, numbers and writing-system metadata only",
    }
    baseline = {
        "baseline_id": f"{locale}-financial-analysis",
        "version": PACK_VERSION,
        "status": "draft",
        "locale": locale,
        "inherits_core": "financial-editorial-core@1.0.0",
        "language": {"english_name": item["language"], "native_name": item["native"]},
        "writing_system": {"script": item["script"], "direction": item["direction"]},
        "reader_profile": {
            "level": "general_to_intermediate_investor",
            "description": "ผู้อ่านบทวิเคราะห์ตลาดทั่วไปถึงระดับกลางใน locale เป้าหมาย",
            "technical_term_policy": "รักษาสัญลักษณ์สากล; ศัพท์ภาษาปลายทางต้องผ่าน calibration ก่อนล็อก",
        },
        "translation_scope": {
            "mode": "translation_and_localization_only",
            "source_locale": "th-TH",
            "may_rephrase_for_naturalness": True,
            "may_add_or_remove_claims": False,
            "may_change_protected_content": False,
            "may_research_or_add_market_context": False,
        },
        "principles": [
            "ใช้ไวยากรณ์และลำดับคำธรรมชาติของภาษาปลายทาง ไม่แปลคำต่อคำ",
            "รักษาจำนวน Claim ตัวเลข ทิศทาง กรอบเวลา ความมั่นใจ และเงื่อนไขเท่าต้นฉบับ",
            "ห้ามเติมข้อมูล ราคา เหตุผล หรือมุมมองตลาดจากความรู้ของผู้แปล",
            "รักษาน้ำเสียงบทวิเคราะห์ที่เป็นทางการ กระชับ และอ่านสแกนได้",
            "ใช้รูปวันที่ ตัวเลข เครื่องหมายวรรคตอน และทิศทางข้อความตาม locale reference",
        ],
        "review_categories": [
            "natural_target_language", "literal_translation", "financial_semantics",
            "certainty", "conditionality", "causal_overreach", "term_consistency",
            "number_date_format", "source_language_residue", "sentence_repetition",
        ],
        "certainty": {
            "preserve_modality": True,
            "preserve_conditions": True,
            "note": "ห้ามยกระดับหรือลดระดับความมั่นใจเพื่อทำให้ภาษาอ่านลื่น",
        },
        "length_policy": {
            "status": "calibration_required",
            "note": "ห้ามใช้เพดานคำภาษาไทยกับ locale นี้จนมี corpus จริง",
        },
        "locale_reference": source,
        "approval": {
            "baseline_changes_require_user_approval": True,
            "calibration_question_batching": "daily_batch",
        },
    }
    glossary = {
        "locale": locale,
        "version": PACK_VERSION,
        "status": "draft",
        "note": "ล็อกเฉพาะสัญลักษณ์สากล ศัพท์ภาษาปลายทางยังต้องเสนอเป็น calibration batch",
        "terms": {key: {**value, "allowed": [], "avoid": []} for key, value in PROTECTED_GLOSSARY.items()},
        "concepts_requiring_calibration": [
            "trend", "momentum", "volatility", "support", "resistance", "breakout",
            "close", "scenario", "confirmation", "invalidation", "timeframe",
        ],
    }
    preferred = {
        "locale": locale, "version": PACK_VERSION, "status": "draft", "patterns": [],
        "note": "ยังไม่มี pattern ที่ผู้ใช้ออนุมัติ ห้ามนำประโยคจาก locale อื่นมาแทน",
    }
    avoid = {
        "locale": locale, "version": PACK_VERSION,
        "inherits_denylist": {
            "enabled": False,
            "severity": "warning",
            "exceptions": [],
            "reason": "VOICE_DENYLIST ปัจจุบันเป็นภาษาไทย จึงห้ามใช้กับแพ็กภาษาต่างประเทศ",
        },
        "phrases": [],
    }
    patterns = {
        "locale": locale, "version": PACK_VERSION, "status": "draft",
        "script": item["script"], "direction": item["direction"],
        "cldr_reference": source,
        "rules": [
            "use_target_language_native_syntax",
            "preserve_paragraph_claim_order_unless_reordering_keeps_all_links_explicit",
            "avoid_repeating_one_sentence_template_across_paragraphs",
            "apply_locale_specific_punctuation_and_spacing",
            "do_not_apply_thai_word_count_limits",
        ],
    }
    regression = {
        "locale": locale, "version": PACK_VERSION, "status": "draft",
        "cases": [{
            "id": f"{locale}-protected-roundtrip-001",
            "source": "[[CLAIM:C1]] XAUUSD D1 [[LEVEL:SUPPORT_1]] [[MODALITY:CONDITIONAL]]",
            "must_preserve": ["[[CLAIM:C1]]", "XAUUSD", "D1", "[[LEVEL:SUPPORT_1]]", "[[MODALITY:CONDITIONAL]]"],
            "note": "behavioral target text จะเพิ่มหลัง calibration; เคสนี้ล็อกเฉพาะ contract ขั้นต้น",
        }],
    }
    approved = f"# Approved examples — {locale}\n\nยังไม่มีตัวอย่างที่ผู้ใช้ออนุมัติ · copy_allowed: false\n"
    rejected = f"# Rejected examples — {locale}\n\nยังไม่มีรายการ · ใช้บันทึกพร้อมเหตุผลหลัง calibration\n"
    changelog = (
        f"# Changelog — {locale}\n\n"
        f"## {PACK_VERSION} · 2026-09-02\n\n"
        "- สร้าง draft scaffold สำหรับ translation/localization only\n"
        f"- ผูก Unicode CLDR {CLDR_VERSION} commit `{CLDR_COMMIT}`\n"
        "- ยังไม่อนุมัติศัพท์หรือรูปประโยคภาษาปลายทาง\n"
    )
    return {
        "baseline.json": baseline,
        "glossary.json": glossary,
        "preferred-phrases.json": preferred,
        "avoid-phrases.json": avoid,
        "sentence-patterns.json": patterns,
        "regression-cases.json": regression,
        "approved-examples.md": approved,
        "rejected-examples.md": rejected,
        "CHANGELOG.md": changelog,
    }


def _country_registry() -> dict:
    direction_by_pack = {item["locale"]: item["direction"] for item in MASTER_LOCALES}
    direction_by_pack["th-TH"] = "ltr"
    return {
        "registry_version": "1.0.0",
        "updated_at": "2026-09-02",
        "status": "draft",
        "source_sheet": "https://docs.google.com/spreadsheets/d/1xLO1Rn3hcxFnnsCqiU1LE9bMJ9_RZNtSkKeql_icROs/edit?gid=59868993#gid=59868993",
        "source_sheet_id": "1xLO1Rn3hcxFnnsCqiU1LE9bMJ9_RZNtSkKeql_icROs",
        "source_tab": "ประเทศ ภาษา ความสำคัญ",
        "source_gid": 59868993,
        "source_columns": "A:D",
        "source_of_truth_fields": ["country selection", "source rank", "priority", "language"],
        "technical_supplement_fields": ["economic_city", "timezone", "content_locale", "rollout_wave"],
        "source_locale": "th-TH",
        "foreign_language_pack_count": len(MASTER_LOCALES),
        "country_count": len(COUNTRIES),
        "publish_window_local": {"start": "06:00", "end": "08:00"},
        "countries": [
            {
                "country_code": code,
                "country_name_en": name_en,
                "country_name_th": name_th,
                "source_rank": SOURCE_RANK_BY_CODE[code],
                "source_priority": "ต้องทำหลัก",
                "content_locale": content_locale,
                "language_pack": pack,
                "economic_city": city,
                "timezone": timezone,
                "direction": direction_by_pack[pack],
                "rollout_wave": wave,
            }
            for code, name_en, name_th, content_locale, pack, city, timezone, wave
            in sorted(COUNTRIES, key=lambda row: SOURCE_RANK_BY_CODE[row[0]])
        ],
    }


def sync_country_registry() -> None:
    """อัปเดตเฉพาะทะเบียนที่สร้างจากชีต โดยไม่แตะ Locale Pack อื่น."""
    _write_json(COUNTRY_REGISTRY_PATH, _country_registry())


def bootstrap() -> None:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    existing = set((registry.get("locales") or {}).keys())
    conflicts = sorted(existing & {item["locale"] for item in MASTER_LOCALES})
    if conflicts:
        raise RuntimeError(f"locale มีอยู่แล้ว ห้ามเขียนทับ: {', '.join(conflicts)}")
    if COUNTRY_REGISTRY_PATH.exists():
        raise RuntimeError(f"มี {COUNTRY_REGISTRY_PATH.name} แล้ว ห้ามเขียนทับ")

    with tempfile.TemporaryDirectory(prefix="p002-locale-bootstrap-") as tmp:
        temp_root = Path(tmp)
        for item in MASTER_LOCALES:
            pack_dir = temp_root / item["locale"]
            for filename, payload in _pack_files(item).items():
                path = pack_dir / filename
                if isinstance(payload, dict):
                    _write_json(path, payload)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(payload, encoding="utf-8")

        for item in MASTER_LOCALES:
            locale = item["locale"]
            target = LANGUAGE_DIR / "locales" / locale
            if target.exists():
                raise RuntimeError(f"โฟลเดอร์มีอยู่แล้ว ห้ามเขียนทับ: {target}")
            shutil.copytree(temp_root / locale, target)

    for item in MASTER_LOCALES:
        locale = item["locale"]
        registry["locales"][locale] = {
            "default": PACK_VERSION,
            "versions": {
                PACK_VERSION: {
                    "status": "draft",
                    "path": f"locales/{locale}",
                    "baseline_id": f"{locale}-financial-analysis",
                    "approved_by": None,
                    "approved_at": None,
                    "parent_version": None,
                    "sha256": None,
                }
            },
        }
    registry["registry_version"] = "1.1.0"
    registry["note"] = (
        registry.get("note", "")
        + " · เพิ่ม 19 foreign locale packs สถานะ draft เมื่อ 2026-09-02; ยังห้าม production"
    )
    _write_json(REGISTRY_PATH, registry)
    _write_json(COUNTRY_REGISTRY_PATH, _country_registry())


def check() -> None:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    country_registry = json.loads(COUNTRY_REGISTRY_PATH.read_text(encoding="utf-8"))
    expected = {item["locale"] for item in MASTER_LOCALES}
    actual = set((registry.get("locales") or {}).keys()) - {"th-TH"}
    if actual != expected:
        raise RuntimeError(f"registry locale mismatch: missing={sorted(expected-actual)} extra={sorted(actual-expected)}")
    if country_registry.get("country_count") != 33 or len(country_registry.get("countries") or []) != 33:
        raise RuntimeError("country registry ต้องมี 33 ประเทศ")
    ranks = [item.get("source_rank") for item in country_registry["countries"]]
    if ranks != sorted(SOURCE_RANK_BY_CODE.values()):
        raise RuntimeError("country registry ต้องเรียงตามลำดับใน source sheet")
    if any(item.get("source_priority") != "ต้องทำหลัก" for item in country_registry["countries"]):
        raise RuntimeError("country registry ต้องมีเฉพาะประเทศระดับ ต้องทำหลัก")
    for item in MASTER_LOCALES:
        pack_dir = LANGUAGE_DIR / "locales" / item["locale"]
        missing = [name for name in _pack_files(item) if not (pack_dir / name).is_file()]
        if missing:
            raise RuntimeError(f"{item['locale']} ขาดไฟล์: {missing}")
    print(f"READY: {len(expected)} foreign locale packs | 33 countries | status=draft")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--sync-country-registry", action="store_true")
    args = parser.parse_args(argv)
    if args.sync_country_registry:
        sync_country_registry()
        check()
    elif args.check:
        check()
    else:
        bootstrap()
        check()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
