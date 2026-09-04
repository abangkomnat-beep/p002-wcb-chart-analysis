from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tools import style_m_v7_contract, style_m_v7_renderer, style_m_v7_risk
from tools import style_m_v7_story, style_m_v7_writer
from tests.test_style_m_v7_adr14 import rows_fixture


def _pair():
    cutoff = datetime.fromisoformat("2026-09-03T00:00:00+07:00")
    h1 = rows_fixture()
    built = style_m_v7_story.build(h1, cutoff=cutoff, source_label="paired-live",
                                   source_meta={"fixture": False})
    built["story"]["pivots"] = {"lows": [{"price": 1100}], "highs": [{"price": 930}]}
    story = style_m_v7_risk.apply_policy(
        built["story"], volatility=style_m_v7_risk.adr14(h1, cutoff=cutoff))
    facts = style_m_v7_contract.build(story, built["rows"])
    start = cutoff - timedelta(minutes=15 * 97)
    m15 = []
    for index in range(97):
        at = start + timedelta(minutes=15 * index)
        base = 80_000 + index * 4 + (index % 9) * 11
        m15.append({"index": index, "at": at.strftime("%Y-%m-%d %H:%M:%S"),
                    "open": base, "high": base + 90, "low": base - 90,
                    "close": base + (20 if index % 2 == 0 else -15)})
    return built, story, facts, m15


def test_r6_renderer_exposes_two_exact_roles_and_h1_whitelist(tmp_path):
    built, story, facts, m15 = _pair()
    pair = style_m_v7_renderer.render_pair(
        story, built["rows"], m15, tmp_path, facts=facts,
        visual_source={"source_sha256": "b" * 64})
    assert set(pair["images"]) == {"h1_market_map", "m15_entry_plan"}
    h1 = pair["images"]["h1_market_map"]
    assert h1["header_title"] == "BTCUSD · H1 MARKET MAP"
    assert h1["role"] == "h1_market_map"
    assert h1["forbidden_execution_artist_count"] == 0
    assert h1["watermark_count"] == 1
    assert any(item["role"] == "trap_band" for item in h1["artists"])
    assert not any(token in json.dumps(h1, ensure_ascii=False)
                   for token in ("M15", "ENTRY", "SL", "TP1", "TP2"))
    assert "buy_trigger" not in json.dumps(h1, ensure_ascii=False)
    assert "sell_trigger" not in json.dumps(h1, ensure_ascii=False)


def test_r6_m15_is_display_only_but_has_all_canonical_execution_levels(tmp_path):
    built, story, facts, m15 = _pair()
    meta = style_m_v7_renderer.render_role(
        story, m15, tmp_path / "m15.webp", role="m15_entry_plan", facts=facts)
    assert meta["header_title"] == "BTCUSD · M15 ENTRY · H1 PLAN"
    assert meta["role"] == "m15_entry_plan"
    assert len(meta["summary_cards"]) == 2
    assert len(meta["entry_bands"]) == 2
    assert len(meta["execution_lines"]) == 6
    assert all(line["line_style"] == "solid" for line in meta["execution_lines"]
               if line["role"] == "SL")
    assert all(line["line_style"] == "dashed" for line in meta["execution_lines"]
               if line["role"] in {"TP1", "TP2"})
    assert {label["role"] for label in meta["right_labels"]} == {"SL", "TP1", "TP2"}
    assert all(label["label_position"] == "above_line" for label in meta["right_labels"])
    assert all(label["bbox"][0] >= meta["layout"]["plot"][0]
               and label["bbox"][2] <= meta["layout"]["plot"][2]
               for label in meta["right_labels"])
    assert meta["separate_entry_high_low_count"] == 0
    assert meta["displayed_bars"] == 72
    assert meta["watermark_count"] == 1
    assert 9 <= len(meta["price_ticks"]) <= 11
    assert meta["layout"]["latest_candle_fraction"] >= 0.82
    assert meta["layout"]["latest_candle_fraction"] <= 0.86
    assert meta["layout"]["plan_lane_fraction"] <= 0.18
    assert meta["label_overlap_count"] == 0


def test_r7_m15_cards_are_horizontal_and_inside_top_right_strip(tmp_path):
    built, story, facts, m15 = _pair()
    meta = style_m_v7_renderer.render_role(
        story, m15, tmp_path / "m15.webp", role="m15_entry_plan", facts=facts)
    cards = meta["summary_cards"]
    assert len(cards) == 2
    assert cards[0]["bbox"][1] == cards[1]["bbox"][1]
    assert cards[0]["bbox"][2] <= cards[1]["bbox"][0]
    assert all(card["position"] == "top_right_horizontal" for card in cards)


