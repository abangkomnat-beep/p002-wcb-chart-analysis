"""Independent contracts for manual BTCUSD Style E+ H1/M15."""

from __future__ import annotations

import importlib
import json
import math
import os
from copy import deepcopy
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
    h1, m15 = rows(minutes=60, last_close=95.0), b100_m15_rows(side, m15_close)
    indicators = h1_indicators(side, **overrides)
    with (mock.patch.object(story_module, "_indicator_contract", return_value=indicators),
          mock.patch.object(story_module, "_m15_indicator_contract",
                            return_value=m15_indicators())):
        story = story_module.build(
            h1, m15, candle_basis=basis(h1, "1h"),
            m15_candle_basis=basis(m15, "15min"),
            publish_date="2026-08-25", now=NOW)
    return story, h1, m15


def b100_m15_rows(side: str, last_close: float) -> list[dict]:
    """Build rows whose canonical decision window has accepted B target space."""
    output = rows(minutes=15, last_close=last_close)
    base = len(output) - 23
    if side == "buy":
        # Relative pivot 14, raw risk = 2 ATR with the mocked ATR=8/entry=92.
        for index, value in zip((base + 12, base + 13, base + 14,
                                 base + 15, base + 16),
                                (80.0, 79.0, 78.0, 79.0, 80.0)):
            output[index]["low"] = value
        output[base + 5]["high"] = 130.0
    else:
        # Relative pivot 14, raw risk = 2 ATR with entry=88.
        for index, value in zip((base + 12, base + 13, base + 14,
                                 base + 15, base + 16),
                                (100.0, 101.0, 102.0, 101.0, 100.0)):
            output[index]["high"] = value
        output[base + 5]["low"] = 50.0
    return output


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
    assert story["schema"] == "style-e-plus-story/v4"
    assert story["timeframe"] == "1h/15min"
    assert story["candle_basis"]["h1"]["timeframe"] == "1h"
    assert story["candle_basis"]["m15"]["timeframe"] == "15min"
    assert story["candle_basis"]["h1"]["candle_state"] == "closed"
    assert story["candle_basis"]["m15"]["candle_state"] == "closed"
    assert len(set(story["images"].values())) == 2
    assert story["adaptive_context"]["count"] == 23
    assert story["adaptive_context"]["window"]["decision_at"] == story["m15_bar_at"]


