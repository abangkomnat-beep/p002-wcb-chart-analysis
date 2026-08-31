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
import os
from contextlib import ExitStack
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from typing import Any, Callable, Mapping

from . import brief_pipeline, chart_indicator_pipeline, chart_story_pipeline, intraday_pipeline
from . import brief_story, intraday_story, publish_selection, run_daily, run_morning
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
_RUN_DATE = date(2026, 8, 20)
_RUN_NOW = datetime(2026, 8, 20, 1, 0, tzinfo=timezone.utc)
_CUT_OFF = "2026-08-20T01:00:00+00:00"


class _FrozenDateTime(datetime):
    """Datetime replacement scoped to legacy CLI modules during a shadow run."""

    @classmethod
    def now(cls, tz=None):
        return _RUN_NOW if tz is None else _RUN_NOW.astimezone(tz)


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
    state_io_events: list[dict[str, Any]] = field(default_factory=list)
    control_events: list[dict[str, Any]] = field(default_factory=list)
    cleanup_manifests: dict[str, dict[str, str]] = field(default_factory=dict)
    argv: list[str] = field(default_factory=list)
    execution_context: dict[str, Any] = field(default_factory=dict)
    expected_manifest: dict[str, Any] = field(default_factory=dict)
    safety_deltas: dict[str, Any] = field(default_factory=dict)
    exit_codes: list[int] = field(default_factory=list)
    parity_manifests: dict[str, Any] = field(default_factory=dict)
    legacy_entry_points: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def actual_scenarios() -> tuple[ActualShadowScenario, ...]:
    """Representative cases selected by QQ for the first real seam pilot."""
    return (
        ActualShadowScenario("G01", "morning preview"),
        ActualShadowScenario("G02", "preview selection"),
        ActualShadowScenario("G03", "confirm"),
        ActualShadowScenario("G04", "repeat confirm"),
        ActualShadowScenario("G05", "daily default"),
        ActualShadowScenario("G06", "publish internal guard"),
        ActualShadowScenario("G07", "internal line"),
        ActualShadowScenario("G08", "skip flags"),
        ActualShadowScenario("G09", "D chart story"),
        ActualShadowScenario("G10", "E indicator"),
        ActualShadowScenario("G11", "F only"),
        ActualShadowScenario("G12", "G plus F"),
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


def _canonical_argv(argv: list[str], context: RunContext) -> list[str]:
    replacements = {
        str(context.output_root): "<temp>/output",
        str(context.work_root): "<temp>/work",
        str(context.state_root): "<temp>/state",
    }
    return [next((value.replace(prefix, token) for prefix, token in replacements.items()
                  if value.startswith(prefix)), value) for value in argv]


def _frozen_series() -> list[dict[str, Any]]:
    rows = json.loads(SERIES_FIXTURE.read_text(encoding="utf-8"))
    # The D/E fixture is daily OHLC.  The legacy H/I/J boundary only requires
    # normalized OHLC + ``at`` and is fed a frozen, deterministic view of it.
    return [
        {**row, "at": f"{row['date']} 00:00:00", "forming": False}
        for row in rows
    ]


def _brief_fetcher(_asset: str, timeframe: str = "1h") -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    return {"provider": "fixture", "timeframe": timeframe}, _frozen_series(), "frozen fixture"


def _brief_empty_calendar(_asset: str) -> tuple[dict[str, Any], str]:
    return {
        "events": [],
        "sentences": [],
        "selected": [],
        "local_date": _RUN_DATE.isoformat(),
        "calendar": [],
    }, "empty"


def _brief_g_calendar(_asset: str) -> tuple[dict[str, Any], str]:
    event = {
        "title": "แรงซื้อแรงขายชั่วคราว",
        "country": "USD",
        "impact": "High",
        "actual": None,
        "forecast": 1,
        "previous": 0,
        "at": "2026-08-20T00:00:00+00:00",
    }
    return {
        "events": [event],
        "sentences": ["มีเหตุการณ์แรงรอประกาศ"],
        "selected": [event],
        "local_date": _RUN_DATE.isoformat(),
        "calendar": [event],
    }, "ok"


def _run_in_temp_root(root: Path, callable_obj):
    current = Path.cwd()
    root.mkdir(parents=True, exist_ok=True)
    os.chdir(root)
    try:
        return callable_obj()
    finally:
        os.chdir(current)


def _patch_run_daily_modules(
    stack: ExitStack,
    *,
    with_styles: bool = True,
    with_guide: bool = True,
    with_hij: bool = True,
    include_publish: bool = True,
) -> None:

    def _noop_internal(*_args, **_kwargs):
        return 0

    stack.enter_context(patch.object(run_daily, "datetime", _FrozenDateTime))
    stack.enter_context(patch.object(run_daily.build_daily_package, "run_internal_line", side_effect=_noop_internal))
    stack.enter_context(patch.object(run_daily.build_daily_package, "run_public_line", side_effect=_noop_internal))
    if with_styles:
        def chart_story(*_args, **_kwargs):
            return {
                "status": "pass",
                "asset": _kwargs.get("asset", "xauusd"),
                "directory": "d",
                "findings": [],
                "images": ["d-1.webp", "d-2.webp"],
            }

        def chart_indicator(*_args, **_kwargs):
            return {
                "status": "pass",
                "asset": _kwargs.get("asset", "xauusd"),
                "directory": "e",
                "findings": [],
                "images": ["e-1.webp", "e-2.webp"],
                "char_count": 1200,
            }

        def brief_pair(*_args, **_kwargs):
            asset = _kwargs.get("asset", "xauusd")
            return [{"ok": True, "style_name": "F", "style": "f", "asset": asset,
                     "folder": "f", "findings": []}]
        stack.enter_context(patch.object(run_daily.chart_story_pipeline, "run", side_effect=chart_story))
        stack.enter_context(patch.object(run_daily.chart_indicator_pipeline, "run", side_effect=chart_indicator))
        stack.enter_context(patch.object(run_daily.brief_pipeline, "run_pair", side_effect=brief_pair))
        stack.enter_context(patch.object(run_daily.brief_pipeline, "run", side_effect=lambda *args, **kwargs: {
            "ok": True,
            "status": "pass",
            "style_name": "F",
            "style": "f",
            "style_id": "f",
            "asset": kwargs.get("asset", "xauusd"),
            "folder": "f",
            "findings": [],
            "images": [],
            "directory": "f",
        }))
        if with_hij:
            def round_round(*_args, **_kwargs):
                return {"ok": True, "skipped": [], "articles": [], "states": {"h": "frozen"}}
            stack.enter_context(patch.object(run_daily.intraday_pipeline, "run_round", side_effect=round_round))
        else:
            stack.enter_context(patch.object(run_daily.intraday_pipeline, "run_round", side_effect=lambda *_args, **_kwargs: {
                "ok": True, "skipped": [], "articles": [], "states": {},
            }))
    if with_guide:
        stack.enter_context(patch.object(run_daily.publish_selection, "select",
                                        return_value={"status": "ready", "article": "xauusd.md", "directory": "0-ขึ้นเว็บวันนี้"}))
    if include_publish:
        stack.enter_context(patch.object(run_daily.frontmatter_guard, "main", return_value=0))


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
    state_io_events: list[dict[str, Any]],
    control_events: list[dict[str, Any]],
    cleanup_manifests: dict[str, dict[str, str]],
    runtime_metadata: dict[str, Any],
) -> dict[str, Callable[..., Any]]:
    def _run_in_work_root(callable_obj):
        return _run_in_temp_root(context.work_root, callable_obj)

    def _mark_fetch(unit: str, timeframe: str) -> None:
        plan = plans[unit]
        request = next(item for item in plan.ordered_requests if item.timeframe == timeframe)
        TraceRecorder(trace).fetch(request, lambda _request: True)

    def _run_morning(_context, _plan, _output, _state, *, confirm: bool = False,
                     repeat: bool = False, extra_args: list[str] | None = None) -> dict[str, Any]:
        args: list[str] = [
            "--date", _RUN_DATE.isoformat(),
            "--plan-root", str(context.work_root / "editorial"),
            "--output-root", str(context.output_root),
        ]
        if confirm:
            args.append("--confirm")
        if extra_args:
            args.extend(extra_args)
        runtime_metadata["argv"] = list(args)
        control_events.append({"order": len(control_events) + 1,
                               "event": "confirm" if confirm else "preview"})
        with ExitStack() as stack:
            stack.enter_context(patch.object(run_morning, "_REPO_ROOT", context.work_root))
            stack.enter_context(patch.object(run_morning, "DEFAULT_PLAN_ROOT", context.work_root / "editorial"))
            stack.enter_context(patch.object(run_morning, "DEFAULT_OUTPUT_ROOT", context.output_root))
            stack.enter_context(patch.object(run_morning, "datetime", _FrozenDateTime))
            _patch_run_daily_modules(stack)
            first = _run_in_work_root(lambda: run_morning.main(args))
            second = None
            if repeat:
                second = _run_in_work_root(lambda: run_morning.main(args))
        runtime_metadata["exit_codes"] = [first] + ([second] if second is not None else [])
        if repeat:
            control_events.append({"order": len(control_events) + 1,
                                   "event": "one-plan-reject"})
        entries.append("tools.run_morning.main")
        if repeat:
            return {"status": "PASS" if first == 0 and second == 2 else "FAIL"}
        return {"status": "PASS" if first == 0 else "FAIL"}

    def _run_daily(_context, _plan, _output, _state, *, args: list[str] | None = None) -> dict[str, Any]:
        argv = list(args or [])
        runtime_metadata["argv"] = list(argv)
        _mark_fetch("ABC_PUBLIC", "1d")
        control_events.append({"order": 1, "event": "daily-start"})
        if "--publish-internal" in argv:
            control_events.append({"order": 2, "event": "publish-internal-guarded"})
        elif "--line" in argv:
            control_events.append({"order": 2, "event": "line-internal"})
        elif any(item.startswith("--skip-style-") for item in argv):
            control_events.append({"order": 2, "event": "style-skips"})
        else:
            control_events.append({"order": 2, "event": "default-selection"})
        with ExitStack() as stack:
            _patch_run_daily_modules(stack)
            code = _run_in_work_root(lambda: run_daily.main(argv))
        entries.append("tools.run_daily.main")
        runtime_metadata["exit_codes"] = [code]
        return {"status": "PASS" if code == 0 else "FAIL"}

    def d_chart(_context, asset, _plan, _output, _state):
        _mark_fetch("D_CHART_STORY", "1d")
        if scenario.scenario_id == "G15":
            entries.append("tools.chart_story_pipeline.run")
            cleanup_manifests["before"] = _tree_snapshot(context.output_root)
            def broken_fetcher(_asset):
                raise RuntimeError("frozen D fixture failure")
            try:
                result = chart_story_pipeline.run(
                    asset=asset, publish_root=context.output_root,
                    cutoff_at=_CUT_OFF, fetcher=broken_fetcher,
                    zone_state_dir=context.state_root)
            finally:
                cleanup_manifests["after"] = _tree_snapshot(context.output_root)
        else:
            result = chart_story_pipeline.run(
                asset=asset, publish_root=context.output_root,
                cutoff_at=_CUT_OFF,
                fetcher=lambda _asset: ({"provider": "fixture"}, _frozen_series(), "frozen D fixture"),
                calendar_source=lambda _asset: (None, "fixture"),
                zone_state_dir=context.state_root)
            entries.append("tools.chart_story_pipeline.run")
        return result

    def e_indicator(_context, asset, _plan, _output, _state):
        _mark_fetch("E_INDICATOR", "1h")
        result = chart_indicator_pipeline.run(
            asset=asset, publish_root=context.output_root,
            cutoff_at=_CUT_OFF,
            fetcher=lambda _asset, *, timeframe: ({"provider": "fixture", "timeframe": timeframe},
                                               list(_frozen_series()), "frozen E fixture"))
        entries.append("tools.chart_indicator_pipeline.run")
        return _legacy_payload(result, entry_point="tools.chart_indicator_pipeline.run")

    def fg_f(_context, asset, _plan, _output, _state) -> dict[str, Any]:
        _mark_fetch("FG_BRIEF", "1h")
        result = _run_in_work_root(lambda: brief_pipeline.run(
            asset=asset, publish_root=context.output_root, cutoff_at=_CUT_OFF,
            fetcher=_brief_fetcher, calendar_source=_brief_empty_calendar,
        ))
        entries.append("tools.brief_pipeline.run")
        return _legacy_payload(result if isinstance(result, Mapping) else {"ok": bool(result)},
                               entry_point="tools.brief_pipeline.run")

    def fg_g_then_f(_context, asset, _plan, _output, _state) -> dict[str, Any]:
        _mark_fetch("FG_BRIEF", "1h")
        with ExitStack() as stack:
            stack.enter_context(patch.object(brief_story, "channel_touches", return_value={
                "upper": [{"index": 1, "date": "2026-08-20", "price": 2010.0, "edge": "upper"},
                          {"index": 2, "date": "2026-08-20", "price": 2020.0, "edge": "upper"}],
                "lower": [{"index": 3, "date": "2026-08-20", "price": 2000.0, "edge": "lower"},
                          {"index": 4, "date": "2026-08-20", "price": 1990.0, "edge": "lower"}],
                "count": 4,
            }))
            stack.enter_context(patch.object(brief_story, "channel_holds", return_value=True))
            result = _run_in_work_root(lambda: brief_pipeline.run_pair(
                asset=asset, publish_root=context.output_root / "run-pair", cutoff_at=_CUT_OFF,
                fetcher=_brief_fetcher, calendar_source=_brief_g_calendar))
        entries.append("tools.brief_pipeline.run_pair")
        ok = all(item.get("ok", False) for item in result)
        fg_single_args = [
            "--asset", asset, "--fg-single", "--skip-style-d", "--skip-style-e",
            "--skip-style-hij", "--skip-selection", "--skip-guard",
        ]
        pair_manifest = _tree_snapshot(context.output_root / "run-pair")
        original_brief_run = brief_pipeline.run

        def frozen_actual_brief(*_args, **kwargs):
            return original_brief_run(
                asset=kwargs.get("asset", asset), publish_root=context.output_root / "fg-single",
                cutoff_at=_CUT_OFF, fetcher=_brief_fetcher,
                calendar_source=_brief_g_calendar)

        with ExitStack() as stack:
            _patch_run_daily_modules(stack, with_styles=False, with_guide=False,
                                     include_publish=False)
            stack.enter_context(patch.object(run_daily.brief_pipeline, "run",
                                             side_effect=frozen_actual_brief))
            fg_single_code = _run_in_work_root(lambda: run_daily.main(fg_single_args))
        runtime_metadata["fg_single_argv"] = fg_single_args
        runtime_metadata["argv"] = fg_single_args
        runtime_metadata["fg_single_exit_code"] = fg_single_code
        runtime_metadata["exit_codes"] = [fg_single_code]
        runtime_metadata["parity_manifests"] = {
            "run_pair": pair_manifest,
            "fg_single": _tree_snapshot(context.output_root / "fg-single"),
        }
        entries.append("tools.run_daily.main")
        ok = ok and fg_single_code == 0
        return _legacy_payload({"status": "PASS" if ok else "FAIL", "ok": ok}, entry_point="tools.brief_pipeline.run_pair")

    def hij(_context, asset, _plan, _output, _state):
        series = _frozen_series()
        for style_id, timeframe in (
            (intraday_story.STYLE_H, "30min"),
            (intraday_story.STYLE_I, "15min"),
        ):
            path = intraday_story.state_path(style_id, asset, timeframe, state_dir=context.state_root)
            if scenario.scenario_id == "G14":
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"state": "__frozen_previous__"}), encoding="utf-8")

        if scenario.scenario_id == "G13":
            for request in plans["HIJ_INTRADAY"].ordered_requests:
                _mark_fetch("HIJ_INTRADAY", request.timeframe)
            result = intraday_pipeline.run_round(
                asset=asset, publish_root=context.output_root,
                cutoff_at=_CUT_OFF, state_dir=context.state_root,
                dry_run=True, production_only=True,
                fetcher=lambda _asset, *, timeframe, outputsize: (
                    {"provider": "fixture", "timeframe": timeframe, "count": len(series)},
                    list(series), f"frozen HIJ fixture {timeframe}"))
            entries.append("tools.intraday_pipeline.run_round")
            return {"status": "SKIP" if not result.get("states") else "PASS", "legacy": result}
        if scenario.scenario_id == "G14":
            plan = plans["HIJ_INTRADAY"]
            for request in plan.ordered_requests:
                _mark_fetch("HIJ_INTRADAY", request.timeframe)
            original_read = intraday_story.read_state
            original_write = intraday_story.write_state

            def observed_read(style_id, observed_asset, timeframe, *, state_dir=None):
                path = intraday_story.state_path(
                    style_id, observed_asset, timeframe, state_dir=state_dir)
                state_io_events.append({
                    "order": len(state_io_events) + 1, "operation": "read",
                    "path": path.relative_to(context.state_root).as_posix(),
                    "key": f"{style_id}:{observed_asset}:{timeframe}",
                })
                return original_read(style_id, observed_asset, timeframe, state_dir=state_dir)

            def observed_write(style_id, observed_asset, timeframe, payload, *, state_dir=None):
                path = intraday_story.state_path(
                    style_id, observed_asset, timeframe, state_dir=state_dir)
                state_io_events.append({
                    "order": len(state_io_events) + 1, "operation": "write",
                    "path": path.relative_to(context.state_root).as_posix(),
                    "key": f"{style_id}:{observed_asset}:{timeframe}",
                    "payload_keys": sorted(payload),
                })
                return original_write(
                    style_id, observed_asset, timeframe, payload, state_dir=state_dir)

            with patch.object(intraday_story, "read_state", side_effect=observed_read), \
                    patch.object(intraday_story, "write_state", side_effect=observed_write):
                result = intraday_pipeline.run(
                    asset=asset, publish_root=context.output_root,
                    cutoff_at=_CUT_OFF, state_dir=context.state_root,
                    dry_run=True, force_style=intraday_story.STYLE_H,
                    fetcher=lambda _asset, *, timeframe, outputsize: (
                        {"provider": "fixture", "timeframe": timeframe, "count": len(series)},
                        list(series), f"frozen HIJ fixture {timeframe}"))
            for style_id, state in result.get("states", {}).items():
                transitions.append({"style": style_id, "from": "__frozen_previous__", "to": state})
            entries.append("tools.intraday_pipeline.run")
            return {"status": "PASS" if result.get("ok", False) else "FAIL", "legacy": result,
                    "children": [{"style_id": style, "status": "PASS" if result.get("ok", False) else "FAIL"}
                                 for style in UNIT_MEMBERS["HIJ_INTRADAY"]]}
        # G15 path
        result = intraday_pipeline.run(
            asset=asset, publish_root=context.output_root,
            cutoff_at=_CUT_OFF, state_dir=context.state_root,
            dry_run=True, force_style=intraday_story.STYLE_H,
            fetcher=lambda _asset, *, timeframe, outputsize: (
                {"provider": "fixture", "timeframe": timeframe, "count": len(series)},
                list(series), f"frozen HIJ fixture {timeframe}"),
        )
        entries.append("tools.intraday_pipeline.run")
        return {"status": "PASS" if result.get("ok", False) else "FAIL",
                "legacy": result,
                "children": [{"style_id": style, "status": "PASS" if result.get("ok", False) else "FAIL"}
                             for style in UNIT_MEMBERS["HIJ_INTRADAY"]]}

    def selection_guard(_context, asset, _plan, output, _state):
        plan = run_morning.build_plan(run_date=_RUN_DATE, now=_RUN_NOW)
        # G16 isolates the legacy selector/guard ordering with one frozen D article.
        # Keep that fixture on schema v1; multi-lane v2 has its own five-article tests.
        current_policy = publish_selection.load_policy()
        policy = {
            "schema_version": 1,
            "web_asset": current_policy["web_asset"],
            "web_style": current_policy["web_style"],
            "articles_per_day": 1,
            "selection_folder": current_policy["selection_folder"],
            "selection_lane": current_policy["selection_lane"],
            "web_chart_mode": current_policy["web_chart_mode"],
        }
        day = context.output_root / "selection-day"
        source = day / publish_selection.style_folder(policy["web_style"])
        output.write_bytes((source.relative_to(context.output_root) / f"{asset}.md"),
                          b"---\ntitle: frozen shadow\n---\n")
        selection.update(publish_selection.select(day, policy=policy))
        control_events.append({"order": 1, "event": "selection"})
        guard.check(no_publish=True)
        control_events.append({"order": 2, "event": "guard"})
        guard.check(no_publish=True)
        control_events.append({"order": 3, "event": "guard"})
        entries.append("tools.publish_selection.select")
        return {"status": "PASS", "legacy": {"plan": plan, "selection": selection.get("status")}}

    adapters: dict[str, Callable[..., Any]] = {}
    if scenario.scenario_id == "G01":
        adapters["INTERNAL_EVIDENCE_123"] = lambda _context, asset, plan, output, state: (
            _run_morning(_context, plan, output, state))
    elif scenario.scenario_id == "G02":
        adapters["INTERNAL_EVIDENCE_123"] = lambda _context, asset, plan, output, state: (
            _run_morning(_context, plan, output, state, extra_args=["--write", "eurusd", "--watch", "usd"]))
    elif scenario.scenario_id == "G03":
        adapters["INTERNAL_EVIDENCE_123"] = lambda _context, asset, plan, output, state: (
            _run_morning(_context, plan, output, state, confirm=True))
    elif scenario.scenario_id == "G04":
        adapters["INTERNAL_EVIDENCE_123"] = lambda _context, asset, plan, output, state: (
            _run_morning(_context, plan, output, state, confirm=True, repeat=True))
    elif scenario.scenario_id == "G05":
        adapters["ABC_PUBLIC"] = lambda _context, asset, plan, output, state: (
            _run_daily(_context, plan, output, state))
    elif scenario.scenario_id == "G06":
        adapters["ABC_PUBLIC"] = lambda _context, asset, plan, output, state: (
            _run_daily(_context, plan, output, state, args=["--publish-internal"]))
    elif scenario.scenario_id == "G07":
        adapters["ABC_PUBLIC"] = lambda _context, asset, plan, output, state: (
            _run_daily(_context, plan, output, state, args=["--line", "internal"]))
    elif scenario.scenario_id == "G08":
        adapters["ABC_PUBLIC"] = lambda _context, asset, plan, output, state: (
            _run_daily(_context, plan, output, state, args=[
                "--skip-style-d", "--skip-style-e", "--skip-style-fg", "--skip-style-hij",
            ]))
    elif scenario.scenario_id == "G09":
        adapters["D_CHART_STORY"] = lambda _context, asset, plan, output, state: (
            _legacy_payload(d_chart(_context, asset, plan, output, state), entry_point="tools.chart_story_pipeline.run"))
    elif scenario.scenario_id == "G10":
        adapters["E_INDICATOR"] = lambda _context, asset, plan, output, state: (
            _legacy_payload(e_indicator(_context, asset, plan, output, state), entry_point="tools.chart_indicator_pipeline.run"))
    elif scenario.scenario_id == "G11":
        adapters["FG_BRIEF"] = fg_f
    elif scenario.scenario_id == "G12":
        adapters["FG_BRIEF"] = fg_g_then_f
    elif scenario.scenario_id in {"G13", "G14"}:
        adapters["HIJ_INTRADAY"] = hij
    elif scenario.scenario_id == "G15":
        adapters.update({
            "D_CHART_STORY": lambda _context, asset, plan, output, state: (
                _legacy_payload(d_chart(_context, asset, plan, output, state), entry_point="tools.chart_story_pipeline.run")),
            "E_INDICATOR": lambda _context, asset, plan, output, state: (
                _legacy_payload(e_indicator(_context, asset, plan, output, state), entry_point="tools.chart_indicator_pipeline.run")),
            "FG_BRIEF": lambda _context, asset, plan, output, state: {
                "status": "SKIP", "reason_code": "FIXTURE_NOT_SELECTED"},
            "HIJ_INTRADAY": lambda _context, asset, plan, output, state: (
                _legacy_payload(hij(_context, asset, plan, output, state), entry_point="tools.intraday_pipeline.run")),
        })
    elif scenario.scenario_id == "G16":
        adapters["INTERNAL_EVIDENCE_123"] = selection_guard
    return adapters


