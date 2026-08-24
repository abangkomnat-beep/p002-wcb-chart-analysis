"""Side-effect ordering for the standalone BTCUSD F+ pipeline."""
from __future__ import annotations

from typing import Any, Mapping, Protocol


class PipelineContractError(RuntimeError):
    """Raised before work when orchestration inputs violate the contract."""


class PipelineAdapters(Protocol):
    def reconcile_startup(self, request: Mapping[str, Any]) -> Mapping[str, Any] | None: ...
    def acquire_production(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def acquire_shadow(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def fetch_snapshot(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def evaluate_data(self, snapshot: Mapping[str, Any], config: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def evaluate_news(self, snapshot: Mapping[str, Any], request: Mapping[str, Any], config: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def evaluate_candidates(self, snapshot: Mapping[str, Any], config: Mapping[str, Any]) -> list[Mapping[str, Any]]: ...
    def route(self, candidate_decisions: list[Mapping[str, Any]], gate_report: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def stage_artifacts(self, selected_plan: Mapping[str, Any], request: Mapping[str, Any], config: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def promote(self, staged: Mapping[str, Any], request: Mapping[str, Any], config: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def commit_production(self, request: Mapping[str, Any], promoted: Mapping[str, Any], selected_plan: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def mark_retryable(self, request: Mapping[str, Any], gate_report: Mapping[str, Any]) -> Any: ...
    def record_shadow(self, request: Mapping[str, Any], selected_plan: Mapping[str, Any], staged: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def heartbeat(self, request: Mapping[str, Any]) -> Mapping[str, Any] | None: ...


def validate_shadow_id(shadow_id: str) -> str:
    if shadow_id not in {"S01", "S02", "S03"}:
        raise PipelineContractError("shadow id must be one of S01, S02 or S03")
    return shadow_id


def _validate_request(request: Mapping[str, Any]) -> str:
    if request.get("asset") != "btcusd":
        raise PipelineContractError("asset must be btcusd")
    mode = request.get("mode")
    if mode not in {"shadow", "local"}:
        raise PipelineContractError("mode must be shadow or local")
    if mode == "shadow":
        if request.get("shadow_id") is None:
            raise PipelineContractError("shadow request requires shadow_id S01-S03")
        validate_shadow_id(str(request["shadow_id"]))
    if request.get("generation_request") == "force" and mode != "local":
        raise PipelineContractError("force is available in local mode only")
    return str(mode)


def _enforce_rollout(mode: str, config: Mapping[str, Any]) -> None:
    phase = (config.get("rollout") or {}).get("phase")
    if phase == "disabled":
        raise PipelineContractError("F+ rollout is disabled")
    if mode == "shadow" and phase != "shadow":
        raise PipelineContractError(f"shadow mode is forbidden in rollout phase {phase}")
    if mode == "local" and phase not in {"local", "cutover"}:
        raise PipelineContractError(f"local mode is forbidden in rollout phase {phase}")


def _optional_call(adapters: PipelineAdapters, name: str, *args: Any) -> Any:
    operation = getattr(adapters, name, None)
    return operation(*args) if callable(operation) else None


def run_pipeline(
    request: Mapping[str, Any], *, config: Mapping[str, Any], adapters: PipelineAdapters,
) -> dict[str, Any]:
    mode = _validate_request(request)
    _enforce_rollout(mode, config)
    if mode == "local":
        reconciled = _optional_call(adapters, "reconcile_startup", request)
        if reconciled and reconciled.get("status") in {"already_done", "committed"}:
            result = dict(reconciled)
            result["status"] = "already_done"
            return result
    acquired = (adapters.acquire_shadow(request) if mode == "shadow"
                else adapters.acquire_production(request))
    acquire_status = acquired.get("status")
    if acquire_status in {"already_done", "shadow_already_done", "in_progress"}:
        return dict(acquired)
    if acquire_status != "claimed":
        raise PipelineContractError(f"unexpected acquire status: {acquire_status}")

    snapshot = adapters.fetch_snapshot(request)
    _optional_call(adapters, "heartbeat", request)
    data_report = adapters.evaluate_data(snapshot, config)
    if data_report.get("price_data_status") != "pass":
        if mode == "local":
            adapters.mark_retryable(request, data_report)
        result = dict(data_report)
        result["status"] = "blocked_retryable"
        return result

    news_report = adapters.evaluate_news(snapshot, request, config)
    candidate_decisions = adapters.evaluate_candidates(snapshot, config)
    _optional_call(adapters, "heartbeat", request)
    gate_report = dict(data_report)
    gate_report["news"] = dict(news_report)
    reasons = list(data_report.get("reason_codes", []))
    reasons.extend(news_report.get("reason_codes", []))
    gate_report["reason_codes"] = list(dict.fromkeys(reasons))
    selected_plan = adapters.route(candidate_decisions, gate_report)
    if selected_plan.get("status") == "blocked_retryable":
        if mode == "local":
            adapters.mark_retryable(request, selected_plan)
        return dict(selected_plan)
    staged = adapters.stage_artifacts(selected_plan, request, config)
    _optional_call(adapters, "heartbeat", request)
    if mode == "shadow":
        return dict(adapters.record_shadow(request, selected_plan, staged))
    promoted = adapters.promote(staged, request, config)
    _optional_call(adapters, "heartbeat", request)
    adapters.commit_production(request, promoted, selected_plan)
    result = {
        "status": "no_trade_committed" if selected_plan.get("selection") == "NO_TRADE" else "committed",
        "selection": selected_plan.get("selection"),
        "run_id": request.get("run_id"),
        "trade_date": request.get("trade_date_bangkok"),
        "generation": acquired.get("generation"),
        "paths": promoted.get("paths", []),
        "hashes": promoted.get("hashes", {}),
        "reason_codes": list(selected_plan.get("reason_codes", [])),
    }
    return result
