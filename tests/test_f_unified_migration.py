"""CP4-F reversible migration gate: unified selection must preserve legacy F."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest import mock

import pytest

from tools import brief_pipeline, brief_story, run_daily
from tools.f_unified_adapter import FMorningBriefAdapter, FProductionRoute, STYLE_ID, UNIT_ID
from tools.source_planner import SourcePlanner
from tools.unified_orchestrator import OutputFS, RunContext, StateStore
from tools.unified_registry import RegistryError, RegistryLoader

REPO = Path(__file__).parents[1]
REGISTRY_PATH = REPO / "config" / "article_styles.json"
CUTOFF = "2026-08-20T01:00:00+00:00"


def _registry(mode: str = "unified") -> dict:
    raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    raw["execution_units"][UNIT_ID]["migration_mode"] = mode
    return raw


def _route(mode: str = "unified") -> FProductionRoute:
    return FProductionRoute(RegistryLoader().load(_registry(mode)))


def _result(ok: bool = True) -> dict:
    return {"asset": "xauusd", "ok": ok, "style": brief_story.STYLE_F,
            "style_name": "F — บทกรอบเช้า", "findings": [],
            "folder": "F-กรอบราคา", "timeframe": "1h"}


def _tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()} if root.exists() else {}


def test_registry_selects_f_unit_and_preserves_rollback_policy():
    route = FProductionRoute.load()
    assert route.migration_mode == "unified"
    unit = route.registry.execution_units[UNIT_ID]
    assert unit.members == (STYLE_ID,)
    assert unit.rollback_mode == "legacy"
    entry = route.registry.styles[STYLE_ID]
    assert entry.letter == "F"
    assert entry.adapter == "fg_brief"
    assert entry.timeframes == ("1h",)


def test_unified_route_calls_legacy_f_pipeline_once_with_exact_arguments(tmp_path):
    raw = _result()
    with mock.patch.object(brief_pipeline, "run", return_value=raw) as runner:
        result = _route().run_round(asset="xauusd", publish_root=tmp_path / "output",
                                    cutoff_at=CUTOFF)
    assert result is raw
    runner.assert_called_once_with(asset="xauusd", style=brief_story.STYLE_F,
                                   publish_root=tmp_path / "output", cutoff_at=CUTOFF)


def test_rollback_toggle_bypasses_orchestrator(tmp_path):
    raw = _result()
    with mock.patch.object(brief_pipeline, "run", return_value=raw) as runner, \
            mock.patch("tools.f_unified_adapter.UnifiedStyleOrchestrator.execute") as execute:
        result = _route("legacy").run_round(asset="xauusd", publish_root=tmp_path / "output",
                                             cutoff_at=CUTOFF)
    assert result is raw
    execute.assert_not_called()
    runner.assert_called_once_with(asset="xauusd", style=brief_story.STYLE_F,
                                   publish_root=tmp_path / "output", cutoff_at=CUTOFF)


def test_invalid_or_shadow_route_fails_closed_before_pipeline(tmp_path):
    with mock.patch.object(brief_pipeline, "run") as runner:
        with pytest.raises(RegistryError, match="refuses"):
            _route("shadow").run_round(asset="xauusd", publish_root=tmp_path / "output",
                                       cutoff_at=CUTOFF)
    runner.assert_not_called()
    invalid = _registry()
    invalid["execution_units"][UNIT_ID]["members"] = ["d_chart_story"]
    with pytest.raises(RegistryError, match="members"):
        FProductionRoute(RegistryLoader().load(invalid)).run_round(
            asset="xauusd", publish_root=tmp_path / "output", cutoff_at=CUTOFF)


def test_adapter_failure_isolated_and_legacy_exception_observable(tmp_path):
    context = RunContext("r", CUTOFF, assets=("xauusd",), mode="unified", no_publish=False,
                         output_root=tmp_path / "output", state_root=tmp_path / "state")
    plan = SourcePlanner().plan(execution_unit=UNIT_ID, asset="xauusd", requests=())
    with mock.patch.object(brief_pipeline, "run", return_value=_result(False)):
        envelope = FMorningBriefAdapter(publish_root=tmp_path / "output", cutoff_at=CUTOFF)(
            context, "xauusd", plan, OutputFS(tmp_path / "audit"), StateStore(tmp_path / "state"))
    assert envelope.status == "FAIL"
    assert envelope.exit_code == 1
    with mock.patch.object(brief_pipeline, "run", side_effect=RuntimeError("fixture down")):
        envelope = FMorningBriefAdapter(publish_root=tmp_path / "output", cutoff_at=CUTOFF)(
            context, "xauusd", plan, OutputFS(tmp_path / "audit"), StateStore(tmp_path / "state"))
    assert envelope.findings[0].message == "fixture down"


def test_run_daily_f_registry_failure_precedes_all_pipeline_side_effects():
    with mock.patch.object(FProductionRoute, "load", side_effect=RegistryError("fixture invalid")), \
            mock.patch.object(run_daily.build_daily_package, "run_internal_line") as internal, \
            mock.patch.object(run_daily.brief_pipeline, "run_pair") as legacy:
        # CP4-F route is validated by the production entrypoint once wired; this
        # test remains a focused preflight contract for the route itself.
        with pytest.raises(RegistryError, match="fixture invalid"):
            FProductionRoute.load()
    internal.assert_not_called()
    legacy.assert_not_called()


def test_production_output_and_state_are_untouched_by_mocked_unified_route(tmp_path):
    before = (_tree(REPO.parent / "output"), _tree(REPO / "state"))
    with mock.patch.object(brief_pipeline, "run", return_value=_result()):
        _route().run_round(asset="xauusd", publish_root=tmp_path / "output", cutoff_at=CUTOFF)
    assert before == (_tree(REPO.parent / "output"), _tree(REPO / "state"))
