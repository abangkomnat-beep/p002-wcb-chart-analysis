from tools.translation_adapter import _literal_count


def test_numeric_literal_allows_sentence_punctuation():
    assert _literal_count("Updated on 2026, this update.", "2026") == 1
    assert _literal_count("Updated in 2026.", "2026") == 1


def test_numeric_literal_rejects_decimal_or_grouped_substrings():
    assert _literal_count("Value 2026.5", "2026") == 0
    assert _literal_count("Value 1,2026", "2026") == 0
    assert _literal_count("Value 79,519.5", "79,519") == 0


def test_numeric_literal_exact_grouping_is_preserved():
    assert _literal_count("SELL 4,366–4,370", "4,366–4,370") == 1
