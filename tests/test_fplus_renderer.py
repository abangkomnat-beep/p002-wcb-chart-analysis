"""Single composite WebP contract; renderer consumes rather than recalculates."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from fixtures.fplus.contract_support import load_json, require_module, valid_snapshot


def test_renderer_creates_one_valid_webp_under_200kb(tmp_path):
    renderer = require_module("tools.fplus_renderer")
    target = tmp_path / "btcusd-fplus-2026-08-24.webp"
    returned = renderer.render_webp(load_json("selected_trade.json"), valid_snapshot(), target)
    assert Path(returned) == target
    assert target.is_file()
    assert target.stat().st_size <= 204_800
    assert list(tmp_path.iterdir()) == [target]
    with Image.open(target) as image:
        assert image.format == "WEBP"
        assert image.width >= 1200
        assert image.height >= 675


def test_no_trade_renderer_still_creates_one_image_without_trade_levels(tmp_path):
    renderer = require_module("tools.fplus_renderer")
    plan = load_json("selected_no_trade.json")
    target = tmp_path / "btcusd-fplus-2026-08-24.webp"
    renderer.render_webp(plan, valid_snapshot(), target)
    assert target.is_file()
    metadata = renderer.describe_render(plan)
    assert metadata["selection"] == "NO_TRADE"
    assert metadata["trade_levels"] == []


def test_renderer_does_not_reselect_candidate_or_change_plan_numbers(tmp_path):
    renderer = require_module("tools.fplus_renderer")
    plan = load_json("selected_trade.json")
    metadata = renderer.describe_render(plan)
    assert metadata["selection"] == "J"
    assert metadata["entry_zone"] == plan["entry_zone"]
    assert metadata["stop_loss"] == plan["stop_loss"]
    assert metadata["take_profit_1"] == plan["take_profit_1"]