@pytest.mark.parametrize(("side", "close", "state", "has_plan"), [
    ("buy", 87.0, "WAIT_TRIGGER", True),
    ("buy", 91.0, "ENTRY_READY", True),
    ("buy", 93.0, "NO_CHASE", False),
    ("sell", 93.0, "WAIT_TRIGGER", True),
    ("sell", 89.0, "ENTRY_READY", True),
    ("sell", 87.0, "NO_CHASE", False),
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


def test_legacy_pinned_v3_a_geometry_is_preserved_as_baseline_characterization():
    """Pinned v3/A reference only; this is not a current production assertion."""
    expected = {
        "buy": {"trigger": 90.0, "entry_zone_low": 88.0, "entry_zone_high": 92.0,
                "pre_entry_invalidation_close": 80.0, "disadvantaged_entry": 92.0,
                "risk": 12.0, "tp1": 110.0, "tp2": 116.0},
        "sell": {"trigger": 90.0, "entry_zone_low": 88.0, "entry_zone_high": 92.0,
                 "pre_entry_invalidation_close": 100.0, "disadvantaged_entry": 88.0,
                 "risk": 12.0, "tp1": 70.0, "tp2": 64.0},
    }
    for side, close in (("buy", 87.0), ("sell", 93.0)):
        indicators = m15_indicators()
        atr = indicators["atr"]["value"]
        ema20 = indicators["ema20"]
        zone_low, zone_high = ema20 - 0.25 * atr, ema20 + 0.25 * atr
        entry = zone_high if side == "buy" else zone_low
        stop = zone_low - atr if side == "buy" else zone_high + atr
        risk = abs(entry - stop)
        actual = {
            "trigger": ema20, "entry_zone_low": zone_low,
            "entry_zone_high": zone_high,
            "pre_entry_invalidation_close": stop,
            "disadvantaged_entry": entry, "risk": risk,
            "tp1": entry + (1 if side == "buy" else -1) * 1.5 * risk,
            "tp2": entry + (1 if side == "buy" else -1) * 2.0 * risk,
        }
        for key, value in expected[side].items():
            assert actual[key] == pytest.approx(value)


def test_v4_b_plan_geometry_tamper_is_rejected_by_recomputation():
    story_module = module("tools.style_e_plus_story")
    story, _, _ = built("buy", 87.0)
    tampered = json.loads(json.dumps(story))
    tampered["plan"]["tp2"] += 0.01
    with pytest.raises(story_module.StoryUnavailable):
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
    h1, m15 = rows(minutes=60, last_close=95.0), b100_m15_rows(side, close)
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
    assert story["bias_reason"] not in markdown
    assert "สภาพความผันผวน" in markdown and "ยังไม่สนับสนุนการยืนยันแรงเบรกเอาต์" in markdown
    assert "ภาพที่ 2 BTC/USD M15 แสดงราคาปิดและ EMA20 โดยไม่มีแผนเทรด" in markdown
    assert "ภาพที่ 2 แผนเข้าเทรด BTC/USD M15 พร้อมระดับยกเลิก" not in markdown
    assert writer.validate(markdown, story, now=NOW)["ok"]


def test_copy_contract_uses_natural_status_h1_and_data_derived_m15_copy():
    writer = module("tools.style_e_plus_writer")
    story, _, _ = built("buy", 87.0, bbw_percentile=49.99, atr_percentile=20.0)
    markdown = writer.render_article(story)

    assert "**สถานะวันนี้:** **NO_PLAN (เน้นเฝ้าระวัง – ยังไม่มีจุดเข้าเทรด)**" in markdown
    assert "แนะนำให้พักมือ" in markdown
    assert "**ทิศทางแรงซื้อขาย:**" in markdown
    assert "**สภาพความผันผวน:**" in markdown
    assert "**กรอบแนวรับ-แนวต้าน H1:**" in markdown
    assert "**ข้อสรุป:**" not in markdown
    assert "ตามเกณฑ์ของระบบรอบนี้ ความผันผวนยังไม่สนับสนุนการยืนยันแรงเบรกเอาต์" in markdown
    assert story["bias_reason"] not in markdown
    assert "M15 ปิดล่าสุดที่ 87.00 ดอลลาร์ อยู่ต่ำกว่าเส้น EMA20 (90.00 ดอลลาร์)" in markdown


def test_daily_watch_datetime_is_bangkok_local_and_fails_closed_without_timezone():
    writer = module("tools.style_e_plus_writer")
    assert writer._thai_datetime("2026-08-27T01:00:00Z") == "27 ส.ค. 2026 (08:00 น.)"
    assert writer._thai_datetime("2026-08-27T08:00:00+07:00") == "27 ส.ค. 2026 (08:00 น.)"
    with pytest.raises(module("tools.style_e_plus_story").StoryUnavailable, match="timezone"):
        writer._thai_datetime("2026-08-27 08:00:00")


@pytest.mark.parametrize(("percentile", "formatted", "branch"), [
    (49.99, "49.99%", "ต่ำกว่าเกณฑ์ 50%"),
    (50.00, "50.00%", "ผ่านเกณฑ์ 50%"),
    (50.01, "50.01%", "ผ่านเกณฑ์ 50%"),
])
def test_h1_percentile_precision_matches_threshold_branch(percentile, formatted, branch):
    writer = module("tools.style_e_plus_writer")
    story, _, _ = built("buy", 87.0, bbw_percentile=percentile,
                        atr_percentile=percentile)
    markdown = writer.render_article(story)
    assert markdown.count(formatted) >= 2
    assert branch in markdown
    assert writer._pct(23.5) == "23.5%"


@pytest.mark.parametrize(("close", "expected"), [
    (90.0, "อยู่ใกล้เส้น EMA20"),
    (93.0, "อยู่เหนือเส้น EMA20"),
    (87.0, "อยู่ต่ำกว่าเส้น EMA20"),
])
def test_m15_ema_copy_is_derived_from_close_and_ema(close, expected):
    writer = module("tools.style_e_plus_writer")
    story, _, _ = built("buy", close)
    markdown = writer.render_article(story)
    assert expected in markdown


@pytest.mark.parametrize(("side", "close", "state"), [
    ("buy", 93.0, "NO_CHASE"),
    ("buy", 87.0, "WAIT_TRIGGER"), ("buy", 91.0, "ENTRY_READY"),
    ("sell", 87.0, "NO_CHASE"),
    ("sell", 93.0, "WAIT_TRIGGER"), ("sell", 89.0, "ENTRY_READY"),
])
def test_writer_state_matrix_keeps_reasons_once_and_copy_truthful(side, close, state):
    writer = module("tools.style_e_plus_writer")
    story, _, _ = built(side, close)
    markdown = writer.render_article(story)

    assert story["state"] == state
    assert writer.validate(markdown, story, now=NOW)["ok"]
    assert markdown.count(story["decision_reason"]) == 1
    h1_section = markdown.split("## " + writer.STATE_HEADINGS[story["state"]][1], 1)[1].split("\n![", 1)[0]
    assert story["bias_reason"] not in h1_section
    assert "ข้อสรุป H1:" not in markdown
    assert "**ข้อสรุป:**" not in markdown
    assert "**ทิศทางแรงซื้อขาย:**" in markdown
    assert "**สภาพความผันผวน:**" in markdown
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
        assert "ยังไม่มีจุดเข้าเทรด" in markdown or "งดไล่ราคา" in markdown
        if state == "NO_PLAN":
            assert "## เหตุผลที่ไม่มีแผนเทรด M15" in markdown
            assert "ยังไม่เข้าเงื่อนไขการสร้างแผนเทรด M15" in markdown
            assert "เนื่องจากH1" not in markdown
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


# ---------------------------------------------------------------------------
# RED contracts for the approved BTCUSD Adaptive Stop B100 migration.
# These tests intentionally name the production-owned pure helper boundary
# selected by the plan.  They must not import the isolated research harness.
# ---------------------------------------------------------------------------


def _adaptive_module():
    return module("tools.style_e_plus_adaptive_stop")


def b100_rows(*, side: str = "buy", pivot_price: float | None = None) -> list[dict]:
    """Small deterministic closed M15 fixture with one eligible pivot."""
    output = []
    start = datetime(2026, 8, 1)
    for index in range(60):
        at = start + timedelta(minutes=15 * index)
        base = 100.0
        output.append({
            "at": at.isoformat(), "open": base, "high": 110.0,
            "low": 99.0, "close": base, "forming": False,
        })
    if side == "sell":
        for row in output:
            row.update({"high": 101.0, "low": 90.0})
    # 2L/2R strict pivot at index 26; all other rows are flat.
    if side == "buy":
        for index, value in zip((24, 25, 26, 27, 28), (98.0, 97.5,
                                                          pivot_price or 96.0,
                                                          97.5, 98.0)):
            output[index]["low"] = value
    else:
        for index, value in zip((24, 25, 26, 27, 28), (102.0, 102.5,
                                                          pivot_price or 104.0,
                                                          102.5, 102.0)):
            output[index]["high"] = value
    return output


@pytest.mark.parametrize(("side", "expected"), [
    ("buy", {"index": 26, "price": 96.0, "confirmed_index": 28,
             "left": 2, "right": 2}),
    ("sell", {"index": 26, "price": 104.0, "confirmed_index": 28,
              "left": 2, "right": 2}),
])
def test_b100_pure_pivot_matches_locked_research_equivalence(side, expected):
    adaptive = _adaptive_module()
    assert adaptive.confirmed_pivot(
        b100_rows(side=side), decision_index=30, side=side) == expected


def test_b100_pivot_is_strict_past_only_and_lookback_is_20_bars():
    adaptive = _adaptive_module()
    tied = b100_rows()
    tied[25]["low"] = tied[26]["low"]
    assert adaptive.confirmed_pivot(tied, decision_index=30, side="buy") is None
    old = b100_rows()
    assert adaptive.confirmed_pivot(old, decision_index=47, side="buy") is None
    changed_future = deepcopy(b100_rows())
    for row in changed_future[31:]:
        row.update({"high": 999.0, "low": 1.0, "close": 500.0})
    assert adaptive.confirmed_pivot(
        changed_future, decision_index=30, side="buy") == adaptive.confirmed_pivot(
            b100_rows(), decision_index=30, side="buy")


@pytest.mark.parametrize(("raw_atr", "accepted", "risk_atr", "reason"), [
    (1.999, True, 2.0, None), (2.0, True, 2.0, None),
    (3.0, True, 3.0, None), (3.001, False, None, "STOP_GT_3ATR"),
])
def test_b100_risk_floor_and_cap_have_locked_tolerance(raw_atr, accepted,
                                                        risk_atr, reason):
    adaptive = _adaptive_module()
    result = adaptive.bounded_adaptive_risk(raw_atr * 10.0, atr=10.0)
    assert result["accepted"] is accepted
    if accepted:
        assert result["risk_atr"] == pytest.approx(risk_atr)
    assert result.get("reason") == reason


@pytest.mark.parametrize(("space_r", "accepted"), [(1.499, False), (1.5, True)])
def test_b100_donchian_target_space_boundary_is_exact(space_r, accepted):
    adaptive = _adaptive_module()
    assert adaptive.target_space_check(
        side="buy", entry=100.0, boundary=100.0 + space_r * 2.0,
        risk=2.0)["accepted"] is accepted
    assert adaptive.target_space_check(
        side="sell", entry=100.0, boundary=100.0 - space_r * 2.0,
        risk=2.0)["accepted"] is accepted


@pytest.mark.parametrize(("side", "entry_low", "entry_high", "expected"), [
    ("buy", 99.5, 100.5, {"entry": 100.5, "stop": 95.5,
                           "risk_atr": 2.5, "raw_stop": 95.5}),
    ("sell", 99.5, 100.5, {"entry": 99.5, "stop": 104.5,
                            "risk_atr": 2.5, "raw_stop": 104.5}),
])
def test_b100_plan_uses_confirmed_swing_buffer_and_exact_tp_geometry(
        side, entry_low, entry_high, expected):
    adaptive = _adaptive_module()
    result = adaptive.adaptive_plan(
        b100_rows(side=side), decision_index=30, side=side,
        entry_low=entry_low, entry_high=entry_high, atr=2.0)
    assert result["accepted"] is True
    plan = result["plan"]
    for key, value in expected.items():
        assert plan[key] == pytest.approx(value)
    assert plan["tp1"] == pytest.approx(
        plan["entry"] + (1 if side == "buy" else -1) * 1.5 * plan["risk"])
    assert plan["tp2"] == pytest.approx(
        plan["entry"] + (1 if side == "buy" else -1) * 2.0 * plan["risk"])
    assert plan["pivot"]["confirmed_index"] <= 30
    assert plan["prefix_end_index"] == 30


def test_b100_rejects_missing_swing_with_machine_reason():
    adaptive = _adaptive_module()
    no_swing = b100_rows()
    for row in no_swing:
        row["low"] = 99.0
    assert adaptive.adaptive_plan(
        no_swing, decision_index=30, side="buy", entry_low=99.5,
        entry_high=100.5, atr=2.0)["reason"] == "NO_CONFIRMED_SWING"


def test_b100_rejects_stop_over_cap_with_machine_reason():
    adaptive = _adaptive_module()
    cap = b100_rows(pivot_price=80.0)
    assert adaptive.adaptive_plan(
        cap, decision_index=30, side="buy", entry_low=99.5,
        entry_high=100.5, atr=2.0)["reason"] == "STOP_GT_3ATR"


def test_b100_rejects_tight_donchian_target_space_with_machine_reason():
    adaptive = _adaptive_module()
    tight = b100_rows()
    for row in tight[10:30]:
        row["high"] = 102.0
    assert adaptive.adaptive_plan(
        tight, decision_index=30, side="buy", entry_low=99.5,
        entry_high=100.5, atr=2.0)["reason"] == "TARGET_SPACE_LT_1_5R"


@pytest.mark.parametrize(("pivot_price", "expected_multiplier"), [
    (97.0, 0.75), (96.0, 0.60), (95.0, 0.50),
])
def test_b100_sizing_is_dimensionless_and_normalizes_to_a(
        pivot_price, expected_multiplier):
    adaptive = _adaptive_module()
    result = adaptive.adaptive_plan(
        b100_rows(pivot_price=pivot_price), decision_index=30, side="buy",
        entry_low=99.5, entry_high=100.5, atr=2.0)
    assert result["accepted"] is True
    plan = result["plan"]
    assert plan["risk_atr"] in (2.0, 2.5, 3.0)
    assert plan["sizing_multiplier"] == pytest.approx(expected_multiplier)
    assert plan["normalized_risk_ratio"] <= 1.0 + 1e-12
    assert "btc" not in plan and "quantity" not in plan and "usd" not in plan


def test_b100_story_is_schema_v4_with_exact_canonical_context23():
    story, _, m15 = built("buy", 87.0)
    assert story["schema"] == "style-e-plus-story/v4"
    context = story["adaptive_context"]
    assert set(context) == {"schema", "timeframe", "candle_state", "count",
                            "window", "rows", "sha256"}
    assert context["schema"] == "style-e-plus-adaptive-context/v1"
    assert context["timeframe"] == "15min"
    assert context["candle_state"] == "closed"
    assert context["count"] == 23
    assert len(context["rows"]) == 23
    assert context["window"]["start_at"] == context["rows"][0]["at"]
    assert context["window"]["decision_at"] == context["rows"][-1]["at"]
    assert context["rows"][-1]["at"].endswith("Z")
    assert context["rows"] == sorted(context["rows"], key=lambda row: row["at"])
    assert len(context["sha256"]) == 64
    assert all(set(row) == {"at", "open", "high", "low", "close"}
               for row in context["rows"])
    assert all(isinstance(row[key], str) and "e" not in row[key].lower()
               for row in context["rows"] for key in ("open", "high", "low", "close"))


@pytest.mark.parametrize("mutation", [
    lambda story: story["adaptive_context"]["rows"].__setitem__(
        10, {**story["adaptive_context"]["rows"][10], "close": 1.0}),
    lambda story: story["adaptive_context"]["rows"].reverse(),
    lambda story: story["adaptive_context"]["rows"].append(
        {"at": "2026-08-25T12:15:00+00:00", "open": 1, "high": 2,
         "low": 0, "close": 1}),
    lambda story: story["adaptive_context"].__setitem__("sha256", "0" * 64),
    lambda story: story["plan"].__setitem__("sizing_multiplier", 0.9),
])
def test_b100_validator_recomputes_context_and_rejects_every_tamper(mutation):
    story, _, _ = built("buy", 87.0)
    mutation(story)
    with pytest.raises(module("tools.style_e_plus_story").StoryUnavailable):
        module("tools.style_e_plus_story").validate_story(story, now=NOW)


def test_b100_validator_rejects_tp2_tamper_below_one_nanounit():
    story, _, _ = built("buy", 87.0)
    story["plan"]["tp2"] += 5e-10
    with pytest.raises(module("tools.style_e_plus_story").StoryUnavailable):
        module("tools.style_e_plus_story").validate_story(story, now=NOW)


def test_b100_validator_rejects_missing_accepted_audit_metadata():
    story, _, _ = built("buy", 87.0)
    story["adaptive_stop"]["risk_atr"] = None
    with pytest.raises(module("tools.style_e_plus_story").StoryUnavailable):
        module("tools.style_e_plus_story").validate_story(story, now=NOW)


@pytest.mark.parametrize("state", ["NO_PLAN", "NO_CHASE", "WAIT_TRIGGER", "ENTRY_READY"])
def test_b100_lifecycle_keeps_manual_only_and_no_ghost_levels(state):
    story, _, _ = built("buy", 87.0)
    assert story["schema"] == "style-e-plus-story/v4"
    story["state"] = state
    if state in {"NO_PLAN", "NO_CHASE"}:
        story["plan"] = None
    assert story["lifecycle"] == {
        "mode": "manual_analysis_only",
        "external_fill_evidence_accepted": False,
        "position_confirmed": False,
        "protective_stop_active": False,
    }
    if state in {"NO_PLAN", "NO_CHASE"}:
        assert story["plan"] is None
