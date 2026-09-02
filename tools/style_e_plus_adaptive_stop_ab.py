"""Isolated offline research harness for the Style E+ BTC adaptive-stop A/B.

This module is intentionally not imported by production entrypoints.  It consumes
local closed-candle snapshots only and writes research evidence under ``work/``.
Synthetic fills are analytics proxies, never execution or lifecycle evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import shutil
import sys
import tempfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median
from zoneinfo import ZoneInfo

try:
    from tools import style_e_plus_story as production_story
    from tools import style_e_plus_adaptive_stop as adaptive_stop
except ModuleNotFoundError as exc:  # Preserve direct ``python tools/...py`` CLI use.
    if exc.name != "tools":
        raise
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tools import style_e_plus_story as production_story
    from tools import style_e_plus_adaptive_stop as adaptive_stop


SCHEMA = "style-e-plus-adaptive-stop-ab/v1"
PUBLIC_STATES = ("NO_PLAN", "NO_CHASE", "WAIT_TRIGGER", "ENTRY_READY")
REJECT_REASONS = (
    "NO_CONFIRMED_SWING", "STOP_GT_3ATR", "TARGET_SPACE_LT_1_5R")
HORIZONS = (16, 32, 64)
BANGKOK = ZoneInfo("Asia/Bangkok")
CONFIG = {
    "experiment_id": "style-e-plus-btc-adaptive-stop-ab-2026-08-26",
    "asset": "btcusd",
    "local_only": True,
    "baseline_risk_atr": 1.5,
    "entry_half_width_atr": 0.25,
    "pivot_left": 2,
    "pivot_right": 2,
    "pivot_lookback_bars": 20,
    "structure_buffer_atr": 0.25,
    "risk_floor_atr": 2.0,
    "risk_cap_atr": 3.0,
    "target_space_min_r": 1.5,
    "donchian_length": 20,
    "trigger_buffer_atr": None,
    "same_bar_order": "SL_FIRST",
    "primary_horizon": 32,
    "horizons": list(HORIZONS),
    "touch_fill_bars": 4,
    "split": [0.60, 0.20, 0.20],
    "minimum_days": 180,
    "target_days": 365,
    "warmup_bars": {"1h": 240, "15min": 240},
    "synthetic_fill": True,
    "production_enabled": False,
}
PRODUCER_ID = "style-e-plus-production-prefix-recompute/v1"


class ResearchError(RuntimeError):
    """Research input or contract is invalid."""


def json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _object_sha256(value: object) -> str:
    return hashlib.sha256(json_text(value).encode("utf-8")).hexdigest()


def _number(value, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ResearchError(f"{label} must be numeric") from exc
    if not math.isfinite(result):
        raise ResearchError(f"{label} must be finite")
    return result


def _at(value: object) -> datetime:
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ResearchError(f"invalid timestamp: {value}") from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=BANGKOK)
    return moment.astimezone(BANGKOK)


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _normalized_rows(rows: list[dict], timeframe: str) -> tuple[list[dict], list[str]]:
    if not isinstance(rows, list):
        raise ResearchError(f"{timeframe} rows must be a list")
    output, issues, previous = [], [], None
    timestamps = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ResearchError(f"{timeframe} row {index} must be an object")
        if row.get("forming") is True or row.get("candle_state") not in (None, "closed"):
            raise ResearchError(f"{timeframe} row {index} is not closed")
        moment = _at(row.get("at"))
        canonical = moment.isoformat()
        if canonical in timestamps:
            raise ResearchError(f"{timeframe} duplicate timestamp: {canonical}")
        if previous is not None and moment <= previous:
            raise ResearchError(f"{timeframe} rows are not strictly ordered")
        timestamps.add(canonical)
        previous = moment
        open_, high, low, close = (
            _number(row.get(key), f"{timeframe}[{index}].{key}")
            for key in ("open", "high", "low", "close"))
        if high < max(open_, close) or low > min(open_, close) or low > high:
            raise ResearchError(f"{timeframe} row {index} has invalid OHLC")
        output.append({
            "at": canonical, "open": open_, "high": high,
            "low": low, "close": close, "forming": False,
        })
    expected = timedelta(minutes=15 if timeframe == "15min" else 60)
    for left, right in zip(output, output[1:]):
        delta = _at(right["at"]) - _at(left["at"])
        if delta != expected:
            issues.append(
                f"MISSING_INTERVAL:{left['at']}->{right['at']}:{int(delta.total_seconds())}")
    return output, issues


def derive_decisions(h1_rows: list[dict], m15_rows: list[dict], *,
                     dataset_sha256: str, excluded_oos_count: int = 0,
                     dataset_hash_scope: str = "provided_closed_prefix") -> dict:
    """Recompute every eligible M15 state from closed H1/M15 prefixes only."""
    if not dataset_sha256:
        raise ResearchError("producer requires dataset hash")
    events = []
    previous_state = None
    h1_count = 0
    h1_cache: dict[int, tuple[dict, str | None]] = {}
    for index in range(production_story.MIN_CLOSED_BARS - 1, len(m15_rows)):
        decision_close_at = _at(m15_rows[index]["at"]) + timedelta(minutes=15)
        while (h1_count < len(h1_rows)
               and _at(h1_rows[h1_count]["at"]) + timedelta(hours=1) <= decision_close_at):
            h1_count += 1
        if h1_count < production_story.MIN_CLOSED_BARS:
            continue
        if h1_count not in h1_cache:
            try:
                h1_indicators = production_story._indicator_contract(h1_rows[:h1_count])
                h1_side, _ = production_story._h1_bias(h1_indicators)
            except production_story.StoryUnavailable as exc:
                raise ResearchError(f"production H1 recomputation failed at M15 {index}") from exc
            h1_cache[h1_count] = (h1_indicators, h1_side)
        h1_indicators, h1_side = h1_cache[h1_count]
        try:
            m15_indicators = production_story._m15_indicator_contract(m15_rows[:index + 1])
            plan_created_at = decision_close_at.isoformat()
            state, plan, _, _ = production_story._m15_decision(
                m15_indicators, float(m15_rows[index]["close"]), h1_side,
                plan_created_at=plan_created_at,
                context=adaptive_stop.build_context(m15_rows[:index + 1]))
        except production_story.StoryUnavailable as exc:
            raise ResearchError(f"production M15 recomputation failed at index {index}") from exc
        atr = float(m15_indicators["atr"]["value"])
        ema20 = float(m15_indicators["ema20"])
        half_width = production_story.ENTRY_HALF_WIDTH_ATR * atr
        event = {
            "index": index, "at": m15_rows[index]["at"], "state": state,
            "previous_state": previous_state if previous_state is not None else state,
            "side": h1_side, "entry_low": ema20 - half_width,
            "entry_high": ema20 + half_width, "atr": atr,
            "evidence": {
                "producer_id": PRODUCER_ID, "prefix_only": True,
                "m15_prefix_count": index + 1, "m15_prefix_end_at": m15_rows[index]["at"],
                "m15_decision_close_at": decision_close_at.isoformat(),
                "m15_ema20": ema20, "m15_atr14": atr,
                "h1_prefix_count": h1_count,
                "h1_prefix_end_at": h1_rows[h1_count - 1]["at"],
                "h1_prefix_closed_at": (
                    _at(h1_rows[h1_count - 1]["at"]) + timedelta(hours=1)).isoformat(),
                "h1_bias_side": h1_side,
                "production_plan_present": plan is not None,
            },
        }
        events.append(event)
        previous_state = state
    module_path = Path(__file__).resolve()
    oracle_path = Path(production_story.__file__).resolve()
    return {
        "schema": f"{SCHEMA}/derived-decisions", "producer_id": PRODUCER_ID,
        "producer_code_sha256": sha256(module_path),
        "production_oracle": "tools.style_e_plus_story",
        "production_oracle_code_sha256": sha256(oracle_path),
        "production_story_schema": production_story.STORY_SCHEMA,
        "dataset_sha256": dataset_sha256,
        "dataset_hash_scope": dataset_hash_scope,
        "excluded_oos_count": excluded_oos_count,
        "config": {
            "minimum_closed_bars": production_story.MIN_CLOSED_BARS,
            "entry_half_width_atr": production_story.ENTRY_HALF_WIDTH_ATR,
            "h1_close_lag_minutes": 60, "m15_close_lag_minutes": 15,
        },
        "events": events,
    }


def baseline_plan(side: str, *, entry_low: float, entry_high: float, atr: float) -> dict:
    """Return locked production-baseline geometry without importing production code."""
    if side not in {"buy", "sell"}:
        raise ResearchError("side must be buy or sell")
    atr = _number(atr, "atr")
    if atr <= 0:
        raise ResearchError("atr must be positive")
    entry_low, entry_high = _number(entry_low, "entry_low"), _number(entry_high, "entry_high")
    if entry_low > entry_high:
        raise ResearchError("entry zone is reversed")
    entry = entry_high if side == "buy" else entry_low
    risk = CONFIG["baseline_risk_atr"] * atr
    direction = 1.0 if side == "buy" else -1.0
    return {
        "variant": "A", "accepted": True, "side": side,
        "entry": entry, "risk": risk, "risk_atr": CONFIG["baseline_risk_atr"],
        "stop": entry - direction * risk,
        "tp1": entry + direction * 1.5 * risk,
        "tp2": entry + direction * 2.0 * risk,
        "synthetic_fill": True,
    }


def confirmed_pivot(rows: list[dict], *, decision_index: int, side: str) -> dict | None:
    """Find the latest strict 2L/2R pivot confirmed by the closed decision prefix."""
    if side not in {"buy", "sell"}:
        raise ResearchError("side must be buy or sell")
    if decision_index < 0 or decision_index >= len(rows):
        raise ResearchError("decision_index outside rows")
    earliest = max(CONFIG["pivot_left"], decision_index - CONFIG["pivot_lookback_bars"])
    latest = decision_index - CONFIG["pivot_right"]
    field = "low" if side == "buy" else "high"
    for index in range(latest, earliest - 1, -1):
        value = _number(rows[index].get(field), f"rows[{index}].{field}")
        neighbors = [
            _number(rows[position].get(field), f"rows[{position}].{field}")
            for position in range(index - CONFIG["pivot_left"],
                                  index + CONFIG["pivot_right"] + 1)
            if position != index]
        is_pivot = (all(value < other for other in neighbors) if side == "buy"
                    else all(value > other for other in neighbors))
        if is_pivot:
            return {
                "index": index, "price": value,
                "confirmed_index": index + CONFIG["pivot_right"],
                "left": CONFIG["pivot_left"], "right": CONFIG["pivot_right"],
            }
    return None


def bounded_adaptive_risk(raw_risk: float, *, atr: float) -> dict:
    raw_risk, atr = _number(raw_risk, "raw_risk"), _number(atr, "atr")
    if raw_risk <= 0 or atr <= 0:
        raise ResearchError("risk and atr must be positive")
    raw_atr = raw_risk / atr
    if raw_atr > CONFIG["risk_cap_atr"] + 1e-12:
        return {"accepted": False, "reason": "STOP_GT_3ATR", "raw_risk_atr": raw_atr}
    risk_atr = max(raw_atr, CONFIG["risk_floor_atr"])
    return {
        "accepted": True, "reason": None, "raw_risk": raw_risk,
        "raw_risk_atr": raw_atr, "risk": risk_atr * atr, "risk_atr": risk_atr,
        "floor_applied": raw_atr < CONFIG["risk_floor_atr"],
    }


def target_space_check(*, side: str, entry: float, boundary: float, risk: float) -> dict:
    entry, boundary, risk = (_number(entry, "entry"), _number(boundary, "boundary"),
                             _number(risk, "risk"))
    if risk <= 0 or side not in {"buy", "sell"}:
        raise ResearchError("invalid target-space inputs")
    space = boundary - entry if side == "buy" else entry - boundary
    space_r = space / risk
    accepted = space_r + 1e-12 >= CONFIG["target_space_min_r"]
    return {
        "accepted": accepted,
        "reason": None if accepted else "TARGET_SPACE_LT_1_5R",
        "boundary": boundary, "space": space, "space_r": space_r,
    }


def adaptive_plan(rows: list[dict], *, decision_index: int, side: str,
                  entry_low: float, entry_high: float, atr: float) -> dict:
    """Build research variant B strictly from bars visible at decision_index."""
    pivot = confirmed_pivot(rows, decision_index=decision_index, side=side)
    if pivot is None:
        return {"variant": "B", "accepted": False, "reason": "NO_CONFIRMED_SWING"}
    entry = _number(entry_high if side == "buy" else entry_low, "disadvantaged_entry")
    atr = _number(atr, "atr")
    buffer = CONFIG["structure_buffer_atr"] * atr
    raw_stop = pivot["price"] - buffer if side == "buy" else pivot["price"] + buffer
    raw_risk = entry - raw_stop if side == "buy" else raw_stop - entry
    if raw_risk <= 0:
        return {"variant": "B", "accepted": False, "reason": "NO_CONFIRMED_SWING",
                "pivot": pivot, "raw_stop": raw_stop}
    bounded = bounded_adaptive_risk(raw_risk, atr=atr)
    if not bounded["accepted"]:
        return {"variant": "B", **bounded, "pivot": pivot, "raw_stop": raw_stop}
    risk = bounded["risk"]
    direction = 1.0 if side == "buy" else -1.0
    stop = entry - direction * risk
    prefix = rows[max(0, decision_index - CONFIG["donchian_length"]):decision_index]
    if len(prefix) < CONFIG["donchian_length"]:
        raise ResearchError("decision prefix lacks Donchian20 history")
    boundary = (max(_number(row["high"], "high") for row in prefix)
                if side == "buy" else min(_number(row["low"], "low") for row in prefix))
    target = target_space_check(side=side, entry=entry, boundary=boundary, risk=risk)
    if not target["accepted"]:
        return {
            "variant": "B", "accepted": False, "reason": target["reason"],
            "pivot": pivot, "raw_stop": raw_stop, "risk": risk,
            "risk_atr": bounded["risk_atr"], "target_space": target,
        }
    return {
        "variant": "B", "accepted": True, "reason": None,
        "plan": {
            "variant": "B", "side": side, "entry": entry, "stop": stop,
            "raw_stop": raw_stop, "risk": risk, "risk_atr": bounded["risk_atr"],
            "raw_risk_atr": bounded["raw_risk_atr"],
            "floor_applied": bounded["floor_applied"],
            "tp1": entry + direction * 1.5 * risk,
            "tp2": entry + direction * 2.0 * risk,
            "pivot": pivot, "structure_buffer_atr": CONFIG["structure_buffer_atr"],
            "donchian_boundary": boundary, "target_space_r": target["space_r"],
            "decision_index": decision_index, "prefix_end_index": decision_index,
            "synthetic_fill": True, "protective_stop_active": False,
        },
    }


def _touch(row: dict, price: float) -> bool:
    return _number(row["low"], "low") <= price <= _number(row["high"], "high")


def evaluate_outcome(rows: list[dict], *, decision_index: int, side: str, entry: float,
                     stop: float, tp1: float, tp2: float, horizon: int,
                     touch_confirmed: bool = False) -> dict:
    """Evaluate a synthetic proxy using conservative SL-first intrabar ordering."""
    if horizon not in HORIZONS:
        raise ResearchError(f"unsupported horizon: {horizon}")
    if side not in {"buy", "sell"}:
        raise ResearchError("side must be buy or sell")
    entry, stop, tp1, tp2 = map(float, (entry, stop, tp1, tp2))
    risk = abs(entry - stop)
    if risk <= 0:
        raise ResearchError("outcome risk must be positive")
    required_terminal = decision_index + horizon
    if required_terminal >= len(rows):
        return {
            "filled": False, "status": "CENSORED", "reason": "INCOMPLETE_HORIZON",
            "excluded_from_metrics": True, "horizon": horizon,
            "required_terminal_index": required_terminal,
            "available_terminal_index": len(rows) - 1,
            "fill_proxy": ("touch_within_4_bars" if touch_confirmed
                           else "disadvantaged_entry"),
            "synthetic_fill_only": True,
        }
    first = decision_index + 1
    last = required_terminal
    fill_index = decision_index
    if touch_confirmed:
        fill_index = next(
            (index for index in range(first, min(last, decision_index + 4) + 1)
             if _touch(rows[index], entry)), -1)
        if fill_index < 0:
            return {
                "filled": False, "fill_proxy": "touch_within_4_bars",
                "result": "NO_FILL_PROXY", "horizon": horizon,
                "ambiguous_intrabar": False,
            }
        first = fill_index
    direction = 1.0 if side == "buy" else -1.0
    max_adverse = max_favorable = 0.0
    result, expectancy, terminal = "MARK_TO_MARKET", None, last
    ambiguous = False
    bars_to_stop = None
    tp2_before_stop = False
    tp2_resolved = False
    for index in range(first, last + 1):
        row = rows[index]
        low, high = float(row["low"]), float(row["high"])
        if side == "buy":
            adverse, favorable = entry - low, high - entry
            stop_hit, tp1_hit, tp2_hit = low <= stop, high >= tp1, high >= tp2
        else:
            adverse, favorable = high - entry, entry - low
            stop_hit, tp1_hit, tp2_hit = high >= stop, low <= tp1, low <= tp2
        max_adverse = max(max_adverse, adverse)
        max_favorable = max(max_favorable, favorable)
        if not tp2_resolved and (stop_hit or tp2_hit):
            tp2_before_stop = tp2_hit and not stop_hit
            tp2_resolved = True
        if result == "MARK_TO_MARKET" and (stop_hit or tp1_hit):
            if stop_hit:
                result, expectancy, terminal = "SL", -1.0, index
                bars_to_stop = index - fill_index
                ambiguous = tp1_hit
            else:
                result, expectancy, terminal = "TP1", 1.5, index
    if expectancy is None:
        close = float(rows[last]["close"])
        mark_r = direction * (close - entry) / risk
        expectancy = min(1.5, max(-1.0, mark_r))
    return {
        "filled": True,
        "fill_proxy": "touch_within_4_bars" if touch_confirmed else "disadvantaged_entry",
        "fill_index": fill_index, "result": result, "expectancy_r": expectancy,
        "horizon": horizon, "terminal_index": terminal,
        "bars_to_stop": bars_to_stop,
        "early_stop": {str(bar): bars_to_stop is not None and bars_to_stop <= bar
                       for bar in range(1, 5)},
        "ambiguous_intrabar": ambiguous, "tp2_before_sl": tp2_before_stop,
        "mae_r": max_adverse / risk, "mfe_r": max_favorable / risk,
        "mae_usd": max_adverse, "mfe_usd": max_favorable,
        "mae_pct_entry": max_adverse / entry * 100.0,
        "mfe_pct_entry": max_favorable / entry * 100.0,
        "synthetic_fill_only": True,
        "status": "COMPLETE", "excluded_from_metrics": False,
    }


def state_compatibility(public_state: str, *, b_accepted: bool) -> dict:
    if public_state not in PUBLIC_STATES:
        raise ResearchError("unknown public state")
    has_plan = public_state in {"WAIT_TRIGGER", "ENTRY_READY"}
    return {
        "public_state": public_state,
        "research_state": public_state if (not has_plan or b_accepted) else "NO_PLAN",
        "b_rejected": has_plan and not b_accepted,
        "synthetic_fill_only": True,
        "position_confirmed": False,
        "protective_stop_active": False,
    }


def _metric_summary(outcomes: list[dict]) -> dict:
    complete = [item for item in outcomes if not item.get("excluded_from_metrics")]
    filled = [item for item in complete if item.get("filled")]
    touched = [item for item in filled if item["result"] in {"SL", "TP1"}]
    expectancies = [float(item["expectancy_r"]) for item in filled]
    return {
        "fills": len(filled),
        "eligible_complete_horizon": len(complete),
        "censored": len(outcomes) - len(complete),
        "censor_reasons": dict(Counter(
            item.get("reason") for item in outcomes if item.get("excluded_from_metrics"))),
        "no_fill": len(complete) - len(filled),
        "early_stop_cumulative": {
            str(bar): (sum(bool(item["early_stop"][str(bar)]) for item in filled) / len(filled)
                       if filled else None)
            for bar in range(1, 5)},
        "tp1_before_sl_per_resolved": (
            sum(item["result"] == "TP1" for item in touched) / len(touched) if touched else None),
        "tp1_before_sl_per_fill": (
            sum(item["result"] == "TP1" for item in filled) / len(filled) if filled else None),
        "tp2_before_sl_per_fill": (
            sum(bool(item["tp2_before_sl"]) for item in filled) / len(filled) if filled else None),
        "expectancy_r": mean(expectancies) if expectancies else None,
        "ambiguous_intrabar": sum(bool(item["ambiguous_intrabar"]) for item in filled),
        "mae_r": _distribution([float(item["mae_r"]) for item in filled]),
        "mfe_r": _distribution([float(item["mfe_r"]) for item in filled]),
        "mae_usd": _distribution([float(item["mae_usd"]) for item in filled]),
        "mfe_usd": _distribution([float(item["mfe_usd"]) for item in filled]),
        "mae_pct_entry": _distribution(
            [float(item["mae_pct_entry"]) for item in filled]),
        "mfe_pct_entry": _distribution(
            [float(item["mfe_pct_entry"]) for item in filled]),
    }


def _distribution(values: list[float]) -> dict:
    return {
        "count": len(values), "mean": mean(values) if values else None,
        "median": median(values) if values else None,
        "p75": _percentile(values, 0.75), "p90": _percentile(values, 0.90),
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
    }


def _stop_width_summary(plans: list[dict]) -> dict:
    return {
        "risk_atr": _distribution([float(plan["risk_atr"]) for plan in plans]),
        "risk_usd": _distribution([float(plan["risk"]) for plan in plans]),
        "risk_pct_entry": _distribution(
            [float(plan["risk"]) / float(plan["entry"]) * 100.0 for plan in plans]),
    }


def _cost_adjusted_expectancy(outcomes: list[dict], plans: list[dict], bps: int) -> float | None:
    values = []
    for outcome, plan in zip(outcomes, plans):
        if not outcome.get("filled"):
            continue
        cost_usd = float(plan["entry"]) * bps / 10_000.0
        values.append(float(outcome["expectancy_r"]) - cost_usd / float(plan["risk"]))
    return mean(values) if values else None


def _cost_sensitivity(events: list[dict], key: str) -> dict:
    paired = [event for event in events if event["b"]["accepted"]]
    result = {}
    for bps in (0, 5, 10):
        a_all_outcomes = [event["a"]["outcomes"][key] for event in events]
        a_all_plans = [event["a"]["plan"] for event in events]
        a_pair_outcomes = [event["a"]["outcomes"][key] for event in paired]
        a_pair_plans = [event["a"]["plan"] for event in paired]
        b_pair_outcomes = [event["b"]["outcomes"][key] for event in paired]
        b_pair_plans = [event["b"]["plan"] for event in paired]
        a_pair = _cost_adjusted_expectancy(a_pair_outcomes, a_pair_plans, bps)
        b_pair = _cost_adjusted_expectancy(b_pair_outcomes, b_pair_plans, bps)
        b_system_values = []
        for event in events:
            if not event["b"]["accepted"]:
                b_system_values.append(0.0)
                continue
            outcome, plan = event["b"]["outcomes"][key], event["b"]["plan"]
            if not outcome.get("filled"):
                b_system_values.append(0.0)
                continue
            cost_usd = float(plan["entry"]) * bps / 10_000.0
            b_system_values.append(
                float(outcome["expectancy_r"]) - cost_usd / float(plan["risk"]))
        result[str(bps)] = {
            "a_paired_expectancy_r": a_pair,
            "b_paired_expectancy_r": b_pair,
            "paired_delta_r": (b_pair - a_pair if a_pair is not None and b_pair is not None
                               else None),
            "a_system_expectancy_r": _cost_adjusted_expectancy(
                a_all_outcomes, a_all_plans, bps),
            "b_system_expectancy_per_a_signal_r": (
                mean(b_system_values) if b_system_values else None),
        }
    return result


def bootstrap_paired_delta(a_values: list[float], b_values: list[float], *,
                           iterations: int = 2000, seed: int = 260826) -> dict:
    if len(a_values) != len(b_values) or not a_values:
        return {"n": len(a_values), "mean": None, "lower_95": None, "upper_95": None}
    rng = random.Random(seed)
    deltas = [b - a for a, b in zip(a_values, b_values)]
    samples = [mean([deltas[rng.randrange(len(deltas))] for _ in deltas])
               for _ in range(iterations)]
    return {
        "n": len(deltas), "mean": mean(deltas),
        "lower_95": _percentile(samples, 0.025),
        "upper_95": _percentile(samples, 0.975),
    }


def replay(rows: list[dict], decisions: list[dict], *, horizons=HORIZONS) -> dict:
    """Replay predeclared decision events without overlap or access beyond each prefix."""
    state_counts = Counter()
    eligible = []
    for decision in decisions:
        state = decision.get("state")
        if state not in PUBLIC_STATES:
            raise ResearchError(f"unknown public state in decision: {state}")
        state_counts[state] += 1
        if state == "ENTRY_READY" and decision.get("previous_state") != "ENTRY_READY":
            eligible.append(decision)
    events, skipped, occupied_until = [], 0, -1
    for decision in sorted(eligible, key=lambda item: item["index"]):
        index = int(decision["index"])
        if index < 0 or index >= len(rows):
            raise ResearchError("decision index outside rows")
        if index <= occupied_until:
            skipped += 1
            continue
        a_plan = baseline_plan(
            decision["side"], entry_low=decision["entry_low"],
            entry_high=decision["entry_high"], atr=decision["atr"])
        b_result = adaptive_plan(
            rows[:index + 1], decision_index=index, side=decision["side"],
            entry_low=decision["entry_low"], entry_high=decision["entry_high"],
            atr=decision["atr"])
        event = {
            "decision_index": index, "decision_at": rows[index]["at"],
            "side": decision["side"], "public_state": decision.get("state", "ENTRY_READY"),
            "a": {"plan": a_plan, "outcomes": {}, "outcomes_touch": {}},
            "b": {"accepted": b_result["accepted"], "reason": b_result.get("reason"),
                  "plan": b_result.get("plan"), "outcomes": {}, "outcomes_touch": {}},
            "lifecycle": state_compatibility(
                decision.get("state", "ENTRY_READY"), b_accepted=b_result["accepted"]),
        }
        terminals = []
        for horizon in horizons:
            a_outcome = evaluate_outcome(
                rows, decision_index=index, side=decision["side"],
                entry=a_plan["entry"], stop=a_plan["stop"], tp1=a_plan["tp1"],
                tp2=a_plan["tp2"], horizon=horizon)
            event["a"]["outcomes"][str(horizon)] = a_outcome
            event["a"]["outcomes_touch"][str(horizon)] = evaluate_outcome(
                rows, decision_index=index, side=decision["side"],
                entry=a_plan["entry"], stop=a_plan["stop"], tp1=a_plan["tp1"],
                tp2=a_plan["tp2"], horizon=horizon, touch_confirmed=True)
            if horizon == CONFIG["primary_horizon"]:
                terminals.append(a_outcome.get("terminal_index", len(rows) - 1))
            if b_result["accepted"]:
                plan = b_result["plan"]
                b_outcome = evaluate_outcome(
                    rows, decision_index=index, side=decision["side"],
                    entry=plan["entry"], stop=plan["stop"], tp1=plan["tp1"],
                    tp2=plan["tp2"], horizon=horizon)
                event["b"]["outcomes"][str(horizon)] = b_outcome
                event["b"]["outcomes_touch"][str(horizon)] = evaluate_outcome(
                    rows, decision_index=index, side=decision["side"],
                    entry=plan["entry"], stop=plan["stop"], tp1=plan["tp1"],
                    tp2=plan["tp2"], horizon=horizon, touch_confirmed=True)
                if horizon == CONFIG["primary_horizon"]:
                    terminals.append(b_outcome.get("terminal_index", len(rows) - 1))
        occupied_until = max(terminals) if terminals else min(
            len(rows) - 1, index + CONFIG["primary_horizon"])
        events.append(event)
    metrics = {}
    for horizon in horizons:
        key = str(horizon)
        a_all = [event["a"]["outcomes"][key] for event in events]
        complete_events = [
            event for event in events
            if not event["a"]["outcomes"][key].get("excluded_from_metrics")]
        paired = [event for event in complete_events if event["b"]["accepted"]]
        a_paired = [event["a"]["outcomes"][key] for event in paired]
        b_paired = [event["b"]["outcomes"][key] for event in paired]
        a_all_touch = [event["a"]["outcomes_touch"][key] for event in events]
        a_paired_touch = [event["a"]["outcomes_touch"][key] for event in paired]
        b_paired_touch = [event["b"]["outcomes_touch"][key] for event in paired]
        a_exp = [item["expectancy_r"] for item in a_paired]
        b_exp = [item["expectancy_r"] for item in b_paired]
        a_early4 = [float(bool(item["early_stop"]["4"])) for item in a_paired]
        b_early4 = [float(bool(item["early_stop"]["4"])) for item in b_paired]
        metrics[key] = {
            "a_all": _metric_summary(a_all),
            "a_paired": _metric_summary(a_paired),
            "b_paired": _metric_summary(b_paired),
            "a_all_touch": _metric_summary(a_all_touch),
            "a_paired_touch": _metric_summary(a_paired_touch),
            "b_paired_touch": _metric_summary(b_paired_touch),
            "stop_width": {
                "a_all": _stop_width_summary(
                    [event["a"]["plan"] for event in complete_events]),
                "a_paired": _stop_width_summary([event["a"]["plan"] for event in paired]),
                "b_paired": _stop_width_summary([event["b"]["plan"] for event in paired]),
            },
            "cost_sensitivity_bps": _cost_sensitivity(complete_events, key),
            "paired_expectancy_delta_ci": bootstrap_paired_delta(a_exp, b_exp),
            "paired_early_stop_4_delta_ci": bootstrap_paired_delta(
                a_early4, b_early4),
            "a_eligible": len(complete_events), "b_accepted": len(paired),
            "signals_before_horizon_censor": len(events),
            "incomplete_horizon": len(events) - len(complete_events),
            "retention": (len(paired) / len(complete_events)
                          if complete_events else None),
            "b_rejects": dict(Counter(
                event["b"]["reason"] for event in complete_events
                if not event["b"]["accepted"])),
            "system_expectancy_a": mean(
                [event["a"]["outcomes"][key]["expectancy_r"]
                 for event in complete_events]) if complete_events else None,
            "system_expectancy_b_per_a_signal": (
                sum(item["expectancy_r"] for item in b_paired) / len(complete_events)
                if complete_events else None),
            "counts": {
                "signals": len(complete_events), "signals_censored": len(events) - len(complete_events),
                "primary_fills_a": sum(item.get("filled", False) for item in a_all),
                "primary_fills_b": sum(item.get("filled", False) for item in b_paired),
                "touch_fills_a": sum(item.get("filled", False) for item in a_all_touch),
                "touch_fills_b": sum(item.get("filled", False) for item in b_paired_touch),
                "rejects_b": len(complete_events) - len(paired),
            },
        }
    return {"schema": f"{SCHEMA}/replay", "events": events, "metrics": metrics,
            "skipped_overlap": skipped, "horizons": list(horizons),
            "input_counts": {
                "states": dict(sorted(state_counts.items())),
                "h1_eligible": len(decisions),
                "entry_ready_transitions": len(eligible),
                "non_entry_states_skipped": len(decisions) - len(eligible),
            }}


def _timeframe_report(rows: list[dict], timeframe: str, issues: list[str]) -> dict:
    warmup = CONFIG["warmup_bars"][timeframe]
    coverage = ((_at(rows[-1]["at"]) - _at(rows[0]["at"])).total_seconds() / 86400
                if len(rows) > 1 else 0.0)
    usable = ((_at(rows[-1]["at"]) - _at(rows[warmup - 1]["at"])).total_seconds() / 86400
              if len(rows) >= warmup else 0.0)
    large_gap = sum(
        1 for issue in issues
        if timeframe == "15min" and int(issue.rsplit(":", 1)[-1]) > 4 * 15 * 60)
    return {
        "row_count": len(rows), "first_at": rows[0]["at"] if rows else None,
        "last_at": rows[-1]["at"] if rows else None,
        "coverage_days": coverage, "usable_days_after_warmup": usable,
        "warmup_bars": warmup, "missing_intervals": len(issues),
        "gaps_over_4_m15_bars": large_gap, "issues": issues[:100],
        "closed_only": True, "timezone": "Asia/Bangkok",
    }


def _h1_crosscheck(h1_rows: list[dict], m15_rows: list[dict]) -> dict:
    buckets: dict[str, list[dict]] = {}
    for row in m15_rows:
        moment = _at(row["at"]).replace(minute=0, second=0, microsecond=0)
        buckets.setdefault(moment.isoformat(), []).append(row)
    h1 = {_at(row["at"]).replace(minute=0, second=0, microsecond=0).isoformat(): row
          for row in h1_rows}
    compared = mismatches = 0
    for key, group in buckets.items():
        if len(group) != 4 or key not in h1:
            continue
        aggregate = {
            "open": group[0]["open"], "high": max(row["high"] for row in group),
            "low": min(row["low"] for row in group), "close": group[-1]["close"],
        }
        compared += 1
        if any(not math.isclose(float(aggregate[field]), float(h1[key][field]),
                                rel_tol=1e-9, abs_tol=1e-7)
               for field in aggregate):
            mismatches += 1
    return {
        "compared_bars": compared, "mismatches": mismatches,
        "status": "PASS" if compared and not mismatches else "MISMATCH_OR_NO_OVERLAP",
    }


def split_manifest(rows: list[dict], *, dataset_sha256: str) -> dict:
    count = len(rows)
    development_end = int(count * CONFIG["split"][0])
    validation_end = int(count * sum(CONFIG["split"][:2]))
    ranges = {
        "development": (0, development_end),
        "validation": (development_end, validation_end),
        "locked_oos": (validation_end, count),
    }
    split = {}
    for name, (start, end) in ranges.items():
        split[name] = {
            "start_index": start, "end_index_exclusive": end,
            "row_count": max(0, end - start),
            "first_at": rows[start]["at"] if start < end else None,
            "last_at": rows[end - 1]["at"] if start < end else None,
        }
    return {
        "schema": f"{SCHEMA}/split-lock", "dataset_sha256": dataset_sha256,
        "method": "chronological_60_20_20", "random_shuffle": False,
        "locked": True, "oos_opened": False, "splits": split,
        "walk_forward": {
            "context_days": 90, "evaluate_days": 30, "step_days": 30,
            "minimum_folds": 4,
        },
    }


def preflight_snapshot(snapshot_path: Path) -> dict:
    """Inspect a local snapshot without network access or data interpolation."""
    snapshot_path = Path(snapshot_path).expanduser().resolve()
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ResearchError(f"cannot read local snapshot: {snapshot_path}") from exc
    if payload.get("asset") != "btcusd":
        raise ResearchError("snapshot asset must be btcusd")
    timeframes = payload.get("timeframes") or {}
    if set(timeframes) != {"1h", "15min"}:
        raise ResearchError("snapshot must contain exactly 1h and 15min")
    normalized, reports = {}, {}
    for timeframe in ("1h", "15min"):
        source = timeframes[timeframe]
        rows, issues = _normalized_rows(source.get("rows"), timeframe)
        normalized[timeframe] = rows
        reports[timeframe] = _timeframe_report(rows, timeframe, issues)
        reports[timeframe]["source_label"] = source.get("source_label")
        reports[timeframe]["source_meta"] = source.get("source_meta", {})
    usable_days = min(report["usable_days_after_warmup"] for report in reports.values())
    crosscheck = _h1_crosscheck(normalized["1h"], normalized["15min"])
    reasons = []
    if usable_days < CONFIG["minimum_days"]:
        reasons.append("HISTORY_LT_180_DAYS")
    if crosscheck["status"] != "PASS":
        reasons.append("H1_M15_ALIGNMENT_NOT_VERIFIED")
    if any(report["gaps_over_4_m15_bars"] for report in reports.values()):
        reasons.append("GAP_GT_4_M15_BARS")
    dataset_hash = sha256(snapshot_path)
    return {
        "schema": f"{SCHEMA}/data-preflight", "status": "BLOCKED_DATA" if reasons else "PASS",
        "reasons": reasons, "local_only": True, "network_used": False,
        "source_path": str(snapshot_path), "dataset_sha256": dataset_hash,
        "minimum_days": CONFIG["minimum_days"], "target_days": CONFIG["target_days"],
        "usable_days_after_warmup": usable_days, "timeframes": reports,
        "h1_from_m15_crosscheck": crosscheck,
        "normalized_rows": normalized,
    }


def _fixture_visuals(folder: Path) -> list[str]:
    """Create deterministic research-only visual QA cases, never production charts."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image
    from io import BytesIO

    decision_index, atr = 30, 2.0

    def fixture_rows(side: str, mode: str) -> list[dict]:
        start = datetime(2026, 8, 1, tzinfo=timezone.utc)
        rows = [{
            "at": (start + timedelta(minutes=15 * index)).isoformat(),
            "open": 100.0, "high": 101.0, "low": 99.0,
            "close": 100.0, "forming": False,
        } for index in range(64)]
        if mode == "no-swing":
            if side == "sell":
                for row in rows[decision_index - 20:decision_index]:
                    row["low"] = 92.0
            return rows
        pivot_index = decision_index - 4
        if side == "buy":
            pivot_price = 92.0 if mode == "cap" else 97.0
            lows = (pivot_price + 2.0, pivot_price + 1.0, pivot_price,
                    pivot_price + 1.5, pivot_price + 2.5)
            for offset, low in zip(range(-2, 3), lows):
                rows[pivot_index + offset]["low"] = low
            for row in rows[decision_index - 20:decision_index]:
                row["high"] = 108.0
        else:
            pivot_price = 104.0
            for offset, high in zip(range(-2, 3), (102.0, 103.0, pivot_price,
                                                   102.5, 101.5)):
                rows[pivot_index + offset]["high"] = high
            boundary = 98.0 if mode == "target" else 92.0
            for row in rows[decision_index - 20:decision_index]:
                row["low"] = boundary
        if mode == "early-stop":
            rows[decision_index + 1].update(
                {"open": 100.0, "high": 101.0, "low": 97.25, "close": 98.0})
        return rows

    cases = [
        ("accepted-buy-floor-2atr", "buy", "accepted"),
        ("accepted-sell-raw-2-3atr", "sell", "accepted"),
        ("reject-stop-over-cap", "buy", "cap"),
        ("reject-target-space", "sell", "target"),
        ("early-stop-buy", "buy", "early-stop"),
        ("no-confirmed-swing", "sell", "no-swing"),
    ]
    outputs = []
    for name, side, mode in cases:
        rows = fixture_rows(side, mode)
        entry_low, entry_high = 99.5, 100.5
        a_plan = baseline_plan(
            side, entry_low=entry_low, entry_high=entry_high, atr=atr)
        b_result = adaptive_plan(
            rows[:decision_index + 1], decision_index=decision_index, side=side,
            entry_low=entry_low, entry_high=entry_high, atr=atr)
        entry = a_plan["entry"]
        b_plan = b_result.get("plan")
        a_outcome = evaluate_outcome(
            rows, decision_index=decision_index, side=side,
            entry=a_plan["entry"], stop=a_plan["stop"], tp1=a_plan["tp1"],
            tp2=a_plan["tp2"], horizon=CONFIG["primary_horizon"])
        b_outcome = (evaluate_outcome(
            rows, decision_index=decision_index, side=side,
            entry=b_plan["entry"], stop=b_plan["stop"], tp1=b_plan["tp1"],
            tp2=b_plan["tp2"], horizon=CONFIG["primary_horizon"])
            if b_plan else None)
        pivot = b_plan.get("pivot") if b_plan else b_result.get("pivot")
        boundary = (b_plan.get("donchian_boundary") if b_plan else
                    (b_result.get("target_space") or {}).get("boundary"))
        note = ("B ACCEPTED" if b_result["accepted"] else
                f"B REJECT · {b_result['reason']}")
        if mode == "early-stop":
            note = "EARLY STOP EXAMPLE · A SL FIRST"
        figure, axes = plt.subplots(figsize=(12, 6), dpi=120)
        xs = list(range(len(rows)))
        closes = [row["close"] for row in rows]
        axes.plot(xs, closes, color="#64748b", linewidth=1.5, label="closed M15 fixture")
        future_xs = xs[decision_index + 1:]
        axes.vlines(
            future_xs, [rows[index]["low"] for index in future_xs],
            [rows[index]["high"] for index in future_xs], color="#94a3b8",
            linewidth=0.8, alpha=0.55, label="future closed-bar high/low")
        axes.axvline(decision_index, color="#111827", linestyle="--", linewidth=1.2,
                     label="decision t / future begins")
        axes.axvspan(decision_index + 1, len(rows) - 1, color="#e2e8f0", alpha=0.55,
                     label="future outcome")
        axes.axhspan(entry_low, entry_high, color="#99f6e4", alpha=0.28,
                     label=f"Entry Zone {entry_low:.2f}–{entry_high:.2f}")
        axes.axhline(entry, color="#0f766e", linewidth=1.6, label=f"synthetic entry {entry:.2f}")
        axes.axhline(a_plan["stop"], color="#f59e0b", linestyle="--",
                     label=f"A stop {a_plan['stop']:.2f} · {a_plan['risk_atr']:.2f} ATR")
        axes.axhline(a_plan["tp1"], color="#65a30d", linestyle=":",
                     label=f"A TP1 {a_plan['tp1']:.2f}")
        axes.axhline(a_plan["tp2"], color="#4d7c0f", linestyle="-.",
                     label=f"A TP2 {a_plan['tp2']:.2f}")
        if b_plan:
            axes.axhline(b_plan["stop"], color="#dc2626", linestyle="--",
                         label=f"B stop {b_plan['stop']:.2f} · {b_plan['risk_atr']:.2f} ATR")
            axes.axhline(b_plan["tp1"], color="#16a34a", linestyle=":",
                         label=f"B TP1 {b_plan['tp1']:.2f}")
            axes.axhline(b_plan["tp2"], color="#15803d", linestyle="-.",
                         label=f"B TP2 {b_plan['tp2']:.2f}")
        if pivot:
            axes.scatter([pivot["index"]], [pivot["price"]],
                         marker="v" if side == "buy" else "^",
                         s=70, color="#7c3aed", zorder=8,
                         label=(f"confirmed pivot {pivot['price']:.2f} "
                                f"(confirmed bar {pivot['confirmed_index']})"))
        if boundary is not None:
            axes.axhline(boundary, color="#2563eb", linewidth=1.2,
                         label=f"Donchian20 opposing boundary {boundary:.2f}")
        axes.set_title("RESEARCH A/B · NOT LIVE · SYNTHETIC FILL", loc="left",
                       fontweight="bold", fontsize=14)
        axes.text(0.99, 0.97, f"{note} · {side.upper()}", transform=axes.transAxes,
                  va="top", ha="right", fontweight="bold", color="#7f1d1d",
                  bbox={"boxstyle": "round,pad=0.3", "facecolor": "white",
                        "edgecolor": "#fecaca", "alpha": 0.96})
        axes.grid(True, alpha=0.25)
        axes.legend(loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=3, fontsize=8)
        axes.set_xlabel(f"fixture bar index (prefix 0–{decision_index} / future {decision_index + 1}–{len(rows) - 1})")
        axes.set_ylabel("synthetic USD price")
        figure.subplots_adjust(bottom=0.30, top=0.88, left=0.08, right=0.98)
        buffer = BytesIO()
        figure.savefig(buffer, format="png", dpi=120, facecolor="white")
        plt.close(figure)
        buffer.seek(0)
        image = Image.open(buffer).convert("RGB")
        path = folder / f"{name}.webp"
        image.save(path, format="WEBP", quality=88, method=6)
        sidecar = {
            "schema": f"{SCHEMA}/visual-evidence",
            "banner": "RESEARCH A/B · NOT LIVE · SYNTHETIC FILL",
            "case": name, "side": side, "decision_index": decision_index,
            "visible_prefix_end": decision_index,
            "future_outcome_start": decision_index + 1,
            "entry_zone": {"low": entry_low, "high": entry_high},
            "entry": entry, "atr": atr,
            "variant_a": {**a_plan, "outcome_32": a_outcome},
            "variant_b": {"accepted": b_result["accepted"],
                          "reason": b_result.get("reason"), "plan": b_plan,
                          "outcome_32": b_outcome},
            "confirmed_pivot": pivot, "donchian_boundary": boundary,
            "note": note,
            "production_artifact": False,
        }
        path.with_suffix(".json").write_text(json_text(sidecar), encoding="utf-8")
        outputs.extend([path.name, path.with_suffix(".json").name])
    return outputs


