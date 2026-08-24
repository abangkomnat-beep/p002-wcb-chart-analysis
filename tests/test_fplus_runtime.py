"""Concrete manual runtime and synthetic shadow acceptance contracts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from fixtures.fplus.contract_support import load_json, require_module, valid_snapshot


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "fplus"
RISK_SOURCE = REPO_ROOT / "config" / "risk_thresholds.json"
PIPELINE_PORTS = (
    "acquire_production", "acquire_shadow", "fetch_snapshot", "evaluate_data",
    "evaluate_news", "evaluate_candidates", "route", "stage_artifacts", "promote",
    "commit_production", "mark_retryable", "record_shadow",
)


def shadow_request(tmp_path):
    contracts = require_module("tools.fplus_contracts")
    config = load_json("config_valid.json")
    return contracts.FPlusRunRequest.from_dict({
        "schema_version": "fplus-run-request-v1",
        "run_id": "00000000-0000-4000-8000-000000000101",
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


def synthetic_snapshot():
    snapshot = valid_snapshot()
    snapshot.update(load_json("runtime_shadow_inputs.json"))
    return snapshot


def test_concrete_runtime_adapter_implements_every_pipeline_port():
    runtime = require_module("tools.fplus_runtime")
    adapter_type = runtime.ConcreteRuntimeAdapters
    missing = [name for name in PIPELINE_PORTS if not callable(getattr(adapter_type, name, None))]
    assert missing == []


def test_synthetic_shadow_runs_end_to_end_without_final_or_production_lock(tmp_path):
    runtime_module = require_module("tools.fplus_runtime")
    request = shadow_request(tmp_path)
    snapshots = []

    def snapshot_provider(received_request):
        snapshots.append(received_request)
        return synthetic_snapshot()

    runtime = runtime_module.FPlusRuntime(
        config_path=FIXTURE_ROOT / "config_valid.json",
        snapshot_provider=snapshot_provider,
    )
    result = runtime.run(request)

    assert result["status"] == "shadow_pass"
    assert result["selection"] == "J"
    assert result["shadow_id"] == "S01"
    assert snapshots == [request]

    work_root = Path(request.work_root).resolve()
    output_root = Path(request.output_root).resolve()
    state_root = Path(request.state_root).resolve()
    report_path = Path(result["shadow_report_path"]).resolve()
    staging_dir = Path(result["staging_dir"]).resolve()
    shadow_record = Path(result["shadow_record_path"]).resolve()
    assert report_path.is_file() and report_path.is_relative_to(work_root)
    assert staging_dir.is_dir() and staging_dir.is_relative_to(work_root)
    assert shadow_record.is_file()
    assert shadow_record == state_root / "fplus" / "btcusd" / "shadow" / "2026-08-24" / "S01.json"
    assert sorted(path.name for path in staging_dir.iterdir() if path.is_file()) == [
        "btcusd-fplus-2026-08-24.webp", "btcusd.md",
    ]
    assert not output_root.exists() or not any(output_root.rglob("*"))
    assert not (state_root / "fplus" / "btcusd" / "2026-08-24.json").exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "shadow_pass"
    assert report["shadow_id"] == "S01"
    assert report["selection"] == "J"
    assert report["snapshot_id"] == "fixture-snapshot"
    assert report["risk_policy_fingerprint"] == hashlib.sha256(RISK_SOURCE.read_bytes()).hexdigest()
    assert report["replay"]["deterministic"] is True
    assert report["replay"]["selected_plan_sha256"]
    assert report["replay"]["artifact_set_sha256"]


def _prepare_stage(root: Path) -> tuple[Path, dict]:
    stage = root / "stage"
    stage.mkdir(parents=True)
    contents = {
        "btcusd.md": b"generation=1\n",
        "btcusd-fplus-2026-08-24.webp": b"WEBP-generation=1",
    }
    files = []
    for name, content in contents.items():
        (stage / name).write_bytes(content)
        files.append({
            "name": name,
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
        })
    return stage, {"run_id": "run-reconcile", "generation": 1, "files": files}


def test_runtime_startup_reconciles_visible_journal_to_committed_lock(tmp_path):
    runtime = require_module("tools.fplus_runtime")
    locks = require_module("tools.fplus_lock")
    artifacts = require_module("tools.fplus_artifacts")
    lock_store = locks.LocalLockStore(tmp_path / "state")
    artifact_store = artifacts.ArtifactTransaction(
        work_root=tmp_path / "work", output_root=tmp_path / "output",
    )
    key = "fplus:btcusd:2026-08-24"
    lock_store.acquire(
        key=key, run_id="run-reconcile", now_utc="2026-08-24T02:00:00Z",
        lease_seconds=300, cutoff_at_utc="2026-08-24T02:00:00Z",
        config_fingerprint="c" * 64, force=False, force_reason=None,
    )
    relative = Path("24-08-2026") / "F+-BTCUSD-แผนระยะสั้น"
    stage, manifest = _prepare_stage(tmp_path)
    with pytest.raises(artifacts.InjectedTransactionFailure):
        artifact_store.commit(
            stage, relative_final_dir=relative, manifest=manifest,
            fault_at="before_lock_commit",
        )

    reconciled = runtime.reconcile_startup(
        key=key, run_id="run-reconcile", now_utc="2026-08-24T02:01:00Z",
        relative_final_dir=relative, lock_store=lock_store,
        artifact_store=artifact_store,
    )

    assert reconciled["status"] == "committed"
    assert reconciled["reconciled"] is True
    expected_hashes = {item["name"]: item["sha256"] for item in manifest["files"]}
    assert reconciled["artifact_hashes"] == expected_hashes
    rerun = lock_store.acquire(
        key=key, run_id="run-after-reconcile", now_utc="2026-08-24T02:02:00Z",
        lease_seconds=300, cutoff_at_utc="2026-08-24T02:00:00Z",
        config_fingerprint="c" * 64, force=False, force_reason=None,
    )
    assert rerun["status"] == "already_done"
    assert rerun["artifact_hashes"] == expected_hashes
