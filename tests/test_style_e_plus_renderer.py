"""Offline image contracts for the two Style E+ BTCUSD charts."""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PIL import Image

from tools import image_output, intraday_bars
from tools import style_e_plus_renderer as renderer
from tools import style_e_plus_story


NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


def rows(*, minutes: int, count: int = 260, start_price: float = 79_000.0) -> list[dict]:
    start = datetime(2026, 8, 10)
    output, previous = [], start_price
    for index in range(count):
        movement = 14.0 + ((index % 11) - 5) * 18.0 + (45.0 if index % 17 == 0 else 0.0)
        if minutes == 15:
            movement = ((index % 8) - 3.5) * 12.0
        close = previous + movement
        high = max(previous, close) + 90.0 + index % 13
        low = min(previous, close) - 85.0 - index % 7
        at = start + timedelta(minutes=minutes * index)
        output.append({
            "at": at.strftime("%Y-%m-%d %H:%M:%S"),
            "date": at.strftime("%Y-%m-%d"),
            "open": previous, "high": high, "low": low, "close": close,
            "forming": False,
        })
        previous = close
    return output


def built_story():
    h1, m15 = rows(minutes=60), rows(minutes=15, start_price=80_000.0)
    story = style_e_plus_story.build(
        h1, m15,
        candle_basis=intraday_bars.basis_for(
            "btcusd", h1[-1]["at"], timeframe="1h", now=NOW),
        m15_candle_basis=intraday_bars.basis_for(
            "btcusd", m15[-1]["at"], timeframe="15min", now=NOW),
        publish_date="2026-08-25", now=NOW)
    # Renderer fixture always carries an inspectable BUY overlay; story decision
    # semantics are covered independently in test_style_e_plus_contract.py.
    ema20 = story["m15"]["indicators"]["ema20"]
    atr = story["m15"]["indicators"]["atr"]["value"]
    entry_low, entry_high = ema20 - 0.25 * atr, ema20 + 0.25 * atr
    stop = entry_low - atr
    risk = entry_high - stop
    plan_created_at = story["candle_basis"]["m15"]["basis_close_at"]
    story.update({"state": "WAIT_TRIGGER", "side": "buy", "plan": {
        "side": "buy", "timeframe": "15min", "trigger": ema20,
        "plan_created_at": plan_created_at, "effective_from": plan_created_at,
        "trigger_rule": "close_above_ema20", "entry_zone_low": entry_low,
        "entry_zone_high": entry_high, "pre_entry_invalidation_close": stop,
        "pre_entry_invalidation_rule": "m15_close_at_or_below_level_after_effective_from",
        "protective_stop": {
            "price": stop, "active": False,
            "status": "inactive_until_external_fill",
            "activation_event": "external_entry_fill", "effective_from": None,
        },
        "disadvantaged_entry": entry_high, "risk": risk,
        "tp1": entry_high + 1.5 * risk, "tp2": entry_high + 2.0 * risk,
        "rr1": 1.5, "rr2": 2.0, "trigger_confirmed": False,
    }})
    return story, h1, m15


def built_no_plan_story():
    h1, m15 = rows(minutes=60), rows(minutes=15, start_price=80_000.0)
    story = style_e_plus_story.build(
        h1, m15,
        candle_basis=intraday_bars.basis_for(
            "btcusd", h1[-1]["at"], timeframe="1h", now=NOW),
        m15_candle_basis=intraday_bars.basis_for(
            "btcusd", m15[-1]["at"], timeframe="15min", now=NOW),
        publish_date="2026-08-25", now=NOW)
    assert story["state"] == "NO_PLAN" and story["plan"] is None
    return story, m15


def test_metadata_contracts_separate_context_from_execution():
    h1 = renderer.context_metadata_contract()
    m15 = renderer.execution_metadata_contract()
    assert h1["role"] == "h1_context" and h1["layout"]["panel_count"] == 3
    assert m15["role"] == "m15_execution" and m15["layout"]["panel_count"] == 1
    assert h1["elements"]["trade_plan_overlay"] is False
    assert m15["elements"]["trade_plan_overlay"] is True
    assert m15["elements"]["stop_loss"] is False
    assert m15["elements"]["protective_stop_plan"] is True
    assert m15["elements"]["protective_stop_active"] is False
    assert m15["elements"]["conditional_projection"] is False
    assert h1["elements"]["volume"] is m15["elements"]["volume"] is False
    first = renderer.context_metadata_contract()
    first["layout"]["panels"].append("bad")
    assert "bad" not in renderer.context_metadata_contract()["layout"]["panels"]


