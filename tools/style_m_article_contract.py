"""Canonical facts, semantic claims, migration and parity for Style M v5."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from tools import style_m_semantics, style_m_story


SCHEMA = "style-m-article-visual-facts/v2"
LEGACY_SCHEMA = "style-m-article-visual-facts/v1"
CONTRACT_VERSION = "M-PROD/v5"
PARITY_SCHEMA = "style-m-claim-parity-report/v2"
MIGRATION_VERSION = "style-m-v1-prior-adapter/v1"
H2 = ("BTCUSD H1 บอกอะไรจากโครงสร้างล่าสุด", "แนวรับ แนวต้าน และแผน BTCUSD วันนี้")
PRIMARY_ROUTE = "/thailand/asset-btc"
SECONDARY_ROUTE = "/thailand/analysis"
OCCUPANCY_BINS = 72
DUPLICATE_NO_PLAN_ATR_TOLERANCE = 0.10
PERMISSIONS = {"FORBIDDEN", "CONTEXT_ONLY", "DIAGNOSTIC_ONLY", "CONDITIONAL", "ALLOWED"}
ROLES = {"MARKET_CONTEXT", "STRUCTURE_CONTEXT", "SEMANTIC_RELATION", "DECISION_STATUS",
         "REASSESSMENT", "PLAN_SIDE", "PLAN_TRIGGER", "PLAN_LEVEL", "PLAN_RISK",
         "TRENDLINE_CONTEXT", "BREAKOUT_CONTEXT", "OCCUPANCY_DISCLOSURE",
         "NEWS_RISK_CONTEXT"}
VALUE_TYPES = {"NUMBER", "ENUM", "TEXT", "RANGE", "STATUS", "ANCHOR_LINE"}
UNITS = {"USD", "RR", "ATR", "HOURS", "NONE"}


class ArticleContractError(RuntimeError):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _json_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _fact(value: Any, *, unit: str | None = None, at: str | None = None,
          permission: str | None = None, derived_from: list[str] | None = None,
          rule: str | None = None) -> dict[str, Any]:
    output: dict[str, Any] = {"value": value}
    if unit:
        output["unit"] = unit
    if at:
        output["at"] = at
    if permission:
        output["permission"] = permission
    if derived_from is not None:
        output["derived_from"] = list(derived_from)
    if rule:
        output["rule"] = rule
    return output


def _build_base_facts(story: dict, rows: list[dict]) -> dict[str, Any]:
    """Build the source fact registry without making semantic decisions."""
    style_m_story.validate(story)
    latest = story["latest"]
    indicators = story["indicators"]
    facts: dict[str, Any] = {
        "market.latest.close": _fact(latest["close"], unit="USD", at=latest["at"]),
        "market.ema20": _fact(indicators["ema20"], unit="USD"),
        "market.ema50": _fact(indicators["ema50"], unit="USD"),
        "market.atr14": _fact(indicators["atr14"], unit="USD"),
        "market.ema_relation": _fact(
            "ema20_above_ema50" if indicators["ema20"] > indicators["ema50"] else
            "ema20_below_ema50" if indicators["ema20"] < indicators["ema50"] else
            "ema20_equal_ema50"),
        "occupancy.price_bins": {"count": OCCUPANCY_BINS,
                                  "source_volume_available": False,
                                  "meaning": "closed_h1_price_occupancy"},
        "plan.state": _fact(story["state"]),
        "decision.reason_code": _fact(story.get("reason_code")),
    }
    indexed_rows = []
    for ordinal, raw in enumerate(rows or []):
        row = dict(raw)
        row.setdefault("index", ordinal)
        indexed_rows.append(row)
    for row in indexed_rows[-style_m_semantics.VISIBLE_H1_BARS:]:
        facts[f"market.candle.close.{row['index']}"] = _fact(
            row["close"], unit="USD", at=row.get("at"))
    visible_start = (int(indexed_rows[-style_m_semantics.VISIBLE_H1_BARS:][0]["index"])
                     if indexed_rows else -10**12)
    for kind in ("high", "low"):
        for pivot in story.get("pivots", {}).get(f"{kind}s", []):
            if int(pivot["index"]) < visible_start:
                continue
            facts[f"structure.pivot.{kind}.{pivot['index']}"] = _fact(
                pivot["price"], unit="USD", at=pivot["at"])
    highs = story.get("pivots", {}).get("highs", [])
    lows = story.get("pivots", {}).get("lows", [])
    if highs:
        facts["zone.resistance.primary"] = {
            "low": highs[-1]["price"], "high": highs[-1]["price"],
            "unit": "USD", "source": "confirmed_pivot",
            "source_fact_ids": [f"structure.pivot.high.{highs[-1]['index']}"]}
    if lows:
        facts["zone.support.primary"] = {
            "low": lows[-1]["price"], "high": lows[-1]["price"],
            "unit": "USD", "source": "confirmed_pivot",
            "source_fact_ids": [f"structure.pivot.low.{lows[-1]['index']}"]}
    state, plan = story["state"], story.get("plan")
    if state in ("WAIT_H1_CONFIRM", "PLAN_VALID") and plan:
        permission = "CONDITIONAL" if state == "WAIT_H1_CONFIRM" else "ALLOWED"
        facts["plan.side"] = _fact(story.get("side"), permission=permission)
        for key in ("entry_low", "entry_high", "sl", "tp1", "tp2", "rr1", "rr2"):
            unit = "RR" if key.startswith("rr") else "USD"
            facts[f"plan.{key}"] = _fact(plan[key], unit=unit, permission=permission)
        facts["plan.trigger"] = _fact("conditional_h1_close", permission=permission)
        facts["plan.invalidation"] = _fact("pre_trigger_h1_close_beyond_sl", permission=permission)
        facts["plan.post_entry_stop"] = _fact("stop_loss_after_fill", permission=permission)
        facts["plan.sl_tp_rr"] = _fact("available", permission=permission)
        for key in ("entry_zone_atr", "stop_buffer_atr", "worst_entry_risk_atr"):
            facts[f"plan.{key}"] = _fact(plan[key], unit="ATR", permission=permission)
        for key in ("min_rr1", "min_rr2"):
            facts[f"plan.{key}"] = _fact(plan[key], unit="RR", permission=permission)
        facts["plan.execution_costs"] = _fact(
            "recalculate_fees_spread_slippage_before_entry", permission=permission)
    else:
        for fact_id in ("plan.side", "plan.trigger", "plan.entry", "plan.sl_tp_rr",
                        "plan.post_entry_stop", "plan.execution_costs"):
            facts[fact_id] = _fact(None, permission="FORBIDDEN")
        facts["plan.invalidation"] = _fact(None, permission="FORBIDDEN")
    return facts


def _derived_fact(value: Any, source_ids: list[str]) -> dict:
    return _fact(value, derived_from=source_ids, rule=style_m_semantics.RULE_VERSION)


def _claim(claim_id: str, *, role: str, value_type: str, value: Any,
           source_fact_ids: list[str], permission: str, consumers: list[str],
           cutoff: str, label: str, unit: str = "NONE", at: str | None = None,
           required: bool = True) -> dict:
    return {"claim_id": claim_id, "role": role, "value_type": value_type,
            "value": value, "unit": unit, "timeframe": "H1", "at": at,
            "cutoff": cutoff, "source_fact_ids": list(source_fact_ids),
            "permission": permission, "consumers": list(consumers),
            "required": required, "label": label}


def _claims(story: dict, facts: dict, semantic: dict,
            events: list[dict]) -> dict[str, dict]:
    cutoff = story["cutoff"]
    claims: dict[str, dict] = {}

    def add(name: str, **kwargs):
        claims[name] = _claim(name, cutoff=cutoff, **kwargs)

    add("claim.plan.state", role="DECISION_STATUS", value_type="STATUS",
        value=story["state"], source_fact_ids=["plan.state"], permission="ALLOWED",
        consumers=["writer", "renderer"], label="สถานะ")
    for key, label in (("latest_close", "ราคาปิดล่าสุด"), ("ema20", "EMA20"),
                       ("ema50", "EMA50"), ("atr14", "ATR14")):
        fact_id = "market.latest.close" if key == "latest_close" else f"market.{key}"
        add(f"claim.market.{key}", role="MARKET_CONTEXT",
            value_type="NUMBER", value=facts[fact_id]["value"],
            unit="USD", at=facts[fact_id].get("at"), source_fact_ids=[fact_id],
            permission="CONTEXT_ONLY", consumers=["writer", "renderer"], label=label)
    relation_specs = (
        ("ema_stack", "ภาพเส้นเฉลี่ย"), ("close_position", "ตำแหน่งราคาปิด"),
        ("high_relation", "ความสัมพันธ์จุดสูง"), ("low_relation", "ความสัมพันธ์จุดต่ำ"),
        ("structure_pattern", "รูปแบบโครงสร้าง"),
    )
    for key, label in relation_specs:
        item = semantic["relations"][key]
        add(f"claim.analysis.{key}", role="SEMANTIC_RELATION", value_type="ENUM",
            value=item["value"], source_fact_ids=item["derived_from"],
            permission="CONTEXT_ONLY", consumers=["writer"], label=label)
    add("claim.analysis.decision_implication", role="DECISION_STATUS", value_type="ENUM",
        value=semantic["decision"]["implication"],
        source_fact_ids=["plan.state", "decision.reason_code"],
        permission="ALLOWED", consumers=["writer"], label="คำตัดสิน")
    add("claim.analysis.reassessment", role="REASSESSMENT", value_type="TEXT",
        value=semantic["decision"]["reassessment_observation_codes"],
        source_fact_ids=["analysis.decision_implication"], permission="ALLOWED",
        consumers=["writer"], label="เงื่อนไขประเมินใหม่")
    conflict = story.get("reason_code") == "STRUCTURE_CONFLICT"
    for kind, label in (("high", "จุดสูง"), ("low", "จุดต่ำ")):
        pivots = story.get("pivots", {}).get(f"{kind}s", [])[-2:]
        for ordinal, pivot in enumerate(pivots):
            fact_id = f"structure.pivot.{kind}.{pivot['index']}"
            if fact_id not in facts:
                continue
            consumers = ["writer", "renderer"] if conflict else ["renderer"]
            add(f"claim.{fact_id}", role="STRUCTURE_CONTEXT", value_type="NUMBER",
                value=facts[fact_id]["value"], unit="USD", at=facts[fact_id].get("at"),
                source_fact_ids=[fact_id], permission="CONTEXT_ONLY", consumers=consumers,
                label=f"{label}{'ก่อนหน้า' if ordinal == 0 else 'ล่าสุด'}")
    for family, label in (("support", "แนวรับ"), ("resistance", "แนวต้าน")):
        fact_id = f"zone.{family}.primary"
        if fact_id in facts:
            add(f"claim.zone.{family}.primary", role="STRUCTURE_CONTEXT", value_type="RANGE",
                value={"low": facts[fact_id]["low"], "high": facts[fact_id]["high"]},
                unit="USD", source_fact_ids=facts[fact_id]["source_fact_ids"],
                permission="CONTEXT_ONLY", consumers=["writer", "renderer"], label=label)
    add("claim.occupancy.disclosure", role="OCCUPANCY_DISCLOSURE", value_type="TEXT",
        value="closed_h1_price_occupancy_not_volume", source_fact_ids=["occupancy.price_bins"],
        permission="CONTEXT_ONLY", consumers=["writer", "renderer"], label="แถบการกระจุกตัว")
    trend = semantic["trendline"]
    if trend["status"] == "SHOWN":
        add("claim.analysis.trendline", role="TRENDLINE_CONTEXT", value_type="ANCHOR_LINE",
            value={"anchor_fact_ids": trend["anchor_fact_ids"],
                   "slope_per_bar": trend["slope_per_bar"], "intercept": trend["intercept"]},
            source_fact_ids=trend["anchor_fact_ids"], permission="CONTEXT_ONLY",
            consumers=["writer", "renderer"], label="เส้นแนวโน้ม")
    breakout = semantic["breakout"]
    if breakout["status"] == "CONFIRMED_UP_BREAK":
        add("claim.analysis.breakout", role="BREAKOUT_CONTEXT", value_type="STATUS",
            value=breakout["status"],
            source_fact_ids=trend["anchor_fact_ids"] + [breakout["evaluated_candle_fact_id"]],
            permission="CONTEXT_ONLY", consumers=["writer", "renderer"], label="การผ่านเส้นแนวโน้ม")
    if story["state"] in ("WAIT_H1_CONFIRM", "PLAN_VALID") and story.get("plan"):
        permission = "CONDITIONAL" if story["state"] == "WAIT_H1_CONFIRM" else "ALLOWED"
        add("claim.plan.side", role="PLAN_SIDE", value_type="ENUM", value=story["side"],
            source_fact_ids=["plan.side"], permission=permission,
            consumers=["writer", "renderer"], label="ฝั่งแผน")
        for key, label in (("entry_low", "ขอบล่าง Entry"), ("entry_high", "ขอบบน Entry"),
                           ("sl", "Stop Loss"), ("tp1", "TP1"), ("tp2", "TP2"),
                           ("rr1", "RR1"), ("rr2", "RR2")):
            fact_id = f"plan.{key}"
            consumers = ["writer"] if key.startswith("rr") else ["writer", "renderer"]
            add(f"claim.{fact_id}", role="PLAN_RISK" if key.startswith("rr") else "PLAN_LEVEL",
                value_type="NUMBER", value=facts[fact_id]["value"], unit=facts[fact_id]["unit"],
                source_fact_ids=[fact_id], permission=permission,
                consumers=consumers, label=label)
        add("claim.plan.trigger", role="PLAN_TRIGGER", value_type="TEXT",
            value=facts["plan.trigger"]["value"], source_fact_ids=[
                "plan.trigger", "plan.entry_high" if story.get("side") == "BUY"
                else "plan.entry_low"],
            permission=permission, consumers=["writer"], label="Trigger")
        add("claim.plan.invalidation", role="PLAN_TRIGGER", value_type="TEXT",
            value=facts["plan.invalidation"]["value"], source_fact_ids=["plan.invalidation"],
            permission=permission, consumers=["writer"], label="ยกเลิกแผนก่อนเข้า")
        add("claim.plan.post_entry_stop", role="PLAN_RISK", value_type="TEXT",
            value=facts["plan.post_entry_stop"]["value"],
            source_fact_ids=["plan.post_entry_stop", "plan.sl"], permission=permission,
            consumers=["writer"], label="Stop Loss หลังจับคู่")
        for key, label in (("stop_buffer_atr", "ระยะ Stop Loss"),
                           ("worst_entry_risk_atr", "ความเสี่ยงขอบ Entry"),
                           ("min_rr1", "RR ขั้นต่ำ TP1"),
                           ("min_rr2", "RR ขั้นต่ำ TP2")):
            fact_id = f"plan.{key}"
            add(f"claim.{fact_id}", role="PLAN_RISK", value_type="NUMBER",
                value=facts[fact_id]["value"], unit=facts[fact_id]["unit"],
                source_fact_ids=[fact_id], permission=permission, consumers=["writer"],
                label=label)
        add("claim.plan.execution_costs", role="PLAN_RISK", value_type="TEXT",
            value=facts["plan.execution_costs"]["value"],
            source_fact_ids=["plan.execution_costs"], permission=permission,
            consumers=["writer"], label="ต้นทุนการจับคู่")
    if events:
        event = events[0]
        add("claim.news.risk_context", role="NEWS_RISK_CONTEXT", value_type="TEXT",
            value={"event_id": event.get("event_id"), "title": event.get("title"),
                   "time_thai": event.get("time_thai"), "url": event.get("url")},
            source_fact_ids=["news.risk_context"], permission="CONTEXT_ONLY",
            consumers=["writer"], label="ความเสี่ยงตามเวลา")
    return claims


def build(story: dict, rows: list[dict], *, events: list[dict] | None = None,
          news_report: dict | None = None,
          prior_fingerprint: dict | None = None) -> dict[str, Any]:
    base = _build_base_facts(story, rows)
    semantic = style_m_semantics.build(story, base, rows)
    facts = dict(base)
    for key, item in semantic["relations"].items():
        facts[f"analysis.{key}"] = _derived_fact(item["value"], item["derived_from"])
    facts["analysis.decision_alignment"] = _derived_fact(
        semantic["decision"]["alignment"], ["plan.state", "decision.reason_code"])
    facts["analysis.decision_implication"] = _derived_fact(
        semantic["decision"]["implication"], ["plan.state", "decision.reason_code"])
    facts["analysis.reassessment_observations"] = _derived_fact(
        semantic["decision"]["reassessment_observation_codes"], ["analysis.decision_implication"])
    facts["analysis.trendline"] = {**semantic["trendline"],
                                   "derived_from": semantic["trendline"].get("anchor_fact_ids", []),
                                   "rule": style_m_semantics.RULE_VERSION}
    breakout_sources = list(semantic["breakout"].get("trendline_anchor_fact_ids", []))
    if semantic["breakout"].get("evaluated_candle_fact_id"):
        breakout_sources.append(semantic["breakout"]["evaluated_candle_fact_id"])
    facts["analysis.breakout"] = {**semantic["breakout"], "derived_from": breakout_sources,
                                  "rule": style_m_semantics.RULE_VERSION}
    events = list(events or [])[:1]
    if events:
        event = events[0]
        facts["news.risk_context"] = _fact(
            {"event_id": event.get("event_id"), "title": event.get("title"),
             "time_thai": event.get("time_thai"), "url": event.get("url")})
    claims = _claims(story, facts, semantic, events)
    fingerprint_basis = {
        "state": story["state"], "reason_bucket": story.get("reason_code"),
        "ema_relation": facts["market.ema_relation"]["value"],
        "atr14": story["indicators"]["atr14"], "support": facts.get("zone.support.primary"),
        "resistance": facts.get("zone.resistance.primary"),
        "plan": {key: item["value"] for key, item in facts.items()
                 if key.startswith("plan.") and isinstance(item, dict) and item.get("value") is not None},
    }
    output = {
        "schema": SCHEMA, "contract_version": CONTRACT_VERSION,
        "asset": story["asset"], "timeframe": story["timeframe"], "cutoff": story["cutoff"],
        "source": {"sha256": story["source_sha256"], "closed_h1": True},
        "facts": facts, "semantic_decision": semantic, "claims": claims,
        "news": {"public_advisory": bool(events),
                 "selected_event_id": events[0].get("event_id") if events else None,
                 "provider_status": (news_report or {}).get("provider_status", "ok")},
        "web_routes": {"primary": PRIMARY_ROUTE, "secondary": SECONDARY_ROUTE},
        "fingerprint_basis": fingerprint_basis,
        "semantic_fingerprint": _json_hash(fingerprint_basis),
        "prior_fingerprint": prior_fingerprint,
        "migration": (migrate_prior_v1(prior_fingerprint)
                      if isinstance(prior_fingerprint, dict) and
                      prior_fingerprint.get("schema") == LEGACY_SCHEMA else None),
    }
    output["facts_sha256"] = _facts_hash(output)
    validate(output, story=story, rows=rows)
    return output


def _facts_hash(facts: dict) -> str:
    payload = dict(facts)
    payload.pop("facts_sha256", None)
    payload.pop("prior_fingerprint", None)
    return _json_hash(payload)


def validate(facts: dict, *, story: dict | None = None,
             rows: list[dict] | None = None) -> None:
    if facts.get("schema") != SCHEMA or facts.get("contract_version") != CONTRACT_VERSION:
        raise ArticleContractError("SCHEMA_UNSUPPORTED", str(facts.get("schema")))
    if facts.get("facts_sha256") != _facts_hash(facts):
        raise ArticleContractError("STALE_FACTS_HASH", "facts hash mismatch")
    registry = facts.get("facts", {})
    semantic = facts.get("semantic_decision", {})
    state = ((story or {}).get("state") or semantic.get("oracle", {}).get("state"))
    plan_permission = ("CONDITIONAL" if state == "WAIT_H1_CONFIRM" else
                       "ALLOWED" if state == "PLAN_VALID" else "FORBIDDEN")
    semantic_payload = dict(semantic)
    semantic_hash = semantic_payload.pop("semantic_sha256", None)
    if semantic_hash != _json_hash(semantic_payload):
        raise ArticleContractError("SEMANTIC_HASH_MISMATCH", "semantic hash mismatch")
    for key, claim in facts.get("claims", {}).items():
        if claim.get("claim_id") != key:
            raise ArticleContractError("CLAIM_ID_UNKNOWN", key)
        sources = claim.get("source_fact_ids", [])
        if len(sources) != len(set(sources)):
            raise ArticleContractError("CLAIM_SOURCE_DUPLICATE", key)
        missing = [item for item in sources if item not in registry]
        if missing:
            raise ArticleContractError("CLAIM_SOURCE_UNKNOWN", f"{key}: {missing}")
        if claim.get("role") not in ROLES:
            raise ArticleContractError("CLAIM_ROLE_INVALID", key)
        if claim.get("value_type") not in VALUE_TYPES:
            raise ArticleContractError("CLAIM_VALUE_TYPE_INVALID", key)
        if claim.get("unit") not in UNITS:
            raise ArticleContractError("CLAIM_UNIT_INVALID", key)
        if claim.get("permission") not in PERMISSIONS:
            raise ArticleContractError("CLAIM_PERMISSION_INVALID", key)
        expected_permission = (
            "ALLOWED" if key in {"claim.plan.state", "claim.analysis.decision_implication",
                                  "claim.analysis.reassessment"} else
            plan_permission if key.startswith("claim.plan.") else "CONTEXT_ONLY")
        if claim.get("permission") != expected_permission:
            raise ArticleContractError("CLAIM_PERMISSION_DERIVATION_MISMATCH", key)
        consumers = claim.get("consumers")
        if (not isinstance(consumers, list) or len(consumers) != len(set(consumers)) or
                any(item not in ("writer", "renderer") for item in consumers) or
                consumers != [item for item in ("writer", "renderer") if item in consumers]):
            raise ArticleContractError("CLAIM_CONSUMER_INVALID", key)
        if claim["permission"] == "FORBIDDEN" and consumers:
            raise ArticleContractError("CLAIM_PERMISSION_INVALID", key)
        for required in ("timeframe", "cutoff", "required", "label"):
            if required not in claim:
                raise ArticleContractError("CLAIM_SCHEMA_INCOMPLETE", f"{key}: {required}")
    for fact_id, item in registry.items():
        if isinstance(item, dict) and "permission" in item and item["permission"] not in PERMISSIONS:
            raise ArticleContractError("FACT_PERMISSION_INVALID", fact_id)
        if isinstance(item, dict) and "permission" in item:
            expected_permission = (plan_permission if fact_id.startswith("plan.") else
                                   semantic.get("trendline", {}).get("permission")
                                   if fact_id == "analysis.trendline" else
                                   semantic.get("breakout", {}).get("permission")
                                   if fact_id == "analysis.breakout" else "CONTEXT_ONLY")
            if item["permission"] != expected_permission:
                raise ArticleContractError("FACT_PERMISSION_DERIVATION_MISMATCH", fact_id)
    active = state in {"WAIT_H1_CONFIRM", "PLAN_VALID"}
    expected_semantic_permissions = {
        "market_structure": "CONTEXT_ONLY",
        "active_side": plan_permission if active else "FORBIDDEN",
        "prior_side": "DIAGNOSTIC_ONLY" if state == "INVALIDATED" else "FORBIDDEN",
        "trade_geometry": plan_permission if active else "FORBIDDEN",
        "trigger_status": plan_permission if active else "FORBIDDEN",
        "reassessment": "ALLOWED",
        "news": "CONTEXT_ONLY",
        "trendline": semantic.get("trendline", {}).get("permission"),
        "breakout": semantic.get("breakout", {}).get("permission"),
    }
    if semantic.get("decision", {}).get("permissions") != expected_semantic_permissions:
        raise ArticleContractError("SEMANTIC_PERMISSION_DERIVATION_MISMATCH", state or "UNKNOWN")
    if story:
        oracle = facts.get("semantic_decision", {}).get("oracle", {})
        if (oracle.get("state"), oracle.get("side"), oracle.get("reason_code")) != (
                story.get("state"), story.get("side"), story.get("reason_code")):
            raise ArticleContractError("ORACLE_BINDING_MISMATCH", "story changed")
        state = story["state"]
        if state in ("NO_PLAN", "INVALIDATED"):
            ghost = [key for key, item in registry.items()
                     if key.startswith("plan.") and key not in ("plan.state", "plan.invalidation")
                     and isinstance(item, dict) and item.get("value") is not None]
            ghost_claims = [key for key in facts.get("claims", {})
                            if key.startswith("claim.plan.") and key != "claim.plan.state"]
            if ghost or ghost_claims:
                raise ArticleContractError("STATE_PERMISSION_VIOLATION", str(ghost + ghost_claims))
        if rows is not None:
            try:
                style_m_semantics.validate(semantic, story=story,
                                           base_facts=registry, rows=rows)
            except style_m_semantics.SemanticContractError as exc:
                raise ArticleContractError("SEMANTIC_DERIVATION_MISMATCH", exc.code) from exc


def migrate_prior_v1(payload: dict) -> dict:
    raw_hash = _json_hash(payload)
    valid = (payload.get("schema") == LEGACY_SCHEMA and
             isinstance(payload.get("semantic_fingerprint"), str) and
             isinstance(payload.get("fingerprint_basis"), dict))
    return {"schema": "style-m-prior-fingerprint-adapter/v1",
            "migration_version": MIGRATION_VERSION, "migrated_from": payload.get("schema"),
            "source_sha256": raw_hash, "source_semantic_fingerprint": payload.get("semantic_fingerprint"),
            "legacy_basis": payload.get("fingerprint_basis", {}) if valid else {},
            "comparable_to_v2": False,
            "cache_miss_reason": "V1_MISSING_V5_SEMANTICS" if valid else "PRIOR_V1_INVALID"}


def index_recommendation(facts: dict, prior_fingerprint: dict | str | None = None) -> dict[str, Any]:
    current = facts.get("semantic_fingerprint")
    prior = prior_fingerprint
    if isinstance(prior, dict) and prior.get("schema") == LEGACY_SCHEMA:
        migrate_prior_v1(prior)
        return {"schema": "style-m-index-policy/v1", "recommendation": "NEW_DRAFT",
                "index": True, "reason": "PRIOR_SCHEMA_MIGRATED_NOT_COMPARABLE"}
    previous = prior.get("semantic_fingerprint") if isinstance(prior, dict) else prior
    previous_basis = prior.get("fingerprint_basis") if isinstance(prior, dict) else None
    duplicate = previous == current
    if previous_basis and facts.get("fingerprint_basis"):
        duplicate = _duplicate_basis(facts["fingerprint_basis"], previous_basis)
    if facts.get("facts", {}).get("plan.state", {}).get("value") == "NO_PLAN" and duplicate:
        return {"schema": "style-m-index-policy/v1", "recommendation": "HOLD_DUPLICATE_NO_PLAN",
                "index": False, "reason": "semantic_fingerprint_within_0.10_atr"}
    return {"schema": "style-m-index-policy/v1", "recommendation": "NEW_DRAFT",
            "index": True, "reason": "new_semantic_fingerprint"}


def _duplicate_basis(current: dict, previous: dict) -> bool:
    for key in ("state", "reason_bucket", "ema_relation"):
        if current.get(key) != previous.get(key):
            return False
    try:
        tolerance = DUPLICATE_NO_PLAN_ATR_TOLERANCE * min(
            float(current["atr14"]), float(previous["atr14"]))
    except (KeyError, TypeError, ValueError):
        return current == previous
    for key in ("support", "resistance"):
        left, right = current.get(key), previous.get(key)
        if (left is None) != (right is None):
            return False
        if left is None:
            continue
        for bound in ("low", "high"):
            if abs(float(left[bound]) - float(right[bound])) > tolerance + 1e-9:
                return False
    return True


def _number_fragments(value: float) -> set[str]:
    return {f"{float(value):,.2f}", f"{float(value):.2f}", str(value)}


def _label_token(claim_id: str, claim: dict) -> str:
    aliases = {
        "claim.plan.state": "BTCUSD H1", "claim.analysis.decision_implication": "เงื่อนไข",
        "claim.analysis.reassessment": "เงื่อนไข",
        "claim.plan.side": "ฝั่ง", "claim.plan.entry_low": "Entry",
        "claim.plan.entry_high": "Entry", "claim.plan.rr1": "RR",
        "claim.plan.rr2": "RR", "claim.plan.trigger": "Trigger",
        "claim.plan.invalidation": "ยกเลิกแผน", "claim.plan.post_entry_stop": "Stop Loss",
        "claim.plan.execution_costs": "slippage", "claim.occupancy.disclosure": "แถบการกระจุกตัว",
        "claim.analysis.trendline": "เส้นแนวโน้ม",
        "claim.analysis.breakout": "การผ่านเส้นแนวโน้ม",
        "claim.news.risk_context": "ความเสี่ยงตามเวลา",
    }
    if claim_id.startswith("claim.analysis.") and claim["role"] == "SEMANTIC_RELATION":
        relation_aliases = {"ema_stack": "EMA20", "close_position": "ราคาปิด",
                            "high_relation": "จุดสูง", "low_relation": "จุดต่ำ",
                            "structure_pattern": "กรอบ"}
        return relation_aliases.get(claim_id.rsplit(".", 1)[-1], claim["label"])
    if claim_id.startswith("claim.structure.pivot.high"):
        return claim["label"]
    if claim_id.startswith("claim.structure.pivot.low"):
        return claim["label"]
    return aliases.get(claim_id, claim["label"])


def _fragment_supports_claim(claim_id: str, claim: dict, fragment: str,
                             registry: dict) -> bool:
    if _label_token(claim_id, claim) not in fragment:
        return False
    value, value_type = claim.get("value"), claim.get("value_type")
    def numbers_for(number) -> str:
        return "|".join(re.escape(item) for item in sorted(
            _number_fragments(number), key=len, reverse=True))

    plan_number_patterns = {
        "claim.plan.entry_low": rf"Entry[^0-9\n]{{0,24}}(?:{numbers_for(value)})\s*[–-]",
        "claim.plan.entry_high": rf"[–-]\s*(?:{numbers_for(value)})(?![0-9.,])",
        "claim.plan.sl": rf"Stop Loss[^0-9\n]{{0,24}}(?:{numbers_for(value)})(?![0-9.,])",
        "claim.plan.tp1": rf"TP1 / TP2[^0-9\n]{{0,24}}(?:{numbers_for(value)})\s*/",
        "claim.plan.tp2": rf"/\s*(?:{numbers_for(value)})(?![0-9.,])",
        "claim.plan.rr1": rf"RR โดยประมาณ[^0-9\n]{{0,24}}(?:{numbers_for(value)})\s*/",
        "claim.plan.rr2": rf"/\s*(?:{numbers_for(value)})(?![0-9.,])",
    } if value_type == "NUMBER" else {}
    if claim_id in plan_number_patterns:
        return bool(re.search(plan_number_patterns[claim_id], fragment))
    if value_type == "NUMBER":
        role_tokens = {
            "claim.market.latest_close": "ราคาปิดล่าสุด",
            "claim.market.ema20": "EMA20",
            "claim.market.ema50": "EMA50",
            "claim.market.atr14": "ATR14",
        }
        role_token = role_tokens.get(claim_id, claim["label"])
        numbers = numbers_for(value)
        # Verify every numeric value in the grammatical slot owned by its
        # canonical role.  Finding a label and value elsewhere in a shared
        # paragraph is not sufficient evidence.
        return bool(re.search(
            rf"{re.escape(role_token)}[^0-9\n]{{0,80}}(?:{numbers})(?![0-9.,])",
            fragment))
    if value_type == "RANGE":
        if value["low"] == value["high"]:
            return any(token in fragment for token in _number_fragments(value["low"]))
        low, high = numbers_for(value["low"]), numbers_for(value["high"])
        return bool(re.search(rf"(?:{low})\s*[–-]\s*(?:{high})(?![0-9.,])", fragment))
    if value_type == "ANCHOR_LINE":
        return bool(value.get("anchor_fact_ids"))
    enum_tokens = {
        "BULLISH": "EMA20", "BEARISH": "EMA20", "FLAT": "EMA20",
        "ABOVE_BOTH": "เหนือ EMA20", "BELOW_BOTH": "ใต้ EMA20",
        "BETWEEN": "ระหว่าง EMA20", "AT_BAND": "ทับแถบ EMA",
        "HIGHER_HIGH": "จุดสูงสูงขึ้น", "LOWER_HIGH": "จุดสูงลดลง",
        "EQUAL_HIGH": "จุดสูงเท่าเดิม", "HIGHER_LOW": "จุดต่ำสูงขึ้น",
        "LOWER_LOW": "จุดต่ำต่ำลง", "EQUAL_LOW": "จุดต่ำเท่าเดิม",
        "EXPANDING_HH_LL": "ขยายออกสองด้าน", "CONTRACTING_LH_HL": "หดตัว",
        "BULLISH_HH_HL": "ยกฐาน", "BEARISH_LH_LL": "ลดฐาน",
        "INSUFFICIENT": "ยังไม่พอ", "AMBIGUOUS_EQUAL": "เสมอกัน",
        "BUY": "ฝั่งซื้อ", "SELL": "ฝั่งขาย",
    }
    if value_type == "ENUM" and value in enum_tokens:
        return enum_tokens[value] in fragment
    if claim_id == "claim.plan.state":
        state_tokens = {
            "NO_PLAN": "ยังไม่มีแผนเข้าเทรด",
            "INVALIDATED": "แผนเดิมถูกยกเลิก",
            "WAIT_H1_CONFIRM": "ยังต้องรอแท่ง H1",
            "PLAN_VALID": "ปิดผ่านเงื่อนไข",
        }
        return state_tokens.get(value, "") in fragment
    if claim_id == "claim.plan.trigger":
        side = registry.get("plan.side", {}).get("value")
        threshold_id = "plan.entry_high" if side == "BUY" else "plan.entry_low"
        threshold = registry.get(threshold_id, {}).get("value")
        if threshold is None:
            return False
        operator = "เหนือ" if side == "BUY" else "ต่ำกว่า"
        return bool(re.search(
            rf"Trigger[^\n]{{0,80}}{operator}[^0-9\n]{{0,12}}(?:{numbers_for(threshold)})(?![0-9.,])",
            fragment))
    return True


def _expected_renderer_geometry(claim_id: str) -> str | None:
    exact = {
        "claim.plan.state": "badge.plan.state",
        "claim.market.ema20": "line.ema20",
        "claim.market.ema50": "line.ema50",
        "claim.market.latest_close": "line.latest_close",
        "claim.market.atr14": "label.atr14",
        "claim.occupancy.disclosure": "histogram.price_occupancy",
        "claim.zone.support.primary": "zone.support.primary",
        "claim.zone.resistance.primary": "zone.resistance.primary",
        "claim.plan.side": "zone.plan.side",
        "claim.plan.entry_low": "zone.plan.entry.low",
        "claim.plan.entry_high": "zone.plan.entry.high",
        "claim.plan.sl": "line.plan.sl",
        "claim.plan.tp1": "line.plan.tp1",
        "claim.plan.tp2": "line.plan.tp2",
        "claim.analysis.trendline": "trendline.primary",
        "claim.analysis.breakout": "annotation.breakout.primary",
    }
    if claim_id.startswith("claim.structure.pivot."):
        return f"zone.{claim_id.removeprefix('claim.')}"
    return exact.get(claim_id)


def _scan_unbound_numeric(markdown: str, claims: dict) -> list[str]:
    allowed = {"1", "14", "20", "50", "72"}
    for claim in claims.values():
        value = claim.get("value")
        stack = list(value.values()) if isinstance(value, dict) else value if isinstance(value, list) else [value]
        for item in stack:
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                allowed.update(_number_fragments(item))
    body = markdown.split("---", 2)[-1]
    unexpected = []
    for line in body.splitlines():
        if not line or line.startswith("#") or line.startswith("![") or "](" in line:
            continue
        unexpected.extend(token for token in re.findall(r"(?<![A-Za-z0-9])\d[\d,]*(?:\.\d+)?", line)
                          if token not in allowed)
    return sorted(set(unexpected))


def parity_report(facts: dict, *, markdown: str, writer_report: dict,
                  render_report: dict) -> dict[str, Any]:
    findings: list[dict] = []

    def finding(code: str, detail: str, *, claim_id=None, binding_id=None):
        findings.append({"code": code, "claim_id": claim_id,
                         "binding_id": binding_id, "detail": detail})

    if facts.get("schema") != SCHEMA:
        finding("SCHEMA_UNSUPPORTED", str(facts.get("schema")))
    actual_hash = _facts_hash(facts) if facts.get("schema") == SCHEMA else None
    if facts.get("facts_sha256") != actual_hash:
        finding("STALE_FACTS_HASH", "canonical facts were mutated")
    expected_hash = facts.get("facts_sha256")
    markdown_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    if writer_report.get("markdown_sha256") != markdown_hash:
        finding("STALE_MARKDOWN_HASH", "writer report does not describe markdown")
    reports = (("writer", writer_report), ("renderer", render_report))
    expected_schemas = {"writer": "style-m-writer-claim-report/v1",
                        "renderer": "style-m-renderer-claim-report/v1"}
    bindings_by_consumer: dict[str, list[dict]] = {}
    claims = facts.get("claims", {})
    for consumer, report in reports:
        if report.get("schema", report.get("claim_report_schema")) != expected_schemas[consumer]:
            finding("SCHEMA_UNSUPPORTED", f"{consumer} report schema")
        if report.get("facts_sha256") != expected_hash:
            finding("STALE_FACTS_HASH", f"{consumer} facts hash")
        bindings = list(report.get("bindings", []))
        bindings_by_consumer[consumer] = bindings
        seen_ids: set[str] = set()
        seen_claim_ids: set[str] = set()
        for binding in bindings:
            binding_id, claim_id = binding.get("binding_id"), binding.get("claim_id")
            if binding_id in seen_ids:
                finding("CLAIM_BINDING_UNEXPECTED", "duplicate binding id",
                        claim_id=claim_id, binding_id=binding_id)
            seen_ids.add(binding_id)
            if claim_id in seen_claim_ids:
                finding("CLAIM_BINDING_DUPLICATE", consumer,
                        claim_id=claim_id, binding_id=binding_id)
            seen_claim_ids.add(claim_id)
            claim = claims.get(claim_id)
            if not claim:
                finding("CLAIM_ID_UNKNOWN", consumer, claim_id=claim_id, binding_id=binding_id)
                continue
            if consumer not in claim["consumers"] or claim["permission"] == "FORBIDDEN":
                finding("CLAIM_PERMISSION_VIOLATION", consumer,
                        claim_id=claim_id, binding_id=binding_id)
            if binding.get("label") != claim.get("label"):
                finding("CLAIM_LABEL_MISMATCH", consumer, claim_id=claim_id, binding_id=binding_id)
            if binding.get("unit") != claim.get("unit"):
                finding("CLAIM_UNIT_MISMATCH", consumer, claim_id=claim_id, binding_id=binding_id)
            if binding.get("timeframe") != claim.get("timeframe"):
                finding("CLAIM_TIMEFRAME_MISMATCH", consumer, claim_id=claim_id, binding_id=binding_id)
            if binding.get("source_fact_ids") != claim.get("source_fact_ids"):
                code = ("CLAIM_SOURCE_DUPLICATE" if len(binding.get("source_fact_ids", [])) !=
                        len(set(binding.get("source_fact_ids", []))) else "CLAIM_SOURCE_UNKNOWN")
                finding(code, consumer, claim_id=claim_id, binding_id=binding_id)
            if binding.get("rendered_value") != claim.get("value"):
                finding("CLAIM_VALUE_MISMATCH", consumer, claim_id=claim_id, binding_id=binding_id)
            if consumer == "writer":
                fragment = binding.get("fragment", "")
                if (not fragment or fragment not in markdown or
                        binding.get("fragment_sha256") != hashlib.sha256(
                            fragment.encode("utf-8")).hexdigest() or
                        not _fragment_supports_claim(claim_id, claim, fragment, facts.get("facts", {}))):
                    finding("CLAIM_FRAGMENT_MISMATCH", consumer,
                            claim_id=claim_id, binding_id=binding_id)
            else:
                expected_geometry = _expected_renderer_geometry(claim_id)
                if (not expected_geometry or binding.get("geometry_id") != expected_geometry or
                        binding_id != f"renderer.{expected_geometry}"):
                    finding("RENDER_TRACE_MISMATCH", "renderer geometry is not canonical",
                            claim_id=claim_id, binding_id=binding_id)
            if claim.get("value_type") == "ANCHOR_LINE":
                if binding.get("anchor_fact_ids") != claim["value"]["anchor_fact_ids"]:
                    finding("CLAIM_ANCHOR_MISMATCH", consumer,
                            claim_id=claim_id, binding_id=binding_id)
    for claim_id, claim in claims.items():
        if not claim.get("required"):
            continue
        for consumer in claim.get("consumers", []):
            if not any(item.get("claim_id") == claim_id
                       for item in bindings_by_consumer.get(consumer, [])):
                finding("CLAIM_BINDING_MISSING", consumer, claim_id=claim_id)
    draw_trace = render_report.get("draw_trace")
    trace_hash = _json_hash(draw_trace) if isinstance(draw_trace, list) else None
    if (not isinstance(draw_trace, list) or
            render_report.get("visual_trace_sha256") != trace_hash):
        finding("RENDER_TRACE_MISMATCH", "draw trace hash is missing or stale")
        draw_trace = []
    renderer_bindings = bindings_by_consumer.get("renderer", [])
    binding_trace = [{"claim_id": item.get("claim_id"),
                      "geometry_id": item.get("geometry_id"),
                      "label_id": item.get("label_id"),
                      "rendered_value": item.get("rendered_value")}
                     for item in renderer_bindings]
    if draw_trace != binding_trace:
        finding("RENDER_TRACE_MISMATCH", "bindings do not match draw operations")
    expected_renderer_claims = sorted(
        claim_id for claim_id, claim in claims.items()
        if claim.get("required") and "renderer" in claim.get("consumers", []))
    traced_claims = [item.get("claim_id") for item in draw_trace]
    if sorted(traced_claims) != expected_renderer_claims or len(traced_claims) != len(set(traced_claims)):
        finding("RENDER_TRACE_MISMATCH", "draw operations are incomplete or duplicated")
    unbound = _scan_unbound_numeric(markdown, claims)
    if sorted(set(writer_report.get("unbound_numeric_tokens", []))) != unbound:
        finding("UNBOUND_NUMERIC_TOKEN", "writer numeric scan does not match output")
    for token in unbound:
        finding("UNBOUND_NUMERIC_TOKEN", str(token))
    canonical_trend = facts.get("semantic_decision", {}).get("trendline", {})
    actual_trend = render_report.get("trendline_geometry")
    if canonical_trend.get("status") == "SHOWN":
        if actual_trend != canonical_trend:
            finding("TRENDLINE_PROVENANCE_INCOMPLETE", "renderer trendline trace mismatch",
                    claim_id="claim.analysis.trendline")
    elif actual_trend is not None:
        finding("TRENDLINE_PROVENANCE_INCOMPLETE", "renderer drew forbidden trendline",
                claim_id="claim.analysis.trendline")
    canonical_breakout = facts.get("semantic_decision", {}).get("breakout", {})
    actual_breakout = render_report.get("breakout_annotation")
    if canonical_breakout.get("status") == "CONFIRMED_UP_BREAK":
        if actual_breakout != canonical_breakout:
            finding("BREAKOUT_STATUS_MISMATCH", "renderer breakout trace mismatch",
                    claim_id="claim.analysis.breakout")
    elif actual_breakout is not None:
        finding("BREAKOUT_STATUS_MISMATCH", "renderer drew unconfirmed breakout",
                claim_id="claim.analysis.breakout")
    status = "PASS" if not findings else (
        "STALE" if all(item["code"].startswith("STALE_") for item in findings) else "BLOCK")
    return {"schema": PARITY_SCHEMA, "status": status, "facts_sha256": expected_hash,
            "writer_report_sha256": _json_hash(writer_report),
            "renderer_report_sha256": _json_hash(render_report),
            "checked_claim_ids": sorted(claims), "findings": findings,
            "unbound_numeric_tokens": unbound,
            "missing_bindings": [item for item in findings if item["code"] == "CLAIM_BINDING_MISSING"],
            "unexpected_bindings": [item for item in findings if item["code"] == "CLAIM_BINDING_UNEXPECTED"]}


__all__ = ["ArticleContractError", "CONTRACT_VERSION", "DUPLICATE_NO_PLAN_ATR_TOLERANCE",
           "H2", "LEGACY_SCHEMA", "MIGRATION_VERSION", "OCCUPANCY_BINS", "PARITY_SCHEMA",
           "PRIMARY_ROUTE", "SCHEMA", "SECONDARY_ROUTE", "_build_base_facts", "build",
           "index_recommendation", "migrate_prior_v1", "parity_report", "validate"]
