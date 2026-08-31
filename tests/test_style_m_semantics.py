from __future__ import annotations

import copy
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
