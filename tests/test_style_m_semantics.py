from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timedelta

import pytest

from tools import style_m_article_contract, style_m_semantics, style_m_story


BKK = style_m_story.BANGKOK
CUTOFF = datetime(2026, 8, 31, 11, 0, tzinfo=BKK)


def rows_fixture(count: int = 130) -> list[dict]:
    start = CUTOFF - timedelta(hours=count)
    rows = []
    for index in range(count):
        close = 78_400.0 - index * 2.0
        rows.append({
            "index": index,
            "at": (start + timedelta(hours=index)).strftime("%Y-%m-%d %H:%M:%S"),
            "open": close + 20.0,
            "high": close + 180.0,
            "low": close - 180.0,
            "close": close,
        })
    rows[-1].update({"open": 77_474.0, "high": 77_872.0,
                     "low": 77_394.0, "close": 77_756.71})
    return rows


def conflict_story(rows: list[dict] | None = None) -> dict:
    rows = rows or rows_fixture()
    highs = [
        {"index": 58, "at": rows[58]["at"], "price": 80_520.0},
        {"index": 74, "at": rows[74]["at"], "price": 80_848.74},
        {"index": 112, "at": rows[112]["at"], "price": 78_966.76},
        {"index": 119, "at": rows[119]["at"], "price": 79_400.0},
    ]
    lows = [
        {"index": 105, "at": rows[105]["at"], "price": 77_962.49},
        {"index": 124, "at": rows[124]["at"], "price": 77_000.0},
    ]
    story = {
        "schema": style_m_story.SCHEMA,
        "asset": "btcusd",
        "timeframe": "1h",
        "cutoff": CUTOFF.isoformat(),
        "latest": {key: rows[-1][key] for key in ("at", "open", "high", "low", "close")},
        "indicators": {"ema20": 78_220.4937, "ema50": 78_306.3061, "atr14": 459.9026},
        "pivots": {"highs": highs, "lows": lows},
        "source_label": "fixture",
        "source_meta": {},
        "source_sha256": "a" * 64,
        "volume_policy": "unavailable-and-forbidden",
        "state": "NO_PLAN",
        "side": None,
        "reason_code": "STRUCTURE_CONFLICT",
        "reason": "โครงสร้างและเส้นเฉลี่ยยังไม่ให้ทิศเดียวกัน",
        "show_plan_geometry": False,
        "plan": None,
    }
    story["source_sha256"] = projection_hash(story, rows)
    style_m_story.validate(story)
    return story


def test_f03_real_20260831_conflict_relations():
    rows = rows_fixture()
    story = conflict_story(rows)
    base = style_m_article_contract._build_base_facts(story, rows)
    semantic = style_m_semantics.build(story, base, rows)

    assert semantic["schema"] == "style-m-semantic-decision/v1"
    assert semantic["oracle"] == {
        "schema": "style-m-story/v1", "state": "NO_PLAN", "side": None,
        "reason_code": "STRUCTURE_CONFLICT",
    }
    assert semantic["relations"]["ema_stack"]["value"] == "BEARISH"
    assert semantic["relations"]["close_position"]["value"] == "BELOW_BOTH"
    assert semantic["relations"]["high_relation"]["value"] == "HIGHER_HIGH"
    assert semantic["relations"]["low_relation"]["value"] == "LOWER_LOW"
    assert semantic["relations"]["structure_pattern"]["value"] == "EXPANDING_HH_LL"
    assert semantic["decision"]["alignment"] == "MIXED"
    assert semantic["decision"]["implication"] == "WAIT_FOR_ALIGNMENT"
    assert semantic["decision"]["supporting_claim_ids"]
    assert semantic["decision"]["contradicting_claim_ids"]
    assert semantic["oracle"]["state"] == story["state"]
    assert semantic["oracle"]["side"] == story["side"]


