"""Representative actual legacy-runtime shadow evidence for Unified A–J."""
from __future__ import annotations

from tools.unified_actual_shadow import ActualShadowHarness, actual_scenarios


EXPECTED_SCENARIOS = [f"G{i:02d}" for i in range(1, 17)]
EXPECTED_ENTRYPOINTS = {
    "G01": ["tools.run_morning.main"],
    "G02": ["tools.run_morning.main"],
    "G03": ["tools.run_morning.main"],
    "G04": ["tools.run_morning.main"],
    "G05": ["tools.run_daily.main"],
    "G06": ["tools.run_daily.main"],
    "G07": ["tools.run_daily.main"],
    "G08": ["tools.run_daily.main"],
    "G09": ["tools.chart_story_pipeline.run"],
    "G10": ["tools.chart_indicator_pipeline.run"],
    "G11": ["tools.brief_pipeline.run"],
    "G12": ["tools.brief_pipeline.run_pair"],
    "G14": ["tools.intraday_pipeline.run"],
    "G16": ["tools.publish_selection.select"],
}


def test_actual_shadow_reaches_real_legacy_entrypoints(tmp_path):
    evidence = ActualShadowHarness().run_all(evidence_root=tmp_path / "audit")
    assert [item.scenario_id for item in evidence] == EXPECTED_SCENARIOS
    by_id = {item.scenario_id: item for item in evidence}
    for scenario_id in EXPECTED_ENTRYPOINTS:
        assert by_id[scenario_id].legacy_entry_points == EXPECTED_ENTRYPOINTS[scenario_id]


def test_actual_shadow_hij_state_and_failure_isolation_are_observable():
    harness = ActualShadowHarness()
    by_id = {item.scenario_id: item for item in harness.run_all()}
    assert by_id["G13"].unit_statuses["HIJ_INTRADAY"] == "SKIP"
    assert by_id["G14"].unit_statuses["HIJ_INTRADAY"] == "PASS"
    assert len(by_id["G14"].state_transitions) == 3
    assert by_id["G15"].status == "FAIL"
    assert by_id["G15"].unit_statuses["D_CHART_STORY"] == "FAIL"
    assert by_id["G15"].unit_statuses["E_INDICATOR"] == "PASS"
    assert by_id["G15"].unit_statuses["HIJ_INTRADAY"] == "PASS"


def test_actual_shadow_selection_and_guard_order_is_recorded():
    evidence = ActualShadowHarness().run(actual_scenarios()[-1])
    assert evidence.selection_calls == 1
    assert evidence.guard_calls == 2
    assert evidence.selection_status == "ready"
