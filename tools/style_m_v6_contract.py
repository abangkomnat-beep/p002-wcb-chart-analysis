"""Typed facts and lightweight claim parity for Style M v6."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP

from tools import public_number_policy, style_m_v6_story


SCHEMA = "style-m-article-visual-facts/v3"
PARITY_SCHEMA = "style-m-claim-parity-report/v3"
CONTRACT_VERSION = "M-PROD/v6"


def _hash(value: dict) -> str:
    payload = dict(value)
    payload.pop("facts_sha256", None)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def build(story: dict, rows: list[dict]) -> dict:
    style_m_v6_story.validate(story)
    facts = {
        "market.latest.close": story["latest"]["close"],
        "market.atr14": story["indicators"]["atr14"],
        "market.adx14": story["indicators"]["adx14"],
        "market.previous_adx14": story["indicators"]["previous_adx14"],
        "analysis.adx_regime": story["indicators"]["adx_regime"],
        "analysis.structure_pattern": story["structure"]["pattern"],
        "zone.donchian.upper": story["donchian"]["upper"],
        "zone.donchian.lower": story["donchian"]["lower"],
        "zone.donchian.width": story["donchian"]["width"],
        "zone.liquidity.buy_side_reference": story["zones"]["buy_side_liquidity_reference"],
        "zone.liquidity.sell_side_reference": story["zones"]["sell_side_liquidity_reference"],
        "zone.trap.low": story["zones"]["trap_zone_low"],
        "zone.trap.high": story["zones"]["trap_zone_high"],
        "analysis.squeeze_status": story["squeeze"]["status"],
        "analysis.market_position": story["market_position"],
    }
    claims = {}
    for fact_id, value in facts.items():
        claims[f"claim.{fact_id}"] = {"claim_id": f"claim.{fact_id}", "value": value,
                                       "source_fact_ids": [fact_id], "consumer": "writer+renderer"}
    for side, plan in story["scenarios"].items():
        for key in ("trigger", "entry_low", "entry_high", "sl", "tp1", "tp2", "rr1", "rr2"):
            fact_id = f"plan.{side}.{key}"
            facts[fact_id] = plan[key]
            claims[f"claim.{fact_id}"] = {
                "claim_id": f"claim.{fact_id}", "value": plan[key],
                "source_fact_ids": [fact_id],
                "consumer": "sidecar" if key in {"rr1", "rr2"} else "writer+renderer",
            }
    output = {"schema": SCHEMA, "contract_version": CONTRACT_VERSION,
              "asset": story["asset"], "timeframe": story["timeframe"],
              "cutoff": story["cutoff"], "source_sha256": story["source_sha256"],
              "rows_count": len(rows), "facts": facts, "claims": claims}
    output["facts_sha256"] = _hash(output)
    return output


def validate(facts: dict, *, story: dict | None = None) -> None:
    if facts.get("schema") != SCHEMA or facts.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("facts schema/version ไม่ตรง v6")
    if facts.get("facts_sha256") != _hash(facts):
        raise ValueError("facts hash mismatch")
    if "EMA" in json.dumps(facts, ensure_ascii=False):
        raise ValueError("ห้ามมี EMA ใน v6 facts")
    if story is not None:
        expected = build(story, [{}] * int(facts.get("rows_count", 0)))
        if expected != facts:
            raise ValueError("facts ไม่ตรง story")


def parity_report(facts: dict, *, markdown: str) -> dict:
    validate(facts)
    findings = []
    text_markers = {
        "claim.analysis.adx_regime": {
            "QUIET_RANGE": "ความแรงของแนวโน้มยังต่ำ",
            "TRANSITION": "ช่วงเปลี่ยนผ่านของแรงแนวโน้ม",
            "TRENDING": "ความแรงของแนวโน้มอยู่ในระดับสูง",
        },
        "claim.analysis.structure_pattern": {
            "MIXED": "โครงสร้างยังผสม",
            "INSUFFICIENT": "จุดกลับตัวยังมีไม่พอ",
            "BULLISH_HH_HL": "ยอดและฐานยกสูงขึ้น",
            "BEARISH_LH_LL": "ยอดและฐานลดต่ำลง",
        },
        "claim.analysis.squeeze_status": {
            "CONFIRMED": "Volatility Squeeze",
        },
        "claim.analysis.market_position": {
            "CENTER": "กึ่งกลางระหว่างขอบบนและขอบล่าง",
            "NEAR_UPPER": "เข้าใกล้ขอบบนของกรอบ Donchian",
            "NEAR_LOWER": "เข้าใกล้ขอบล่างของกรอบ Donchian",
        },
    }
    for claim_id, claim in facts["claims"].items():
        if claim.get("consumer") == "sidecar":
            continue
        value = claim["value"]
        if isinstance(value, (int, float)):
            if claim_id.endswith(".rr1"):
                rendered = f"TP1 {public_number_policy.ratio(f'{float(value):.2f}')}"
            elif claim_id.endswith(".rr2"):
                rendered = f"TP2 {public_number_policy.ratio(f'{float(value):.2f}')}"
            else:
                rounded = Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                rendered = f"{rounded:,.0f}"
            if rendered not in markdown:
                findings.append({"code": "CLAIM_VALUE_MISSING", "claim_id": claim_id})
        elif claim_id in text_markers:
            marker = text_markers[claim_id].get(value)
            if marker and marker not in markdown:
                findings.append({"code": "CLAIM_TEXT_MISSING", "claim_id": claim_id})
    if "EMA" in markdown:
        findings.append({"code": "REMOVED_INDICATOR_PRESENT", "claim_id": None})
    return {"schema": PARITY_SCHEMA, "status": "PASS" if not findings else "FAIL",
            "facts_sha256": facts["facts_sha256"], "findings": findings,
            "checked_claim_ids": sorted(facts["claims"])}


__all__ = ["SCHEMA", "PARITY_SCHEMA", "CONTRACT_VERSION", "build", "validate", "parity_report"]
