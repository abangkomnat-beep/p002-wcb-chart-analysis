"""Canonical facts and gates shared by the Style M v4 article and image.

The module deliberately contains no network or publishing code.  It turns the
closed-H1 story into a small, deterministic semantic manifest so that the
writer and renderer cannot silently disagree about levels or meanings.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


SCHEMA = "style-m-article-visual-facts/v1"
CONTRACT_VERSION = "M-PROD/v4"
H2 = ("BTCUSD H1 บอกอะไรจากโครงสร้างล่าสุด", "แนวรับ แนวต้าน และแผน BTCUSD วันนี้")
PRIMARY_ROUTE = "/thailand/asset-btc"
SECONDARY_ROUTE = "/thailand/analysis"
OCCUPANCY_BINS = 72
DUPLICATE_NO_PLAN_ATR_TOLERANCE = 0.10


def _fact(value: Any, *, unit: str | None = None, at: str | None = None,
          permission: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"value": value}
    if unit:
        result["unit"] = unit
    if at:
        result["at"] = at
    if permission:
        result["permission"] = permission
    return result


def _reason_bucket(story: dict) -> str:
    return re.sub(r"[^A-Z0-9_]+", "_", str(story.get("reason_code") or "UNKNOWN").upper()).strip("_")


def _trendline_fact(story: dict) -> dict[str, Any]:
    highs = story.get("pivots", {}).get("highs", [])
    candidates = []
    for left in highs:
        for right in highs:
            gap = int(right.get("index", 0)) - int(left.get("index", 0))
            if gap >= 12 and float(left["price"]) > float(right["price"]):
                candidates.append((gap, left, right))
    if not candidates:
        return {"status": "not_shown", "anchor_ids": []}
    _, left, right = max(candidates, key=lambda item: item[0])
    return {"status": "shown", "anchor_ids": [
        f"structure.pivot.high.{left['index']}", f"structure.pivot.high.{right['index']}"
    ]}


def build(story: dict, rows: list[dict], *, events: list[dict] | None = None,
          news_report: dict | None = None,
          prior_fingerprint: dict | None = None) -> dict[str, Any]:
    """Build canonical facts from the already validated story/evidence."""
    latest = story["latest"]
    indicators = story["indicators"]
    highs = story.get("pivots", {}).get("highs", [])
    lows = story.get("pivots", {}).get("lows", [])
    facts: dict[str, Any] = {
        "market.latest.close": _fact(latest["close"], unit="USD", at=latest["at"]),
        "market.ema20": _fact(indicators["ema20"], unit="USD"),
        "market.ema50": _fact(indicators["ema50"], unit="USD"),
        "market.ema_relation": _fact(
            "ema20_above_ema50" if indicators["ema20"] > indicators["ema50"] else
            "ema20_below_ema50" if indicators["ema20"] < indicators["ema50"] else "ema20_equal_ema50"),
        "market.atr14": _fact(indicators["atr14"], unit="USD"),
        "occupancy.price_bins": {"count": OCCUPANCY_BINS, "source_volume_available": False,
                                  "meaning": "closed_h1_price_occupancy"},
        "structure.trendline": _trendline_fact(story),
        "structure.breakout_rejection": _fact("none"),
        "plan.state": _fact(story["state"]),
    }
    for kind, pivots in (("high", highs), ("low", lows)):
        for pivot in pivots[-2:]:
            facts[f"structure.pivot.{kind}.{pivot['index']}"] = _fact(
                pivot["price"], unit="USD", at=pivot["at"])
    if highs:
        facts["zone.resistance.primary"] = {"low": highs[-1]["price"], "high": highs[-1]["price"],
                                             "unit": "USD", "source": "confirmed_pivot"}
    if lows:
        facts["zone.support.primary"] = {"low": lows[-1]["price"], "high": lows[-1]["price"],
                                          "unit": "USD", "source": "confirmed_pivot"}
    state = story["state"]
    plan = story.get("plan")
    if state in ("WAIT_H1_CONFIRM", "PLAN_VALID") and plan:
        facts["plan.side"] = _fact(
            story.get("side"),
            permission="conditional" if state == "WAIT_H1_CONFIRM" else "allowed")
        for key in ("entry_low", "entry_high", "sl", "tp1", "tp2", "rr1", "rr2"):
            facts[f"plan.{key}"] = _fact(plan[key], unit="USD" if key not in ("rr1", "rr2") else "RR")
        facts["plan.trigger"] = _fact("conditional_h1_close", permission="conditional")
        facts["plan.invalidation"] = _fact("h1_close_beyond_sl", permission="conditional")
        facts["plan.sl_tp_rr"] = _fact("available", permission="conditional" if state == "WAIT_H1_CONFIRM" else "allowed")
    else:
        facts["plan.trigger"] = _fact(None, permission="forbidden")
        facts["plan.side"] = _fact(None, permission="forbidden")
        facts["plan.entry"] = _fact(None, permission="forbidden")
        facts["plan.invalidation"] = _fact("reassess_on_next_closed_h1", permission="conditional_only")
        facts["plan.sl_tp_rr"] = _fact(None, permission="forbidden")
    selected = (events or [])[:1]
    news = {"public_advisory": bool(selected),
            "selected_event_id": selected[0].get("event_id") if selected else None,
            "provider_status": (news_report or {}).get("provider_status", "ok")}
    fingerprint_payload = {
        "asset": story["asset"], "timeframe": story["timeframe"], "state": state,
        "reason_bucket": _reason_bucket(story),
        "ema_relation": facts["market.ema_relation"]["value"],
        "atr14": indicators["atr14"],
        "support": facts.get("zone.support.primary"),
        "resistance": facts.get("zone.resistance.primary"),
        "plan": {key: facts[key]["value"] for key in facts if key.startswith("plan.") and
                 isinstance(facts[key], dict) and facts[key].get("value") is not None},
    }
    fingerprint = hashlib.sha256(json.dumps(fingerprint_payload, ensure_ascii=False,
                                             sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "schema": SCHEMA, "contract_version": CONTRACT_VERSION, "asset": story["asset"],
        "timeframe": story["timeframe"], "cutoff": story["cutoff"],
        "source": {"sha256": story["source_sha256"], "closed_h1": True},
        "facts": facts, "news": news,
        "web_routes": {"primary": PRIMARY_ROUTE, "secondary": SECONDARY_ROUTE},
        "semantic_fingerprint": fingerprint, "fingerprint_basis": fingerprint_payload,
        "prior_fingerprint": prior_fingerprint,
    }


def index_recommendation(facts: dict, prior_fingerprint: dict | str | None = None) -> dict[str, Any]:
    """Return a local-only recommendation; this function never changes indexing."""
    current = facts.get("semantic_fingerprint")
    current_basis = facts.get("fingerprint_basis") or {}
    previous = (prior_fingerprint or {}).get("semantic_fingerprint") if isinstance(prior_fingerprint, dict) else prior_fingerprint
    previous_basis = (prior_fingerprint or {}).get("fingerprint_basis") if isinstance(prior_fingerprint, dict) else None
    duplicate = previous == current
    if previous_basis and current_basis:
        duplicate = _duplicate_basis(current_basis, previous_basis)
    if facts.get("facts", {}).get("plan.state", {}).get("value") == "NO_PLAN" and duplicate:
        return {"schema": "style-m-index-policy/v1", "recommendation": "HOLD_DUPLICATE_NO_PLAN",
                "index": False, "reason": "semantic_fingerprint_within_0.10_atr"}
    return {"schema": "style-m-index-policy/v1", "recommendation": "NEW_DRAFT",
            "index": True, "reason": "new_semantic_fingerprint"}


def _duplicate_basis(current: dict, previous: dict) -> bool:
    """Conservative semantic duplicate test for NO_PLAN (levels within 0.10 ATR)."""
    for key in ("state", "reason_bucket", "ema_relation"):
        if current.get(key) != previous.get(key):
            return False
    try:
        atr = min(float(current["atr14"]), float(previous["atr14"]))
    except (KeyError, TypeError, ValueError):
        return current == previous
    tolerance = DUPLICATE_NO_PLAN_ATR_TOLERANCE * atr
    for key in ("support", "resistance"):
        left, right = current.get(key), previous.get(key)
        if (left is None) != (right is None):
            return False
        if left is None:
            continue
        for bound in ("low", "high"):
            try:
                if abs(float(left[bound]) - float(right[bound])) > tolerance + 1e-9:
                    return False
            except (KeyError, TypeError, ValueError):
                return False
    return True


def parity_report(facts: dict, *, markdown: str, render_report: dict) -> dict[str, Any]:
    """Compare the two consumers' declared facts and fail closed on divergence."""
    text_ids = []
    for fact_id, item in facts.get("facts", {}).items():
        value = item.get("value") if isinstance(item, dict) else None
        tokens = {str(value)}
        if isinstance(value, (int, float)):
            tokens.add(f"{float(value):,.2f}")
            tokens.add(f"{float(value):,.0f}")
        if value is not None and any(token in markdown for token in tokens):
            text_ids.append(fact_id)
        elif isinstance(item, dict) and {"low", "high"} <= set(item):
            if all(any(token in markdown for token in {str(item[key]), f"{float(item[key]):,.2f}",
                                                        f"{float(item[key]):,.0f}"}) for key in ("low", "high")):
                text_ids.append(fact_id)
        elif fact_id == "occupancy.price_bins" and "การกระจุกตัวของราคาปิด" in markdown:
            text_ids.append(fact_id)
        elif fact_id == "plan.state":
            labels = {"NO_PLAN": "ยังไม่ควรสร้างแผน", "INVALIDATED": "แผนก่อนหน้าใช้ต่อไม่ได้",
                      "WAIT_H1_CONFIRM": "ฉากทัศน์", "PLAN_VALID": "ฉากทัศน์"}
            if labels.get(value) in markdown:
                text_ids.append(fact_id)
        elif fact_id == "plan.side":
            labels = {"BUY": "ฝั่งซื้อ", "SELL": "ฝั่งขาย"}
            if value in labels and labels[value] in markdown:
                text_ids.append(fact_id)
        elif fact_id == "structure.trendline" and item.get("status") == "shown":
            if "เส้นแนวโน้ม" in markdown:
                text_ids.append(fact_id)
    visual_ids = list(render_report.get("displayed_fact_ids", []))
    orphan_text = sorted(set(text_ids) - set(visual_ids))
    orphan_visual = sorted(set(visual_ids) - set(text_ids))
    # Structural facts can be visible in the image without a numeric text token;
    # only level-bearing facts are strict here.
    strict_orphans = list(orphan_visual)
    numeric_mismatches = []
    for fact_id in visual_ids:
        item = facts.get("facts", {}).get(fact_id)
        if not isinstance(item, dict):
            continue
        values = []
        if item.get("value") is not None:
            values.append(item["value"])
        if {"low", "high"} <= set(item):
            values.extend((item["low"], item["high"]))
        for value in values:
            if isinstance(value, (int, float)):
                tokens = (str(value), f"{float(value):,.2f}", f"{float(value):,.0f}")
                if not any(token in markdown for token in tokens):
                    numeric_mismatches.append({"fact_id": fact_id, "value": value})
    rendered_values = render_report.get("rendered_fact_values", {})
    for fact_id, rendered in rendered_values.items():
        canonical = facts.get("facts", {}).get(fact_id)
        if canonical != rendered:
            numeric_mismatches.append({"fact_id": fact_id, "canonical": canonical,
                                        "rendered": rendered})
    # Market context (latest close/ATR) is intentionally article-only; levels
    # must be present in both consumers because they affect execution geometry.
    # RR is an article-only calculation; it is deliberately not drawn as a
    # label or zone in the image. All displayed execution levels remain two-way.
    strict_text_orphans = [item for item in orphan_text
                           if (item.startswith(("zone.", "plan.")) and
                               item not in {"plan.rr1", "plan.rr2"})]
    status = "BLOCK" if strict_orphans or strict_text_orphans or numeric_mismatches else "PASS"
    return {"schema": "style-m-parity-report/v1", "status": status,
            "text_fact_ids": sorted(text_ids), "visual_fact_ids": sorted(visual_ids),
            "orphan_text": orphan_text, "orphan_visual": orphan_visual,
            "numeric_mismatches": numeric_mismatches}


__all__ = ["CONTRACT_VERSION", "DUPLICATE_NO_PLAN_ATR_TOLERANCE", "H2", "OCCUPANCY_BINS", "PRIMARY_ROUTE", "SCHEMA",
           "SECONDARY_ROUTE", "build", "index_recommendation", "parity_report"]
