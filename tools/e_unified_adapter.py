"""Thin reversible production route for Style E (indicator chart).

The adapter delegates the complete legacy E pipeline unchanged.  The route
only selects the unified control plane and validates the E registry seam
before any data or filesystem side effect; ``legacy`` is the rollback path.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from . import chart_indicator_pipeline, chart_indicator_writer, zone_memory
from .result_envelope import Finding, ResultEnvelope
from .source_planner import SourcePlanner
from .unified_orchestrator import RunContext, UnifiedStyleOrchestrator
from .unified_registry import ArticleStylesRegistry, RegistryError, RegistryLoader

UNIT_ID = "E_INDICATOR"
STYLE_ID = chart_indicator_writer.STYLE_ID
STYLE_LETTER = "E"


class EIndicatorAdapter:
    """Invoke the existing E pipeline once with production arguments."""

    def __init__(self, *, publish_root: Path, cutoff_at: str,
                 runner_kwargs: Mapping[str, Any] | None = None) -> None:
        self.publish_root = Path(publish_root)
        self.cutoff_at = cutoff_at
        self.runner_kwargs = dict(runner_kwargs or {})

    def __call__(self, context, asset, _plan, _output, _state) -> ResultEnvelope:
        try:
            raw = chart_indicator_pipeline.run(
                asset=asset, publish_root=self.publish_root,
                cutoff_at=self.cutoff_at, **self.runner_kwargs,
            )
        except Exception as exc:
            return ResultEnvelope.fail(
                context.run_id, asset, UNIT_ID, [STYLE_LETTER],
                reason_code="LEGACY_EXCEPTION", exception=exc,
                findings=[Finding("legacy_exception", "fatal", str(exc))],
            )
        if not isinstance(raw, Mapping):
            return ResultEnvelope.fail(
                context.run_id, asset, UNIT_ID, [STYLE_LETTER],
                reason_code="LEGACY_RESULT_INVALID",
                findings=[Finding("legacy_result", "fatal", "chart_indicator_pipeline.run returned a non-mapping result")],
            )
        status = "PASS" if raw.get("status") == "pass" else "FAIL"
        reason = "OK" if status == "PASS" else "LEGACY_VALIDATION_FAILED"
        return ResultEnvelope(context.run_id, asset, UNIT_ID, [STYLE_LETTER], status,
                              reason, legacy_result=raw)


@dataclass(frozen=True)
class EProductionRoute:
    """Validated E route; legacy mode is the immediate rollback path."""

    registry: ArticleStylesRegistry

    @classmethod
    def load(cls, path: Path | None = None) -> "EProductionRoute":
        path = path or (Path(__file__).resolve().parents[1] / "config" / "article_styles.json")
        registry = RegistryLoader().load(path)
        try:
            unit = registry.execution_units[UNIT_ID]
            entry = registry.styles[STYLE_ID]
        except KeyError as exc:
            raise RegistryError(f"missing Style E registration: {exc.args[0]}") from exc
        if tuple(unit.members) != (STYLE_ID,):
            raise RegistryError(f"{UNIT_ID} members must be {(STYLE_ID,)!r}, got {tuple(unit.members)!r}")
        if entry.letter != STYLE_LETTER or entry.adapter != "e_indicator":
            raise RegistryError(f"{UNIT_ID} must map to Style E with e_indicator adapter")
        if not unit.execute_once_per_asset:
            raise RegistryError(f"{UNIT_ID} must execute once per asset")
        return cls(registry)

    @property
    def migration_mode(self) -> str:
        return self.registry.execution_units[UNIT_ID].migration_mode

    def run_round(self, *, asset: str, publish_root: Path, cutoff_at: str,
                  _runner_kwargs: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        if self.migration_mode == "legacy":
            return chart_indicator_pipeline.run(asset=asset, publish_root=publish_root,
                                                cutoff_at=cutoff_at, **dict(_runner_kwargs or {}))
        if self.migration_mode != "unified":
            raise RegistryError(f"production route refuses {UNIT_ID} mode {self.migration_mode!r}")
        plan = SourcePlanner().plan(
            execution_unit=UNIT_ID, asset=asset,
            requests=({"provider": "WCB", "timeframe": "1h",
                        "request_role": "indicator_series", "required_by": (STYLE_LETTER,)},),
        )
        context = RunContext(
            run_id=f"daily-{cutoff_at}-{asset}-{UNIT_ID}", cutoff_at=cutoff_at,
            line="public", assets=(asset,), output_root=Path(publish_root),
            state_root=Path(zone_memory.STATE_DIR), mode="unified", no_publish=False,
        )
        e_registry = ArticleStylesRegistry(
            schema=self.registry.schema, styles={STYLE_ID: self.registry.styles[STYLE_ID]},
            execution_units={UNIT_ID: self.registry.execution_units[UNIT_ID]},
            source_schema=self.registry.source_schema,
        )
        result = UnifiedStyleOrchestrator({UNIT_ID: EIndicatorAdapter(
            publish_root=Path(publish_root), cutoff_at=cutoff_at,
            runner_kwargs=_runner_kwargs,
        )}).execute(context, e_registry, {UNIT_ID: plan})
        if len(result) != 1:
            raise RuntimeError(f"{UNIT_ID}: expected one result, got {len(result)}")
        envelope = result[0]
        if envelope.legacy_result is None:
            message = envelope.findings[0].message if envelope.findings else envelope.reason_code
            raise RuntimeError(message)
        return envelope.legacy_result


__all__ = ["EIndicatorAdapter", "EProductionRoute", "UNIT_ID", "STYLE_ID"]
