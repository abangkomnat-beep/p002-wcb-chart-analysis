from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from tools import forex_daily_calendar_renderer, forex_daily_plan


CUTOFF = datetime(2026, 9, 3, 2, 35, 16, tzinfo=timezone.utc)


def _plan(side: str = "SELL", status: str = "WAIT_TRIGGER") -> dict:
    return {
        "schema": forex_daily_plan.STYLE_L_PLAN_SCHEMA,
        "side": side,
        "status": status,
        "current_close": 1.34813,
        "cutoff_at": "2026-09-03T09:35:16+07:00",
        "valid_until": "2026-09-04T09:35:16+07:00",
        "evidence_hash": "a" * 64,
        "plans": [{
            "side": side,
            "trigger": {"condition": "M15_CLOSE_BELOW", "value": 1.34914},
            "entry_zone": {"low": 1.34914, "high": 1.34914},
            "stop_loss": 1.35018,
            "take_profit": [1.34810, 1.34707],
            "risk_reward": [1.0, 1.9904],
            "invalidation": {"condition": "H1_CLOSE_ABOVE", "value": 1.35223},
        }],
    }


def test_daily_event_filter_uses_article_day_pair_currencies_and_medium_high_only():
    events = [
        {"at": "2026-09-03 09:00", "country": "GBP", "impact": "High", "title": "GBP"},
        {"at": "2026-09-03 10:00", "country": "USD", "impact": "Medium", "title": "USD"},
        {"at": "2026-09-03 11:00", "country": "CAD", "impact": "High", "title": "CAD"},
        {"at": "2026-09-03 12:00", "country": "GBP", "impact": "Low", "title": "Low"},
        {"at": "2026-09-04 09:00", "country": "USD", "impact": "High", "title": "Tomorrow"},
    ]
    selected = forex_daily_plan.daily_relevant_events("gbpusd", events, CUTOFF)
    assert [event["title"] for event in selected] == ["GBP", "USD"]
    assert {event["country"] for event in selected} == {"GBP", "USD"}


def test_calendar_pagination_and_height_are_deterministic_and_bounded():
    events = [
        {"at": f"2026-09-03 {9 + index:02d}:00", "country": "USD",
         "impact": "Medium", "title": "ข่าวเศรษฐกิจ " + ("ยาวมาก " * 14)}
        for index in range(8)
    ]
    first = forex_daily_calendar_renderer.paginate_events(events)
    second = forex_daily_calendar_renderer.paginate_events(events)
    assert first == second
    assert len(first) > 1
    assert [item for page in first for item in page] == events
    for page in first:
        height, units = forex_daily_calendar_renderer.calendar_height(page)
        assert forex_daily_calendar_renderer.MIN_HEIGHT_PX <= height <= forex_daily_calendar_renderer.MAX_HEIGHT_PX
        assert sum(units) <= forex_daily_calendar_renderer.MAX_PAGE_UNITS


def test_calendar_status_and_important_numbers_follow_cutoff_and_feed_only():
    cutoff = datetime(2026, 9, 3, 13, 0, tzinfo=timezone.utc)  # 20:00 Bangkok
    future = {"at": "2026-09-03 21:00", "actual": None,
              "forecast": "54.3 จุด", "previous": "54.1 จุด"}
    complete = {"at": "2026-09-03 19:30", "actual": "205 พันราย",
                "forecast": "204 พันราย", "previous": "203 พันราย"}
    actual_only = {"at": "2026-09-03 19:30", "actual": "51.2",
                   "forecast": None, "previous": None}
    no_numbers = {"at": "2026-09-03 19:30", "actual": None,
                  "forecast": None, "previous": None}
    currency_unit = {"at": "2026-09-03 19:30", "actual": None,
                     "forecast": "3.6C$", "previous": "3.86C$"}
    assert forex_daily_calendar_renderer.event_status(future, cutoff) == "รอประกาศ"
    assert forex_daily_calendar_renderer.event_status(complete, cutoff) == "ประกาศแล้ว"
    assert forex_daily_calendar_renderer.important_numbers(future) == (
        "คาด 54.3 จุด · ก่อนหน้า 54.1 จุด")
    assert forex_daily_calendar_renderer.important_numbers(complete) == (
        "จริง 205 พันราย · คาด 204 พันราย · ก่อนหน้า 203 พันราย")
    assert forex_daily_calendar_renderer.important_numbers(actual_only) == "จริง 51.2"
    assert forex_daily_calendar_renderer.important_numbers(no_numbers) == "ไม่มีตัวเลขคาดการณ์"
    assert forex_daily_calendar_renderer.important_numbers(currency_unit) == (
        "คาด 3.6C$ · ก่อนหน้า 3.86C$")