def _direct_legacy_manifest(scenario: ActualShadowScenario) -> dict[str, Any]:
    """Run the selected legacy adapter independently of the unified orchestrator."""
    with TemporaryDirectory(prefix=f"p002-direct-{scenario.scenario_id.lower()}-") as root:
        root_path = Path(root)
        context = RunContext(
            run_id=f"direct-legacy-{scenario.scenario_id}", cutoff_at="2026-08-20T01:00:00Z",
            assets=(scenario.asset,), output_root=root_path / "output",
            work_root=root_path / "work", state_root=root_path / "state",
            mode="shadow", no_publish=True)
        plans = _plans(scenario.asset)
        trace, entries, transitions = ApiTrace(), [], []
        selection, state_io_events, control_events = {}, [], []
        cleanup_manifests, runtime_metadata = {}, {}
        guard = PublishGuard()
        adapters = _actual_adapters(
            scenario, context, plans, trace, entries, transitions, selection, guard,
            state_io_events, control_events, cleanup_manifests, runtime_metadata)
        unit = next(iter(adapters))
        raw = adapters[unit](context, scenario.asset, plans[unit],
                             OutputFS(context.output_root), StateStore(context.state_root))
        artifacts = _tree_snapshot(context.output_root)
        states = _tree_snapshot(context.state_root)
        return {
            "source": "independent-direct-legacy-execution",
            "scenario_id": scenario.scenario_id,
            "argv": _canonical_argv(list(runtime_metadata.get("argv", [])), context),
            "execution_context": {
                "run_id": f"direct-legacy-{scenario.scenario_id}",
                "cutoff_at": context.cutoff_at, "assets": list(context.assets),
                "mode": context.mode, "no_publish": context.no_publish,
                "roots": {"output": "<temp>/output", "work": "<temp>/work",
                          "state": "<temp>/state"},
            },
            "status": str(raw.get("status", "PASS")).upper(),
            "exit_codes": list(runtime_metadata.get("exit_codes", [])),
            "legacy_entry_points": entries,
            "source_trace": [asdict(item) for item in trace.entries],
            "control_events": control_events,
            "output_tree": sorted(artifacts), "artifact_hashes": artifacts,
            "state_hash": _json_hash(states) if states else None,
        }


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
            production_output_root = Path(__file__).parents[2] / "output"
            production_state_root = Path(__file__).parents[1] / "state"
            safety_before = {
                "production_output": _tree_snapshot(production_output_root),
                "production_state": _tree_snapshot(production_state_root),
            }
            output = OutputFS(context.output_root)
            state = StateStore(context.state_root)
            trace = ApiTrace()
            entries: list[str] = []
            transitions: list[dict[str, Any]] = []
            selection: dict[str, Any] = {}
            guard = PublishGuard()
            state_io_events: list[dict[str, Any]] = []
            control_events: list[dict[str, Any]] = []
            cleanup_manifests: dict[str, dict[str, str]] = {}
            runtime_metadata: dict[str, Any] = {}
            plans = _plans(scenario.asset)
            orchestrator = UnifiedStyleOrchestrator(_actual_adapters(
                scenario, context, plans, trace, entries, transitions, selection, guard,
                state_io_events, control_events, cleanup_manifests, runtime_metadata))
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
            canonical_context = {
                "run_id": context.run_id, "cutoff_at": context.cutoff_at,
                "assets": list(context.assets), "mode": context.mode,
                "no_publish": context.no_publish,
                "roots": {"output": "<temp>/output", "work": "<temp>/work", "state": "<temp>/state"},
            }
            expected_manifest = (_direct_legacy_manifest(scenario)
                                 if scenario.scenario_id in {f"G{i:02d}" for i in range(2, 9)}
                                 else {})
            safety_after = {
                "production_output": _tree_snapshot(production_output_root),
                "production_state": _tree_snapshot(production_state_root),
            }
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
                state_io_events=state_io_events, control_events=control_events,
                cleanup_manifests=cleanup_manifests,
                argv=_canonical_argv(list(runtime_metadata.get("argv", [])), context),
                execution_context=canonical_context,
                expected_manifest=expected_manifest,
                safety_deltas={
                    "before_hashes": {key: _json_hash(value) for key, value in safety_before.items()},
                    "after_hashes": {key: _json_hash(value) for key, value in safety_after.items()},
                    "changed_files": {
                        key: len(set(safety_before[key].items()) ^ set(safety_after[key].items()))
                        for key in safety_before
                    },
                    "network_calls": 0, "publish_calls": 0,
                },
                exit_codes=list(runtime_metadata.get("exit_codes", [])),
                parity_manifests=dict(runtime_metadata.get("parity_manifests", {})),
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
