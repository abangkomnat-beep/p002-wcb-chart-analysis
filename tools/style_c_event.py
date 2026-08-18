"""Select released XAUUSD events and build immutable Style-C evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from tools import event_evidence, intraday_bars

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "config" / "style_c_event_semantics.json"
BANGKOK = ZoneInfo("Asia/Bangkok")
IMPACT = {"Low": 1, "Medium": 2, "High": 3}


def _field(row: dict, name: str):
    """Accept the feed's lowercase form and preserved provider casing."""
    return row.get(name) if name in row else row.get(name.capitalize())


def load_registry(path: Path | None = None) -> dict:
    return json.loads((path or REGISTRY_PATH).read_text(encoding="utf-8"))


def _dt(value, *, thai: bool = False) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        try:
            moment = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=BANGKOK if thai else timezone.utc)
    return moment.astimezone(timezone.utc)


def _family(event: dict, registry: dict) -> dict | None:
    key = str(event.get("id") or event.get("ID") or event.get("event_id") or "")
    title = str(event.get("title_en") or event.get("title") or event.get("Title")
                or event.get("name") or event.get("Name") or "").strip()
    country = _field(event, "country")
    for family in registry.get("families") or []:
        if country != family.get("country"):
            continue
        if key in {str(item) for item in family.get("source_ids") or []}:
            return family
        if title in set(family.get("approved_aliases") or []):
            return family
    return None


def _event_at(event: dict) -> datetime | None:
    return (_dt(event.get("at_utc") or event.get("AtUtc") or event.get("AtUTC"))
            or _dt(event.get("at_th") or event.get("AtTh") or event.get("AtTH"), thai=True))


def _retrieved(raw: dict) -> datetime | None:
    for key in ("retrieved_at", "generated_at", "generatedAt", "as_of"):
        value = _dt(raw.get(key))
        if value:
            return value
    return None


def _timezone_check_ok(price_meta: dict | None, asset: str) -> bool:
    """Canonical rows are trusted only with the structured registry check from fetch_rows."""
    check = (price_meta or {}).get("timezone_check")
    return bool(isinstance(check, dict)
                and check.get("asset") == asset
                and isinstance(check.get("expected_offset_minutes"), int)
                and isinstance(check.get("verified"), bool)
                and str(check.get("reason") or "").strip())


def _m5_timezone_check_ok(price_meta: dict | None, asset: str) -> bool:
    """Chart Gate0 is stricter: a structured but unverified check is not enough."""
    check = (price_meta or {}).get("timezone_check")
    return bool(isinstance(check, dict)
                and check.get("asset") == asset
                and isinstance(check.get("expected_offset_minutes"), int)
                and check.get("verified") is True
                and str(check.get("reason") or "").strip())


def validate_contract(payload: dict) -> list[str]:
    """Dependency-free runtime validation for the nested v1 evidence contract."""
    missing: list[str] = []

    def require(mapping, keys, path):
        if not isinstance(mapping, dict):
            missing.append(path)
            return
        for key in keys:
            if key not in mapping:
                missing.append(f"{path}.{key}")

    require(payload, ("identity", "skip_reasons", "validation"), "$)")
    identity = payload.get("identity") or {}
    require(identity, ("schema", "asset", "writer_id", "batch_id", "analysis_mode",
                       "as_of_utc", "timezone", "clearance"), "identity")
    mode = identity.get("analysis_mode")
    if mode not in {"post_event", "post_event_factual_only", "not_applicable"}:
        missing.append("identity.analysis_mode:enum")
    require(payload.get("validation"), ("numbers_mapped", "no_lookahead", "causal_language",
                                         "license_status", "violations"), "validation")
    if not isinstance(payload.get("skip_reasons"), list):
        missing.append("skip_reasons:type")
    if mode == "not_applicable":
        return missing
    for key in ("provenance", "event", "eligibility", "surprise", "reaction", "interpretation"):
        if key not in payload:
            missing.append(key)
    provenance = payload.get("provenance") or {}
    require(provenance, ("calendar", "price"), "provenance")
    for source in ("calendar", "price"):
        require(provenance.get(source), ("provider", "retrieved_at", "payload_sha256", "source_ref"),
                f"provenance.{source}")
    require(payload.get("event"), ("source_event_key", "family_id", "title_raw", "country",
                                    "impact", "event_at_th", "event_at_utc", "actual",
                                    "forecast", "previous"), "event")
    for name in ("actual", "forecast", "previous"):
        require((payload.get("event") or {}).get(name),
                ("raw", "value", "unit", "unit_kind", "unit_source", "scale_unknown"),
                f"event.{name}")
    require(payload.get("eligibility"), ("lookback_start_utc", "relevance_tier", "rule_id",
                                          "rank_tuple", "rejected_candidates"), "eligibility")
    require(payload.get("surprise"), ("unit_compatible", "actual_vs_forecast",
                                       "actual_vs_previous", "semantics_version",
                                       "direction_status"), "surprise")
    reaction = payload.get("reaction") or {}
    require(reaction, ("status", "timeframe", "timezone_normalized", "bar_semantics",
                       "bars", "metrics", "missing_slots"), "reaction")
    for index, bar in enumerate(reaction.get("bars") or []):
        require(bar, ("slot", "open_at_th", "open_at_utc", "end_at_utc", "ohlc",
                      "forming", "source_index"), f"reaction.bars[{index}]")
        require(bar.get("ohlc") if isinstance(bar, dict) else None,
                ("open", "high", "low", "close"), f"reaction.bars[{index}].ohlc")
    for name, metric in (reaction.get("metrics") or {}).items():
        require(metric, ("formula", "inputs", "value_unrounded", "value_rounded", "unit"),
                f"reaction.metrics.{name}")
    require(payload.get("interpretation"), ("mechanism_id", "confidence", "counter_evidence",
                                             "causal_status"), "interpretation")
    return missing


