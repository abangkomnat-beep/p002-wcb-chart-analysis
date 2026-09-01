from datetime import datetime, timedelta
import re

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


def test_writer_has_m7_two_sided_table_and_no_removed_indicator():
    prepared = style_m_v6_story.build(rows_fixture(), cutoff=datetime(2026, 8, 31, 11, tzinfo=style_m_v6_story.BANGKOK), source_label="fixture")
    markdown = style_m_v6_writer.compose(prepared)
    assert "Donchian" in markdown
    assert "ADX (14)" in markdown
    assert "แผน Long" in markdown and "แผน Short" in markdown
    assert "EMA" not in markdown
    assert "WAIT_TRIGGER" not in markdown
    assert "Liquidity Pools & Trap Zones" in markdown
    assert "False Breakout" in markdown
    assert "RR โดยประมาณ (TP1 / TP2)" not in markdown
    assert "วอลลุ่ม" not in markdown and "Order Book" not in markdown
    assert "[กราฟ BTCUSD แบบเรียลไทม์](/thailand/asset-btc)" in markdown
    assert "[บทวิเคราะห์เทคนิคทั้งหมด](/thailand/analysis)" in markdown


def test_public_technical_copy_has_no_decimals_but_news_keeps_source_value():
    prepared = style_m_v6_story.build(
        rows_fixture(),
        cutoff=datetime(2026, 8, 31, 11, tzinfo=style_m_v6_story.BANGKOK),
        source_label="fixture")
    events = [{"title": "เงินเฟ้ออยู่ที่ 3.2%", "time_thai": "19:30 น.",
               "source": "Official", "url": "https://example.test/news"}]
    markdown = style_m_v6_writer.compose(prepared, events=events)
    assert "3.2%" in markdown
    technical = "\n".join(line for line in markdown.splitlines()
                            if not line.startswith("**ข่าวที่ต้องติดตาม:**"))
    assert not re.search(r"(?<![A-Za-z0-9])\d[\d,]*\.\d+", technical)
    assert "RR ยังไม่หัก spread/slippage" in markdown
