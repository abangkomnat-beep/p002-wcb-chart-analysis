import pytest

from tools.locale_loader import LanguagePackError, _build_avoid_index


def test_compact_phrase_is_context_warning_and_preserves_negation():
    rules = _build_avoid_index({"locale": "ru-RU", "phrases": ["гарантированная прибыль"],
                               "note": "Review in context."})
    assert len(rules) == 1
    assert rules[0]["severity"] == "warning"
    assert rules[0]["reason"] == "Review in context."
    assert rules[0]["phrase"] not in "не гарантирует отскок цены"


def test_invalid_phrase_structure_fails_closed():
    with pytest.raises(LanguagePackError):
        _build_avoid_index({"locale": "ru-RU", "phrases": [42]})
