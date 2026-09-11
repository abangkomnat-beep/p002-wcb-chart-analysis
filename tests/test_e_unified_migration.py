"""CP3-E reversible migration gate: unified selection must preserve legacy E."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest import mock

import pytest

from tools import chart_indicator_pipeline, chart_indicator_writer, run_daily, style_e_plus_daily
from tools.e_unified_adapter import EIndicatorAdapter, EProductionRoute, STYLE_ID, UNIT_ID
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


def _route(mode: str = "unified") -> EProductionRoute:
    return EProductionRoute(RegistryLoader().load(_registry(mode)))


def _result(status: str = "pass") -> dict:
    return {"asset": "xauusd", "status": status, "char_count": 1800,
            "findings": [], "directory": "e", "images": ["e.webp"]}


def test_style_e_publicization_keeps_excerpt_price_and_body_consistent():
    article = "---\nexcerpt: ทองปิดที่ 4,402.20 ดอลลาร์ RSI(14) ที่ 51.8\n---\n\nราคาปิด 4,402.20 และ RSI 51.8\n"
    rendered = chart_indicator_pipeline._publicize_style_e(article)
    assert "excerpt: ทองปิดที่ 4,402 ดอลลาร์ RSI(14) ที่ 52" in rendered
    assert "ราคาปิด 4,402 และ RSI 52" in rendered


def _tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()} if root.exists() else {}


def test_registry_selects_e_unit_and_preserves_rollback_policy():
    route = EProductionRoute.load()
    assert route.migration_mode == "unified"
    unit = route.registry.execution_units[UNIT_ID]
    assert unit.members == (STYLE_ID,)
    assert unit.rollback_mode == "legacy"
    entry = route.registry.styles[STYLE_ID]
    assert entry.letter == "E"
    assert entry.adapter == "e_indicator"
    assert entry.assets == ("btcusd", "xauusd", "usdjpy")
    assert entry.timeframes == ("1h", "15min")
    assert entry.metadata["asset_variants"]["btcusd"]["folder"] == \
        style_e_plus_daily.FOLDER


def test_unified_route_calls_legacy_e_pipeline_once_with_exact_arguments(tmp_path):
    raw = _result()
    with mock.patch.object(chart_indicator_pipeline, "run", return_value=raw) as runner:
        result = _route().run_round(asset="xauusd", publish_root=tmp_path / "output",
                                    cutoff_at=CUTOFF)
    assert result is raw
    runner.assert_called_once_with(asset="xauusd", publish_root=tmp_path / "output",
                                   cutoff_at=CUTOFF)


def test_unified_route_dispatches_btcusd_to_daily_eplus(tmp_path):
    raw = {**_result(), "asset": "btcusd", "variant": "e_plus_h1_m15",
           "images": ["h1.webp", "m15.webp"]}
    with mock.patch.object(style_e_plus_daily, "run", return_value=raw) as eplus, \
            mock.patch.object(chart_indicator_pipeline, "run") as legacy:
        result = _route().run_round(asset="btcusd", publish_root=tmp_path / "output",
                                    cutoff_at=CUTOFF)
    assert result is raw
    eplus.assert_called_once_with(asset="btcusd", publish_root=tmp_path / "output",
                                  cutoff_at=CUTOFF)
    legacy.assert_not_called()


def test_rollback_toggle_bypasses_orchestrator(tmp_path):
    raw = _result()
    with mock.patch.object(chart_indicator_pipeline, "run", return_value=raw) as runner, \
            mock.patch("tools.e_unified_adapter.UnifiedStyleOrchestrator.execute") as execute:
        result = _route("legacy").run_round(asset="xauusd", publish_root=tmp_path / "output",
                                             cutoff_at=CUTOFF)
    assert result is raw
    execute.assert_not_called()
    runner.assert_called_once()


def test_invalid_or_shadow_route_fails_closed_before_pipeline(tmp_path):
    with mock.patch.object(chart_indicator_pipeline, "run") as runner:
        with pytest.raises(RegistryError, match="refuses"):
            _route("shadow").run_round(asset="xauusd", publish_root=tmp_path / "output",
                                       cutoff_at=CUTOFF)
    runner.assert_not_called()
    invalid = _registry()
    invalid["execution_units"][UNIT_ID]["members"] = ["d_chart_story"]
    with pytest.raises(RegistryError, match="membership mismatch"):
        EProductionRoute(RegistryLoader().load(invalid))


def test_adapter_failure_isolated_and_legacy_exception_observable(tmp_path):
    context = RunContext("r", CUTOFF, assets=("xauusd",), mode="unified", no_publish=False,
                         output_root=tmp_path / "output", state_root=tmp_path / "state")
    plan = SourcePlanner().plan(execution_unit=UNIT_ID, asset="xauusd", requests=())
    with mock.patch.object(chart_indicator_pipeline, "run", return_value=_result("fail")):
        envelope = EIndicatorAdapter(publish_root=tmp_path / "output", cutoff_at=CUTOFF)(
            context, "xauusd", plan, OutputFS(tmp_path / "audit"), StateStore(tmp_path / "state"))
    assert envelope.status == "FAIL"
    assert envelope.exit_code == 1
    with mock.patch.object(chart_indicator_pipeline, "run", side_effect=RuntimeError("fixture down")):
        envelope = EIndicatorAdapter(publish_root=tmp_path / "output", cutoff_at=CUTOFF)(
            context, "xauusd", plan, OutputFS(tmp_path / "audit"), StateStore(tmp_path / "state"))
    assert envelope.findings[0].message == "fixture down"


def test_run_daily_e_registry_failure_precedes_all_pipeline_side_effects():
    with mock.patch.object(EProductionRoute, "load", side_effect=RegistryError("fixture invalid")), \
            mock.patch.object(run_daily.build_daily_package, "run_internal_line") as internal, \
            mock.patch.object(run_daily.build_daily_package, "run_public_line") as public, \
            mock.patch.object(run_daily.chart_indicator_pipeline, "run") as legacy:
        assert run_daily.main(["--asset", "xauusd"]) == 1
    internal.assert_not_called()
    public.assert_not_called()
    legacy.assert_not_called()


def test_production_output_and_state_are_untouched_by_mocked_unified_route(tmp_path):
    before = (_tree(REPO.parent / "output"), _tree(REPO / "state"))
    raw = _result()
    with mock.patch.object(chart_indicator_pipeline, "run", return_value=raw):
        _route().run_round(asset="xauusd", publish_root=tmp_path / "output", cutoff_at=CUTOFF)
    assert before == (_tree(REPO.parent / "output"), _tree(REPO / "state"))
