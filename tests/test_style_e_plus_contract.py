"""Independent contracts for manual BTCUSD Style E+ H1/M15."""

from __future__ import annotations

import importlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
EPLUS_MODULES = (
    "tools.style_e_plus_story", "tools.style_e_plus_writer",
    "tools.style_e_plus_renderer", "tools.style_e_plus_pipeline",
)


def module(name: str):
    return importlib.import_module(name)


def rows(*, minutes: int, count: int = 260, last_close: float = 90.0) -> list[dict]:
    start = datetime(2026, 8, 1)
    output = []
    for index in range(count):
        close = 88.0 + index * 0.005 + math.sin(index / 6.0)
        opened = close - 0.18
        at = start + timedelta(minutes=minutes * index)
        output.append({
            "date": at.strftime("%Y-%m-%d"), "at": at.strftime("%Y-%m-%d %H:%M:%S"),
            "at_feed": at.strftime("%Y-%m-%d %H:%M:%S"),
            "open": opened, "high": max(opened, close) + 0.55,
            "low": min(opened, close) - 0.55, "close": close, "forming": False,
        })
    output[-1].update({"open": last_close - 0.2, "high": last_close + 0.6,
                       "low": last_close - 0.7, "close": last_close})
    return output


def basis(source: list[dict], timeframe: str) -> dict:
    from tools import intraday_bars
    return intraday_bars.basis_for(
        "btcusd", source[-1]["at"], timeframe=timeframe, now=NOW)


def h1_indicators(side: str = "buy", *, adx: float = 25.0,
                  bbw_percentile: float = 70.0,
                  atr_percentile: float = 80.0) -> dict:
    plus_di, minus_di = ((30.0, 18.0) if side == "buy" else (18.0, 30.0))
    return {
        "donchian": {"length": 20, "upper": 100.0, "lower": 80.0,
                     "middle": 90.0, "width": 20.0, "excludes_signal_bar": True},
        "atr": {"length": 14, "value": 8.0, "previous": 7.8, "rising": True,
                "percentile": atr_percentile, "percentile_samples": 200},
        "keltner": {"ema_length": 20, "atr_length": 14, "multiplier": 1.5,
                    "middle": 90.0, "upper": 95.0, "lower": 85.0},
        "bbw": {"length": 20, "stdev": 2.0, "value": 4.2, "previous": 4.0,
                "rising": True, "percentile": bbw_percentile,
                "percentile_samples": 200},
        "dmi_adx": {"length": 14, "plus_di": plus_di, "minus_di": minus_di,
                    "adx": adx, "previous_adx": adx - 0.5,
                    "direction": "up" if side == "buy" else "down"},
    }


def m15_indicators() -> dict:
    return {
        "ema20": 90.0,
        "atr": {"length": 14, "value": 8.0, "previous": 8.2, "rising": False,
                "percentile": 65.0, "percentile_samples": 200},
        "donchian": {"length": 20, "upper": 98.0, "lower": 82.0,
                     "middle": 90.0, "width": 16.0, "excludes_signal_bar": True},
    }


def built(side: str, m15_close: float, **overrides):
    story_module = module("tools.style_e_plus_story")
    h1, m15 = rows(minutes=60, last_close=95.0), rows(minutes=15, last_close=m15_close)
    indicators = h1_indicators(side, **overrides)
    with (mock.patch.object(story_module, "_indicator_contract", return_value=indicators),
          mock.patch.object(story_module, "_m15_indicator_contract",
                            return_value=m15_indicators())):
        story = story_module.build(
            h1, m15, candle_basis=basis(h1, "1h"),
            m15_candle_basis=basis(m15, "15min"),
            publish_date="2026-08-25", now=NOW)
    return story, h1, m15


def test_daily_route_registers_eplus_inside_the_e_family():
    run_daily = (ROOT / "tools" / "run_daily.py").read_text(encoding="utf-8").lower()
    assert 'style_e = "e"' in run_daily and "e_plus_h1_m15" in run_daily
    registry = json.loads((ROOT / "config" / "article_styles.json").read_text(encoding="utf-8"))
    assert registry["styles"]["e_indicator"]["assets"] == ["btcusd", "xauusd", "usdjpy"]
    assert registry["styles"]["e_indicator"]["timeframes"] == ["1h", "15min"]
    assert registry["styles"]["e_indicator"]["asset_variants"]["btcusd"]["folder"] == \
        "E+-แผนเทรด-H1-M15"


