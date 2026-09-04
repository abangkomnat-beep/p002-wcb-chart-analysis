from __future__ import annotations

import ast
import copy
from pathlib import Path
from unittest import mock

import pytest

from tools import forex_daily_plan


ASSETS = ("eurusd", "gbpusd", "usdjpy", "audusd", "usdcad")


def _neutral_plan() -> dict:
    return {
        "active": False,
        "direction": None,
        "side": "OCO",
        "watch_low": 1.38320,
        "watch_high": 1.38473,
        "plans": [
            {"side": "BUY", "trigger": {"value": 1.38473},
             "entry_zone": {"low": 1.38473, "high": 1.38473},
             "stop_loss": 1.38366, "take_profit": [1.38580, 1.38686]},
            {"side": "SELL", "trigger": {"value": 1.38320},
             "entry_zone": {"low": 1.38320, "high": 1.38320},
             "stop_loss": 1.38427, "take_profit": [1.38213, 1.38107]},
        ],
    }


def _active_plan(side: str = "BUY", *, zone=(1.3840, 1.3842)) -> dict:
    trigger = 1.3841 if side == "BUY" else 1.3832
    return {
        "active": True,
        "direction": "up" if side == "BUY" else "down",
        "side": side,
        "watch_low": 1.3830,
        "watch_high": 1.3850,
        "plans": [{"side": side, "trigger": {"value": trigger},
                   "entry_zone": {"low": zone[0], "high": zone[1]},
                   "stop_loss": 1.3820 if side == "BUY" else 1.3850,
                   "take_profit": [1.3860, 1.3880] if side == "BUY"
                   else [1.3810, 1.3790]}],
    }


def _wait_plan() -> dict:
    plan = _active_plan("SELL")
    plan["active"] = False
    return plan


def _rows(price=1.3840, count=120):
    return [{"at": f"2026-09-{(i % 28) + 1:02d} {i % 24:02d}:00:00",
             "open": price, "high": price + 0.001,
             "low": price - 0.001, "close": price + 0.0002}
            for i in range(count)]


def _capture(monkeypatch):
    captured = []

    def save(figure, *_args, **_kwargs):
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        FigureCanvasAgg(figure).draw()
        captured.append(figure)
        return 123

    monkeypatch.setattr(forex_daily_plan, "_thai_font", lambda: None)
    monkeypatch.setattr(forex_daily_plan.image_output, "save_figure", save)
    return captured


def _visible_specs(figure):
    return [artist for artist in figure.axes[-1].texts
            if str(artist.get_gid() or "").startswith(
                "premium-label:style-l:")]


def test_m15_neutral_oco_contract_is_asset_agnostic_current_matrix(monkeypatch):
    plan = _neutral_plan()
    for asset in ASSETS:
        captured = _capture(monkeypatch)
        forex_daily_plan.save_m15_chart(
            asset, _rows(), "NO_SETUP", {"I": {}}, copy.deepcopy(plan), None,
            {"basis_close_at": "2026-09-04T00:00:00+00:00"},
            forex_daily_plan.load_decision_policy(), Path("unused.webp"))
        figure = captured[0]
        texts = _visible_specs(figure)
        visible = " ".join(item.get_text() for item in texts)
        assert figure._premium_header_card_layout["text"] == (
            "NEUTRAL / โซนสังเกตการณ์")
        assert figure._premium_axis_layout["central_decision_card_count"] == 0
        assert sum(item.get_text().startswith("BUY Entry ") for item in texts) == 1
        assert sum(item.get_text().startswith("SELL Entry ") for item in texts) == 1
        assert sum(item.get_text().startswith(("TP1 ", "TP2 ")) for item in texts) == 4
        assert not any(word in visible for word in ("OCO", "Trigger", "SL"))
        profile = forex_daily_plan.wcb_source.profile_for(asset)
        decimals = profile.get("chart_decimals", profile["decimals"])
        price_tokens = [item.get_text().rsplit(" ", 1)[-1] for item in texts]
        assert all(len(token.split(".")[-1]) == decimals
                   for token in price_tokens)

        # The labels must be the canonical values formatted by the shared
        # visual precision policy, not values rounded by the asset slug.
        formatter = forex_daily_plan.chart_price_formatter(asset)
        assert f"BUY Entry {formatter(1.38473)}" in visible
        assert f"SELL Entry {formatter(1.38320)}" in visible


