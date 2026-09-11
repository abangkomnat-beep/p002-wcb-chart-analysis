"""Offline English presentation tests; no market feed or production output."""
import copy
import re
from datetime import datetime, timezone

import pytest
from tools import forex_daily_plan as fx
from tools import forex_daily_calendar_renderer as cal


@pytest.mark.parametrize("direction", [None, "up", "down"])
def test_translation_changes_only_contract_display_text(direction):
    plan = fx.scenario("NO_SETUP" if direction is None else "WAIT", direction, direction,
                       {"close": 1.35, "pdh": 1.36, "pdl": 1.34, "atr14": 0.001},
                       {"I": {"donchian": {"lower": 1.34, "upper": 1.36}}},
                       asset="gbpusd", cutoff=datetime(2026, 9, 7, tzinfo=timezone.utc),
                       evidence_hash="a" * 64, current_close=1.35)
    original = copy.deepcopy(plan)
    thai = fx.resolve_m15_visual_contract("gbpusd", plan, direction)
    assert thai == fx.resolve_m15_visual_contract("gbpusd", plan, direction, locale="th-TH")
    english = fx.resolve_m15_visual_contract("gbpusd", plan, direction, locale="en-ZA")
    assert plan == original
    assert not re.search(r"[\u0e00-\u0e7f]", str(english))
    thai.pop("header_accessory_text")
    english.pop("header_accessory_text")
    for a, b in zip(thai["specs"], english["specs"]):
        a.pop("text")
        b.pop("text")
    assert thai == english


def test_tick_keeps_timestamp_and_default_thai():
    raw = "2026-09-07 09:30:00"
    assert fx.thai_tick(raw) == "7 ก.ย. 09:30"
    assert fx.thai_tick(raw, locale="en-ZA") == "7 Sep 09:30"
    with pytest.raises(ValueError):
        fx.thai_tick(raw, locale="unsupported")


@pytest.mark.parametrize("locale", ["en-NG", "en-SG"])
def test_style_l_country_english_locales_share_verified_render_path(locale):
    plan = fx.scenario("NO_SETUP", None, None,
                       {"close": 1.35, "pdh": 1.36, "pdl": 1.34, "atr14": 0.001},
                       {"I": {"donchian": {"lower": 1.34, "upper": 1.36}}},
                       asset="gbpusd", cutoff=datetime(2026, 9, 7, tzinfo=timezone.utc),
                       evidence_hash="a" * 64, current_close=1.35)
    assert fx.render_locale(locale) == "en-ZA"
    assert fx.resolve_m15_visual_contract("gbpusd", plan, None, locale=locale) == \
        fx.resolve_m15_visual_contract("gbpusd", plan, None, locale="en-ZA")
    assert fx.thai_tick("2026-09-07 09:30:00", locale=locale) == "7 Sep 09:30"


@pytest.mark.parametrize("locale", ["ar-001", "fr-FR"])
def test_style_l_rejects_draft_or_unsupported_render_routes(locale):
    with pytest.raises(ValueError, match="unsupported chart locale"):
        fx.render_locale(locale)


def test_calendar_english_preserves_cutoff_values_and_dimensions(tmp_path):
    event = {"title": "ผลผลิตภาคอุตสาหกรรม (รายเดือน)", "title_en": "Industrial Production MoM",
             "at": "2026-09-07 13:00", "country": "EUR", "impact": "Medium",
             "forecast": "0.3%", "previous": "0.2%", "actual": None}
    before = copy.deepcopy(event)
    cutoff = datetime.fromisoformat("2026-09-07T09:55:40+07:00")
    args = dict(asset="eurusd", symbol="EUR/USD", article_date="2026-09-07", events=[event],
                output_path=tmp_path / "calendar.webp", page_number=1, page_count=1, cutoff=cutoff)
    result = cal.render_page(**args, locale="en-ZA")
    assert result["canvas"] == [1920, 560]
    assert result["display_rows"] == [["7 Sep 2026 · 13:00", "EUR", "Medium",
                                         "Industrial Production MoM", "Awaiting release", "Forecast 0.3% · Previous 0.2%"]]
    assert "UTC+07:00" in result["columns"][0]
    assert not re.search(r"[\u0e00-\u0e7f]", str(result["display_rows"]))
    assert event == before
    assert cal.event_status(event, cutoff) == "รอประกาศ"
    assert cal.important_numbers(event) == "คาด 0.3% · ก่อนหน้า 0.2%"
    with pytest.raises(ValueError, match="English event title"):
        cal._wrapped_title({"title": "ภาษาไทย"}, locale="en-ZA")


@pytest.mark.parametrize("locale", ["en-NG", "en-SG"])
def test_calendar_country_english_locales_share_english_labels(tmp_path, locale):
    event = {"title": "ผลผลิตภาคอุตสาหกรรม (รายเดือน)", "title_en": "Industrial Production MoM",
             "at": "2026-09-07 13:00", "country": "EUR", "impact": "Medium",
             "forecast": "0.3%", "previous": "0.2%", "actual": None}
    result = cal.render_page(asset="eurusd", symbol="EUR/USD", article_date="2026-09-07", events=[event],
                             output_path=tmp_path / f"{locale}.webp", page_number=1, page_count=1,
                             cutoff=datetime.fromisoformat("2026-09-07T09:55:40+07:00"), locale=locale)
    assert result["display_rows"][0][2] == "Medium"
