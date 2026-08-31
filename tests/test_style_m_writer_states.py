from __future__ import annotations

import pytest

from tools import style_m_article_contract, style_m_writer
from test_style_m_semantics import conflict_story, projection_hash, rows_fixture


def state_story(state: str, side: str) -> dict:
    rows = rows_fixture()
    story = conflict_story(rows)
    story.update({"state": state, "side": side, "reason_code": (
        "STOP_INVALIDATED" if state == "INVALIDATED" else "PLAN_VALID")})
    if state == "INVALIDATED":
        story.update({"plan": None, "show_plan_geometry": False})
        return story
    if side == "BUY":
        plan = {"entry_low": 92.0, "entry_high": 93.0, "sl": 90.0,
                "tp1": 100.0, "tp2": 108.0, "rr1": 2.0, "rr2": 4.0,
                "dynamic_entry_limit": 94.0}
    else:
        plan = {"entry_low": 107.0, "entry_high": 108.0, "sl": 110.0,
                "tp1": 100.0, "tp2": 92.0, "rr1": 2.0, "rr2": 4.0,
                "dynamic_entry_limit": 106.0}
    plan.update({"min_rr1": 1.5, "min_rr2": 2.0, "entry_zone_atr": 0.25,
                 "stop_buffer_atr": 0.75, "worst_entry_risk_atr": 1.0})
    story.update({"plan": plan, "show_plan_geometry": True})
    return story


def test_f03_structure_conflict_explains_supporting_and_contradicting_fact_families():
    rows = rows_fixture()
    story = conflict_story(rows)
    facts = style_m_article_contract.build(story, rows)
    composed = style_m_writer.compose(story, [], facts)
    markdown = composed["markdown"]
    assert "78,966.76" in markdown and "79,400.00" in markdown
    assert "77,962.49" in markdown and "77,000.00" in markdown
    assert "สูงขึ้น" in markdown and "ต่ำลง" in markdown
    assert "รอบนี้ยังไม่มีแผนเข้าเทรด" in markdown
    assert "ไม่ใช่สัญญาณเข้าอัตโนมัติ" in markdown
    assert "ดอลลาร์." not in markdown
    assert [line[3:] for line in markdown.splitlines() if line.startswith("## ")] == list(style_m_writer.H2)
    assert markdown.count("btcusd-style-m-h1-") == 1
    assert composed["claim_report"]["schema"] == "style-m-writer-claim-report/v1"


@pytest.mark.parametrize(
    ("reason", "phrase"),
    [
        ("INSUFFICIENT_STRUCTURE", "หลักฐานโครงสร้างหรือ ATR ยังไม่พอ"),
        ("STALE_STRUCTURE", "เก่าเกินเกณฑ์ 72 ชั่วโมง"),
        ("INVALID_GEOMETRY", "ลำดับระดับของแผนยังไม่ผ่านเกณฑ์"),
        ("RR_TOO_LOW", "RR ขั้นต่ำ"),
        ("TARGET_PASSED", "ไม่ไล่ราคา"),
        ("PRICE_EXTENDED", "ห่างจากบริเวณแผนเกิน 1 ATR"),
    ],
)
def test_reason_specific_no_plan_copy_has_no_generic_fallback(reason, phrase):
    rows = rows_fixture()
    story = conflict_story(rows)
    story["reason_code"] = reason
    facts = style_m_article_contract.build(story, rows)
    markdown = style_m_writer.compose(story, [], facts)["markdown"]
    assert phrase in markdown
    for label in ("**Entry:**", "**Stop Loss:**", "**TP1 / TP2:**", "**RR โดยประมาณ:**"):
        assert label not in markdown


