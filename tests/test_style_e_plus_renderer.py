"""Offline image contracts for the two Style E+ BTCUSD charts."""

from __future__ import annotations

import copy
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PIL import Image

from tools import image_output, intraday_bars
from tools import style_e_plus_renderer as renderer
from tools import style_e_plus_story
from tests.test_style_e_plus_contract import (
    b100_m15_rows as contract_m15_rows,
    rows as contract_rows,
)


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


def _renderer_story(side: str, close: float, *, accepted: bool) -> tuple[dict, list[dict], list[dict]]:
    """Build a real, numerically renderable v4/B100 fixture without mocks."""
    h1 = contract_rows(minutes=60, last_close=95.0)
    m15 = contract_m15_rows(side, close)
    # Keep H1 directional structure beyond Keltner without inflating ATR.
    if side == "buy":
        for row in h1[-20:]:
            row["high"] = row["close"] + 0.5
        h1[-10]["high"] = 100.0
    else:
        for row in h1[-20:]:
            row["low"] = row["close"] - 0.5
        h1[-10]["low"] = 70.0
    base = len(m15) - 23
    if side == "buy":
        values = (83.0, 82.0, 81.0, 82.0, 83.0) if accepted else (76.0, 75.0, 74.0, 75.0, 76.0)
        for index, value in zip(range(base + 12, base + 17), values):
            m15[index]["low"] = value
        m15[base + 5]["high"] = 130.0
    else:
        values = (94.0, 95.0, 96.0, 95.0, 94.0) if accepted else (104.0, 105.0, 106.0, 105.0, 104.0)
        for index, value in zip(range(base + 12, base + 17), values):
            m15[index]["high"] = value
        m15[base + 5]["low"] = 50.0
    m15[-1].update({"open": close - 0.1, "high": close + 0.5,
                    "low": close - 0.5, "close": close})
    story = style_e_plus_story.build(
        h1, m15,
        candle_basis=intraday_bars.basis_for(
            "btcusd", h1[-1]["at"], timeframe="1h", now=NOW),
        m15_candle_basis=intraday_bars.basis_for(
            "btcusd", m15[-1]["at"], timeframe="15min", now=NOW),
        publish_date="2026-08-25", now=NOW)
    return story, h1, m15


def built_story():
    return _renderer_story("buy", 87.0, accepted=True)


def built_no_plan_story():
    story, _, m15 = _renderer_story("buy", 87.0, accepted=False)
    assert story["state"] == "NO_PLAN" and story["plan"] is None
    return story, m15


def story_for_state(state: str, side: str):
    close = {("buy", "NO_PLAN"): 87.0,
             ("buy", "NO_CHASE"): 93.0,
             ("buy", "WAIT_TRIGGER"): 87.0,
             ("buy", "ENTRY_READY"): 89.0,
             ("sell", "NO_PLAN"): 93.0,
             ("sell", "NO_CHASE"): 87.0,
             ("sell", "WAIT_TRIGGER"): 93.0,
             ("sell", "ENTRY_READY"): 88.0}[side, state]
    story, _, m15 = _renderer_story(side, close, accepted=state != "NO_PLAN")
    assert story["state"] == state and story["side"] == (side if state != "NO_PLAN" else side)
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
    assert m15["layout"]["title"] is True
    assert m15["layout"]["status_box"] is True
    assert m15["elements"]["close_right_tag"] is True
    assert m15["elements"]["ema20_right_tag"] is False
    assert m15["elements"]["state_badge"] is True
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


@pytest.mark.parametrize("role", ["h1", "m15"])
def test_a_shaped_plan_fails_closed_at_both_renderers(role):
    story, h1, m15 = built_story()
    story["plan"].pop("variant")
    with tempfile.TemporaryDirectory() as folder:
        source = m15 if role == "m15" else h1
        function = renderer.render_execution if role == "m15" else renderer.render_context
        target = Path(folder) / story["images"][role]
        with pytest.raises(renderer.RendererContractError):
            function(story, source, target)
        assert not target.exists()


@pytest.mark.parametrize("role", ["h1", "m15"])
def test_adaptive_context_tamper_fails_closed_at_both_renderers(role):
    story, h1, m15 = built_story()
    story["adaptive_context"]["rows"][0]["close"] = "999.99"
    with tempfile.TemporaryDirectory() as folder:
        source = h1 if role == "h1" else m15
        function = renderer.render_context if role == "h1" else renderer.render_execution
        target = Path(folder) / story["images"][role]
        with pytest.raises(renderer.RendererContractError):
            function(story, source, target)
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
            "protective_stop_status": "inactive_until_external_fill",
            "protective_stop_activation_event": "external_entry_fill",
            "plan_created_at": story["plan"]["plan_created_at"],
            "effective_from": story["plan"]["effective_from"],
        }
        assert {path.name for path in Path(folder).iterdir()} == set(story["images"].values())


