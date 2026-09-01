"""Adapters from existing canonical D/E/M evidence to the public TPR contract.

Adapters only project fields already present in a style oracle.  Missing RR,
expiry, trigger, or lifecycle evidence produces an explicit DATA_HOLD manifest;
no adapter derives replacement levels.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta
from typing import Any

from tools import trade_plan_public_contract


_VOLATILE_EVIDENCE_KEYS = {
    # Generated at evaluation time; not part of the market snapshot.
    "evaluated_at", "retrieved_at", "generated_at",
    # Continuity metadata may change after a successful rerun while the
    # underlying confirmed price levels remain identical.
    "locked_since",
}


def _stable_evidence(value: Any) -> Any:
    """Remove runtime metadata before hashing canonical evidence.

    Price/level facts and their source fields are retained recursively.  This
    keeps a rerun over the same closed-bar snapshot byte-stable even when the
    evaluator clock or zone-memory bookkeeping changes.
    """
    if isinstance(value, dict):
        return {key: _stable_evidence(nested) for key, nested in value.items()
                if key not in _VOLATILE_EVIDENCE_KEYS}
    if isinstance(value, list):
        return [_stable_evidence(nested) for nested in value]
    return value


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        _stable_evidence(value), sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def hold(*, style_id: str, asset: str, article_name: str, article_bytes: bytes,
         evidence: Any, reasons: list[str]) -> dict:
    """Return a diagnostic sidecar that the selector must reject."""
    return {
        "schema": trade_plan_public_contract.SCHEMA,
        "style_id": style_id,
        "asset": asset,
        "article": article_name,
        "article_sha256": trade_plan_public_contract.sha256_bytes(article_bytes),
        "qa_status": "DATA_HOLD",
        "publishable": False,
        "plan_status": "DATA_HOLD",
        "side": None,
        "current_close": None,
        "valid_until": None,
        "evidence_hash": canonical_hash(evidence),
        "rr_policy_version": "TPR-RR/v1",
        "plans": [],
        "hold_reasons": list(reasons),
    }


def bind_article(contract: dict, article_bytes: bytes) -> dict:
    bound = dict(contract)
    bound["article_sha256"] = trade_plan_public_contract.sha256_bytes(article_bytes)
    return bound


def _cutoff(cutoff_at: str | datetime) -> datetime:
    value = (cutoff_at if isinstance(cutoff_at, datetime)
             else datetime.fromisoformat(str(cutoff_at).replace("Z", "+00:00")))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("cutoff_at ต้องมี timezone")
    return value


def _eligible_targets(side: str, low: float, high: float, stop: float,
                      targets: list[float], *, minimum_rr: float | None = None) -> tuple[list[float], list[float]]:
    """Keep canonical TP levels whose calculated gross RR passes the public floor."""
    if side == "BUY":
        risk = high - stop
        rewards = [target - high for target in targets]
    else:
        risk = stop - low
        rewards = [low - target for target in targets]
    if risk <= 0:
        return [], []
    floor = _minimum_rr() if minimum_rr is None else float(minimum_rr)
    pairs = [(target, round(reward / risk, 6))
             for target, reward in zip(targets, rewards)
             if reward > 0 and round(reward / risk, 6) >= floor]
    return [target for target, _ in pairs], [ratio for _, ratio in pairs]


def _contract(*, style_id: str, asset: str, article_name: str,
              article_bytes: bytes, evidence: dict, current_close: float,
              cutoff_at: str, valid_until: str, leg: dict) -> dict:
    return {
        "schema": trade_plan_public_contract.SCHEMA,
        "style_id": style_id, "asset": asset, "article": article_name,
        "article_sha256": trade_plan_public_contract.sha256_bytes(article_bytes),
        "qa_status": "PASS_QA", "publishable": True,
        "plan_status": "WAIT_TRIGGER", "side": leg["side"],
        "current_close": current_close, "cutoff_at": cutoff_at,
        "valid_until": valid_until,
        "evidence_hash": canonical_hash(evidence),
        "rr_policy_version": "TPR-RR/v1", "plans": [leg],
    }


def _minimum_rr() -> float:
    return float(trade_plan_public_contract.load_policy()["minimum_gross_rr"])


def select_e_candidate(story: dict) -> str | None:
    """เลือก key เดียวกับ public adapter เพื่อให้บท/ภาพ/sidecar พูดฝั่งเดียวกัน."""
    current = float((story.get("current") or {}).get("close", math.nan))
    scenarios = story.get("scenarios") or {}
    order = [story.get("public_plan_key", "primary"), "primary", "counter", "contingency"]
    seen: set[str] = set()
    for key in order:
        if key in seen:
            continue
        seen.add(key)
        raw = scenarios.get(key)
        if not isinstance(raw, dict) or not raw.get("daily_entry", True):
            continue
        try:
            side = str(raw["side"]).upper()
            low, high = sorted((float(raw["entry_low"]), float(raw["entry_high"])))
            stop = float(raw["sl"])
            trigger = float(raw["trigger"])
            targets, _ratios = _eligible_targets(
                side, low, high, stop, [float(value) for value in raw["tps"]],
                minimum_rr=1.2)
            strict = trigger > current if side == "BUY" else trigger < current
            if side in {"BUY", "SELL"} and targets and strict:
                return key
        except (KeyError, TypeError, ValueError):
            continue
    return None


def style_d(*, story: dict, cutoff_at: str | datetime,
            article_name: str, article_bytes: bytes) -> dict:
    """Choose the regime-side complete D1 scenario and project its existing levels."""
    current = float((story.get("current") or {}).get("close", math.nan))
    scenarios = story.get("scenarios") or {}
    preferred = "down" if (story.get("regime") or {}).get("down") else "up"
    expiry = trade_plan_public_contract.load_policy()["expiry_hours_by_style"][
        "d_chart_story"]
    reasons = []
    for key in (preferred,):
        raw = scenarios.get(key)
        if not isinstance(raw, dict):
            reasons.append(f"D_{key.upper()}_SCENARIO_MISSING")
            continue
        try:
            side = "BUY" if key == "up" else "SELL"
            low, high = sorted((float(raw["entry_low"]), float(raw["entry_high"])))
            stop, trigger = float(raw["entry_invalidation"]), float(raw["trigger"])
            raw_targets = [float(value) for value in raw["targets"]]
            targets, ratios = _eligible_targets(side, low, high, stop, raw_targets,
                                                minimum_rr=1.2)
            strict = trigger > current if side == "BUY" else trigger < current
            if not targets or not strict:
                raise ValueError("geometry/RR/strict trigger")
            leg = {
                "side": side,
                "trigger": {"condition": str(raw["condition"]), "value": trigger},
                "entry_zone": {"low": low, "high": high},
                "stop_loss": stop, "take_profit": targets,
                "risk_reward": ratios, "rr_basis": "gross_pre_cost",
                "invalidation": {"condition": str(raw["invalidation"]),
                                 "value": stop},
            }
            cutoff = _cutoff(cutoff_at)
            return _contract(
                style_id="d_chart_story", asset=story["asset"],
                article_name=article_name, article_bytes=article_bytes,
                evidence=story, current_close=current, cutoff_at=cutoff.isoformat(),
                valid_until=(cutoff + timedelta(hours=expiry)).isoformat(),
                leg=leg)
        except (KeyError, TypeError, ValueError):
            reasons.append(f"D_{key.upper()}_SCENARIO_INCOMPLETE_OR_RR_FAIL")
    return hold(style_id="d_chart_story", asset=story.get("asset", ""),
                article_name=article_name, article_bytes=article_bytes,
                evidence=story, reasons=reasons)


def style_e(*, story: dict, cutoff_at: str | datetime,
            article_name: str, article_bytes: bytes) -> dict:
    """Project an existing Fibonacci scenario; trigger is the canonical zone exit.

    BUY uses the upper entry boundary and SELL uses the lower entry boundary after
    the scenario's closed-H1 confirmation.  No new price is introduced.
    """
    current = float((story.get("current") or {}).get("close", math.nan))
    expiry = trade_plan_public_contract.load_policy()["expiry_hours_by_style"][
        "e_indicator"]
    reasons = []
    # เลือกตามลำดับ: แผนหลัก → สวนแนวโน้ม → contingency ที่คำนวณจากแท่งปิดล่าสุด
    # โดยตัดแผนที่ไกลเกิน daily_entry หรือ trigger ไม่ strict ออกก่อนเสมอ
    keys = [story.get("public_plan_key", "primary"), "primary", "counter", "contingency"]
    seen: set[str] = set()
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        raw = (story.get("scenarios") or {}).get(key)
        if not isinstance(raw, dict):
            reasons.append(f"E_{key.upper()}_SCENARIO_MISSING")
            continue
        try:
            side = str(raw["side"]).upper()
            low, high = sorted((float(raw["entry_low"]), float(raw["entry_high"])))
            stop = float(raw["sl"])
            raw_targets = [float(value) for value in raw["tps"]]
            trigger = float(raw["trigger"])
            targets, ratios = _eligible_targets(side, low, high, stop, raw_targets)
            strict = trigger > current if side == "BUY" else trigger < current
            reachable = bool(raw.get("daily_entry", True))
            if side not in {"BUY", "SELL"} or not targets or not strict or not reachable:
                raise ValueError("geometry/RR/strict trigger")
            leg = {
                "side": side,
                "trigger": {"condition": str(raw["trigger_condition"]),
                            "value": trigger},
                "entry_zone": {"low": low, "high": high},
                "stop_loss": stop, "take_profit": targets,
                "risk_reward": ratios, "rr_basis": "gross_pre_cost",
                "invalidation": {"condition": "closed H1 reaches canonical SL",
                                 "value": stop},
            }
            cutoff = _cutoff(cutoff_at)
            return _contract(
                style_id="e_indicator", asset=story["asset"],
                article_name=article_name, article_bytes=article_bytes,
                evidence=story, current_close=current, cutoff_at=cutoff.isoformat(),
                valid_until=(cutoff + timedelta(hours=expiry)).isoformat(),
                leg=leg)
        except (KeyError, TypeError, ValueError):
            reasons.append(f"E_{key.upper()}_SCENARIO_INCOMPLETE_OR_RR_FAIL_OR_TOO_FAR")
    return hold(style_id="e_indicator", asset=story.get("asset", ""),
                article_name=article_name, article_bytes=article_bytes,
                evidence=story, reasons=reasons)


def public_plan_block(contract: dict) -> str:
    """Render contract facts without deriving or changing any value."""
    return trade_plan_public_contract.public_plan_block(contract)


def style_m_v6(*, story: dict, article_name: str, article_bytes: bytes) -> dict:
    """Project canonical v6 OCO facts; non-baseline lifecycle states fail closed."""
    scenarios = story.get("scenarios") or {}
    if set(scenarios) != {"long", "short"}:
        return hold(style_id="m_btcusd_h1_visual_daily", asset="btc",
                    article_name=article_name, article_bytes=article_bytes,
                    evidence=story, reasons=["M_SCENARIOS_INCOMPLETE"])
    if any(plan.get("state") != "WAIT_TRIGGER" for plan in scenarios.values()):
        return hold(style_id="m_btcusd_h1_visual_daily", asset="btc",
                    article_name=article_name, article_bytes=article_bytes,
                    evidence=story, reasons=["M_LIFECYCLE_NOT_MAPPED_TO_TPR_V1"])
    if any(plan.get("extended") or plan.get("no_chase") for plan in scenarios.values()):
        return hold(style_id="m_btcusd_h1_visual_daily", asset="btc",
                    article_name=article_name, article_bytes=article_bytes,
                    evidence=story, reasons=["M_ENTRY_TOO_FAR_NO_CHASE"])
    valid_until = {plan.get("valid_until") for plan in scenarios.values()}
    if len(valid_until) != 1 or None in valid_until:
        return hold(style_id="m_btcusd_h1_visual_daily", asset="btc",
                    article_name=article_name, article_bytes=article_bytes,
                    evidence=story, reasons=["M_VALID_UNTIL_MISMATCH"])

    def leg(key: str, side: str) -> dict:
        plan = scenarios[key]
        return {
            "side": side,
            "trigger": {"condition": plan["trigger_rule"], "value": plan["trigger"]},
            "entry_zone": {"low": plan["entry_low"], "high": plan["entry_high"]},
            "stop_loss": plan["sl"],
            "take_profit": [plan["tp1"], plan["tp2"]],
            "risk_reward": [plan["rr1"], plan["rr2"]],
            "rr_basis": "gross_pre_cost",
            "invalidation": {
                "condition": "closed H1 reaches stop after trigger", "value": plan["sl"]},
        }

    return {
        "schema": trade_plan_public_contract.SCHEMA,
        "style_id": "m_btcusd_h1_visual_daily",
        "asset": "btc",
        "article": article_name,
        "article_sha256": trade_plan_public_contract.sha256_bytes(article_bytes),
        "qa_status": "PASS_QA",
        "publishable": True,
        "plan_status": "WAIT_TRIGGER",
        "side": "OCO",
        "current_close": story["latest"]["close"],
        "cutoff_at": story["cutoff"],
        "valid_until": next(iter(valid_until)),
        "evidence_hash": story["source_sha256"],
        "rr_policy_version": "TPR-RR/v1",
        "plans": [leg("long", "BUY"), leg("short", "SELL")],
    }


__all__ = ["bind_article", "canonical_hash", "hold", "public_plan_block",
           "style_d", "style_e", "style_m_v6"]
