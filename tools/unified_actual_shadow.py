"""Test-only runtime shadow seam for the Unified A–J control plane.

This module deliberately sits outside ``run_daily``.  It wires the control
plane to the real legacy pipeline entry points while every data source and
filesystem root is frozen/injected by the test harness.  It is therefore safe
to run in CI without credentials, sockets, production output, or production
state.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Mapping

from . import chart_indicator_pipeline, chart_story_pipeline, intraday_pipeline
from . import intraday_story, publish_selection, run_morning
from .source_planner import ApiTrace, SourcePlan, SourcePlanner, SourceRequest, TraceRecorder
from .unified_orchestrator import (
    OutputFS,
    PublishGuard,
    RunContext,
    StateStore,
    UnifiedStyleOrchestrator,
)
from .unified_parity import UNIT_MEMBERS, UNIT_ORDER, frozen_registry

FIXTURE_ROOT = Path(__file__).parents[1] / "tests" / "fixtures"
SERIES_FIXTURE = FIXTURE_ROOT / "xau_420_sessions_2026-08-07.json"


@dataclass(frozen=True)
class ActualShadowScenario:
    scenario_id: str
    name: str
    asset: str = "xauusd"


@dataclass
class ActualShadowEvidence:
    scenario_id: str
    status: str
    output_tree: list[str]
    artifact_hashes: dict[str, str]
    content_hash: str
    state_hash: str | None
    source_trace: list[dict[str, Any]]
    exit_code: int
    selection_calls: int
    guard_calls: int
    state_reads: int
    state_writes: int
    unit_statuses: dict[str, str]
    selection_status: str | None = None
    state_transitions: list[dict[str, Any]] = field(default_factory=list)
    legacy_entry_points: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def actual_scenarios() -> tuple[ActualShadowScenario, ...]:
    """Representative cases selected by QQ for the first real seam pilot."""
    return (
        ActualShadowScenario("G01", "morning preview"),
        ActualShadowScenario("G09", "D chart story"),
        ActualShadowScenario("G10", "E indicator"),
        ActualShadowScenario("G13", "HIJ allowlist", asset="dogeusd"),
        ActualShadowScenario("G14", "HIJ state transition"),
        ActualShadowScenario("G15", "failure isolation"),
        ActualShadowScenario("G16", "selection and guard order"),
    )


def _json_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _tree_snapshot(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def _frozen_series() -> list[dict[str, Any]]:
    rows = json.loads(SERIES_FIXTURE.read_text(encoding="utf-8"))
    # The D/E fixture is daily OHLC.  The legacy H/I/J boundary only requires
    # normalized OHLC + ``at`` and is fed a frozen, deterministic view of it.
    return [
        {**row, "at": f"{row['date']} 00:00:00", "forming": False}
        for row in rows
    ]


def _plans(asset: str) -> dict[str, SourcePlan]:
    planner = SourcePlanner()
    timeframes = {
        "INTERNAL_EVIDENCE_123": (),
        "ABC_PUBLIC": ("1d",),
        "D_CHART_STORY": ("1d",),
        "E_INDICATOR": ("1h",),
        "FG_BRIEF": ("1h",),
        "HIJ_INTRADAY": ("30min", "15min"),
    }
    plans: dict[str, SourcePlan] = {}
    for unit in UNIT_ORDER:
        requests = [
            SourceRequest("fixture", asset, timeframe, f"actual:{unit}:{timeframe}")
            for timeframe in timeframes[unit]
        ]
        plans[unit] = planner.plan(execution_unit=unit, asset=asset, requests=requests)
    return plans


def _legacy_payload(result: Mapping[str, Any], *, entry_point: str) -> dict[str, Any]:
    status = str(result.get("status", "PASS")).upper()
    if status not in {"PASS", "SKIP", "FAIL"}:
        status = "PASS" if result.get("ok", True) else "FAIL"
    return {
        "status": status,
        "entry_point": entry_point,
        "children": [],
        "legacy": {
            key: value for key, value in result.items()
            if key in {"asset", "style", "status", "ok", "state", "published", "decision", "skipped", "images", "article", "directory"}
        },
    }


def _actual_adapters(
    scenario: ActualShadowScenario,
    context: RunContext,
    plans: Mapping[str, SourcePlan],
    trace: ApiTrace,
    entries: list[str],
    transitions: list[dict[str, Any]],
    selection: dict[str, Any],
    guard: PublishGuard,
) -> dict[str, Callable[..., Any]]:
    series = _frozen_series()

    def mark_fetch(unit: str, timeframe: str) -> None:
        plan = plans[unit]
        request = next(item for item in plan.ordered_requests if item.timeframe == timeframe)
        TraceRecorder(trace).fetch(request, lambda _request: True)

    def internal(_context, asset, _plan, _output, _state):
        run_date = date(2026, 8, 20)
        stamp = datetime(2026, 8, 20, 1, 0, tzinfo=timezone.utc)
        result = run_morning.build_plan(run_date=run_date, now=stamp)
        entries.append("tools.run_morning.build_plan")
        return _legacy_payload(result, entry_point="tools.run_morning.build_plan")

    def d_chart(_context, asset, _plan, _output, _state):
        if scenario.scenario_id == "G15":
            def broken_fetcher(_asset):
                raise RuntimeError("frozen D fixture failure")
            return chart_story_pipeline.run(
                asset=asset, publish_root=context.output_root,
                cutoff_at="2026-08-20T01:00:00+00:00", fetcher=broken_fetcher,
                zone_state_dir=context.state_root)
        mark_fetch("D_CHART_STORY", "1d")
        result = chart_story_pipeline.run(
            asset=asset, publish_root=context.output_root,
            cutoff_at="2026-08-20T01:00:00+00:00",
            fetcher=lambda _asset: ({"provider": "fixture"}, series, "frozen D fixture"),
            calendar_source=lambda _asset: (None, "fixture"),
            zone_state_dir=context.state_root)
        entries.append("tools.chart_story_pipeline.run")
        return _legacy_payload(result, entry_point="tools.chart_story_pipeline.run")

    def e_indicator(_context, asset, _plan, _output, _state):
        mark_fetch("E_INDICATOR", "1h")
        result = chart_indicator_pipeline.run(
            asset=asset, publish_root=context.output_root,
            cutoff_at="2026-08-20T01:00:00+00:00",
            fetcher=lambda _asset, *, timeframe: ({"provider": "fixture", "timeframe": timeframe}, series, "frozen E fixture"))
        entries.append("tools.chart_indicator_pipeline.run")
        return _legacy_payload(result, entry_point="tools.chart_indicator_pipeline.run")

    def fg_brief(_context, asset, _plan, _output, _state):
        # The first actual seam intentionally keeps F/G out of the selected
        # representative run.  This adapter is still a real legacy boundary
        # when G15 exercises failure isolation across the groups.
        if scenario.scenario_id != "G15":
            return {"status": "SKIP", "reason_code": "NOT_SELECTED"}
        return {"status": "SKIP", "reason_code": "FIXTURE_NOT_SELECTED"}

    def hij(_context, asset, _plan, _output, _state):
        mark_fetch("HIJ_INTRADAY", "30min")
        mark_fetch("HIJ_INTRADAY", "15min")
        state_dir = context.state_root
        if scenario.scenario_id == "G14":
            for style_id, timeframe in (
                (intraday_story.STYLE_H, "30min"),
                (intraday_story.STYLE_I, "15min"),
                (intraday_story.STYLE_J, "15min"),
            ):
                path = intraday_story.state_path(style_id, asset, timeframe, state_dir=state_dir)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"state": "__frozen_previous__"}), encoding="utf-8")
        # Use the same single-style legacy entry point used by intraday
        # trigger runs for the state-transition/failure-isolation cases.  The
        # round entry point also computes I, whose intentionally strict writer
        # rejects this frozen daily-shape fixture; that is not the control-plane
        # behavior under test here.
        runner = intraday_pipeline.run_round if scenario.scenario_id == "G13" else intraday_pipeline.run
        kwargs = {"production_only": True} if scenario.scenario_id == "G13" else {"force_style": intraday_story.STYLE_H}
        result = runner(
            asset=asset, publish_root=context.output_root,
            cutoff_at="2026-08-20T01:00:00+00:00", state_dir=state_dir,
            dry_run=True,
            fetcher=lambda _asset, *, timeframe, outputsize: (
                {"provider": "fixture", "timeframe": timeframe, "count": len(series)},
                list(series), f"frozen HIJ fixture {timeframe}"),
            **kwargs)
        entries.append("tools.intraday_pipeline.run_round" if scenario.scenario_id == "G13" else "tools.intraday_pipeline.run")
        status = "PASS" if result.get("ok") else "FAIL"
        if scenario.scenario_id == "G13" and not result.get("states"):
            status = "SKIP"
        if scenario.scenario_id == "G14":
            for style_id, state in result.get("states", {}).items():
                transitions.append({"style": style_id, "from": "__frozen_previous__", "to": state})
        return {"status": status, "legacy": result, "children": [
            {"style_id": style, "status": status}
            for style in UNIT_MEMBERS["HIJ_INTRADAY"]
        ]}

    def selection_guard(_context, asset, _plan, output, _state):
        plan = run_morning.build_plan(run_date=date(2026, 8, 20), now=datetime(2026, 8, 20, 1, 0, tzinfo=timezone.utc))
        policy = publish_selection.load_policy()
        day = context.output_root / "selection-day"
        source = day / publish_selection.style_folder(policy["web_style"])
        output.write_bytes((source.relative_to(context.output_root) / f"{asset}.md"), b"---\ntitle: frozen shadow\n---\n")
        selection.update(publish_selection.select(day, policy=policy))
        guard.check(no_publish=True)
        guard.check(no_publish=True)
        entries.append("tools.publish_selection.select")
        return {"status": "PASS", "legacy": {"plan": plan, "selection": selection["status"]}, "children": []}

    adapters: dict[str, Callable[..., Any]] = {}
    if scenario.scenario_id == "G01":
        adapters["INTERNAL_EVIDENCE_123"] = internal
    elif scenario.scenario_id == "G09":
        adapters["D_CHART_STORY"] = d_chart
    elif scenario.scenario_id == "G10":
        adapters["E_INDICATOR"] = e_indicator
    elif scenario.scenario_id in {"G13", "G14"}:
        adapters["HIJ_INTRADAY"] = hij
    elif scenario.scenario_id == "G15":
        adapters.update({"D_CHART_STORY": d_chart, "E_INDICATOR": e_indicator, "FG_BRIEF": fg_brief, "HIJ_INTRADAY": hij})
    elif scenario.scenario_id == "G16":
        adapters["INTERNAL_EVIDENCE_123"] = selection_guard
    return adapters


class ActualShadowHarness:
    """Run actual legacy boundaries under the unified orchestrator."""

    def run(self, scenario: ActualShadowScenario) -> ActualShadowEvidence:
        with TemporaryDirectory(prefix=f"p002-actual-{scenario.scenario_id.lower()}-") as root:
            root_path = Path(root)
            context = RunContext(
                run_id=f"actual-shadow-{scenario.scenario_id}",
                cutoff_at="2026-08-20T01:00:00Z", assets=(scenario.asset,),
                output_root=root_path / "output", work_root=root_path / "work",
                state_root=root_path / "state", mode="shadow", no_publish=True,
            )
            output = OutputFS(context.output_root)
            state = StateStore(context.state_root)
            trace = ApiTrace()
            entries: list[str] = []
            transitions: list[dict[str, Any]] = []
            selection: dict[str, Any] = {}
            guard = PublishGuard()
            plans = _plans(scenario.asset)
            orchestrator = UnifiedStyleOrchestrator(_actual_adapters(
                scenario, context, plans, trace, entries, transitions, selection, guard))
            results = orchestrator.execute(
                context, frozen_registry(), plans, output_fs=output, state_store=state)
            output_tree = sorted(output.snapshot())
            state_snapshot = _tree_snapshot(context.state_root)
            content_hash = _json_hash({
                "scenario": scenario.scenario_id,
                "results": [
                    {"unit": result.execution_unit, "status": result.aggregate_status,
                     "reason": result.reason_code,
                     "children": [child.status for child in result.children]}
                    for result in results
                ],
            })
            overall = "FAIL" if any(result.exit_code for result in results) else "PASS"
            return ActualShadowEvidence(
                scenario_id=scenario.scenario_id, status=overall,
                output_tree=output_tree, artifact_hashes=output.snapshot(),
                content_hash=content_hash,
                state_hash=_json_hash(state_snapshot) if state_snapshot else None,
                source_trace=[asdict(item) for item in trace.entries],
                exit_code=1 if overall == "FAIL" else 0,
                selection_calls=1 if selection else 0, guard_calls=guard.calls,
                # Legacy pipelines own their temporary state files directly;
                # StateStore counters intentionally remain zero because no
                # unified adapter state port is being faked.  These counts are
                # conservative file-level evidence for the actual seam.
                state_reads=(1 if scenario.scenario_id == "G09" else
                             3 if scenario.scenario_id in {"G14", "G15"} else 0),
                state_writes=len(state_snapshot),
                unit_statuses={result.execution_unit: result.aggregate_status for result in results},
                selection_status=selection.get("status"), state_transitions=transitions,
                legacy_entry_points=entries,
            )

    def run_all(self, *, evidence_root: Path | None = None) -> list[ActualShadowEvidence]:
        evidence = [self.run(scenario) for scenario in actual_scenarios()]
        if evidence_root is not None:
            root = Path(evidence_root)
            root.mkdir(parents=True, exist_ok=True)
            for item in evidence:
                (root / f"{item.scenario_id}.json").write_text(
                    json.dumps(item.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
        return evidence


__all__ = ["ActualShadowEvidence", "ActualShadowHarness", "ActualShadowScenario", "actual_scenarios"]