def test_same_input_semantic_json_and_hash_are_identical():
    rows = rows_fixture()
    story = conflict_story(rows)
    base = style_m_article_contract._build_base_facts(story, rows)
    assert style_m_semantics.build(story, base, rows) == style_m_semantics.build(story, base, rows)


def test_story_state_mutation_after_projection_blocks():
    rows = rows_fixture()
    story = conflict_story(rows)
    base = style_m_article_contract._build_base_facts(story, rows)
    semantic = style_m_semantics.build(story, base, rows)
    changed = copy.deepcopy(story)
    changed["state"] = "INVALIDATED"
    changed["reason_code"] = "STOP_INVALIDATED"
    with pytest.raises(style_m_semantics.SemanticContractError) as caught:
        style_m_semantics.validate(semantic, story=changed, base_facts=base, rows=rows)
    assert caught.value.code == "SEM_ORACLE_BINDING_MISMATCH"


def test_unknown_reason_state_pair_blocks_without_fallback():
    rows = rows_fixture()
    story = conflict_story(rows)
    story["reason_code"] = "UNKNOWN_REASON"
    base = style_m_article_contract._build_base_facts(story, rows)
    with pytest.raises(style_m_semantics.SemanticContractError) as caught:
        style_m_semantics.build(story, base, rows)
    assert caught.value.code == "SEM_UNKNOWN_REASON_STATE"


def test_trendline_intermediate_high_above_line_returns_not_shown():
    rows = rows_fixture()
    story = conflict_story(rows)
    story["pivots"]["highs"] = [
        {"index": 20, "at": rows[20]["at"], "price": 82_000.0},
        {"index": 105, "at": rows[105]["at"], "price": 83_000.0},
        {"index": 110, "at": rows[110]["at"], "price": 79_400.0},
    ]
    base = style_m_article_contract._build_base_facts(story, rows)
    semantic = style_m_semantics.build(story, base, rows)
    assert semantic["trendline"]["status"] == "NOT_SHOWN"
    assert semantic["trendline"]["permission"] == "FORBIDDEN"
    assert semantic["breakout"]["status"] == "NOT_EVALUATED"


def test_valid_descending_trendline_records_ordered_anchors_and_line_parameters():
    rows = rows_fixture()
    story = conflict_story(rows)
    story["pivots"]["highs"] = [
        {"index": 20, "at": rows[20]["at"], "price": 82_000.0},
        {"index": 60, "at": rows[60]["at"], "price": 80_500.0},
        {"index": 110, "at": rows[110]["at"], "price": 79_400.0},
    ]
    base = style_m_article_contract._build_base_facts(story, rows)
    semantic = style_m_semantics.build(story, base, rows)
    trendline = semantic["trendline"]
    assert trendline["status"] == "SHOWN"
    assert trendline["anchor_fact_ids"] == [
        "structure.pivot.high.20", "structure.pivot.high.110"]
    assert trendline["slope_per_bar"] < 0
    assert trendline["selection_rule"] == "descending-high-visible/v1"
    assert trendline["source_sha256"] == story["source_sha256"]


def test_real_shape_rows_without_indexes_share_canonical_breakout_index_space():
    rows = rows_fixture(499)
    for row in rows:
        row.pop("index")
    story = conflict_story(rows)
    story["pivots"] = {
        "highs": [
            {"index": 400, "at": rows[400]["at"], "price": 80_017.02},
            {"index": 450, "at": rows[450]["at"], "price": 79_517.02},
        ],
        "lows": [
            {"index": 410, "at": rows[410]["at"], "price": 77_500.0},
            {"index": 460, "at": rows[460]["at"], "price": 77_000.0},
        ],
    }
    story["source_sha256"] = projection_hash(story, rows)
    facts = style_m_article_contract.build(story, rows)
    breakout = facts["semantic_decision"]["breakout"]
    assert breakout["status"] == "NOT_CONFIRMED"
    assert breakout["evaluated_candle_fact_id"] == "market.candle.close.498"
    assert breakout["evaluated_close"] == 77_756.71
    assert breakout["line_value_at_candle"] == pytest.approx(79_037.02)