def test_no_plan_execution_keeps_ema_legend_but_has_no_ema_right_tag():
    story, m15 = built_no_plan_story()
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / story["images"]["m15"]
        result = renderer.render_execution(story, m15, target)

    assert result["metadata"]["labels"]["ema20"] == "EMA20 สำหรับจังหวะ M15"
    assert result["metadata"]["labels"]["ema20_role"] == "legend_only"
    assert result["metadata"]["labels"]["ema20_right_tag"] == {
        "visible": False, "text": None}
    offsets = result["metadata"]["labels"]["tag_offsets_points"]
    assert offsets == {"close": 0}
    assert result["metadata"]["labels"]["execution_levels"] == []


@pytest.mark.parametrize("state", ["NO_PLAN", "NO_CHASE", "WAIT_TRIGGER", "ENTRY_READY"])
@pytest.mark.parametrize("side", ["buy", "sell"])
def test_execution_state_matrix_has_truthful_badge_overlays_and_metadata(
        state, side, tmp_path):
    story, m15 = story_for_state(state, side)
    target = tmp_path / f"{state.lower()}-{side}.webp"
    result = renderer.render_execution(story, m15, target)
    metadata = result["metadata"]
    has_plan = state in {"WAIT_TRIGGER", "ENTRY_READY"}

    assert target.is_file() and target.stat().st_size <= image_output.MAX_IMAGE_BYTES
    with Image.open(target) as image:
        assert image.format == "WEBP"
        assert image.width >= 1800 and image.height >= 1000
    assert metadata["labels"]["state_badge"]["visible"] is True
    assert state in metadata["labels"]["state_badge"]["text"]
    assert metadata["elements"]["ema20"] is True
    assert metadata["elements"]["ema20_right_tag"] is False
    assert metadata["labels"]["ema20_role"] == "legend_only"
    assert metadata["labels"]["close_right_tag"]["visible"] is True
    assert metadata["elements"]["trade_plan_overlay"] is has_plan
    assert metadata["elements"]["execution_level_labels"] is has_plan
    assert metadata["lifecycle"]["position_confirmed"] is False
    assert metadata["lifecycle"]["protective_stop_active"] is False
    levels = metadata["labels"]["execution_levels"]
    if not has_plan:
        assert levels == []
        assert metadata["elements"]["entry_zone"] is False
        assert metadata["elements"]["protective_stop_plan"] is False
        assert metadata["elements"]["take_profit"] is False
    else:
        by_role = {item["role"]: item for item in levels}
        assert set(by_role) == {"entry_zone", "protective_stop_plan", "tp1", "tp2"}
        assert by_role["entry_zone"]["low"] == story["plan"]["entry_zone_low"]
        assert by_role["entry_zone"]["high"] == story["plan"]["entry_zone_high"]
        assert by_role["protective_stop_plan"]["price"] == (
            story["plan"]["protective_stop"]["price"])
        assert by_role["protective_stop_plan"]["active"] is False
        assert "หลัง Fill" in by_role["protective_stop_plan"]["text"]
        assert "ยังไม่ active" in by_role["protective_stop_plan"]["text"]


@pytest.mark.parametrize(("state", "mutation", "message"), [
    ("NO_PLAN", lambda story: story.__setitem__("plan", built_story()[0]["plan"]),
     "plan=None"),
    ("WAIT_TRIGGER", lambda story: story.__setitem__("plan", None), "story.plan"),
    ("WAIT_TRIGGER", lambda story: story["plan"]["protective_stop"].__setitem__(
        "status", "active"), "protective stop"),
    ("WAIT_TRIGGER", lambda story: story["plan"]["protective_stop"].__setitem__(
        "activation_event", "assumed_fill"), "protective stop"),
    ("WAIT_TRIGGER", lambda story: story["plan"]["protective_stop"].__setitem__(
        "effective_from", "2026-08-25T12:00:00+00:00"), "protective stop"),
    ("ENTRY_READY", lambda story: story["plan"].__setitem__(
        "trigger_confirmed", False), "trigger_confirmed"),
])
def test_execution_state_plan_and_lifecycle_mismatch_fail_before_write(
        state, mutation, message, tmp_path):
    story, m15 = story_for_state(state, "buy")
    mutation(story)
    target = tmp_path / "must-not-exist.webp"
    with pytest.raises(renderer.RendererContractError, match=message):
        renderer.render_execution(story, m15, target)
    assert not target.exists()


@pytest.mark.parametrize("state", ["NO_PLAN", "NO_CHASE", "WAIT_TRIGGER", "ENTRY_READY"])
def test_ema20_never_creates_a_right_price_tag(state, monkeypatch, tmp_path):
    story, m15 = story_for_state(state, "buy")
    observed = []
    original = renderer._right_tag

    def capture(axes, value, text, color, **kwargs):
        observed.append(text)
        return original(axes, value, text, color, **kwargs)

    monkeypatch.setattr(renderer, "_right_tag", capture)
    renderer.render_execution(story, m15, tmp_path / f"{state}.webp")
    assert len(observed) == 1
    assert observed[0].startswith("ราคาปิด M15 ")
    assert "EMA20" not in observed[0]
