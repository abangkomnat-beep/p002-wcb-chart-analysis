from copy import deepcopy
import re

import pytest
from tools import chart_indicator, chart_indicator_renderer as renderer
from tests.test_chart_indicator import make_rows


@pytest.mark.parametrize("name", ["render_fibonacci", "render_trade_plan"])
def test_za_preserves_default_numeric_geometry_and_input(tmp_path, name):
    rows = make_rows()
    story = chart_indicator.build_indicators(rows, asset="xauusd")
    original = deepcopy((story, rows))
    render = getattr(renderer, name)
    before = render(story, rows, tmp_path / "default.webp")
    render(story, rows, tmp_path / "thai.webp", locale="th-TH")
    assert (tmp_path / "default.webp").read_bytes() == (tmp_path / "thai.webp").read_bytes()
    after = render(story, rows, tmp_path / "za.webp", locale="en-ZA", source_timezone="+07:00")
    assert (story, rows) == original
    assert before["bars"] == after["bars"]
    assert before["layout"]["price_viewport"] == after["layout"]["price_viewport"]
    assert after["layout"]["bbox_assertions"]["overlap_count"] == 0
    if name == "render_fibonacci":
        assert before["layout"]["fib_visibility"] == after["layout"]["fib_visibility"]
        for key, anchor in before["layout"]["anchor_records"].items():
            actual = after["layout"]["anchor_records"][key]
            assert {k: v for k, v in anchor.items() if k != "label"} == {k: v for k, v in actual.items() if k != "label"}
            assert not re.search("[\u0e00-\u0e7f]", actual["label"])
    else:
        for key in ("entry_zone_band", "current_marker_anchor", "price_line_anchors",
                    "price_line_labels", "price_axis_tick_labels", "latest_candle_x_fraction"):
            assert before["layout"][key] == after["layout"][key]
        assert not re.search("[\u0e00-\u0e7f]", after["layout"]["header_card_visible_text"][0])


def test_status_translation_retains_thresholds_and_polarity():
    assert [renderer._rsi_status(x, locale="en-ZA") for x in (49, 50, 51)] == [
        "Sellers dominate", "Buying and selling balanced", "Buyers dominate"]
    assert [renderer._macd_status(x, locale="en-ZA") for x in (-1, 0, 1)] == [
        "Short-term selling pressure", "Short-term momentum steady", "Short-term rebound"]
    assert renderer._rsi_status(49) == "ฝั่งขายครองตลาด"
    assert renderer._macd_status(-1) == "แรงขายระยะสั้น"


def test_invalid_locale_or_unverified_timezone_has_no_output(tmp_path):
    for options in ({"locale": "fr-FR"}, {"locale": "en-ZA"},
                    {"locale": "en-ZA", "source_timezone": "+02:00"}):
        with pytest.raises(ValueError):
            renderer.render_fibonacci({}, [], tmp_path / "bad.webp", **options)
        assert not (tmp_path / "bad.webp").exists()
