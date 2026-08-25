"""Foundation-only tests; these never invoke production routing or a network."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.result_envelope import ResultEnvelope
from tools.source_planner import ApiTrace, SourcePlanner, SourceRequest, TraceRecorder
from tools.unified_orchestrator import (
    OutputFS,
    PublishGuard,
    RunContext,
    SelectionPort,
    SideEffectDenied,
    StateStore,
    UnifiedStyleOrchestrator,
    VisualReferenceReviewer,
    compare_decoded_pixel_parity,
    decoded_rgba_digest,
    rollback_smoke,
)
from tools.unified_registry import RegistryError, RegistryLoader, validate_registry


TARGET_LETTERS = "ABCDEFGHIJL"


def _registry() -> dict:
    styles = {}
    units = {}
    adapters = {
        "A": "abc_public", "B": "abc_public", "C": "abc_public",
        "D": "d_chart_story", "E": "e_indicator", "F": "fg_brief",
        "G": "fg_brief", "H": "hij_intraday", "I": "hij_intraday",
        "J": "hij_intraday", "L": "forex_daily_plan",
    }
    for order, letter in enumerate(TARGET_LETTERS):
        sid = f"style_{letter.lower()}"
        unit = f"UNIT_{letter}"
        styles[sid] = {
            "id": sid, "letter": letter, "name": f"Style {letter}",
            "folder": f"{letter}-folder", "execution_unit": unit,
            "adapter": adapters[letter], "order": order,
            "assets": ["xauusd"], "timeframes": ["1d"],
            "trigger": "daily", "production": False,
            "migration_mode": "legacy", "publish_eligible": True,
        }
        units[unit] = {
            "id": unit, "members": [sid], "order": order,
            "migration_mode": "legacy", "rollback_mode": "legacy",
            "execute_once_per_asset": True,
        }
    return {"schema": "article-styles-v2", "styles": styles, "execution_units": units}


def test_production_registry_has_only_hij_on_the_first_unified_unit():
    path = Path(__file__).parents[1] / "config" / "article_styles.json"
    registry = RegistryLoader().load(path)
    assert registry.source_schema == "article-styles-v2"
    assert registry.execution_units["HIJ_INTRADAY"].migration_mode == "unified"
    assert registry.execution_units["HIJ_INTRADAY"].rollback_mode == "legacy"
    assert registry.execution_units["HIJ_INTRADAY"].members == (
        "h_trend_strength", "i_volatility_breakout", "j_pullback_continuation",
    )
    assert "K" not in registry.letters


@pytest.mark.parametrize("mutation", [
    lambda d: d["styles"]["style_a"]["letter"] if False else None,
])
def test_v2_target_registry_is_valid(mutation):
    # The parameter keeps this test compatible with pytest's subtest accounting;
    # no mutation is applied to the fixture.
    assert set(validate_registry(_registry(), require_target=True).letters) == set(TARGET_LETTERS)


def test_invalid_registry_fails_closed_before_any_injected_work():
    bad = _registry()
    bad["styles"]["style_a"]["adapter"] = "unknown"
    with pytest.raises(RegistryError, match="unknown adapter"):
        RegistryLoader().load(bad, require_target=True)

    bad = _registry()
    bad["styles"]["style_a"]["letter"] = "K"
    with pytest.raises(RegistryError, match="retired"):
        RegistryLoader().load(bad, require_target=True)


def test_source_plan_is_declarative_and_trace_is_injected():
    plan = SourcePlanner().plan(
        execution_unit="UNIT_D", asset="xauusd",
        requests=[
            {"provider": "WCB", "timeframe": "1d", "request_role": "series"},
            {"provider": "WCB", "timeframe": "calendar", "request_role": "calendar", "endpoint_kind": "calendar"},
        ],
    )
    trace = ApiTrace()
    recorder = TraceRecorder(trace)
    values = [recorder.fetch(req, lambda _: {"fixture": True}) for req in plan.ordered_requests]
    trace.assert_matches(plan)
    assert values == [{"fixture": True}, {"fixture": True}]
    assert trace.to_dict()["entries"][0]["ordinal"] == 0


def test_envelope_statuses_and_child_mapping():
    parent = ResultEnvelope.from_legacy(
        {"status": "PASS", "children": [{"style_id": "A", "status": "PASS"}, {"style_id": "B", "status": "SKIP"}]},
        run_id="r1", asset="xauusd", execution_unit="ABC_PUBLIC", style_ids=["A", "B", "C"],
    )
    assert parent.status == "PASS"
    assert [child.style_ids for child in parent.children] == [["A"], ["B"]]
    assert parent.aggregate_status == "PASS"
    assert ResultEnvelope.fail("r1", "xauusd", "D", ["D"]).exit_code == 1


def test_orchestrator_legacy_default_does_not_invoke_adapters(tmp_path):
    calls = []
    orchestrator = UnifiedStyleOrchestrator({"UNIT_A": lambda *args: calls.append(args) or {"status": "PASS"}})
    context = RunContext("legacy-1", "2026-08-20T00:00:00Z", assets=("xauusd",),
                         output_root=tmp_path / "out", work_root=tmp_path / "work", state_root=tmp_path / "state")
    results = orchestrator.execute(context, _registry(), {})
    assert calls == []
    assert results and all(item.reason_code == "LEGACY_MODE" for item in results)
    assert not (tmp_path / "out").exists()


def test_orchestrator_shadow_uses_one_adapter_per_unit_and_temp_ports(tmp_path):
    registry = _registry()
    plans = {f"UNIT_{letter}": SourcePlanner().plan(
        execution_unit=f"UNIT_{letter}", asset="xauusd",
        requests=[SourceRequest("fixture", "xauusd", "1d", "series")],
    ) for letter in TARGET_LETTERS}
    calls = []

    def adapter(context, asset, plan, output, state):
        calls.append(plan.execution_unit)
        output.write_json(f"audit/{plan.execution_unit}.json", {"asset": asset})
        return {"status": "PASS", "children": [{"style_id": plan.execution_unit, "status": "PASS"}]}

    orchestrator = UnifiedStyleOrchestrator({f"UNIT_{letter}": adapter for letter in TARGET_LETTERS})
    context = RunContext("shadow-1", "2026-08-20T00:00:00Z", assets=("xauusd",), mode="shadow",
                         output_root=tmp_path / "out", work_root=tmp_path / "work", state_root=tmp_path / "state")
    output = OutputFS(context.output_root)
    state = StateStore(context.state_root)
    results = orchestrator.execute(context, registry, plans, output_fs=output, state_store=state)
    assert calls == [f"UNIT_{letter}" for letter in TARGET_LETTERS]
    assert len(results) == 11 and all(item.exit_code == 0 for item in results)
    assert len(output.snapshot()) == 11
    assert state.write_count == 0


def test_temp_state_counter_and_no_duplicate_write(tmp_path):
    state = StateStore(tmp_path / "state")
    assert state.read("xauusd/H", {}) == {}
    state.write("xauusd/H", {"state": "new"})
    assert state.read("xauusd/H")["state"] == "new"
    assert state.read_count == 2
    assert state.write_count == 1
    assert state.writes_for("xauusd/H") == 1


def test_selection_and_publish_guards_are_explicit(tmp_path):
    selection = SelectionPort(selected=("xauusd",))
    assert selection.select(("xauusd", "eurusd")) == ("xauusd",)
    assert selection.calls == 1
    guard = PublishGuard()
    assert guard.check(no_publish=True) is False
    with pytest.raises(SideEffectDenied):
        guard.publish(tmp_path / "production", no_publish=True)


def test_agent10_visual_reviewer_has_no_write_or_repair_path(tmp_path):
    image = tmp_path / "reference.bin"
    image.write_bytes(b"fixture")
    reviewer = VisualReferenceReviewer()
    assert reviewer.inspect(image)["write"] is False
    with pytest.raises(SideEffectDenied):
        reviewer.write(image, b"changed")
    with pytest.raises(SideEffectDenied):
        reviewer.repair(image)


def test_d_e_decoded_pixel_digest_uses_rgba_not_raw_hash():
    image = Path(__file__).parent / "fixtures" / "pilot-baseline" / "2026-08-03_xauusd.png"
    dimensions, digest = decoded_rgba_digest(image)
    assert dimensions[0] > 0 and dimensions[1] > 0
    assert len(digest) == 64


def test_d_e_pixel_drift_is_fail_unless_explicitly_allowlisted(tmp_path):
    actual = Path(__file__).parent / "fixtures" / "pilot-baseline" / "2026-08-03_xauusd.png"
    expected = tmp_path / "drift.png"
    from PIL import Image
    with Image.open(actual) as image:
        altered = image.convert("RGBA")
        altered.putpixel((0, 0), (255, 0, 0, 255))
        altered.save(expected)
    assert compare_decoded_pixel_parity(actual, actual)["status"] == "PASS"
    assert compare_decoded_pixel_parity(actual, expected)["status"] == "FAIL"
    assert compare_decoded_pixel_parity(actual, expected, allowlisted=True)["status"] == "ALLOWLISTED"


def test_rollback_smoke_keeps_all_units_legacy():
    result = rollback_smoke(_registry())
    assert len(result) == len(TARGET_LETTERS)
    assert set(result.values()) == {"legacy"}


def test_golden_matrix_contains_exactly_16_scenarios():
    matrix = json.loads((Path(__file__).parent / "fixtures" / "unified" / "parity_matrix.json").read_text())
    assert [item["id"] for item in matrix["scenarios"]] == [f"G{i:02d}" for i in range(1, 17)]
    assert matrix["production_delta_expected"] == 0


def test_shadow_context_cannot_publish_or_escape_root(tmp_path):
    with pytest.raises(SideEffectDenied):
        RunContext("bad", "2026-08-20T00:00:00Z", mode="shadow", no_publish=False)
    output = OutputFS(tmp_path / "out")
    with pytest.raises(SideEffectDenied):
        output.write_bytes("../production.txt", b"no")
