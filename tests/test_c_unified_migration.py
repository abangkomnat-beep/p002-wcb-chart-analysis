"""CP5-C reversible migration gate: unified selection preserves legacy C."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from tools import build_daily_package
from tools.c_unified_adapter import CEventAdapter, CProductionRoute, STYLE_ID, UNIT_ID
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


def _route(mode: str = "unified") -> CProductionRoute:
    return CProductionRoute(RegistryLoader().load(_registry(mode)))


def _result(status: str = "built") -> dict:
    return {"asset": "xauusd", "line": "public", "status": status,
            "content_ok": status == "built", "clearance": "approved-internal-only"}


def test_registry_selects_c_unit_with_rollback_legacy():
    route = CProductionRoute.load()
    assert route.migration_mode == "unified"
    assert route.registry.execution_units[UNIT_ID].members == (STYLE_ID,)
    assert route.registry.execution_units[UNIT_ID].rollback_mode == "legacy"
    assert route.registry.styles[STYLE_ID].letter == "C"
    assert route.registry.styles[STYLE_ID].adapter == "abc_public"


def test_unified_route_calls_legacy_public_builder_once_with_exact_arguments(tmp_path):
    raw = _result()
    with mock.patch.object(build_daily_package, "build_public", return_value=raw) as builder:
        result = _route().run_round(
            asset="xauusd", batch_id="batch-c", output_root=tmp_path / "work",
            publish_root=tmp_path / "output", cutoff_at=CUTOFF,
            calendar_feed_enabled=False,
        )
    assert result is raw
    builder.assert_called_once_with(
        "xauusd", batch_id="batch-c", output_root=tmp_path / "work",
        publish_root=tmp_path / "output", snapshot_path=None, cutoff_at=CUTOFF,
    )


def test_rollback_toggle_bypasses_orchestrator(tmp_path):
    raw = _result()
    with mock.patch.object(build_daily_package, "build_public", return_value=raw) as builder, \
            mock.patch("tools.c_unified_adapter.UnifiedStyleOrchestrator.execute") as execute:
        result = _route("legacy").run_round(
            asset="xauusd", batch_id="batch-c", output_root=tmp_path / "work",
            publish_root=tmp_path / "output", cutoff_at=CUTOFF,
            calendar_feed_enabled=False,
        )
    assert result is raw
    execute.assert_not_called()
    builder.assert_called_once()


def test_invalid_or_shadow_mode_fails_closed_before_legacy_side_effect(tmp_path):
    with mock.patch.object(build_daily_package, "build_public") as builder:
        with pytest.raises(RegistryError, match="refuses"):
            _route("shadow").run_round(
                asset="xauusd", batch_id="batch-c", output_root=tmp_path / "work",
                publish_root=tmp_path / "output", cutoff_at=CUTOFF,
            )
    builder.assert_not_called()
    invalid = _registry()
    invalid["execution_units"][UNIT_ID]["members"] = ["a_standard"]
    with pytest.raises(RegistryError, match="members"):
        CProductionRoute(RegistryLoader().load(invalid))


def test_adapter_failure_isolated_and_legacy_result_is_observable(tmp_path):
    context = RunContext("r", CUTOFF, line="public", assets=("xauusd",), mode="unified",
                         no_publish=True, output_root=tmp_path / "output", state_root=tmp_path / "state")
    plan = SourcePlanner().plan(execution_unit=UNIT_ID, asset="xauusd", requests=())
    adapter = CEventAdapter(batch_id="batch-c", output_root=tmp_path / "work",
                            publish_root=None, cutoff_at=CUTOFF,
                            calendar_feed_enabled=False)
    with mock.patch.object(build_daily_package, "build_public", side_effect=RuntimeError("fixture down")):
        envelope = adapter(context, "xauusd", plan, OutputFS(tmp_path / "audit"),
                           StateStore(tmp_path / "state"))
    assert envelope.status == "FAIL"
    assert envelope.findings[0].message == "fixture down"

    raw = _result("rejected")
    with mock.patch.object(build_daily_package, "build_public", return_value=raw):
        envelope = adapter(context, "xauusd", plan, OutputFS(tmp_path / "audit2"),
                           StateStore(tmp_path / "state2"))
    assert envelope.status == "FAIL"
    assert envelope.style_ids == ["C"]
