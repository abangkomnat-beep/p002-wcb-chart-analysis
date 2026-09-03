"""Canonical Style M v7 facts and parity contract."""
from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal, ROUND_HALF_UP

from tools import style_m_v7_risk, style_m_v7_story

SCHEMA = "style-m-article-visual-facts/v4"
PARITY_SCHEMA = "style-m-claim-parity-report/v4"
CONTRACT_VERSION = "M-PROD/v7"


def _hash(value: dict) -> str:
    payload = dict(value)
    payload.pop("facts_sha256", None)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def build(story: dict, rows: list[dict]) -> dict:
    style_m_v7_story.validate(story)
    geometry = story.get("risk_geometry")
    if not isinstance(geometry, dict) or geometry.get("policy_id") != style_m_v7_risk.POLICY_ID:
        raise ValueError("v7 facts ต้องมี ADR14 risk_geometry")
    facts = {"market.latest.close": story["latest"]["close"],
             "market.atr14": story["indicators"]["atr14"],
             "zone.donchian.upper": story["donchian"]["upper"],
             "zone.donchian.lower": story["donchian"]["lower"],
             "zone.donchian.width": story["donchian"]["width"],
             "risk_geometry": geometry}
    claims = {}
    for side, plan in story["scenarios"].items():
        leg = {key: plan.get(key) for key in
               ("trigger", "entry_low", "entry_high", "sl", "tp1", "tp2", "risk", "rr1", "rr2", "state", "no_plan_reason")}
        facts[f"plan.{side}"] = leg
        claims[f"claim.plan.{side}"] = {"claim_id": f"claim.plan.{side}", "value": leg,
                                          "source_fact_ids": [f"plan.{side}"], "consumer": "writer+renderer+public"}
    facts["risk.policy_id"] = geometry["policy_id"]
    facts["risk.volatility"] = geometry["volatility"]
    output = {"schema": SCHEMA, "contract_version": CONTRACT_VERSION,
              "asset": story["asset"], "timeframe": story["timeframe"],
              "cutoff": story["cutoff"], "source_sha256": story["source_sha256"],
              "rows_count": len(rows), "facts": facts, "claims": claims}
    output["facts_sha256"] = _hash(output)
    return output


def validate(facts: dict, *, story: dict | None = None) -> None:
    if facts.get("schema") != SCHEMA or facts.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("facts schema/version ไม่ตรง v7")
    if facts.get("facts_sha256") != _hash(facts):
        raise ValueError("facts hash mismatch")
    geometry = (facts.get("facts") or {}).get("risk_geometry") or {}
    if geometry.get("policy_id") != style_m_v7_risk.POLICY_ID:
        raise ValueError("risk policy ไม่ตรง ADR14 frozen policy")
    vol = geometry.get("volatility") or {}
    if vol.get("metric") != "ADR14" or vol.get("length") != 14:
        raise ValueError("v7 ต้องใช้ ADR14/14")
    for plan in (facts.get("facts") or {}).values():
        if isinstance(plan, dict) and "state" in plan and plan["state"] == "NO_PLAN":
            continue
    if story is not None and build(story, [{}] * int(facts.get("rows_count", 0))) != facts:
        raise ValueError("facts ไม่ตรง story")


def parity_report(facts: dict, *, markdown: str) -> dict:
    validate(facts)
    findings = []
    for side, leg in ((key.rsplit(".", 1)[-1], value)
                      for key, value in facts["facts"].items() if key.startswith("plan.")):
        if leg.get("state") == "NO_PLAN":
            if any(leg.get(field) is not None for field in ("entry_low", "entry_high", "sl", "tp1", "tp2")):
                findings.append({"code": "NO_PLAN_GEOMETRY_PRESENT", "side": side})
            continue
        for field in ("trigger", "entry_low", "entry_high", "sl", "tp1", "tp2"):
            value = leg.get(field)
            rendered = f"{Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP):,.0f}"
            if str(value) not in markdown and rendered not in markdown:
                findings.append({"code": "CLAIM_VALUE_MISSING", "side": side, "field": field})
    return {"schema": PARITY_SCHEMA, "contract_version": CONTRACT_VERSION,
            "status": "PASS" if not findings else "FAIL",
            "facts_sha256": facts["facts_sha256"], "findings": findings}


__all__ = ["SCHEMA", "PARITY_SCHEMA", "CONTRACT_VERSION", "build", "validate", "parity_report"]