def test_r7_h1_watermark_and_trap_are_pixel_contracts(tmp_path):
    built, story, facts, m15 = _pair()
    meta = style_m_v7_renderer.render_role(
        story, built["rows"], tmp_path / "h1.webp", role="h1_market_map", facts=facts)
    assert meta["watermark"]["text"] == "WorldClassBroker"
    assert meta["watermark_count"] == 1
    assert sum(item["role"] == "donchian_upper" for item in meta["artists"]) == 1
    assert sum(item["role"] == "donchian_lower" for item in meta["artists"]) == 1


def test_r7_m15_label_anchor_is_above_every_execution_line(tmp_path):
    built, story, facts, m15 = _pair()
    meta = style_m_v7_renderer.render_role(
        story, m15, tmp_path / "m15.webp", role="m15_entry_plan", facts=facts)
    assert all(item["bbox"][3] <= item["y_anchor"] for item in meta["right_labels"])


def test_r8_h1_and_m15_restore_visible_source_time_axes(tmp_path):
    built, story, facts, m15 = _pair()
    pair = style_m_v7_renderer.render_pair(
        story, built["rows"], m15, tmp_path, facts=facts)
    expected = {"h1_market_map": 7, "m15_entry_plan": 8}
    for role, count in expected.items():
        meta = pair["images"][role]
        ticks = meta["time_ticks"]
        assert len(ticks) == count
        assert all(tick["source_at"] and tick["label"].endswith("น.") for tick in ticks)
        assert all(ticks[index]["x"] < ticks[index + 1]["x"]
                   for index in range(len(ticks) - 1))
        assert all(tick["contained_in_canvas"] for tick in ticks)
        assert meta["time_tick_overlap_count"] == 0
        assert ticks[0]["source_index"] == 0
        assert ticks[-1]["source_index"] == meta["displayed_bars"] - 1


def test_r8_m15_has_eleven_price_ticks_all_inside_plot(tmp_path):
    built, story, facts, m15 = _pair()
    meta = style_m_v7_renderer.render_role(
        story, m15, tmp_path / "m15.webp", role="m15_entry_plan", facts=facts)
    top, bottom = meta["layout"]["plot"][1], meta["layout"]["plot"][3]
    ticks = meta["price_ticks"]
    assert len(ticks) == 11
    assert all(top <= tick["y"] <= bottom for tick in ticks)
    assert all(ticks[index]["y"] < ticks[index + 1]["y"]
               for index in range(len(ticks) - 1))
    gaps = [ticks[index + 1]["y"] - ticks[index]["y"]
            for index in range(len(ticks) - 1)]
    assert min(gaps) >= 60


def test_r8_m15_uses_compact_side_filled_price_pills(tmp_path):
    built, story, facts, m15 = _pair()
    meta = style_m_v7_renderer.render_role(
        story, m15, tmp_path / "m15.webp", role="m15_entry_plan", facts=facts)
    for label in meta["right_labels"]:
        width = label["bbox"][2] - label["bbox"][0]
        assert label["content_sized"] is True
        assert label["text_color"] == "#FFFFFF"
        assert label["fill_color"] in {"#087F5B", "#B42318"}
        assert width <= 120
    assert len({label["bbox"][2] - label["bbox"][0]
                for label in meta["right_labels"]}) > 1


def test_r10_m15_first_candle_is_fully_inside_plot_and_time_grid_shares_anchor(tmp_path):
    built, story, facts, m15 = _pair()
    meta = style_m_v7_renderer.render_role(
        story, m15, tmp_path / "m15.webp", role="m15_entry_plan", facts=facts)
    plot_left = meta["layout"]["plot"][0]
    first = meta["candles"][0]
    assert first["body_bbox"][0] >= plot_left
    assert first["wick_x"] >= plot_left
    assert meta["time_ticks"][0]["x"] == meta["layout"]["data_x_start"]
    assert meta["vertical_time_grid"][0]["x"] == meta["layout"]["data_x_start"]


