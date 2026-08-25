"""Weekly editorial memory for Style D.

This module deliberately stores only structured market evidence.  It never
stores article prose and never changes chart geometry.  The writer can thus
explain what changed from the previous published week without inventing a new
support or resistance level merely to make the article look fresh.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "style_d_writing.json"
STATE_DIR = REPO_ROOT / "state"
CONFIG_SCHEMA = "style-d-writing-v1"
STATE_SCHEMA = "style-d-weekly-state-v1"
MODES = {"legacy", "weekly_delta"}


class WeeklyDeltaConfigError(RuntimeError):
    """The writing-mode switch is unreadable or unsafe."""


def load_mode(path: Path = CONFIG_PATH) -> str:
    """Load the reversible writing-mode switch and fail closed on corruption."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WeeklyDeltaConfigError(f"อ่าน config การเขียน Style D ไม่ได้: {exc}") from None
    if payload.get("schema") != CONFIG_SCHEMA or payload.get("mode") not in MODES:
        raise WeeklyDeltaConfigError(
            "config การเขียน Style D ต้องใช้ schema style-d-writing-v1 "
            "และ mode legacy/weekly_delta")
    return str(payload["mode"])


def state_path(asset: str, state_dir: Path | None = None) -> Path:
    return (state_dir or STATE_DIR) / f"style-d-weekly-{asset}.json"


def load(asset: str, state_dir: Path | None = None) -> dict | None:
    """Read weekly state; missing/corrupt state becomes a safe baseline round."""
    path = state_path(asset, state_dir)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (not isinstance(payload, dict) or payload.get("schema") != STATE_SCHEMA
            or payload.get("asset") != asset):
        return None
    return payload


def save(asset: str, state: dict, state_dir: Path | None = None) -> Path:
    """Atomically persist state only after the caller has completed QA/output."""
    path = state_path(asset, state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=1)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return path


def _week_bounds(publish_date: str) -> tuple[str, str]:
    anchor = date.fromisoformat(publish_date)
    monday = anchor - timedelta(days=anchor.weekday())
    return monday.isoformat(), (monday + timedelta(days=4)).isoformat()


def snapshot(story: dict) -> dict:
    """Capture only evidence needed to compare the next published week."""
    week_start, week_end = _week_bounds(story.get("publish_date")
                                        or story["current"]["date"])
    channel = story.get("channel")
    return {
        "week_start": week_start,
        "week_end": week_end,
        "publish_date": story.get("publish_date") or story["current"]["date"],
        "candle_date": story["current"]["date"],
        "close": story["current"]["close"],
        "atr14": story["atr14"],
        "sma50": story.get("sma50_last"),
        "sma200": story.get("sma200_last"),
        "regime_down": bool(story["regime"]["down"]),
        "channel": None if not channel else {
            "main_is_upper": bool(channel["main_is_upper"]),
            "locked_since": channel.get("locked_since"),
        },
        "zones": [{
            "low": zone["low"], "high": zone["high"], "mean": zone["mean"],
            "touches": zone["touches"], "locked_since": zone.get("locked_since"),
        } for zone in story.get("zones") or []],
        "resistance": [{
            "mean": level["mean"], "touches": level["touches"],
            "locked_since": level.get("locked_since"),
        } for level in sorted(story.get("resistance") or [],
                              key=lambda item: item["mean"])],
    }


def _same_level(first: dict | None, second: dict | None) -> bool:
    if first is None or second is None:
        return first is second
    keys = ("low", "high", "mean") if "low" in first or "low" in second else ("mean",)
    return all(abs(float(first[key]) - float(second[key])) <= 1e-8 for key in keys)


def _comparison(current: dict, previous: dict | None) -> dict:
    current_zone = current["zones"][0] if current["zones"] else None
    current_resistance = current["resistance"][0] if current["resistance"] else None
    if previous is None:
        return {
            "status": "baseline",
            "current": current,
            "previous": None,
            "close_change": None,
            "close_change_pct": None,
            "regime_changed": False,
            "zone_status": "baseline",
            "zone_touches_change": None,
            "resistance_status": "baseline",
            "change_count": 0,
        }

    previous_zone = previous["zones"][0] if previous.get("zones") else None
    previous_resistance = (previous["resistance"][0]
                           if previous.get("resistance") else None)
    if current_zone is None:
        zone_status = "missing" if previous_zone else "none"
    elif previous_zone is None:
        zone_status = "new"
    else:
        zone_status = "unchanged" if _same_level(current_zone, previous_zone) else "changed"
    if current_resistance is None:
        resistance_status = "missing" if previous_resistance else "none"
    elif previous_resistance is None:
        resistance_status = "new"
    else:
        resistance_status = ("unchanged" if _same_level(current_resistance,
                                                         previous_resistance)
                             else "changed")
    close_change = current["close"] - previous["close"]
    close_change_pct = ((close_change / abs(previous["close"])) * 100
                        if previous["close"] else 0.0)
    touches_change = None
    if current_zone is not None and previous_zone is not None and zone_status == "unchanged":
        touches_change = current_zone["touches"] - previous_zone["touches"]
    regime_changed = current["regime_down"] != previous["regime_down"]
    change_count = sum((
        abs(close_change) > 1e-12,
        regime_changed,
        zone_status not in {"unchanged", "none"},
        resistance_status not in {"unchanged", "none"},
        bool(touches_change),
    ))
    return {
        "status": "comparison",
        "current": current,
        "previous": previous,
        "close_change": close_change,
        "close_change_pct": close_change_pct,
        "regime_changed": regime_changed,
        "zone_status": zone_status,
        "zone_touches_change": touches_change,
        "resistance_status": resistance_status,
        "change_count": change_count,
    }


def prepare(story: dict, state: dict | None) -> tuple[dict, dict]:
    """Return writer delta plus the state to save after successful output."""
    current = snapshot(story)
    previous = None
    next_previous = None
    stored_current = state.get("current_week") if state else None
    stored_previous = state.get("previous_week") if state else None

    if stored_current and stored_current.get("week_start") == current["week_start"]:
        # Same-week rerun keeps comparing against the prior published week.
        previous = stored_previous
        next_previous = stored_previous
    elif stored_current:
        gap = ((date.fromisoformat(current["week_start"])
                - date.fromisoformat(stored_current["week_start"])).days)
        if gap == 7:
            previous = stored_current
            next_previous = stored_current
        # Backfills or skipped weeks deliberately become a new baseline.

    delta = _comparison(current, previous)
    next_state = {
        "schema": STATE_SCHEMA,
        "asset": story["asset"],
        "previous_week": next_previous,
        "current_week": current,
    }
    return delta, next_state


__all__ = [
    "CONFIG_PATH", "STATE_DIR", "WeeklyDeltaConfigError", "load_mode",
    "state_path", "load", "save", "snapshot", "prepare",
]
