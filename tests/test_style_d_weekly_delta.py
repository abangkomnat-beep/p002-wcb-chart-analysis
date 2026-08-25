import json
import difflib
import re
import tempfile
from pathlib import Path

import pytest

from tools import chart_story, chart_story_writer, style_d_weekly_delta


REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_ROWS = json.loads(
    (REPO_ROOT / "tests" / "fixtures" / "xau_420_sessions_2026-08-07.json")
    .read_text(encoding="utf-8"))


def _story(*, publish_date="2026-08-24", close=4603.92, down=False,
           zone=(3942.19, 4039.38, 3990.79), resistance=4773.50,
           touches=5):
    low, high, mean = zone
    return {
        "asset": "xauusd", "publish_date": publish_date,
        "current": {"date": publish_date, "close": close},
        "atr14": 95.0, "sma50_last": 4172.70, "sma200_last": 4010.0,
        "regime": {"down": down},
        "channel": {"main_is_upper": down, "locked_since": "2026-08-18"},
        "zones": [{"low": low, "high": high, "mean": mean,
                   "touches": touches, "locked_since": "2026-08-07"}],
        "resistance": [{"mean": resistance, "touches": 2,
                        "locked_since": "2026-08-21"}],
    }


def test_first_round_is_baseline_and_next_week_compares_with_it():
    first_delta, first_state = style_d_weekly_delta.prepare(
        _story(publish_date="2026-08-24", close=4603.92), None)
    second_delta, second_state = style_d_weekly_delta.prepare(
        _story(publish_date="2026-08-31", close=4775.00), first_state)

    assert first_delta["status"] == "baseline"
    assert second_delta["status"] == "comparison"
    assert second_delta["previous"]["close"] == 4603.92
    assert second_delta["close_change"] == pytest.approx(171.08)
    assert second_state["previous_week"] == first_state["current_week"]


def test_same_week_rerun_keeps_previous_week_as_baseline():
    _, week_one = style_d_weekly_delta.prepare(
        _story(publish_date="2026-08-17", close=4376.56, down=True), None)
    _, week_two = style_d_weekly_delta.prepare(
        _story(publish_date="2026-08-24", close=4603.92), week_one)
    rerun_delta, rerun_state = style_d_weekly_delta.prepare(
        _story(publish_date="2026-08-25", close=4610.00), week_two)

    assert rerun_delta["status"] == "comparison"
    assert rerun_delta["previous"]["close"] == 4376.56
    assert rerun_state["previous_week"]["close"] == 4376.56


def test_skipped_week_and_backfill_become_safe_baselines():
    _, state = style_d_weekly_delta.prepare(
        _story(publish_date="2026-08-17"), None)
    skipped, _ = style_d_weekly_delta.prepare(
        _story(publish_date="2026-09-07"), state)
    backfill, _ = style_d_weekly_delta.prepare(
        _story(publish_date="2026-08-10"), state)

    assert skipped["status"] == "baseline"
    assert backfill["status"] == "baseline"


def test_delta_detects_regime_and_level_changes_without_changing_story():
    _, first = style_d_weekly_delta.prepare(
        _story(publish_date="2026-08-17", down=True, resistance=4558.48), None)
    current = _story(publish_date="2026-08-24", down=False, resistance=4773.50)
    delta, _ = style_d_weekly_delta.prepare(current, first)

    assert delta["regime_changed"] is True
    assert delta["zone_status"] == "unchanged"
    assert delta["resistance_status"] == "changed"
    assert delta["change_count"] >= 2
    assert current["resistance"][0]["mean"] == 4773.50


def test_state_io_is_atomic_and_corruption_falls_back_to_none():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _, state = style_d_weekly_delta.prepare(_story(), None)
        path = style_d_weekly_delta.save("xauusd", state, root)

        assert style_d_weekly_delta.load("xauusd", root) == state
        assert list(root.glob("*.tmp")) == []
        path.write_text("{broken", encoding="utf-8")
        assert style_d_weekly_delta.load("xauusd", root) is None


def test_config_switch_accepts_only_known_modes():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "writing.json"
        path.write_text(json.dumps({"schema": "style-d-writing-v1",
                                    "mode": "weekly_delta"}), encoding="utf-8")
        assert style_d_weekly_delta.load_mode(path) == "weekly_delta"
        path.write_text(json.dumps({"schema": "style-d-writing-v1",
                                    "mode": "random_words"}), encoding="utf-8")
        try:
            style_d_weekly_delta.load_mode(path)
        except style_d_weekly_delta.WeeklyDeltaConfigError:
            pass
        else:
            raise AssertionError("unknown mode must fail closed")


def _weekly_story():
    story = chart_story.build_story(
        REAL_ROWS, asset="xauusd", publish_date="2026-08-24")
    # ล็อกเคส regression ที่เคยเกิดจริง: current เป็นขาขึ้น แต่ writer เดิมยังพิมพ์
    # ว่า "มุมมองขาลงเดิมยังไม่เปลี่ยน" ในหัวข้อกรณีขาขึ้น
    story["regime"]["down"] = False
    previous = style_d_weekly_delta.snapshot(story)
    previous.update({
        "week_start": "2026-08-17", "week_end": "2026-08-21",
        "publish_date": "2026-08-17", "close": story["current"]["close"] * 0.95,
        "regime_down": True,
    })
    state = {"schema": style_d_weekly_delta.STATE_SCHEMA, "asset": "xauusd",
             "previous_week": None, "current_week": previous}
    delta, _ = style_d_weekly_delta.prepare(story, state)
    story["weekly_delta"] = delta
    return story


def test_weekly_writer_leads_with_changes_and_removes_repeated_support_theory():
    story = _weekly_story()
    markdown = chart_story_writer.render_article(story)
    validation = chart_story_writer.validate(markdown, story)

    assert f"## {chart_story_writer.H2_WEEKLY_DELTA}" in markdown
    assert "แนวรับหลักยังไม่เปลี่ยน" in markdown
    assert "แนวรับที่ถูกทดสอบหลายครั้งอาจเหลือแรงซื้อน้อยลง" not in markdown
    assert "มุมมองขาลงเดิมยังไม่เปลี่ยน" not in markdown
    assert markdown.count("ราคาปิดล่าสุดยังอยู่เหนือโซน") <= 1
    assert validation["status"] == "pass", validation["findings"]


def test_weekly_writer_is_materially_different_from_legacy_without_random_words():
    story = _weekly_story()
    weekly = chart_story_writer.render_article(story)
    legacy_story = json.loads(json.dumps(story))
    legacy_story.pop("weekly_delta")
    legacy = chart_story_writer.render_article(legacy_story)

    normalize = lambda text: re.sub(r"\s+", " ", re.sub(r"\d[\d,.:-]*", "#", text))
    similarity = difflib.SequenceMatcher(None, normalize(weekly), normalize(legacy)).ratio()
    assert similarity <= 0.85


def test_direction_gate_rejects_current_regime_contradiction():
    story = _weekly_story()
    markdown = chart_story_writer.render_article(story)
    contradiction = ("ภาพรายวันยังอยู่ในแนวโน้มขาขึ้น"
                     if story["regime"]["down"]
                     else "มุมมองขาลงเดิมยังไม่เปลี่ยน")
    broken = markdown + "\n" + contradiction
    findings = chart_story_writer.validate(broken, story)["findings"]

    assert any(item["rule"] == "direction_language_conflict" for item in findings)
