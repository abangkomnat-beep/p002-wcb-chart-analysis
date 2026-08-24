"""Closed-bar normalization and fail-closed data gates for BTCUSD F+."""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Iterable, Mapping


TIMEFRAME_SECONDS = {"4h": 14_400, "1h": 3_600, "30min": 1_800, "15min": 900}
REQUIRED_TIMEFRAMES = ("4h", "1h", "30min", "15min")


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must contain timezone")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def trim_closed_rows(
    rows: Iterable[Mapping[str, Any]], *, timeframe: str, cutoff_at_utc: str,
) -> dict[str, Any]:
    if timeframe not in TIMEFRAME_SECONDS:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    cutoff = _utc(cutoff_at_utc)
    closed: list[dict[str, Any]] = []
    dropped = 0
    for source_row in rows:
        row = dict(source_row)
        try:
            close_at = _utc(str(row["bar_close_at_utc"]))
        except (KeyError, TypeError, ValueError):
            dropped += 1
            continue
        if close_at <= cutoff:
            row["bar_close_at_utc"] = _iso(close_at)
            closed.append(row)
        else:
            dropped += 1
    closed.sort(key=lambda row: row["bar_close_at_utc"])
    return {"rows": closed, "dropped_forming_bars": dropped}


def _gate(status: str, reasons: list[str]) -> dict[str, Any]:
    return {"status": status, "reason_codes": list(reasons)}


def _valid_ohlc(row: Mapping[str, Any]) -> bool:
    try:
        values = [float(row[name]) for name in ("open", "high", "low", "close")]
    except (KeyError, TypeError, ValueError):
        return False
    if not all(math.isfinite(value) and value > 0 for value in values):
        return False
    open_, high, low, close = values
    return low <= high and low <= open_ <= high and low <= close <= high