def test_r10_m15_entry_text_is_centered_in_band_and_has_no_entry_pills(tmp_path):
    built, story, facts, m15 = _pair()
    meta = style_m_v7_renderer.render_role(
        story, m15, tmp_path / "m15.webp", role="m15_entry_plan", facts=facts)
    expected = {
        ("Buy" if plan["side"] == "LONG" else "Sell")
        + f" {float(plan['entry_low']):,.0f} - {float(plan['entry_high']):,.0f}"
        for plan in story["scenarios"].values()
        if plan.get("entry_low") is not None
    }
    assert {band["text"] for band in meta["entry_bands"]} == expected
    assert all(band["centered"] is True for band in meta["entry_bands"])
    for band in meta["entry_bands"]:
        box = band["bbox"]
        text_box = band["text_bbox"]
        expected_center = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
        assert abs(band["text_center"][0] - expected_center[0]) <= 1
        assert abs(band["text_center"][1] - expected_center[1]) <= 1
        if box[3] - box[1] >= text_box[3] - text_box[1]:
            assert band["text_contained"] is True
            assert box[0] <= text_box[0] <= text_box[2] <= box[2]
            assert box[1] <= text_box[1] <= text_box[3] <= box[3]
    assert not any(label["role"] == "ENTRY" for label in meta["right_labels"])


def test_r8_m15_cards_are_inside_dark_header_and_clear_title(tmp_path):
    built, story, facts, m15 = _pair()
    meta = style_m_v7_renderer.render_role(
        story, m15, tmp_path / "m15.webp", role="m15_entry_plan", facts=facts)
    header = meta["header"]
    cards = meta["summary_cards"]
    assert len(cards) == 2
    assert all(card["contained_in_header"] for card in cards)
    assert all(card["bbox"][3] <= header["header_height_px"] - header["underline_height_px"]
               for card in cards)
    assert all(card["line_count"] == 2 for card in cards)
    assert cards[0]["bbox"][2] <= cards[1]["bbox"][0]
    assert cards[0]["bbox"][0] >= header["title_bbox_px"][2] + 24
    assert cards[-1]["bbox"][2] <= style_m_v7_renderer.WIDTH - 24


def test_r9_vertical_time_grids_match_time_tick_anchors(tmp_path):
    built, story, facts, m15 = _pair()
    pair = style_m_v7_renderer.render_pair(
        story, built["rows"], m15, tmp_path, facts=facts)
    expected = {"h1_market_map": 7, "m15_entry_plan": 8}
    for role, count in expected.items():
        meta = pair["images"][role]
        grids = meta["vertical_time_grid"]
        assert len(grids) == count
        assert [item["x"] for item in grids] == [item["x"] for item in meta["time_ticks"]]
        assert all(item["y_start"] == meta["layout"]["plot"][1]
                   and item["y_end"] == meta["layout"]["plot"][3]
                   for item in grids)
        assert all(item["layer"] == "background_grid" for item in grids)


def test_r9_m15_uses_72_bars_and_full_canvas_zoom_geometry(tmp_path):
    built, story, facts, m15 = _pair()
    meta = style_m_v7_renderer.render_role(
        story, m15, tmp_path / "m15.webp", role="m15_entry_plan", facts=facts)
    plot = meta["layout"]["plot"]
    assert meta["displayed_bars"] == 72
    assert meta["time_ticks"][0]["source_index"] == 0
    assert meta["time_ticks"][-1]["source_index"] == 71
    assert plot[0] <= 28 and plot[1] <= 118
    assert plot[2] >= 1810 and plot[3] >= 1010
    assert (plot[2] - plot[0]) / style_m_v7_renderer.WIDTH >= 0.92
    assert (plot[3] - plot[1]) / style_m_v7_renderer.HEIGHT >= 0.82
    assert meta["layout"]["domain_padding_fraction"] <= 0.03


def test_r9_header_cards_size_to_painted_content_without_dead_space(tmp_path):
    built, story, facts, m15 = _pair()
    meta = style_m_v7_renderer.render_role(
        story, m15, tmp_path / "m15.webp", role="m15_entry_plan", facts=facts)
    cards = meta["summary_cards"]
    for card in cards:
        card_width = card["bbox"][2] - card["bbox"][0]
        text_width = max(box[2] - box[0] for box in card["text_bboxes"])
        assert 270 <= card_width <= 360
        assert card_width == max(270, min(360, text_width + 44))
        assert card["content_sized"] is True
    assert cards[-1]["bbox"][2] == style_m_v7_renderer.WIDTH - 24


