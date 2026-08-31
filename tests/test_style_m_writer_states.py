from __future__ import annotations

import pytest

from tools import style_m_article_contract, style_m_writer
from test_style_m_semantics import conflict_story, rows_fixture


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

