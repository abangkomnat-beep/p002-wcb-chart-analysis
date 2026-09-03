"""Targeted contract tests for the shared D/E/L visual system."""

import json
import math
from pathlib import Path

import pytest

from tools import chart_indicator, chart_indicator_renderer, visual_theme


def test_theme_schema_version_palette_and_contrast():
    config = json.loads((Path(__file__).parents[1] / "config" / "visual_theme.json").read_text(encoding="utf-8"))
    assert config["schema"] == visual_theme.SCHEMA
    assert config["version"] == visual_theme.VERSION
    assert config["brand"] == {
        "deep_green": "#0E2A1D", "header_green": "#123E2B", "gold": "#C9A227"
    }
    colors = visual_theme.for_chart()
    assert colors["bg"] == "#ffffff"
    assert colors["buy"] != colors["sell"]
    assert colors["sl"] != colors["tp"]
    for key in ("text", "muted", "axis", "buy", "sell", "sl", "tp", "warning", "info", "neutral", "indicator"):
        assert visual_theme.contrast_ratio(colors[key], colors["bg"]) >= 4.5


def test_theme_keeps_plot_alias_for_real_style_l_h4_inset():
    colors = visual_theme.for_chart()
    assert colors["plot"] == colors["bg"] == visual_theme.SURFACE["plot"]


def test_premium_chart_is_opt_in_editorial_card_and_central_callout_is_aaa():
    light = visual_theme.for_chart()
    premium = visual_theme.for_premium_chart()
    assert light["bg"] == "#ffffff"
    assert premium["bg"] == "#FFFFFF"
    assert premium["canvas"] == "#F4F1E7"
    assert premium["header_start"] == "#071A11"
    assert visual_theme.contrast_ratio(premium["ivory"], premium["callout"]) >= 7.0
    for key in ("text", "muted", "axis", "buy", "sell", "sl", "tp",
                "warning", "info", "neutral", "indicator"):
        assert visual_theme.contrast_ratio(premium[key], premium["bg"]) >= 4.5


def test_premium_overlap_report_measures_text_patches_not_annotation_arrows():
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(6, 4), dpi=120)
    try:
        leader = axis.annotate(
            "Leader label", xy=(.82, .18), xycoords="axes fraction",
            xytext=(.12, .82), textcoords="axes fraction",
            bbox={"boxstyle": "round,pad=.3", "facecolor": "white"},
            arrowprops={"arrowstyle": "->"})
        leader.set_gid("premium-label:test:leader")
        target = axis.text(
            .72, .12, "Target", transform=axis.transAxes,
            bbox={"boxstyle": "round,pad=.3", "facecolor": "white"})
        target.set_gid("premium-label:test:target")

        report = visual_theme.premium_text_patch_overlap_report(
            figure, gap_pixels=12.0)

        assert report["overlap_count"] == 0
        assert report["clipping_count"] == 0
        assert {box["role"] for box in report["boxes"]} == {
            "premium-label:test:leader", "premium-label:test:target"}
    finally:
        plt.close(figure)


def test_header_accessory_card_uses_exact_palette_and_masks_approved_cream():
    import matplotlib.pyplot as plt

    colors = visual_theme.for_premium_chart()
    figure = plt.figure(figsize=(19.2, 11.4), dpi=100,
                        facecolor=colors["canvas"])
    plot = figure.add_axes([.06, .06, .86, .82])
    header = figure.add_axes([.06, .87, .86, .10])
    try:
        title, _face, underline = visual_theme.draw_edge_to_edge_header(
            figure, header, plot, "XAU/USD · D1", colors)
        artist, layout = visual_theme.draw_header_accessory_card(
            figure, header, title, underline, "STATUS CARD", colors,
            role="contract", font_size=22.0)
        raster = visual_theme.premium_header_raster_report(
            figure, header, underline)

        assert artist.get_gid() == "premium-label:header-card:contract"
        assert layout["face"] == "#F4F1E7"
        assert layout["text_color"] == "#0E2A1D"
        assert layout["edge"] == "#D6B34A"
        assert 1.0 <= layout["border_width_px"] <= 1.5
        assert layout["contrast"] >= 7
        assert layout["line_count"] == 1
        assert layout["right_safe_margin_px_at_768"] >= 8
        assert layout["title_gap_px_at_768"] >= 8
        assert layout["font_height_px_at_768"] >= 12
        assert layout["contained_in_header"]
        assert not layout["overlaps_title"]
        assert not layout["overlaps_underline"]
        assert not layout["clipped"]
        assert not layout["leader"]
        assert not layout["connector"]
        assert not layout["accent_to_plot"]
        assert raster["approved_header_card_count"] == 1
        assert raster["header_background_cream_like_pixels"] == 0
        assert raster["top_row_green_coverage"] == 1.0
    finally:
        plt.close(figure)