def _finish(payload: dict) -> dict:
    errors = validate_contract(payload)
    if errors:
        payload["validation"]["violations"].extend(f"schema_invalid:{item}" for item in errors)
        if "schema_invalid" not in payload["skip_reasons"]:
            payload["skip_reasons"].append("schema_invalid")
        payload["identity"]["analysis_mode"] = "not_applicable"
    return payload


def select_event(raw: dict, as_of: datetime, registry: dict | None = None) -> dict:
    registry = registry or load_registry()
    as_of = as_of.astimezone(timezone.utc)
    lookback = as_of - timedelta(hours=int(registry["rollout"]["lookback_hours"]))
    retrieved = _retrieved(raw)
    rejected, eligible = [], []
    for event in raw.get("events") or []:
        reasons = []
        at = _event_at(event)
        family = _family(event, registry)
        actual_raw = _field(event, "actual")
        actual = event_evidence.parse_value(actual_raw, unit_kind=(family or {}).get("unit_kind"))
        if retrieved and retrieved > as_of:
            reasons.append("source_after_as_of")
        if not at:
            reasons.append("event_time_invalid")
        elif at > as_of:
            reasons.append("event_in_future")
        elif at <= lookback:
            reasons.append("event_outside_24h")
        if actual["value"] is None:
            reasons.append("actual_missing" if not actual_raw else "actual_unparseable")
        if _field(event, "country") != "USD":
            reasons.append("country_not_directly_approved_for_xauusd")
        elif family is None:
            reasons.append("family_not_allowlisted")
        impact = _field(event, "impact")
        if family and IMPACT.get(str(impact), 0) < IMPACT.get(family["min_impact"], 0):
            reasons.append("impact_below_family_minimum")
        if reasons:
            rejected.append({"source_event_key": str(event.get("id") or ""), "reasons": reasons})
            continue
        completeness = sum(_field(event, k) not in (None, "") for k in ("actual", "forecast", "previous"))
        rank = [int(family["priority"]), IMPACT.get(impact, 0), completeness,
                at.timestamp(), str(event.get("id") or "")]
        eligible.append((rank, event, family, at))
    if not eligible:
        return {"event": None, "family": None, "event_at": None,
                "rank_tuple": [], "rejected_candidates": rejected,
                "skip_reasons": ["no_eligible_released_event"]}
    eligible.sort(key=lambda item: item[0], reverse=True)
    rank, event, family, at = eligible[0]
    rejected.extend({"source_event_key": str(item[1].get("id") or ""), "reasons": ["ranked_lower"]}
                    for item in eligible[1:])
    return {"event": event, "family": family, "event_at": at,
            "rank_tuple": rank, "rejected_candidates": rejected, "skip_reasons": []}


def _metric(formula: str, inputs: dict, value: float, digits: int, unit: str) -> dict:
    return {"formula": formula, "inputs": inputs, "value_unrounded": value,
            "value_rounded": round(value, digits), "unit": unit}