@pytest.mark.parametrize(
    ("state", "reason", "implication"),
    [
        ("NO_PLAN", "INSUFFICIENT_STRUCTURE", "WAIT_FOR_STRUCTURE"),
        ("NO_PLAN", "STALE_STRUCTURE", "WAIT_FOR_FRESH_STRUCTURE"),
        ("NO_PLAN", "STRUCTURE_CONFLICT", "WAIT_FOR_ALIGNMENT"),
        ("NO_PLAN", "INVALID_GEOMETRY", "REJECT_INVALID_GEOMETRY"),
        ("NO_PLAN", "RR_TOO_LOW", "REJECT_LOW_RR"),
        ("NO_PLAN", "TARGET_PASSED", "NO_CHASE_TARGET_PASSED"),
        ("NO_PLAN", "PRICE_EXTENDED", "NO_CHASE_PRICE_EXTENDED"),
        ("INVALIDATED", "STOP_INVALIDATED", "REBUILD_AFTER_INVALIDATION"),
    ],
)
def test_no_plan_and_invalidated_reason_mapping(state, reason, implication):
    rows = rows_fixture()
    story = conflict_story(rows)
    story.update({"state": state, "reason_code": reason})
    if state == "INVALIDATED":
        story["side"] = "BUY"
    base = style_m_article_contract._build_base_facts(story, rows)
    semantic = style_m_semantics.build(story, base, rows)
    assert semantic["decision"]["implication"] == implication


def trend_story_with_middle(middle_price: float) -> tuple[list[dict], dict]:
    rows = rows_fixture()
    story = conflict_story(rows)
    story["pivots"]["highs"] = [
        {"index": 20, "at": rows[20]["at"], "price": 82_000.0},
        {"index": 60, "at": rows[60]["at"], "price": middle_price},
        {"index": 110, "at": rows[110]["at"], "price": 79_400.0},
    ]
    return rows, story


def test_top_ranked_trendline_rejected_by_intermediate_high_then_fallback_selected():
    rows, story = trend_story_with_middle(81_500.0)
    semantic = style_m_semantics.build(
        story, style_m_article_contract._build_base_facts(story, rows), rows)
    assert semantic["trendline"]["anchor_fact_ids"] == [
        "structure.pivot.high.60", "structure.pivot.high.110"]
    assert semantic["trendline"]["intermediate_high_fact_ids_checked"] == []


def test_all_descending_candidates_rejected_returns_not_shown_with_provenance_policy():
    rows = rows_fixture()
    story = conflict_story(rows)
    story["pivots"]["highs"] = [
        {"index": 20, "at": rows[20]["at"], "price": 82_000.0},
        {"index": 105, "at": rows[105]["at"], "price": 83_000.0},
        {"index": 110, "at": rows[110]["at"], "price": 79_400.0},
    ]
    semantic = style_m_semantics.build(
        story, style_m_article_contract._build_base_facts(story, rows), rows)
    assert semantic["trendline"]["status"] == "NOT_SHOWN"
    assert semantic["trendline"]["precision_policy"] == "usd-price-2dp/v1"
    assert semantic["trendline"]["price_epsilon_usd"] == 0.01


def test_intermediate_high_exactly_at_one_cent_epsilon_keeps_top_candidate():
    slope = (79_400.0 - 82_000.0) / (110 - 20)
    line_at_60 = 82_000.0 + slope * (60 - 20)
    rows, story = trend_story_with_middle(line_at_60 + 0.01)
    semantic = style_m_semantics.build(
        story, style_m_article_contract._build_base_facts(story, rows), rows)
    assert semantic["trendline"]["anchor_fact_ids"] == [
        "structure.pivot.high.20", "structure.pivot.high.110"]


