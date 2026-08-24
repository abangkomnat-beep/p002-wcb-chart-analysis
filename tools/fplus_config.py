"""Validation for the locked BTCUSD F+ configuration."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from tools.fplus_contracts import FORBIDDEN_SCHEDULE_FIELDS


class ConfigError(ValueError):
    """Raised when configuration weakens or changes a locked policy."""


REPO_ROOT = Path(__file__).resolve().parents[1]
RISK_PATH = REPO_ROOT / "config" / "risk_thresholds.json"
RISK_SOURCE = "config/risk_thresholds.json"


def _risk_contract() -> dict[str, str]:
    try:
        payload = json.loads(RISK_PATH.read_text(encoding="utf-8"))
        thresholds = payload["thresholds"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ConfigError("risk_thresholds.json is unavailable or invalid") from exc
    if set(thresholds) != {"minimum_rr", "minimum_stop_atr", "maximum_entry_atr"}:
        raise ConfigError("risk threshold source has an invalid key set")
    if any(not isinstance(value, (int, float)) or value <= 0 for value in thresholds.values()):
        raise ConfigError("risk threshold values must be positive numbers")
    return {
        "source": RISK_SOURCE,
        "sha256": hashlib.sha256(RISK_PATH.read_bytes()).hexdigest(),
    }


def _walk_forbidden(value: Any, path: str = "config") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in FORBIDDEN_SCHEDULE_FIELDS:
                raise ConfigError(f"manual-only config rejects schedule field {path}.{key}")
            _walk_forbidden(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_forbidden(child, f"{path}[{index}]")


def validate_config(mapping: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(mapping, Mapping):
        raise ConfigError("config must be a mapping")
    config = deepcopy(dict(mapping))
    _walk_forbidden(config)
    required = {
        "schema", "asset", "execution", "timezone", "candidate_order", "news",
        "timeframes", "freshness_grace_by_timeframe", "cross_timeframe_tolerance",
        "artifact", "lock", "rollout",
    }
    missing = required.difference(config)
    optional = {"risk", "warmup_bars"}
    extra = set(config).difference(required | optional)
    if missing or extra:
        raise ConfigError(f"config fields invalid; missing={sorted(missing)}, extra={sorted(extra)}")
    if config["schema"] != "fplus-btc-daily-v1":
        raise ConfigError("unsupported F+ config schema")
    if config["asset"] != "btcusd":
        raise ConfigError("F+ asset must remain btcusd")
    if config["execution"] != {"manual_only": True}:
        raise ConfigError("execution must be manual_only with no schedule")
    if config["timezone"] != "Asia/Bangkok":
        raise ConfigError("trade-date timezone must remain Asia/Bangkok")
    if config["candidate_order"] != ["J", "I", "E_LOGIC", "F"]:
        raise ConfigError("candidate order must remain J, I, E_LOGIC, F")
    if config["news"] != {
        "source": "wcb", "currency": "USD", "impact": "high",
        "before_minutes": 30, "after_minutes": 30,
    }:
        raise ConfigError("news policy must remain WCB High-impact USD ±30 minutes")
    if config["timeframes"] != {
        "bias": "4h", "setup": "1h", "evidence": "30min", "trigger": "15min"
    }:
        raise ConfigError("timeframe contract must remain H4/H1/M30/M15")
    for timeframe in ("4h", "1h", "30min", "15min"):
        if timeframe not in config["freshness_grace_by_timeframe"]:
            raise ConfigError(f"missing freshness grace for {timeframe}")
        if int(config["freshness_grace_by_timeframe"][timeframe]) < 0:
            raise ConfigError("freshness grace cannot be negative")
    if float(config["cross_timeframe_tolerance"]) < 0:
        raise ConfigError("cross-timeframe tolerance cannot be negative")
    artifact = config["artifact"]
    if artifact.get("folder") != "F+-BTCUSD-แผนระยะสั้น":
        raise ConfigError("artifact folder is locked")
    if int(artifact.get("image_max_bytes", 0)) != 204800:
        raise ConfigError("image size gate must remain 200 KB")
    lock = config["lock"]
    if int(lock.get("lease_seconds", 0)) <= 0 or int(lock.get("heartbeat_seconds", 0)) <= 0:
        raise ConfigError("lock lease and heartbeat must be positive")
    if int(lock["heartbeat_seconds"]) >= int(lock["lease_seconds"]):
        raise ConfigError("heartbeat must be shorter than the lease")
    if config["rollout"].get("phase") not in {"disabled", "shadow", "local", "cutover"}:
        raise ConfigError("invalid rollout phase")
    risk = _risk_contract()
    supplied_risk = config.get("risk")
    if supplied_risk is not None and supplied_risk != risk:
        raise ConfigError("risk source/fingerprint must match config/risk_thresholds.json")
    config["risk"] = risk
    warmup = config.get("warmup_bars") or {
        "4h": 4, "1h": 4, "30min": 4, "15min": 4,
    }
    if set(warmup) != {"4h", "1h", "30min", "15min"}:
        raise ConfigError("warmup_bars must cover H4/H1/M30/M15 exactly")
    if any(int(value) <= 0 or int(value) > 500 for value in warmup.values()):
        raise ConfigError("warmup_bars must be between 1 and 500")
    config["warmup_bars"] = {key: int(value) for key, value in warmup.items()}
    return config
