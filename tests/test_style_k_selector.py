"""เทสตัวเลือกหลักฐานและตัวสร้างสถานการณ์

กันสองอย่างที่พังเงียบได้ง่ายที่สุด: ผลที่แกว่งไปมาระหว่างรัน และการลดเกณฑ์
เพื่อให้เขียนบทได้เมื่อหลักฐานไม่พอ
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from tools import style_k_dataset as ds  # noqa: E402
from tools import style_k_scenarios as sc  # noqa: E402
from tools import style_k_selector as sel  # noqa: E402
from tools import style_k_techniques as tk  # noqa: E402
from tests.test_style_k_no_lookahead import bars, make_bundle  # noqa: E402


@pytest.fixture
def config() -> dict:
    return ds.load_config()


@pytest.fixture
def record(config) -> dict:
    rows = bars(300)
    return tk.build_evidence(make_bundle(rows, rows[-1]["date"]), config=config)


@pytest.fixture
def two_sided_record(config) -> dict:
    """ราคาที่ย่อลงจากยอด — จึงมีระดับทั้งเหนือและใต้ราคาให้เขียนเงื่อนไขได้

    ชุด `record` เป็นขาขึ้นล้วนจนราคาอยู่เหนือทุกระดับ ซึ่งเป็นกรณี no-trade
    ที่ถูกต้อง แต่ทดสอบเนื้อหาของ scenario ไม่ได้
    """
    import datetime as dt
    rows = bars(300)
    last = rows[-1]
    day = dt.date.fromisoformat(last["date"])
    for step in range(1, 6):
        close = last["close"] - 4.0 * step
        rows.append({
            "date": (day + dt.timedelta(days=step)).isoformat(),
            "open": close + 1.5, "high": close + 2.5,
            "low": close - 2.5, "close": close,
        })
    return tk.build_evidence(make_bundle(rows, rows[-1]["date"]), config=config)


def test_selection_is_deterministic(record, config):
    first = sel.select(record, config=config)
    second = sel.select(record, config=config)
    assert ds.hash_payload(first) == ds.hash_payload(second)


def test_selection_order_does_not_depend_on_evidence_order(record, config):
    shuffled = dict(record)
    shuffled["evidence"] = list(reversed(record["evidence"]))
    assert sel.select(record, config=config)["primary_evidence_id"] == \
        sel.select(shuffled, config=config)["primary_evidence_id"]


def test_selection_respects_counts_and_families(record, config):
    selection = sel.select(record, config=config)
    assert sel.selection_problems(selection, record) == []


def test_unavailable_evidence_is_never_selected(record, config):
    selection = sel.select(record, config=config)
    by_id = {unit["evidence_id"]: unit for unit in record["evidence"]}
    chosen = [selection["primary_evidence_id"], *selection["supporting_evidence_ids"],
              *selection["conflicting_evidence_ids"]]
    assert all(by_id[key]["quality"] != tk.QUALITY_UNAVAILABLE for key in chosen)


def test_thin_evidence_produces_watch_not_a_lowered_bar(config):
    """หลักฐานน้อยต้องออก watch/insufficient — ห้ามลดเกณฑ์เพื่อให้มีบท"""
    record = tk.build_evidence(make_bundle(bars(20), bars(20)[-1]["date"]), config=config)
    selection = sel.select(record, config=config)
    assert selection["decision"] in {sel.DECISION_WATCH, sel.DECISION_INSUFFICIENT}
    assert selection["reason_codes"]


def test_no_trade_carries_a_reason_and_no_fabricated_levels(config):
    record = tk.build_evidence(make_bundle(bars(20), bars(20)[-1]["date"]), config=config)
    selection = sel.select(record, config=config)
    manifest = sc.build_scenarios(record, selection)
    assert manifest["scenarios"] == []
    assert manifest["no_trade_reason"]
    assert sc.scenario_problems(manifest, record) == []


def _unit(evidence_id, *, family, direction, prices) -> dict:
    return {
        "evidence_id": evidence_id, "asset": "xauusd", "session_date": "2026-08-07",
        "cutoff": "2026-08-07T23:59:59+00:00", "timeframe": "D1", "technique_group": 1,
        "technique_name": "Market Structure", "independence_family": family,
        "observation": {"type": "higher_high_higher_low"}, "interpretation": "ทดสอบ",
        "direction": direction, "certainty": "confirmed",
        "level_refs": [{"label": "ระดับทดสอบ", "price": price} for price in prices],
        "source_refs": ["2026-08-07"], "quality": "pass", "explainability": 1.0,
        "limitations": [],
    }


def test_price_above_every_measurable_level_is_an_honest_no_trade():
    """ราคายืนเหนือทุกระดับที่วัดได้ = เขียนเงื่อนไขยืนยันฝั่งบนไม่ได้ ต้องบอกตรง ๆ

    กรณีนี้เกิดจริงกับ XAUUSD วันที่ 2026-08-07 ในชุด pilot — ทองทำระดับสูงกว่า
    ทุกจุดกลับตัวที่ยืนยันแล้ว จึงไม่มีระดับใดอยู่เหนือราคาให้ใช้เป็นเงื่อนไข
    """
    record = {
        "asset": "xauusd", "session_date": "2026-08-07",
        "cutoff": "2026-08-07T23:59:59+00:00", "reference_price": 4342.63,
        "atr14": 97.19, "unavailable_groups": [6, 8],
        "evidence": [_unit("E1", family="structure", direction="bullish", prices=[4200.0]),
                     _unit("E2", family="trend", direction="bullish", prices=[4100.0]),
                     _unit("E3", family="zone", direction="bullish", prices=[4000.0])],
    }
    selection = {
        "decision": sel.DECISION_ARTICLE, "bias": "bullish",
        "primary_evidence_id": "E1", "supporting_evidence_ids": ["E2", "E3"],
        "conflicting_evidence_ids": [], "reason_codes": [],
    }
    manifest = sc.build_scenarios(record, selection)
    assert manifest["scenarios"] == []
    assert "ไม่แต่งระดับขึ้นเอง" in manifest["no_trade_reason"]


def test_level_pool_widens_before_giving_up_and_says_so():
    """ระดับฝั่งที่ขาดหาจากหลักฐานนอกชุดได้ แต่ต้องติดธงว่าไม่ได้มาจากชุดที่บทเล่า"""
    record = {
        "asset": "xauusd", "session_date": "2026-08-07",
        "cutoff": "2026-08-07T23:59:59+00:00", "reference_price": 4342.63,
        "atr14": 97.19, "unavailable_groups": [],
        "evidence": [_unit("E1", family="structure", direction="bullish", prices=[4200.0]),
                     _unit("E2", family="trend", direction="bullish", prices=[4100.0]),
                     _unit("E3", family="zone", direction="bullish", prices=[4000.0]),
                     _unit("E9", family="liquidity", direction="neutral", prices=[4400.0])],
    }
    selection = {
        "decision": sel.DECISION_ARTICLE, "bias": "bullish",
        "primary_evidence_id": "E1", "supporting_evidence_ids": ["E2", "E3"],
        "conflicting_evidence_ids": [], "reason_codes": [],
    }
    manifest = sc.build_scenarios(record, selection)
    assert manifest["scenarios"], "มีระดับฝั่งบนในหลักฐานชิ้นอื่นแล้วต้องเขียนได้"
    assert manifest["level_pool_notes"], "การขยายพูลต้องถูกบันทึกไว้เสมอ"
    assert manifest["scenarios"][0]["confirmation_rule"]["level_evidence_id"] == "E9"


def test_scenarios_are_machine_checkable_and_opposite(two_sided_record, config):
    record = two_sided_record
    selection = sel.select(record, config=config)
    manifest = sc.build_scenarios(record, selection)
    assert sc.scenario_problems(manifest, record) == []
    scenario_a, scenario_b = manifest["scenarios"]
    assert scenario_a["bias"] != scenario_b["bias"]
    for scenario in manifest["scenarios"]:
        assert isinstance(scenario["confirmation_rule"]["level"], float)
        assert scenario["confirmation_rule"]["level"] != scenario["invalidation_rule"]["level"]


def test_scenario_levels_always_reference_real_evidence(two_sided_record, config):
    record = two_sided_record
    selection = sel.select(record, config=config)
    manifest = sc.build_scenarios(record, selection)
    ids = {unit["evidence_id"] for unit in record["evidence"]}
    assert manifest["scenarios"], "ชุดสองฝั่งต้องเขียนเงื่อนไขได้"
    for scenario in manifest["scenarios"]:
        assert scenario["confirmation_rule"]["level_evidence_id"] in ids
        assert scenario["invalidation_rule"]["level_evidence_id"] in ids


def test_outcome_fields_are_not_available_to_the_selector(record, config):
    """ตัวเลือกต้องไม่มีทางเห็นผลจริง — ตรวจว่า record ที่มันรับไม่มีคีย์ฝั่งวัดผลเลย"""
    forbidden = {"mfe", "mae", "first_event", "scenario_status", "target_reached",
                 "confirmation_triggered", "invalidation_triggered"}
    assert not forbidden & set(record)
    for unit in record["evidence"]:
        assert not forbidden & set(unit)