def test_imports_have_zero_network_or_working_directory_side_effects():
    probe = r'''
import importlib, json, pathlib, socket, urllib.request
network = []
def blocked(*args, **kwargs):
    network.append(repr(args[:1])); raise AssertionError("network during import")
urllib.request.urlopen = blocked; socket.create_connection = blocked
before = sorted(p.name for p in pathlib.Path.cwd().iterdir())
for name in json.loads(__import__("os").environ["MODULES"]): importlib.import_module(name)
after = sorted(p.name for p in pathlib.Path.cwd().iterdir())
assert network == [] and after == before
'''
    with tempfile.TemporaryDirectory() as folder:
        env = os.environ.copy()
        env.update({"PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1",
                    "MODULES": json.dumps(EPLUS_MODULES)})
        completed = subprocess.run(
            [sys.executable, "-c", probe], cwd=folder, env=env,
            capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_story_carries_two_closed_candle_bases_and_two_unique_images():
    story, _, _ = built("buy", 87.0)
    assert story["schema"] == "style-e-plus-story/v3"
    assert story["timeframe"] == "1h/15min"
    assert story["candle_basis"]["h1"]["timeframe"] == "1h"
    assert story["candle_basis"]["m15"]["timeframe"] == "15min"
    assert story["candle_basis"]["h1"]["candle_state"] == "closed"
    assert story["candle_basis"]["m15"]["candle_state"] == "closed"
    assert len(set(story["images"].values())) == 2


@pytest.mark.parametrize(("side", "close", "state", "has_plan"), [
    ("buy", 87.0, "WAIT_TRIGGER", True),
    ("buy", 91.0, "ENTRY_READY", True),
    ("buy", 93.0, "NO_CHASE", False),
    ("buy", 79.0, "NO_PLAN", False),
    ("sell", 93.0, "WAIT_TRIGGER", True),
    ("sell", 89.0, "ENTRY_READY", True),
    ("sell", 87.0, "NO_CHASE", False),
    ("sell", 101.0, "NO_PLAN", False),
])
def test_m15_state_matrix_under_h1_bias(side, close, state, has_plan):
    story, _, _ = built(side, close)
    assert story["state"] == state and story["side"] == side
    assert (story["plan"] is not None) is has_plan


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_exact_m15_ema_trigger_remains_wait(side):
    story, _, _ = built(side, 90.0)
    assert story["state"] == "WAIT_TRIGGER"
    assert story["plan"]["trigger_confirmed"] is False


def test_plan_geometry_is_recomputed_from_m15_ema_and_atr():
    expected = {
        "buy": {"trigger": 90.0, "entry_zone_low": 88.0, "entry_zone_high": 92.0,
                "pre_entry_invalidation_close": 80.0, "disadvantaged_entry": 92.0,
                "risk": 12.0, "tp1": 110.0, "tp2": 116.0},
        "sell": {"trigger": 90.0, "entry_zone_low": 88.0, "entry_zone_high": 92.0,
                 "pre_entry_invalidation_close": 100.0, "disadvantaged_entry": 88.0,
                 "risk": 12.0, "tp1": 70.0, "tp2": 64.0},
    }
    story_module = module("tools.style_e_plus_story")
    for side, close in (("buy", 87.0), ("sell", 93.0)):
        story, _, _ = built(side, close)
        for key, value in expected[side].items():
            assert story["plan"][key] == pytest.approx(value)
        assert story["plan"]["protective_stop"] == {
            "price": pytest.approx(expected[side]["pre_entry_invalidation_close"]),
            "active": False,
            "status": "inactive_until_external_fill",
            "activation_event": "external_entry_fill",
            "effective_from": None,
        }
        assert "stop_loss" not in story["plan"]
        tampered = json.loads(json.dumps(story))
        tampered["plan"]["tp2"] += 0.01
        with pytest.raises(story_module.StoryUnavailable, match="plan.tp2"):
            story_module.validate_story(tampered, now=NOW)


@pytest.mark.parametrize(("side", "close"), [("buy", 91.0), ("sell", 89.0)])
def test_entry_ready_never_claims_position_or_active_protective_stop(side, close):
    story, _, _ = built(side, close)
    assert story["state"] == "ENTRY_READY"
    assert story["lifecycle"] == {
        "mode": "manual_analysis_only",
        "external_fill_evidence_accepted": False,
        "position_confirmed": False,
        "protective_stop_active": False,
    }
    assert story["plan"]["protective_stop"]["active"] is False
    assert story["plan"]["plan_created_at"] == story["plan"]["effective_from"]
    assert story["plan"]["effective_from"] == story["candle_basis"]["m15"]["basis_close_at"]


@pytest.mark.parametrize(("side", "close", "extreme_key", "extreme"), [
    ("buy", 91.0, "low", 79.0),
    ("sell", 89.0, "high", 101.0),
])
def test_creation_bar_intrabar_extreme_cannot_activate_new_stop(
        side, close, extreme_key, extreme):
    story_module = module("tools.style_e_plus_story")
    h1, m15 = rows(minutes=60, last_close=95.0), rows(minutes=15, last_close=close)
    m15[-1][extreme_key] = extreme
    with (mock.patch.object(story_module, "_indicator_contract",
                            return_value=h1_indicators(side)),
          mock.patch.object(story_module, "_m15_indicator_contract",
                            return_value=m15_indicators())):
        story = story_module.build(
            h1, m15, candle_basis=basis(h1, "1h"),
            m15_candle_basis=basis(m15, "15min"),
            publish_date="2026-08-25", now=NOW)
    assert story["state"] == "ENTRY_READY"
    assert story["plan"]["protective_stop"]["active"] is False
    assert story["lifecycle"]["position_confirmed"] is False


def test_tampered_lifecycle_or_stop_activation_fails_closed():
    story_module = module("tools.style_e_plus_story")
    story, _, _ = built("buy", 91.0)
    tampered = json.loads(json.dumps(story))
    tampered["plan"]["protective_stop"]["active"] = True
    with pytest.raises(story_module.StoryUnavailable, match="protective_stop"):
        story_module.validate_story(tampered, now=NOW)
    tampered = json.loads(json.dumps(story))
    tampered["lifecycle"]["position_confirmed"] = True
    with pytest.raises(story_module.StoryUnavailable, match="lifecycle"):
        story_module.validate_story(tampered, now=NOW)


@pytest.mark.parametrize("override", [
    {"adx": 19.99}, {"bbw_percentile": 49.99}, {"atr_percentile": 49.99},
])
def test_weak_h1_context_never_exposes_m15_trade_levels(override):
    story, _, _ = built("buy", 87.0, **override)
    assert story["state"] == "NO_PLAN" and story["side"] is None and story["plan"] is None
    markdown = module("tools.style_e_plus_writer").render_article(story)
    assert all(term not in markdown for term in
               ("Entry Zone):", "Protective Stop ตามแผน):", "TP1):", "TP2):"))


def test_no_plan_copy_uses_exact_bias_reason_and_planless_image_alt():
    writer = module("tools.style_e_plus_writer")
    story, _, _ = built("buy", 87.0, bbw_percentile=49.99)
    markdown = writer.render_article(story)

    assert story["state"] == "NO_PLAN" and story["side"] is None
    assert story["bias_reason"] in markdown
    assert "ภาพที่ 2 BTC/USD M15 แสดงราคาปิดและ EMA20 โดยไม่มีแผนเทรด" in markdown
    assert "ภาพที่ 2 แผนเข้าเทรด BTC/USD M15 พร้อมระดับยกเลิก" not in markdown
    assert writer.validate(markdown, story, now=NOW)["ok"]


@pytest.mark.parametrize(("side", "close", "state"), [
    ("buy", 79.0, "NO_PLAN"), ("buy", 93.0, "NO_CHASE"),
    ("buy", 87.0, "WAIT_TRIGGER"), ("buy", 91.0, "ENTRY_READY"),
    ("sell", 101.0, "NO_PLAN"), ("sell", 87.0, "NO_CHASE"),
    ("sell", 93.0, "WAIT_TRIGGER"), ("sell", 89.0, "ENTRY_READY"),
])
def test_writer_state_matrix_keeps_reasons_once_and_copy_truthful(side, close, state):
    writer = module("tools.style_e_plus_writer")
    story, _, _ = built(side, close)
    markdown = writer.render_article(story)

    assert story["state"] == state
    assert writer.validate(markdown, story, now=NOW)["ok"]
    assert markdown.count(story["bias_reason"]) == 1
    assert markdown.count(story["decision_reason"]) == 1
    assert "ข้อสรุป H1:" not in markdown
    assert "**ข้อสรุป:**" in markdown
    assert "Volume" not in markdown
    assert "Pin Bar" not in markdown
    assert "Mean Reversion" not in markdown
    assert "ยืนยันว่าแนวโน้มมีแรง" not in markdown
    assert "เกณฑ์ขั้นต่ำของระบบ" in markdown
    assert "โซนเข้าซื้อที่ปลอดภัย" not in markdown
    assert "แม้ทิศทางจะเป็นเทรนด์" not in markdown
    assert "รอการจับคู่ Order" not in markdown
    if state in {"NO_PLAN", "NO_CHASE"}:
        assert story["plan"] is None
        assert all(term not in markdown for term in
                   ("Entry Zone):", "Protective Stop ตามแผน):", "TP1):", "TP2):",
                    "Risk/Reward", "R)"))
        assert "ยังไม่มีแผน M15" in markdown or "งดไล่ราคา" in markdown
        if state == "NO_PLAN":
            assert "## เหตุผลที่ไม่มีแผนเทรด M15" in markdown
            assert "ยังไม่เข้าเงื่อนไขการสร้างแผนเทรด M15" in markdown
        else:
            assert f"Entry Zone สำหรับฝั่ง {side.upper()}" in markdown
    else:
        assert story["plan"] is not None
        assert "Entry Zone" in markdown and "Protective Stop" in markdown
        assert ("ต่ำกว่าขอบล่าง" if side == "buy" else "สูงกว่าขอบบน") in markdown
        assert ("ขอบบนของโซน" if side == "buy" else "ขอบล่างของโซน") in markdown
        assert "ข้อมูลยืนยันการเปิดสถานะจริง (Fill)" in markdown
        assert "หากราคาไปถึง TP1" not in markdown
        assert "ระบบจะเปลี่ยนเป็น NO_CHASE" in markdown
        if state == "WAIT_TRIGGER":
            assert "ปิดสมบูรณ์ (Candle Close)" in markdown
            assert "การแตะระดับระหว่างแท่งยังไม่ถือว่าเกิด Trigger" in markdown
        if state == "ENTRY_READY":
            assert "เงื่อนไข Trigger ครบถ้วน" in markdown


def test_writer_validator_rejects_forbidden_content_even_when_story_is_valid():
    writer = module("tools.style_e_plus_writer")
    story, _, _ = built("buy", 87.0)
    markdown = writer.render_article(story)
    tampered = markdown + "\nVolume และ backtest ให้ผลดีที่สุด"
    report = writer.validate(tampered, story, now=NOW)
    assert not report["ok"]
    assert any(item["rule"] == "forbidden_term" for item in report["findings"])


def test_article_is_action_first_has_two_images_and_no_emoji_or_numbered_h2():
    writer = module("tools.style_e_plus_writer")
    story, _, _ = built("buy", 87.0)
    markdown = writer.render_article(story)
    report = writer.validate(markdown, story, now=NOW)
    assert report["ok"], report
    assert markdown.index("## แผน M15 วันนี้: รอยืนยันจุดเข้า") < markdown.index("## ภาพรวมตลาดและกรอบ H1")
    assert all(markdown.count(f"]({name})") == 1 for name in story["images"].values())
    assert "M15 Trigger" in markdown and "H1 Bias" in markdown
    assert not any(term in markdown for term in ("📌", "📈", "📉", "⚠", "✅", "❌"))
    assert not __import__("re").search(r"(?m)^##\s+\d+[.)]?\s", markdown)