def test_calendar_render_is_dynamic_one_line_and_web_safe(tmp_path: Path):
    events = [
        {"at": "2026-09-03 19:30", "country": "USD", "impact": "High",
         "title": "ยอดขอรับสวัสดิการว่างงานครั้งแรก",
         "actual": None, "forecast": "205 พันราย", "previous": "203 พันราย"},
        {"at": "2026-09-03 21:00", "country": "GBP", "impact": "Medium",
         "title": "ดัชนีผู้จัดการฝ่ายจัดซื้อภาคบริการ",
         "actual": "51.2", "forecast": "50.8", "previous": "50.5"},
        {"at": "2026-09-03 22:00", "country": "USD", "impact": "Medium",
         "title": "คำสั่งซื้อภาคโรงงาน", "actual": None, "forecast": None,
         "previous": "0.7%"},
    ]
    rendered = forex_daily_calendar_renderer.render_daily_calendar(
        asset="gbpusd", symbol="GBP/USD", article_date="2026-09-03",
        events=events, output_dir=tmp_path,
        cutoff=datetime(2026, 9, 3, 13, 0, tzinfo=timezone.utc))
    assert len(rendered) == 1
    info = rendered[0]
    assert info["canvas"][0] == 1920
    assert 600 <= info["canvas"][1] <= 700
    assert info["date_time_one_line"] is True
    assert info["clipped"] is False
    assert info["cell_mathtext_disabled"] is True
    assert info["rows"] == 3
    assert info["kb"] <= 200
    assert info["columns"] == [
        "วันที่และเวลาไทย", "สกุลเงิน", "ระดับ", "ข่าว", "สถานะ", "ตัวเลขสำคัญ"]
    assert not {"Actual", "Forecast", "Previous"} & set(info["columns"])
    assert info["display_rows"][0][4:] == [
        "ประกาศแล้ว", "คาด 205 พันราย · ก่อนหน้า 203 พันราย"]
    assert info["display_rows"][1][4:] == [
        "รอประกาศ", "จริง 51.2 · คาด 50.8 · ก่อนหน้า 50.5"]
    assert info["display_rows"][2][4:] == [
        "รอประกาศ", "ก่อนหน้า 0.7%"]
    with Image.open(info["path"]) as image:
        assert image.size == tuple(info["canvas"])


def test_long_important_numbers_increase_row_units_without_breaking_pagination():
    short = {"title": "ข่าว", "forecast": "1", "previous": "2"}
    long = {"title": "ข่าว", "forecast": "หน่วยข้อมูลเศรษฐกิจที่ยาวมาก " * 8,
            "previous": "ฐานเปรียบเทียบที่ยาวมาก " * 8}
    assert forex_daily_calendar_renderer.event_row_units(long) > (
        forex_daily_calendar_renderer.event_row_units(short))
    pages = forex_daily_calendar_renderer.paginate_events([long, long, long])
    assert [event for page in pages for event in page] == [long, long, long]


def test_continuity_hides_without_prior_successful_output(tmp_path: Path):
    current, summary = forex_daily_plan.continuity_snapshot(
        "gbpusd", CUTOFF, "down", _plan(), [],
        published_root=tmp_path / "output", internal_root=tmp_path / "work" / "build")
    assert current["date"] == "2026-09-03"
    assert current["entry_zone"] == {"low": 1.34914, "high": 1.34914}
    assert summary is None


def test_continuity_uses_prior_successful_date_and_ignores_same_day(tmp_path: Path):
    output = tmp_path / "output"
    internal = tmp_path / "work" / "build"
    previous_article = output / "01-09-2026" / forex_daily_plan.STYLE_FOLDER / "gbpusd.md"
    previous_article.parent.mkdir(parents=True)
    previous_article.write_text("prior published article", encoding="utf-8")
    previous_hash = hashlib.sha256(previous_article.read_bytes()).hexdigest()
    prior = {
        "qa_status": "PASS_QA", "publishable": True, "side": "SELL",
        "plan_status": "WAIT_TRIGGER", "cutoff_at": "2026-09-01T14:39:59+07:00",
        "valid_until": "2026-09-02T14:39:59+07:00", "evidence_hash": "b" * 64,
        "article_sha256": previous_hash,
        "plans": [{"side": "SELL", "trigger": {"condition": "M15_CLOSE_BELOW", "value": 1.35357},
                   "entry_zone": {"low": 1.35357, "high": 1.35357},
                   "stop_loss": 1.35448, "take_profit": [1.35266, 1.35176],
                   "invalidation": {"condition": "H1_CLOSE_ABOVE", "value": 1.35652}}],
    }
    sidecar = internal / "01-09-2026" / "gbpusd" / "internal" / "style-l" / "gbpusd.trade-plan-public.json"
    sidecar.parent.mkdir(parents=True)
    sidecar.write_text(json.dumps(prior), encoding="utf-8")
    same_day = internal / "03-09-2026" / "gbpusd" / "internal" / "style-l" / "gbpusd.trade-plan-public.json"
    same_day.parent.mkdir(parents=True)
    same_day.write_text(json.dumps({**prior, "cutoff_at": "2026-09-03T08:00:00+07:00"}), encoding="utf-8")
    rows = [
        {"at": "2026-09-01 15:00:00", "open": 1.3538, "high": 1.3539,
         "low": 1.3530, "close": 1.3532},
        {"at": "2026-09-01 15:15:00", "open": 1.3532, "high": 1.3533,
         "low": 1.3516, "close": 1.3517},
    ]
    _, summary = forex_daily_plan.continuity_snapshot(
        "gbpusd", CUTOFF, "down", _plan(), rows,
        published_root=output, internal_root=internal)
    assert summary["baseline_date"] == "2026-09-01"
    assert "SELL" in summary["previous"]
    assert summary["result"] == "Completed"
    assert "2026-09-03T08:00:00+07:00" not in json.dumps(summary)


def test_prior_plan_ambiguous_bar_fails_closed():
    prior = _plan()
    prior["cutoff_at"] = "2026-09-01T09:00:00+07:00"
    prior["valid_until"] = "2026-09-02T09:00:00+07:00"
    row = {"at": "2026-09-01 10:00:00", "open": 1.3493, "high": 1.3505,
           "low": 1.3470, "close": 1.3480}
    assert forex_daily_plan.evaluate_prior_plan(prior, [row]) == "ประเมินผลไม่ได้จากแท่งปิด"