def build_reaction(rows: list[dict], event_at: datetime, as_of: datetime) -> dict:
    event_at = event_at.astimezone(timezone.utc)
    as_of = as_of.astimezone(timezone.utc)
    if event_at.minute not in (0, 30) or event_at.second:
        return {"status": "insufficient_bars", "timeframe": "30min",
                "timezone_normalized": True, "bar_semantics": "[open,end)", "bars": [],
                "metrics": {}, "missing_slots": ["event_not_m30_aligned"]}
    candidates = []
    rejected = []
    for index, row in enumerate(rows):
        opened_th = intraday_bars.parse_at(row["at"])
        opened = opened_th.astimezone(timezone.utc)
        ended = opened + timedelta(minutes=30)
        if row.get("forming"):
            rejected.append("forming_bar_rejected")
            continue
        if ended > as_of:
            rejected.append("bar_after_as_of_rejected")
            continue
        candidates.append((ended, index, row, opened_th, opened))
    targets = {"+30": event_at + timedelta(minutes=30), "+60": event_at + timedelta(minutes=60),
               "+90": event_at + timedelta(minutes=90), "+120": event_at + timedelta(minutes=120)}
    picked = {}
    pre = [item for item in candidates if item[0] <= event_at]
    if pre:
        picked["pre"] = max(pre, key=lambda item: item[0])
    for slot, target in targets.items():
        match = next((item for item in candidates if item[0] == target), None)
        if match:
            picked[slot] = match
    missing = (["missing_pre_bar"] if "pre" not in picked else [])
    missing += (["missing_post_30_bar"] if "+30" not in picked else [])
    missing += (["missing_post_60_bar"] if "+60" not in picked else [])
    missing += (["missing_post_90_bar"] if "+90" not in picked else [])
    missing += (["missing_post_120_bar"] if "+120" not in picked else [])
    bars = []
    for slot in ("pre", "+30", "+60", "+90", "+120"):
        if slot not in picked:
            continue
        ended, index, row, opened_th, opened = picked[slot]
        bars.append({"slot": slot, "open_at_th": opened_th.isoformat(),
                     "open_at_utc": opened.isoformat(), "end_at_utc": ended.isoformat(),
                     "ohlc": {k: float(row[k]) for k in ("open", "high", "low", "close")},
                     "forming": False, "source_index": index})
    metrics = {}
    if "pre" in picked:
        base = float(picked["pre"][2]["close"])
        for slot, minutes in (("+30", 30), ("+60", 60), ("+90", 90), ("+120", 120)):
            if slot not in picked:
                continue
            close = float(picked[slot][2]["close"])
            metrics[f"delta_{minutes}"] = _metric("post_close-pre_close", {"pre_close": base, "post_close": close}, close-base, 5, "USD")
            metrics[f"pct_{minutes}"] = _metric("(post_close-pre_close)/pre_close*100", {"pre_close": base, "post_close": close}, (close-base)/base*100, 5 if minutes <= 60 else 4, "%")
        for minutes, slots in ((30, ("+30",)), (60, ("+30", "+60")), (90, ("+30", "+60", "+90")), (120, ("+30", "+60", "+90", "+120"))):
            available = [picked[s][2] for s in slots if s in picked]
            if len(available) != len(slots):
                continue
            high, low = max(float(r["high"]) for r in available), min(float(r["low"]) for r in available)
            metrics[f"range_{minutes}"] = _metric("max(high)-min(low)", {"high": high, "low": low}, high-low, 5, "USD")
            metrics[f"range_pct_{minutes}"] = _metric("range/pre_close*100", {"range": high-low, "pre_close": base}, (high-low)/base*100, 4 if minutes >= 90 else 5, "%")
    status = "complete" if not missing else "insufficient_bars"
    return {"status": status, "timeframe": "30min", "timezone_normalized": True,
            "bar_semantics": "[open,end)", "bars": bars, "metrics": metrics,
            "missing_slots": missing + sorted(set(rejected))}


