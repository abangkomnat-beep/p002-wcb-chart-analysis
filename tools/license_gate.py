"""ด่านสิทธิ์ข้อมูล — แยกจากด่านคุณภาพเนื้อหาโดยสิ้นเชิง

เนื้อหาดีแค่ไหนก็เผยแพร่ไม่ได้ถ้าสิทธิ์ข้อมูลยังไม่ชัด และสิทธิ์ครบก็ไม่ได้แปลว่าเนื้อหาผ่าน
ทั้งสองด่านต้องผ่านพร้อมกันเท่านั้นจึงจะได้ approved-for-publication
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "provider_license_registry.json"

HOLD_LICENSE = "hold-data-license-review"
HOLD_QUALITY = "hold-data-quality"
HOLD_CONTENT = "hold-content-qa"
APPROVED_INTERNAL = "approved-internal-only"
APPROVED_PUBLIC = "approved-for-publication"

UNKNOWN = "unknown"


def load_registry(path: Path | None = None) -> dict:
    return json.loads((path or CONFIG_PATH).read_text(encoding="utf-8"))


def _as_date(value):
    return date.fromisoformat(str(value)[:10]) if value else None


def check_provider(name: str, entry: dict, *, today: date, max_age_days: int) -> list[str]:
    """คืนรายการเหตุผลที่ทำให้เผยแพร่ไม่ได้ ว่างเปล่า = ผ่าน"""
    reasons: list[str] = []
    use_case = entry.get("use_case", {})

    for field in ("public_display", "commercial_use", "redistribution"):
        value = use_case.get(field, UNKNOWN)
        if value is True:
            continue
        if value is False:
            reasons.append(f"{name}: `{field}` ระบุว่าไม่อนุญาต")
        else:
            reasons.append(f"{name}: `{field}` ยังเป็น unknown — ต้องอ่านสัญญาจริงก่อน")

    verified_at = _as_date(entry.get("verified_at"))
    if verified_at is None:
        reasons.append(f"{name}: ยังไม่เคยบันทึกวันตรวจสัญญา")
    elif verified_at + timedelta(days=max_age_days) < today:
        reasons.append(f"{name}: ตรวจสัญญาครั้งล่าสุด {verified_at.isoformat()} เกิน {max_age_days} วันแล้ว")

    expiry_at = _as_date(entry.get("expiry_at"))
    if expiry_at is not None and expiry_at < today:
        reasons.append(f"{name}: สัญญาหมดอายุ {expiry_at.isoformat()}")

    return reasons


def evaluate(
    asset: str,
    *,
    registry: dict | None = None,
    today: date | None = None,
    content_qa_passed: bool = False,
    data_quality_passed: bool = False,
    providers: list[str] | None = None,
) -> dict:
    """`providers` ระบุเองได้เมื่อสินทรัพย์เดียวกันมาจากคนละแหล่งในคนละสาย

    ตาราง `asset_providers` ผูก 1 สินทรัพย์ต่อ 1 ชุด provider ซึ่งพอสำหรับสายเดียว
    แต่ `xauusd` ตอนนี้เดินสองสาย — สายภายในใช้ MT5 · สายเว็บใช้ snapshot API
    ถ้าไม่มีทางระบุ สายเว็บจะถูกตัดสินด้วยสิทธิ์ของ MT5 ซึ่งเป็นคนละสัญญากันคนละฉบับ
    """
    registry = registry or load_registry()
    today = today or date.today()
    policy = registry.get("review_policy", {})
    max_age_days = policy.get("max_age_days", 180)

    providers = providers or registry.get("asset_providers", {}).get(asset)
    if not providers:
        return {
            "clearance": HOLD_LICENSE,
            "providers": [],
            "license_reasons": [f"ยังไม่ได้ลงทะเบียนว่า {asset} ใช้ข้อมูลจาก provider ใด"],
            "attribution_required": [],
            "checked_at": today.isoformat(),
        }

    reasons: list[str] = []
    attribution: list[str] = []
    for name in providers:
        entry = registry.get("providers", {}).get(name)
        if entry is None:
            reasons.append(f"{name}: ไม่มีในทะเบียนสิทธิ์")
            continue
        reasons.extend(check_provider(name, entry, today=today, max_age_days=max_age_days))
        if entry.get("attribution_required") is True:
            attribution.append(name)
        elif entry.get("attribution_required") == UNKNOWN:
            reasons.append(f"{name}: ยังไม่รู้ว่าต้องให้เครดิตอย่างไร")

    if reasons:
        clearance = APPROVED_INTERNAL if (content_qa_passed and data_quality_passed) else HOLD_LICENSE
    elif not data_quality_passed:
        clearance = HOLD_QUALITY
    elif not content_qa_passed:
        clearance = HOLD_CONTENT
    else:
        clearance = APPROVED_PUBLIC

    return {
        "clearance": clearance,
        "providers": providers,
        "license_reasons": reasons,
        "attribution_required": attribution,
        "checked_at": today.isoformat(),
    }


def is_publishable(result: dict) -> bool:
    return result.get("clearance") == APPROVED_PUBLIC
