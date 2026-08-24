"""Concrete manual runtime for BTCUSD F+ Foundation and Shadow.

No work starts on import. Network access is performed only when a user invokes
``FPlusRuntime.run`` without an injected snapshot provider.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

from tools.fplus_adapters import ConcreteFPlusAdapters
from tools.fplus_artifacts import ArtifactTransaction
from tools.fplus_candidates import evaluate_candidate
from tools.fplus_config import validate_config
from tools.fplus_contracts import FPlusRunRequest
from tools.fplus_lock import LocalLockStore
from tools.fplus_pipeline import run_pipeline
from tools.fplus_risk import evaluate_risk


DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "fplus_btc_daily.json"


def reconcile_startup(
    *, key: str, run_id: str, now_utc: str, relative_final_dir: str | Path,
    lock_store: LocalLockStore, artifact_store: ArtifactTransaction,
) -> dict[str, Any]:
    """Reconcile a verified visible generation with its pre-existing lock owner."""
    recovered = artifact_store.recover(relative_final_dir=relative_final_dir)
    manifest = recovered["manifest"]
    if str(manifest.get("run_id")) != str(run_id):
        raise RuntimeError("artifact journal run_id differs from startup reconciliation owner")
    hashes = {item["name"]: item["sha256"] for item in manifest.get("files", [])}
    final = Path(recovered["final_dir"])
    if not artifact_store._manifest_matches(final, manifest):  # noqa: SLF001
        raise RuntimeError("recovered final directory does not match the journal manifest")
    paths = [str(final / item["name"]) for item in manifest.get("files", [])]
    record = lock_store.reconcile_committed(
        key=key, run_id=run_id, generation=int(manifest["generation"]),
        now_utc=now_utc, artifact_hashes=hashes, artifact_paths=paths,
    )
    artifact_store.mark_lock_committed(relative_final_dir=relative_final_dir)
    return {**record, "status": "committed", "reconciled": True,
            "artifact_hashes": hashes, "paths": paths}


class ConcreteRuntimeAdapters(ConcreteFPlusAdapters):
    """The twelve concrete pipeline ports plus injectable offline snapshot input."""

    def __init__(
        self, config: Mapping[str, Any], *,
        snapshot_provider: Callable[[FPlusRunRequest], Mapping[str, Any]] | None = None,
        request_object: FPlusRunRequest | None = None,
    ):
        super().__init__(config)
        self.snapshot_provider = snapshot_provider
        self.request_object = request_object

    def fetch_snapshot(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if self.snapshot_provider is None:
            return super().fetch_snapshot(request)
        if self.request_object is None:
            raise RuntimeError("injected snapshot provider requires the immutable request")
        snapshot = dict(self.snapshot_provider(self.request_object))
        self._snapshot = snapshot
        return snapshot

    def build_replay_adapter(self, snapshot_path: str | Path) -> "ConcreteRuntimeAdapters":
        """Create a fresh offline decision adapter from an immutable snapshot file."""
        path = Path(snapshot_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"persisted replay snapshot not found: {path}")
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(snapshot, dict):
            raise RuntimeError("persisted replay snapshot must be a JSON object")
        adapter = ConcreteRuntimeAdapters(self.config)
        adapter._snapshot = snapshot  # noqa: SLF001 - replay provenance is loaded locally
        return adapter

    def evaluate_candidates(
        self, snapshot: Mapping[str, Any], config: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        candidate_inputs = snapshot.get("candidate_inputs")
        if not isinstance(candidate_inputs, Mapping):
            return super().evaluate_candidates(snapshot, config)
        narratives = dict(snapshot.get("narratives") or {})
        decisions: list[dict[str, Any]] = []
        for name in ("J", "I", "E_LOGIC", "F"):
            item = candidate_inputs[name]
            risk = evaluate_risk(
                thresholds=self.risk_contract["thresholds"], **dict(item["risk"]))
            decision = evaluate_candidate(
                name, evidence=dict(item["evidence"]), risk_result=risk)
            decision["summary"] = {
                "bias_h4": "up" if "ขาขึ้น" in narratives.get("bias_h4", "") else "neutral",
                "bias_h1": "up" if "ขาขึ้น" in narratives.get("bias_h4", "") else "neutral",
                "m30": narratives.get("evidence_m30", ""),
                "m15": narratives.get("trigger_m15", ""),
                "invalidation": narratives.get("invalidation", ""),
                "setup_h1": narratives.get("setup_h1", ""),
            }
            decisions.append(decision)
        self._candidate_decisions = decisions
        return [dict(item) for item in decisions]


class FPlusRuntime:
    """Manual runtime facade used by the CLI and offline synthetic acceptance tests."""

    def __init__(
        self, *, config_path: str | Path = DEFAULT_CONFIG,
        snapshot_provider: Callable[[FPlusRunRequest], Mapping[str, Any]] | None = None,
    ):
        self.config_path = Path(config_path)
        self.config = validate_config(json.loads(self.config_path.read_text(encoding="utf-8")))
        self.snapshot_provider = snapshot_provider

    def run(self, request: FPlusRunRequest) -> dict[str, Any]:
        if not isinstance(request, FPlusRunRequest):
            raise TypeError("FPlusRuntime.run requires an immutable FPlusRunRequest")
        adapters = ConcreteRuntimeAdapters(
            self.config, snapshot_provider=self.snapshot_provider, request_object=request)
        return run_pipeline(request.to_dict(), config=self.config, adapters=adapters)
