"""Predeclared, IS-selected diagnostics for Style M v6 strategy variants.

QA research only: this module does not change the production oracle or select a
variant from OOS results.  It evaluates a deliberately small set of interpretable
rules from the same frozen BTCUSD H1 snapshot as the 180-day QA gate.
"""

from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from statistics import mean

from tools import (style_m_v6_story, style_m_v6_walkforward as walk)


SCHEMA = "style-m-v6-variant-diagnostics/v1"
DEFAULT_SNAPSHOT = Path("qa/style-m-v6-walkforward-20260831-v2/source-btcusd-h1.json")


@dataclass(frozen=True)
class Variant:
    name: str
    min_adx: float | None
    retest_quality: str
    entry_geometry: str
    expiry_hours: int
    rationale: str


# Fixed before looking at this diagnostic run.  This is a small hypothesis set,
# not an exhaustive optimizer: trend-strength context, retest confirmation,
# limit-entry geometry, and time decay are each tested once.
VARIANTS = (
    Variant("baseline", None, "zone_touch", "worst_boundary", 24,
            "Reference implementation of the approved 11:00 lifecycle."),
    Variant("adx20", 20.0, "zone_touch", "worst_boundary", 24,
            "Avoid quiet-range conditions while retaining transition/trending."),
    Variant("adx25", 25.0, "zone_touch", "worst_boundary", 24,
            "Trade only trending-strength conditions."),
    Variant("adx20_reclaim", 20.0, "reclaim_trigger_close", "worst_boundary", 24,
            "Require retest H1 close back through the trigger in trade direction."),
    Variant("adx25_reclaim", 25.0, "reclaim_trigger_close", "worst_boundary", 24,
            "Stronger ADX plus post-retest directional close confirmation."),
    Variant("adx20_limit", 20.0, "touch_trigger_boundary", "trigger_limit", 24,
            "Require a full return to the trigger boundary; model a limit fill there."),
    Variant("adx20_reclaim_12h", 20.0, "reclaim_trigger_close", "worst_boundary", 12,
            "Reject late signals/retests; conditional plan expires after half a day."),
)


def _quality_ok(plan: dict, row: dict, quality: str) -> bool:
    if quality == "zone_touch":
        return walk._touches(row, plan["entry_low"], plan["entry_high"])
    if quality == "reclaim_trigger_close":
        if not walk._touches(row, plan["entry_low"], plan["entry_high"]):
            return False
        return float(row["close"]) > plan["trigger"] if plan["side"] == "LONG" else float(row["close"]) < plan["trigger"]
    if quality == "touch_trigger_boundary":
        return (float(row["low"]) <= plan["entry_low"] if plan["side"] == "LONG"
                else float(row["high"]) >= plan["entry_high"])
    raise ValueError(f"unknown retest quality: {quality}")


def _entry_plan(plan: dict, geometry: str) -> tuple[dict, dict]:
    result = copy.deepcopy(plan)
    if geometry == "worst_boundary":
        fill = result["entry_high"] if result["side"] == "LONG" else result["entry_low"]
        basis = "worst_entry_boundary"
    elif geometry == "trigger_limit":
        fill = result["entry_low"] if result["side"] == "LONG" else result["entry_high"]
        basis = "trigger_boundary_limit"
    else:
        raise ValueError(f"unknown entry geometry: {geometry}")
    risk = (fill - result["sl"] if result["side"] == "LONG" else result["sl"] - fill)
    if risk <= 0:
        raise ValueError("entry geometry has non-positive risk")
    result["risk"] = round(float(risk), 8)
    if result["side"] == "LONG":
        result["rr1"] = round((result["tp1"] - fill) / risk, 8)
        result["rr2"] = round((result["tp2"] - fill) / risk, 8)
    else:
        result["rr1"] = round((fill - result["tp1"]) / risk, 8)
        result["rr2"] = round((fill - result["tp2"]) / risk, 8)
    return result, {"fill": fill, "basis": basis}