def _minimum_rows(timeframe: str, warmup: Mapping[str, Any]) -> int:
    """Keep enough bars for the configured number of complete H4 windows."""
    own = int(warmup.get(timeframe, 0))
    values = {int(warmup.get(name, 0)) for name in REQUIRED_TIMEFRAMES}
    # The compact synthetic contract fixture declares one common H4 horizon.
    # Runtime config declares calculator-specific history for each timeframe.
    if len(values) == 1:
        h4_windows = int(warmup.get("4h", 0))
        aligned = h4_windows * (TIMEFRAME_SECONDS["4h"] // TIMEFRAME_SECONDS[timeframe])
        return max(own, aligned)
    return own


def _cross_timeframe_matches(series: Mapping[str, Any], tolerance: float) -> bool:
    m15 = list(series["15min"]["rows"])
    for timeframe, factor in (("30min", 2), ("1h", 4), ("4h", 16)):
        comparisons = 0
        span = TIMEFRAME_SECONDS[timeframe]
        for actual in series[timeframe]["rows"]:
            close_at = _utc(actual["bar_close_at_utc"])
            start_at = close_at.timestamp() - span
            group = [row for row in m15
                     if start_at < _utc(row["bar_close_at_utc"]).timestamp() <= close_at.timestamp()]
            if len(group) != factor:
                continue
            comparisons += 1
            expected = {
                "open": float(group[0]["open"]),
                "high": max(float(row["high"]) for row in group),
                "low": min(float(row["low"]) for row in group),
                "close": float(group[-1]["close"]),
            }
            for field in ("open", "high", "low", "close"):
                if abs(float(actual[field]) - float(expected[field])) > tolerance:
                    return False
        if comparisons == 0:
            return False
    return True


def evaluate_data_gates(snapshot: Mapping[str, Any], *, config: Mapping[str, Any]) -> dict[str, Any]:
    cutoff_text = str(snapshot.get("cutoff_at_utc", ""))
    report: dict[str, Any] = {
        "cutoff_at_utc": cutoff_text,
        "trade_date_bangkok": snapshot.get("trade_date_bangkok"),
    }
    reasons: list[str] = []
    freshness_reasons: list[str] = []
    integrity_reasons: list[str] = []
    alignment_reasons: list[str] = []
    try:
        cutoff = _utc(cutoff_text)
    except (TypeError, ValueError):
        cutoff = datetime.min.replace(tzinfo=timezone.utc)
        integrity_reasons.append("CUTOFF_INVALID")
    if snapshot.get("asset") != "btcusd":
        integrity_reasons.append("ASSET_INVALID")
    if str(snapshot.get("source", "")).lower() != "wcb":
        integrity_reasons.append("SOURCE_INVALID")

    series = snapshot.get("series")
    if not isinstance(series, Mapping):
        series = {}
    required = tuple(config.get("required_timeframes", REQUIRED_TIMEFRAMES))
    for timeframe in required:
        if timeframe not in series:
            integrity_reasons.append(f"MISSING_TIMEFRAME_{timeframe.upper()}")
    if not integrity_reasons:
        warmup = config.get("warmup_bars", {name: 1 for name in REQUIRED_TIMEFRAMES})
        grace_map = config.get(
            "freshness_grace_seconds",
            config.get("freshness_grace_by_timeframe", {}),
        )
        for timeframe in required:
            frame = series[timeframe]
            rows = frame.get("rows", [])
            code = timeframe.upper()
            if not frame.get("timezone_verified", False):
                integrity_reasons.append(f"TIMEZONE_UNVERIFIED_{code}")
            if not isinstance(rows, list) or len(rows) < _minimum_rows(timeframe, warmup):
                integrity_reasons.append(f"INSUFFICIENT_WARMUP_{code}")
                if not isinstance(rows, list) or not rows:
                    continue
            try:
                close_times = [_utc(row["bar_close_at_utc"]) for row in rows]
                start_times = [_utc(row["bar_start_at_utc"]) for row in rows]
            except (KeyError, TypeError, ValueError):
                integrity_reasons.append(f"TIMESTAMP_INVALID_{code}")
                continue
            if close_times != sorted(close_times) or len(set(close_times)) != len(close_times):
                integrity_reasons.append(f"DUPLICATE_BAR_{code}")
            expected_delta = TIMEFRAME_SECONDS[timeframe]
            if any(int((right - left).total_seconds()) != expected_delta
                   for left, right in zip(close_times, close_times[1:])):
                integrity_reasons.append(f"GAP_{code}")
            if any(int((close - start).total_seconds()) != expected_delta
                   for start, close in zip(start_times, close_times)):
                integrity_reasons.append(f"BAR_DURATION_INVALID_{code}")
            if any(not _valid_ohlc(row) for row in rows):
                integrity_reasons.append(f"OHLC_INVALID_{code}")
            if any(close > cutoff for close in close_times):
                integrity_reasons.append(f"FORMING_BAR_{code}")
            latest_text = frame.get("latest_bar_close_at_utc")
            try:
                latest = _utc(latest_text)
            except (TypeError, ValueError):
                freshness_reasons.append(f"LATEST_CLOSE_INVALID_{code}")
                continue
            if latest != close_times[-1]:
                integrity_reasons.append(f"LATEST_CLOSE_MISMATCH_{code}")
            age = (cutoff - latest).total_seconds()
            budget = TIMEFRAME_SECONDS[timeframe] + int(grace_map.get(timeframe, 0))
            if age < 0 or age > budget:
                freshness_reasons.append(f"STALE_{code}")

        if all(
            isinstance(series.get(timeframe, {}).get("rows"), list)
            and series[timeframe]["rows"]
            for timeframe in required
        ):
            tolerance = float(config.get("cross_timeframe_tolerance", 0.0))
            if not _cross_timeframe_matches(series, tolerance):
                alignment_reasons.append("CROSS_TIMEFRAME_MISMATCH")

    reasons.extend(freshness_reasons)
    reasons.extend(integrity_reasons)
    reasons.extend(alignment_reasons)
    report["freshness"] = _gate("pass" if not freshness_reasons else "fail", freshness_reasons)
    report["integrity"] = _gate("pass" if not integrity_reasons else "fail", integrity_reasons)
    report["alignment"] = _gate("pass" if not alignment_reasons else "fail", alignment_reasons)
    report["reason_codes"] = reasons
    report["price_data_status"] = "pass" if not reasons else "blocked_retryable"
    return report