def _validate_decision_cache(path: Path, *, derived: dict) -> dict:
    path = Path(path).expanduser().resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ResearchError(f"cannot read local derived-decisions cache: {path}") from exc
    if payload != derived:
        raise ResearchError("derived-decisions cache mismatch: recomputation rejects tampering")
    return {
        "schema": f"{SCHEMA}/decision-cache-evidence", "source_path": str(path),
        "source_sha256": sha256(path), "exact_recomputation_match": True,
        "dataset_sha256": derived["dataset_sha256"],
        "event_count": len(derived["events"]), "oos_opened": False,
    }


def _walk_forward(rows: list[dict], decisions: list[dict], *, end_index: int) -> dict:
    """Evaluate locked dev/validation decisions in 90d context + 30d step-30 folds."""
    if not rows or end_index <= 0:
        return {"folds": [], "fold_count": 0, "consistent_direction_folds": 0}
    first = _at(rows[0]["at"])
    end_time = _at(rows[min(end_index, len(rows)) - 1]["at"])
    evaluation_start = first + timedelta(days=90)
    folds = []
    fold_number = 0
    while evaluation_start <= end_time:
        evaluation_end = min(evaluation_start + timedelta(days=30),
                             end_time + timedelta(microseconds=1))
        fold_row_end = next(
            (index for index, row in enumerate(rows[:end_index])
             if _at(row["at"]) >= evaluation_end), end_index)
        selected = [
            event for event in decisions
            if event["index"] < end_index
            and evaluation_start <= _at(rows[event["index"]]["at"]) < evaluation_end
            and event["index"] + 1 < fold_row_end
        ]
        result = replay(rows[:fold_row_end], selected)
        primary = result["metrics"][str(CONFIG["primary_horizon"])]
        a4 = primary["a_all"]["early_stop_cumulative"]["4"]
        b4 = primary["b_paired"]["early_stop_cumulative"]["4"]
        improved = (a4 is not None and b4 is not None and b4 < a4)
        folds.append({
            "fold": fold_number, "context_start_at": max(first, evaluation_start - timedelta(days=90)).isoformat(),
            "evaluation_start_at": evaluation_start.isoformat(),
            "evaluation_end_exclusive_at": evaluation_end.isoformat(),
            "decision_count": len(selected), "fold_prefix_end_index_exclusive": fold_row_end,
            "replay": result,
            "primary_early_stop_4_delta_b_minus_a": (
                b4 - a4 if a4 is not None and b4 is not None else None),
            "direction_improved": improved,
        })
        fold_number += 1
        evaluation_start += timedelta(days=30)
    nonempty = [fold for fold in folds if fold["decision_count"]]
    return {
        "schema": f"{SCHEMA}/walk-forward", "context_days": 90,
        "evaluate_days": 30, "step_days": 30, "folds": folds,
        "fold_count": len(folds), "nonempty_fold_count": len(nonempty),
        "consistent_direction_folds": sum(fold["direction_improved"] for fold in nonempty),
        "prefix_only": True, "locked_oos_opened": False,
    }


