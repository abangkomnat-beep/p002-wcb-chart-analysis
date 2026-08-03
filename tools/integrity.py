"""ร้อยด่านตรวจข้อมูลทั้งหมดเข้าด้วยกัน — เรียกจุดเดียวได้ผลครบชุด

    ปฏิทิน -> แท่งเทียนที่รู้สถานะ -> ตรวจวันหาย -> indicator ตามจำนวนแท่ง -> pivot -> ด่านเผยแพร่
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import candles as candles_module  # noqa: E402
from tools import gap_detector, indicators, market_calendar, pivots, publication_gate  # noqa: E402


def assess(
    rows: list[dict],
    asset: str,
    *,
    latest_candle_state: str = "forming",
    calculated_at: str | None = None,
    source_timestamp: str | None = None,
    provider_indicators: dict | None = None,
    config: dict | None = None,
) -> dict:
    """ประเมินชุดข้อมูลดิบหนึ่งชุดแบบครบด่าน

    provider_indicators: ค่าที่ provider ส่งมาสำเร็จรูป เช่น {"sma50": 4093.86}
    จะถูกบันทึกเป็น provider_only และไม่ถูกอนุมัติให้เผยแพร่
    """
    calendar = market_calendar.for_asset(asset, config)
    normalized = candles_module.normalize_candles(
        rows,
        calendar,
        asset=asset,
        latest_candle_state=latest_candle_state,
        source_timestamp=source_timestamp,
    )
    candle_list = normalized["candles"]
    anomalies = normalized["anomalies"]
    valid = candles_module.valid_completed_candles(candle_list)

    gap_check = gap_detector.detect_gaps(candle_list, calendar)
    indicator_set = indicators.compute_indicator_set(valid)

    for name, value in (provider_indicators or {}).items():
        current = indicator_set.get(name)
        if current and current.get("status") == indicators.AVAILABLE:
            continue
        indicator_set[name] = indicators.provider_value(
            name,
            value,
            required=(current or {}).get("required_bars", 0),
            available=len(valid),
        )

    pivot_block = pivots.compute_classic_pivots(
        candle_list, calendar=calendar, calculated_at=calculated_at
    )
    gate = publication_gate.evaluate(
        indicators=indicator_set,
        pivots=pivot_block,
        gap_check=gap_check,
        anomalies=anomalies,
        calendar=calendar,
        checked_at=calculated_at,
    )

    return {
        "asset": asset,
        "asset_class": calendar.asset_class,
        "session_timezone": calendar.session_timezone,
        "public_timezone": calendar.public_timezone,
        "candles": candle_list,
        "valid_completed_bars": len(valid),
        "anomalies": anomalies,
        "gap_check": gap_check,
        "indicators": indicator_set,
        "published_indicator_values": indicators.published_values(indicator_set),
        "pivots": pivot_block,
        "publication_gate": gate,
    }


def summary_line(report: dict) -> str:
    """บรรทัดเดียวสำหรับ log และรายงานให้คนอ่าน"""
    gate = report["publication_gate"]
    published = ", ".join(sorted(report["published_indicator_values"])) or "ไม่มี"
    return (
        f"{report['asset']} ({report['asset_class']}): แท่งใช้ได้ {report['valid_completed_bars']} · "
        f"indicator ที่เผยแพร่ได้ {published} · ด่านเผยแพร่ {gate['status']} "
        f"({len(gate['reasons'])} เหตุผล)"
    )