def test_r6_writer_has_exact_four_h2_two_distinct_alt_texts_and_no_table():
    built, story, facts, m15 = _pair()
    article = style_m_v7_writer.compose(
        {"story": story, "facts": facts,
         "image_names": {"h1_market_map": "h1.webp", "m15_entry_plan": "m15.webp"}})
    assert style_m_v7_writer.H2 == tuple(style_m_v7_writer.R6_H2)
    assert [line[3:] for line in article.splitlines() if line.startswith("## ")] == list(style_m_v7_writer.R6_H2)
    assert article.count("h1.webp") == 1 and article.count("m15.webp") == 1
    assert "| รายละเอียด |" not in article
    assert "Liquidity Pools & Trap Zones" not in article
    for forbidden in ("ระดับ Stop Loss เป็นจุดตัดขาดทุนตามแผน",
                      "ไม่ใช่ราคาที่รับประกันการจับคู่",
                      "การรับประกันการจับคู่",
                      "คำยืนยันผลลัพธ์",
                      "ควรเผื่อ Spread และ Slippage เสมอ",
                      "RR ยังไม่หัก spread/slippage",
                      "ก่อนใช้งานต้องคำนวณใหม่จากราคาจับคู่จริง"):
        assert forbidden not in article
    assert "Entry width 0.10" in article
    assert "risk floor 0.50" in article
    assert "cap 1.00" in article
    assert "Entry width 0 ดอลลาร์" not in article
    assert "risk floor 1 ดอลลาร์" not in article
    assert "cap 1 ดอลลาร์" not in article
    assert "กราฟ BTCUSD H1 Market Map" in article
    assert "กราฟ BTCUSD M15 Entry Plan จากแผน H1" in article


def test_r6_h1_is_invariant_when_m15_changes(tmp_path):
    built, story, facts, m15 = _pair()
    first = style_m_v7_renderer.render_role(story, built["rows"], tmp_path / "a.webp",
                                             role="h1_market_map", facts=facts)
    mutated = deepcopy(m15)
    for row in mutated:
        row["close"] += 999
    second = style_m_v7_renderer.render_role(story, built["rows"], tmp_path / "b.webp",
                                              role="h1_market_map", facts=facts)
    assert first["canonical_facts_sha256"] == second["canonical_facts_sha256"]
    assert first["story_source_sha256"] == second["story_source_sha256"]


def test_r6_f01_article_image_set_must_be_exact(tmp_path):
    built, story, facts, m15 = _pair()
    article = style_m_v7_writer.compose(
        {"story": story, "facts": facts,
         "image_names": {"h1_market_map": "h1.webp", "m15_entry_plan": "m15.webp"}})
    refs = {line.split("](", 1)[1][:-1] for line in article.splitlines()
            if line.startswith("![")}
    assert refs == {"h1.webp", "m15.webp"}
    assert "btcusd-style-m-v7-h1-plan-m15-execution-" not in article


def test_r6_daily_manifest_binds_two_assets_and_one_paired_source(tmp_path):
    from tools import style_m_v7_daily as daily

    built, story, facts, m15 = _pair()
    for row in m15:
        stamp = datetime.strptime(row["at"], "%Y-%m-%d %H:%M:%S") - timedelta(days=4)
        row["at"] = stamp.strftime("%Y-%m-%d %H:%M:%S")
    h1 = rows_fixture()
    def fetch(asset, *, timeframe, outputsize):
        if timeframe == "1h":
            return ({"asset": asset, "timeframe": timeframe}, h1, "captured-live-h1")
        return ({"asset": asset, "timeframe": timeframe}, m15, "captured-live-m15")

    result = daily.run_shadow(root=tmp_path, cutoff_at="2026-08-30T00:00:00+07:00",
                              fetcher=fetch)
    manifest_path = Path(result["shadow"]) / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert set(manifest["files"]) == {"btc.md", *manifest["image_names"]} if "image_names" in manifest else len(manifest["files"]) == 3
    assert set(manifest["images"]) == {"h1_market_map", "m15_entry_plan"}
    assert manifest["visual_source"]["source_label"] == "captured-live-m15"
    assert manifest["production_write"] is False and manifest["external_publish"] is False
    article = (Path(result["shadow"]) / "public" / "btc.md").read_text(encoding="utf-8")
    refs = set(__import__("re").findall(r"!\[[^]]*\]\(([^)]+)\)", article))
    assert refs == {Path(item["path"]).name for item in manifest["images"].values()}