def _acceptance_diagnostics(metrics: dict) -> dict:
    replay_metrics = metrics.get("replay", {}).get("metrics", {})
    primary = replay_metrics.get(str(CONFIG["primary_horizon"]), {})
    a = primary.get("a_paired", {})
    b = primary.get("b_paired", {})
    a_early = (a.get("early_stop_cumulative") or {}).get("4")
    b_early = (b.get("early_stop_cumulative") or {}).get("4")
    absolute_improvement = (a_early - b_early
                            if a_early is not None and b_early is not None else None)
    relative_improvement = (absolute_improvement / a_early
                            if absolute_improvement is not None and a_early else None)
    a_tp1 = a.get("tp1_before_sl_per_fill")
    b_tp1 = b.get("tp1_before_sl_per_fill")
    paired_ci = primary.get("paired_expectancy_delta_ci", {})
    early_ci = primary.get("paired_early_stop_4_delta_ci", {})
    a_touch_early = ((primary.get("a_paired_touch", {}).get("early_stop_cumulative")
                      or {}).get("4"))
    b_touch_early = ((primary.get("b_paired_touch", {}).get("early_stop_cumulative")
                      or {}).get("4"))
    touch_improvement = (a_touch_early - b_touch_early
                         if a_touch_early is not None and b_touch_early is not None else None)
    retention = primary.get("retention")
    wf = metrics.get("walk_forward", {})
    nonempty = wf.get("nonempty_fold_count", 0)
    consistent = wf.get("consistent_direction_folds", 0)
    checks = {
        "early_stop_absolute_ge_5pp": (
            absolute_improvement >= 0.05 if absolute_improvement is not None else None),
        "early_stop_relative_ge_20pct": (
            relative_improvement >= 0.20 if relative_improvement is not None else None),
        "tp1_not_lower_by_more_than_2pp": (
            b_tp1 >= a_tp1 - 0.02 if a_tp1 is not None and b_tp1 is not None else None),
        "paired_expectancy_delta_ge_minus_005r": (
            paired_ci.get("mean") >= -0.05 if paired_ci.get("mean") is not None else None),
        "system_expectancy_delta_ge_minus_005r": (
            primary.get("system_expectancy_b_per_a_signal") >=
            primary.get("system_expectancy_a") - 0.05
            if primary.get("system_expectancy_a") is not None
            and primary.get("system_expectancy_b_per_a_signal") is not None else None),
        "retention_ge_70pct": retention >= 0.70 if retention is not None else None,
        "rejection_rate_le_30pct": (1.0 - retention) <= 0.30 if retention is not None else None,
        "walk_forward_direction_3_of_4": (
            consistent >= 3 and nonempty >= 4 if nonempty else None),
        "primary_touch_direction_consistent": (
            absolute_improvement * touch_improvement >= 0
            if absolute_improvement is not None and touch_improvement is not None else None),
        "early_stop_ci_not_extremely_wide": (
            not (early_ci.get("lower_95") < -0.05 and early_ci.get("upper_95") > 0.05)
            if early_ci.get("lower_95") is not None
            and early_ci.get("upper_95") is not None else None),
        "paired_sample_ge_50": primary.get("b_accepted", 0) >= 50,
        "a_sample_ge_100": primary.get("a_eligible", 0) >= 100,
    }
    return {
        "schema": f"{SCHEMA}/acceptance-diagnostics",
        "stage": "DEVELOPMENT_VALIDATION_ONLY", "locked_oos_evaluated": False,
        "thresholds": {
            "early_stop_absolute_improvement": 0.05,
            "early_stop_relative_improvement": 0.20,
            "tp1_max_degradation": 0.02,
            "expectancy_max_degradation_r": 0.05,
            "retention_minimum": 0.70, "rejection_maximum": 0.30,
            "walk_forward_consistency": "3_of_4",
        },
        "observed": {
            "early_stop_absolute_improvement": absolute_improvement,
            "early_stop_relative_improvement": relative_improvement,
            "tp1_delta_b_minus_a": (
                b_tp1 - a_tp1 if a_tp1 is not None and b_tp1 is not None else None),
            "paired_expectancy_delta_r": paired_ci.get("mean"),
            "paired_early_stop_4_delta_b_minus_a_ci": early_ci,
            "touch_early_stop_absolute_improvement": touch_improvement,
            "retention": retention,
        },
        "checks": checks,
        "performance_pass_to_next_gate_allowed": False,
        "reason": "LOCKED_OOS_REMAINS_CLOSED_UNTIL_CHECKPOINT_D",
    }


