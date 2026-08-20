"""Representative actual legacy-runtime shadow evidence for Unified A–J."""
from tools.unified_actual_shadow import ActualShadowHarness, actual_scenarios


def test_actual_shadow_reaches_real_legacy_entrypoints(tmp_path):
    evidence = ActualShadowHarness().run_all(evidence_root=tmp_path / "audit")
    assert [item.scenario_id for item in evidence] == ["G01", "G09", "G10", "G13", "G14", "G15", "G16"]
    assert all(item.legacy_entry_points for item in evidence)
    assert evidence[1].legacy_entry_points == ["tools.chart_story_pipeline.run"]
    assert evidence[2].legacy_entry_points == ["tools.chart_indicator_pipeline.run"]
    assert evidence[3].legacy_entry_points == ["tools.intraday_pipeline.run_round"]
    assert evidence[4].legacy_entry_points == ["tools.intraday_pipeline.run"]


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
