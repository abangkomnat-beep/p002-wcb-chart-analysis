"""English display must preserve numeric labels and isolate locale context."""
import pytest
from tools import za_d_display as display


def test_default_thai_unchanged():
    original = "ราคาปัจจุบัน 4,430.06 · 4 ก.ย. 2026"
    assert display.label(original) == original


def test_english_numeric_and_date_preserved():
    @display.localized_render
    def labels():
        return display.label("ราคาปัจจุบัน 4,430.06 · 4 ก.ย. 2026")
    assert labels(locale="en-ZA") == "Current price 4,430.06 · 4 Sep 2026"
    assert labels() == "ราคาปัจจุบัน 4,430.06 · 4 ก.ย. 2026"


def test_unknown_label_fails_and_context_restores():
    @display.localized_render
    def labels():
        return display.label("ข้อความใหม่")
    with pytest.raises(ValueError, match="Unmapped"):
        labels(locale="en-ZA")
    assert labels() == "ข้อความใหม่"
    with pytest.raises(ValueError, match="supports"):
        labels(locale="fr-FR")


def test_calendar_uses_only_authentic_english_title():
    event = {"title": "เหตุการณ์", "title_en": "Crude Oil Inventories"}
    @display.localized_render
    def title(value):
        return display.calendar_title(value)
    assert title(event) == "เหตุการณ์"
    assert title(event, locale="en-ZA") == "Crude Oil Inventories"
    with pytest.raises(ValueError, match="missing"):
        title({"title": "เหตุการณ์"}, locale="en-ZA")
    assert event == {"title": "เหตุการณ์", "title_en": "Crude Oil Inventories"}
