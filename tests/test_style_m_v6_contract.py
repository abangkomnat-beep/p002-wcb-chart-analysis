from datetime import datetime, timedelta

from tools import style_m_v6_contract, style_m_v6_story, style_m_v6_writer


def rows_fixture(count=96):
    start = datetime(2026, 8, 27, 11, tzinfo=style_m_v6_story.BANGKOK)
    return [{"at": (start + timedelta(hours=i)).strftime("%Y-%m-%d %H:%M:%S"),
             "open": 100 + (i % 7) * .15, "high": 101.2 + (i % 7) * .15,
             "low": 99 + (i % 7) * .15, "close": 100.2 + (i % 7) * .15}
            for i in range(count)]


def test_v6_facts_bind_both_plans_and_parity():
    rows = rows_fixture()
    prepared = style_m_v6_story.build(rows, cutoff=datetime(2026, 8, 31, 11, tzinfo=style_m_v6_story.BANGKOK), source_label="fixture")
    facts = style_m_v6_contract.build(prepared["story"], prepared["rows"])
    article = style_m_v6_writer.compose(prepared)
    style_m_v6_contract.validate(facts, story=prepared["story"])
    assert style_m_v6_contract.parity_report(facts, markdown=article)["status"] == "PASS"