def simulate_variant(story: dict, forward_bars: list[dict], variant: Variant,
                     *, execution_costs: dict) -> dict:
    """OCO/retest simulation with a predeclared variant, never future data."""
    if len(forward_bars) != walk.HORIZON_HOURS:
        raise ValueError("variant diagnostics require the full 24 H1 forward horizon")
    if variant.min_adx is not None and float(story["indicators"]["adx14"]) < variant.min_adx:
        return {"status": "FILTERED_ADX", "scenario_states": {}, "exit_models": {}}
    bars = forward_bars[:variant.expiry_hours]
    plans = story["scenarios"]
    state = {side: "WAIT_TRIGGER" for side in plans}
    active: str | None = None
    trigger_index: int | None = None
    entry_index: int | None = None
    lifecycle = {"triggered": 0, "retests": 0, "invalidations": 0}

    signal_hits = [side for side, plan in plans.items()
                   if plan["state"] == "TRIGGERED_WAIT_RETEST"]
    if len(signal_hits) == 1:
        active = signal_hits[0]
        state[active] = "TRIGGERED_WAIT_RETEST"
        state["short" if active == "long" else "long"] = "CANCELLED_OPPOSITE_TRIGGER"
        trigger_index = -1
        lifecycle["triggered"] += 1

    entry: dict | None = None
    active_plan: dict | None = None
    for index, row in enumerate(bars):
        if active is None:
            long_hit = float(row["close"]) > plans["long"]["trigger"]
            short_hit = float(row["close"]) < plans["short"]["trigger"]
            if long_hit == short_hit:
                continue
            active = "long" if long_hit else "short"
            state[active] = "TRIGGERED_WAIT_RETEST"
            state["short" if active == "long" else "long"] = "CANCELLED_OPPOSITE_TRIGGER"
            trigger_index = index
            lifecycle["triggered"] += 1
            continue
        plan = plans[active]
        if index <= (trigger_index if trigger_index is not None else index):
            continue
        if walk._invalidated(plan, row):
            state[active] = "INVALIDATED"
            lifecycle["invalidations"] += 1
            break
        if _quality_ok(plan, row, variant.retest_quality):
            active_plan, entry = _entry_plan(plan, variant.entry_geometry)
            entry["at"] = row["at"]
            state[active] = "RETEST_OBSERVED"
            entry_index = index
            lifecycle["retests"] += 1
            break

    if active is None:
        state = {side: "EXPIRED" for side in plans}
    elif entry_index is None and state[active] == "TRIGGERED_WAIT_RETEST":
        state[active] = "EXPIRED"
    result = {"status": "PASS", "scenario_states": state, "triggered_side": active,
              "lifecycle": lifecycle, "entry": entry, "exit_models": {}}
    if active_plan is not None and entry_index is not None:
        exit_bars = bars[entry_index:]
        cost_r, cost_detail = walk._cost_r(active_plan, entry, execution_costs)
        for name, target in (("tp1_all_in", "tp1"), ("tp2_all_in", "tp2")):
            exit_result = walk._exit_model(active_plan, exit_bars, target_key=target)
            exit_result["cost_r"] = round(cost_r, 8)
            exit_result["after_cost_r"] = (round(float(exit_result["r"]) - cost_r, 8)
                                            if exit_result["r"] is not None else None)
            exit_result["cost_detail"] = cost_detail
            result["exit_models"][name] = exit_result
    return result


def _summary(records: list[dict]) -> dict:
    eligible = [record for record in records if record["simulation"]["status"] == "PASS"]
    summary = walk.summarize(eligible)
    summary["filtered_adx_days"] = len(records) - len(eligible)
    summary["eligible_plan_days"] = len(eligible)
    return summary


def _records(rows: list[dict], source_label: str, source_meta: dict, variant: Variant,
             *, days: int, in_sample_days: int, execution_costs: dict) -> list[dict]:
    candidates = []
    for index, row in enumerate(rows):
        cutoff = walk._at(row) + timedelta(hours=1)
        if (cutoff.hour == walk.CUTOFF_HOUR_BANGKOK and cutoff.minute == 0 and index >= 59
                and index + walk.HORIZON_HOURS < len(rows)):
            candidates.append((index, cutoff))
    if len(candidates) < days:
        raise ValueError("snapshot has insufficient 11:00 daily cutoffs")
    output = []
    for ordinal, (index, cutoff) in enumerate(candidates[-days:]):
        prepared = style_m_v6_story.build(rows[:index + 1], cutoff=cutoff,
                                          source_label=source_label, source_meta=source_meta)
        future = rows[index + 1:index + 1 + walk.HORIZON_HOURS]
        output.append({"ordinal": ordinal + 1,
                       "partition": "IN_SAMPLE" if ordinal < in_sample_days else "OUT_OF_SAMPLE",
                       "cutoff": cutoff.isoformat(), "adx14": prepared["story"]["indicators"]["adx14"],
                       "simulation": simulate_variant(prepared["story"], future, variant,
                                                       execution_costs=execution_costs)})
    return output


