"""Contract surface for BTCUSD F+ schemas, config, and manual-only CLI."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from fixtures.fplus.contract_support import load_json, require_module


FORBIDDEN_SCHEDULE_FIELDS = ("schedule", "cron", "run_at", "interval", "watch", "daemon", "repeat")


def request_payload(**overrides) -> dict:
    value = {
        "schema_version": "fplus-run-request-v1",
        "run_id": "00000000-0000-4000-8000-000000000001",
        "asset": "btcusd",
        "mode": "shadow",
        "shadow_id": "S01",
        "requested_at_utc": "2026-08-24T02:01:00Z",
        "decision_cutoff_utc": "2026-08-24T02:00:00Z",
        "trade_date_bangkok": "2026-08-24",
        "generation_request": "normal",
        "force_reason": None,
        "work_root": "work",
        "output_root": "output",
        "state_root": "state",
        "config_fingerprint": "a" * 64,
    }
    value.update(overrides)
    return value


def test_run_request_round_trip_and_canonical_json_are_deterministic():
    contracts = require_module("tools.fplus_contracts")
    request = contracts.FPlusRunRequest.from_dict(request_payload())
    assert request.to_dict() == request_payload()
    left = contracts.canonical_json({"b": 2, "a": 1})
    right = contracts.canonical_json({"a": 1, "b": 2})
    assert left == right
    assert contracts.sha256_canonical({"b": 2, "a": 1}) == contracts.sha256_canonical({"a": 1, "b": 2})


@pytest.mark.parametrize("field", FORBIDDEN_SCHEDULE_FIELDS)
def test_run_request_rejects_schedule_fields(field):
    contracts = require_module("tools.fplus_contracts")
    with pytest.raises(contracts.ContractError, match="manual|schedule|field"):
        contracts.FPlusRunRequest.from_dict(request_payload(**{field: "09:05"}))


def test_run_request_rejects_non_btc_and_force_in_shadow():
    contracts = require_module("tools.fplus_contracts")
    with pytest.raises(contracts.ContractError, match="btcusd"):
        contracts.FPlusRunRequest.from_dict(request_payload(asset="xauusd"))
    with pytest.raises(contracts.ContractError, match="force|local"):
        contracts.FPlusRunRequest.from_dict(request_payload(
            generation_request="force", force_reason="QA correction"))


@pytest.mark.parametrize("shadow_id", ["S01", "S02", "S03"])
def test_shadow_request_round_trip_preserves_manual_shadow_id(shadow_id):
    contracts = require_module("tools.fplus_contracts")
    request = contracts.FPlusRunRequest.from_dict(request_payload(shadow_id=shadow_id))
    assert request.shadow_id == shadow_id
    assert request.to_dict()["shadow_id"] == shadow_id


@pytest.mark.parametrize("shadow_id", [None, "", "S00", "S04", "AUTO", "09:05"])
def test_shadow_request_requires_s01_to_s03(shadow_id):
    contracts = require_module("tools.fplus_contracts")
    with pytest.raises(contracts.ContractError, match="shadow|S01|S02|S03"):
        contracts.FPlusRunRequest.from_dict(request_payload(shadow_id=shadow_id))


def test_local_request_requires_null_shadow_id():
    contracts = require_module("tools.fplus_contracts")
    local = contracts.FPlusRunRequest.from_dict(request_payload(mode="local", shadow_id=None))
    assert local.shadow_id is None
    assert local.to_dict()["shadow_id"] is None
    with pytest.raises(contracts.ContractError, match="shadow|local|null|None"):
        contracts.FPlusRunRequest.from_dict(request_payload(mode="local", shadow_id="S01"))


def test_force_requires_non_blank_audit_reason():
    contracts = require_module("tools.fplus_contracts")
    with pytest.raises(contracts.ContractError, match="reason"):
        contracts.FPlusRunRequest.from_dict(request_payload(
            mode="local", shadow_id=None, generation_request="force", force_reason="  "))


def test_no_trade_selected_plan_forbids_trade_numbers():
    contracts = require_module("tools.fplus_contracts")
    plan = contracts.SelectedPlan.from_dict(load_json("selected_no_trade.json"))
    assert plan.selection == "NO_TRADE"
    assert plan.entry_zone is None
    invalid = load_json("selected_no_trade.json")
    invalid["stop_loss"] = 69000.0
    with pytest.raises(contracts.ContractError, match="NO_TRADE|stop|trade"):
        contracts.SelectedPlan.from_dict(invalid)


def test_config_is_manual_only_and_rejects_locked_contract_changes():
    config_module = require_module("tools.fplus_config")
    valid = load_json("config_valid.json")
    assert config_module.validate_config(valid)["execution"]["manual_only"] is True
    mutations = [
        ("candidate_order", ["I", "J", "E_LOGIC", "F"]),
        ("timezone", "UTC"),
        ("asset", "xauusd"),
    ]
    for key, value in mutations:
        changed = deepcopy(valid)
        changed[key] = value
        with pytest.raises(config_module.ConfigError):
            config_module.validate_config(changed)


@pytest.mark.parametrize("field", FORBIDDEN_SCHEDULE_FIELDS)
def test_config_rejects_schedule_related_keys_at_any_depth(field):
    config_module = require_module("tools.fplus_config")
    changed = load_json("config_valid.json")
    changed.setdefault("execution", {})[field] = "09:05"
    with pytest.raises(config_module.ConfigError, match="manual|schedule|field"):
        config_module.validate_config(changed)


def test_cli_accepts_only_manual_options_and_rejects_schedule_options():
    daily = require_module("tools.fplus_daily")
    parser = daily.build_parser()
    parsed = parser.parse_args(["--mode", "shadow", "--shadow-id", "S01"])
    assert parsed.mode == "shadow"
    assert parsed.shadow_id == "S01"
    for option in ("--schedule", "--cron", "--run-at", "--interval", "--watch", "--daemon", "--repeat"):
        with pytest.raises(SystemExit):
            parser.parse_args(["--mode", "shadow", option, "09:05"])


def test_cli_force_contract_requires_local_mode_and_reason():
    daily = require_module("tools.fplus_daily")
    with pytest.raises(SystemExit):
        daily.parse_request(["--mode", "shadow", "--force", "--force-reason", "QA"])
    with pytest.raises(SystemExit):
        daily.parse_request(["--mode", "local", "--force"])


def test_cli_parse_request_preserves_shadow_id_and_local_null():
    daily = require_module("tools.fplus_daily")
    shadow = daily.parse_request([
        "--mode", "shadow", "--shadow-id", "S02",
        "--cutoff-at", "2026-08-24T02:00:00Z",
    ])
    assert shadow.shadow_id == "S02"
    local = daily.parse_request([
        "--mode", "local", "--cutoff-at", "2026-08-24T02:00:00Z",
    ])
    assert local.shadow_id is None


class _InjectedRuntime:
    def __init__(self, result):
        self.result = result
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        return dict(self.result)


@pytest.mark.parametrize("status,expected_exit", [
    ("committed", 0),
    ("no_trade_committed", 0),
    ("already_done", 0),
    ("shadow_pass", 0),
    ("in_progress", 20),
    ("blocked_retryable", 30),
    ("failed_retryable", 40),
    ("shadow_fail", 40),
])
def test_cli_main_invokes_injected_runtime_and_returns_exit_contract(
    status, expected_exit, capsys,
):
    daily = require_module("tools.fplus_daily")
    runtime = _InjectedRuntime({"status": status, "selection": "J"})
    factory_requests = []

    def runtime_factory(request):
        factory_requests.append(request)
        return runtime

    exit_code = daily.main([
        "--mode", "shadow", "--shadow-id", "S01",
        "--cutoff-at", "2026-08-24T02:00:00Z", "--json",
    ], runtime_factory=runtime_factory)

    assert exit_code == expected_exit
    assert len(factory_requests) == 1
    assert runtime.requests == factory_requests
    assert runtime.requests[0].shadow_id == "S01"
    assert json.loads(capsys.readouterr().out)["status"] == status
