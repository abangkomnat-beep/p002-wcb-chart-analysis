"""Correctness contracts for the isolated Style E+ adaptive-stop research harness."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tools import style_e_plus_adaptive_stop_ab as ab
from tools import style_e_plus_adaptive_stop as adaptive_stop
from tools import style_e_plus_story as production_story


def bars(count: int = 100, *, start: float = 100.0) -> list[dict]:
    at = datetime(2026, 1, 1)
    result = []
    for index in range(count):
        close = start + (index % 7 - 3) * 0.1
        result.append({
            "at": (at + timedelta(minutes=15 * index)).isoformat(),
            "open": close, "high": close + 1.0, "low": close - 1.0,
            "close": close, "forming": False,
        })
    return result


def pivot_rows(*, side: str, decision_index: int = 30) -> list[dict]:
    result = bars(90)
    pivot_index = decision_index - 4
    if side == "buy":
        for offset, low in zip(range(-2, 3), (98.0, 97.0, 96.0, 97.5, 98.5)):
            result[pivot_index + offset]["low"] = low
        for row in result[max(0, decision_index - 20):decision_index]:
            row["high"] = max(row["high"], 108.0)
    else:
        for offset, high in zip(range(-2, 3), (102.0, 103.0, 104.0, 102.5, 101.5)):
            result[pivot_index + offset]["high"] = high
        for row in result[max(0, decision_index - 20):decision_index]:
            row["low"] = min(row["low"], 92.0)
    return result


def producer_rows(*, daily_spacing: bool = False) -> tuple[list[dict], list[dict]]:
    start = datetime(2023 if daily_spacing else 2025, 1, 1)
    h1_count = 800 if daily_spacing else 500
    h1 = []
    for index in range(h1_count):
        close = 100.0 * (1.005 ** index)
        width = close * 0.01
        h1.append({
            "at": (start + (timedelta(days=index) if daily_spacing
                              else timedelta(hours=index))).isoformat(),
            "open": close - 0.1, "high": close + width,
            "low": close - width, "close": close, "forming": False,
        })
    m15_start = start + (timedelta(days=260) if daily_spacing else timedelta(hours=260))
    m15 = []
    for index in range(400):
        close = 100.2 if index in (258, 260, 300, 340) else 100.0
        if daily_spacing and index >= 1:
            # Keep the decision prefix contiguous for B100's M15 context
            # contract, while retaining a long initial gap for walk-forward
            # temporal coverage. The gap falls outside every eligible context.
            offset = timedelta(days=180) + timedelta(minutes=15 * (index - 1))
        else:
            offset = timedelta(minutes=15 * index)
        m15.append({
            "at": (m15_start + offset).isoformat(),
            "open": 100.0, "high": 101.0, "low": 99.0,
            "close": close, "forming": False,
        })
    pivot_index = 260 - 4
    for offset, low in zip(range(-2, 3), (98.0, 97.0, 96.0, 97.5, 98.5)):
        m15[pivot_index + offset]["low"] = low
    m15[240]["high"] = 110.0
    return h1, m15


def test_baseline_a_is_locked_to_1_5_atr_and_rr_targets():
    buy = ab.baseline_plan("buy", entry_low=99.5, entry_high=100.5, atr=2.0)
    sell = ab.baseline_plan("sell", entry_low=99.5, entry_high=100.5, atr=2.0)
    assert buy["risk_atr"] == sell["risk_atr"] == 1.5
    assert buy["risk"] == sell["risk"] == 3.0
    assert buy["stop"] == 97.5 and sell["stop"] == 102.5
    assert buy["tp1"] == 105.0 and buy["tp2"] == 106.5
    assert sell["tp1"] == 95.0 and sell["tp2"] == 93.5


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_confirmed_pivot_is_2_left_2_right_prefix_only(side):
    source = pivot_rows(side=side)
    pivot = ab.confirmed_pivot(source, decision_index=30, side=side)
    assert pivot == {
        "index": 26, "price": 96.0 if side == "buy" else 104.0,
        "confirmed_index": 28, "left": 2, "right": 2,
    }
    changed_future = source + bars(20, start=1.0)
    assert ab.confirmed_pivot(changed_future, decision_index=30, side=side) == pivot


def test_pivot_ties_and_pivots_older_than_20_decision_bars_are_rejected():
    source = pivot_rows(side="buy", decision_index=30)
    for row in source:
        row["low"] = 99.0
    source[26]["low"] = 96.0
    source[25]["low"] = source[26]["low"]
    assert ab.confirmed_pivot(source, decision_index=30, side="buy") is None
    old = pivot_rows(side="buy", decision_index=30)
    for row in old:
        row["low"] = 99.0
    old[26]["low"] = 96.0
    assert ab.confirmed_pivot(old, decision_index=47, side="buy") is None


@pytest.mark.parametrize(("raw_atr", "accepted", "risk_atr", "reason"), [
    (1.999, True, 2.0, None),
    (2.000, True, 2.0, None),
    (3.000, True, 3.0, None),
    (3.001, False, None, "STOP_GT_3ATR"),
])
def test_adaptive_risk_floor_and_cap_boundaries(raw_atr, accepted, risk_atr, reason):
    result = ab.bounded_adaptive_risk(raw_atr * 10.0, atr=10.0)
    assert result["accepted"] is accepted
    assert result.get("risk_atr") == pytest.approx(risk_atr) if accepted else True
    assert result.get("reason") == reason


@pytest.mark.parametrize(("space_r", "accepted"), [(1.499, False), (1.500, True)])
def test_target_space_boundary_is_locked_at_1_5r(space_r, accepted):
    assert ab.target_space_check(
        side="buy", entry=100.0, boundary=100.0 + space_r * 2.0,
        risk=2.0)["accepted"] is accepted
    assert ab.target_space_check(
        side="sell", entry=100.0, boundary=100.0 - space_r * 2.0,
        risk=2.0)["accepted"] is accepted


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_variant_b_uses_past_pivot_buffer_and_donchian_boundary(side):
    source = pivot_rows(side=side)
    result = ab.adaptive_plan(
        source, decision_index=30, side=side,
        entry_low=99.5, entry_high=100.5, atr=2.0)
    assert result["accepted"] is True
    plan = result["plan"]
    assert 2.0 <= plan["risk_atr"] <= 3.0
    assert plan["pivot"]["index"] == 26
    assert plan["pivot"]["confirmed_index"] <= 30
    assert plan["structure_buffer_atr"] == 0.25
    assert plan["target_space_r"] >= 1.5


def test_variant_b_rejects_no_swing_cap_and_target_space_with_reason_codes():
    source = bars(60)
    for row in source:
        row["low"] = 99.0
    assert ab.adaptive_plan(
        source, decision_index=30, side="buy", entry_low=99.5,
        entry_high=100.5, atr=2.0)["reason"] == "NO_CONFIRMED_SWING"
    cap = pivot_rows(side="buy")
    cap[26]["low"] = 80.0
    assert ab.adaptive_plan(
        cap, decision_index=30, side="buy", entry_low=99.5,
        entry_high=100.5, atr=2.0)["reason"] == "STOP_GT_3ATR"
    tight = pivot_rows(side="buy")
    for row in tight[10:30]:
        row["high"] = min(row["high"], 102.0)
    assert ab.adaptive_plan(
        tight, decision_index=30, side="buy", entry_low=99.5,
        entry_high=100.5, atr=2.0)["reason"] == "TARGET_SPACE_LT_1_5R"


def test_same_bar_stop_and_tp_is_conservative_sl_first():
    source = bars(22)
    source[6].update({"low": 96.0, "high": 104.0, "close": 101.0})
    outcome = ab.evaluate_outcome(
        source, decision_index=5, side="buy", entry=100.0,
        stop=97.0, tp1=103.0, tp2=104.0, horizon=16)
    assert outcome["result"] == "SL"
    assert outcome["expectancy_r"] == -1.0
    assert outcome["ambiguous_intrabar"] is True
    assert outcome["bars_to_stop"] == 1


def test_touch_confirmed_proxy_can_return_no_fill_without_changing_primary():
    source = bars(22, start=110.0)
    primary = ab.evaluate_outcome(
        source, decision_index=5, side="buy", entry=100.0,
        stop=97.0, tp1=103.0, tp2=104.0, horizon=16)
    touch = ab.evaluate_outcome(
        source, decision_index=5, side="buy", entry=100.0,
        stop=97.0, tp1=103.0, tp2=104.0, horizon=16,
        touch_confirmed=True)
    assert primary["filled"] is True
    assert touch["filled"] is False and touch["result"] == "NO_FILL_PROXY"


def test_replay_locks_horizons_skips_overlap_and_is_deterministic():
    source = pivot_rows(side="buy")
    for offset, low in zip(range(-2, 3), (98.0, 97.0, 96.0, 97.5, 98.5)):
        source[66 + offset]["low"] = low
    for row in source[50:70]:
        row["high"] = max(row["high"], 108.0)
    decisions = [
        {"index": 30, "side": "buy", "entry_low": 99.5,
         "entry_high": 100.5, "atr": 2.0, "state": "ENTRY_READY",
         "previous_state": "WAIT_TRIGGER"},
        {"index": 31, "side": "buy", "entry_low": 99.5,
         "entry_high": 100.5, "atr": 2.0, "state": "ENTRY_READY",
         "previous_state": "WAIT_TRIGGER"},
        {"index": 70, "side": "buy", "entry_low": 99.5,
         "entry_high": 100.5, "atr": 2.0, "state": "ENTRY_READY",
         "previous_state": "WAIT_TRIGGER"},
    ]
    first = ab.replay(source, decisions)
    second = ab.replay(source, decisions)
    assert first == second
    assert first["horizons"] == [16, 32, 64]
    assert first["skipped_overlap"] >= 1
    assert set(first["metrics"]) == {"16", "32", "64"}
    assert "a_all_touch" in first["metrics"]["32"]
    assert "b_paired_touch" in first["metrics"]["32"]
    assert "stop_width" in first["metrics"]["32"]
    assert "cost_sensitivity_bps" in first["metrics"]["32"]
    assert "paired_early_stop_4_delta_ci" in first["metrics"]["32"]
    assert first["input_counts"]["h1_eligible"] == len(decisions)
    assert all(event["b"]["plan"]["prefix_end_index"] == event["decision_index"]
               for event in first["events"] if event["b"]["accepted"])


def test_replay_only_creates_events_for_transition_into_entry_ready():
    source = pivot_rows(side="buy", decision_index=60)
    decisions = [
        {"index": 30, "state": "NO_PLAN", "previous_state": "NO_PLAN"},
        {"index": 40, "state": "NO_CHASE", "previous_state": "WAIT_TRIGGER"},
        {"index": 50, "state": "WAIT_TRIGGER", "previous_state": "NO_PLAN",
         "side": "buy", "entry_low": 99.5, "entry_high": 100.5, "atr": 2.0},
        {"index": 60, "state": "ENTRY_READY", "previous_state": "WAIT_TRIGGER",
         "side": "buy", "entry_low": 99.5, "entry_high": 100.5, "atr": 2.0},
        {"index": 70, "state": "ENTRY_READY", "previous_state": "ENTRY_READY",
         "side": "buy", "entry_low": 99.5, "entry_high": 100.5, "atr": 2.0},
    ]
    result = ab.replay(source, decisions)
    assert len(result["events"]) == 1
    assert result["events"][0]["decision_index"] == 60
    assert result["input_counts"]["states"] == {
        "ENTRY_READY": 2, "NO_CHASE": 1, "NO_PLAN": 1, "WAIT_TRIGGER": 1}
    assert result["input_counts"]["entry_ready_transitions"] == 1
    assert result["input_counts"]["non_entry_states_skipped"] == 4


def test_adaptive_plan_is_invariant_to_rows_after_decision():
    source = pivot_rows(side="sell")
    before = ab.adaptive_plan(
        source, decision_index=30, side="sell",
        entry_low=99.5, entry_high=100.5, atr=2.0)
    changed = [dict(row) for row in source]
    for row in changed[31:]:
        row.update({"high": 999.0, "low": 1.0, "close": 500.0})
    after = ab.adaptive_plan(
        changed, decision_index=30, side="sell",
        entry_low=99.5, entry_high=100.5, atr=2.0)
    assert before == after


def test_state_compatibility_keeps_four_public_states_and_never_claims_fill():
    for state in ("NO_PLAN", "NO_CHASE", "WAIT_TRIGGER", "ENTRY_READY"):
        accepted = state in {"WAIT_TRIGGER", "ENTRY_READY"}
        result = ab.state_compatibility(state, b_accepted=accepted)
        assert result["public_state"] in ab.PUBLIC_STATES
        assert result["synthetic_fill_only"] is True
        assert result["position_confirmed"] is False
        assert result["protective_stop_active"] is False
    assert ab.state_compatibility("ENTRY_READY", b_accepted=False)["research_state"] == "NO_PLAN"


def test_decision_producer_recomputes_production_prefixes_with_provenance():
    h1, m15 = producer_rows()
    result = ab.derive_decisions(h1, m15, dataset_sha256="fixture-dataset")
    assert result["schema"].endswith("/derived-decisions")
    assert result["producer_id"] == ab.PRODUCER_ID
    assert len(result["producer_code_sha256"]) == 64
    assert len(result["production_oracle_code_sha256"]) == 64
    assert result["dataset_sha256"] == "fixture-dataset"
    transitions = [event for event in result["events"]
                   if event["state"] == "ENTRY_READY"
                   and event["previous_state"] != "ENTRY_READY"]
    assert transitions
    event = transitions[0]
    evidence = event["evidence"]
    h1_prefix = h1[:evidence["h1_prefix_count"]]
    m15_prefix = m15[:event["index"] + 1]
    h1_indicators = production_story._indicator_contract(h1_prefix)
    side, _ = production_story._h1_bias(h1_indicators)
    m15_indicators = production_story._m15_indicator_contract(m15_prefix)
    state, plan, _, _ = production_story._m15_decision(
        m15_indicators, m15_prefix[-1]["close"], side,
        plan_created_at=evidence["m15_decision_close_at"],
        context=adaptive_stop.build_context(m15_prefix))
    assert (event["state"], event["side"]) == (state, side)
    assert event["entry_low"] == pytest.approx(plan["entry_zone_low"])
    assert event["entry_high"] == pytest.approx(plan["entry_zone_high"])
    assert event["atr"] == pytest.approx(m15_indicators["atr"]["value"])
    assert evidence["h1_prefix_closed_at"] <= evidence["m15_decision_close_at"]


def test_decision_event_is_invariant_to_h1_and_m15_future_mutation():
    h1, m15 = producer_rows()
    original = ab.derive_decisions(h1, m15, dataset_sha256="before")
    target = next(event for event in original["events"]
                  if event["state"] == "ENTRY_READY"
                  and event["previous_state"] != "ENTRY_READY")
    changed_h1, changed_m15 = deepcopy(h1), deepcopy(m15)
    h1_cutoff = target["evidence"]["h1_prefix_count"]
    for row in changed_h1[h1_cutoff:]:
        row.update({"open": 5000.0, "high": 6000.0, "low": 4000.0, "close": 5500.0})
    for row in changed_m15[target["index"] + 1:]:
        row.update({"open": 500.0, "high": 600.0, "low": 400.0, "close": 550.0})
    changed = ab.derive_decisions(changed_h1, changed_m15, dataset_sha256="after")
    changed_target = next(event for event in changed["events"]
                          if event["index"] == target["index"])
    assert changed_target == target


@pytest.mark.parametrize(("field", "mutator"), [
    ("side", lambda value: "sell" if value == "buy" else "buy"),
    ("state", lambda _value: "NO_CHASE"),
    ("entry_low", lambda value: value + 1.0),
    ("atr", lambda value: value + 1.0),
])
def test_decision_cache_rejects_tampered_production_fields(tmp_path, field, mutator):
    h1, m15 = producer_rows()
    derived = ab.derive_decisions(h1, m15, dataset_sha256="fixture-dataset")
    target = next(event for event in derived["events"]
                  if event["state"] == "ENTRY_READY"
                  and event["previous_state"] != "ENTRY_READY")
    target[field] = mutator(target[field])
    cache = tmp_path / "tampered.json"
    cache.write_text(json.dumps(derived), encoding="utf-8")
    clean = ab.derive_decisions(h1, m15, dataset_sha256="fixture-dataset")
    with pytest.raises(ab.ResearchError, match="rejects tampering"):
        ab._validate_decision_cache(cache, derived=clean)


def test_horizon_metrics_censor_incomplete_tail_at_exact_boundaries():
    source = pivot_rows(side="buy")
    while len(source) < 95:
        row = dict(source[-1])
        row["at"] = (datetime.fromisoformat(source[-1]["at"])
                     + timedelta(minutes=15)).isoformat()
        source.append(row)
    decision = [{
        "index": 30, "side": "buy", "entry_low": 99.5,
        "entry_high": 100.5, "atr": 2.0, "state": "ENTRY_READY",
        "previous_state": "WAIT_TRIGGER",
    }]
    sixteen = ab.replay(source[:47], decision)
    assert sixteen["metrics"]["16"]["a_eligible"] == 1
    assert sixteen["metrics"]["32"]["a_eligible"] == 0
    assert sixteen["metrics"]["32"]["a_all"]["censor_reasons"] == {
        "INCOMPLETE_HORIZON": 1}
    assert sixteen["metrics"]["32"]["counts"]["rejects_b"] == 0
    assert sixteen["metrics"]["32"]["counts"]["signals_censored"] == 1
    thirty_two = ab.replay(source[:63], decision)
    assert thirty_two["metrics"]["32"]["a_eligible"] == 1
    assert thirty_two["metrics"]["64"]["a_eligible"] == 0
    sixty_four = ab.replay(source[:95], decision)
    assert sixty_four["metrics"]["64"]["a_eligible"] == 1


def test_preflight_reports_blocked_data_for_short_local_snapshot(tmp_path):
    snapshot = {
        "schema": "fixture", "asset": "btcusd", "analysis_at": "2026-01-03T00:00:00+00:00",
        "timeframes": {
            "15min": {"rows": bars(300), "source_label": "fixture:m15",
                      "candle_basis": {"timezone": "Asia/Bangkok"}},
            "1h": {"rows": bars(300), "source_label": "fixture:h1",
                   "candle_basis": {"timezone": "Asia/Bangkok"}},
        },
    }
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    report = ab.preflight_snapshot(path)
    assert report["status"] == "BLOCKED_DATA"
    assert report["minimum_days"] == 180
    assert report["timeframes"]["15min"]["row_count"] == 300
    assert report["dataset_sha256"] == ab.sha256(path)


def test_blocked_run_is_atomic_hashed_deterministic_and_research_only(tmp_path):
    snapshot = {
        "schema": "fixture", "asset": "btcusd", "analysis_at": "2026-01-03T00:00:00+00:00",
        "timeframes": {
            "15min": {"rows": bars(300), "source_label": "fixture:m15",
                      "candle_basis": {"timezone": "Asia/Bangkok"}},
            "1h": {"rows": bars(300), "source_label": "fixture:h1",
                   "candle_basis": {"timezone": "Asia/Bangkok"}},
        },
    }
    source = tmp_path / "source.json"
    source.write_text(json.dumps(snapshot), encoding="utf-8")
    target = tmp_path / "research"
    result = ab.run_experiment(snapshot_path=source, output_root=target)
    assert result["data_status"] == "BLOCKED_DATA"
    assert result["decision"] == "INCONCLUSIVE"
    assert result["production_changed"] is False
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["config"]["trigger_buffer_atr"] is None
    assert set(manifest["files"]) == {
        path.name for path in target.iterdir() if path.name != "manifest.json"}
    for name, evidence in manifest["files"].items():
        artifact = target / name
        assert evidence == {"bytes": artifact.stat().st_size,
                            "sha256": ab.sha256(artifact)}
    assert len(list(target.glob("*.webp"))) >= 6
    assert all("RESEARCH A/B" in path.with_suffix(".json").read_text(encoding="utf-8")
               for path in target.glob("*.webp"))
    for path in target.glob("*.webp"):
        visual = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        assert set(("entry_zone", "confirmed_pivot", "variant_a", "variant_b",
                    "donchian_boundary")).issubset(visual)
        assert visual["entry"] == (visual["entry_zone"]["high"]
                                    if visual["side"] == "buy"
                                    else visual["entry_zone"]["low"])
        assert visual["variant_a"]["risk_atr"] == 1.5
        if visual["variant_b"]["accepted"]:
            assert 2.0 <= visual["variant_b"]["plan"]["risk_atr"] <= 3.0
        else:
            assert visual["variant_b"]["plan"] is None
        assert visual["visible_prefix_end"] < visual["future_outcome_start"]


def test_pass_data_path_derives_decisions_and_runs_walk_forward_without_oos(
        tmp_path, monkeypatch):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"asset": "btcusd"}), encoding="utf-8")
    h1_rows, source_rows = producer_rows(daily_spacing=True)
    fake_preflight = {
        "schema": "fixture", "status": "PASS", "reasons": [],
        "local_only": True, "network_used": False, "source_path": str(source),
        "dataset_sha256": "locked-dataset", "minimum_days": 180,
        "target_days": 365, "usable_days_after_warmup": 300,
        "timeframes": {}, "h1_from_m15_crosscheck": {"status": "PASS"},
        "normalized_rows": {"1h": h1_rows, "15min": source_rows},
    }
    monkeypatch.setattr(ab, "preflight_snapshot", lambda _path: deepcopy(fake_preflight))
    target = tmp_path / "pass-research"
    result = ab.run_experiment(snapshot_path=source, output_root=target)
    assert result["data_status"] == "PASS"
    assert result["locked_oos_opened"] is False
    metrics = json.loads((target / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["status"] == "RUN_DEVELOPMENT_VALIDATION"
    assert len(metrics["walk_forward"]["folds"]) >= 4
    assert metrics["replay"]["input_counts"]["entry_ready_transitions"] > 0
    assert set(metrics["replay"]["metrics"]) == {"16", "32", "64"}
    derived = json.loads((target / "derived-decisions.json").read_text(encoding="utf-8"))
    assert derived["producer_id"] == ab.PRODUCER_ID
    validation_end = json.loads(
        (target / "split-manifest.json").read_text(encoding="utf-8"))[
            "splits"]["validation"]["end_index_exclusive"]
    assert max(event["index"] for event in derived["events"]) < validation_end
    assert derived["excluded_oos_count"] == len(source_rows) - validation_end
    assert derived["dataset_hash_scope"] == "development_validation_prefix"
    report = json.loads((target / "research-report.json").read_text(encoding="utf-8"))
    assert report["locked_oos_opened"] is False
    assert report["checkpoint_d"] in {"GO_REVIEW", "HOLD"}
    cached_target = tmp_path / "pass-research-from-verified-cache"
    cached = ab.run_experiment(
        snapshot_path=source, decisions_path=target / "derived-decisions.json",
        output_root=cached_target)
    assert cached["locked_oos_opened"] is False
    cache_evidence = json.loads(
        (cached_target / "decision-cache-evidence.json").read_text(encoding="utf-8"))
    assert cache_evidence["exact_recomputation_match"] is True
    changed_preflight = deepcopy(fake_preflight)
    changed_preflight["dataset_sha256"] = "changed-full-dataset"
    for row in changed_preflight["normalized_rows"]["15min"][validation_end:]:
        row.update({"open": 500.0, "high": 600.0, "low": 400.0, "close": 550.0})
    monkeypatch.setattr(
        ab, "preflight_snapshot", lambda _path: deepcopy(changed_preflight))
    changed_target = tmp_path / "pass-research-oos-mutated"
    ab.run_experiment(snapshot_path=source, output_root=changed_target)
    changed_derived = json.loads(
        (changed_target / "derived-decisions.json").read_text(encoding="utf-8"))
    assert changed_derived == derived


def test_research_module_is_not_imported_by_production_entrypoints():
    repo = Path(__file__).resolve().parents[1]
    forbidden = "style_e_plus_adaptive_stop_ab"
    production = [path for path in (repo / "tools").glob("*.py")
                  if path.name != f"{forbidden}.py"]
    assert all(forbidden not in path.read_text(encoding="utf-8") for path in production)
    assert ab.CONFIG["trigger_buffer_atr"] is None
    assert "0.10" not in Path(ab.__file__).read_text(encoding="utf-8")
