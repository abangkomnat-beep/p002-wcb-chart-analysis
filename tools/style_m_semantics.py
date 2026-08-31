"""Deterministic semantic projection for Style M v5.

This module never decides a trade state.  It explains the already validated
``style-m-story/v1`` result with typed relations derived from the same facts.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from tools import style_m_story


SCHEMA = "style-m-semantic-decision/v1"
RULE_VERSION = "style-m-semantic-rules/v1"
VISIBLE_H1_BARS = 120
PRICE_EPSILON_USD = 0.01
PRECISION_POLICY = "usd-price-2dp/v1"


class SemanticContractError(RuntimeError):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def build(story: dict, base_facts: dict, rows: list[dict]) -> dict:
    try:
        style_m_story.validate(story)
    except Exception as exc:
        raise SemanticContractError("SEM_STORY_INVALID", str(exc)) from exc
    _validate_rows_source(story, rows)
    facts = base_facts.get("facts", base_facts)
    required = ("market.latest.close", "market.ema20", "market.ema50", "market.atr14")
    missing = [item for item in required if item not in facts]
    if missing:
        raise SemanticContractError("SEM_BASE_FACT_MISSING", ", ".join(missing))

    close = float(facts["market.latest.close"]["value"])
    ema20 = float(facts["market.ema20"]["value"])
    ema50 = float(facts["market.ema50"]["value"])
    atr = float(facts["market.atr14"]["value"])

    def relation(left: float, right: float) -> str:
        return "ABOVE" if left > right else "BELOW" if left < right else "EQUAL"

    close_20 = relation(close, ema20)
    close_50 = relation(close, ema50)
    close_position = ("ABOVE_BOTH" if close > ema20 and close > ema50 else
                      "BELOW_BOTH" if close < ema20 and close < ema50 else
                      "AT_BAND" if close in (ema20, ema50) else "BETWEEN")
    ema_stack = "BULLISH" if ema20 > ema50 else "BEARISH" if ema20 < ema50 else "FLAT"

    highs = list(story.get("pivots", {}).get("highs", []))
    lows = list(story.get("pivots", {}).get("lows", []))

    def pivot_relation(items: list[dict], kind: str) -> dict:
        if len(items) < 2:
            return {"value": "UNAVAILABLE", "previous_id": None, "latest_id": None,
                    "delta_usd": None, "delta_atr": None, "derived_from": []}
        previous, latest = items[-2], items[-1]
        delta = float(latest["price"]) - float(previous["price"])
        if kind == "high":
            value = "HIGHER_HIGH" if delta > 0 else "LOWER_HIGH" if delta < 0 else "EQUAL_HIGH"
        else:
            value = "HIGHER_LOW" if delta > 0 else "LOWER_LOW" if delta < 0 else "EQUAL_LOW"
        previous_id = f"structure.pivot.{kind}.{previous['index']}"
        latest_id = f"structure.pivot.{kind}.{latest['index']}"
        for fact_id in (previous_id, latest_id):
            if fact_id not in facts:
                raise SemanticContractError("SEM_BASE_FACT_MISSING", fact_id)
        return {"value": value, "previous_id": previous_id, "latest_id": latest_id,
                "delta_usd": round(delta, 8),
                "delta_atr": round(delta / atr, 8) if atr else None,
                "derived_from": [previous_id, latest_id, "market.atr14"]}

    high_relation = pivot_relation(highs, "high")
    low_relation = pivot_relation(lows, "low")
    pattern_map = {
        ("HIGHER_HIGH", "HIGHER_LOW"): "BULLISH_HH_HL",
        ("LOWER_HIGH", "LOWER_LOW"): "BEARISH_LH_LL",
        ("HIGHER_HIGH", "LOWER_LOW"): "EXPANDING_HH_LL",
        ("LOWER_HIGH", "HIGHER_LOW"): "CONTRACTING_LH_HL",
    }
    if "UNAVAILABLE" in (high_relation["value"], low_relation["value"]):
        pattern = "INSUFFICIENT"
    elif high_relation["value"].startswith("EQUAL") or low_relation["value"].startswith("EQUAL"):
        pattern = "AMBIGUOUS_EQUAL"
    else:
        pattern = pattern_map[(high_relation["value"], low_relation["value"])]

    sequence_buy = False
    sequence_sell = False
    if len(highs) >= 2 and len(lows) >= 2:
        hprev, hlast, lprev, llast = highs[-2], highs[-1], lows[-2], lows[-1]
        sequence_buy = bool(hprev["index"] < llast["index"] < hlast["index"] and
                            high_relation["value"] == "HIGHER_HIGH" and
                            low_relation["value"] == "HIGHER_LOW")
        sequence_sell = bool(lprev["index"] < hlast["index"] < llast["index"] and
                             high_relation["value"] == "LOWER_HIGH" and
                             low_relation["value"] == "LOWER_LOW")

    implications = {
        ("NO_PLAN", "INSUFFICIENT_STRUCTURE"): "WAIT_FOR_STRUCTURE",
        ("NO_PLAN", "STALE_STRUCTURE"): "WAIT_FOR_FRESH_STRUCTURE",
        ("NO_PLAN", "STRUCTURE_CONFLICT"): "WAIT_FOR_ALIGNMENT",
        ("NO_PLAN", "INVALID_GEOMETRY"): "REJECT_INVALID_GEOMETRY",
        ("NO_PLAN", "RR_TOO_LOW"): "REJECT_LOW_RR",
        ("NO_PLAN", "TARGET_PASSED"): "NO_CHASE_TARGET_PASSED",
        ("NO_PLAN", "PRICE_EXTENDED"): "NO_CHASE_PRICE_EXTENDED",
        ("WAIT_H1_CONFIRM", "PLAN_VALID"): "WAIT_FOR_H1_CONFIRMATION",
        ("PLAN_VALID", "PLAN_VALID"): "WAIT_FOR_RETEST",
        ("INVALIDATED", "STOP_INVALIDATED"): "REBUILD_AFTER_INVALIDATION",
    }
    key = (story["state"], story.get("reason_code"))
    if key not in implications:
        raise SemanticContractError("SEM_UNKNOWN_REASON_STATE", f"{key[0]}/{key[1]}")

    if story["state"] in ("WAIT_H1_CONFIRM", "PLAN_VALID"):
        alignment = "BUY_ALIGNED" if story.get("side") == "BUY" else "SELL_ALIGNED"
    elif story.get("reason_code") == "INSUFFICIENT_STRUCTURE":
        alignment = "INSUFFICIENT"
    elif story.get("reason_code") == "STALE_STRUCTURE":
        alignment = "STALE"
    else:
        alignment = "MIXED"

    supporting: list[str] = []
    contradicting: list[str] = []
    ordered = [
        ("claim.analysis.ema_stack", ema_stack),
        ("claim.analysis.close_position", close_position),
        ("claim.analysis.high_relation", high_relation["value"]),
        ("claim.analysis.low_relation", low_relation["value"]),
        ("claim.analysis.structure_pattern", pattern),
    ]
    bearish_market = ema_stack == "BEARISH" and close_position == "BELOW_BOTH"
    bullish_market = ema_stack == "BULLISH" and close_position == "ABOVE_BOTH"
    for claim_id, value in ordered:
        if bearish_market:
            (contradicting if value in {"HIGHER_HIGH", "HIGHER_LOW", "BULLISH_HH_HL"}
             else supporting).append(claim_id)
        elif bullish_market:
            (contradicting if value in {"LOWER_LOW", "LOWER_HIGH", "BEARISH_LH_LL"}
             else supporting).append(claim_id)
        elif claim_id.startswith("claim.analysis.ema") or claim_id.endswith("close_position"):
            supporting.append(claim_id)
        else:
            contradicting.append(claim_id)

    observations = {
        "WAIT_FOR_STRUCTURE": ["NEED_MORE_CONFIRMED_PIVOTS"],
        "WAIT_FOR_FRESH_STRUCTURE": ["NEED_FRESH_ANCHORS_WITHIN_72H"],
        "WAIT_FOR_ALIGNMENT": ["NEED_BULLISH_SEQUENCE_HL_THEN_HH", "NEED_BEARISH_SEQUENCE_LH_THEN_LL"],
        "REJECT_INVALID_GEOMETRY": ["NEED_VALID_ORDERED_GEOMETRY"],
        "REJECT_LOW_RR": ["NEED_POLICY_RR_SPACE"],
        "NO_CHASE_TARGET_PASSED": ["NEED_NEW_SETUP_AFTER_TARGET_PASSED"],
        "NO_CHASE_PRICE_EXTENDED": ["NEED_PRICE_RETURN_WITHIN_ONE_ATR"],
        "WAIT_FOR_H1_CONFIRMATION": ["NEED_H1_TRIGGER_CLOSE"],
        "WAIT_FOR_RETEST": ["NEED_RETEST_WITHOUT_CHASING"],
        "REBUILD_AFTER_INVALIDATION": ["NEED_FULL_REBUILD_AFTER_INVALIDATION"],
    }
    implication = implications[key]
    trendline = _trendline(story, facts, rows)
    breakout = _breakout(story, facts, rows, trendline)
    relations = {
        "close_vs_ema20": {"value": close_20, "derived_from": ["market.latest.close", "market.ema20"]},
        "close_vs_ema50": {"value": close_50, "derived_from": ["market.latest.close", "market.ema50"]},
        "close_position": {"value": close_position,
                           "derived_from": ["market.latest.close", "market.ema20", "market.ema50"]},
        "ema_stack": {"value": ema_stack, "derived_from": ["market.ema20", "market.ema50"]},
        "high_relation": high_relation,
        "low_relation": low_relation,
        "structure_pattern": {"value": pattern,
                              "derived_from": high_relation["derived_from"][:2] + low_relation["derived_from"][:2]},
        "sequence_buy_ok": {"value": sequence_buy,
                            "derived_from": high_relation["derived_from"][:2] + low_relation["derived_from"][:2]},
        "sequence_sell_ok": {"value": sequence_sell,
                             "derived_from": high_relation["derived_from"][:2] + low_relation["derived_from"][:2]},
    }
    permissions = _permissions(story["state"], trendline, breakout)
    output = {
        "schema": SCHEMA, "rule_version": RULE_VERSION, "asset": story["asset"],
        "timeframe": story["timeframe"], "cutoff": story["cutoff"],
        "source_sha256": story["source_sha256"],
        "oracle": {"schema": story["schema"], "state": story["state"],
                   "side": story.get("side"), "reason_code": story.get("reason_code")},
        "relations": relations,
        "decision": {"alignment": alignment, "implication": implication,
                     "supporting_claim_ids": supporting,
                     "contradicting_claim_ids": contradicting,
                     "unmet_observation_codes": observations[implication],
                     "reassessment_observation_codes": observations[implication],
                     "permissions": permissions},
        "trendline": trendline, "breakout": breakout,
    }
    output["semantic_sha256"] = _hash(output)
    return output


def validate(semantic: dict, *, story: dict, base_facts: dict, rows: list[dict]) -> None:
    oracle = semantic.get("oracle", {})
    expected_oracle = {"schema": story.get("schema"), "state": story.get("state"),
                       "side": story.get("side"), "reason_code": story.get("reason_code")}
    if oracle != expected_oracle:
        raise SemanticContractError("SEM_ORACLE_BINDING_MISMATCH", "oracle projection changed")
    rebuilt = build(story, base_facts, rows)
    if rebuilt != semantic:
        raise SemanticContractError("SEM_DERIVATION_MISMATCH", "semantic projection mismatch")


def _hash(value: dict) -> str:
    payload = dict(value)
    payload.pop("semantic_sha256", None)
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _validate_rows_source(story: dict, rows: list[dict]) -> None:
    if not rows:
        return
    cutoff = datetime.fromisoformat(str(story["cutoff"]).replace("Z", "+00:00"))
    previous_at = None
    previous_index = None
    projected_rows = []
    for ordinal, raw in enumerate(rows):
        try:
            at = datetime.fromisoformat(str(raw["at"]).replace("Z", "+00:00"))
            if at.tzinfo is None:
                at = at.replace(tzinfo=cutoff.tzinfo)
            index = int(raw.get("index", ordinal))
            projected = {key: raw[key] for key in ("at", "open", "high", "low", "close")}
        except (KeyError, TypeError, ValueError) as exc:
            raise SemanticContractError("SEM_ROWS_NOT_CANONICAL", str(exc)) from exc
        if (raw.get("forming") is True or at >= cutoff or
                (previous_at is not None and at <= previous_at) or
                (previous_index is not None and index <= previous_index)):
            raise SemanticContractError("SEM_ROWS_NOT_CANONICAL", f"row {ordinal}")
        previous_at, previous_index = at, index
        projected_rows.append(projected)
    latest = story.get("latest", {})
    if any(latest.get(key) != projected_rows[-1].get(key)
           for key in ("at", "open", "high", "low", "close") if key in latest):
        raise SemanticContractError("SEM_ROWS_NOT_CANONICAL", "latest row mismatch")
    projection = {"cutoff": story["cutoff"], "source_label": story.get("source_label"),
                  "source_meta": story.get("source_meta", {}), "rows": projected_rows}
    source_hash = hashlib.sha256(json.dumps(
        projection, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    if source_hash != story.get("source_sha256"):
        raise SemanticContractError("SEM_SOURCE_HASH_MISMATCH", "rows/source projection changed")


def _trendline(story: dict, facts: dict, rows: list[dict]) -> dict:
    forbidden = {"selection_rule": "descending-high-visible/v1", "status": "NOT_SHOWN",
                 "reason": "NO_ELIGIBLE_PAIR", "anchor_fact_ids": [], "anchor_indexes": [],
                 "anchor_prices": [], "anchor_times": [], "slope_per_bar": None,
                 "intercept": None, "visible_start_index": None,
                 "precision_policy": PRECISION_POLICY,
                 "price_epsilon_usd": PRICE_EPSILON_USD,
                 "intermediate_high_fact_ids_checked": [],
                 "cutoff": story["cutoff"], "source_sha256": story["source_sha256"],
                 "permission": "FORBIDDEN"}
    if not rows:
        return forbidden
    visible = rows[-VISIBLE_H1_BARS:]
    visible_start = int(visible[0].get("index", len(rows) - len(visible)))
    highs = [item for item in story.get("pivots", {}).get("highs", [])
             if int(item["index"]) >= visible_start]
    candidates = []
    for left in highs:
        for right in highs:
            gap = int(right["index"]) - int(left["index"])
            if gap >= 12 and float(left["price"]) > float(right["price"]):
                candidates.append((gap, left, right))
    candidates.sort(key=lambda item: (-item[0], int(item[1]["index"]), int(item[2]["index"])))
    for _, left, right in candidates:
        slope = (float(right["price"]) - float(left["price"])) / (
            int(right["index"]) - int(left["index"]))
        intercept = float(left["price"]) - slope * int(left["index"])
        intermediate = [item for item in highs
                        if int(left["index"]) < int(item["index"]) < int(right["index"])]
        checked_ids = [f"structure.pivot.high.{item['index']}" for item in intermediate]
        if any(float(item["price"]) - (intercept + slope * int(item["index"])) >
               PRICE_EPSILON_USD
               for item in intermediate):
            continue
        ids = [f"structure.pivot.high.{left['index']}",
               f"structure.pivot.high.{right['index']}"]
        if any(item not in facts for item in ids):
            result = dict(forbidden)
            result["reason"] = "PROVENANCE_INCOMPLETE"
            return result
        return {"selection_rule": "descending-high-visible/v1", "status": "SHOWN",
                "reason": "ELIGIBLE_PAIR", "anchor_fact_ids": ids,
                "anchor_indexes": [int(left["index"]), int(right["index"])],
                "anchor_prices": [float(left["price"]), float(right["price"])],
                "anchor_times": [left["at"], right["at"]],
                "slope_per_bar": slope, "intercept": intercept,
                "visible_start_index": visible_start, "cutoff": story["cutoff"],
                "precision_policy": PRECISION_POLICY,
                "price_epsilon_usd": PRICE_EPSILON_USD,
                "intermediate_high_fact_ids_checked": checked_ids,
                "source_sha256": story["source_sha256"], "permission": "CONTEXT_ONLY"}
    forbidden["visible_start_index"] = visible_start
    return forbidden


def _breakout(story: dict, facts: dict, rows: list[dict], trendline: dict) -> dict:
    base = {"evaluation_rule": "closed-h1-above-descending-line/v1",
            "status": "NOT_EVALUATED", "trendline_anchor_fact_ids": [],
            "evaluated_candle_fact_id": None, "evaluated_close": None,
            "line_value_at_candle": None, "source_sha256": story["source_sha256"],
            "permission": "FORBIDDEN"}
    if trendline["status"] != "SHOWN":
        return base
    right_index = trendline["anchor_indexes"][1]
    checked = [row for row in rows if int(row.get("index", -1)) > right_index]
    base["trendline_anchor_fact_ids"] = list(trendline["anchor_fact_ids"])
    if not checked:
        return base
    last = checked[-1]
    for row in checked:
        line = trendline["intercept"] + trendline["slope_per_bar"] * int(row["index"])
        if float(row["close"]) > line:
            fact_id = f"market.candle.close.{row['index']}"
            if fact_id not in facts:
                return base
            return {**base, "status": "CONFIRMED_UP_BREAK",
                    "evaluated_candle_fact_id": fact_id,
                    "evaluated_close": float(row["close"]),
                    "line_value_at_candle": line, "permission": "CONTEXT_ONLY"}
    fact_id = f"market.candle.close.{last['index']}"
    if fact_id not in facts:
        return base
    line = trendline["intercept"] + trendline["slope_per_bar"] * int(last["index"])
    return {**base, "status": "NOT_CONFIRMED", "evaluated_candle_fact_id": fact_id,
            "evaluated_close": float(last["close"]), "line_value_at_candle": line,
            "permission": "CONTEXT_ONLY"}


def _permissions(state: str, trendline: dict, breakout: dict) -> dict:
    active = state in {"WAIT_H1_CONFIRM", "PLAN_VALID"}
    allowed = "CONDITIONAL" if state == "WAIT_H1_CONFIRM" else "ALLOWED"
    return {"market_structure": "CONTEXT_ONLY",
            "active_side": allowed if active else "FORBIDDEN",
            "prior_side": "DIAGNOSTIC_ONLY" if state == "INVALIDATED" else "FORBIDDEN",
            "trade_geometry": allowed if active else "FORBIDDEN",
            "trigger_status": allowed if active else "FORBIDDEN",
            "reassessment": "ALLOWED", "news": "CONTEXT_ONLY",
            "trendline": trendline["permission"], "breakout": breakout["permission"]}


__all__ = ["PRECISION_POLICY", "PRICE_EPSILON_USD", "RULE_VERSION", "SCHEMA",
           "VISIBLE_H1_BARS", "SemanticContractError", "build", "validate"]