def _decision(preflight: dict, metrics: dict) -> tuple[str, list[str]]:
    if preflight["status"] != "PASS":
        return "INCONCLUSIVE", ["BLOCKED_DATA"] + list(preflight["reasons"])
    replay_metrics = metrics.get("replay", {}).get("metrics", metrics)
    primary = replay_metrics.get(str(CONFIG["primary_horizon"]), {})
    if primary.get("a_eligible", 0) < 100 or primary.get("b_accepted", 0) < 50:
        return "INCONCLUSIVE", ["INSUFFICIENT_EVENT_SAMPLE"]
    retention = primary.get("retention")
    if retention is not None and retention < 0.70:
        return "REJECT_B", ["RETENTION_LT_70_PERCENT"]
    diagnostics = metrics.get("acceptance", {})
    checks = diagnostics.get("checks", {})
    if checks.get("tp1_not_lower_by_more_than_2pp") is False:
        return "INCONCLUSIVE", ["VALIDATION_TP1_GATE_NOT_MET", "LOCKED_OOS_CLOSED"]
    if checks.get("paired_expectancy_delta_ge_minus_005r") is False:
        return "INCONCLUSIVE", ["VALIDATION_EXPECTANCY_GATE_NOT_MET", "LOCKED_OOS_CLOSED"]
    return "INCONCLUSIVE", ["CHECKPOINT_D_REQUIRED_BEFORE_LOCKED_OOS"]


