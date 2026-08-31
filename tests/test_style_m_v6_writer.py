from datetime import datetime, timedelta

from tools import style_m_v6_story, style_m_v6_writer


def rows_fixture(count=96):
    start = datetime(2026, 8, 27, 11, tzinfo=style_m_v6_story.BANGKOK)
    rows = []
    for index in range(count):
        price = 100 + (index % 7) * 0.15
        rows.append({"at": (start + timedelta(hours=index)).strftime("%Y-%m-%d %H:%M:%S"),
                     "open": price, "high": price + 1.2, "low": price - 1.0,
                     "close": price + 0.2})
    return rows


def test_writer_has_two_scenarios_and_no_removed_indicator():
    prepared = style_m_v6_story.build(rows_fixture(), cutoff=datetime(2026, 8, 31, 11, tzinfo=style_m_v6_story.BANGKOK), source_label="fixture")
    markdown = style_m_v6_writer.compose(prepared)
    assert "Donchian" in markdown
    assert "ADX14" in markdown
    assert "แผน Long" in markdown and "แผน Short" in markdown
    assert "EMA" not in markdown
    assert "WAIT_TRIGGER" not in markdown
