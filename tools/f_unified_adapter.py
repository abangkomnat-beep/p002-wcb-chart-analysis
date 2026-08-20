"""Thin reversible production route for Style F (morning range brief).

The adapter delegates the existing F pipeline unchanged.  The unified route
only validates the F registry seam and supplies a declarative source plan;
``legacy`` remains the immediate rollback path.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from . import brief_pipeline, brief_story, brief_writer, zone_memory
from .result_envelope import Finding, ResultEnvelope
from .source_planner import SourcePlanner
from .unified_orchestrator import RunContext, UnifiedStyleOrchestrator
from .unified_registry import ArticleStylesRegistry, RegistryError, RegistryLoader

UNIT_ID = "F_BRIEF"
STYLE_ID = "f_morning_range"
STYLE_LETTER = "F"


class FMorningBriefAdapter:
    """Invoke the existing F pipeline once with its production arguments."""

    def __init__(self, *, publish_root: Path, cutoff_at: str,
                 runner_kwargs: Mapping[str, Any] | None = None) -> None:
        self.publish_root = Path(publish_root)
        self.cutoff_at = cutoff_at
        self.runner_kwargs = dict(runner_kwargs or {})

    def __call__(self, context, asset, _plan, _output, _state) -> ResultEnvelope:
        try:
            raw = brief_pipeline.run(
                asset=asset, style=brief_story.STYLE_F,
                publish_root=self.publish_root, cutoff_at=self.cutoff_at,
                **self.runner_kwargs,
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
                findings=[Finding("legacy_result", "fatal", "brief_pipeline.run returned a non-mapping result")],
            )
        status = "PASS" if raw.get("ok") else "FAIL"
        reason = "OK" if status == "PASS" else "LEGACY_VALIDATION_FAILED"
        return ResultEnvelope(context.run_id, asset, UNIT_ID, [STYLE_LETTER], status,
                              reason, legacy_result=raw)


@dataclass(frozen=True)
class FProductionRoute:
    """Validated F route; legacy mode is the immediate rollback path."""

    registry: ArticleStylesRegistry

    @classmethod
    def load(cls, path: Path | None = None) -> "FProductionRoute":
        path = path or (Path(__file__).resolve().parents[1] / "config" / "article_styles.json")
        registry = RegistryLoader().load(path)
        try:
            unit = registry.execution_units[UNIT_ID]
            entry = registry.styles[STYLE_ID]
        except KeyError as exc:
            raise RegistryError(f"missing Style F registration: {exc.args[0]}") from exc
        if tuple(unit.members) != (STYLE_ID,):
            raise RegistryError(f"{UNIT_ID} members must be {(STYLE_ID,)!r}, got {tuple(unit.members)!r}")
        if entry.letter != STYLE_LETTER or entry.adapter != "fg_brief":
            raise RegistryError(f"{UNIT_ID} must map to Style F with fg_brief adapter")
        if not unit.execute_once_per_asset:
            raise RegistryError(f"{UNIT_ID} must execute once per asset")
        return cls(registry)

    @property
    def migration_mode(self) -> str:
        return self.registry.execution_units[UNIT_ID].migration_mode

    def run_round(self, *, asset: str, publish_root: Path, cutoff_at: str,
                  _runner_kwargs: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        kwargs = dict(_runner_kwargs or {})
        if self.migration_mode == "legacy":
            return brief_pipeline.run(asset=asset, style=brief_story.STYLE_F,
                                      publish_root=publish_root, cutoff_at=cutoff_at,
                                      **kwargs)
        if self.migration_mode != "unified":
            raise RegistryError(f"production route refuses {UNIT_ID} mode {self.migration_mode!r}")
        plan = SourcePlanner().plan(
            execution_unit=UNIT_ID, asset=asset,
            requests=(
                {"provider": "WCB", "timeframe": "1h", "request_role": "brief_series",
                 "required_by": (STYLE_LETTER,)},
                {"provider": "WCB", "timeframe": "calendar", "request_role": "calendar",
                 "endpoint_kind": "calendar", "required_by": (STYLE_LETTER,)},
            ),
        )
        context = RunContext(
            run_id=f"daily-{cutoff_at}-{asset}-{UNIT_ID}", cutoff_at=cutoff_at,
            line="public", assets=(asset,), output_root=Path(publish_root),
            state_root=Path(zone_memory.STATE_DIR), mode="unified", no_publish=False,
        )
        f_registry = ArticleStylesRegistry(
            schema=self.registry.schema, styles={STYLE_ID: self.registry.styles[STYLE_ID]},
            execution_units={UNIT_ID: self.registry.execution_units[UNIT_ID]},
            source_schema=self.registry.source_schema,
        )
        result = UnifiedStyleOrchestrator({UNIT_ID: FMorningBriefAdapter(
            publish_root=Path(publish_root), cutoff_at=cutoff_at,
            runner_kwargs=kwargs,
        )}).execute(context, f_registry, {UNIT_ID: plan})
        if len(result) != 1:
            raise RuntimeError(f"{UNIT_ID}: expected one result, got {len(result)}")
        envelope = result[0]
        if envelope.legacy_result is None:
            message = envelope.findings[0].message if envelope.findings else envelope.reason_code
            raise RuntimeError(message)
        return envelope.legacy_result


__all__ = ["FMorningBriefAdapter", "FProductionRoute", "UNIT_ID", "STYLE_ID"]
