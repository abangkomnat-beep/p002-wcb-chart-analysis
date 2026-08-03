"""ด่านหยุดการเผยแพร่ — ครอบคลุม fatal rule ข้อ 1-5 ของ P002_FIX_INSTRUCTIONS

ข้อ 6 (cross-provider mismatch) อยู่นอกขอบเขตตามการตัดสินของผู้ใช้ 2026-08-03
ที่ไม่เพิ่มแหล่งข้อมูลที่สอง — ต้องระบุข้อจำกัดนี้ใน README
"""

from __future__ import annotations


VALIDATOR_VERSION = "1.0.0"

RULES = {
    1: "indicator_insufficient_bars",
    2: "pivot_uses_forming_candle",
    3: "pivot_uses_invalid_session",
    4: "crypto_daily_gap",
    5: "business_session_gap",
}


def _reason(rule: int, detail: str) -> dict:
    return {"rule": rule, "code": RULES[rule], "detail": detail}


def evaluate(
    *,
    indicators: dict,
    pivots: dict,
    gap_check: dict,
    anomalies: list[dict] | None = None,
    calendar=None,
    checked_at: str | None = None,
) -> dict:
    reasons: list[dict] = []
    warnings: list[str] = []

    for name, item in (indicators or {}).items():
        if item.get("value") is not None and item.get("status") != "available":
            reasons.append(_reason(1, (
                f"{name} มีค่าแต่สถานะเป็น {item.get('status')} "
                f"(ต้องการ {item.get('required_bars')} แท่ง มี {item.get('available_completed_bars')})"
            )))
        elif item.get("status") == "insufficient_data":
            warnings.append(
                f"{name} ข้อมูลไม่พอ ({item.get('available_completed_bars')}/{item.get('required_bars')}) "
                "จึงไม่คำนวณและไม่แสดงผล"
            )

    state = (pivots or {}).get("basis_candle_state")
    if state is not None and state != "closed":
        reasons.append(_reason(2, f"Pivot ใช้แท่งสถานะ {state}"))
    if (pivots or {}).get("quality_status") == "invalid":
        reasons.append(_reason(3, (pivots or {}).get("reason") or "ฐาน Pivot ไม่ถูกต้อง"))
    elif (pivots or {}).get("quality_status") == "warning":
        warnings.append((pivots or {}).get("reason") or "ฐาน Pivot มีข้อสังเกต")

    for anomaly in (anomalies or []):
        if anomaly.get("severity") != "fatal_for_publication":
            continue
        if anomaly.get("type", "").startswith("unexpected_"):
            reasons.append(_reason(3, (
                f"พบแท่งนอกปฏิทิน {anomaly.get('session_date')} ({anomaly.get('type')})"
            )))
        else:
            reasons.append(_reason(3, f"ข้อมูลผิดปกติ: {anomaly.get('type')} {anomaly.get('session_date')}"))

    if gap_check and gap_check.get("publication_blocked"):
        rule = 4 if calendar is not None and calendar.is_continuous else 5
        missing = ", ".join(gap_check.get("missing_sessions", [])) or "ไม่ระบุ"
        reasons.append(_reason(rule, f"ขาด session: {missing}"))
    elif gap_check and gap_check.get("status") == "warning":
        warnings.extend(gap_check.get("notes", []))

    # ตัดรายการซ้ำแต่คงลำดับเดิมไว้
    unique: list[dict] = []
    for item in reasons:
        if item not in unique:
            unique.append(item)

    return {
        "status": "fail" if unique else "pass",
        "reasons": unique,
        "warnings": warnings,
        "checked_at": checked_at,
        "validator_version": VALIDATOR_VERSION,
    }
