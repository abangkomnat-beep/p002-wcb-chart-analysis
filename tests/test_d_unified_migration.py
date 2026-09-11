"""CP3 isolated migration gate for Style D."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from tools import chart_story_pipeline, run_daily
from tools.d_unified_adapter import DChartStoryAdapter, DProductionRoute, STYLE_ID, UNIT_ID
from tools.source_planner import SourcePlanner
from tools.unified_registry import RegistryError, RegistryLoader
from tools.unified_orchestrator import OutputFS, RunContext, StateStore

REPO = Path(__file__).parents[1]
REGISTRY_PATH = REPO / "config" / "article_styles.json"
CUTOFF = "2026-08-20T01:00:00+00:00"


def _registry(mode: str = "unified") -> dict:
    raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    raw["execution_units"][UNIT_ID]["migration_mode"] = mode
    return raw


def _route(mode: str = "unified") -> DProductionRoute:
    return DProductionRoute(RegistryLoader().load(_registry(mode)))


def _result(status: str = "pass") -> dict:
    return {"asset": "xauusd", "status": status, "findings": [], "images": [], "directory": "fixture"}


def test_registry_selects_d_unit_and_preserves_legacy_rollback():
    route = DProductionRoute.load()
    assert route.migration_mode == "unified"
    unit = route.registry.execution_units[UNIT_ID]
    assert unit.members == (STYLE_ID,)
    assert unit.rollback_mode == "legacy"
    assert route.registry.styles[STYLE_ID].letter == "D"
    assert route.registry.styles[STYLE_ID].adapter == "d_chart_story"


def test_unified_route_calls_legacy_d_pipeline_once_with_exact_arguments(tmp_path):
    raw = _result()
    with mock.patch.object(chart_story_pipeline, "run", return_value=raw) as runner:
        result = _route().run_round(asset="xauusd", publish_root=tmp_path / "output", cutoff_at=CUTOFF)
    assert result is raw
    runner.assert_called_once_with(asset="xauusd", publish_root=tmp_path / "output", cutoff_at=CUTOFF)


def test_rollback_toggle_bypasses_orchestrator_and_is_reversible(tmp_path):
    raw = _result()
    with mock.patch.object(chart_story_pipeline, "run", return_value=raw) as runner, \
            mock.patch("tools.d_unified_adapter.UnifiedStyleOrchestrator.execute") as execute:
        result = _route("legacy").run_round(asset="xauusd", publish_root=tmp_path / "output", cutoff_at=CUTOFF)
    assert result is raw
    execute.assert_not_called()
    runner.assert_called_once()


def test_invalid_or_shadow_mode_fails_closed_before_legacy_side_effect(tmp_path):
    with mock.patch.object(chart_story_pipeline, "run") as runner:
        with pytest.raises(RegistryError, match="refuses"):
            _route("shadow").run_round(asset="xauusd", publish_root=tmp_path / "output", cutoff_at=CUTOFF)
    runner.assert_not_called()

    invalid = _registry()
    invalid["execution_units"][UNIT_ID]["members"] = ["h_trend_strength"]
    with pytest.raises(RegistryError, match="membership mismatch"):
        DProductionRoute(RegistryLoader().load(invalid))


def test_adapter_maps_legacy_status_and_exception_without_changing_result(tmp_path):
    context = RunContext("r", CUTOFF, assets=("xauusd",), mode="unified", no_publish=False,
                         output_root=tmp_path / "output", state_root=tmp_path / "state")
    plan = SourcePlanner().plan(execution_unit=UNIT_ID, asset="xauusd", requests=())
    with mock.patch.object(chart_story_pipeline, "run", return_value=_result("pass")):
        envelope = DChartStoryAdapter(publish_root=tmp_path / "output", cutoff_at=CUTOFF)(
            context, "xauusd", plan, OutputFS(tmp_path / "audit"), StateStore(tmp_path / "state"))
    assert envelope.status == "PASS"
    assert envelope.style_ids == ["D"]

    with mock.patch.object(chart_story_pipeline, "run", side_effect=RuntimeError("fixture down")):
        envelope = DChartStoryAdapter(publish_root=tmp_path / "output", cutoff_at=CUTOFF)(
            context, "xauusd", plan, OutputFS(tmp_path / "audit2"), StateStore(tmp_path / "state2"))
    assert envelope.status == "FAIL"
    assert envelope.findings[0].message == "fixture down"


def test_run_daily_registry_preflight_blocks_d_before_any_pipeline_side_effect():
    with mock.patch.object(run_daily, "scheduled_lane_plan", return_value={"D": ["xauusd"]}), \
            mock.patch.object(DProductionRoute, "load", side_effect=RegistryError("fixture invalid")), \
            mock.patch.object(run_daily.build_daily_package, "run_internal_line") as internal, \
            mock.patch.object(run_daily.chart_story_pipeline, "run") as legacy:
        assert run_daily.main(["--asset", "xauusd"]) == 1
    internal.assert_not_called()
    legacy.assert_not_called()