def test_matplotlib_watermark_contract_is_single_centered_and_unboxed():
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(12, 6), dpi=100)
    try:
        layout = visual_theme.draw_matplotlib_watermark(
            figure, axis, surface="chart")
        artist = next(item for item in axis.texts
                      if item.get_gid() == "premium-decoration:watermark")

        assert layout["text"] == "WorldClassBroker"
        assert layout["count"] == 1
        assert layout["color"] == "#F4F1E7"
        assert layout["alpha"] == pytest.approx(0.08)
        assert layout["rotation"] == 0
        assert layout["box"] is False
        assert layout["shadow"] is False
        assert layout["path_effect"] is False
        assert layout["font_weight"] == "medium"
        assert layout["tracking_px"] >= 1.0
        assert layout["tracking_target_px"] == pytest.approx(2.0)
        assert layout["glyph_count"] == len("WorldClassBroker")
        assert 0.30 <= layout["bbox_width_ratio"] <= 0.35
        assert 0.49 <= layout["center_x_ratio"] <= 0.51
        assert 0.42 <= layout["center_y_ratio"] <= 0.58
        assert artist.get_bbox_patch() is None
        assert artist.get_path_effects() == []
        assert artist.get_visible() is False
        glyphs = [item for item in axis.texts
                  if str(item.get_gid() or "").startswith(
                      "premium-decoration:watermark-glyph:")]
        assert len(glyphs) == len("WorldClassBroker")
        assert all(item.get_visible() for item in glyphs)
    finally:
        plt.close(figure)


def test_matplotlib_surface_aware_watermark_uses_restrained_green_on_light_plot():
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(12, 6), dpi=100)
    axis.set_facecolor("#FFFFFF")
    try:
        layout = visual_theme.draw_matplotlib_watermark(
            figure, axis, surface="chart", surface_aware=True)
        contrast = layout["surface_contrast"]
        assert layout["color"] == "#0E2A1D"
        assert layout["alpha"] == pytest.approx(0.12)
        assert layout["palette_role"] == "light_plot"
        assert contrast["mode"] == "surface-aware"
        assert contrast["light_plot_detected"] is True
        assert contrast["visibility_pass"] is True
        assert contrast["effective_contrast_ratio"] >= 1.20
        assert layout["tracking_px"] >= 1.0
    finally:
        plt.close(figure)

    figure, axis = plt.subplots(figsize=(12, 6), dpi=100)
    axis.set_facecolor("#071A11")
    try:
        unchanged = visual_theme.draw_matplotlib_watermark(
            figure, axis, surface="chart", surface_aware=True)
        assert unchanged["color"] == "#F4F1E7"
        assert unchanged["alpha"] == pytest.approx(0.08)
        assert unchanged["palette_role"] == "chart"
        assert unchanged["surface_contrast"]["light_plot_detected"] is False
    finally:
        plt.close(figure)


def test_pil_header_and_calendar_watermark_contracts_are_deterministic():
    from PIL import Image, ImageFont

    image = Image.new("RGB", (1200, 675), "#FFFFFF")
    font_factory = lambda size: ImageFont.truetype("arial.ttf", size)  # noqa: E731
    header = visual_theme.draw_pil_edge_to_edge_header(
        image, "BTCUSD · H1", plot_left=80, font_factory=font_factory)
    watermark = visual_theme.draw_pil_watermark(
        image, surface="calendar", font_factory=font_factory)

    assert header["title"] == "BTCUSD · H1"
    assert header["x0_px"] == 0 and header["x1_px"] == 1200
    assert header["top_gap_px"] == 0
    assert 3 <= header["underline_height_px"] <= 6
    assert header["title_x_px"] == 80
    assert watermark["text"] == "WorldClassBroker"
    assert watermark["count"] == 1
    assert watermark["color"] == "#0E2A1D"
    assert watermark["alpha"] == pytest.approx(0.05)
    assert 0.30 <= watermark["bbox_width_ratio"] <= 0.35
    assert 0.49 <= watermark["center_x_ratio"] <= 0.51
    assert 0.42 <= watermark["center_y_ratio"] <= 0.58


