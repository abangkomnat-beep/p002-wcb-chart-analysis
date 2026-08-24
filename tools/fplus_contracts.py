"""Core immutable contracts for the BTCUSD F+ manual pipeline."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from typing import Any, Mapping


class ContractError(ValueError):
    """Raised when an F+ value crosses a locked contract boundary."""


FORBIDDEN_SCHEDULE_FIELDS = {
    "schedule", "cron", "run_at", "interval", "watch", "daemon", "repeat"
}


def canonical_json(value: Any) -> str:
    """Serialize JSON deterministically for fingerprints and replay."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_canonical(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _parse_utc(value: str, field: str) -> datetime:
    if not isinstance(value, str):
        raise ContractError(f"{field} must be an ISO-8601 UTC string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{field} must be valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{field} must include a UTC offset")
    return parsed


@dataclass(frozen=True)
class FPlusRunRequest:
    schema_version: str
    run_id: str
    asset: str
    mode: str
    requested_at_utc: str
    decision_cutoff_utc: str
    trade_date_bangkok: str
    generation_request: str
    force_reason: str | None
    work_root: str
    output_root: str
    state_root: str
    config_fingerprint: str
    shadow_id: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FPlusRunRequest":
        if not isinstance(payload, Mapping):
            raise ContractError("run request must be a mapping")
        forbidden = FORBIDDEN_SCHEDULE_FIELDS.intersection(payload)
        if forbidden:
            raise ContractError(
                f"manual-only request rejects schedule field: {sorted(forbidden)[0]}"
            )
        expected = set(cls.__dataclass_fields__)
        optional = {"shadow_id"}
        missing = expected.difference(optional).difference(payload)
        extra = set(payload).difference(expected)
        if missing or extra:
            raise ContractError(
                f"run request fields invalid; missing={sorted(missing)}, extra={sorted(extra)}"
            )
        values = dict(payload)
        values.setdefault("shadow_id", None)
        if values["schema_version"] != "fplus-run-request-v1":
            raise ContractError("unsupported run request schema_version")
        if str(values["asset"]).lower() != "btcusd":
            raise ContractError("asset must be btcusd")
        values["asset"] = "btcusd"
        if values["mode"] not in {"shadow", "local"}:
            raise ContractError("mode must be shadow or local")
        shadow_id = values["shadow_id"]
        if values["mode"] == "shadow" and shadow_id not in {"S01", "S02", "S03"}:
            raise ContractError("shadow mode requires shadow_id S01, S02 or S03")
        if values["mode"] == "local" and shadow_id is not None:
            raise ContractError("local mode requires shadow_id null/None")
        if values["generation_request"] not in {"normal", "force"}:
            raise ContractError("generation_request must be normal or force")
        if values["generation_request"] == "force":
            if values["mode"] != "local":
                raise ContractError("force is available in local mode only")
            if not isinstance(values["force_reason"], str) or not values["force_reason"].strip():
                raise ContractError("force requires a non-blank audit reason")
            values["force_reason"] = values["force_reason"].strip()
        elif values["force_reason"] not in {None, ""}:
            raise ContractError("force_reason is valid only for a force request")
        _parse_utc(values["requested_at_utc"], "requested_at_utc")
        _parse_utc(values["decision_cutoff_utc"], "decision_cutoff_utc")
        try:
            datetime.strptime(values["trade_date_bangkok"], "%Y-%m-%d")
        except (TypeError, ValueError) as exc:
            raise ContractError("trade_date_bangkok must be YYYY-MM-DD") from exc
        fingerprint = values["config_fingerprint"]
        if not isinstance(fingerprint, str) or len(fingerprint) != 64:
            raise ContractError("config_fingerprint must be SHA-256")
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelectedPlan:
    schema_version: str
    selection: str
    snapshot_id: str
    cutoff_at_utc: str
    trade_date_bangkok: str
    direction: str
    bias_h4: str
    setup_h1: str
    evidence_m30: str
    trigger_m15: str
    entry_zone: dict[str, float] | None
    stop_loss: float | None
    take_profit_1: float | None
    rr: float | None
    invalidation: str
    news_notice: str
    reason_codes: list[str]
    source_candidate_id: str | None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SelectedPlan":
        if not isinstance(payload, Mapping):
            raise ContractError("selected plan must be a mapping")
        expected = set(cls.__dataclass_fields__)
        missing = expected.difference(payload)
        extra = set(payload).difference(expected)
        if missing or extra:
            raise ContractError(
                f"selected plan fields invalid; missing={sorted(missing)}, extra={sorted(extra)}"
            )
        values = dict(payload)
        if values["schema_version"] != "fplus-selected-plan-v1":
            raise ContractError("unsupported selected plan schema_version")
        if values["selection"] not in {"J", "I", "E_LOGIC", "F", "NO_TRADE"}:
            raise ContractError("selection is not an F+ candidate")
        if values["direction"] not in {"long", "short", "neutral"}:
            raise ContractError("direction must be long, short or neutral")
        _parse_utc(values["cutoff_at_utc"], "cutoff_at_utc")
        if values["selection"] == "NO_TRADE":
            trade_fields = ("entry_zone", "stop_loss", "take_profit_1", "rr")
            if values["direction"] != "neutral" or any(values[name] is not None for name in trade_fields):
                raise ContractError("NO_TRADE forbids direction and trade/stop/target numbers")
            if values["source_candidate_id"] is not None:
                raise ContractError("NO_TRADE cannot identify a source candidate")
        else:
            if values["direction"] not in {"long", "short"}:
                raise ContractError("trade plan requires long or short direction")
            if any(values[name] is None for name in ("entry_zone", "stop_loss", "take_profit_1", "rr")):
                raise ContractError("trade plan requires entry, stop, target and RR")
            zone = values["entry_zone"]
            if not isinstance(zone, Mapping) or set(zone) != {"low", "high"}:
                raise ContractError("entry_zone requires low and high")
            if float(zone["low"]) > float(zone["high"]):
                raise ContractError("entry_zone low must not exceed high")
            values["entry_zone"] = {"low": float(zone["low"]), "high": float(zone["high"])}
        values["reason_codes"] = list(values["reason_codes"])
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
