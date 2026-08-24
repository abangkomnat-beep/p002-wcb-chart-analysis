"""One F+ Markdown shape for trade and No-trade selections."""
from __future__ import annotations

import re

from fixtures.fplus.contract_support import load_json, require_module


REQUIRED_SECTIONS = (
    "สรุปแผนวันนี้", "Bias H4", "Setup H1", "Evidence M30", "Trigger M15",
    "เงื่อนไขยกเลิก", "ข่าว",
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
    plan = load_json("selected_no_trade.json")
    markdown = writer.render_markdown(plan)
    assert "No-trade" in markdown or "งดเทรด" in markdown
    assert "NEWS_GATE_UNPROVEN" not in markdown, "internal reason code must not leak to public copy"
    deny = re.compile(r"\b(?:Entry|SL|TP1?|Stop Loss|Take Profit)\b", re.IGNORECASE)
    assert not deny.search(markdown)
    assert "รอแท่งปิดยืนยันใหม่" in markdown


def test_writer_is_deterministic_and_does_not_mutate_selected_plan():
    writer = require_module("tools.fplus_writer")
    plan = load_json("selected_trade.json")
    before = repr(plan)
    assert writer.render_markdown(plan) == writer.render_markdown(plan)
    assert repr(plan) == before