def test_pil_surface_aware_watermark_uses_restrained_green_on_light_plot():
    from PIL import Image, ImageFont

    image = Image.new("RGB", (1920, 1080), "#FFFFFF")
    font_factory = lambda size: ImageFont.truetype("arial.ttf", size)  # noqa: E731
    watermark = visual_theme.draw_pil_watermark(
        image, surface="chart", font_factory=font_factory,
        surface_aware=True)
    contrast = watermark["surface_contrast"]
    assert watermark["text"] == "WorldClassBroker"
    assert watermark["count"] == 1
    assert watermark["color"] == "#0E2A1D"
    assert watermark["alpha"] == pytest.approx(0.12)
    assert watermark["palette_role"] == "light_plot"
    assert contrast["mode"] == "surface-aware"
    assert contrast["background_color"] == "#FFFFFF"
    assert contrast["light_plot_detected"] is True
    assert contrast["effective_contrast_ratio"] >= 1.20
    assert contrast["visibility_pass"] is True
    assert watermark["box"] is False
    assert watermark["shadow"] is False
    assert watermark["rotation"] == 0


@pytest.mark.parametrize("fixture", ["bullish", "bearish", "sideways", "near_entry"])
def test_e_renderer_declares_header_and_price_line_bbox_contract(tmp_path, fixture):
    rows = []
    price = 300.0
    step = {"bullish": 0.3, "bearish": -0.3, "sideways": 0.0, "near_entry": -0.3}[fixture]
    for index in range(420):
        close = price + index * step + 6.0 * math.sin(index / 6)
        rows.append({"date": f"2025-01-{(index % 28) + 1:02d}", "open": close - .4,
                     "high": close + 1.2, "low": close - 1.2, "close": close})
    story = chart_indicator.build_indicators(rows, asset="xauusd")
    if fixture == "near_entry":
        primary = story["scenarios"]["primary"]
        story["current"]["close"] = (primary["entry_low"] + primary["entry_high"]) / 2
    result = chart_indicator_renderer.render_trade_plan(story, rows, tmp_path / "e-near-entry.webp")
    metadata = result["metadata"]
    assert metadata["schema"] == "style-e-trade-plan-renderer-v1"
    assert metadata["theme"]["schema"] == visual_theme.SCHEMA
    assert metadata["layout"]["summary_strip"] == "header_accessory_card"
    assert metadata["layout"]["header_accessory_card"] is not None
    assert metadata["layout"]["old_floating_summary_count"] == 0
    assert metadata["layout"]["header_visible_text"] == ["XAU/USD · H1"]
    assert metadata["layout"]["watermark_count"] == 1
    assert metadata["layout"]["watermark"]["text"] == "WorldClassBroker"
    assert metadata["layout"]["annotation_rail"] == "price_line_end_labels"
    assert metadata["layout"]["leader_lines"] is False
    assert "side_table" not in metadata["layout"]
    assert "side_table_count" not in metadata["layout"]
    assert metadata["layout"]["bbox_assertions"]["checked"] is True
    assert metadata["layout"]["bbox_assertions"]["overlap_count"] == 0
    roles = {box["role"] for box in metadata["layout"]["bbox_assertions"]["boxes"]}
    assert {"header_plan",
            "price_stop_loss", "rsi-rsi", "macd-macd"}.issubset(roles)
    assert "current_price" not in roles
    assert metadata["layout"]["current_price_location"] == "header_card"
    assert metadata["layout"]["current_marker"] == "latest_candle"
    assert metadata["layout"]["current_price_label_in_plot"] is False
    assert metadata["layout"]["header_accessory_card"]["one_line"] is True
    assert metadata["layout"]["header_accessory_card"]["truncated"] is False
    assert "entry_zone" not in roles
    assert metadata["layout"]["price_viewport"]["extension_included_in_anchors"] is False
    assert all("." not in label
               for label in metadata["layout"]["price_axis_tick_labels"])
    assert all(position > 0.85 for position in metadata["layout"]
               ["price_line_label_x_fractions"].values())
    assert not any("side-table" in role for role in roles)
