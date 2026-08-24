"""One F+ Markdown shape for trade and No-trade selections."""
from __future__ import annotations

import re

from copy import deepcopy

from fixtures.fplus.contract_support import load_json, require_module


REQUIRED_SECTIONS = (
    "สรุปแผนวันนี้", "Bias H4", "Setup H1", "Evidence M30", "Trigger M15",
    "เงื่อนไขยกเลิก", "ข่าว",
)


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


def no_trade_inputs():
    """Inline evidence fixture; production/output/state/config must stay untouched."""
    return (
        load_json("selected_no_trade.json"),
        deepcopy(NO_TRADE_CANDIDATE_DECISIONS),
        deepcopy(NO_TRADE_GATE_REPORT),
    )


def test_trade_writer_uses_one_fplus_template_and_selected_plan_numbers_only():
    writer = require_module("tools.fplus_writer")
    plan = load_json("selected_trade.json")
    markdown = writer.render_markdown(plan)
    assert markdown.startswith("---\n")
    for field in ("asset:", "title:", "excerpt:", "author:", "trade_date:",
                  "cutoff:", "timeframe_set:", "trend:"):
        assert field in markdown.split("---", 2)[1]
    for heading in REQUIRED_SECTIONS:
        assert heading in markdown
    for value in ("70000", "70100", "69500", "70820", "1.2"):
        assert value in markdown
    assert "F+" in markdown
    assert "Style E" not in markdown
    assert "สไตล์ H" not in markdown


def test_no_trade_writer_has_no_entry_stop_target_or_fake_plan_numbers():
    writer = require_module("tools.fplus_writer")
    plan, candidate_decisions, gate_report = no_trade_inputs()
    markdown = writer.render_markdown(
        plan,
        candidate_decisions=candidate_decisions,
        gate_report=gate_report,
    )
    assert "No-trade" in markdown or "งดเทรด" in markdown
    deny = re.compile(
        r"\b(?:Entry|SL|TP1?|Stop Loss|Take Profit|price)\b|ราคา",
        re.IGNORECASE,
    )
    assert not deny.search(markdown)
    assert "รอแท่งปิดยืนยันใหม่" in markdown
    assert "เหตุผลราย candidate" in markdown
    assert "สิ่งที่ต้องรอ" in markdown
    assert "เงื่อนไขประเมินใหม่" in markdown

    # Public copy must map evidence to human language without leaking internals.
    for internal_code in (
        "J_CONTRACT_NOT_CONFIRMED",
        "I_BREAKOUT_NOT_CONFIRMED",
        "E_LOGIC_NOT_CONFIRMED",
        "F_RANGE_EDGE_NOT_CONFIRMED",
    ):
        assert internal_code not in markdown
    assert "สัญญาณของ J ยังไม่ยืนยัน" in markdown
    assert "การเบรกเอาต์ของ I ยังไม่ยืนยัน" in markdown
    assert "ตรรกะของ E ยังไม่ยืนยัน" in markdown
    assert "ขอบช่วงของ F ยังไม่ยืนยัน" in markdown

    # Candidate explanations must follow the router's public order J → I → E_LOGIC → F.
    positions = [markdown.index(f"### {candidate}") for candidate in ("J", "I", "E_LOGIC", "F")]
    assert positions == sorted(positions)
    assert "สรุป risk/gate" in markdown
    assert "data gate" in markdown
    assert "news gate" in markdown


def test_no_trade_writer_missing_reason_data_falls_back_without_inventing_details():
    writer = require_module("tools.fplus_writer")
    plan, _candidate_decisions, _gate_report = no_trade_inputs()
    markdown = writer.render_markdown(
        plan,
        candidate_decisions=[
            {"candidate": name, "eligible": False, "state": "blocked"}
            for name in ("J", "I", "E_LOGIC", "F")
        ],
        gate_report={},
    )
    assert "ไม่พบเหตุผลเฉพาะใน snapshot นี้" in markdown
    assert "ไม่พบผล gate/risk เฉพาะ" in markdown
    assert "ข้อมูลไม่พอ" in markdown
    assert "No-trade" in markdown or "งดเทรด" in markdown
    assert not re.search(r"\b(?:Entry|SL|TP1?|Stop Loss|Take Profit|price)\b|ราคา", markdown, re.I)


def test_no_trade_writer_actual_gate_shape_shows_data_gate_pass():
    writer = require_module("tools.fplus_writer")
    plan = load_json("selected_no_trade.json")
    gate_report = {
        "data": {"price_data_status": "pass", "reason_codes": []},
        "news": {"status": "pass", "reason_codes": []},
    }
    markdown = writer.render_markdown(
        plan,
        candidate_decisions=deepcopy(NO_TRADE_CANDIDATE_DECISIONS),
        gate_report=gate_report,
    )
    assert "- data gate: ผ่าน" in markdown
    assert "- data gate: ไม่พบผล gate/risk เฉพาะ" not in markdown


def test_writer_is_deterministic_and_does_not_mutate_selected_plan():
    writer = require_module("tools.fplus_writer")
    plan = load_json("selected_trade.json")
    before = repr(plan)
    assert writer.render_markdown(plan) == writer.render_markdown(plan)
    assert repr(plan) == before
