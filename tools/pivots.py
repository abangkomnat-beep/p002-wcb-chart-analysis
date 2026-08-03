"""Classic Pivot ที่คำนวณจาก previous valid completed session เท่านั้น

ห้ามใช้: แท่งที่กำลังก่อตัว · แท่งเสาร์อาทิตย์/วันหยุด · แถวสุดท้ายแบบไม่ตรวจสถานะ
ทุกครั้งต้องบันทึกฐานการคำนวณให้ครบเพื่อให้ย้อนกลับได้
"""

from __future__ import annotations

from datetime import date


def _levels(high: float, low: float, close: float) -> dict:
    pivot = (high + low + close) / 3.0
    return {
        "p": pivot,
        "r1": (2.0 * pivot) - low,
        "r2": pivot + (high - low),
        "r3": high + (2.0 * (pivot - low)),
        "s1": (2.0 * pivot) - high,
        "s2": pivot - (high - low),
        "s3": low - (2.0 * (high - pivot)),
    }


def _empty(reason: str, *, calculated_at: str | None) -> dict:
    return {
        "method": "classic",
        "basis_session_date": None,
        "basis_timezone": None,
        "basis_open": None,
        "basis_high": None,
        "basis_low": None,
        "basis_close": None,
        "basis_candle_state": None,
        "calculated_at": calculated_at,
        "quality_status": "invalid",
        "reason": reason,
        "p": None, "r1": None, "r2": None, "r3": None,
        "s1": None, "s2": None, "s3": None,
    }


def select_basis_candle(candles: list[dict]) -> dict | None:
    """แท่งฐาน = แท่งที่ปิดแล้วและอยู่ในปฏิทิน ตัวล่าสุดก่อนแท่งปัจจุบัน

    แท่งสุดท้ายของชุดถือเป็น session ปัจจุบันเสมอ จึงไม่ถูกใช้เป็นฐาน
    """
    for candle in reversed(candles[:-1]):
        if candle.get("is_expected_session") and candle.get("candle_state") == "closed":
            return candle
    return None


def compute_classic_pivots(
    candles: list[dict],
    *,
    calendar=None,
    calculated_at: str | None = None,
    stale_after_sessions: int = 3,
) -> dict:
    if len(candles) < 2:
        return _empty("ต้องมีอย่างน้อยสองแท่งจึงจะหาฐานได้", calculated_at=calculated_at)

    basis = select_basis_candle(candles)
    if basis is None:
        return _empty("ไม่พบแท่งที่ปิดแล้วและอยู่ในปฏิทิน", calculated_at=calculated_at)

    high, low, close = float(basis["high"]), float(basis["low"]), float(basis["close"])
    result = {
        "method": "classic",
        "basis_session_date": basis["session_date"],
        "basis_timezone": basis.get("session_timezone") or (calendar.session_timezone if calendar else None),
        "basis_open": float(basis["open"]),
        "basis_high": high,
        "basis_low": low,
        "basis_close": close,
        "basis_candle_state": basis["candle_state"],
        "calculated_at": calculated_at,
        "quality_status": "valid",
        "reason": None,
        **_levels(high, low, close),
    }

    if calendar is not None:
        current = candles[-1]["session_date"]
        gap = len(calendar.expected_sessions(basis["session_date"], current)) - 1
        result["sessions_since_basis"] = gap
        if gap > stale_after_sessions:
            result["quality_status"] = "warning"
            result["reason"] = f"ฐาน Pivot เก่ากว่า {stale_after_sessions} session ({gap} session)"

    return result
