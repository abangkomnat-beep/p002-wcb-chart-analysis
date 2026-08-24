"""Concrete local/WCB adapters for the standalone BTCUSD F+ pipeline.

The adapter owns all runtime side effects. Shadow artifacts remain below ``work``
and use a separate S01-S03 guard; production Output and daily locks are untouched.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any, Mapping

from tools import (
    brief_story,
    calendar_feed,
    chart_indicator,
    intraday_bars,
    intraday_breakout_story,
    intraday_pullback_story,
    intraday_trend_story,
)
from tools.fplus_artifacts import ArtifactTransaction
from tools.fplus_candidates import evaluate_candidate
from tools.fplus_config import validate_config
from tools.fplus_contracts import SelectedPlan, canonical_json, sha256_canonical
from tools.fplus_data import evaluate_data_gates
from tools.fplus_lock import LocalLockStore, LocalShadowStore
from tools.fplus_news import evaluate_news_gate
from tools.fplus_renderer import render_webp
from tools.fplus_risk import evaluate_risk, load_risk_thresholds
from tools.fplus_router import route as strict_route
from tools.fplus_validator import validate_artifact_set
from tools.fplus_writer import render_markdown


class ConcreteAdapterError(RuntimeError):
    """Raised when the concrete runtime cannot safely complete a stage."""


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ConcreteAdapterError("runtime timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _now() -> str:
    return _iso(datetime.now(timezone.utc))


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                         encoding="utf-8")
    os.replace(temporary, path)


def _write_immutable_canonical_json(path: Path, payload: Mapping[str, Any]) -> bytes:
    """Persist a new canonical JSON record without permitting replacement."""
    if path.exists():
        raise ConcreteAdapterError(f"immutable replay input already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    if path.exists():
        temporary.unlink(missing_ok=True)
        raise ConcreteAdapterError(f"immutable replay input appeared during write: {path}")
    os.replace(temporary, path)
    return path.read_bytes()


def _canonical_gate_context(gate_report: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the pipeline's flat data gate for presentation/replay."""
    raw = dict(gate_report)
    raw_news = raw.get("news")
    news = deepcopy(raw_news) if isinstance(raw_news, Mapping) else {}
    data = {key: deepcopy(value) for key, value in raw.items() if key != "news"}
    aggregate: list[Any] = []
    for source in (data.get("reason_codes", []), news.get("reason_codes", [])):
        if isinstance(source, (list, tuple)):
            aggregate.extend(source)
    canonical = {
        "data": data,
        "news": news,
        "reason_codes": list(dict.fromkeys(aggregate)),
    }
    return json.loads(canonical_json(canonical))


def _bias(rows: list[Mapping[str, Any]]) -> str:
    if len(rows) < 56:
        return "neutral"
    closes = [float(row["close"]) for row in rows]
    current_sma = sum(closes[-50:]) / 50
    previous_sma = sum(closes[-55:-5]) / 50
    if closes[-1] > current_sma and current_sma > previous_sma:
        return "up"
    if closes[-1] < current_sma and current_sma < previous_sma:
        return "down"
    return "neutral"


def _direction_text(direction: str) -> str:
    return {"up": "ขาขึ้น", "down": "ขาลง", "neutral": "ยังไม่ชัดเจน"}.get(direction, direction)


def _rejection(rows: list[Mapping[str, Any]], zone: Mapping[str, float], direction: str) -> bool:
    if not rows:
        return False
    row = rows[-1]
    low, high = sorted((float(zone["low"]), float(zone["high"])))
    touched = float(row["low"]) <= high and float(row["high"]) >= low
    if direction == "up":
        return touched and float(row["close"]) > float(row["open"]) and float(row["close"]) >= low
    if direction == "down":
        return touched and float(row["close"]) < float(row["open"]) and float(row["close"]) <= high
    return False