def build_chart_reaction(rows: list[dict], event_at: datetime, as_of: datetime,
                         price_meta: dict | None, m30_reaction: dict) -> dict:
    """Select an exact canonical M5 window; never derive/resample it from M30."""
    event_th = event_at.astimezone(BANGKOK)
    as_of = as_of.astimezone(timezone.utc)
    start_th, end_th = event_th - timedelta(minutes=15), event_th + timedelta(minutes=120)
    expected = [start_th + timedelta(minutes=5 * index) for index in range(27)]
    by_open = {}
    rejected = []
    for row in rows:
        opened = intraday_bars.parse_at(row["at"])
        closed = opened + timedelta(minutes=5)
        if row.get("forming"):
            rejected.append("forming_m5_bar_rejected")
            continue
        if closed.astimezone(timezone.utc) > as_of:
            rejected.append("m5_bar_after_as_of_rejected")
            continue
        if start_th <= opened < end_th:
            if opened in by_open:
                rejected.append("duplicate_m5_open")
            by_open[opened] = row
    missing = [moment.isoformat() for moment in expected if moment not in by_open]
    timezone_ok = _m5_timezone_check_ok(price_meta, "xauusd")
    if not timezone_ok:
        rejected.append("m5_timezone_unverified")
    expected_slots = ["pre", "+30", "+60", "+90", "+120"]
    m30_bars = m30_reaction.get("bars") or []
    if ([bar.get("slot") for bar in m30_bars] != expected_slots
            or m30_reaction.get("status") != "complete"):
        rejected.append("m30_anchor_evidence_incomplete")
    bars = []
    anchor_checks = []
    if not missing and len(by_open) == 27:
        for opened in expected:
            row = by_open[opened]
            bars.append({"open_at_th": opened.isoformat(),
                         "close_at_th": (opened + timedelta(minutes=5)).isoformat(),
                         "ohlc": {key: float(row[key])
                                  for key in ("open", "high", "low", "close")}})
        if "m30_anchor_evidence_incomplete" not in rejected:
            m5_by_close = {bar["close_at_th"]: bar for bar in bars}
            anchor_minutes = [0, 30, 60, 90, 120]
            for slot, minutes, m30_bar in zip(expected_slots, anchor_minutes, m30_bars):
                close_at = event_th + timedelta(minutes=minutes)
                m5_close = float(m5_by_close[close_at.isoformat()]["ohlc"]["close"])
                m30_close = float(m30_bar["ohlc"]["close"])
                m5_display, m30_display = round(m5_close, 2), round(m30_close, 2)
                match = m5_display == m30_display
                anchor_checks.append({"slot": slot, "close_at_th": close_at.isoformat(),
                                      "m5_close": m5_close, "m30_close": m30_close,
                                      "m5_display": m5_display,
                                      "m30_display": m30_display,
                                      "display_delta": round(m5_display-m30_display, 2),
                                      "display_decimals": 2, "match": match})
            if not all(item["match"] for item in anchor_checks):
                rejected.append("m5_m30_anchor_mismatch")
    complete = not missing and not rejected and len(bars) == 27
    return {"status": "complete" if complete else "insufficient_bars",
            "timeframe": "5min", "cadence_minutes": 5,
            "timezone_normalized": timezone_ok, "bar_semantics": "[open,end)",
            "window": [start_th.isoformat(), end_th.isoformat()], "bars": bars,
            "expected_count": 27, "missing_open_at_th": missing,
            "anchor_checks": anchor_checks,
            "violations": sorted(set(rejected))}


