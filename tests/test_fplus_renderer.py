"""Single composite WebP contract; renderer consumes rather than recalculates."""
from __future__ import annotations

from pathlib import Path
from copy import deepcopy

from PIL import Image

from fixtures.fplus.contract_support import load_json, require_module, valid_snapshot


NO_TRADE_CANDIDATE_DECISIONS = [
    {
        "candidate": "J",
        "eligible": False,
        "state": "blocked",
        "reason_codes": ["J_CONTRACT_NOT_CONFIRMED"],
        "gate_results": {"candidate": "fail", "risk": "pass"},
        "evidence_refs": ["series.4h.latest_bar_close_at_utc"],
    },
    {
        "candidate": "I",
        "eligible": False,
        "state": "blocked",
        "reason_codes": ["I_BREAKOUT_NOT_CONFIRMED"],
        "gate_results": {"candidate": "fail", "risk": "pass"},
        "evidence_refs": ["series.1h.latest_bar_close_at_utc"],
    },
    {
        "candidate": "E_LOGIC",
        "eligible": False,
        "state": "blocked",
        "reason_codes": ["E_LOGIC_NOT_CONFIRMED"],
        "gate_results": {"candidate": "fail", "risk": "pass"},
        "evidence_refs": ["series.30min.latest_bar_close_at_utc"],
    },
    {
        "candidate": "F",
        "eligible": False,
        "state": "blocked",
        "reason_codes": ["F_RANGE_EDGE_NOT_CONFIRMED"],
        "gate_results": {"candidate": "fail", "risk": "fail"},
        "evidence_refs": ["calendar.available", "series.15min.latest_bar_close_at_utc"],
    },
]

NO_TRADE_GATE_REPORT = {
    "data": {"status": "pass", "reason_codes": []},
    "news": {"status": "pass", "reason_codes": []},
    "reason_codes": [],
}


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
    renderer.render_webp(
        plan,
        valid_snapshot(),
        target,
        candidate_decisions=deepcopy(NO_TRADE_CANDIDATE_DECISIONS),
        gate_report=deepcopy(NO_TRADE_GATE_REPORT),
    )
    assert target.is_file()
    metadata = renderer.describe_render(plan)
    assert metadata["selection"] == "NO_TRADE"
    assert metadata["trade_levels"] == []

    with Image.open(target) as image:
        assert image.format == "WEBP"
        assert (image.width, image.height) == (1200, 675)
    assert target.stat().st_size <= 204_800


def test_no_trade_renderer_summary_lines_are_deterministic_and_have_no_levels(tmp_path, monkeypatch):
    renderer = require_module("tools.fplus_renderer")
    plan = load_json("selected_no_trade.json")
    decisions = deepcopy(NO_TRADE_CANDIDATE_DECISIONS)
    gates = deepcopy(NO_TRADE_GATE_REPORT)
    first = tmp_path / "first.webp"
    second = tmp_path / "second.webp"

    first_drawn_text: list[str] = []
    original_text = renderer.ImageDraw.ImageDraw.text

    def capture_text(self, xy, text, *args, **kwargs):
        first_drawn_text.append(str(text))
        return original_text(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(renderer.ImageDraw.ImageDraw, "text", capture_text)

    renderer.render_webp(plan, valid_snapshot(), first, candidate_decisions=decisions, gate_report=gates)
    first_summary = list(first_drawn_text)
    first_drawn_text.clear()
    renderer.render_webp(plan, valid_snapshot(), second, candidate_decisions=decisions, gate_report=gates)

    assert first.read_bytes() == second.read_bytes()
    assert first_summary == first_drawn_text
    assert any("J: ยังไม่ยืนยัน" in line for line in first_summary)
    assert any("I: ยังไม่ยืนยัน" in line for line in first_summary)
    assert any("E_LOGIC: ยังไม่ยืนยัน" in line for line in first_summary)
    assert any("F: ยังไม่ยืนยัน" in line for line in first_summary)
    assert any("รอการยืนยัน" in line for line in first_summary)
    assert any("ประเมินใหม่" in line for line in first_summary)
    for internal_code in (
        "J_CONTRACT_NOT_CONFIRMED",
        "I_BREAKOUT_NOT_CONFIRMED",
        "E_LOGIC_NOT_CONFIRMED",
        "F_RANGE_EDGE_NOT_CONFIRMED",
    ):
        assert internal_code not in "\n".join(first_summary)
    assert not any(
        token in "\n".join(first_summary).lower()
        for token in ("entry", "stop", "target", "price", "rr", "ราคา")
    )
    assert renderer.describe_render(plan)["trade_levels"] == []


def test_no_trade_renderer_actual_gate_shape_shows_data_gate_pass(tmp_path, monkeypatch):
    renderer = require_module("tools.fplus_renderer")
    plan = load_json("selected_no_trade.json")
    target = tmp_path / "actual-gate-shape.webp"
    gate_report = {
        "data": {"price_data_status": "pass", "reason_codes": []},
        "news": {"status": "pass", "reason_codes": []},
    }
    drawn: list[str] = []
    original_text = renderer.ImageDraw.ImageDraw.text

    def capture_text(self, xy, text, *args, **kwargs):
        drawn.append(str(text))
        return original_text(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(renderer.ImageDraw.ImageDraw, "text", capture_text)
    renderer.render_webp(
        plan,
        valid_snapshot(),
        target,
        candidate_decisions=deepcopy(NO_TRADE_CANDIDATE_DECISIONS),
        gate_report=gate_report,
    )
    summary = "\n".join(drawn)
    assert "data gate: ผ่าน | news gate: ผ่าน" in summary
    assert "data gate: ไม่พบผล gate/risk เฉพาะ" not in summary


def test_renderer_does_not_reselect_candidate_or_change_plan_numbers(tmp_path):
    renderer = require_module("tools.fplus_renderer")
    plan = load_json("selected_trade.json")
    metadata = renderer.describe_render(plan)
    assert metadata["selection"] == "J"
    assert metadata["entry_zone"] == plan["entry_zone"]
    assert metadata["stop_loss"] == plan["stop_loss"]
    assert metadata["take_profit_1"] == plan["take_profit_1"]
