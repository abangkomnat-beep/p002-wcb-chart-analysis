from tools import public_number_policy


def test_rounds_technical_copy_and_preserves_urls_and_frontmatter():
    article = """---
title: BTC 3.2% source title
---

## ภาพรวม

ราคาปิด 79,446.50 ดอลลาร์ RSI 52.4 และผลตอบแทน 1.5R
[อ้างอิง](https://example.com/v1.2/item)
"""
    rendered = public_number_policy.publicize(article)
    assert "title: BTC 3.2% source title" in rendered
    assert "79,447 ดอลลาร์" in rendered
    assert "RSI 52" in rendered
    assert "3 ต่อ 2" in rendered
    assert "https://example.com/v1.2/item" in rendered
    assert not public_number_policy.validate(rendered)


def test_preserves_decimal_values_in_news_section_only():
    article = """## ข่าวสำคัญและปฏิทิน

ตัวเลข CPI จริง 3.2% คาด 2.9%

## แผนเทรด

ADX 24.6 และราคา 78,000.50
"""
    rendered = public_number_policy.publicize(article)
    assert "จริง 3.2% คาด 2.9%" in rendered
    assert "ADX 25 และราคา 78,001" in rendered


def test_explicit_news_line_is_preserved_without_opening_a_section():
    article = """ราคาปิด 10.5
**ข่าวที่ต้องติดตาม:** GDP 3.2% เวลา 20:30
ATR 2.4
"""
    rendered = public_number_policy.publicize(article)
    assert rendered.splitlines() == [
        "ราคาปิด 11",
        "**ข่าวที่ต้องติดตาม:** GDP 3.2% เวลา 20:30",
        "ATR 2",
    ]


def test_technical_heading_is_body_copy_but_news_heading_is_source_copy():
    article = """# ราคา 79,446.50
## ข่าว CPI 3.2%
ผลจริง 3.2%
## แผนที่ 78,000.50
ราคา 78,000.50
"""
    rendered = public_number_policy.publicize(article)
    assert "# ราคา 79,447" in rendered
    assert "## ข่าว CPI 3.2%" in rendered
    assert "ผลจริง 3.2%" in rendered
    assert "## แผนที่ 78,001" in rendered
    assert "ราคา 78,001" in rendered