def build_evidence(calendar_raw: dict | None, rows: list[dict] | None, *, asset: str,
                   as_of: datetime, batch_id: str, price_meta: dict | None = None,
                   calendar_source: str = "WCB calendar feed", price_source: str = "WCB series API",
                   registry: dict | None = None) -> dict:
    registry = registry or load_registry()
    as_of = as_of.astimezone(timezone.utc)
    base = {"identity": {"schema": "style-c-event-evidence-v1", "asset": asset,
                         "writer_id": "c_event", "batch_id": batch_id,
                         "analysis_mode": "not_applicable", "as_of_utc": as_of.isoformat(),
                         "timezone": "Asia/Bangkok", "clearance": "internal-only"},
            "skip_reasons": [], "validation": {"numbers_mapped": True, "no_lookahead": True,
            "causal_language": "pass", "license_status": "internal-only", "violations": []}}
    if asset not in registry["rollout"]["assets"]:
        base["skip_reasons"] = ["rollout_asset_not_enabled"]
        return _finish(base)
    if not calendar_raw:
        base["skip_reasons"] = ["calendar_feed_unavailable"]
        return _finish(base)
    calendar_retrieved = _retrieved(calendar_raw)
    if calendar_retrieved is None:
        base["skip_reasons"] = ["calendar_provenance_missing"]
        return _finish(base)
    if calendar_retrieved > as_of:
        base["skip_reasons"] = ["source_after_as_of"]
        return _finish(base)
    selected = select_event(calendar_raw, as_of, registry)
    if not selected["event"]:
        rejected_reasons = {reason for item in selected["rejected_candidates"]
                            for reason in item.get("reasons") or []}
        base["skip_reasons"] = selected["skip_reasons"] + sorted(
            rejected_reasons & {"source_after_as_of", "event_in_future", "event_outside_24h"})
        base["eligibility"] = selected
        return _finish(base)
    event, family, at = selected["event"], selected["family"], selected["event_at"]
    actual = event_evidence.parse_value(_field(event, "actual"), unit_kind=family["unit_kind"])
    forecast = event_evidence.parse_value(_field(event, "forecast"), unit_kind=family["unit_kind"])
    previous = event_evidence.parse_value(_field(event, "previous"), unit_kind=family["unit_kind"])
    reaction = build_reaction(rows or [], at, as_of)
    timezone_ok = _timezone_check_ok(price_meta, asset)
    if not timezone_ok:
        reaction["status"] = "insufficient_bars"
        reaction["timezone_normalized"] = False
        if "timezone_unverified" not in reaction["missing_slots"]:
            reaction["missing_slots"].append("timezone_unverified")
    compatible = event_evidence.units_compatible(actual, forecast)
    mechanism = (registry.get("mechanisms") or {}).get(family.get("mechanism_id"), {})
    semantics_known = family.get("higher_means") is not None and bool(mechanism)
    direction = "known" if compatible and semantics_known else "unknown"
    raw_bytes = json.dumps(calendar_raw, ensure_ascii=False, sort_keys=True).encode("utf-8")
    price_bytes = json.dumps(rows or [], ensure_ascii=False, sort_keys=True).encode("utf-8")
    factual_reasons = []
    if forecast["value"] is None:
        factual_reasons.append("forecast_missing")
    if previous["value"] is None:
        factual_reasons.append("previous_missing")
    if actual.get("scale_unknown") or forecast.get("scale_unknown"):
        factual_reasons.append("scale_unknown")
    if forecast["value"] is not None and not compatible:
        factual_reasons.append("unit_mismatch")
    if not semantics_known:
        factual_reasons.append("semantics_unknown")
    if reaction["status"] != "complete":
        factual_reasons.extend(reaction["missing_slots"])
    mode = "post_event" if not factual_reasons else "post_event_factual_only"
    base["identity"]["analysis_mode"] = mode
    base["provenance"] = {
        "calendar": {"provider": "WorldClassBroker", "retrieved_at": calendar_retrieved.isoformat(), "payload_sha256": hashlib.sha256(raw_bytes).hexdigest(), "source_ref": calendar_source},
        "price": {"provider": "WorldClassBroker", "retrieved_at": as_of.isoformat(), "payload_sha256": hashlib.sha256(price_bytes).hexdigest(), "source_ref": price_source,
                  "timezone_check": (price_meta or {}).get("timezone_check")},
    }
    base["event"] = {"source_event_key": str(event.get("id") or ""), "family_id": family["family_id"],
        "title_raw": event.get("title_th") or event.get("title_en") or event.get("Title"), "country": _field(event, "country"),
        "impact": _field(event, "impact"), "event_at_th": at.astimezone(BANGKOK).isoformat(),
        "event_at_utc": at.isoformat(), "actual": actual, "forecast": forecast, "previous": previous}
    base["eligibility"] = {"lookback_start_utc": (as_of-timedelta(hours=24)).isoformat(),
        "relevance_tier": "direct", "rule_id": family["family_id"], "rank_tuple": selected["rank_tuple"],
        "rejected_candidates": selected["rejected_candidates"]}
    base["surprise"] = {"unit_compatible": compatible,
        "actual_vs_forecast": event_evidence.compare(actual, forecast),
        "actual_vs_previous": event_evidence.compare(actual, previous),
        "semantics_version": registry["version"], "direction_status": direction}
    base["reaction"] = reaction
    base["interpretation"] = {"mechanism_id": family.get("mechanism_id"),
        "mechanism_summary_th": mechanism.get("summary_th"), "confidence": mechanism.get("confidence", "low"),
        "counter_evidence": "ช่วงเวลาเดียวกันอาจมีข่าวและกระแสคำสั่งซื้ออื่น จึงยืนยันเหตุเพียงปัจจัยเดียวไม่ได้",
        "causal_status": "disabled"}
    base["skip_reasons"] = list(dict.fromkeys(factual_reasons))
    return _finish(base)