def _selection(summary: dict) -> dict:
    """Predeclared IS-only gate.  OOS deliberately has no role here."""
    tp1, tp2 = summary["exit_sensitivity"]["tp1_all_in"], summary["exit_sensitivity"]["tp2_all_in"]
    passes = (tp1["resolved"] >= 20 and tp2["resolved"] >= 20
              and (tp1["after_cost"]["expectancy_r"] or float("-inf")) > 0
              and (tp2["after_cost"]["expectancy_r"] or float("-inf")) > 0)
    return {"passes_is_gate": passes,
            "rule": "at least 20 resolved IS trades per TP model and positive after-cost expectancy for both"}


def run(*, snapshot: Path = DEFAULT_SNAPSHOT, days: int = 180,
        in_sample_days: int = 60) -> dict:
    source = json.loads(snapshot.read_text(encoding="utf-8"))
    rows = source["rows"]
    costs = walk.load_execution_costs()
    results = []
    for variant in VARIANTS:
        records = _records(rows, source["source_label"], source["source_meta"], variant,
                           days=days, in_sample_days=in_sample_days, execution_costs=costs)
        ins = _summary([record for record in records if record["partition"] == "IN_SAMPLE"])
        oos = _summary([record for record in records if record["partition"] == "OUT_OF_SAMPLE"])
        results.append({"variant": variant.__dict__, "in_sample": ins, "out_of_sample": oos,
                        "selection": _selection(ins)})
    return {"schema": SCHEMA, "snapshot": str(snapshot),
            "snapshot_sha256": walk.hashlib.sha256(snapshot.read_bytes()).hexdigest(),
            "days": days, "in_sample_days": in_sample_days,
            "selection_policy": "Variants are predeclared; OOS is holdout-only and cannot select a winner.",
            "execution_costs": costs, "variants": results}


def markdown(report: dict) -> str:
    lines = ["# Style M v6 — Predeclared strategy-variant diagnostics", "",
             "ใช้ snapshot เดียวกับ QA 180 วัน; grid ถูกกำหนดก่อนดูผล และเลือกได้จาก IS เท่านั้น (OOS มีไว้ทานสอบ).", "",
             "| Variant | IS TP1 after-cost R | IS TP2 after-cost R | OOS TP1 after-cost R | OOS TP2 after-cost R | IS gate |",
             "|---|---:|---:|---:|---:|---|"]
    for item in report["variants"]:
        name = item["variant"]["name"]
        ins, oos = item["in_sample"]["exit_sensitivity"], item["out_of_sample"]["exit_sensitivity"]
        lines.append("| {0} | {1} | {2} | {3} | {4} | {5} |".format(
            name, ins["tp1_all_in"]["after_cost"]["expectancy_r"],
            ins["tp2_all_in"]["after_cost"]["expectancy_r"],
            oos["tp1_all_in"]["after_cost"]["expectancy_r"],
            oos["tp2_all_in"]["after_cost"]["expectancy_r"],
            "PASS" if item["selection"]["passes_is_gate"] else "FAIL"))
    lines += ["", "## Interpretation", "",
              "- ADX filter trades less often; it may reduce noise but can discard profitable transitions.",
              "- Reclaim-close improves confirmation but delays entry and can miss fast continuations.",
              "- Trigger-limit geometry improves nominal RR but requires a deeper pullback and is more sensitive to non-fill and execution assumptions.",
              "- 12-hour expiry reduces stale plans but lowers the sample and can remove valid late-session setups.",
              "- No variant is promoted by this grid. Only variants passing the predeclared IS gate may proceed to a fresh, untouched OOS validation window.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(snapshot=args.snapshot)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "variant-diagnostics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "variant-diagnostics.md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "variants": len(report["variants"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
