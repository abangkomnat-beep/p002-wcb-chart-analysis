"""SHD-01 contract: true offline decision replay from persisted snapshot."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from fixtures.fplus.contract_support import load_json, require_module, valid_snapshot


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "fplus"
DECISION_PATH = (
    "evaluate_data", "evaluate_news", "evaluate_candidates", "route",
)


def _shadow_request(tmp_path):
    contracts = require_module("tools.fplus_contracts")
    config = load_json("config_valid.json")
    return contracts.FPlusRunRequest.from_dict({
        "schema_version": "fplus-run-request-v1",
        "run_id": "00000000-0000-4000-8000-000000000201",
        "asset": "btcusd",
        "mode": "shadow",
        "shadow_id": "S01",
        "requested_at_utc": "2026-08-24T02:01:00Z",
        "decision_cutoff_utc": "2026-08-24T02:00:00Z",
        "trade_date_bangkok": "2026-08-24",
        "generation_request": "normal",
        "force_reason": None,
        "work_root": str(tmp_path / "work"),
        "output_root": str(tmp_path / "output"),
        "state_root": str(tmp_path / "state"),
        "config_fingerprint": contracts.sha256_canonical(config),
    })


def _synthetic_snapshot():
    snapshot = valid_snapshot()
    snapshot.update(load_json("runtime_shadow_inputs.json"))
    return snapshot


class _ReplayProbe:
    """Fresh replay adapter that cannot acquire data or production state."""

    def __init__(self, delegate, *, candidate_drift=False, router_drift=False):
        self.delegate = delegate
        self.candidate_drift = candidate_drift
        self.router_drift = router_drift
        self.calls: list[str] = []
        self.received_snapshot: dict | None = None

    def fetch_snapshot(self, request):  # pragma: no cover - a call is a contract breach
        del request
        raise AssertionError("offline replay must not fetch market/news data")

    def acquire_production(self, request):  # pragma: no cover - contract breach
        del request
        raise AssertionError("offline replay must not acquire a production lock")

    def evaluate_data(self, snapshot, config):
        self.calls.append("evaluate_data")
        self.received_snapshot = deepcopy(dict(snapshot))
        self.delegate._snapshot = deepcopy(dict(snapshot))  # noqa: SLF001
        return self.delegate.evaluate_data(snapshot, config)

    def evaluate_news(self, snapshot, request, config):
        self.calls.append("evaluate_news")
        return self.delegate.evaluate_news(snapshot, request, config)

    def evaluate_candidates(self, snapshot, config):
        self.calls.append("evaluate_candidates")
        decisions = self.delegate.evaluate_candidates(snapshot, config)
        if self.candidate_drift:
            decisions = deepcopy(decisions)
            decisions[1]["reason_codes"] = [
                *decisions[1].get("reason_codes", []),
                "INJECTED_REPLAY_CANDIDATE_DRIFT",
            ]
        return decisions

    def route(self, candidate_decisions, gate_report):
        self.calls.append("route")
        selected = self.delegate.route(candidate_decisions, gate_report)
        if self.router_drift:
            selected = deepcopy(selected)
            selected["trigger_m15"] = (
                f"{selected['trigger_m15']} [INJECTED_REPLAY_ROUTER_DRIFT]"
            )
        return selected


def _run_with_replay_probe(
    tmp_path, monkeypatch, *, candidate_drift=False, router_drift=False,
):
    runtime_module = require_module("tools.fplus_runtime")
    adapters_module = require_module("tools.fplus_adapters")
    request = _shadow_request(tmp_path)
    snapshots = []
    network_calls = []

    def snapshot_provider(received_request):
        snapshots.append(received_request)
        return _synthetic_snapshot()

    def forbidden_network(*args, **kwargs):
        network_calls.append((args, kwargs))
        raise AssertionError("offline synthetic shadow/replay must not use network")

    monkeypatch.setattr(adapters_module.intraday_bars, "fetch_rows", forbidden_network)
    monkeypatch.setattr(adapters_module.calendar_feed, "fetch_raw", forbidden_network)

    probe = _ReplayProbe(
        runtime_module.ConcreteRuntimeAdapters(load_json("config_valid.json")),
        candidate_drift=candidate_drift,
        router_drift=router_drift,
    )
    factory_calls = []

    def build_replay_adapter(owner, snapshot_path):
        snapshot_path = Path(snapshot_path).resolve()
        assert snapshot_path.is_file(), "snapshot must be persisted before replay adapter creation"
        assert snapshot_path.is_relative_to(Path(request.work_root).resolve())
        factory_calls.append({
            "owner_id": id(owner),
            "adapter_id": id(probe),
            "snapshot_path": snapshot_path,
            "snapshot_bytes": snapshot_path.read_bytes(),
        })
        return probe

    # Contract seam: record_shadow must create a fresh decision adapter from
    # the persisted immutable snapshot, rather than replay on the live owner.
    monkeypatch.setattr(
        runtime_module.ConcreteRuntimeAdapters,
        "build_replay_adapter",
        build_replay_adapter,
        raising=False,
    )
    runtime = runtime_module.FPlusRuntime(
        config_path=FIXTURE_ROOT / "config_valid.json",
        snapshot_provider=snapshot_provider,
    )
    result = runtime.run(request)
    return {
        "request": request,
        "result": result,
        "probe": probe,
        "factory_calls": factory_calls,
        "provider_calls": snapshots,
        "network_calls": network_calls,
    }


def _report(run):
    return json.loads(
        Path(run["result"]["shadow_report_path"]).read_text(encoding="utf-8")
    )


def test_record_shadow_persists_full_normalized_snapshot_internal_only(tmp_path, monkeypatch):
    contracts = require_module("tools.fplus_contracts")
    run = _run_with_replay_probe(tmp_path, monkeypatch)
    report_path = Path(run["result"]["shadow_report_path"]).resolve()
    internal = report_path.parent
    snapshot_path = internal / "normalized-market-snapshot.json"

    assert snapshot_path.is_file()
    persisted = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert persisted == _synthetic_snapshot()
    expected_hash = contracts.sha256_canonical(persisted)
    assert run["factory_calls"][0]["snapshot_bytes"] == snapshot_path.read_bytes()

    report = _report(run)
    assert report["replay"]["snapshot_sha256"] == expected_hash
    assert Path(run["result"]["staging_dir"]).resolve() != snapshot_path.parent
    assert snapshot_path.name not in {
        item["name"] for item in json.loads(
            (internal / "artifact-manifest.json").read_text(encoding="utf-8")
        )["files"]
    }
    output_root = Path(run["request"].output_root)
    assert not output_root.exists() or not any(output_root.rglob("*"))


def test_record_shadow_replays_fresh_decision_path_without_network_or_production_lock(
    tmp_path, monkeypatch,
):
    run = _run_with_replay_probe(tmp_path, monkeypatch)
    report = _report(run)

    assert len(run["factory_calls"]) == 1
    assert run["factory_calls"][0]["owner_id"] != run["factory_calls"][0]["adapter_id"]
    assert tuple(run["probe"].calls) == DECISION_PATH
    assert run["probe"].received_snapshot == _synthetic_snapshot()
    assert run["provider_calls"] == [run["request"]]
    assert run["network_calls"] == []
    assert report["replay"]["decision_path"] == list(DECISION_PATH)
    assert report["promoted"] is False
    assert report["production_lock_used"] is False
    production_lock = (
        Path(run["request"].state_root) / "fplus" / "btcusd" / "2026-08-24.json"
    )
    assert not production_lock.exists()


def test_record_shadow_compares_replayed_selected_plan_and_artifact_hashes(
    tmp_path, monkeypatch,
):
    contracts = require_module("tools.fplus_contracts")
    run = _run_with_replay_probe(tmp_path, monkeypatch)
    report = _report(run)
    replay = report["replay"]
    internal = Path(run["result"]["shadow_report_path"]).parent
    original_plan = json.loads(
        (internal / "selected-plan.json").read_text(encoding="utf-8")
    )
    artifact_manifest = json.loads(
        (internal / "artifact-manifest.json").read_text(encoding="utf-8")
    )

    assert run["result"]["status"] == "shadow_pass"
    assert replay["decision_replay_deterministic"] is True
    assert replay["artifact_replay_deterministic"] is True
    assert replay["original_selected_plan_sha256"] == contracts.sha256_canonical(original_plan)
    assert replay["replay_selected_plan_sha256"] == replay["original_selected_plan_sha256"]
    assert replay["original_artifact_set_sha256"] == artifact_manifest["artifact_set_sha256"]
    assert replay["replay_artifact_set_sha256"] == replay["original_artifact_set_sha256"]
    assert replay["original_candidate_decisions_sha256"]
    assert replay["replay_candidate_decisions_sha256"] == replay["original_candidate_decisions_sha256"]


def test_record_shadow_candidate_replay_drift_is_shadow_fail(tmp_path, monkeypatch):
    run = _run_with_replay_probe(tmp_path, monkeypatch, candidate_drift=True)
    report = _report(run)
    replay = report["replay"]

    assert tuple(run["probe"].calls) == DECISION_PATH
    assert run["result"]["status"] == "shadow_fail"
    assert report["status"] == "shadow_fail"
    assert replay["decision_replay_deterministic"] is False
    assert replay["original_candidate_decisions_sha256"] != replay["replay_candidate_decisions_sha256"]
    assert "REPLAY_CANDIDATE_MISMATCH" in report["reason_codes"]


def test_record_shadow_router_replay_drift_is_shadow_fail(tmp_path, monkeypatch):
    run = _run_with_replay_probe(tmp_path, monkeypatch, router_drift=True)
    report = _report(run)
    replay = report["replay"]

    assert tuple(run["probe"].calls) == DECISION_PATH
    assert run["result"]["status"] == "shadow_fail"
    assert report["status"] == "shadow_fail"
    assert replay["decision_replay_deterministic"] is False
    assert replay["original_candidate_decisions_sha256"] == replay["replay_candidate_decisions_sha256"]
    assert replay["original_selected_plan_sha256"] != replay["replay_selected_plan_sha256"]
    assert "REPLAY_SELECTED_PLAN_MISMATCH" in report["reason_codes"]
