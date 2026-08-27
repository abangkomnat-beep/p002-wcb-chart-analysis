"""Pure, offline evaluator for BTCUSD E+ Daily Conditional DC-T/v1.

This module deliberately owns only the additive conditional watch contract.
It accepts explicit closed rows and an explicit strict-story projection; it
does not fetch data, write files, schedule work, or reimplement B100.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone

from tools import intraday_indicators


SESSION_TIMEZONE = "Asia/Bangkok"
BANGKOK = timezone(timedelta(hours=7))
UTC = timezone.utc
ASSET = "btcusd"
H1 = "1h"
M15 = "15min"
MIN_ROWS = 240
DONCHIAN_LENGTH = 20
BUFFER_ATR = 0.25
SCHEMA = "style-e-plus-daily-conditional/v1"
STORY_SCHEMA = "style-e-plus-story/v5"
SOURCE_SNAPSHOT_SCHEMA = "style-e-plus-source-snapshot/v3"
MANIFEST_SCHEMA = "style-e-plus-manifest/v5"
CONTRACT_VERSION = "DC-T/v1"

FORBIDDEN = {
    "entry", "entry_zone", "stop", "sl", "tp", "risk", "sizing",
    "quantity", "order", "fill", "position", "protective_stop", "execution",
}

CONDITIONAL_KEYS = {
    "schema", "role", "contract", "status", "session_timezone",
    "session_cutoff", "effective_from", "expires_at", "creation_basis",
    "watch_geometry", "legs", "selected_side", "trigger_bar_at",
    "strict_projection_hash", "strict_plan_ref", "manual_only",
    "execution_enabled", "sha256",
}
WATCH_KEYS = {"donchian_length", "watch_buffer_h1_atr", "buy_watch", "sell_watch"}
LEG_KEYS = {"side", "status", "trigger_rule"}
REF_KEYS = {"session_id", "evaluation_cutoff", "strict_plan_sha256"}
CONDITIONAL_STATUSES = {
    "NOT_REQUIRED_STRICT_AVAILABLE", "ARMED", "WATCH_TRIGGERED_WAIT_REVALIDATION",
    "READY_AFTER_STRICT_REVALIDATION", "INVALIDATED", "EXPIRED", "STALE_DATA",
}
LEG_STATUSES = {"ARMED", "TRIGGERED_WAIT_REVALIDATION", "CANCELLED_BY_OPPOSITE_TRIGGER",
                "READY_AFTER_STRICT_REVALIDATION"}


class ContractError(ValueError):
    """The supplied artifact or rows violate the DC-T contract."""


class StaleData(ContractError):
    """Rows or candle basis cannot prove an eligible closed prefix."""


class NoValidPriorSession(ContractError):
    """Creation was requested before 08:00 without a reusable prior artifact."""


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def creation_hash(creation: dict) -> str:
    """Return the immutable creation identity without persisting it."""
    return _digest(creation)


def evaluation_key(creation: dict, *, evaluated_at: datetime | str,
                   observed_prefix_hash: str) -> str:
    """Return the deterministic derived-artifact key for external storage.

    Storage is intentionally deferred at this pure boundary; callers may use
    this key with an exclusive-create store without introducing mutable state.
    """
    payload = {
        "creation_hash": creation_hash(creation),
        "evaluation_cutoff": _iso(evaluated_at),
        "observed_prefix_hash": str(observed_prefix_hash),
        "contract_version": CONTRACT_VERSION,
    }
    return _digest(payload)


def _safe_rows_digest(value) -> str:
    """Hash malformed fixture rows without allowing NaN/Infinity to escape."""
    try:
        return _digest(value)
    except (TypeError, ValueError):
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":"), allow_nan=True).encode("utf-8")).hexdigest()


def _parse(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ContractError(f"timestamp ไม่ถูกต้อง: {value}") from exc
    if parsed.tzinfo is None:
        raise ContractError(f"timestamp ต้องมี timezone: {value}")
    return parsed.astimezone(UTC)


def _bangkok(value: datetime | str) -> datetime:
    return _parse(value).astimezone(BANGKOK)


def _session_cutoff(value: datetime | str) -> datetime:
    parsed = _parse(value)
    local = parsed.astimezone(BANGKOK)
    if (local.hour, local.minute, local.second, local.microsecond) != (8, 0, 0, 0):
        raise ContractError("session_cutoff ต้องเป็น 08:00 Asia/Bangkok")
    return parsed


def _iso(value: datetime | str) -> str:
    return _bangkok(value).isoformat(timespec="seconds")


def _utc_iso(value: datetime | str) -> str:
    return _parse(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _number(value, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{label}: ไม่ใช่ตัวเลข") from exc
    if not math.isfinite(result):
        raise ContractError(f"{label}: ต้องเป็น finite number")
    return result


def _interval(timeframe: str) -> timedelta:
    if timeframe == H1:
        return timedelta(hours=1)
    if timeframe == M15:
        return timedelta(minutes=15)
    raise ContractError(f"ไม่รองรับ timeframe: {timeframe}")


def _validate_basis(basis: dict, timeframe: str) -> None:
    if not isinstance(basis, dict):
        raise StaleData(f"{timeframe}: ขาด source/candle basis")
    if basis.get("asset") != ASSET or basis.get("timeframe") != timeframe:
        raise StaleData(f"{timeframe}: source/candle basis ไม่ตรง asset/timeframe")
    if basis.get("candle_state") != "closed":
        raise StaleData(f"{timeframe}: basis ไม่ยืนยัน closed")
    for key in ("basis_bar_at", "basis_close_at"):
        try:
            _parse(basis[key])
        except (KeyError, ContractError) as exc:
            raise StaleData(f"{timeframe}: basis ขาด {key}") from exc
    if basis.get("source") in {None, ""}:
        raise StaleData(f"{timeframe}: basis ขาด source")


def _validate_basis_rows(basis: dict, rows: list[tuple[datetime, dict]], timeframe: str) -> None:
    _validate_basis(basis, timeframe)
    if not rows:
        raise StaleData(f"{timeframe}: ไม่มี closed prefix ให้ผูก basis")
    bar_at, row = rows[-1]
    expected_bar = _parse(basis["basis_bar_at"])
    expected_close = _parse(basis["basis_close_at"])
    actual_close = _row_close_at(bar_at, row, timeframe)
    if bar_at != expected_bar or actual_close != expected_close:
        raise StaleData(f"{timeframe}: basis ไม่ตรง closed prefix row")


def _validate_rows(rows: list[dict], timeframe: str, *, cutoff: datetime | None = None,
                   reject_after_cutoff: bool = False,
                   allow_last_geometry: bool = False) -> list[dict]:
    if not isinstance(rows, list) or len(rows) < MIN_ROWS:
        raise StaleData(f"{timeframe}: ต้องมี closed rows อย่างน้อย {MIN_ROWS}")
    step = _interval(timeframe)
    previous = None
    previous_close = None
    parsed_rows = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise StaleData(f"{timeframe}[{index}]: row ไม่ใช่ object")
        try:
            at = _parse(row["at"])
        except (KeyError, ContractError) as exc:
            raise StaleData(f"{timeframe}[{index}]: timestamp ใช้งานไม่ได้") from exc
        if previous is not None:
            if at <= previous:
                raise StaleData(f"{timeframe}[{index}]: timestamp ไม่ ascending/unique")
            if at - previous != step:
                raise StaleData(f"{timeframe}[{index}]: timestamp มี gap")
        previous = at
        try:
            close_at = _row_close_at(at, row, timeframe)
        except ContractError as exc:
            raise StaleData(f"{timeframe}[{index}]: close_at ใช้งานไม่ได้") from exc
        if previous_close is not None:
            if close_at <= previous_close or close_at - previous_close != step:
                raise StaleData(f"{timeframe}[{index}]: close_at ไม่ต่อเนื่อง")
        previous_close = close_at
        if row.get("forming") or row.get("candle_state") not in {None, "closed"}:
            raise StaleData(f"{timeframe}[{index}]: ยัง forming")
        try:
            opened = _number(row.get("open"), f"{timeframe}[{index}].open")
            high = _number(row.get("high"), f"{timeframe}[{index}].high")
            low = _number(row.get("low"), f"{timeframe}[{index}].low")
            closed = _number(row.get("close"), f"{timeframe}[{index}].close")
        except ContractError as exc:
            raise StaleData(str(exc)) from exc
        malformed_geometry = high < max(opened, closed) or low > min(opened, closed) or high < low
        if malformed_geometry:
            if index == len(rows) - 1:
                raise StaleData(f"{timeframe}[{index}]: OHLC geometry ไม่ถูกต้อง")
            raise StaleData(f"{timeframe}[{index}]: OHLC geometry ไม่ถูกต้อง")
        if cutoff is not None and at > cutoff:
            if reject_after_cutoff:
                raise StaleData(f"{timeframe}[{index}]: row อยู่หลัง session cutoff")
        parsed_rows.append((at, row))
    return parsed_rows


def _row_close_at(at: datetime, row: dict, timeframe: str) -> datetime:
    """Resolve close_at explicitly, with legacy fixture ``at`` as bar-open time."""
    if row.get("close_at") is not None:
        close_at = _parse(row["close_at"])
        if close_at != at + _interval(timeframe):
            raise ContractError(f"{timeframe}: close_at ต้องตรง at + timeframe interval")
        return close_at
    return at + _interval(timeframe)


def _strict_projection(strict_story: dict) -> dict:
    adaptive_context = strict_story.get("adaptive_context") or {}
    context_sha = adaptive_context.get("sha256")
    if context_sha is None:
        context_sha = strict_story.get("adaptive_context_sha256")
    return {
        "state": strict_story.get("state"),
        "side": strict_story.get("side"),
        "plan": copy.deepcopy(strict_story.get("plan")),
        "adaptive_reason_code": strict_story.get("adaptive_reason_code"),
        "adaptive_stop": copy.deepcopy(strict_story.get("adaptive_stop")),
        "adaptive_context_sha256": context_sha,
        "lifecycle": copy.deepcopy(strict_story.get("lifecycle")),
    }


def _strict_hash(strict_story: dict) -> str:
    return _digest(_strict_projection(strict_story))


def _donchian(h1_rows: list[tuple[datetime, dict]]) -> tuple[float, float, float]:
    # The latest closed row is the session anchor; the preceding 20 bars define
    # the watch, matching the production Donchian signal-bar exclusion.
    decision = h1_rows[-21:-1] if len(h1_rows) >= 21 else h1_rows[:-1]
    if len(decision) < DONCHIAN_LENGTH:
        raise StaleData("H1: ไม่พอสำหรับ Donchian20")
    decision = decision[-DONCHIAN_LENGTH:]
    upper = max(_number(row.get("high"), "H1.high") for _, row in decision)
    lower = min(_number(row.get("low"), "H1.low") for _, row in decision)
    production_rows = [row for _, row in h1_rows]
    atr_result = intraday_indicators.atr(production_rows, length=14)
    atr = _number(atr_result.get("value"), "H1.ATR14")
    if not math.isfinite(atr) or atr <= 0:
        raise StaleData("H1: ATR ไม่พร้อมใช้งาน")
    return upper, lower, atr


def _fmt(value: float) -> str:
    return f"{float(value):.2f}"


def _base_conditional(*, strict_story: dict, cutoff: datetime, expiry: datetime,
                      h1_rows: list[tuple[datetime, dict]], m15_rows: list[tuple[datetime, dict]],
                      h1_basis: dict, m15_basis: dict) -> dict:
    upper, lower, atr = _donchian(h1_rows)
    strict_available = _strict_is_available(strict_story)
    watch = {
        "donchian_length": DONCHIAN_LENGTH,
        "watch_buffer_h1_atr": BUFFER_ATR,
        "buy_watch": _fmt(upper + BUFFER_ATR * atr),
        "sell_watch": _fmt(lower - BUFFER_ATR * atr),
    }
    if strict_available:
        status = "NOT_REQUIRED_STRICT_AVAILABLE"
        legs = []
    else:
        status = "ARMED"
        legs = [
            {"side": "buy", "status": "ARMED",
             "trigger_rule": "m15_close_strictly_above_buy_watch"},
            {"side": "sell", "status": "ARMED",
             "trigger_rule": "m15_close_strictly_below_sell_watch"},
        ]
    conditional = {
        "schema": SCHEMA,
        "role": "secondary_additive",
        "contract": CONTRACT_VERSION,
        "session_timezone": SESSION_TIMEZONE,
        "session_cutoff": cutoff.astimezone(BANGKOK).isoformat(timespec="seconds"),
        "effective_from": cutoff.astimezone(BANGKOK).isoformat(timespec="seconds"),
        "expires_at": expiry.astimezone(BANGKOK).isoformat(timespec="seconds"),
        "watch_geometry": watch,
        "status": status,
        "selected_side": None,
        "trigger_bar_at": None,
        "legs": legs,
        "strict_projection_hash": _strict_hash(strict_story),
        "strict_plan_ref": None,
        "manual_only": True,
        "execution_enabled": False,
        "creation_basis": {
            "h1_bar_at": _utc_iso(h1_rows[-1][0]),
            "m15_bar_at": _utc_iso(m15_rows[-1][0]),
        },
    }
    conditional["sha256"] = _digest(conditional)
    return conditional


def _strict_is_available(strict_story: dict) -> bool:
    return (strict_story.get("state") in {"WAIT_TRIGGER", "ENTRY_READY"} and
            isinstance(strict_story.get("plan"), dict) and
            strict_story["plan"].get("variant") == "B")


def _story_payload(strict_story: dict, conditional: dict) -> dict:
    # Writer consumes this small additive envelope; strict v4/v5 truth remains
    # at the caller boundary and is never copied into daily_conditional.
    projection = _strict_projection(strict_story)
    result = {
        "schema": STORY_SCHEMA,
        "asset": ASSET,
        "timeframe": "1h/15min",
        "state": strict_story.get("state"),
        "side": strict_story.get("side"),
        "bias_reason": "Strict B100 state คงเดิม",
        "decision_reason": "Daily Conditional เป็น watch ไม่ใช่จุดเข้า",
        "daily_conditional": copy.deepcopy(conditional),
    }
    for key in ("plan", "adaptive_reason_code", "adaptive_stop", "adaptive_context", "lifecycle"):
        if key in strict_story:
            result[key] = copy.deepcopy(strict_story[key])
    result["strict_projection_oracle"] = {
        "projection": projection,
        "sha256": _digest(projection),
    }
    result["watch_geometry_oracle"] = {
        "geometry": copy.deepcopy(conditional.get("watch_geometry")),
        "sha256": _digest(conditional.get("watch_geometry")),
    }
    result["session_id"] = "dc-" + _parse(conditional["session_cutoff"]).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return result


def _envelope(strict_story: dict, conditional: dict, *, h1_rows: list[dict], m15_rows: list[dict],
              h1_basis: dict, m15_basis: dict, h1_cutoff_close=None) -> dict:
    result = {key: copy.deepcopy(strict_story.get(key)) for key in (
        "state", "side", "plan", "adaptive_reason_code", "adaptive_stop",
        "adaptive_context", "lifecycle") if key in strict_story}
    result["session_id"] = "dc-" + _parse(conditional["session_cutoff"]).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    projection = _strict_projection(strict_story)
    result["strict_projection_oracle"] = {
        "projection": projection,
        "sha256": _digest(projection),
    }
    result["watch_geometry_oracle"] = {
        "geometry": copy.deepcopy(conditional.get("watch_geometry")),
        "sha256": _digest(conditional.get("watch_geometry")),
    }
    result["daily_conditional"] = conditional
    result["source_snapshot"] = {
        "schema": SOURCE_SNAPSHOT_SCHEMA,
        "asset": ASSET,
        "h1_basis": copy.deepcopy(h1_basis),
        "m15_basis": copy.deepcopy(m15_basis),
        "h1_rows_sha256": _safe_rows_digest(h1_rows),
        "m15_rows_sha256": _safe_rows_digest(m15_rows),
        "h1_cutoff_close": h1_cutoff_close,
        "geometry_sha256": result["watch_geometry_oracle"]["sha256"],
    }
    result["manifest"] = {
        "schema": MANIFEST_SCHEMA,
        "story_schema": STORY_SCHEMA,
        "source_snapshot_schema": SOURCE_SNAPSHOT_SCHEMA,
        "strict_projection_sha256": conditional["strict_projection_hash"],
        "conditional_sha256": conditional["sha256"],
        "source_snapshot_sha256": _digest(result["source_snapshot"]),
        "contract_version": CONTRACT_VERSION,
    }
    result["story"] = _story_payload(strict_story, conditional)
    result["story"]["source_snapshot"] = copy.deepcopy(result["source_snapshot"])
    result["story"]["manifest"] = copy.deepcopy(result["manifest"])
    return result


def create(*, strict_story: dict, h1_rows: list[dict], m15_rows: list[dict],
           session_cutoff: datetime, now: datetime, h1_basis: dict, m15_basis: dict,
           prior_artifact: dict | None = None, **_) -> dict:
    cutoff = _session_cutoff(session_cutoff)
    moment = _parse(now)
    if moment < cutoff:
        if prior_artifact is not None:
            try:
                if not isinstance(prior_artifact, dict) or "evaluation_cutoff" in prior_artifact:
                    raise ContractError("prior artifact ไม่ใช่ immutable creation")
                validate(prior_artifact,
                         strict_story=_strict_from_artifact(prior_artifact), now=moment)
                prior_expiry = _parse(_extract(prior_artifact)["expires_at"])
                if moment >= prior_expiry:
                    raise ContractError("prior artifact หมดอายุแล้ว")
            except (ContractError, TypeError, ValueError) as exc:
                raise NoValidPriorSession("prior artifact ไม่ผ่าน schema/hash/expiry validation") from exc
            return copy.deepcopy(prior_artifact)
        raise NoValidPriorSession("ยังไม่ถึง 08:00 และไม่มี prior valid session")
    _validate_basis(h1_basis, H1)
    _validate_basis(m15_basis, M15)
    # A late call is still the same 08:00 session.  Post-cutoff rows are not
    # allowed to influence its geometry, but a malformed post-cutoff prefix is
    # harmless because it is outside the immutable creation basis.
    try:
        h1_valid = _validate_rows(h1_rows, H1, cutoff=cutoff)
        m15_valid = _validate_rows(m15_rows, M15, cutoff=cutoff)
        h1_valid = [item for item in h1_valid
                    if _row_close_at(item[0], item[1], H1) <= cutoff]
        m15_valid = [item for item in m15_valid
                     if _row_close_at(item[0], item[1], M15) <= cutoff]
        if len(h1_valid) < MIN_ROWS or len(m15_valid) < MIN_ROWS:
            raise StaleData("closed prefix ก่อน cutoff ไม่พอ")
        _validate_basis_rows(h1_basis, h1_valid, H1)
        _validate_basis_rows(m15_basis, m15_valid, M15)
        conditional = _base_conditional(strict_story=strict_story, cutoff=cutoff,
                                         expiry=cutoff + timedelta(days=1),
                                         h1_rows=h1_valid, m15_rows=m15_valid,
                                         h1_basis=h1_basis, m15_basis=m15_basis)
    except (StaleData, ContractError):
        # Creation remains a deterministic control artifact with no watch legs.
        conditional = {
            "schema": SCHEMA, "role": "secondary_additive", "contract": CONTRACT_VERSION,
            "session_timezone": SESSION_TIMEZONE,
            "session_cutoff": cutoff.astimezone(BANGKOK).isoformat(timespec="seconds"),
            "effective_from": cutoff.astimezone(BANGKOK).isoformat(timespec="seconds"),
            "expires_at": (cutoff + timedelta(days=1)).astimezone(BANGKOK).isoformat(timespec="seconds"),
            "creation_basis": {"h1_bar_at": None, "m15_bar_at": None},
            "watch_geometry": None, "status": "STALE_DATA", "selected_side": None,
            "trigger_bar_at": None, "legs": [], "strict_projection_hash": _strict_hash(strict_story),
            "strict_plan_ref": None,
            "manual_only": True, "execution_enabled": False,
        }
        conditional["sha256"] = _digest(conditional)
        h1_valid = []
        m15_valid = []
    return _envelope(strict_story, conditional, h1_rows=h1_rows, m15_rows=m15_rows,
                     h1_basis=h1_basis, m15_basis=m15_basis,
                     h1_cutoff_close=(h1_valid[-1][1].get("close") if h1_valid else None))


def _extract(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ContractError("creation ต้องเป็น object")
    conditional = value.get("daily_conditional", value)
    if not isinstance(conditional, dict):
        raise ContractError("daily_conditional ต้องเป็น object")
    return conditional


def _require_creation_artifact(artifact: dict) -> None:
    if not isinstance(artifact, dict) or "evaluation_cutoff" in artifact:
        raise ContractError("รับเฉพาะ immutable creation artifact")
    conditional = artifact.get("daily_conditional", artifact)
    if not isinstance(conditional, dict) or "evaluation_cutoff" in conditional:
        raise ContractError("ห้ามใช้ derived artifact เป็น creation input")


def _assert_safe(value) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN:
                raise ContractError(f"พบ field ต้องห้าม: {key}")
            _assert_safe(child)
    elif isinstance(value, list):
        for child in value:
            _assert_safe(child)


def _validate_state_invariants(conditional: dict) -> None:
    status = conditional["status"]
    selected = conditional["selected_side"]
    trigger = conditional["trigger_bar_at"]
    reference = conditional["strict_plan_ref"]
    legs = conditional["legs"]
    cutoff = _parse(conditional["session_cutoff"])
    expiry = _parse(conditional["expires_at"])
    if selected not in {None, "buy", "sell"}:
        raise ContractError("selected_side ไม่ถูกต้อง")
    if trigger is not None:
        try:
            if _utc_iso(trigger) != str(trigger):
                raise ContractError("trigger_bar_at ต้องเป็น UTC canonical")
            trigger_at = _parse(trigger)
            if not cutoff < trigger_at < expiry:
                raise ContractError("trigger_bar_at อยู่นอก session")
        except ContractError as exc:
            raise ContractError("trigger_bar_at ไม่ถูกต้อง") from exc
    if status in {"NOT_REQUIRED_STRICT_AVAILABLE", "ARMED", "STALE_DATA", "EXPIRED"}:
        if selected is not None or trigger is not None or reference is not None:
            raise ContractError("state นี้ห้ามมี selected/trigger/reference")
    if status == "NOT_REQUIRED_STRICT_AVAILABLE" and legs:
        raise ContractError("strict available ต้องไม่มี legs")
    if status == "ARMED":
        if ({leg["side"] for leg in legs} != {"buy", "sell"} or
                len(legs) != 2 or any(leg["status"] != "ARMED" for leg in legs)):
            raise ContractError("ARMED ต้องมีสอง armed legs")
    if status == "WATCH_TRIGGERED_WAIT_REVALIDATION":
        if selected is None or trigger is None or reference is not None:
            raise ContractError("triggered state ต้องมี selected/trigger และไม่มี ref")
        if ({leg["side"] for leg in legs} != {"buy", "sell"} or
                len(legs) != 2 or sum(leg["status"] == "TRIGGERED_WAIT_REVALIDATION" for leg in legs) != 1):
            raise ContractError("triggered state ต้องมีหนึ่ง triggered leg")
        selected_leg = next((leg for leg in legs if leg["side"] == selected), None)
        other_leg = next((leg for leg in legs if leg["side"] != selected), None)
        if not selected_leg or selected_leg["status"] != "TRIGGERED_WAIT_REVALIDATION" or not other_leg or other_leg["status"] != "CANCELLED_BY_OPPOSITE_TRIGGER":
            raise ContractError("triggered leg/cancellation ไม่สอดคล้อง")
    if status == "READY_AFTER_STRICT_REVALIDATION":
        if selected is None or trigger is None or not isinstance(reference, dict):
            raise ContractError("READY ต้องมี selected/trigger/ref")
        selected_leg = next((leg for leg in legs if leg["side"] == selected), None)
        other_leg = next((leg for leg in legs if leg["side"] != selected), None)
        if ({leg["side"] for leg in legs} != {"buy", "sell"} or
                len(legs) != 2 or not selected_leg or
                selected_leg["status"] != "READY_AFTER_STRICT_REVALIDATION" or
                not other_leg or other_leg["status"] != "CANCELLED_BY_OPPOSITE_TRIGGER"):
            raise ContractError("READY leg/cancellation ไม่สอดคล้อง")
    if status == "INVALIDATED" and (selected is not None or trigger is not None or reference is not None or legs):
        raise ContractError("INVALIDATED ต้องไม่มี active conditional state")


def _validate_geometry(conditional: dict, artifact: dict, *, geometry_oracle: dict | None = None) -> None:
    geometry = conditional.get("watch_geometry")
    if conditional["status"] == "STALE_DATA":
        if geometry is not None:
            raise ContractError("STALE_DATA ต้องไม่มี geometry ที่อ้างใช้ได้")
        return
    if not isinstance(geometry, dict) or set(geometry) != WATCH_KEYS:
        raise ContractError("watch_geometry ไม่ตรง schema")
    if geometry["donchian_length"] != DONCHIAN_LENGTH or geometry["watch_buffer_h1_atr"] != BUFFER_ATR:
        raise ContractError("watch geometry constants ไม่ตรง")
    decimal_pattern = re.compile(r"^-?\d+\.\d{2}$")
    if not all(isinstance(geometry[key], str) and decimal_pattern.fullmatch(geometry[key])
               for key in ("buy_watch", "sell_watch")):
        raise ContractError("watch levels ต้องเป็น canonical fixed-point decimal")
    buy = _number(geometry["buy_watch"], "buy_watch")
    sell = _number(geometry["sell_watch"], "sell_watch")
    if not buy > sell:
        raise ContractError("buy_watch ต้องสูงกว่า sell_watch")
    oracle = geometry_oracle
    if oracle is None and isinstance(artifact, dict):
        oracle = artifact.get("watch_geometry_oracle")
    if oracle is None:
        raise ContractError("watch geometry oracle ไม่พร้อม")
    if (not isinstance(oracle, dict) or set(oracle) != {"geometry", "sha256"} or
            not isinstance(oracle["sha256"], str) or
            re.fullmatch(r"[0-9a-f]{64}", oracle["sha256"]) is None or
            oracle["geometry"] != geometry or _digest(oracle["geometry"]) != oracle["sha256"]):
        raise ContractError("watch geometry oracle ไม่ผูกกับ creation")
    snapshot = artifact.get("source_snapshot") if isinstance(artifact, dict) else None
    if isinstance(snapshot, dict) and snapshot.get("geometry_sha256") != oracle["sha256"]:
        raise ContractError("source snapshot geometry binding ไม่ตรง oracle")
    cutoff_close = snapshot.get("h1_cutoff_close") if isinstance(snapshot, dict) else None
    if cutoff_close is not None:
        cutoff_close = _number(cutoff_close, "h1_cutoff_close")
        if not buy > cutoff_close > sell:
            raise ContractError("watch geometry ต้องคร่อม cutoff close")


def _validate_nested_parity(artifact: dict, conditional: dict) -> None:
    story = artifact.get("story")
    if not isinstance(story, dict) or story.get("_incomplete_fixture") is True:
        raise ContractError("production artifact ห้ามใช้ incomplete fixture marker")
    for key in ("session_id", "daily_conditional", "strict_projection_oracle",
                "watch_geometry_oracle", "source_snapshot", "manifest"):
        if story.get(key) != artifact.get(key):
            raise ContractError(f"nested story parity ไม่ตรง root: {key}")
    if _strict_projection(story) != _strict_projection(_strict_from_artifact(artifact)):
        raise ContractError("nested story strict projection ไม่ตรง root")


def validate(artifact: dict, *, strict_story: dict,
             revalidated_strict_story: dict | None = None,
             geometry_oracle: dict | None = None,
             check_nested_parity: bool = True,
             now: datetime | None = None) -> None:
    if not isinstance(strict_story, dict):
        raise ContractError("strict_story ต้องเป็น object")
    conditional = _extract(artifact)
    _assert_safe(conditional)
    if set(conditional) != CONDITIONAL_KEYS:
        raise ContractError("daily_conditional มี key ขาด/เกิน schema")
    if conditional.get("schema") != SCHEMA:
        raise ContractError("schema DC-T ไม่ตรง")
    if conditional.get("role") != "secondary_additive" or conditional.get("contract") != CONTRACT_VERSION:
        raise ContractError("role/contract DC-T ไม่ตรง")
    if conditional.get("status") not in CONDITIONAL_STATUSES:
        raise ContractError("status DC-T ไม่รองรับ")
    basis = conditional.get("creation_basis")
    if not isinstance(basis, dict) or set(basis) != {"h1_bar_at", "m15_bar_at"}:
        raise ContractError("creation_basis ไม่ตรง schema")
    if conditional.get("status") != "STALE_DATA":
        for basis_at in basis.values():
            _parse(basis_at)
    geometry = conditional.get("watch_geometry")
    if conditional.get("status") != "STALE_DATA" and (not isinstance(geometry, dict) or set(geometry) != WATCH_KEYS):
        raise ContractError("watch_geometry ไม่ตรง schema")
    legs = conditional.get("legs")
    if not isinstance(legs, list) or any(not isinstance(leg, dict) or set(leg) != LEG_KEYS for leg in legs):
        raise ContractError("legs ไม่ตรง schema")
    for leg in legs:
        if leg.get("side") not in {"buy", "sell"} or leg.get("status") not in LEG_STATUSES:
            raise ContractError("leg state ไม่ตรง schema")
        expected_rule = ("m15_close_strictly_above_buy_watch" if leg["side"] == "buy"
                         else "m15_close_strictly_below_sell_watch")
        if leg.get("trigger_rule") != expected_rule:
            raise ContractError("leg trigger rule ไม่ตรง schema")
    reference = conditional.get("strict_plan_ref")
    if reference is not None and (not isinstance(reference, dict) or set(reference) != REF_KEYS):
        raise ContractError("strict_plan_ref ไม่ตรง schema")
    is_full_artifact = (isinstance(artifact, dict) and "daily_conditional" in artifact and
                        "source_snapshot" in artifact and "manifest" in artifact)
    if is_full_artifact:
        source_snapshot = artifact.get("source_snapshot")
        manifest = artifact.get("manifest")
        if (not isinstance(source_snapshot, dict) or
                set(source_snapshot) != {"schema", "asset", "h1_basis", "m15_basis",
                                         "h1_rows_sha256", "m15_rows_sha256",
                                         "h1_cutoff_close", "geometry_sha256"} or
                not isinstance(manifest, dict) or
                set(manifest) != {"schema", "story_schema", "source_snapshot_schema",
                                  "strict_projection_sha256", "conditional_sha256",
                                  "source_snapshot_sha256", "contract_version"}):
            raise ContractError("source snapshot/manifest binding ไม่พร้อม")
        if (source_snapshot.get("schema") != SOURCE_SNAPSHOT_SCHEMA or
                source_snapshot.get("asset") != ASSET or
                manifest.get("schema") != MANIFEST_SCHEMA or
                manifest.get("story_schema") != STORY_SCHEMA or
                manifest.get("source_snapshot_schema") != SOURCE_SNAPSHOT_SCHEMA or
                manifest.get("contract_version") != CONTRACT_VERSION or
                manifest.get("conditional_sha256") != conditional.get("sha256") or
                manifest.get("strict_projection_sha256") != conditional.get("strict_projection_hash") or
                manifest.get("source_snapshot_sha256") != _digest(source_snapshot)):
            raise ContractError("source snapshot/manifest hash ไม่ตรง")
    if is_full_artifact:
        oracle = artifact.get("strict_projection_oracle")
        if (not isinstance(oracle, dict) or set(oracle) != {"projection", "sha256"} or
                not isinstance(oracle["sha256"], str) or
                re.fullmatch(r"[0-9a-f]{64}", oracle["sha256"]) is None or
                not isinstance(oracle["projection"], dict) or
                _digest(oracle["projection"]) != oracle["sha256"] or
                oracle["projection"] != _strict_projection(_strict_from_artifact(artifact))):
            raise ContractError("strict projection oracle ไม่พร้อมหรือไม่ผูกกับ strict top-level")
        expected_projection = oracle["sha256"]
    else:
        expected_projection = _strict_hash(strict_story)
    if conditional.get("strict_projection_hash") != expected_projection:
        raise ContractError("strict projection hash ไม่ตรง")
    strict_projection = (_strict_projection(strict_story) if not is_full_artifact
                         else artifact["strict_projection_oracle"]["projection"])
    strict_available = (strict_projection.get("state") in {"WAIT_TRIGGER", "ENTRY_READY"} and
                        isinstance(strict_projection.get("plan"), dict) and
                        strict_projection["plan"].get("variant") == "B")
    if conditional.get("status") == "NOT_REQUIRED_STRICT_AVAILABLE" and not strict_available:
        raise ContractError("strict status parity ไม่ตรง: strict plan ไม่พร้อม")
    if conditional.get("status") == "ARMED" and strict_available:
        raise ContractError("strict status parity ไม่ตรง: strict plan พร้อมแล้ว")
    supplied_hash = conditional.get("sha256")
    if not isinstance(supplied_hash, str) or supplied_hash != _digest(
            {key: value for key, value in conditional.items() if key != "sha256"}):
        raise ContractError("conditional sha256 ไม่ตรง")
    try:
        cutoff = _parse(conditional["session_cutoff"])
        expiry = _parse(conditional["expires_at"])
    except (KeyError, ContractError) as exc:
        raise ContractError("session boundary ไม่ครบ") from exc
    _session_cutoff(cutoff)
    if expiry != cutoff + timedelta(days=1):
        raise ContractError("expiry ต้องเป็น 08:00 ของวันถัดไป")
    if conditional.get("effective_from") != _iso(cutoff):
        raise ContractError("effective_from ไม่ตรง cutoff")
    if conditional.get("manual_only") is not True or conditional.get("execution_enabled") is not False:
        raise ContractError("DC-T ต้อง manual-only และปิด execution")
    _validate_geometry(conditional, artifact, geometry_oracle=geometry_oracle)
    _validate_state_invariants(conditional)
    if reference is not None:
        if not isinstance(reference["session_id"], str) or not reference["session_id"]:
            raise ContractError("strict_plan_ref.session_id ไม่ถูกต้อง")
        if is_full_artifact and reference["session_id"] != artifact.get("session_id"):
            raise ContractError("strict_plan_ref session ไม่ผูกกับ artifact")
        evaluation_cutoff = reference["evaluation_cutoff"]
        if not isinstance(evaluation_cutoff, str) or _iso(evaluation_cutoff) != evaluation_cutoff:
            raise ContractError("strict_plan_ref.evaluation_cutoff ต้องเป็น Bangkok canonical")
        if is_full_artifact and artifact.get("evaluation_cutoff") != evaluation_cutoff:
            raise ContractError("strict_plan_ref cutoff ไม่ผูกกับ evaluation cutoff")
        plan_hash = reference["strict_plan_sha256"]
        if not isinstance(plan_hash, str) or re.fullmatch(r"[0-9a-f]{64}", plan_hash) is None:
            raise ContractError("strict_plan_ref hash ต้องเป็น lowercase 64-hex")
        bound_story = revalidated_strict_story or strict_story
        if not isinstance(bound_story.get("plan"), dict) or bound_story["plan"].get("variant") != "B":
            raise ContractError("READY strict plan ต้องเป็น variant B")
        if plan_hash != _digest(bound_story["plan"]):
            raise ContractError("strict_plan_ref ไม่ตรง strict plan ที่ revalidate")
    if is_full_artifact and check_nested_parity:
        _validate_nested_parity(artifact, conditional)


def _strict_from_artifact(artifact: dict) -> dict:
    return {key: copy.deepcopy(artifact.get(key)) for key in (
        "state", "side", "plan", "adaptive_reason_code", "adaptive_stop",
        "adaptive_context", "lifecycle")}


def _apply_strict_projection(result: dict, strict_story: dict) -> None:
    for key in ("state", "side", "plan", "adaptive_reason_code",
                "adaptive_stop", "adaptive_context", "lifecycle"):
        if key in strict_story:
            result[key] = copy.deepcopy(strict_story[key])
        else:
            result.pop(key, None)
    projection = _strict_projection(strict_story)
    result["strict_projection_oracle"] = {
        "projection": projection,
        "sha256": _digest(projection),
    }
    conditional = result.get("daily_conditional")
    if isinstance(conditional, dict):
        conditional["strict_projection_hash"] = _digest(projection)
        conditional["sha256"] = _digest({key: value for key, value in conditional.items()
                                          if key != "sha256"})
        if isinstance(result.get("manifest"), dict):
            result["manifest"]["strict_projection_sha256"] = conditional["strict_projection_hash"]
            result["manifest"]["conditional_sha256"] = conditional["sha256"]


def _stale_result(creation: dict, conditional: dict, *, evaluated_at: datetime,
                  strict_story: dict | None = None) -> dict:
    output = copy.deepcopy(creation)
    updated = copy.deepcopy(conditional)
    updated.update({"status": "STALE_DATA", "selected_side": None, "trigger_bar_at": None,
                    "watch_geometry": None, "legs": []})
    updated["sha256"] = _digest({key: value for key, value in updated.items() if key != "sha256"})
    output["daily_conditional"] = updated
    output["evaluation_cutoff"] = _iso(evaluated_at)
    output["manifest"]["conditional_sha256"] = updated["sha256"]
    chosen_strict = strict_story or _strict_from_artifact(output)
    _apply_strict_projection(output, chosen_strict)
    output["story"] = _story_payload(chosen_strict, updated)
    output["story"]["daily_conditional"] = copy.deepcopy(output["daily_conditional"])
    output["story"]["strict_projection_oracle"] = copy.deepcopy(output["strict_projection_oracle"])
    output["story"]["watch_geometry_oracle"] = copy.deepcopy(output["watch_geometry_oracle"])
    output["story"]["source_snapshot"] = copy.deepcopy(output["source_snapshot"])
    output["story"]["manifest"] = copy.deepcopy(output["manifest"])
    validate(output, strict_story=_strict_from_artifact(output), now=evaluated_at)
    return output


def evaluate(*, creation: dict, strict_story: dict, h1_rows: list[dict], m15_rows: list[dict],
             evaluated_at: datetime, **_) -> dict:
    # The strict projection may legitimately change on revalidation; creation
    # integrity is checked against the immutable projection carried by it.
    _require_creation_artifact(creation)
    validate(creation, strict_story=_strict_from_artifact(creation), now=evaluated_at)
    original = _extract(creation)
    evaluated = _parse(evaluated_at)
    cutoff = _parse(original["session_cutoff"])
    expiry = _parse(original["expires_at"])
    # A row closing at/after expiry is outside this session.  Drop it before
    # checking continuity so an exact-expiry bar cannot manufacture a gap or
    # trigger. Post-08:00 rows are valid on-demand observations.
    try:
        filtered_m15 = [row for row in m15_rows
                        if _row_close_at(_parse(row.get("at")), row, M15) < expiry]
    except (ContractError, KeyError, TypeError, ValueError):
        return _stale_result(creation, original, evaluated_at=evaluated,
                             strict_story=strict_story)
    try:
        parsed_h1 = _validate_rows(h1_rows, H1, cutoff=cutoff,
                                   allow_last_geometry=False)
        parsed_m15 = _validate_rows(filtered_m15, M15, cutoff=cutoff,
                                    allow_last_geometry=False)
        for at, row in parsed_h1:
            if _row_close_at(at, row, H1) > evaluated:
                raise StaleData("พบ bar ที่ยังไม่ปิด ณ evaluation cutoff")
        for at, row in parsed_m15:
            if _row_close_at(at, row, M15) > evaluated:
                raise StaleData("พบ bar ที่ยังไม่ปิด ณ evaluation cutoff")
    except StaleData:
        return _stale_result(creation, original, evaluated_at=evaluated,
                             strict_story=strict_story)
    except ContractError:
        raise
    result = copy.deepcopy(creation)
    updated = copy.deepcopy(original)
    if evaluated >= expiry:
        updated.update({"status": "EXPIRED", "selected_side": None, "trigger_bar_at": None,
                        "legs": []})
    elif original.get("status") == "STALE_DATA":
        updated.update({"status": "STALE_DATA", "selected_side": None, "trigger_bar_at": None,
                        "legs": []})
    elif original.get("status") == "NOT_REQUIRED_STRICT_AVAILABLE":
        if _strict_is_available(strict_story):
            updated.update({"status": "NOT_REQUIRED_STRICT_AVAILABLE", "selected_side": None,
                            "trigger_bar_at": None, "legs": []})
        else:
            updated.update({"status": "ARMED", "selected_side": None, "trigger_bar_at": None,
                            "legs": [
                                {"side": "buy", "status": "ARMED",
                                 "trigger_rule": "m15_close_strictly_above_buy_watch"},
                                {"side": "sell", "status": "ARMED",
                                 "trigger_rule": "m15_close_strictly_below_sell_watch"},
                            ]})
    else:
        buy = float(original["watch_geometry"]["buy_watch"])
        sell = float(original["watch_geometry"]["sell_watch"])
        events = []
        for at, row in parsed_m15:
            close_at = _row_close_at(at, row, M15)
            if close_at <= cutoff or close_at >= expiry or close_at > evaluated:
                continue
            close = _number(row.get("close"), "M15.close")
            side = "buy" if close > buy else ("sell" if close < sell else None)
            if side:
                events.append((close_at, side))
        if events:
            first_at, first_side = events[0]
            updated["selected_side"] = first_side
            updated["trigger_bar_at"] = _utc_iso(first_at)
            updated["status"] = "WATCH_TRIGGERED_WAIT_REVALIDATION"
            updated["legs"] = [
                {"side": "buy", "status": ("TRIGGERED_WAIT_REVALIDATION" if first_side == "buy" else "CANCELLED_BY_OPPOSITE_TRIGGER"),
                 "trigger_rule": "m15_close_strictly_above_buy_watch"},
                {"side": "sell", "status": ("TRIGGERED_WAIT_REVALIDATION" if first_side == "sell" else "CANCELLED_BY_OPPOSITE_TRIGGER"),
                 "trigger_rule": "m15_close_strictly_below_sell_watch"},
            ]
            # Revalidation is only allowed on a later closed bar and must use
            # the explicit strict result supplied by the caller.
            next_at = first_at + _interval(M15)
            next_row = next(((close_at, row) for at, row in parsed_m15
                             for close_at in (_row_close_at(at, row, M15),)
                             if close_at == next_at), None)
            next_bar_confirms = False
            if next_row is not None:
                next_close = _number(next_row[1].get("close"), "M15.close")
                next_bar_confirms = (next_close > buy if first_side == "buy"
                                     else next_close < sell)
            strict_state = strict_story.get("state")
            strict_side = strict_story.get("side")
            strict_plan = strict_story.get("plan")
            if (next_bar_confirms and strict_side == first_side and
                    strict_state in {"WAIT_TRIGGER", "ENTRY_READY"} and
                    isinstance(strict_plan, dict) and strict_plan.get("variant") == "B"):
                updated["status"] = "READY_AFTER_STRICT_REVALIDATION"
                for leg in updated["legs"]:
                    if leg["side"] == first_side:
                        leg["status"] = "READY_AFTER_STRICT_REVALIDATION"
                updated["strict_plan_ref"] = {
                        "session_id": result["session_id"],
                    "evaluation_cutoff": _iso(evaluated),
                    "strict_plan_sha256": _digest(strict_story.get("plan")),
                }
                for key in ("state", "side", "plan", "adaptive_reason_code",
                            "adaptive_stop", "adaptive_context", "lifecycle"):
                    if key in strict_story:
                        result[key] = copy.deepcopy(strict_story[key])
                projection = _strict_projection(strict_story)
                result["strict_projection_oracle"] = {
                    "projection": projection,
                    "sha256": _digest(projection),
                }
                updated["strict_projection_hash"] = _digest(projection)
                result["watch_geometry_oracle"] = {
                    "geometry": copy.deepcopy(updated.get("watch_geometry")),
                    "sha256": _digest(updated.get("watch_geometry")),
                }
            elif next_row is not None and strict_side is not None and strict_side != first_side:
                updated["status"] = "INVALIDATED"
                updated.update({"selected_side": None, "trigger_bar_at": None,
                                "strict_plan_ref": None, "legs": []})
        else:
            if _strict_is_available(strict_story):
                updated.update({"status": "NOT_REQUIRED_STRICT_AVAILABLE", "selected_side": None,
                                "trigger_bar_at": None, "legs": []})
            else:
                updated.update({"status": "ARMED", "selected_side": None, "trigger_bar_at": None,
                                "legs": [
                                    {"side": "buy", "status": "ARMED",
                                     "trigger_rule": "m15_close_strictly_above_buy_watch"},
                                    {"side": "sell", "status": "ARMED",
                                     "trigger_rule": "m15_close_strictly_below_sell_watch"},
                                ]})
    result["daily_conditional"] = updated
    _apply_strict_projection(result, strict_story)
    updated = result["daily_conditional"]
    result["evaluation_cutoff"] = _iso(evaluated)
    result["manifest"]["conditional_sha256"] = updated["sha256"]
    result["manifest"]["strict_projection_sha256"] = updated["strict_projection_hash"]
    result["story"] = _story_payload(strict_story, updated)
    result["story"]["source_snapshot"] = copy.deepcopy(result["source_snapshot"])
    result["story"]["manifest"] = copy.deepcopy(result["manifest"])
    validate(result, strict_story=_strict_from_artifact(result),
             revalidated_strict_story=strict_story, now=evaluated_at)
    return result


def replay(creation: dict) -> dict:
    """Return an immutable byte-equivalent replay of a creation artifact."""
    _require_creation_artifact(creation)
    conditional = _extract(creation)
    return copy.deepcopy(creation)