@pytest.mark.parametrize("state", ["WAIT_H1_CONFIRM", "PLAN_VALID"])
@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_f09_f12_active_state_side_matrix_has_permission_and_copy(state, side):
    rows = rows_fixture()
    story = state_story(state, side)
    facts = style_m_article_contract.build(story, rows)
    composed = style_m_writer.compose(story, [], facts)
    markdown = composed["markdown"]
    permission = "CONDITIONAL" if state == "WAIT_H1_CONFIRM" else "ALLOWED"
    assert facts["facts"]["plan.side"]["permission"] == permission
    assert facts["claims"]["claim.plan.side"]["permission"] == permission
    assert facts["semantic_decision"]["decision"]["implication"] == (
        "WAIT_FOR_H1_CONFIRMATION" if state == "WAIT_H1_CONFIRM" else "WAIT_FOR_RETEST")
    assert ("ฝั่งซื้อ" if side == "BUY" else "ฝั่งขาย") in markdown
    assert "**Entry:**" in markdown and "**Stop Loss:**" in markdown
    assert "ยังไม่ใช่ออเดอร์ที่เปิดแล้ว" in markdown
    assert "ไม่ไล่ราคา" in markdown
    assert "ไม่รับประกันการจับคู่จริง" in markdown


@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_f13_f14_invalidated_side_is_diagnostic_only_and_has_no_geometry(side):
    rows = rows_fixture()
    story = state_story("INVALIDATED", side)
    facts = style_m_article_contract.build(story, rows)
    markdown = style_m_writer.compose(story, [], facts)["markdown"]
    assert facts["facts"]["plan.side"]["permission"] == "FORBIDDEN"
    assert "claim.plan.side" not in facts["claims"]
    assert facts["semantic_decision"]["decision"]["implication"] == "REBUILD_AFTER_INVALIDATION"
    for label in ("**Entry:**", "**Stop Loss:**", "**TP1 / TP2:**", "**RR โดยประมาณ:**"):
        assert label not in markdown
    assert "แผนเดิมถูกยกเลิก" in markdown
    assert "ไม่ใช่สัญญาณเข้าอัตโนมัติ" in markdown


def test_v5_compose_does_not_call_legacy_body(monkeypatch):
    rows = rows_fixture()
    story = conflict_story(rows)
    facts = style_m_article_contract.build(story, rows)
    monkeypatch.setattr(style_m_writer, "_render_legacy",
                        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("legacy body")))
    assert style_m_writer.compose(story, [], facts)["markdown"]


def test_plan_valid_copy_has_confirmed_then_retest_without_future_trigger_contradiction():
    rows = rows_fixture()
    story = state_story("PLAN_VALID", "BUY")
    facts = style_m_article_contract.build(story, rows)
    markdown = style_m_writer.compose(story, [], facts)["markdown"]
    assert "ปิดผ่านเงื่อนไข" in markdown
    assert "รอราคากลับมาทดสอบ" in markdown
    assert "จะมีน้ำหนักเมื่อ" not in markdown


def test_structure_conflict_copy_uses_actual_contracting_enums_not_hardcoded_hh_ll():
    rows = rows_fixture()
    story = conflict_story(rows)
    story["pivots"]["highs"][-2]["price"] = 80_000.0
    story["pivots"]["highs"][-1]["price"] = 79_400.0
    story["pivots"]["lows"][-2]["price"] = 77_000.0
    story["pivots"]["lows"][-1]["price"] = 77_500.0
    story["indicators"].update({"ema20": 78_300.0, "ema50": 78_200.0})
    story["latest"]["close"] = 78_250.0
    rows[-1]["close"] = 78_250.0
    story["source_sha256"] = projection_hash(story, rows)
    facts = style_m_article_contract.build(story, rows)
    markdown = style_m_writer.compose(story, [], facts)["markdown"]
    assert "จุดสูงลดลง" in markdown
    assert "จุดต่ำสูงขึ้น" in markdown
    assert "ราคาปิดอยู่ระหว่าง EMA20 และ EMA50" in markdown
    assert "EMA20 อยู่เหนือ EMA50" in markdown


def test_no_plan_lead_is_at_most_two_sentences_and_states_reason():
    rows = rows_fixture()
    story = conflict_story(rows)
    facts = style_m_article_contract.build(story, rows)
    markdown = style_m_writer.compose(story, [], facts)["markdown"]
    body = markdown.split("---", 2)[-1]
    lead = next(line for line in body.splitlines() if line.startswith("&emsp;"))
    assert "ยังไม่มีแผนเข้าเทรด" in lead
    assert "โครงสร้าง" in lead
    assert sum(lead.count(mark) for mark in (".", "?", "!")) <= 2
