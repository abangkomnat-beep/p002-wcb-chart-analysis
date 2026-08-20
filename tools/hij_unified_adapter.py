"""Thin production adapter and reversible route for ``HIJ_INTRADAY``.

The adapter deliberately delegates all market-data, selection, rendering,
state-memory, cleanup and validation behaviour to the legacy
``intraday_pipeline.run_round`` entry point.  The registry toggle changes only
which control plane invokes that one legacy call.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from . import intraday_pipeline, intraday_story
from .result_envelope import Finding, ResultEnvelope
from .source_planner import SourcePlanner
from .unified_orchestrator import RunContext, UnifiedStyleOrchestrator
from .unified_registry import ArticleStylesRegistry, RegistryError, RegistryLoader

UNIT_ID = "HIJ_INTRADAY"
STYLE_LETTERS = ("H", "I", "J")
STYLE_IDS = (
    intraday_story.STYLE_H,
    intraday_story.STYLE_I,
    intraday_story.STYLE_J,
)


def _child_envelopes(raw: Mapping[str, Any], *, run_id: str,
                     asset: str) -> list[ResultEnvelope]:
    """Map the multi-style legacy result without changing its semantics."""
    articles = {str(item.get("style")): item for item in raw.get("articles", ())}
    skipped = {str(item.get("style")): item for item in raw.get("skipped", ())}
    children: list[ResultEnvelope] = []
    for style_id, letter in zip(STYLE_IDS, STYLE_LETTERS):
        if style_id in articles:
            article = articles[style_id]
            status = "PASS" if article.get("ok") else "FAIL"
            reason = "OK" if status == "PASS" else "LEGACY_VALIDATION_FAILED"
            children.append(ResultEnvelope(
                run_id, asset, UNIT_ID, [letter], status, reason,
                legacy_result=article,
            ))
        elif style_id in skipped:
            children.append(ResultEnvelope.skip(
                run_id, asset, UNIT_ID, [letter], "LEGACY_SKIPPED",
                legacy_result=skipped[style_id],
            ))
        else:
            children.append(ResultEnvelope.skip(
                run_id, asset, UNIT_ID, [letter], "NO_NEW_STORY",
            ))
    return children


class HIJIntradayAdapter:
    """Invoke the existing group entry point exactly once for one asset."""

    def __init__(self, *, publish_root: Path, cutoff_at: str,
                 runner_kwargs: Mapping[str, Any] | None = None) -> None:
        self.publish_root = Path(publish_root)
        self.cutoff_at = cutoff_at
        self.runner_kwargs = dict(runner_kwargs or {})

    def __call__(self, context, asset, _plan, _output, _state) -> ResultEnvelope:
        try:
            raw = intraday_pipeline.run_round(
                asset=asset,
                publish_root=self.publish_root,
                cutoff_at=self.cutoff_at,
                **self.runner_kwargs,
            )
        except Exception as exc:  # keep the legacy per-asset failure boundary
            return ResultEnvelope.fail(
                context.run_id, asset, UNIT_ID, STYLE_LETTERS,
                reason_code="LEGACY_EXCEPTION", exception=exc,
                findings=[Finding("legacy_exception", "fatal", str(exc))],
            )

        if not isinstance(raw, Mapping):
            return ResultEnvelope.fail(
                context.run_id, asset, UNIT_ID, STYLE_LETTERS,
                reason_code="LEGACY_RESULT_INVALID",
                findings=[Finding(
                    "legacy_result", "fatal",
                    "intraday_pipeline.run_round returned a non-mapping result",
                )],
            )
        children = _child_envelopes(raw, run_id=context.run_id, asset=asset)
        if not raw.get("ok"):
            status, reason = "FAIL", "LEGACY_FAILURE"
        elif raw.get("articles"):
            status, reason = "PASS", "OK"
        else:
            status, reason = "SKIP", "NO_NEW_STORY"
        return ResultEnvelope(
            context.run_id, asset, UNIT_ID, list(STYLE_LETTERS), status, reason,
            legacy_result=raw, children=children,
        )


@dataclass(frozen=True)
class HIJProductionRoute:
    """Validated route selected before any H/I/J side effect."""

    registry: ArticleStylesRegistry

    @classmethod
    def load(cls, path: Path = intraday_story.STYLES_PATH) -> "HIJProductionRoute":
        registry = RegistryLoader().load(path)
        try:
            unit = registry.execution_units[UNIT_ID]
        except KeyError as exc:
            raise RegistryError(f"missing execution unit {UNIT_ID}") from exc
        if tuple(unit.members) != STYLE_IDS:
            raise RegistryError(
                f"{UNIT_ID} members must be {STYLE_IDS!r}, got {tuple(unit.members)!r}"
            )
        entries = [registry.styles[style_id] for style_id in STYLE_IDS]
        if tuple(entry.letter for entry in entries) != STYLE_LETTERS:
            raise RegistryError(f"{UNIT_ID} must map to Style H/I/J in order")
        if any(entry.adapter != "hij_intraday" for entry in entries):
            raise RegistryError(f"{UNIT_ID} styles must use hij_intraday adapter")
        if not unit.execute_once_per_asset:
            raise RegistryError(f"{UNIT_ID} must execute once per asset")
        return cls(registry)

    @property
    def migration_mode(self) -> str:
        return self.registry.execution_units[UNIT_ID].migration_mode

    def run_round(self, *, asset: str, publish_root: Path,
                  cutoff_at: str,
                  _runner_kwargs: Mapping[str, Any] | None = None
                  ) -> Mapping[str, Any]:
        """Use direct legacy route for rollback, otherwise the unified adapter."""
        if self.migration_mode == "legacy":
            return intraday_pipeline.run_round(
                asset=asset, publish_root=publish_root, cutoff_at=cutoff_at,
                **dict(_runner_kwargs or {}),
            )
        if self.migration_mode != "unified":
            raise RegistryError(
                f"production route refuses {UNIT_ID} mode {self.migration_mode!r}"
            )

        plan = SourcePlanner().plan(
            execution_unit=UNIT_ID,
            asset=asset,
            requests=(
                {"provider": "WCB", "timeframe": "30min",
                 "request_role": "context_series", "required_by": STYLE_LETTERS},
                {"provider": "WCB", "timeframe": "15min",
                 "request_role": "trigger_series", "required_by": STYLE_LETTERS},
            ),
        )
        context = RunContext(
            run_id=f"daily-{cutoff_at}-{asset}-{UNIT_ID}",
            cutoff_at=cutoff_at,
            line="public",
            assets=(asset,),
            output_root=Path(publish_root),
            state_root=intraday_story.STATE_DIR,
            mode="unified",
            no_publish=False,
        )
        # The registry may contain other migrated units (for example CP3 D).
        # Keep this CP2 route scoped to HIJ so one asset yields one envelope.
        hij_registry = ArticleStylesRegistry(
            schema=self.registry.schema,
            styles={style_id: self.registry.styles[style_id] for style_id in STYLE_IDS},
            execution_units={UNIT_ID: self.registry.execution_units[UNIT_ID]},
            source_schema=self.registry.source_schema,
        )
        result = UnifiedStyleOrchestrator({
            UNIT_ID: HIJIntradayAdapter(
                publish_root=Path(publish_root), cutoff_at=cutoff_at,
                runner_kwargs=_runner_kwargs,
            ),
        }).execute(context, hij_registry, {UNIT_ID: plan})
        if len(result) != 1:
            raise RuntimeError(f"{UNIT_ID}: expected one result, got {len(result)}")
        envelope = result[0]
        if envelope.legacy_result is None:
            message = (envelope.findings[0].message if envelope.findings
                       else envelope.reason_code)
            raise RuntimeError(message)
        return envelope.legacy_result


__all__ = [
    "HIJIntradayAdapter", "HIJProductionRoute", "STYLE_IDS",
    "STYLE_LETTERS", "UNIT_ID",
]
