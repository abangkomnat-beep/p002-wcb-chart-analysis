from datetime import datetime, timedelta

from PIL import Image

from tools import style_m_v6_renderer, style_m_v6_story, visual_theme


def rows_fixture(count=96):
    start = datetime(2026, 8, 27, 11, tzinfo=style_m_v6_story.BANGKOK)
    rows = []
    for index in range(count):
        price = 100 + (index % 7) * 0.15
        rows.append({"at": (start + timedelta(hours=index)).strftime("%Y-%m-%d %H:%M:%S"),
                     "open": price, "high": price + 1.2, "low": price - 1.0,
                     "close": price + 0.2})
    return rows


def test_render_is_1920x1080(tmp_path):
    prepared = style_m_v6_story.build(rows_fixture(), cutoff=datetime(2026, 8, 31, 11, tzinfo=style_m_v6_story.BANGKOK), source_label="fixture")
    target = tmp_path / "btc.webp"
    result = style_m_v6_renderer.render(prepared["story"], prepared["rows"], target)
    assert result["width"] == 1920 and result["height"] == 1080
    assert result["theme"] == {"schema": visual_theme.SCHEMA,
                                "version": visual_theme.VERSION}
    with Image.open(target) as image:
        assert image.size == (1920, 1080)
        assert image.format == "WEBP"


def test_m7_plan_cards_axes_and_zones_match_story_without_overlap(tmp_path):
    prepared = style_m_v6_story.build(
        rows_fixture(),
        cutoff=datetime(2026, 8, 31, 11, tzinfo=style_m_v6_story.BANGKOK),
        source_label="fixture")
    story = prepared["story"]
    result = style_m_v6_renderer.render(
        story, prepared["rows"], tmp_path / "btc-m7.webp")
    assert result["label_overlap_count"] == 0
    assert len(result["plan_cards"]) == 2
    actual = {item["side"]: item for item in result["plan_cards"]}
    for plan in story["scenarios"].values():
        for field in ("trigger", "entry_low", "entry_high", "sl", "tp1", "tp2"):
            assert actual[plan["side"]][field] == plan[field]
        expected_entry = (plan["entry_high"] if plan["side"] == "LONG"
                          else plan["entry_low"])
        assert actual[plan["side"]]["display_entry"] == expected_entry
    assert result["reference_labels"] == {
        "buy_side": story["zones"]["buy_side_liquidity_reference"],
        "sell_side": story["zones"]["sell_side_liquidity_reference"],
    }
    assert result["trap_zone"] == {
        "low": story["zones"]["trap_zone_low"],
        "high": story["zones"]["trap_zone_high"],
    }
    assert {(item["side"], item["low"], item["high"])
            for item in result["entry_zones"]} == {
        (plan["side"], plan["entry_low"], plan["entry_high"])
        for plan in story["scenarios"].values()
    }
    assert result["layout"]["adx_panel"] is None
    assert result["layout"]["plan_label_rail"] is None
    assert result["layout"]["plot"] == [80, 170, 1760, 830]
    assert result["layout"]["header_visible_text"] == ["BTCUSD · H1"]
    assert result["layout"]["internal_state_visible_count"] == 0
    assert result["header"]["x0_px"] == 0
    assert result["header"]["x1_px"] == 1920
    assert result["header"]["top_gap_px"] == 0
    assert result["header"]["underline_height_px"] == 5
    assert result["watermark_count"] == 1
    assert result["watermark"]["text"] == "WorldClassBroker"
    assert result["watermark"]["color"] == "#F4F1E7"
    assert result["watermark"]["alpha"] == 0.08
    assert 0.30 <= result["watermark"]["bbox_width_ratio"] <= 0.35
    assert result["layout"]["visible_bars"] == 48
    legend_boxes = result["layout"]["legend_boxes"]
    assert all(box[1] == 120 and box[3] == 152 for box in legend_boxes)
    assert legend_boxes[-1][2] == result["layout"]["plot"][2]
    assert len(result["price_axis"]) == 7
    assert len(result["time_axis"]) == 6
    assert [item["price"] for item in result["price_axis"]] == sorted(
        item["price"] for item in result["price_axis"])
    assert [item["x"] for item in result["time_axis"]] == sorted(
        item["x"] for item in result["time_axis"])
    first_x, last_x = result["layout"]["candle_x_range"]
    assert first_x > result["layout"]["plot"][0]
    assert result["layout"]["plot"][2] - last_x >= 70