def test_intermediate_high_above_one_cent_epsilon_rejects_top_candidate():
    slope = (79_400.0 - 82_000.0) / (110 - 20)
    line_at_60 = 82_000.0 + slope * (60 - 20)
    rows, story = trend_story_with_middle(line_at_60 + 0.0101)
    semantic = style_m_semantics.build(
        story, style_m_article_contract._build_base_facts(story, rows), rows)
    assert semantic["trendline"]["anchor_fact_ids"] != [
        "structure.pivot.high.20", "structure.pivot.high.110"]


def test_intermediate_high_any_amount_above_one_cent_rejects_without_hidden_tolerance():
    slope = (79_400.0 - 82_000.0) / (110 - 20)
    line_at_60 = 82_000.0 + slope * (60 - 20)
    rows, story = trend_story_with_middle(line_at_60 + 0.0100000005)
    semantic = style_m_semantics.build(
        story, style_m_article_contract._build_base_facts(story, rows), rows)
    assert semantic["trendline"]["anchor_fact_ids"] != [
        "structure.pivot.high.20", "structure.pivot.high.110"]


def test_valid_trendline_records_precision_and_all_checked_intermediate_ids():
    rows, story = trend_story_with_middle(80_500.0)
    semantic = style_m_semantics.build(
        story, style_m_article_contract._build_base_facts(story, rows), rows)
    trend = semantic["trendline"]
    assert trend["precision_policy"] == "usd-price-2dp/v1"
    assert trend["price_epsilon_usd"] == 0.01
    assert trend["intermediate_high_fact_ids_checked"] == ["structure.pivot.high.60"]


def projection_hash(story: dict, rows: list[dict]) -> str:
    projection = {"cutoff": story["cutoff"], "source_label": story["source_label"],
                  "source_meta": story["source_meta"],
                  "rows": [{key: row[key] for key in ("at", "open", "high", "low", "close")}
                           for row in rows]}
    return hashlib.sha256(json.dumps(projection, sort_keys=True,
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


@pytest.mark.parametrize("mutation", ["duplicate_timestamp", "out_of_order_index", "after_cutoff"])
def test_canonical_rows_gate_blocks_order_and_cutoff_mutations(mutation):
    rows = rows_fixture()
    story = conflict_story(rows)
    if mutation == "duplicate_timestamp":
        rows[50]["at"] = rows[49]["at"]
    elif mutation == "out_of_order_index":
        rows[50]["index"] = rows[49]["index"] - 1
    else:
        rows[-1]["at"] = (CUTOFF + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    story["source_sha256"] = projection_hash(story, rows)
    with pytest.raises(style_m_semantics.SemanticContractError) as caught:
        style_m_article_contract.build(story, rows)
    assert caught.value.code == "SEM_ROWS_NOT_CANONICAL"


@pytest.mark.parametrize("shift_start", [50, 129])
def test_external_index_suffix_gap_is_rejected_even_when_order_remains_increasing(shift_start):
    rows = rows_fixture()
    story = conflict_story(rows)
    for row in rows[shift_start:]:
        row["index"] += 1
    # External index is deliberately excluded from source hashing, so the
    # canonicalizer itself must reject this second index authority.
    assert projection_hash(story, rows) == story["source_sha256"]
    with pytest.raises(style_m_semantics.SemanticContractError) as caught:
        style_m_article_contract.build(story, rows)
    assert caught.value.code == "SEM_ROWS_NOT_CANONICAL"


def test_source_projection_tamper_blocks_article_contract_build():
    rows = rows_fixture()
    story = conflict_story(rows)
    story["source_sha256"] = projection_hash(story, rows)
    rows[30]["close"] += 999.0
    with pytest.raises(style_m_semantics.SemanticContractError) as caught:
        style_m_article_contract.build(story, rows)
    assert caught.value.code == "SEM_SOURCE_HASH_MISMATCH"
