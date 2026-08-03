"""ตรวจว่าชุดข้อมูลขาด session ที่ควรมีหรือไม่ ตามปฏิทินของสินทรัพย์

crypto 24/7  : ขาดวันไหนก็ถือว่า fail และห้ามเผยแพร่
forex / metal: เสาร์อาทิตย์ไม่นับเป็น gap · ขาด session ล่าสุดถือว่า fail · ขาดของเก่าเป็น warning
"""

from __future__ import annotations


def detect_gaps(candles: list[dict], calendar, *, recent_window: int = 5) -> dict:
    if not candles:
        return {
            "status": "fail",
            "expected_sessions": 0,
            "received_sessions": 0,
            "missing_sessions": [],
            "unexpected_sessions": [],
            "publication_blocked": True,
            "notes": ["ไม่มีแท่งเทียนในชุดข้อมูล"],
        }

    dates = [candle["session_date"] for candle in candles]
    expected = [day.isoformat() for day in calendar.expected_sessions(dates[0], dates[-1])]
    received = sorted({
        candle["session_date"] for candle in candles if candle.get("is_expected_session")
    })
    unexpected = sorted({
        candle["session_date"] for candle in candles if not candle.get("is_expected_session")
    })
    missing = [day for day in expected if day not in set(received)]

    recent_expected = set(expected[-recent_window:]) if recent_window else set()
    missing_recent = [day for day in missing if day in recent_expected]

    notes: list[str] = []
    if calendar.is_continuous and missing:
        status = "fail"
        notes.append("ตลาด 24/7 ต้องมีแท่งทุกวันปฏิทิน")
    elif missing_recent:
        status = "fail"
        notes.append(f"ขาด session ล่าสุด {len(missing_recent)} วัน กระทบการตัดสินใจโดยตรง")
    elif missing:
        status = "warning"
        notes.append("ขาด session ที่ไม่ใช่ช่วงล่าสุด ให้ระบุเป็นข้อจำกัดในบทความ")
    else:
        status = "pass"

    if unexpected:
        notes.append(f"พบแท่งนอกปฏิทิน {len(unexpected)} วัน — ถูกกันออกจากการคำนวณแล้ว")
        if status == "pass":
            status = "warning"

    return {
        "status": status,
        "expected_sessions": len(expected),
        "received_sessions": len(received),
        "missing_sessions": missing,
        "unexpected_sessions": unexpected,
        "publication_blocked": status == "fail",
        "notes": notes,
    }