@pytest.mark.parametrize("role", ["h1", "m15"])
def test_forming_row_fails_before_creating_either_image(role):
    story, h1, m15 = built_story()
    source = h1 if role == "h1" else m15
    source[-1]["forming"] = True
    function = renderer.render_context if role == "h1" else renderer.render_execution
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / story["images"][role]
        with pytest.raises(renderer.RendererContractError, match="forming"):
            function(story, source, target)
        assert not target.exists()


def test_story_indicator_mismatch_fails_before_context_image_write():
    story, h1, _ = built_story()
    story["indicators"]["donchian"]["upper"] += 1.0
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / story["images"]["h1"]
        with pytest.raises(renderer.RendererContractError, match="ไม่ตรง"):
            renderer.render_context(story, h1, target)
        assert not target.exists()


def test_story_indicator_mismatch_fails_before_execution_image_write():
    story, _, m15 = built_story()
    story["m15"]["indicators"]["ema20"] += 1.0
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / story["images"]["m15"]
        with pytest.raises(renderer.RendererContractError, match="ไม่ตรง"):
            renderer.render_execution(story, m15, target)
        assert not target.exists()


def test_active_protective_stop_claim_fails_before_execution_image_write():
    story, _, m15 = built_story()
    story["plan"]["protective_stop"]["active"] = True
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / story["images"]["m15"]
        with pytest.raises(renderer.RendererContractError, match="protective stop"):
            renderer.render_execution(story, m15, target)
        assert not target.exists()


def test_both_renderers_write_distinct_valid_webp_images():
    story, h1, m15 = built_story()
    with tempfile.TemporaryDirectory() as folder:
        h1_path = Path(folder) / story["images"]["h1"]
        m15_path = Path(folder) / story["images"]["m15"]
        results = {
            "h1": renderer.render_context(story, h1, h1_path),
            "m15": renderer.render_execution(story, m15, m15_path),
        }
        for role, path in (("h1", h1_path), ("m15", m15_path)):
            assert results[role]["path"] == str(path)
            assert path.stat().st_size <= image_output.MAX_IMAGE_BYTES
            assert path.read_bytes()[:4] == b"RIFF" and path.read_bytes()[8:12] == b"WEBP"
            with Image.open(path) as image:
                assert image.format == "WEBP"
                assert image.width >= 1800 and image.height >= 1000
                assert image.convert("RGB").getpixel((0, 0)) == (255, 255, 255)
            assert results[role]["metadata"]["bars"]["closed_only"] is True
        assert results["h1"]["metadata"]["role"] == "h1_context"
        assert results["m15"]["metadata"]["role"] == "m15_execution"
        assert results["h1"]["metadata"]["bars"]["displayed"] == 120
        assert results["m15"]["metadata"]["bars"]["displayed"] == 60
        assert results["m15"]["metadata"]["bars"]["future_space"] == 20
        assert results["m15"]["metadata"]["projection"] == {
            "mode": "none", "guaranteed": False,
            "historical_data": False, "visible": False,
        }
        assert results["m15"]["metadata"]["lifecycle"] == {
            "state": "WAIT_TRIGGER",
            "position_confirmed": False,
            "protective_stop_active": False,
            "protective_stop_activation": "external_fill_required",
            "plan_created_at": story["plan"]["plan_created_at"],
            "effective_from": story["plan"]["effective_from"],
        }
        assert {path.name for path in Path(folder).iterdir()} == set(story["images"].values())


def test_no_plan_execution_uses_ema_label_not_trigger_label():
    story, m15 = built_no_plan_story()
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / story["images"]["m15"]
        result = renderer.render_execution(story, m15, target)

    assert result["metadata"]["labels"]["ema20"] == "EMA20 M15"
    assert result["metadata"]["labels"]["ema20_role"] == "reference_only"
    offsets = result["metadata"]["labels"]["tag_offsets_points"]
    assert offsets["ema20"] - offsets["close"] >= 36
