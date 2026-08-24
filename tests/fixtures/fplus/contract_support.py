"""Helpers that keep F+ TDD tests collectable before production modules exist."""
from __future__ import annotations

import importlib
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


FIXTURE_ROOT = Path(__file__).resolve().parent


def require_module(name: str):
    """Import a required production module, failing at test time (not collection)."""
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name == name:
            pytest.fail(
                f"TDD RED: Builder must implement required module {name}",
                pytrace=False,
            )
        raise


def load_json(name: str) -> dict | list:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def make_rows(*, timeframe_minutes: int, count: int = 64,
              end_close: datetime | None = None) -> list[dict]:
    """Create closed, increasing BTCUSD bars ending at ``end_close``."""
    end_close = end_close or datetime(2026, 8, 24, 2, 0, tzinfo=timezone.utc)
    start = end_close - timedelta(minutes=timeframe_minutes * count)
    rows: list[dict] = []
    for index in range(count):
        opened = start + timedelta(minutes=timeframe_minutes * index)
        closed = opened + timedelta(minutes=timeframe_minutes)
        base = 70_000.0 + index * 10.0
        rows.append({
            "bar_start_at_utc": iso(opened),
            "bar_close_at_utc": iso(closed),
            "open": base,
            "high": base + 40.0,
            "low": base - 30.0,
            "close": base + 10.0,
        })
    return rows


def aggregate_rows(rows: list[dict], factor: int) -> list[dict]:
    """Aggregate complete groups so the valid fixture is cross-TF coherent."""
    result = []
    for index in range(0, len(rows), factor):
        group = rows[index:index + factor]
        if len(group) != factor:
            continue
        result.append({
            "bar_start_at_utc": group[0]["bar_start_at_utc"],
            "bar_close_at_utc": group[-1]["bar_close_at_utc"],
            "open": group[0]["open"],
            "high": max(row["high"] for row in group),
            "low": min(row["low"] for row in group),
            "close": group[-1]["close"],
        })
    return result


def valid_snapshot() -> dict:
    cutoff = datetime(2026, 8, 24, 2, 0, tzinfo=timezone.utc)
    m15 = make_rows(timeframe_minutes=15, count=64, end_close=cutoff)
    rows_by_frame = {
        "4h": aggregate_rows(m15, 16),
        "1h": aggregate_rows(m15, 4),
        "30min": aggregate_rows(m15, 2),
        "15min": m15,
    }
    return {
        "schema_version": "fplus-market-snapshot-v1",
        "snapshot_id": "fixture-snapshot",
        "asset": "btcusd",
        "source": "wcb",
        "cutoff_at_utc": iso(cutoff),
        "trade_date_bangkok": "2026-08-24",
        "retrieved_at_utc": iso(cutoff + timedelta(minutes=1)),
        "calendar": {"source": "wcb", "available": True, "events": []},
        "series": {
            name: {
                "rows": rows,
                "latest_bar_start_at_utc": rows[-1]["bar_start_at_utc"],
                "latest_bar_close_at_utc": rows[-1]["bar_close_at_utc"],
                "dropped_forming_bars": 0,
                "timezone_verified": True,
                "row_count": len(rows),
                "rows_sha256": f"fixture-{name}",
            }
            for name, rows in rows_by_frame.items()
        },
    }


def clone(value):
    return deepcopy(value)
