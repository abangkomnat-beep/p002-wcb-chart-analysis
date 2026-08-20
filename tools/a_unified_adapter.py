"""Thin reversible production route for Style A (public WCB article).

Style A currently shares the legacy ``build_public`` implementation with B/C.
This adapter adds only the unified control-plane seam; it does not alter the
legacy writer, validation, output layout, or publication behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from . import build_daily_package
from .result_envelope import Finding, ResultEnvelope
from .source_planner import SourcePlanner
from .unified_orchestrator import RunContext, UnifiedStyleOrchestrator
from .unified_registry import ArticleStylesRegistry, RegistryError, RegistryLoader

UNIT_ID = "A_PUBLIC"
STYLE_ID = "a_standard"
STYLE_LETTER = "A"


class APublicAdapter:
    """Invoke the existing public A/B/C builder exactly once."""

    def __init__(self, *, batch_id: str, output_root: Path,
                 publish_root: Path | None, cutoff_at: str,
                 snapshot_path: Path | None = None,
                 calendar_feed_enabled: bool = True) -> None:
        self.batch_id = batch_id
        self.output_root = Path(output_root)
        self.publish_root = Path(publish_root) if publish_root is not None else None
        self.cutoff_at = cutoff_at
        self.snapshot_path = Path(snapshot_path) if snapshot_path is not None else None
        self.calendar_feed_enabled = calendar_feed_enabled

    def __call__(self, context, asset, _plan, _output, _state) -> ResultEnvelope:
        kwargs: dict[str, Any] = {
            "batch_id": self.batch_id,
            "output_root": self.output_root,
            "publish_root": self.publish_root,
            "snapshot_path": self.snapshot_path,
            "cutoff_at": self.cutoff_at,
        }
        if self.calendar_feed_enabled:
            kwargs["calendar_feed_fetcher"] = lambda _asset: None
        try:
            raw = build_daily_package.build_public(asset, **kwargs)
        except Exception as exc:  # noqa: BLE001 — normalize legacy failures
            return ResultEnvelope.fail(
                context.run_id, asset, UNIT_ID, [STYLE_LETTER],
                reason_code="LEGACY_EXCEPTION", exception=exc,
                findings=[Finding("legacy_exception", "fatal", str(exc))],
            )
        if not isinstance(raw, Mapping):
            return ResultEnvelope.fail(
                context.run_id, asset, UNIT_ID, [STYLE_LETTER],
                reason_code="LEGACY_RESULT_INVALID",
                findings=[Finding("legacy_result", "fatal", "build_public returned a non-mapping result")],
            )
        return ResultEnvelope.from_legacy(
            raw, run_id=context.run_id, asset=asset,
            execution_unit=UNIT_ID, style_ids=[STYLE_LETTER],
        )


@dataclass(frozen=True)
class AProductionRoute:
    """Validated A route; ``legacy`` is the immediate rollback path."""

    registry: ArticleStylesRegistry

    @classmethod
    def load(cls, path: Path | None = None) -> "AProductionRoute":
        path = path or (Path(__file__).resolve().parents[1] / "config" / "article_styles.json")
        registry = RegistryLoader().load(path)
        try:
            unit = registry.execution_units[UNIT_ID]
            entry = registry.styles[STYLE_ID]
        except KeyError as exc:
            raise RegistryError(f"missing Style A registration: {exc.args[0]}") from exc
        if tuple(unit.members) != (STYLE_ID,):
            raise RegistryError(f"{UNIT_ID} members must be {(STYLE_ID,)!r}, got {tuple(unit.members)!r}")
        if entry.letter != STYLE_LETTER or entry.adapter != "abc_public":
            raise RegistryError(f"{UNIT_ID} must map to Style A with abc_public adapter")
        if not unit.execute_once_per_asset:
            raise RegistryError(f"{UNIT_ID} must execute once per asset")
        return cls(registry)

    @property
    def migration_mode(self) -> str:
        return self.registry.execution_units[UNIT_ID].migration_mode

    def run_round(self, *, asset: str, batch_id: str, output_root: Path,
                  publish_root: Path | None, cutoff_at: str,
                  snapshot_path: Path | None = None,
                  calendar_feed_enabled: bool = True) -> Mapping[str, Any]:
        if self.migration_mode == "legacy":
            return build_daily_package.build_public(
                asset, batch_id=batch_id, output_root=Path(output_root),
                publish_root=Path(publish_root) if publish_root is not None else None,
                snapshot_path=snapshot_path, cutoff_at=cutoff_at,
                calendar_feed_fetcher=(lambda _asset: None) if calendar_feed_enabled else None,
            )
        if self.migration_mode != "unified":
            raise RegistryError(f"production route refuses {UNIT_ID} mode {self.migration_mode!r}")
        plan = SourcePlanner().plan(
            execution_unit=UNIT_ID, asset=asset,
            requests=({"provider": "WCB", "timeframe": "1d",
                        "request_role": "public_snapshot", "required_by": (STYLE_LETTER,)},),
        )
        context = RunContext(
            run_id=f"daily-{cutoff_at}-{asset}-{UNIT_ID}", cutoff_at=cutoff_at,
            line="public", assets=(asset,), output_root=Path(output_root),
            mode="unified", no_publish=publish_root is None,
        )
        a_registry = ArticleStylesRegistry(
            schema=self.registry.schema,
            styles={STYLE_ID: self.registry.styles[STYLE_ID]},
            execution_units={UNIT_ID: self.registry.execution_units[UNIT_ID]},
            source_schema=self.registry.source_schema,
        )
        result = UnifiedStyleOrchestrator({UNIT_ID: APublicAdapter(
            batch_id=batch_id, output_root=Path(output_root),
            publish_root=publish_root, cutoff_at=cutoff_at,
            snapshot_path=snapshot_path, calendar_feed_enabled=calendar_feed_enabled,
        )}).execute(context, a_registry, {UNIT_ID: plan})
        if len(result) != 1:
            raise RuntimeError(f"{UNIT_ID}: expected one result, got {len(result)}")
        envelope = result[0]
        if envelope.legacy_result is None:
            message = envelope.findings[0].message if envelope.findings else envelope.reason_code
            raise RuntimeError(message)
        return envelope.legacy_result


__all__ = ["APublicAdapter", "AProductionRoute", "UNIT_ID", "STYLE_ID"]
