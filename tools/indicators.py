"""คำนวณ indicator พร้อมสถานะของตัวเอง — ข้อมูลไม่พอ = ไม่คำนวณ ไม่พล็อต ไม่อ้างในบทความ

ต่างจาก compute_indicators() เดิมตรงที่ทุกตัวคืน object ที่บอกได้ว่า
ใช้แท่งกี่แท่ง ต้องการกี่แท่ง ใครเป็นคนคำนวณ และเผยแพร่ได้หรือยัง
"""

from __future__ import annotations

import json
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "minimum_bars.json"

AVAILABLE = "available"
INSUFFICIENT = "insufficient_data"
PROVIDER_ONLY = "provider_only"
INVALID = "invalid"


def load_minimum_bars(path: Path | None = None) -> dict:
    payload = json.loads((path or CONFIG_PATH).read_text(encoding="utf-8"))
    return payload["minimum_completed_bars"]


def _mean(values):
    return sum(values) / len(values) if values else None


def _status(name, *, required, available, value, owner, status) -> dict:
    return {
        "indicator": name,
        "status": status,
        "required_bars": required,
        "available_completed_bars": available,
        "calculation_owner": owner,
        "value": value,
        "approved_for_publication": status == AVAILABLE,
    }


def unavailable(name: str, *, required: int, available: int, reason: str = INSUFFICIENT) -> dict:
    return _status(name, required=required, available=available, value=None, owner="P002", status=reason)


def provider_value(name: str, value, *, required: int, available: int) -> dict:
    """ค่าที่ provider ส่งมาสำเร็จรูป — บันทึกไว้ได้ แต่ยังไม่อนุมัติให้เผยแพร่"""
    return _status(name, required=required, available=available, value=value,
                   owner="provider", status=PROVIDER_ONLY)


def _sma(closes: list[float], period: int, name: str, minimum: dict) -> dict:
    required = minimum.get(name, period)
    available = len(closes)
    if available < required:
        return unavailable(name, required=required, available=available)
    return _status(name, required=required, available=available,
                   value=float(_mean(closes[-period:])), owner="P002", status=AVAILABLE)


def _rsi14(closes: list[float], minimum: dict) -> dict:
    required = minimum.get("rsi14", 15)
    available = len(closes)
    if available < required:
        return unavailable("rsi14", required=required, available=available)
    diffs = [closes[i] - closes[i - 1] for i in range(1, len(closes))][-14:]
    avg_gain = _mean([max(delta, 0.0) for delta in diffs])
    avg_loss = _mean([max(-delta, 0.0) for delta in diffs])
    if not avg_loss:
        value = 100.0
    else:
        value = 100.0 - (100.0 / (1.0 + (avg_gain / avg_loss)))
    return _status("rsi14", required=required, available=available,
                   value=float(value), owner="P002", status=AVAILABLE)


def _atr14(candles: list[dict], minimum: dict) -> dict:
    required = minimum.get("atr14", 15)
    available = len(candles)
    if available < required:
        return unavailable("atr14", required=required, available=available)
    true_ranges = []
    for index in range(1, len(candles)):
        high = float(candles[index]["high"])
        low = float(candles[index]["low"])
        previous_close = float(candles[index - 1]["close"])
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    return _status("atr14", required=required, available=available,
                   value=float(_mean(true_ranges[-14:])), owner="P002", status=AVAILABLE)


def compute_indicator_set(valid_candles: list[dict], *, minimum_bars: dict | None = None) -> dict:
    """valid_candles ต้องผ่าน candles.valid_completed_candles() มาแล้วเท่านั้น"""
    minimum = minimum_bars or load_minimum_bars()
    closes = [float(candle["close"]) for candle in valid_candles]
    return {
        "sma20": _sma(closes, 20, "sma20", minimum),
        "sma50": _sma(closes, 50, "sma50", minimum),
        "sma200": _sma(closes, 200, "sma200", minimum),
        "rsi14": _rsi14(closes, minimum),
        "atr14": _atr14(valid_candles, minimum),
    }


def publishable(indicator: dict) -> bool:
    return bool(indicator.get("approved_for_publication"))


def published_values(indicator_set: dict) -> dict:
    """ค่าที่อนุญาตให้บทความและกราฟใช้ — ตัวที่ข้อมูลไม่พอจะไม่ปรากฏเลย"""
    return {
        name: item["value"]
        for name, item in indicator_set.items()
        if publishable(item)
    }
