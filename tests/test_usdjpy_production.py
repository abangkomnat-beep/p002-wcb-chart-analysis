"""Production-registration contract for USD/JPY across Styles A-J."""

from __future__ import annotations

import json
from pathlib import Path

from tools import (
    build_daily_package,
    consistency_gate,
    intraday_bars,
    intraday_writer_base,
    license_gate,
    market_calendar,
    style_d_calendar,
    wcb_source,
)


REPO = Path(__file__).resolve().parents[1]


def _json(name: str) -> dict:
    return json.loads((REPO / "config" / name).read_text(encoding="utf-8"))


def test_usdjpy_core_profile_uses_yen_quote_precision():
    asset = build_daily_package.ASSETS["usdjpy"]
    profile = wcb_source.profile_for("usdjpy")

    assert asset["symbol"] == profile["symbol"] == "USD/JPY"
    assert asset["wcb"] == wcb_source.tag_for("usdjpy") == "usdjpy"
    assert asset["instrument_type"] == "forex_spot"
    assert asset["decimals"] == profile["decimals"] == 3
    assert "เยน" in asset["unit"] and "เยน" in profile["unit_phrase"]


def test_usdjpy_is_enabled_in_every_production_style():
    registry = _json("article_styles.json")
    styles = registry["styles"].values()

    assert {style["letter"] for style in styles} == set("ABCDEFGHIJ")
    assert all(style["production"] is True for style in styles)
    assert all("usdjpy" in style["assets"] for style in styles)


def test_usdjpy_data_governance_registries_are_complete():
    assert market_calendar.for_asset("usdjpy").asset_class == "forex_spot"

    timezone_book = intraday_bars.load_feed_timezones()
    assert timezone_book["assets"]["usdjpy"]["offset_minutes"] == 0

    license_book = license_gate.load_registry()
    assert license_book["asset_providers"]["usdjpy"] == ["wcb_series_api"]

    news_book = _json("news_sources.json")
    assert "usdjpy" in news_book["assets"]
    assert "bank of japan" in news_book["assets"]["usdjpy"]["keywords"]


def test_usdjpy_calendar_and_event_mappings_are_fail_closed():
    registry = style_d_calendar.load_registry()
    assert "usdjpy" in registry["assets"]

    event_book = _json("event_impact.json")
    assert "usdjpy" in event_book["currency_assets"]["USD"]
    assert event_book["currency_assets"]["JPY"] == ["usdjpy"]
    assert "usdjpy" in event_book["assets_enabled_now"]


class _Spec:
    @staticmethod
    def title_tail(_story: dict) -> str:
        return "แรงเทรนด์ระหว่างวัน"

    @staticmethod
    def excerpt_clauses(_story: dict) -> list[str]:
        return ["ติดตามสถานะ USD/JPY จากแท่งที่ปิดแล้วและเงื่อนไขที่วัดได้"]


def _frontmatter(direction: str | None) -> str:
    story = {
        "asset": "usdjpy",
        "bar_date": "2026-08-21",
        "timeframe": "30min",
        "direction": direction,
    }
    return "\n".join(intraday_writer_base.frontmatter_lines(story, _Spec))


def test_intraday_frontmatter_preserves_neutral_as_flat():
    assert "trend: up" in _frontmatter("up")
    assert "trend: dn" in _frontmatter("down")
    assert "trend: fl" in _frontmatter(None)


def test_consistency_gate_understands_explicit_flat_trend():
    story = {"regime": {"down": False}, "trend_code": "fl"}
    matching = consistency_gate.check("---\ntrend: fl\n---\n", story)
    mismatching = consistency_gate.check("---\ntrend: up\n---\n", story)

    assert not any(item["rule"] == "trend_regime_mismatch" for item in matching)
    assert any(item["rule"] == "trend_regime_mismatch" for item in mismatching)