class ConcreteFPlusAdapters:
    """Production dependency implementation used only by the manual CLI."""

    def __init__(self, config: Mapping[str, Any]):
        self.config = validate_config(config)
        self.risk_contract = load_risk_thresholds()
        if self.config["risk"]["sha256"] != self.risk_contract["sha256"]:
            raise ConcreteAdapterError("runtime risk fingerprint differs from F+ config")
        self._acquired: dict[str, Any] = {}
        self._snapshot: dict[str, Any] | None = None
        self._data_report: dict[str, Any] | None = None
        self._news_report: dict[str, Any] | None = None
        self._gate_report: dict[str, Any] | None = None
        self._candidate_decisions: list[dict[str, Any]] = []
        self._selected_plan: dict[str, Any] | None = None
        self._transaction: dict[str, Any] | None = None

    @staticmethod
    def _production_key(request: Mapping[str, Any]) -> str:
        return f"fplus:btcusd:{request['trade_date_bangkok']}"

    @staticmethod
    def _shadow_key(request: Mapping[str, Any]) -> str:
        return (f"fplus-shadow:btcusd:{request['trade_date_bangkok']}:"
                f"{request['shadow_id']}")

    @staticmethod
    def _relative_final(request: Mapping[str, Any], config: Mapping[str, Any]) -> Path:
        day = datetime.strptime(str(request["trade_date_bangkok"]), "%Y-%m-%d").strftime("%d-%m-%Y")
        return Path(day) / str(config["artifact"]["folder"])

    @staticmethod
    def _production_store(request: Mapping[str, Any]) -> LocalLockStore:
        return LocalLockStore(Path(str(request["state_root"])) / "fplus" / "btcusd")

    @staticmethod
    def _shadow_store(request: Mapping[str, Any]) -> LocalShadowStore:
        return LocalShadowStore(Path(str(request["state_root"])) / "fplus" / "btcusd" / "shadow")

    def reconcile_startup(self, request: Mapping[str, Any]) -> dict[str, Any] | None:
        relative = self._relative_final(request, self.config)
        transaction = ArtifactTransaction(
            work_root=request["work_root"], output_root=request["output_root"])
        journal = transaction.journal(relative_final_dir=relative)
        if not journal:
            return None
        store = self._production_store(request)
        key = self._production_key(request)
        lock_record = store.get(key=key)
        if lock_record and lock_record.get("status") == "committed":
            return {**lock_record, "status": "already_done"}
        if journal.get("phase") == "prepared":
            return None
        recovered = transaction.recover(relative_final_dir=relative)
        manifest = recovered["manifest"]
        final = Path(recovered["final_dir"])
        if not transaction._manifest_matches(final, manifest):  # noqa: SLF001
            # Recovery restored/kept the previous generation. It is safe to
            # retry, but it is not the generation named by this journal.
            return None
        hashes = {item["name"]: item["sha256"] for item in manifest.get("files", [])}
        paths = [str(final / item["name"]) for item in manifest.get("files", [])]
        reconciled = store.reconcile_committed(
            key=key, run_id=str(manifest["run_id"]), generation=int(manifest["generation"]),
            now_utc=_now(), artifact_hashes=hashes, artifact_paths=paths,
        )
        transaction.mark_lock_committed(relative_final_dir=relative)
        return reconciled

    def acquire_production(self, request: Mapping[str, Any]) -> dict[str, Any]:
        result = self._production_store(request).acquire(
            key=self._production_key(request), run_id=str(request["run_id"]),
            now_utc=_now(), lease_seconds=int(self.config["lock"]["lease_seconds"]),
            cutoff_at_utc=str(request["decision_cutoff_utc"]),
            config_fingerprint=str(request["config_fingerprint"]),
            force=request.get("generation_request") == "force",
            force_reason=request.get("force_reason"),
        )
        self._acquired = dict(result)
        return result

    def acquire_shadow(self, request: Mapping[str, Any]) -> dict[str, Any]:
        shadow_id = str(request.get("shadow_id") or "")
        result = self._shadow_store(request).acquire_shadow(
            key=self._shadow_key(request), run_id=str(request["run_id"]), shadow_id=shadow_id,
            now_utc=_now(), lease_seconds=int(self.config["lock"]["lease_seconds"]),
            cutoff_at_utc=str(request["decision_cutoff_utc"]),
            config_fingerprint=str(request["config_fingerprint"]),
        )
        self._acquired = dict(result)
        return result

    def heartbeat(self, request: Mapping[str, Any]) -> dict[str, Any] | None:
        if not self._acquired or self._acquired.get("status") != "claimed":
            return None
        lease = int(self.config["lock"]["lease_seconds"])
        if request["mode"] == "shadow":
            return self._shadow_store(request).heartbeat(
                key=self._shadow_key(request), run_id=str(request["run_id"]),
                now_utc=_now(), lease_seconds=lease)
        return self._production_store(request).heartbeat(
            key=self._production_key(request), run_id=str(request["run_id"]),
            now_utc=_now(), lease_seconds=lease)

    @staticmethod
    def _normalize_rows(rows: list[dict[str, Any]], timeframe: str) -> list[dict[str, Any]]:
        span = timedelta(minutes=intraday_bars.spec_for(timeframe)["minutes"])
        normalized: list[dict[str, Any]] = []
        for row in rows:
            start = intraday_bars.parse_at(row["at"]).astimezone(timezone.utc)
            close = start + span
            normalized.append({
                "bar_start_at_utc": _iso(start), "bar_close_at_utc": _iso(close),
                "open": float(row["open"]), "high": float(row["high"]),
                "low": float(row["low"]), "close": float(row["close"]),
                "date": row["date"], "at": row["at"], "at_feed": row.get("at_feed"),
                "forming": False,
            })
        return normalized

    @staticmethod
    def _calendar(request: Mapping[str, Any]) -> dict[str, Any]:
        trade_date = str(request["trade_date_bangkok"])
        trade_day = datetime.strptime(trade_date, "%Y-%m-%d").date()
        try:
            raw = calendar_feed.fetch_raw(
                from_date=(trade_day - timedelta(days=1)).isoformat(),
                to_date=(trade_day + timedelta(days=1)).isoformat(),
                impact="High", country="USD")
            source_events = calendar_feed.to_calendar_events(raw)
        except Exception as exc:
            return {"source": "wcb", "available": False, "events": [],
                    "error": type(exc).__name__}
        events: list[dict[str, Any]] = []
        for item in source_events:
            at = item.get("at")
            if not at:
                continue
            try:
                text_at = str(at)
                event_at = (_utc(text_at) if "T" in text_at and (
                    text_at.endswith("Z") or "+" in text_at[10:])
                    else intraday_bars.parse_at(text_at).astimezone(timezone.utc))
            except (ValueError, ConcreteAdapterError):
                continue
            events.append({
                "source": "wcb", "currency": str(item.get("country", "")).upper(),
                "impact": str(item.get("impact", "")).lower(),
                "event_at_utc": _iso(event_at), "title": str(item.get("title", "")),
                "previous": item.get("previous"), "forecast": item.get("forecast"),
                "actual": item.get("actual"),
            })
        return {"source": "wcb", "available": True, "events": events,
                "retrieved_at": raw.get("retrieved_at")}

    def fetch_snapshot(self, request: Mapping[str, Any]) -> dict[str, Any]:
        cutoff = _utc(str(request["decision_cutoff_utc"]))
        series: dict[str, Any] = {}
        for timeframe in ("4h", "1h", "30min", "15min"):
            meta, raw_rows, source = intraday_bars.fetch_rows(
                "btcusd", timeframe=timeframe, outputsize=500, now=cutoff)
            closed_rows, basis = intraday_bars.evaluate(
                raw_rows, asset="btcusd", timeframe=timeframe, now=cutoff)
            rows = self._normalize_rows(closed_rows, timeframe)
            timezone_check = meta.get("timezone_check") or {}
            series[timeframe] = {
                "rows": rows,
                "latest_bar_start_at_utc": rows[-1]["bar_start_at_utc"],
                "latest_bar_close_at_utc": rows[-1]["bar_close_at_utc"],
                "dropped_forming_bars": len(basis.get("dropped_forming_bars", [])),
                "timezone_verified": bool(timezone_check.get("verified")),
                "row_count": len(rows), "rows_sha256": sha256_canonical(rows),
                "source_label": source, "timezone_check": timezone_check,
                "legacy_rows": closed_rows, "candle_basis": basis,
            }
        snapshot: dict[str, Any] = {
            "schema_version": "fplus-market-snapshot-v1", "asset": "btcusd",
            "source": "wcb", "cutoff_at_utc": _iso(cutoff),
            "trade_date_bangkok": request["trade_date_bangkok"],
            "retrieved_at_utc": _now(), "calendar": self._calendar(request), "series": series,
        }
        snapshot["snapshot_id"] = sha256_canonical(snapshot)
        self._snapshot = snapshot
        return snapshot

    def evaluate_data(self, snapshot: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
        gate_config = {
            "required_timeframes": ["4h", "1h", "30min", "15min"],
            "warmup_bars": config["warmup_bars"],
            "freshness_grace_seconds": config["freshness_grace_by_timeframe"],
            "cross_timeframe_tolerance": config["cross_timeframe_tolerance"],
        }
        self._data_report = evaluate_data_gates(snapshot, config=gate_config)
        return self._data_report

    def evaluate_news(
        self, snapshot: Mapping[str, Any], request: Mapping[str, Any],
        config: Mapping[str, Any],
    ) -> dict[str, Any]:
        calendar = snapshot.get("calendar") or {}
        news = config["news"]
        self._news_report = evaluate_news_gate(
            calendar.get("events", []), cutoff_at_utc=str(request["decision_cutoff_utc"]),
            calendar_available=bool(calendar.get("available")), source=str(news["source"]),
            before_minutes=int(news["before_minutes"]), after_minutes=int(news["after_minutes"]),
        )
        return self._news_report

    def _risk(
        self, direction: str, zone: Mapping[str, float], stop: float, target: float,
        current: float, atr: float,
    ) -> dict[str, Any]:
        return evaluate_risk(
            direction="long" if direction == "up" else "short", entry_zone=zone,
            stop_loss=stop, take_profit_1=target, current_price=current, atr=atr,
            thresholds=self.risk_contract["thresholds"],
        )

    @staticmethod
    def _failed_decision(name: str, reason: str) -> dict[str, Any]:
        return {
            "candidate": name, "eligible": False, "state": "UNAVAILABLE",
            "direction": "neutral", "setup_id": None, "entry_zone": None,
            "stop_loss": None, "take_profit_1": None, "rr_worst_edge": None,
            "stop_atr": None, "entry_distance_atr": None,
            "gate_results": {"candidate": False, "risk": False},
            "reason_codes": [reason], "evidence_refs": [],
        }

    def evaluate_candidates(
        self, snapshot: Mapping[str, Any], config: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        del config
        frames = snapshot["series"]
        h4 = frames["4h"]["legacy_rows"]
        h1 = frames["1h"]["legacy_rows"]
        m30 = frames["30min"]["legacy_rows"]
        m15 = frames["15min"]["legacy_rows"]
        bias_h4, bias_h1 = _bias(h4), _bias(h1)
        decisions: dict[str, dict[str, Any]] = {}

        try:
            h_story = intraday_trend_story.build(
                m30, asset="btcusd", timeframe="30min",
                candle_basis=frames["30min"]["candle_basis"], previous_state=None)
            h_state = h_story["state"]
            h_direction = h_story.get("direction")
        except Exception as exc:
            h_story = {"state": "UNAVAILABLE", "direction": None, "error": type(exc).__name__}
            h_state, h_direction = "UNAVAILABLE", None

        try:
            first_j = intraday_pullback_story.build(
                m30, m15, asset="btcusd", candle_basis=frames["15min"]["candle_basis"],
                context_basis=frames["30min"]["candle_basis"], previous_state=None)
            zone = first_j["pullback_zone"]
            prior_close = float(m15[-2]["close"])
            prior_in_zone = float(zone["low"]) <= prior_close <= float(zone["high"])
            j_story = (intraday_pullback_story.build(
                m30, m15, asset="btcusd", candle_basis=frames["15min"]["candle_basis"],
                context_basis=frames["30min"]["candle_basis"],
                previous_state=intraday_pullback_story.PULLBACK_FORMING)
                if prior_in_zone else first_j)
            direction = j_story.get("direction") or "neutral"
            atr = float(j_story["atr"]["value"])
            entry = {"low": float(zone["low"]), "high": float(zone["high"])}
            if direction == "up":
                stop = min(entry.values()) - atr
                edge = entry["high"]
                target = edge + 1.2 * (edge - stop)
            else:
                stop = max(entry.values()) + atr
                edge = entry["low"]
                target = edge - 1.2 * (stop - edge)
            risk = self._risk(direction, entry, stop, target, float(m15[-1]["close"]), atr)
            evidence = {
                "state": j_story["state"], "h4_bias": bias_h4, "h1_bias": bias_h1,
                "m30_bias": direction, "m15_confirmed": j_story["state"] in {
                    "PULLBACK_CONFIRMED", "TREND_RESUMED"}, "invalidated": False,
                "setup_id": f"J-{snapshot['snapshot_id'][:12]}", "entry_zone": entry,
                "stop_loss": stop, "take_profit_1": target,
                "evidence_refs": ["snapshot:H4", "snapshot:H1", "snapshot:M30", "snapshot:M15"],
            }
            decisions["J"] = evaluate_candidate("J", evidence=evidence, risk_result=risk)
            decisions["J"]["summary"] = {"bias_h4": bias_h4, "bias_h1": bias_h1,
                                                "m30": j_story["state"], "m15": j_story["state"],
                                                "invalidation": j_story["invalidation"]["rule"]}
        except Exception as exc:
            decisions["J"] = self._failed_decision("J", f"J_CALCULATION_UNAVAILABLE_{type(exc).__name__.upper()}")

        try:
            i_story = intraday_breakout_story.build(
                m15, asset="btcusd", timeframe="15min",
                candle_basis=frames["15min"]["candle_basis"], previous_state=None)
            direction = i_story.get("direction") or "neutral"
            atr = float(i_story["atr"]["value"])
            boundary = float(i_story["donchian"]["upper" if direction == "up" else "lower"])
            entry = {"low": boundary - 0.05 * atr, "high": boundary + 0.05 * atr}
            if direction == "up":
                stop = entry["low"] - atr
                target = entry["high"] + 1.2 * (entry["high"] - stop)
            else:
                stop = entry["high"] + atr
                target = entry["low"] - 1.2 * (stop - entry["low"])
            risk = self._risk(direction, entry, stop, target, float(m15[-1]["close"]), atr)
            classifier = h_direction or ("no_trend" if h_state == "NO_TREND" else "transition")
            evidence = {
                "state": i_story["state"], "direction": direction, "h4_bias": bias_h4,
                "m30_classifier": classifier, "donchian_confirmed": i_story["state"] in {
                    "BREAKOUT_UP", "BREAKOUT_DOWN"},
                "true_range_confirmed": float(i_story["atr"]["expansion_ratio"]) >= float(i_story["thresholds"]["breakout_tr_atr"]),
                "bbw_expanding": bool(i_story["bbw"]["rising"]),
                "setup_id": f"I-{snapshot['snapshot_id'][:12]}", "entry_zone": entry,
                "stop_loss": stop, "take_profit_1": target,
                "evidence_refs": ["snapshot:H4", "snapshot:M30", "snapshot:M15"],
            }
            decisions["I"] = evaluate_candidate("I", evidence=evidence, risk_result=risk)
            decisions["I"]["summary"] = {"bias_h4": bias_h4, "bias_h1": bias_h1,
                                                "m30": h_state, "m15": i_story["state"],
                                                "invalidation": i_story["invalidation"]["rule"]}
        except Exception as exc:
            decisions["I"] = self._failed_decision("I", f"I_CALCULATION_UNAVAILABLE_{type(exc).__name__.upper()}")

        try:
            e_story = chart_indicator.build_indicators(
                h1, asset="btcusd", publish_date=str(snapshot["trade_date_bangkok"]),
                candle_basis=frames["1h"]["candle_basis"], timeframe="1h")
            scenario = e_story["scenarios"]["primary"]
            if not scenario:
                raise ConcreteAdapterError("no valid Fibonacci swing")
            direction = "up" if scenario["side"] == "buy" else "down"
            entry = {"low": min(float(scenario["entry_low"]), float(scenario["entry_high"])),
                     "high": max(float(scenario["entry_low"]), float(scenario["entry_high"]))}
            m15_rejection = _rejection(m15, entry, direction)
            risk = self._risk(direction, entry, float(scenario["sl"]),
                              float(scenario["tps"][0]), float(m15[-1]["close"]),
                              float(e_story["atr14"]))
            evidence = {
                "scenario": "follow_trend", "daily_entry": bool(scenario["daily_entry"]),
                "h4_bias": bias_h4, "h1_bias": bias_h1,
                "fibonacci_swing_valid": e_story.get("fib") is not None,
                "in_golden_zone": (float(m15[-1]["low"]) <= entry["high"]
                                   and float(m15[-1]["high"]) >= entry["low"]),
                "m15_rejection": m15_rejection,
                "rsi_conflicts": ((direction == "up" and e_story["rsi"]["value"] < 50)
                                  or (direction == "down" and e_story["rsi"]["value"] > 50)),
                "macd_conflicts": ((direction == "up" and not e_story["macd"]["bullish"])
                                   or (direction == "down" and e_story["macd"]["bullish"])),
                "setup_id": f"ELOGIC-{snapshot['snapshot_id'][:12]}", "entry_zone": entry,
                "stop_loss": float(scenario["sl"]), "take_profit_1": float(scenario["tps"][0]),
                "evidence_refs": ["snapshot:H4", "snapshot:H1", "snapshot:M15"],
            }
            decisions["E_LOGIC"] = evaluate_candidate("E_LOGIC", evidence=evidence, risk_result=risk)
            decisions["E_LOGIC"]["summary"] = {"bias_h4": bias_h4, "bias_h1": bias_h1,
                                                      "m30": h_state,
                                                      "m15": "rejection" if m15_rejection else "unconfirmed",
                                                      "invalidation": scenario["condition"]}
        except Exception as exc:
            decisions["E_LOGIC"] = self._failed_decision(
                "E_LOGIC", f"E_LOGIC_CALCULATION_UNAVAILABLE_{type(exc).__name__.upper()}")

        try:
            f_story = brief_story.build_brief(
                h1, asset="btcusd", style="f", candle_basis=frames["1h"]["candle_basis"],
                timeframe="1h", local_date=str(snapshot["trade_date_bangkok"]))
            support, resistance = float(f_story["support"]), float(f_story["resistance"])
            atr = float(f_story["atr14"])
            current = float(m15[-1]["close"])
            inside = support <= current <= resistance
            near_lower = abs(current - support) <= 0.5 * atr
            near_upper = abs(current - resistance) <= 0.5 * atr
            ambiguous = near_lower == near_upper
            location = "lower_edge" if near_lower and not near_upper else "upper_edge" if near_upper and not near_lower else "ambiguous" if ambiguous else "middle"
            direction = "up" if location == "lower_edge" else "down"
            side = "buy" if direction == "up" else "sell"
            plan = f_story["trade_plan"][side]
            entry = {"low": float(plan["open"]), "high": float(plan["open"])}
            risk = self._risk(direction, entry, float(plan["sl"]), float(plan["tp"]), current, atr)
            rejection = _rejection(m15, {"low": support, "high": support} if direction == "up"
                                   else {"low": resistance, "high": resistance}, direction)
            evidence = {
                "h_classifier": h_state, "h1_range_valid": support < resistance,
                "price_location": location, "m15_rejection": rejection,
                "ambiguous_edges": ambiguous, "inside_range": inside,
                "setup_id": f"F-{snapshot['snapshot_id'][:12]}", "entry_zone": entry,
                "stop_loss": float(plan["sl"]), "take_profit_1": float(plan["tp"]),
                "evidence_refs": ["snapshot:H1", "snapshot:M30", "snapshot:M15"],
            }
            decisions["F"] = evaluate_candidate("F", evidence=evidence, risk_result=risk)
            decisions["F"]["summary"] = {"bias_h4": bias_h4, "bias_h1": bias_h1,
                                                "m30": h_state,
                                                "m15": "range-edge rejection" if rejection else "unconfirmed",
                                                "invalidation": "ราคาปิดออกนอกกรอบ H1"}
        except Exception as exc:
            decisions["F"] = self._failed_decision("F", f"F_CALCULATION_UNAVAILABLE_{type(exc).__name__.upper()}")

        self._candidate_decisions = [decisions[name] for name in ("J", "I", "E_LOGIC", "F")]
        return deepcopy(self._candidate_decisions)

    def route(
        self, candidate_decisions: list[Mapping[str, Any]], gate_report: Mapping[str, Any],
    ) -> dict[str, Any]:
        # Keep a canonical presentation snapshot alongside the decision.  It
        # is derived from the same gate input and is not part of SelectedPlan,
        # so routing and its hash/schema remain unchanged.
        try:
            self._gate_report = _canonical_gate_context(gate_report)
        except (TypeError, ValueError) as exc:
            raise ConcreteAdapterError("gate report is not canonically serializable") from exc
        routed = strict_route(candidate_decisions, gate_report=gate_report)
        if routed.get("status") == "blocked_retryable":
            return routed
        selection = str(routed["selection"])
        chosen = next((item for item in candidate_decisions if item["candidate"] == selection), None)
        summary = (chosen or {}).get("summary") or {}
        no_trade = selection == "NO_TRADE"
        reasons = list(routed.get("reason_codes", []))
        news_status = ((gate_report.get("news") or {}).get("status")
                       if isinstance(gate_report.get("news"), Mapping) else gate_report.get("news"))
        plan = {
            "schema_version": "fplus-selected-plan-v1", "selection": selection,
            "snapshot_id": str((self._snapshot or {}).get("snapshot_id", "")),
            "cutoff_at_utc": str((self._snapshot or {}).get("cutoff_at_utc", "")),
            "trade_date_bangkok": str((self._snapshot or {}).get("trade_date_bangkok", "")),
            "direction": "neutral" if no_trade else str(routed["direction"]),
            "bias_h4": ("ยังไม่มีทิศที่สอดคล้องกัน" if no_trade
                        else _direction_text(str(summary.get("bias_h4", "neutral")))),
            "setup_h1": ("ยังไม่มีแผนที่ผ่านเกณฑ์" if no_trade
                         else f"ชุดเงื่อนไข {selection} ผ่านตามลำดับของ Router"),
            "evidence_m30": ("หลักฐานอยู่ในช่วงเปลี่ยนผ่าน" if no_trade
                             else str(summary.get("m30", "ผ่านเกณฑ์"))),
            "trigger_m15": ("รอแท่งปิดยืนยันใหม่" if no_trade
                            else str(summary.get("m15", "แท่งปิดยืนยันแล้ว"))),
            "entry_zone": None if no_trade else routed.get("entry_zone"),
            "stop_loss": None if no_trade else routed.get("stop_loss"),
            "take_profit_1": None if no_trade else routed.get("take_profit_1"),
            "rr": None if no_trade else routed.get("rr"),
            "invalidation": ("ประเมินใหม่เมื่อข้อมูลแท่งปิดชุดถัดไปพร้อม" if no_trade
                             else str(summary.get("invalidation", "ยกเลิกเมื่อโครงสร้างเสีย"))),
            "news_notice": ("อยู่ในช่วงงดเทรดรอบข่าว USD ระดับสูง" if news_status == "blackout"
                            else "ปฏิทินข่าวยังยืนยันไม่ได้" if news_status == "unproven"
                            else "ไม่มีข่าว USD ระดับสูงในช่วงงดเทรด"),
            "reason_codes": reasons,
            "source_candidate_id": None if no_trade else routed.get("source_candidate_id"),
        }
        self._selected_plan = SelectedPlan.from_dict(plan).to_dict()
        return deepcopy(self._selected_plan)

    def _internal_root(self, request: Mapping[str, Any]) -> Path:
        return (Path(str(request["work_root"])) / "build" / str(request["run_id"])
                / "btcusd" / "internal" / "fplus")

    def stage_artifacts(
        self, selected_plan: Mapping[str, Any], request: Mapping[str, Any],
        config: Mapping[str, Any],
    ) -> dict[str, Any]:
        internal = self._internal_root(request)
        stage = internal / "artifact-stage"
        if stage.exists():
            raise ConcreteAdapterError("immutable artifact stage already exists")
        stage.mkdir(parents=True)
        gate_context = self._gate_report or {
            "data": deepcopy(self._data_report or {}),
            "news": deepcopy(self._news_report or {}),
        }
        (stage / "btcusd.md").write_text(
            render_markdown(
                selected_plan,
                candidate_decisions=deepcopy(self._candidate_decisions),
                gate_report=deepcopy(gate_context),
            ),
            encoding="utf-8",
        )
        image_name = f"btcusd-fplus-{selected_plan['trade_date_bangkok']}.webp"
        render_webp(
            selected_plan, self._snapshot or {}, stage / image_name,
            candidate_decisions=deepcopy(self._candidate_decisions),
            gate_report=deepcopy(gate_context),
        )
        manifest = validate_artifact_set(
            stage, selected_plan, image_max_bytes=int(config["artifact"]["image_max_bytes"]))
        manifest |= {"run_id": request["run_id"],
                     "generation": int(self._acquired.get("generation", 1)),
                     "shadow_id": request.get("shadow_id")}
        _atomic_json(internal / "input-manifest.json", {
            "snapshot_id": (self._snapshot or {}).get("snapshot_id"),
            "cutoff_at_utc": request["decision_cutoff_utc"],
            "config_fingerprint": request["config_fingerprint"],
            "risk_fingerprint": self.risk_contract["sha256"],
            "series": {name: {
                "rows_sha256": frame["rows_sha256"], "row_count": frame["row_count"],
                "latest_bar_close_at_utc": frame["latest_bar_close_at_utc"],
            } for name, frame in (self._snapshot or {}).get("series", {}).items()},
        })
        _atomic_json(internal / "gate-report.json", {
            "data": self._data_report or {}, "news": self._news_report or {}})
        _atomic_json(internal / "candidate-decisions.json", {
            "candidate_order": ["J", "I", "E_LOGIC", "F"],
            "decisions": self._candidate_decisions})
        _atomic_json(internal / "selected-plan.json", dict(selected_plan))
        _atomic_json(internal / "artifact-manifest.json", manifest)
        return {"staging_dir": str(stage), "manifest": manifest, "internal_dir": str(internal)}

    def promote(
        self, staged: Mapping[str, Any], request: Mapping[str, Any],
        config: Mapping[str, Any],
    ) -> dict[str, Any]:
        transaction = ArtifactTransaction(
            work_root=request["work_root"], output_root=request["output_root"])
        relative = self._relative_final(request, config)
        result = transaction.commit(
            staged["staging_dir"], relative_final_dir=relative,
            manifest=staged["manifest"], force=request.get("generation_request") == "force")
        self._transaction = {**result, "relative_final_dir": str(relative)}
        final = Path(result["final_dir"])
        hashes = {item["name"]: item["sha256"] for item in staged["manifest"]["files"]}
        paths = [str(final / item["name"]) for item in staged["manifest"]["files"]]
        return {"paths": paths, "hashes": hashes, "transaction_journal": result["transaction_journal"]}

    def commit_production(
        self, request: Mapping[str, Any], promoted: Mapping[str, Any],
        selected_plan: Mapping[str, Any],
    ) -> dict[str, Any]:
        record = self._production_store(request).commit(
            key=self._production_key(request), run_id=str(request["run_id"]), now_utc=_now(),
            artifact_hashes=promoted["hashes"])
        if self._transaction:
            ArtifactTransaction(
                work_root=request["work_root"], output_root=request["output_root"]
            ).mark_lock_committed(relative_final_dir=self._transaction["relative_final_dir"])
        return {**record, "selection": selected_plan["selection"],
                "paths": list(promoted.get("paths", []))}

    def mark_retryable(
        self, request: Mapping[str, Any], gate_report: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._production_store(request).mark_retryable(
            key=self._production_key(request), run_id=str(request["run_id"]),
            status="blocked_retryable", reason_codes=list(gate_report.get("reason_codes", [])),
            now_utc=_now())

    def record_shadow(
        self, request: Mapping[str, Any], selected_plan: Mapping[str, Any],
        staged: Mapping[str, Any],
    ) -> dict[str, Any]:
        shadow_id = str(request["shadow_id"])
        internal = Path(str(staged["internal_dir"]))
        if not self._snapshot:
            raise ConcreteAdapterError("shadow replay requires the normalized market snapshot")
        snapshot_path = internal / "normalized-market-snapshot.json"
        snapshot_bytes = _write_immutable_canonical_json(snapshot_path, self._snapshot)
        persisted_snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        snapshot_hash = sha256_canonical(persisted_snapshot)

        build_replay = getattr(self, "build_replay_adapter", None)
        if not callable(build_replay):
            raise ConcreteAdapterError("runtime does not provide an offline replay adapter")
        replay_adapter = build_replay(snapshot_path)
        replay_data = replay_adapter.evaluate_data(persisted_snapshot, self.config)
        replay_news = replay_adapter.evaluate_news(
            persisted_snapshot, request, self.config)
        replay_candidates = replay_adapter.evaluate_candidates(
            persisted_snapshot, self.config)
        replay_gate = dict(replay_data)
        replay_gate["news"] = dict(replay_news)
        replay_reasons = list(replay_data.get("reason_codes", []))
        replay_reasons.extend(replay_news.get("reason_codes", []))
        replay_gate["reason_codes"] = list(dict.fromkeys(replay_reasons))
        replay_plan = replay_adapter.route(replay_candidates, replay_gate)

        original_candidate_hash = sha256_canonical(self._candidate_decisions)
        replay_candidate_hash = sha256_canonical(replay_candidates)
        original_selected_hash = sha256_canonical(dict(selected_plan))
        replay_selected_hash = sha256_canonical(dict(replay_plan))
        candidate_deterministic = original_candidate_hash == replay_candidate_hash
        selected_deterministic = original_selected_hash == replay_selected_hash
        decision_deterministic = candidate_deterministic and selected_deterministic

        replay = internal / "offline-replay"
        replay.mkdir()
        replay_gate_context = getattr(replay_adapter, "_gate_report", None) or replay_gate
        (replay / "btcusd.md").write_text(
            render_markdown(
                replay_plan,
                candidate_decisions=deepcopy(replay_candidates),
                gate_report=deepcopy(replay_gate_context),
            ),
            encoding="utf-8",
        )
        image_name = f"btcusd-fplus-{replay_plan['trade_date_bangkok']}.webp"
        render_webp(
            replay_plan, persisted_snapshot, replay / image_name,
            candidate_decisions=deepcopy(replay_candidates),
            gate_report=deepcopy(replay_gate_context),
        )
        replay_manifest = validate_artifact_set(
            replay, replay_plan,
            image_max_bytes=int(self.config["artifact"]["image_max_bytes"]))
        original_artifact_hash = str(staged["manifest"]["artifact_set_sha256"])
        replay_artifact_hash = str(replay_manifest["artifact_set_sha256"])
        artifact_deterministic = original_artifact_hash == replay_artifact_hash
        snapshot_immutable = snapshot_path.read_bytes() == snapshot_bytes
        deterministic = (decision_deterministic and artifact_deterministic
                         and snapshot_immutable)
        reason_codes: list[str] = []
        if not candidate_deterministic:
            reason_codes.append("REPLAY_CANDIDATE_MISMATCH")
        if not selected_deterministic:
            reason_codes.append("REPLAY_SELECTED_PLAN_MISMATCH")
        if not artifact_deterministic:
            reason_codes.append("REPLAY_ARTIFACT_MISMATCH")
        if not snapshot_immutable:
            reason_codes.append("REPLAY_SNAPSHOT_MUTATED")
        status = "shadow_pass" if deterministic else "shadow_fail"
        audit = {
            "status": status,
            "shadow_id": shadow_id, "run_id": request["run_id"],
            "trade_date_bangkok": request["trade_date_bangkok"],
            "snapshot_id": (self._snapshot or {}).get("snapshot_id"),
            "selection": selected_plan["selection"],
            "risk_policy_fingerprint": self.risk_contract["sha256"],
            "reason_codes": reason_codes,
            "replay": {
                "deterministic": deterministic,
                "decision_path": [
                    "evaluate_data", "evaluate_news", "evaluate_candidates", "route"],
                "snapshot_sha256": snapshot_hash,
                "decision_replay_deterministic": decision_deterministic,
                "artifact_replay_deterministic": artifact_deterministic,
                "original_candidate_decisions_sha256": original_candidate_hash,
                "replay_candidate_decisions_sha256": replay_candidate_hash,
                "original_selected_plan_sha256": original_selected_hash,
                "replay_selected_plan_sha256": replay_selected_hash,
                "original_artifact_set_sha256": original_artifact_hash,
                "replay_artifact_set_sha256": replay_artifact_hash,
                # Backward-compatible SHD baseline aliases.
                "selected_plan_sha256": original_selected_hash,
                "artifact_set_sha256": original_artifact_hash,
            },
            "promoted": False, "production_lock_used": False,
        }
        report_path = internal / "shadow-report.json"
        _atomic_json(report_path, audit)
        recorded = self._shadow_store(request).record_shadow(
            key=self._shadow_key(request), run_id=str(request["run_id"]),
            shadow_id=shadow_id, now_utc=_now(), audit=audit, status=status)
        record_path = (Path(str(request["state_root"])) / "fplus" / "btcusd" / "shadow"
                       / str(request["trade_date_bangkok"]) / f"{shadow_id}.json")
        return {
            "status": status, "selection": selected_plan["selection"],
            "shadow_id": shadow_id, "run_id": request["run_id"],
            "shadow_report_path": str(report_path),
            "shadow_record_path": str(record_path),
            "staging_dir": str(staged["staging_dir"]),
            "hashes": {item["name"]: item["sha256"] for item in staged["manifest"]["files"]},
            "audit": recorded.get("audit", audit),
        }
