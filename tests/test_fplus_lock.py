"""Daily lock contract: CAS, leases, idempotency, force and concurrency."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from fixtures.fplus.contract_support import require_module


KEY = "fplus:btcusd:2026-08-24"
NOW = "2026-08-24T02:00:00Z"


def acquire(store, run_id, **overrides):
    payload = dict(
        key=KEY, run_id=run_id, now_utc=NOW, lease_seconds=300,
        cutoff_at_utc="2026-08-24T02:00:00Z", config_fingerprint="c" * 64,
        force=False, force_reason=None,
    )
    payload.update(overrides)
    return store.acquire(**payload)


def test_first_acquire_and_active_lease_contract(tmp_path):
    lock = require_module("tools.fplus_lock")
    store = lock.LocalLockStore(tmp_path)
    first = acquire(store, "run-1")
    second = acquire(store, "run-2")
    assert first["status"] == "claimed"
    assert first["generation"] == 1
    assert second["status"] == "in_progress"


def test_committed_rerun_returns_already_done_before_network(tmp_path):
    lock = require_module("tools.fplus_lock")
    store = lock.LocalLockStore(tmp_path)
    acquire(store, "run-1")
    store.commit(key=KEY, run_id="run-1", now_utc="2026-08-24T02:01:00Z",
                 artifact_hashes={"btcusd.md": "a" * 64, "chart.webp": "b" * 64})
    result = acquire(store, "run-2")
    assert result["status"] == "already_done"
    assert result["generation"] == 1


@pytest.mark.parametrize("workers", [2, 8])
def test_concurrent_workers_claim_exactly_one_generation(tmp_path, workers):
    lock = require_module("tools.fplus_lock")
    store = lock.LocalLockStore(tmp_path)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda i: acquire(store, f"run-{i}"), range(workers)))
    assert sum(item["status"] == "claimed" for item in results) == 1
    assert all(item["status"] in {"claimed", "in_progress"} for item in results)


def test_stale_lease_can_be_taken_over_but_active_lease_cannot(tmp_path):
    lock = require_module("tools.fplus_lock")
    store = lock.LocalLockStore(tmp_path)
    acquire(store, "run-1", now_utc="2026-08-24T01:00:00Z", lease_seconds=60)
    takeover = acquire(store, "run-2", now_utc="2026-08-24T02:00:00Z")
    assert takeover["status"] == "claimed"
    assert takeover["generation"] == 1
    assert takeover["supersedes_run_id"] == "run-1"


def test_force_requires_reason_supersedes_committed_and_not_active(tmp_path):
    lock = require_module("tools.fplus_lock")
    store = lock.LocalLockStore(tmp_path)
    acquire(store, "run-1")
    with pytest.raises(lock.LockContractError, match="reason"):
        acquire(store, "force-active", force=True, force_reason="")
    assert acquire(store, "force-active", force=True, force_reason="QA")["status"] == "in_progress"
    store.commit(key=KEY, run_id="run-1", now_utc="2026-08-24T02:01:00Z",
                 artifact_hashes={"btcusd.md": "a" * 64, "chart.webp": "b" * 64})
    forced = acquire(store, "run-2", now_utc="2026-08-24T02:02:00Z",
                     force=True, force_reason="QA correction")
    assert forced["status"] == "claimed"
    assert forced["generation"] == 2
    assert forced["supersedes_run_id"] == "run-1"


def test_blocked_retryable_does_not_consume_daily_job(tmp_path):
    lock = require_module("tools.fplus_lock")
    store = lock.LocalLockStore(tmp_path)
    acquire(store, "run-1")
    store.mark_retryable(key=KEY, run_id="run-1", status="blocked_retryable",
                         reason_codes=["STALE_15MIN"], now_utc="2026-08-24T02:01:00Z")
    retry = acquire(store, "run-2", now_utc="2026-08-24T02:02:00Z")
    assert retry["status"] == "claimed"


def test_heartbeat_extends_active_lease_for_owner_only(tmp_path):
    lock = require_module("tools.fplus_lock")
    store = lock.LocalLockStore(tmp_path)
    acquire(store, "run-1", lease_seconds=60)

    heartbeat = store.heartbeat(
        key=KEY, run_id="run-1", now_utc="2026-08-24T02:00:30Z",
        lease_seconds=60,
    )

    assert heartbeat["status"] == "claimed"
    assert heartbeat["heartbeat_at"] == "2026-08-24T02:00:30Z"
    assert heartbeat["lease_expires_at"] == "2026-08-24T02:01:30Z"
    still_active = acquire(store, "run-2", now_utc="2026-08-24T02:01:10Z")
    assert still_active["status"] == "in_progress"
    assert still_active["run_id"] == "run-1"


def test_heartbeat_rejects_non_owner_and_non_claimed_record(tmp_path):
    lock = require_module("tools.fplus_lock")
    store = lock.LocalLockStore(tmp_path)
    acquire(store, "run-1")
    with pytest.raises(lock.LockContractError, match="owner|active|lease"):
        store.heartbeat(
            key=KEY, run_id="run-2", now_utc="2026-08-24T02:00:30Z",
            lease_seconds=300,
        )
    store.commit(
        key=KEY, run_id="run-1", now_utc="2026-08-24T02:01:00Z",
        artifact_hashes={"btcusd.md": "a" * 64, "chart.webp": "b" * 64},
    )
    with pytest.raises(lock.LockContractError, match="owner|active|claimed|lease"):
        store.heartbeat(
            key=KEY, run_id="run-1", now_utc="2026-08-24T02:01:30Z",
            lease_seconds=300,
        )
