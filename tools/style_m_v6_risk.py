"""Leakage-safe Style M daily-volatility risk research helpers.

Research is side-effect free; production must pass an explicitly approved
policy to ``apply_policy``.  Daily bars are aggregated only from complete
Bangkok calendar days before the cutoff.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from statistics import mean
from typing import Iterable

from tools import style_m_v6_story as story_mod

SCHEMA = "style-m-v6-risk-contract/v1"
CONTRACT_VERSION = "M-RISK/v1"
BASELINE_ID = "B0_H1_ATR14_LEGACY"
DAILY_METRICS = ("ADR14", "D1_ATR14")
FLOOR_COEFFICIENTS = (0.35, 0.50, 0.65)
CAP_COEFFICIENTS = (0.85, 1.00, 1.25)


class RiskUnavailable(ValueError):
    """Incomplete or invalid evidence; callers must fail closed."""


def _at(value: object) -> datetime:
    return story_mod._at(value)


def _num(value: object, label: str) -> float:
    return story_mod._number(value, label)


def completed_daily_bars(rows: Iterable[dict], *, cutoff: datetime,
                         require_complete: bool = True) -> list[dict]:
    if cutoff.tzinfo is None:
        raise RiskUnavailable("cutoff ต้องมี timezone")
    groups: dict[str, list[dict]] = defaultdict(list)
    limit = cutoff.astimezone(story_mod.BANGKOK)
    for index, raw in enumerate(rows or []):
        stamp = _at(raw.get("at"))
        if stamp + timedelta(hours=1) > limit:
            continue
        values = {key: _num(raw.get(key), f"rows[{index}].{key}")
                  for key in ("open", "high", "low", "close")}
        if not values["low"] <= min(values["open"], values["close"]) <= max(values["open"], values["close"]) <= values["high"]:
            raise RiskUnavailable("OHLC envelope ไม่ถูกต้อง")
        groups[stamp.date().isoformat()].append({"at": stamp, **values})
    result = []
    for day in sorted(groups):
        bars = sorted(groups[day], key=lambda item: item["at"])
        complete = len(bars) == 24 and [item["at"].hour for item in bars] == list(range(24))
        if not complete:
            if require_complete:
                continue
            raise RiskUnavailable(f"daily bar ไม่ครบ 24 ชั่วโมง: {day}")
        result.append({"at": f"{day}T00:00:00+07:00", "date": day,
                       "open": bars[0]["open"], "high": max(x["high"] for x in bars),
                       "low": min(x["low"] for x in bars), "close": bars[-1]["close"],
                       "h1_count": 24})
    if result and result[-1]["date"] >= limit.date().isoformat():
        raise RiskUnavailable("forming daily bar ถูกใช้")
    return result


def daily_volatility(rows: Iterable[dict], *, cutoff: datetime, metric: str,
                     length: int = 14) -> dict:
    if metric not in DAILY_METRICS or length != 14:
        raise RiskUnavailable("Style M ใช้ ADR14 หรือ D1_ATR14 เท่านั้น")
    bars = completed_daily_bars(rows, cutoff=cutoff)
    if len(bars) < length:
        raise RiskUnavailable(f"daily bars ไม่พอ: {len(bars)} < {length}")
    tr = []
    for i, bar in enumerate(bars):
        prior = bars[i - 1]["close"] if i else None
        tr.append(max(bar["high"] - bar["low"],
                      abs(bar["high"] - prior), abs(bar["low"] - prior)) if prior is not None else bar["high"] - bar["low"])
    if metric == "ADR14":
        value = mean(bar["high"] - bar["low"] for bar in bars[-length:])
    else:
        value = mean(tr[:length])
        for item in tr[length:]:
            value = (value * 13.0 + item) / 14.0
    if value <= 0:
        raise RiskUnavailable("daily volatility ต้องมากกว่า 0")
    return {"metric": metric, "value": round(float(value), 8), "length": length,
            "closed_daily_bars": len(bars), "last_closed_date": bars[-1]["date"],
            "basis": "completed_bangkok_calendar_days_before_cutoff"}


def _anchor(story: dict, plan: dict) -> tuple[float, str]:
    pivots = story.get("pivots") or {}
    if plan["side"] == "LONG":
        vals = [float(x["price"]) for x in pivots.get("lows", []) if float(x["price"]) < plan["entry_high"]]
        return (max(vals), "confirmed_h1_swing_low") if vals else (float(story["donchian"]["lower"]), "opposite_donchian_boundary")
    vals = [float(x["price"]) for x in pivots.get("highs", []) if float(x["price"]) > plan["entry_low"]]
    return (min(vals), "confirmed_h1_swing_high") if vals else (float(story["donchian"]["upper"]), "opposite_donchian_boundary")


def candidate_grid() -> list[dict]:
    result = [{"candidate_id": BASELINE_ID, "volatility_metric": "H1_ATR14",
               "floor_coefficient": None, "max_cap_coefficient": None,
               "structural_rule": "legacy_h1_atr_buffer"}]
    for metric in DAILY_METRICS:
        for floor in FLOOR_COEFFICIENTS:
            for cap in CAP_COEFFICIENTS:
                result.append({"candidate_id": f"{metric}_F{floor:.2f}_C{cap:.2f}",
                               "volatility_metric": metric, "floor_coefficient": floor,
                               "max_cap_coefficient": cap,
                               "structural_rule": "confirmed_swing_else_opposite_donchian"})
    return result


def _round(value: float, mode) -> float:
    return float(Decimal(str(value)).quantize(story_mod.PRICE_TICK, rounding=mode))


def apply_policy(story: dict, *, volatility: dict, floor_coefficient: float,
                 max_cap_coefficient: float, candidate_id: str,
                 no_plan_on_cap: bool = True) -> dict:
    if volatility.get("metric") not in DAILY_METRICS or float(volatility.get("value", 0)) <= 0:
        raise RiskUnavailable("volatility evidence ไม่ถูกต้อง")
    if floor_coefficient not in FLOOR_COEFFICIENTS or max_cap_coefficient not in CAP_COEFFICIENTS:
        raise RiskUnavailable("coefficient ไม่อยู่ใน frozen grid")
    cap = float(volatility["value"]) * max_cap_coefficient
    output = dict(story); output["scenarios"] = {}; legs = {}
    cap_breach = False
    for key, source in story["scenarios"].items():
        plan = dict(source); edge = float(plan["entry_high"] if plan["side"] == "LONG" else plan["entry_low"])
        anchor, rule = _anchor(story, plan)
        structural = edge - anchor if plan["side"] == "LONG" else anchor - edge
        if structural <= 0: raise RiskUnavailable(f"{plan['side']} structural risk ไม่เป็นบวก")
        floor = float(volatility["value"]) * floor_coefficient
        risk = max(structural, floor)
        detail = {"volatility_metric": volatility["metric"], "volatility_value": round(float(volatility["value"]), 8),
                  "floor_coefficient": floor_coefficient, "structural_anchor": round(anchor, 8),
                  "structural_anchor_rule": rule, "structural_risk": round(structural, 8),
                  "volatility_floor": round(floor, 8), "final_risk": round(risk, 8),
                  "max_risk_cap": round(cap, 8), "no_plan_reason": None}
        if risk > cap:
            cap_breach = True; detail["no_plan_reason"] = "FINAL_RISK_EXCEEDS_DAILY_VOLATILITY_CAP"
        else:
            if plan["side"] == "LONG":
                plan["sl"] = _round(edge - risk, ROUND_FLOOR); plan["risk"] = _round(edge - plan["sl"], ROUND_HALF_UP)
                plan["tp1"] = _round(edge + 1.5 * plan["risk"], ROUND_CEILING); plan["tp2"] = _round(edge + 2.0 * plan["risk"], ROUND_CEILING)
                plan["rr1"] = round((plan["tp1"] - edge) / plan["risk"], 4); plan["rr2"] = round((plan["tp2"] - edge) / plan["risk"], 4)
            else:
                plan["sl"] = _round(edge + risk, ROUND_CEILING); plan["risk"] = _round(plan["sl"] - edge, ROUND_HALF_UP)
                plan["tp1"] = _round(edge - 1.5 * plan["risk"], ROUND_FLOOR); plan["tp2"] = _round(edge - 2.0 * plan["risk"], ROUND_FLOOR)
                plan["rr1"] = round((edge - plan["tp1"]) / plan["risk"], 4); plan["rr2"] = round((edge - plan["tp2"]) / plan["risk"], 4)
            plan["risk_policy"] = candidate_id
        legs[key] = detail; output["scenarios"][key] = plan
    if no_plan_on_cap and cap_breach:
        for key, plan in output["scenarios"].items():
            plan["state"] = "NO_PLAN"; legs[key]["no_plan_reason"] = legs[key]["no_plan_reason"] or "OCO_LEG_EXCEEDS_CAP"
    output["risk_contract"] = {"schema": SCHEMA, "contract_version": CONTRACT_VERSION,
                                "candidate_id": candidate_id, "volatility": volatility,
                                "no_plan_on_cap": no_plan_on_cap, "legs": legs}
    return output


def snapshot_hash(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _code_hash() -> str:
    """Hash the exact research implementation used for a calibration run."""
    return hashlib.sha256(__import__("pathlib").Path(__file__).read_bytes()).hexdigest()


def _baseline_risk_metadata(story: dict) -> dict:
    legs = {key: {"volatility_metric": "H1_ATR14", "volatility_value": story["indicators"]["atr14"],
                  "floor_coefficient": None, "structural_anchor": plan["sl"],
                  "structural_anchor_rule": "legacy_h1_atr_buffer", "structural_risk": plan["risk"],
                  "volatility_floor": None, "final_risk": plan["risk"], "max_risk_cap": None,
                  "no_plan_reason": None}
            for key, plan in story["scenarios"].items()}
    return {"volatility_metric": "H1_ATR14", "volatility_value": story["indicators"]["atr14"],
            "floor_coefficient": None, "structural_anchor": None, "structural_risk": None,
            "final_risk": None, "max_risk_cap": None, "no_plan_reason": None, "legs": legs}


def validate_no_future_leakage(rows: Iterable[dict], *, cutoff: datetime) -> None:
    completed_daily_bars(rows, cutoff=cutoff)


def calibrate(rows: list[dict], *, source_label: str = "snapshot",
              source_meta: dict | None = None, days: int = 180,
              in_sample_days: int = 60, execution_costs: dict | None = None) -> dict:
    """Evaluate the frozen candidate grid on identical chronological slices."""
    from collections import Counter
    from tools import style_m_v6_walkforward as walk
    ordered = sorted((dict(item) for item in rows), key=lambda item: item["at"])
    cutoffs = []
    for index, row in enumerate(ordered):
        cutoff = _at(row["at"]) + timedelta(hours=1)
        if (cutoff.hour == walk.CUTOFF_HOUR_BANGKOK and cutoff.minute == 0
                and index >= 59 and index + walk.HORIZON_HOURS < len(ordered)):
            cutoffs.append((index, cutoff))
    if len(cutoffs) < days:
        raise RiskUnavailable(f"usable daily cutoffs {len(cutoffs)} < requested {days}")
    grid = candidate_grid(); records = {item["candidate_id"]: [] for item in grid}
    dataset_hash = snapshot_hash({"source_label": source_label, "source_meta": source_meta or {}, "rows": ordered})
    cost_path = walk.DEFAULT_COST_CONFIG_PATH if execution_costs is None else None
    cost_hash = (hashlib.sha256(cost_path.read_bytes()).hexdigest()
                 if cost_path is not None else snapshot_hash(execution_costs or {}))
    code_hash = _code_hash()
    grid_hash = snapshot_hash(grid)
    for ordinal, (index, cutoff) in enumerate(cutoffs[-days:]):
        prefix, future = ordered[:index + 1], ordered[index + 1:index + 1 + walk.HORIZON_HOURS]
        base = {"ordinal": ordinal + 1, "cutoff": cutoff.isoformat(),
                "partition": "IN_SAMPLE" if ordinal < in_sample_days else "OUT_OF_SAMPLE",
                "dataset_snapshot_hash": dataset_hash, "code_hash": code_hash,
                "execution_cost_config_hash": cost_hash, "grid_hash": grid_hash}
        try:
            built = story_mod.build(prefix, cutoff=cutoff, source_label=source_label,
                                    source_meta=source_meta or {})
        except story_mod.StoryUnavailable as exc:
            for candidate in grid:
                record_base = {**base, "candidate_id": candidate["candidate_id"],
                               "candidate_config_hash": snapshot_hash(candidate)}
                metadata = {"volatility_metric": None,
                    "volatility_value": None, "floor_coefficient": None,
                    "structural_anchor": None, "structural_risk": None,
                    "final_risk": None, "max_risk_cap": None,
                    "no_plan_reason": "STORY_UNAVAILABLE"}
                records[candidate["candidate_id"]].append({**record_base, "status": "UNAVAILABLE",
                    "error": str(exc), "risk_metadata": metadata,
                    "risk_metadata_hash": snapshot_hash(metadata)})
            continue
        for candidate in grid:
            cid = candidate["candidate_id"]
            record_base = {**base, "candidate_id": cid,
                           "candidate_config_hash": snapshot_hash(candidate)}
            if cid == BASELINE_ID:
                trial = built["story"]
                risk_metadata = _baseline_risk_metadata(trial)
            else:
                try:
                    vol = daily_volatility(prefix, cutoff=cutoff, metric=candidate["volatility_metric"])
                    trial = apply_policy(built["story"], volatility=vol,
                                         floor_coefficient=candidate["floor_coefficient"],
                                         max_cap_coefficient=candidate["max_cap_coefficient"], candidate_id=cid)
                    legs = trial["risk_contract"]["legs"]
                    risk_metadata = {"volatility_metric": vol["metric"],
                                     "volatility_value": vol["value"],
                                     "floor_coefficient": candidate["floor_coefficient"],
                                     "structural_anchor": None, "structural_risk": None,
                                     "final_risk": None,
                                     "max_risk_cap": candidate["max_cap_coefficient"],
                                     "no_plan_reason": next((item["no_plan_reason"] for item in legs.values()
                                                              if item.get("no_plan_reason")), None),
                                     "legs": legs}
                except RiskUnavailable as exc:
                    metadata = {"volatility_metric": candidate["volatility_metric"],
                                                            "volatility_value": None,
                                                            "floor_coefficient": candidate["floor_coefficient"],
                                                            "structural_anchor": None, "structural_risk": None,
                                                            "final_risk": None,
                                                            "max_risk_cap": candidate["max_cap_coefficient"],
                                                            "no_plan_reason": "RISK_EVIDENCE_UNAVAILABLE"}
                    records[cid].append({**record_base, "status": "UNAVAILABLE", "error": str(exc),
                                         "risk_metadata": metadata,
                                         "risk_metadata_hash": snapshot_hash(metadata)}); continue
            if any(plan.get("state") == "NO_PLAN" for plan in trial["scenarios"].values()):
                records[cid].append({**record_base, "status": "NO_PLAN", "risk_metadata": risk_metadata,
                                     "risk_metadata_hash": snapshot_hash(risk_metadata)}); continue
            simulation = walk.simulate(trial, future, execution_costs=execution_costs)
            records[cid].append({**record_base, "status": "PASS", "risk_metadata": risk_metadata,
                                 "risk_metadata_hash": snapshot_hash(risk_metadata),
                                 "simulation": simulation})

    def summarize(items: list[dict]) -> dict:
        no_plan = sum(x["status"] == "NO_PLAN" for x in items)
        valid = [x for x in items if x["status"] == "PASS"]
        sims = [x["simulation"] for x in valid]
        triggered = sum(bool(x.get("triggered_side")) for x in sims)
        fills = sum(bool(x.get("entry")) for x in sims)
        exits = {}
        for model in ("tp1_all_in", "tp2_all_in"):
            vals = [x["exit_models"][model] for x in sims if model in x.get("exit_models", {})]
            raw = [float(x["r"]) for x in vals if x.get("r") is not None]
            net = [float(x["after_cost_r"]) for x in vals if x.get("after_cost_r") is not None]
            counts = Counter(x["outcome"] for x in vals)
            exits[model] = {"resolved": len(raw), "trades_with_retest": len(vals),
                            "tp1_wins": counts.get("TP1", 0), "tp2_wins": counts.get("TP2", 0),
                            "stop_before_tp": counts.get("STOP", 0) + counts.get("STOP_AMBIGUOUS_BAR", 0),
                            "same_bar": counts.get("STOP_AMBIGUOUS_BAR", 0) + counts.get("AMBIGUOUS_ENTRY_TARGET", 0),
                            "expiry": counts.get("OPEN_AT_EXPIRY", 0),
                            "raw_expectancy_r": mean(raw) if raw else None,
                            "after_cost_expectancy_r": mean(net) if net else None,
                            "outcomes": dict(sorted(counts.items()))}
        return {"attempted": len(items), "evaluated": len(valid), "triggered": triggered, "fills": fills,
                "trigger_rate": triggered / len(items) if items else None,
                "fill_rate": fills / triggered if triggered else None, "no_plan": no_plan,
                "no_plan_rate": no_plan / len(items) if items else None, "exits": exits}
    summary = {}
    for item in grid:
        cid = item["candidate_id"]; all_items = records[cid]
        summary[cid] = {"candidate": item,
                        "in_sample": summarize([x for x in all_items if x["partition"] == "IN_SAMPLE"]),
                        "out_of_sample": summarize([x for x in all_items if x["partition"] == "OUT_OF_SAMPLE"]),
                        "combined": summarize(all_items), "records": all_items}
    def eligible(item: dict) -> bool:
        oos = item["out_of_sample"]["exits"]["tp1_all_in"]
        combined = item["combined"]["exits"]["tp1_all_in"]
        return oos["resolved"] >= 30 and combined["resolved"] >= 60 and (oos["after_cost_expectancy_r"] or 0) > 0
    options = [item for item in summary.values() if eligible(item)]
    options.sort(key=lambda item: ((item["out_of_sample"]["exits"]["tp1_all_in"]["after_cost_expectancy_r"] or float("-inf")),
                                   (item["out_of_sample"]["fill_rate"] or float("-inf")),
                                   -(item["out_of_sample"]["no_plan_rate"] or 1.0),
                                   item["candidate"]["candidate_id"]), reverse=True)
    recommendation = {"status": "PROMOTE_CANDIDATE", "candidate_id": options[0]["candidate"]["candidate_id"]} if options else {"status": "STOP_NO_EVIDENCE", "reason": "minimum 60 resolved/30 OOS positive after-cost not met"}
    pareto = [{"candidate_id": item["candidate"]["candidate_id"],
               "oos_after_cost_tp1_r": item["out_of_sample"]["exits"]["tp1_all_in"]["after_cost_expectancy_r"],
               "oos_fill_rate": item["out_of_sample"]["fill_rate"], "oos_no_plan_rate": item["out_of_sample"]["no_plan_rate"],
               "oos_resolved": item["out_of_sample"]["exits"]["tp1_all_in"]["resolved"]} for item in summary.values()]
    return {"schema": "style-m-v6-calibration/v1", "contract_version": CONTRACT_VERSION,
            "methodology": {"closed_h1_only": True, "chronological": True, "cutoff": "Asia/Bangkok 11:00",
                            "forward_bars": walk.HORIZON_HOURS, "grid_hash": grid_hash,
                            "execution_costs": walk.load_execution_costs() if execution_costs is None else execution_costs},
            "provenance": {"dataset_snapshot_hash": dataset_hash, "source_label": source_label,
                           "source_meta": source_meta or {}, "code_hash": code_hash,
                           "execution_cost_config_path": str(cost_path) if cost_path else None,
                           "execution_cost_config_hash": cost_hash,
                           "candidate_grid_hash": grid_hash, "candidate_count": len(grid)},
            "coverage": {"source_rows": len(ordered), "attempted_days": days, "in_sample_days": in_sample_days,
                         "out_of_sample_days": days - in_sample_days}, "pareto_table": pareto,
            "recommendation": recommendation, "candidates": summary}


__all__ = ["SCHEMA", "CONTRACT_VERSION", "BASELINE_ID", "DAILY_METRICS", "FLOOR_COEFFICIENTS", "CAP_COEFFICIENTS", "RiskUnavailable", "completed_daily_bars", "daily_volatility", "candidate_grid", "apply_policy", "snapshot_hash", "validate_no_future_leakage", "calibrate"]
