"""Runtime shadow parity evidence tests for G01–G16."""
from __future__ import annotations

from tools.unified_parity import ShadowParityHarness, default_scenarios, load_expected


def test_frozen_runtime_parity_has_no_findings_for_all_scenarios(tmp_path):
    harness = ShadowParityHarness()
    evidence_root = tmp_path / "audit"
    evidence = harness.run_all(evidence_root=evidence_root)
    expected = load_expected()
    assert [item.scenario_id for item in evidence] == [f"G{i:02d}" for i in range(1, 17)]
    assert sorted(path.name for path in evidence_root.glob("G*.json")) == [f"G{i:02d}.json" for i in range(1, 17)]
    assert harness.verify(evidence, expected["scenarios"]) == []


def test_hij_allowlist_and_state_transition_evidence_are_explicit():
    harness = ShadowParityHarness()
    allowlist = harness.run(default_scenarios()[12])
    transition = harness.run(default_scenarios()[13])
    assert allowlist.unit_statuses["HIJ_INTRADAY"] == "SKIP"
    assert allowlist.state_reads == 0 and allowlist.state_writes == 0
    assert transition.unit_statuses["HIJ_INTRADAY"] == "PASS"
    assert transition.state_reads == 2 and transition.state_writes == 2
    assert transition.transitions == [
        {"from": "NONE", "to": "TREND"},
        {"from": "TREND", "to": "PULLBACK"},
    ]


def test_failure_isolation_keeps_other_units_and_nonzero_exit():
    evidence = ShadowParityHarness().run(default_scenarios()[14])
    assert evidence.status == "FAIL"
    assert evidence.exit_code == 1
    assert evidence.unit_statuses["D_CHART_STORY"] == "FAIL"
    assert evidence.unit_statuses["E_INDICATOR"] == "PASS"
    assert evidence.unit_statuses["HIJ_INTRADAY"] == "PASS"
    assert "artifacts/D_CHART_STORY.json" not in evidence.output_tree