def run_experiment(*, snapshot_path: Path, output_root: Path,
                   decisions_path: Path | None = None) -> dict:
    """Run local preflight and emit a deterministic, atomic research evidence package."""
    output_root = Path(output_root).expanduser().resolve()
    if output_root.exists():
        raise ResearchError(f"research output already exists: {output_root}")
    preflight = preflight_snapshot(snapshot_path)
    rows = preflight.pop("normalized_rows")
    split = split_manifest(rows["15min"], dataset_sha256=preflight["dataset_sha256"])
    metrics: dict = {
        str(horizon): {
            "status": "NOT_RUN_BLOCKED_DATA", "paired": {}, "system": {},
            "cost_sensitivity_bps": [0, 5, 10],
        } for horizon in HORIZONS
    }
    decision_evidence = None
    derived_decisions = None
    if preflight["status"] == "PASS":
        dev_validation_end = split["splits"]["validation"]["end_index_exclusive"]
        scoped_m15 = rows["15min"][:dev_validation_end]
        last_decision_close = _at(scoped_m15[-1]["at"]) + timedelta(minutes=15)
        scoped_h1 = [
            row for row in rows["1h"]
            if _at(row["at"]) + timedelta(hours=1) <= last_decision_close]
        scoped_dataset_hash = _object_sha256({"1h": scoped_h1, "15min": scoped_m15})
        derived_decisions = derive_decisions(
            scoped_h1, scoped_m15, dataset_sha256=scoped_dataset_hash,
            excluded_oos_count=len(rows["15min"]) - dev_validation_end,
            dataset_hash_scope="development_validation_prefix")
        if decisions_path is not None:
            decision_evidence = _validate_decision_cache(
                decisions_path, derived=derived_decisions)
        development_validation = [
            event for event in derived_decisions["events"]
            if event["index"] < dev_validation_end]
        aggregate = replay(rows["15min"][:dev_validation_end], development_validation)
        metrics = {
            "status": "RUN_DEVELOPMENT_VALIDATION",
            "replay": aggregate,
            "walk_forward": _walk_forward(
                rows["15min"], development_validation, end_index=dev_validation_end),
            "locked_oos_opened": False,
            "locked_oos_events_ignored": sum(
                event["index"] >= dev_validation_end
                for event in derived_decisions["events"]),
        }
        metrics["acceptance"] = _acceptance_diagnostics(metrics)
    decision, decision_reasons = _decision(preflight, metrics)
    checkpoint_d = "HOLD"
    if preflight["status"] == "PASS" and decision != "REJECT_B":
        checkpoint_d = "GO_REVIEW" if not decision_reasons else "HOLD"
    report = {
        "schema": f"{SCHEMA}/research-report", "experiment": CONFIG["experiment_id"],
        "data_status": preflight["status"], "decision": decision,
        "decision_reasons": decision_reasons,
        "checkpoint_d": checkpoint_d,
        "locked_oos_opened": False, "production_changed": False,
        "network_used": False, "synthetic_fill_only": True,
        "phase_2_trigger_buffer_tested": False,
        "summary": (
            "Local history does not meet the minimum data gate; performance replay and OOS "
            "remain unopened. Deterministic fixture correctness and visual QA are provided."
            if preflight["status"] != "PASS" else
            "Data preflight passed; Checkpoint D review is required before opening OOS."),
    }
    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".adaptive-stop-ab-", dir=output_root.parent))
    try:
        (temporary / "config.json").write_text(json_text(CONFIG), encoding="utf-8")
        (temporary / "data-preflight.json").write_text(json_text(preflight), encoding="utf-8")
        (temporary / "split-manifest.json").write_text(json_text(split), encoding="utf-8")
        (temporary / "metrics.json").write_text(json_text(metrics), encoding="utf-8")
        (temporary / "research-report.json").write_text(json_text(report), encoding="utf-8")
        if derived_decisions is not None:
            (temporary / "derived-decisions.json").write_text(
                json_text(derived_decisions), encoding="utf-8")
        if decision_evidence is not None:
            (temporary / "decision-cache-evidence.json").write_text(
                json_text(decision_evidence), encoding="utf-8")
        _fixture_visuals(temporary)
        artifact_names = sorted(path.name for path in temporary.iterdir() if path.is_file())
        manifest = {
            "schema": f"{SCHEMA}/manifest", "experiment": CONFIG["experiment_id"],
            "config": CONFIG, "dataset_sha256": preflight["dataset_sha256"],
            "code_sha256": sha256(Path(__file__)), "split_locked": True,
            "oos_opened": False, "production_changed": False,
            "files": {
                name: {"bytes": (temporary / name).stat().st_size,
                       "sha256": sha256(temporary / name)}
                for name in artifact_names
            },
        }
        (temporary / "manifest.json").write_text(json_text(manifest), encoding="utf-8")
        temporary.replace(output_root)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return {
        "status": "pass", "data_status": preflight["status"], "decision": decision,
        "locked_oos_opened": False,
        "production_changed": False, "directory": str(output_root),
        "manifest": str(output_root / "manifest.json"),
        "visual_count": len(list(output_root.glob("*.webp"))),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline research-only Style E+ BTC adaptive-stop A/B harness")
    parser.add_argument("--snapshot", required=True, type=Path,
                        help="local source-snapshot.json; network fetch is not supported")
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--decisions", type=Path,
                        help=("optional local derived-decisions cache; every field is "
                              "recomputed from prefixes and must match exactly"))
    args = parser.parse_args(argv)
    try:
        result = run_experiment(snapshot_path=args.snapshot, output_root=args.output_root,
                                decisions_path=args.decisions)
    except Exception as exc:
        print(f"adaptive-stop A/B: FAIL — {exc}")
        return 1
    print(json_text(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CONFIG", "HORIZONS", "PUBLIC_STATES", "REJECT_REASONS", "ResearchError",
    "adaptive_plan", "baseline_plan", "bootstrap_paired_delta", "derive_decisions",
    "bounded_adaptive_risk", "confirmed_pivot", "evaluate_outcome",
    "preflight_snapshot", "replay", "run_experiment", "sha256",
    "split_manifest", "state_compatibility", "target_space_check",
]
