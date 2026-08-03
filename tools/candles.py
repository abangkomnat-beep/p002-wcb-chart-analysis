"""แปลงแถว OHLC ดิบให้เป็นแท่งเทียนที่รู้สถานะตัวเอง

กติกาสำคัญ:
- ไม่ลบแท่งที่ผิดปฏิทินทิ้งเงียบ ๆ — ติดธง is_expected_session=False และบันทึก anomaly เสมอ
- แท่งสุดท้ายถือเป็น forming จนกว่าผู้เรียกจะยืนยันว่าปิดแล้ว (ค่าปลอดภัยที่สุด)
- เฉพาะแท่งที่ expected + closed เท่านั้นที่นำไปคำนวณ indicator และ pivot ได้
"""

from __future__ import annotations


FATAL = "fatal_for_publication"
WARNING = "warning"


def normalize_ohlc(row: dict) -> tuple[dict, list[str]]:
    """กันไม่ให้ quote ที่อัปเดตไม่พร้อมกันดัน open/close ออกนอกกรอบแท่ง"""
    notes: list[str] = []
    high = max(float(row["high"]), float(row["open"]), float(row["close"]))
    low = min(float(row["low"]), float(row["open"]), float(row["close"]))
    if high != float(row["high"]):
        notes.append("high ถูกขยายให้ครอบ open/close")
    if low != float(row["low"]):
        notes.append("low ถูกขยายให้ครอบ open/close")
    normalized = {
        "open": float(row["open"]),
        "high": high,
        "low": low,
        "close": float(row["close"]),
    }
    return normalized, notes


def normalize_candles(
    rows: list[dict],
    calendar,
    *,
    asset: str = "",
    latest_candle_state: str = "forming",
    source_timestamp: str | None = None,
) -> dict:
    """คืน {"candles": [...], "anomalies": [...]}"""
    if latest_candle_state not in {"forming", "closed"}:
        raise ValueError("latest_candle_state ต้องเป็น forming หรือ closed")

    candles: list[dict] = []
    anomalies: list[dict] = []
    seen: dict[str, int] = {}

    for index, row in enumerate(rows):
        session_date = str(row.get("session_date") or row["date"])[:10]
        values, notes = normalize_ohlc(row)
        classification = calendar.classify(session_date)
        is_expected = classification == "expected"
        is_last = index == len(rows) - 1

        if session_date in seen:
            anomalies.append({
                "type": "duplicate_session_candle",
                "asset": asset,
                "session_date": session_date,
                "action": "excluded_from_session_calculations",
                "severity": FATAL,
            })

        if not is_expected:
            anomalies.append({
                "type": f"unexpected_{classification}_candle",
                "asset": asset,
                "session_date": session_date,
                "action": "excluded_from_session_calculations",
                "severity": FATAL,
            })
            notes.append(f"วันนี้ไม่ใช่ session ที่คาดหวังของ {calendar.asset_class} ({classification})")

        seen[session_date] = index
        candles.append({
            "session_date": session_date,
            "session_timezone": calendar.session_timezone,
            "market_calendar": calendar.calendar,
            "candle_state": latest_candle_state if is_last else "closed",
            "is_expected_session": is_expected,
            "is_synthetic": not is_expected,
            "source_timestamp": source_timestamp,
            "normalization_notes": notes,
            **values,
        })

    return {"candles": candles, "anomalies": anomalies}


def valid_completed_candles(candles: list[dict]) -> list[dict]:
    """แท่งที่ใช้คำนวณได้จริง — อยู่ในปฏิทินและปิดแล้วเท่านั้น"""
    return [
        candle for candle in candles
        if candle.get("is_expected_session") and candle.get("candle_state") == "closed"
    ]


def fatal_anomalies(anomalies: list[dict]) -> list[dict]:
    return [item for item in anomalies if item.get("severity") == FATAL]