@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_m15_active_directional_contract_is_asset_agnostic_current_matrix(
        monkeypatch, side):
    for asset in ASSETS:
        captured = _capture(monkeypatch)
        plan = _active_plan(side)
        before = copy.deepcopy(plan)
        forex_daily_plan.save_m15_chart(
            asset, _rows(), "I", {"I": {}}, plan, "up" if side == "BUY" else "down",
            {"basis_close_at": "2026-09-04T00:00:00+00:00"},
            forex_daily_plan.load_decision_policy(), Path("unused.webp"))
        figure = captured[0]
        texts = _visible_specs(figure)
        visible = " ".join(item.get_text() for item in texts)
        assert figure._premium_header_card_layout["text"] == f"แผน {side}"
        assert figure._premium_axis_layout["central_decision_card_count"] == 0
        assert sum(item.get_text().startswith(f"{side} Entry ") for item in texts) == 1
        assert any(item.get_text().startswith("SL ") for item in texts)
        assert sum(item.get_text().startswith(("TP1 ", "TP2 ")) for item in texts) == 2
        assert "Trigger" not in visible and "Target" not in visible
        assert plan == before
        assert any(patch.get_gid() == "premium-zone:style-l:entry-zone"
                   for patch in figure.axes[-1].patches)


def test_m15_directional_wait_contract_is_asset_agnostic_current_matrix(monkeypatch):
    for asset in ASSETS:
        captured = _capture(monkeypatch)
        forex_daily_plan.save_m15_chart(
            asset, _rows(), "WAIT", {"I": {}}, _wait_plan(), "down",
            {"basis_close_at": "2026-09-04T00:00:00+00:00"},
            forex_daily_plan.load_decision_policy(), Path("unused.webp"))
        figure = captured[0]
        assert figure._premium_header_card_layout["text"] == "NO TRADE / รอยืนยัน"
        assert figure._premium_axis_layout["central_decision_card_count"] == 0


def test_m15_contract_supports_synthetic_future_asset_without_visual_code_change(monkeypatch):
    asset = "nzdusd_future_fixture"
    profile = {"symbol": "NZD/USD", "digits": 5, "decimals": 5,
               "chart_decimals": 5}
    monkeypatch.setattr(forex_daily_plan.wcb_source, "profile_for",
                        lambda candidate: profile if candidate == asset else
                        forex_daily_plan.wcb_source.profile_for(candidate))
    for plan, preferred in ((_neutral_plan(), None), (_active_plan("BUY"), "up")):
        captured = _capture(monkeypatch)
        forex_daily_plan.save_m15_chart(
            asset, _rows(), "I", {"I": {}}, copy.deepcopy(plan), preferred,
            {"basis_close_at": "2026-09-04T00:00:00+00:00"},
            forex_daily_plan.load_decision_policy(), Path("unused.webp"))
        assert captured[0]._premium_axis_layout["central_decision_card_count"] == 0
        texts = _visible_specs(captured[0])
        expected_entry = (1.38473 if preferred is None else 1.3841)
        formatter = forex_daily_plan.chart_price_formatter(asset)
        assert any(f"Entry {formatter(expected_entry)}" in item.get_text()
                   for item in texts)


def test_m15_resolver_uses_injected_formatter_for_future_precision():
    formatter = lambda value: f"{float(value):.7f}"
    contract = forex_daily_plan.resolve_m15_visual_contract(
        "future_without_profile", _active_plan("BUY"), "up",
        price_formatter=formatter)
    assert contract["specs"][0]["text"] == "BUY Entry 1.3841000"
    assert contract["specs"][1]["text"] == "SL 1.3820000"
    assert contract["specs"][2]["text"] == "TP1 1.3860000"


def test_m15_visual_policy_has_no_asset_slug_branch():
    module = Path(forex_daily_plan.__file__).read_text(encoding="utf-8")
    tree = ast.parse(module)
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef)
                    and node.name == "save_m15_chart")
    source = ast.get_source_segment(module, function)
    assert "asset ==" not in source
    assert "asset in" not in source
    assert "asset not in" not in source
    assert "usdcad_neutral_oco" not in source


@pytest.mark.parametrize("broken", [
    {"active": False, "direction": None, "side": "OCO", "plans": []},
    dict(_neutral_plan(), plans=[_neutral_plan()["plans"][0]]),
    dict(_active_plan(), side="OCO"),
    dict(_active_plan(), plans=[dict(_active_plan()["plans"][0],
                                    trigger={"value": float("nan")})]),
])
def test_m15_malformed_semantic_state_fails_closed(broken):
    with pytest.raises(forex_daily_plan.M15VisualContractError):
        forex_daily_plan.resolve_m15_visual_contract("future_asset", broken, None)


def test_m15_render_does_not_mutate_semantic_payload(monkeypatch):
    plan = _neutral_plan()
    before = copy.deepcopy(plan)
    captured = _capture(monkeypatch)
    forex_daily_plan.save_m15_chart(
        "eurusd", _rows(), "NO_SETUP", {"I": {}}, plan, None,
        {"basis_close_at": "2026-09-04T00:00:00+00:00"},
        forex_daily_plan.load_decision_policy(), Path("unused.webp"))
    assert plan == before
    assert {leg["side"] for leg in plan["plans"]} == {"BUY", "SELL"}
    assert all(leg["stop_loss"] and len(leg["take_profit"]) == 2
               for leg in plan["plans"])
